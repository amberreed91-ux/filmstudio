from typing import Any, Optional, Callable, Awaitable
from datetime import datetime
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from copy import deepcopy
from urllib.parse import urlparse
from app.models import (
    RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset,
    ProviderConfig, ProviderStatus, StudioProject
)
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services.scene002_contract_only import is_contract_only as _is_contract_only
from app.adapters import RenderProviderAdapter, get_adapter, ADAPTER_REGISTRY
from app.config import get_settings
from app.prompt_assembly_context import preserve_generation_facts
from app.services.project_store import project_store
from app.services.stability import ProviderError, PersistenceError, StateError, log_stage_event
from app.services.character_name_matching import character_name_match_position
from app.services.reference_validation import validate_generation_payload
from app.utils.helpers import derive_scene_id_from_shot_id
import logging
import asyncio
from contextvars import ContextVar

logger = logging.getLogger("studio-render")

_queue_execution_fence: ContextVar[dict[str, Any] | None] = ContextVar("queue_execution_fence", default=None)


class QueueExecutionLeaseLost(RuntimeError):
    """Raised when a queue-backed render no longer owns its fencing token."""


def queue_execution_lease_is_current() -> bool:
    fence = _queue_execution_fence.get()
    if fence is None:
        return True
    storage = _storage
    checker = getattr(storage, "queue_lease_is_current", None) if storage is not None else None
    return bool(
        callable(checker)
        and checker(fence["queue_item_id"], fence["lease_owner"], fence["lease_generation"])
    )


def assert_queue_execution_lease_current() -> None:
    if not queue_execution_lease_is_current():
        raise QueueExecutionLeaseLost("Production queue lease was lost before render state or provider execution")


def _current_queue_execution_fence() -> dict[str, Any] | None:
    return _queue_execution_fence.get()

_CONTINUITY_CONTEXT_BLOCK = (
    "\n\n[CINEMATIC CONTEXT]"
    "\nEmotional register: {emotional_register}"
    "\nActive visual motifs: {active_motifs}"
    "\nTonal direction: {tonal_direction}"
    "\nContinuity anchors: {continuity_anchors}"
)

_ENVIRONMENT_CONTEXT_BLOCK = "\n\n[ENVIRONMENT CONTINUITY]\n{environment_lines}"

# WebSocket notification callback - will be set by main.py
_job_update_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None

# Database storage reference - will be set by main.py
_storage = None

# Job retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds, exponential backoff
STALE_RENDER_THRESHOLD_SECONDS = 15 * 60
PROVIDER_CALL_TIMEOUT_SECONDS = int(float(os.getenv("RENDER_PROVIDER_CALL_TIMEOUT_SECONDS", "310") or "310"))


async def _close_provider_adapter(adapter: RenderProviderAdapter | None) -> None:
    if adapter is None:
        return
    close = getattr(adapter, "close", None)
    if not callable(close):
        return
    result = close()
    if asyncio.iscoroutine(result):
        await result


def set_storage(storage):
    """Set the database storage"""
    global _storage
    _storage = storage


def set_job_update_callback(callback: Callable[[str, dict], Awaitable[None]]):
    """Set the WebSocket broadcast callback"""
    global _job_update_callback
    _job_update_callback = callback


async def _run_continuity_review(job: RenderJobModel) -> None:
    """
    Run advisory continuity review after a job completes.
    Attaches result to job.continuity_review and logs outcome.
    Never raises — silent fallback on any error.
    """
    from app.services.scene002_contract_only import is_contract_only
    if is_contract_only(job):
        return
    try:
        from app.services.continuity_intelligence_service import (
            continuity_intelligence_service as _cont_svc,
        )
        output_url = ""
        if job.output_payload:
            output_url = str(job.output_payload.asset_url or "").strip()
        # Derive scene_id from shot_id (e.g. "scene_001_shot_001" → "scene_001")
        shot_id = job.shot_id or ""
        scene_id = derive_scene_id_from_shot_id(shot_id)
        review = await _cont_svc.review_render_output(
            scene_id=scene_id,
            film_id=job.project_id,
            render_job_id=job.id,
            render_output_url=output_url,
            scene_data=(
                (job.metadata or {}).get("environment_continuity_context", {})
                if isinstance(job.metadata, dict)
                else {}
            ),
            shot_id=shot_id,
            prompt=(job.input_payload.prompt if job.input_payload else "") or "",
        )
        job.continuity_review = review
        if review.get("drift_detected"):
            logger.info(
                "CONTINUITY_DRIFT_DETECTED | scene=%s | job=%s | flags=%d",
                scene_id,
                job.id,
                len(review.get("continuity_flags") or []),
            )
        else:
            logger.info(
                "CONTINUITY_REVIEW_PASSED | scene=%s | job=%s",
                scene_id,
                job.id,
            )
    except Exception as exc:
        logger.debug("Continuity review skipped for job %s: %s", job.id, exc)


async def _run_render_quality_check(job: RenderJobModel) -> None:
    """
    Run prompt adherence and keyframe quality check after a job completes.
    Records result in render_attempts table for retry decision analysis.
    Never raises — silent fallback on any error.
    """
    from app.services.scene002_contract_only import is_contract_only
    if is_contract_only(job):
        return
    try:
        _set_zero_touch_phase(job, "evaluate", "running")
        _persist_job(job)
        from app.services.render_retry_service import render_retry_service
        
        output_url = ""
        if job.output_payload:
            output_url = str(job.output_payload.asset_url or "").strip()
        
        if not output_url:
            logger.debug("Skipping quality check for job %s: no output URL", job.id)
            _set_zero_touch_phase(job, "evaluate", "skipped", reason="no output URL")
            _set_zero_touch_phase(job, "retry", "skipped", reason="evaluation skipped")
            _persist_job(job)
            return

        _expected_slots = None
        try:
            _parameters = job.input_payload.parameters if job.input_payload else {}
            if isinstance(_parameters, dict):
                _slots = _parameters.get("prompt_slots")
                if isinstance(_slots, dict):
                    _expected_slots = {
                        str(_slot): str(_value or "")
                        for _slot, _value in _slots.items()
                    }
        except Exception:
            _expected_slots = None
        
        # Record the render attempt with quality analysis
        _qa_result = await render_retry_service.record_render_attempt(
            project_id=job.project_id,
            shot_id=job.shot_id,
            job_id=job.id,
            output_url=output_url,
            prompt=(job.input_payload.prompt if job.input_payload else "") or "",
            expected_slots=_expected_slots,
        )

        # ── Standing corrections lifecycle (Phase 4) ───────────────────
        # After adherence scoring completes and the attempt is persisted to
        # render_attempts, update hits/misses/confidence for any corrections
        # that were injected for this job_id.
        _sc_score_json = (
            _qa_result.get("score_json")
            if isinstance(_qa_result, dict) else None
        )
        if isinstance(_sc_score_json, dict):
            job.metadata = dict(job.metadata or {})
            job.metadata["adherence_review"] = {
                "verdict": _sc_score_json.get("verdict"),
                "failed_slots": _sc_score_json.get("failed_slots") or [],
                "advisory_note": _sc_score_json.get("advisory_note") or "",
                "outcome": _sc_score_json.get("outcome") or "",
            }
            _persist_job(job)

        if _sc_score_json:
            try:
                from app.services.standing_corrections_service import (
                    standing_corrections_service as _sc_svc,
                )
                _sc_svc.record_render_outcome(
                    project_id=job.project_id,
                    shot_id=job.shot_id,
                    job_id=job.id,
                    score_json=_sc_score_json,
                )
            except Exception as _sc_exc:
                logger.debug(
                    "Standing corrections lifecycle skipped for job %s: %s",
                    job.id, _sc_exc,
                )

        try:
            _parameters = job.input_payload.parameters if job.input_payload else {}
            _is_adherence_retry = bool(
                isinstance(_parameters, dict)
                and (
                    _parameters.get("retry_strategy")
                    or _parameters.get("adherence_retry_parent_job_id")
                )
            )
            _failed_slots = (
                _sc_score_json.get("failed_slots")
                if isinstance(_sc_score_json, dict) else []
            )
            _can_retry = (
                isinstance(_parameters, dict)
                and bool(_expected_slots)
                and bool(_failed_slots)
                and not _is_adherence_retry
            )
            if _can_retry:
                _max_retries = int(os.getenv("ADHERENCE_AUTO_RETRY_MAX", "2") or "2")
                _max_retries = max(0, min(_max_retries, 5))
                if _max_retries > 0:
                    _set_zero_touch_phase(
                        job,
                        "retry",
                        "running",
                        reason=_sc_score_json.get("mismatch_description", ""),
                        max_retries=_max_retries,
                    )
                    _retry_result = await render_retry_service.evaluate_and_select_best(
                        shot_id=job.shot_id,
                        project_id=job.project_id,
                        original_slots=_expected_slots,
                        max_attempts=_max_retries,
                        submission_strategy="combined_reorder_and_fresh_seeds",
                        source_job_id=job.id,
                        cascade_depth=1,
                    )
                    job.metadata = dict(job.metadata or {})
                    job.metadata["adherence_retry_cascade"] = {
                        "triggered": True,
                        "max_retries": _max_retries,
                        "source_job_id": job.id,
                        "jobs_submitted": _retry_result.get("jobs_submitted", []),
                        "mismatch_description": _sc_score_json.get("mismatch_description", ""),
                    }
                    _set_zero_touch_phase(
                        job,
                        "retry",
                        "complete",
                        jobs_submitted=_retry_result.get("jobs_submitted", []),
                    )
                    _persist_job(job)
                    logger.info(
                        "ADHERENCE_RETRY_CASCADE_TRIGGERED | job=%s | shot=%s | retries=%d | failed_slots=%s",
                        job.id,
                        job.shot_id,
                        _max_retries,
                        _failed_slots,
                    )
        except Exception as _retry_exc:
            _set_zero_touch_phase(job, "retry", "failed", error=str(_retry_exc))
            logger.debug(
                "Adherence retry cascade skipped for job %s: %s",
                job.id, _retry_exc,
            )

        _set_zero_touch_phase(job, "evaluate", "complete")
        if not (
            isinstance(job.metadata, dict)
            and isinstance(job.metadata.get("adherence_retry_cascade"), dict)
        ):
            _set_zero_touch_phase(job, "retry", "skipped", reason="no recoverable adherence mismatch")
        _persist_job(job)
        logger.info(
            "RENDER_QUALITY_CHECK_COMPLETE | job=%s | project=%s | shot=%s",
            job.id,
            job.project_id,
            job.shot_id,
        )
    except Exception as exc:
        _set_zero_touch_phase(job, "evaluate", "failed", error=str(exc))
        _persist_job(job)
        logger.debug("Render quality check skipped for job %s: %s", job.id, exc)


async def _run_character_reference_lock(job: RenderJobModel) -> None:
    """Lock first successful character visual references after render completion."""
    from app.services.scene002_contract_only import is_contract_only
    if is_contract_only(job):
        return
    try:
        storage = _storage
        if storage is None:
            from app.data.storage import get_storage

            storage = get_storage("sqlite")
        if storage is None:
            return
        from app.services.character_visual_reference_service import (
            character_visual_reference_service as _char_ref_svc,
        )

        # Verify identity BEFORE locking. Afterwards the job's own frames are in
        # the lock set and the comparison would include this render against
        # itself.
        identity_report = None
        try:
            identity_report = _char_ref_svc.verify_shot_identity(job=job, storage=storage)
        except Exception as verify_exc:
            logger.debug("Shot identity verification skipped for job %s: %s", job.id, verify_exc)

        locks = _char_ref_svc.lock_first_references_for_completed_job(
            job=job,
            storage=storage,
        )

        # Close the loop: a lock made from a mediocre frame stayed permanent
        # because a weak reference makes later shots more likely to fail, so
        # nothing ever promoted a better one. Only runs on a verified-consistent
        # render, and never over a director's explicit choice.
        upgraded = []
        try:
            upgraded = _char_ref_svc.upgrade_references_from_verified_job(
                job=job,
                storage=storage,
                identity_report=identity_report,
            )
        except Exception as upgrade_exc:
            logger.debug("Reference upgrade skipped for job %s: %s", job.id, upgrade_exc)

        if locks or identity_report or upgraded:
            job.metadata = dict(job.metadata or {})
            if locks:
                job.metadata["character_reference_locks_created"] = [
                    lock.model_dump(mode="json") for lock in locks
                ]
            if upgraded:
                job.metadata["character_reference_locks_upgraded"] = [
                    lock.model_dump(mode="json") for lock in upgraded
                ]
            if identity_report:
                job.metadata["character_identity_verification"] = identity_report
                if identity_report.get("status") == "identity_drift":
                    drifted = [
                        row.get("character_name") or row.get("character_id")
                        for row in identity_report.get("characters", [])
                        if row.get("status") == "identity_drift"
                    ]
                    logger.warning(
                        "CHARACTER_IDENTITY_DRIFT | job=%s | shot=%s | characters=%s | "
                        "measures_identity=%s",
                        job.id,
                        job.shot_id,
                        ", ".join(str(name) for name in drifted if name),
                        identity_report.get("measures_identity"),
                    )
            _persist_job(job)
    except Exception as exc:
        logger.debug("Character reference lock skipped for job %s: %s", job.id, exc)


async def _notify_update(job_id: str, job_data: dict):
    """Notify subscribers of job update"""
    if _job_update_callback:
        try:
            await _job_update_callback(job_id, job_data)
        except Exception as e:
            logger.error(f"Failed to notify job update: {e}")


def _persist_job(job: RenderJobModel) -> bool:
    """Persist job to database with error handling"""
    if _storage:
        try:
            fence = _current_queue_execution_fence()
            if fence is not None:
                _storage.save_job(job, queue_lease_fence=fence)
            else:
                _storage.save_job(job)
            return True
        except Exception as e:
            if queue_lease_fence := _current_queue_execution_fence():
                # Never suppress a failed fenced write or let it fall through to
                # the legacy project/FK repair path: either could leave runtime
                # state ahead of durable authoritative job state.
                if not queue_execution_lease_is_current():
                    persisted_job = _storage.get_job(job.id)
                    render_service = globals().get("render_service")
                    if render_service is not None:
                        if persisted_job is None:
                            render_service._jobs.pop(job.id, None)
                        else:
                            render_service._jobs[job.id] = persisted_job
                    raise QueueExecutionLeaseLost(
                        "Production queue lease was lost before render state could be persisted"
                    ) from e
                logger.error(
                    "Fenced render persistence failed job_id=%s queue_item_id=%s error=%s",
                    job.id,
                    queue_lease_fence["queue_item_id"],
                    e,
                )
                raise PersistenceError(
                    "Queue-fenced render job state could not be persisted",
                    stage="render_persistence",
                    metadata={"queue_item_id": queue_lease_fence["queue_item_id"]},
                ) from e
            error_text = str(e)
            from app.services.scene002_contract_only import is_contract_only
            if is_contract_only(job):
                logger.error("Protected render persistence failed without project recovery job=%s error=%s", job.id, error_text)
                return False
            if "FOREIGN KEY constraint failed" in error_text:
                parent_project_exists = False
                try:
                    parent_project_exists = _storage.get_project(job.project_id) is not None
                except Exception:
                    parent_project_exists = False
                logger.error(
                    "Render FK failure job_id=%s project_id=%s shot_id=%s parent_project_exists=%s error=%s",
                    job.id,
                    job.project_id,
                    job.shot_id,
                    parent_project_exists,
                    error_text,
                )
                try:
                    project = project_store.get_project(job.project_id)
                    if isinstance(project, dict):
                        from app.models import StudioProject
                        _storage.save_project(
                            StudioProject(
                                project_id=str(project.get("project_id") or job.project_id),
                                title=str(project.get("title") or job.project_id),
                                updated_at=str(project.get("updated_at") or datetime.now().isoformat()),
                            )
                        )
                        _storage.save_job(job)
                        logger.info("Recovered FK persistence for job %s by syncing project %s", job.id, job.project_id)
                        return True
                except Exception as retry_exc:
                    logger.error("FK recovery failed for job %s project %s: %s", job.id, job.project_id, retry_exc)
            metadata = dict(job.metadata or {})
            metadata["persistence_failure"] = {
                "error_type": "persistence_error",
                "message": error_text,
                "recorded_at": _now_iso(),
            }
            job.metadata = metadata
            _record_failure_location(
                job,
                phase="persist",
                reason=error_text,
                error_type="persistence_error",
                category="temporary",
            )
            logger.error(f"Failed to persist job {job.id}: {e}")
            return False
    return True


def _now_iso() -> str:
    return datetime.now().isoformat()


def _stable_request_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _request_idempotency_key(
    *,
    project_id: str,
    shot_id: str,
    provider: str,
    prompt: str,
    reference_assets: list[str] | None,
    parameters: dict[str, Any] | None,
) -> tuple[str, bool]:
    params = dict(parameters or {})
    explicit = str(params.get("idempotency_key") or params.get("request_id") or "").strip()
    if explicit:
        return explicit, True
    params.pop("zero_touch_debug", None)
    return _stable_request_hash(
        {
            "project_id": project_id,
            "shot_id": shot_id,
            "provider": provider,
            "prompt": prompt or "",
            "reference_assets": reference_assets or [],
            "parameters": params,
        }
    ), False


def _ensure_reliability_metadata(job: RenderJobModel) -> dict[str, Any]:
    if _is_contract_only(job):
        return dict((job.metadata or {}).get("pipeline_reliability") or {})
    metadata = dict(job.metadata or {})
    reliability = dict(metadata.get("pipeline_reliability") or {})
    correlation_id = str(reliability.get("correlation_id") or "").strip()
    if not correlation_id:
        correlation_id = f"corr-{uuid.uuid4().hex[:16]}"
    reliability.setdefault("correlation_id", correlation_id)
    reliability.setdefault("created_at", job.created_at or _now_iso())
    reliability.setdefault("phase_timing", {})
    metadata["pipeline_reliability"] = reliability
    job.metadata = metadata
    return reliability


def _record_failure_location(
    job: RenderJobModel,
    *,
    phase: str,
    reason: str,
    error_type: str = "",
    category: str = "",
) -> None:
    if _is_contract_only(job):
        return
    reliability = _ensure_reliability_metadata(job)
    reliability["failure_location"] = {
        "phase": phase,
        "reason": reason,
        "error_type": error_type,
        "category": category,
        "recorded_at": _now_iso(),
    }
    metadata = dict(job.metadata or {})
    metadata["pipeline_reliability"] = reliability
    job.metadata = metadata


def _log_audit(action: str, resource_type: str, resource_id: str, user_id: str = None, details: str = None):
    """Log audit event"""
    if _storage:
        try:
            # Would use storage.audit_log() in production
            logger.info(f"AUDIT: {action} {resource_type}:{resource_id} by {user_id} - {details}")
        except Exception as e:
            logger.error(f"Failed to log audit: {e}")


# ── Prompt-budget constants ─────────────────────────────────────────────────
# Runway (and most video providers) enforce a 512-character prompt limit.
_PROMPT_BUDGET = 512
_CINEMATIC_TAG = "Cinematic, film quality, single continuous shot."


def _extract_visual_action(text: str, max_chars: int = 280) -> str:
    """Extract visual action/description from scene text, stripping dialogue.

    Screenplay format has character names in ALL CAPS on their own line
    followed by dialogue.  Section headers (e.g. ``THE FIRST TIMELINE``)
    are also ALL CAPS but longer.  This helper keeps only the action
    paragraphs that describe what the camera sees — which is all that
    matters for a video-generation prompt.
    """
    import re as _re

    lines = text.split("\n")
    action_parts: list[str] = []
    skip_dialogue = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank line ends dialogue-skip mode
            skip_dialogue = False
            continue

        # ── Character cue detection ──────────────────────────────────────
        # Short ALL-CAPS line that looks like a character name.
        # Strip parentheticals like "(V.O.)" before testing.
        clean = _re.sub(r"\(.*?\)", "", stripped).strip().rstrip(".")
        is_char_cue = (
            len(stripped) < 35
            and len(clean) >= 2
            and clean.replace(" ", "").replace("'", "").isalpha()
            and clean.isupper()
            and not clean.startswith(("THE ", "ACT ", "INT ", "EXT ", "CUT ", "FADE"))
        )
        if is_char_cue:
            skip_dialogue = True
            continue

        # ── Skip dialogue lines following a character cue ────────────────
        if skip_dialogue:
            # Parenthetical stage direction — skip
            if stripped.startswith("(") and stripped.endswith(")"):
                continue
            # Dialogue text — skip (but a new ALL-CAPS cue resets)
            continue

        # ── Section headers (longer ALL-CAPS phrases) — skip ─────────────
        if stripped.isupper() and len(stripped) > 15:
            continue

        action_parts.append(stripped)

    result = " ".join(action_parts)
    from app.prompt_assembly_context import collecting_generation_prompt
    if not collecting_generation_prompt.get() and len(result) > max_chars:
        result = result[:max_chars]
        # Truncate at last word boundary for clean cutoff
        last_space = result.rfind(" ")
        if last_space > int(max_chars * 0.6):
            result = result[:last_space]

    return result.strip()


def _extract_initial_visual_beat(text: str, max_chars: int = 360) -> str:
    """Return the opening visual beat before dialogue or later scene business."""
    import re as _re

    paragraphs = [
        " ".join(line.strip() for line in chunk.splitlines() if line.strip()).strip()
        for chunk in _re.split(r"\n\s*\n", text)
    ]
    action_parts: list[str] = []
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped:
            continue
        clean = _re.sub(r"\(.*?\)", "", stripped).strip().rstrip(".")
        is_char_cue = (
            len(stripped) < 35
            and len(clean) >= 2
            and clean.replace(" ", "").replace("'", "").isalpha()
            and clean.isupper()
            and not clean.startswith(("THE ", "ACT ", "INT ", "EXT ", "CUT ", "FADE"))
        )
        if is_char_cue and action_parts:
            break
        if (
            stripped.isupper() and len(stripped) > 15
        ) or clean.upper().startswith(("INT ", "EXT ", "INT.", "EXT.")):
            continue
        action_parts.append(stripped)
        if len(action_parts) >= 2 or len(" ".join(action_parts)) >= max_chars:
            break

    result = " ".join(action_parts)
    from app.prompt_assembly_context import collecting_generation_prompt
    if not collecting_generation_prompt.get() and len(result) > max_chars:
        result = result[:max_chars]
        last_space = result.rfind(" ")
        if last_space > int(max_chars * 0.6):
            result = result[:last_space]
    return result.strip()


def _normalize_character_names(names: Any) -> list[str]:
    if isinstance(names, str):
        raw_names = [part.strip() for part in names.split(",")]
    elif isinstance(names, list):
        raw_names = [str(name).strip() for name in names]
    else:
        raw_names = []
    normalized: list[str] = []
    seen: set[str] = set()
    for name in raw_names:
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(name)
    return normalized


def _infer_scene_characters_from_text(
    all_characters: list[dict[str, Any]],
    *,
    primary_text: str,
    fallback_text: str,
) -> list[str]:
    """Infer visible cast from the shot action before falling back to the scene."""
    candidates: list[str] = []
    for text in (primary_text, fallback_text):
        text_lower = str(text or "").lower()
        if not text_lower:
            continue
        matches: list[tuple[int, str]] = []
        seen: set[str] = set()
        for character in all_characters:
            name = str(character.get("name") or "").strip()
            name_lower = name.lower()
            if not name or name_lower in seen:
                continue
            index = character_name_match_position(text_lower, name)
            if index is not None:
                seen.add(name_lower)
                matches.append((index, name))
        for _, name in sorted(matches, key=lambda item: item[0]):
            if name not in candidates:
                candidates.append(name)
        if candidates:
            return candidates
    return []


def _build_intent_fidelity(slotted: dict, shot_id: str) -> dict | None:
    """Compare the director's pre-budget slot text against the outgoing prompt.

    Runs before the render is submitted and never blocks it. Everything else in
    the pipeline measures the render against the prompt; this is the only check
    that measures the prompt against what was asked for.
    """
    try:
        from app.services.intent_fidelity_service import build_intent_fidelity_report

        if not isinstance(slotted, dict):
            return None
        report = build_intent_fidelity_report(
            source_slots=slotted.get("source_slots"),
            final_slots=slotted.get("slots"),
            prompt=str(slotted.get("prompt") or ""),
            shot_id=shot_id,
            defaulted_slots=slotted.get("defaulted_slots"),
        )
        if report.get("status") == "reduced":
            logger.warning(
                "INTENT_FIDELITY_REDUCED | shot=%s | slots=%s | note=%s",
                shot_id,
                ",".join(report.get("reduced_slots") or []),
                report.get("advisory_note", ""),
            )
        return report
    except Exception as exc:
        logger.debug("Intent fidelity check skipped for %s: %s", shot_id, exc)
        return None


def _format_visible_cast_constraint(character_names: list[str]) -> str:
    names = _normalize_character_names(character_names)
    if not names:
        return ""
    joined = " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + f", and {names[-1]}"
    return f"Only {joined} visible; no extras."


def _compact_prompt_guidance(lines: list[str], max_chars: int) -> str:
    clean = " ".join(
        " ".join(str(line or "").split())
        for line in lines
        if str(line or "").strip()
    ).strip()
    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get() or len(clean) <= max_chars:
        return clean
    shortened = clean[: max_chars - 3]
    last_space = shortened.rfind(" ")
    if last_space >= int(max_chars * 0.55):
        shortened = shortened[:last_space]
    return shortened.rstrip(" ,;:.") + "..."


def _prepend_bounded_prompt_context(
    prompt: str,
    context: str,
    *,
    budget: int = _PROMPT_BUDGET,
) -> str:
    clean_prompt = str(prompt or "").strip()
    clean_context = str(context or "").strip()
    if not clean_context:
        return clean_prompt
    combined = f"{clean_context}. {clean_prompt}" if clean_prompt else clean_context
    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get() or len(combined) <= budget:
        return combined
    prompt_budget = max(0, budget - len(clean_context) - 2)
    return f"{clean_context}. {_compact_prompt_guidance([clean_prompt], prompt_budget)}".strip()


def _shot_planning_value(shot_planning: Any, key: str) -> str:
    if not isinstance(shot_planning, dict):
        return ""
    value = shot_planning.get(key)
    return str(value or "").strip() if value is not None else ""


def _join_shot_planning_values(shot_planning: Any, keys: list[str]) -> str:
    parts: list[str] = []
    for key in keys:
        value = _shot_planning_value(shot_planning, key)
        if value:
            parts.append(value)
    return " ".join(parts).strip()


def _provider_model_for_job(provider: str, parameters: dict[str, Any]) -> str:
    requested = str(parameters.get("model") or "").strip()
    if requested:
        return requested
    if provider == "runway_router":
        # Routing mode, not a concrete model: the router owns model choice.
        return "<model_router>"
    if provider in {"runway", "runway_direct"}:
        return os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5"
    if provider == "happyhorse-r2v":
        return "happyhorse-1.1-r2v"
    if provider == "happyhorse":
        return "happyhorse-1.1-t2v"
    if provider == "wan":
        return "wan2.6-t2v"
    return str(parameters.get("model") or provider or "default")


def _resolve_model_selection(
    provider: str,
    parameters: dict[str, Any],
    *,
    reference_count: int = 0,
    duration_seconds: int = 5,
    require_audio: bool = False,
) -> dict[str, Any] | None:
    """Resolve the model for this job through the bounded router.

    A caller-supplied ``parameters["model"]`` is USER_SELECTED and is never
    replaced. Otherwise the router performs AUTO selection over the verified
    registry. Selection failures here are raised so the render is blocked
    before any provider call — never silently downgraded.

    Only the Runway provider consults the registry today; every other provider
    keeps its existing default-model behavior untouched.
    """
    requested = str(parameters.get("model") or "").strip()
    if provider != "runway":
        return None
    from app.services.model_router import SELECTION_MODE_AUTO, model_router

    requirements: dict[str, Any] = {
        "generation_mode": "image_to_video" if reference_count else "text_to_video",
        "reference_count": reference_count,
        "duration_seconds": duration_seconds,
    }
    if require_audio:
        requirements["audio"] = True
    try:
        selection = model_router.select_model(
            provider=provider,
            requirements=requirements,
            user_model_id=requested or None,
        )
    except ValueError:
        # USER selection failed validation → the error message names the
        # capability conflict and blocks the render (fail closed).
        if requested:
            raise
        # AUTO with no compatible model: keep the env default so existing
        # non-registry flows (tests, local providers) stay functional; the
        # adapter's own override validation still gates per-request models.
        return {
            "model_id": os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5",
            "selection_mode": SELECTION_MODE_AUTO,
            "selection_reason": "Router found no strictly compatible model; "
            "using the operator-configured default model.",
            "estimated_cost_credits": None,
            "warnings": ["model_selection_fallback_to_default"],
        }
    return selection.to_dict()


def _generation_context_metadata(
    job_id: str,
    provider: str,
    parameters: dict[str, Any],
    reference_assets: list[str] | None,
    prompt: str,
) -> dict[str, Any]:
    """Record the generation context + model selection metadata for this job.

    Best-effort and observational: a failure here must never block a render
    that was already valid under the previous (pre-workstream) behavior.
    Persisted keys follow the workstream's Generation Metadata contract:
    generation_context_id, scene/shot/storyboard/reference/camera versions,
    model, selection_mode, selection_reason, estimated_cost.
    """
    try:
        from app.services.generation_context_service import generation_context_service
        from app.services.model_registry import model_registry

        params = parameters if isinstance(parameters, dict) else {}
        shot_id = str(params.get("shot_id") or job_id)
        scene_id = derive_scene_id_from_shot_id(shot_id)
        storyboard_meta = params.get("storyboard") if isinstance(params.get("storyboard"), dict) else None
        blueprint_version = ""
        storyboard_shot_id = ""
        if storyboard_meta:
            blueprint_version = str(storyboard_meta.get("version_id") or storyboard_meta.get("blueprint_version_id") or "")
            storyboard_shot_id = str(storyboard_meta.get("storyboard_shot_id") or "")
        if not blueprint_version:
            blueprint_version = str(params.get("blueprint_version_id") or "")

        scene = None
        try:
            _project = project_store.get_project(job_id if False else params.get("project_id") or "")
        except Exception:
            _project = None
        # project lookup is skipped here: the caller persists project context
        # elsewhere; the context service fingerprints what this call site has.
        scene = params.get("_scene_snapshot") if isinstance(params.get("_scene_snapshot"), dict) else None

        duration = params.get("duration") or params.get("duration_seconds") or 5
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = 5

        # P0-1: fingerprint the REAL current shot when canonical state is
        # reachable, so job metadata carries the actual shot version instead
        # of a permanent "absent" stub. The camera provenance uses the same
        # record so heuristic board values stay AI_SUGGESTED (P0-2).
        current_shot = None
        if storyboard_meta and storyboard_shot_id:
            try:
                from app.services.storyboard_blueprint_service import storyboard_blueprint_service

                current_shot = storyboard_blueprint_service.storage.get_storyboard_shot(storyboard_shot_id)
                if current_shot is not None and str(getattr(current_shot, "version_id", "") or "") != str(
                    storyboard_meta.get("version_id") or ""
                ):
                    # The pinned board version outranks a re-resolved row: if
                    # they disagree, the shot moved — do not bless either.
                    current_shot = None
            except Exception:
                current_shot = None

        # Only explicit creator request parameters count as USER_SPECIFIED.
        # Board-written ``shot_planning`` is template output and must not be
        # transmuted into user camera approval (audit H-2).
        camera_instructions = generation_context_service.derive_camera_instructions(
            creator_planning=params.get("creator_shot_planning"),
            approved_camera_plan=params.get("camera_plan"),
            storyboard_shot=current_shot,
        )
        context = generation_context_service.create_generation_context(
            project_id=str(params.get("project_id") or ""),
            scene_id=scene_id,
            shot_id=shot_id,
            scene=scene,
            storyboard_context={"version": blueprint_version} if blueprint_version else None,
            reference_assets=reference_assets,
            camera_instructions=camera_instructions,
            prompt_source="USER_EDITED" if params.get("preserve_shot_prompt") else "BOARD" if storyboard_meta else "DERIVED",
            shot=current_shot,
        )

        reference_count = len([a for a in (reference_assets or []) if str(a or "").strip()])
        model_id = str(params.get("model") or "").strip()
        if provider == "runway_router":
            # Routed path: the canonical contract records the ROUTING MODE and
            # config id — never a concrete model. The model Runway actually
            # selects is execution metadata, recorded after execution under
            # metadata["router_execution"] ("resolved_model").
            from app.services.providers.runway_router_provider import (
                ROUTING_MODE_MODEL_ROUTER,
                get_router_config_id,
            )

            selection = {
                "model_id": None,
                "routing_mode": ROUTING_MODE_MODEL_ROUTER,
                "router_config_id": get_router_config_id(),
                "selection_mode": "ROUTED",
                "selection_reason": (
                    "Routed through the Runway Model Router; Runway selects the "
                    "eligible model from the routing configuration."
                ),
                "estimated_cost_credits": None,
                "warnings": [],
            }
        else:
            selection = _resolve_model_selection(
                provider,
                params,
                reference_count=reference_count,
                duration_seconds=duration,
            ) or {}
            if model_id and not selection.get("model_id"):
                selection["model_id"] = model_id

        estimated_cost = selection.get("estimated_cost_credits")
        if estimated_cost is None and model_id:
            model_def = model_registry.get_model(model_id)
            if model_def is not None:
                estimated_cost = model_registry.estimate_cost_credits(model_def, duration)

        metadata: dict[str, Any] = {
            "generation_context": context.to_dict(),
            "model_selection": {
                "model": selection.get("model_id") or model_id or "provider_default",
                "selection_mode": selection.get("selection_mode") or "USER_SELECTED" if model_id else "AUTO_SELECTED",
                "selection_reason": selection.get("selection_reason") or "",
                "estimated_cost_credits": estimated_cost,
                "warnings": selection.get("warnings") or [],
            },
            "estimated_cost_credits": estimated_cost,
        }
        if provider == "runway_router":
            # Canonical model-agnostic generation contract (routing mode +
            # config id), kept separate from execution metadata. The resolved
            # model — what Runway actually selected — lands in
            # metadata["router_execution"] only, never here.
            from app.services.providers.runway_router_provider import (
                ROUTING_MODE_MODEL_ROUTER,
                get_router_config_id,
            )

            metadata["model_selection"]["routing_mode"] = ROUTING_MODE_MODEL_ROUTER
            metadata["model_selection"]["router_config_id"] = get_router_config_id()
            metadata["model_selection"]["model"] = "<model_router>"
        if storyboard_shot_id:
            metadata["generation_context"]["metadata"]["storyboard_shot_id"] = storyboard_shot_id
        return metadata
    except Exception as exc:  # noqa: BLE001 — observational metadata must never block a render
        logger.debug("GENERATION_CONTEXT_METADATA_SKIPPED | job_id=%s | cause=%s", job_id, type(exc).__name__)
        return {}


def _validate_model_override(provider: str, parameters: dict[str, Any]) -> None:
    requested = str(parameters.get("model") or "").strip()
    if not requested:
        return
    if provider == "runway_router":
        # Fail closed: the Model Router selects the model. A concrete model on
        # the routed path would defeat the routing contract (and Runway's
        # /v1/generate/* schema has no model field), so the request is rejected
        # before any provider call — never silently stripped.
        raise ValueError(
            f"The Runway Model Router selects the eligible model; a concrete "
            f"model override ('{requested}') is not allowed on provider "
            f"'runway_router'. Remove the model override or use a direct-model "
            "provider."
        )
    if provider in {"runway", "runway_direct"}:
        # Single source of truth: the centralized model registry (verified
        # against the published Runway Dev API). Replaces the retired hardcoded
        # frozenset that still accepted nonexistent gen6/gen3 identifiers.
        # "runway_direct" shares the runway allowlist (same upstream models).
        from app.services.model_registry import model_registry

        allowed = model_registry.allowed_model_ids("runway")
        if requested not in allowed:
            raise ValueError(
                f"Unsupported Runway model '{requested}'. Allowed models: {sorted(allowed)}"
            )
    elif provider == "happyhorse" and requested != "happyhorse-1.1-t2v":
        raise ValueError("HappyHorse text-to-video does not support this model override")
    elif provider == "happyhorse-r2v" and requested != "happyhorse-1.1-r2v":
        raise ValueError("HappyHorse reference-to-video does not support this model override")
    elif provider == "wan" and requested != "wan2.6-t2v":
        raise ValueError("Wan text-to-video does not support this model override")


def _model_requirements_for_user_selection(
    parameters: dict[str, Any],
    reference_assets: list[str] | None,
) -> dict[str, Any]:
    """Build registry requirements from the shot's already-validated inputs.

    Only uses fields the caller actually supplied; unknown dimensions are
    omitted so validation fails open on absence but fails closed on a known
    capability conflict. Mirrors the requirement keys of
    ``ModelRegistry.check_requirements``.
    """
    params = parameters if isinstance(parameters, dict) else {}
    refs = [str(a or "").strip() for a in (reference_assets or []) if str(a or "").strip()]
    requirements: dict[str, Any] = {
        "generation_mode": "image_to_video" if refs else "text_to_video",
        "reference_count": len(refs),
    }
    duration = params.get("duration") if params.get("duration") is not None else params.get("duration_seconds")
    if isinstance(duration, bool):
        pass
    elif isinstance(duration, (int, float)) and int(duration) > 0:
        requirements["duration_seconds"] = int(duration)
    resolution = str(params.get("resolution") or "").strip()
    if resolution:
        requirements["resolution"] = resolution
    if params.get("audio") is True or params.get("require_audio") is True:
        requirements["audio"] = True
    if params.get("first_frame") is True:
        requirements["first_frame"] = True
    if params.get("last_frame") is True:
        requirements["last_frame"] = True
    return requirements


def _validate_user_model_capabilities(
    provider: str,
    parameters: dict[str, Any],
    reference_assets: list[str] | None = None,
) -> dict[str, Any] | None:
    """Enforce creator-selected Runway model capabilities before execution.

    A caller-supplied ``parameters["model"]`` is USER_SELECTED and authoritative:
    it is validated against the verified registry for this shot's requirements
    and never silently replaced. An incompatible selection raises ValueError
    naming the capability conflict so creation/submission fails closed before
    any provider call. Returns the validated selection record for identity
    recording, or None when no creator model was requested or the provider
    does not consult the registry (including ``runway_router``, whose concrete
    overrides are already rejected by ``_validate_model_override``).
    """
    params = parameters if isinstance(parameters, dict) else {}
    requested = str(params.get("model") or "").strip()
    if not requested:
        return None
    if provider not in {"runway", "runway_direct"}:
        return None
    from app.services.model_router import model_router

    requirements = _model_requirements_for_user_selection(params, reference_assets)
    # Registry entries are keyed under provider "runway"; "runway_direct"
    # shares the same upstream allowlist and capabilities.
    selection = model_router.select_model(
        provider="runway",
        requirements=requirements,
        user_model_id=requested,
    )
    return selection.to_dict()


def _apply_visual_model_reference(job: RenderJobModel) -> None:
    """Attach a registered visual-model reference to the provider payload.

    Rendering is unchanged unless the job explicitly asks for a trained visual
    model via ``parameters["visual_model_id"]`` or
    ``parameters["visual_model_target"]``. When a model is requested but not
    registered/complete for the project, this raises ProviderError (fail-closed)
    rather than silently rendering with an untrained or unrelated model.

    When a model resolves, its reference is stored on ``parameters`` and its
    trigger word is folded into the prompt so the identity is actually invoked
    by the provider (every adapter renders from ``input_payload.prompt``).
    """
    if not job.input_payload or not isinstance(job.input_payload.parameters, dict):
        return

    params = job.input_payload.parameters
    visual_model_id = params.get("visual_model_id")
    raw_target = params.get("visual_model_target")
    target = raw_target if isinstance(raw_target, dict) else {}
    target_type = target.get("target_type")
    target_id = target.get("target_id")

    if not visual_model_id and not (target_type and target_id):
        return

    from app.services.stability import ValidationError
    from app.services.visual_training_service import visual_training_service

    try:
        reference = visual_training_service.resolve_render_reference(
            project_id=job.project_id,
            visual_model_id=visual_model_id,
            target_type=target_type,
            target_id=target_id,
        )
    except ValidationError as exc:
        raise ProviderError(
            exc.message if hasattr(exc, "message") else str(exc),
            stage="visual_model_resolution",
            metadata={"project_id": job.project_id, "visual_model_id": visual_model_id},
        ) from exc

    if reference is None:
        raise ProviderError(
            "Requested visual model is not registered for this project",
            stage="visual_model_resolution",
            metadata={"project_id": job.project_id, "visual_model_id": visual_model_id},
        )

    params["visual_model_reference"] = reference

    # Consume the resolved identity so it actually reaches the provider. Every
    # adapter renders from ``input_payload.prompt``, and a trained identity is
    # invoked by its trigger word, so fold the trigger into the prompt here —
    # provider-agnostically — instead of patching each adapter. This only runs
    # when a visual model was explicitly requested (resolved above), so renders
    # without an opt-in identity are untouched. Guarded against re-injection on
    # retries so the trigger is never duplicated.
    trigger = str(reference.get("trigger") or "").strip()
    if trigger:
        existing_prompt = str(job.input_payload.prompt or "")
        if trigger not in existing_prompt:
            job.input_payload.prompt = _prepend_bounded_prompt_context(
                existing_prompt,
                f"Render with the trained visual identity {trigger}",
            )

    logger.info(
        "VISUAL_MODEL_REFERENCE_APPLIED | project=%s | job=%s | model_id=%s | trigger_injected=%s",
        job.project_id,
        job.id,
        reference.get("model_id"),
        bool(trigger),
    )


def _scene_character_names_for_debug(project_id: str, scene_id: str) -> list[str]:
    try:
        project = project_store.get_project(project_id)
        if not isinstance(project, dict):
            return []
        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") or []
        scene = next(
            (
                item for item in scenes
                if isinstance(item, dict) and str(item.get("scene_id") or "") == scene_id
            ),
            None,
        )
        if not isinstance(scene, dict):
            return []
        return _normalize_character_names(
            scene.get("characters") or scene.get("character_appearances") or []
        )
    except Exception:
        return []


def _reference_debug(consistency_payload: ConsistencyPayload | None, provider: str) -> list[dict[str, Any]]:
    if consistency_payload is None:
        return []
    # Provider reference support comes from the evidence-gated capability
    # contract (UNKNOWN-aware), not a hardcoded provider allowlist. Support
    # means the provider request can carry reference images at all — a
    # multi-reference set OR a single start-frame anchor. Unknown providers
    # report support=False with provider_support_unknown=True instead of
    # claiming a capability nobody verified.
    from app.services.provider_capability_contract import get_provider_capability
    _ref_cond = get_provider_capability(provider).get("reference_conditioning") or {}
    _image_channels = tuple(
        _ref_cond.get(key) for key in ("multi_reference", "start_frame")
    )
    _channel_values = tuple(
        entry.get("supported") if isinstance(entry, dict) else None
        for entry in _image_channels
    )
    if any(value is True for value in _channel_values):
        supports_images = True
        support_unknown = False
    elif any(value not in (True, False) for value in _channel_values):
        supports_images = False
        support_unknown = True
    else:
        supports_images = False
        support_unknown = False
    rows: list[dict[str, Any]] = []
    for ref in consistency_payload.refs:
        fallback = str(consistency_payload.fallback_text.get(ref.ref_id, "")).strip()
        rows.append(
            {
                "reference_type": ref.kind,
                "reference_id": ref.ref_id,
                "path": ref.image_url,
                "reason": fallback or f"Selected confirmed {ref.kind.replace('_', ' ')} reference.",
                "entity": ref.source_shot_id or "project",
                "provider_supports_reference": supports_images,
                "provider_support_unknown": support_unknown,
                "injected_into_request": supports_images,
                "fallback_prompt_constraint": fallback if not supports_images else "",
            }
        )
    return rows


def _selection_audit_debug(consistency_payload: ConsistencyPayload | None) -> list[dict[str, Any]]:
    """Expose the deterministic reference-selection audit in job metadata.

    Internal debugging/reproducibility data — job metadata and logs only; it is
    never rendered as a filmmaker-facing score and never sent to the provider.
    """
    if consistency_payload is None:
        return []
    audit = getattr(consistency_payload, "selection_audit", None)
    return [row for row in (audit or []) if isinstance(row, dict)]


def _zero_touch_debug_metadata(
    *,
    project_id: str,
    shot_id: str,
    provider: str,
    parameters: dict[str, Any],
    prompt: str,
    consistency_payload: ConsistencyPayload | None,
) -> dict[str, Any]:
    scene_id = derive_scene_id_from_shot_id(shot_id)
    characters = _scene_character_names_for_debug(project_id, scene_id)
    references = _reference_debug(consistency_payload, provider)
    staging_applied = bool(characters and "In this shot:" in prompt)
    return {
        "version": "zero_touch_v1",
        "phases": [
            {"phase": "validate_input", "status": "complete"},
            {"phase": "load_project_context", "status": "complete", "scene_id": scene_id},
            {"phase": "resolve_characters", "status": "complete", "characters": characters},
            {
                "phase": "build_staging",
                "status": "complete" if staging_applied else "skipped",
                "reason": "" if staging_applied else ("no resolved character staging" if characters else "no characters resolved"),
            },
            {"phase": "resolve_references", "status": "complete" if references else "skipped", "references": references},
            {"phase": "prepare_provider_request", "status": "complete"},
            {"phase": "render", "status": "pending"},
            {"phase": "evaluate", "status": "pending"},
            {"phase": "retry", "status": "pending"},
            {"phase": "persist", "status": "complete"},
        ],
        "provider_selection": {
            "provider": provider,
            "model": _provider_model_for_job(provider, parameters),
            "reason": "explicit override" if parameters.get("model") else "configured default or caller-selected provider",
        },
        "staging": {
            "applied": staging_applied,
            "characters": characters,
        },
        "reference_selection": _selection_audit_debug(consistency_payload),
        "references": references,
        "prompt": {
            "length": len(prompt),
            "structured_slots": bool(parameters.get("prompt_slots")),
        },
        "retry": {
            "max_attempts": max(0, min(int(os.getenv("ADHERENCE_AUTO_RETRY_MAX", "2") or "2"), 5)),
            "history": [],
        },
    }


def _set_zero_touch_phase(job: RenderJobModel, phase: str, status: str, **details: Any) -> None:
    if _is_contract_only(job):
        return
    now = _now_iso()
    metadata = dict(job.metadata or {})
    debug = dict(metadata.get("zero_touch_pipeline") or {})
    phases = debug.get("phases")
    if not isinstance(phases, list):
        phases = []
    updated = False
    for row in phases:
        if isinstance(row, dict) and row.get("phase") == phase:
            if status == "running" and not row.get("started_at"):
                row["started_at"] = now
            if status in {"complete", "failed", "skipped", "needs_review", "cancelled"}:
                row["completed_at"] = now
                started_at = RenderService._parse_iso(str(row.get("started_at") or ""))
                completed_at = RenderService._parse_iso(now)
                if started_at and completed_at:
                    row["duration_ms"] = int((completed_at - started_at).total_seconds() * 1000)
            row.update({"status": status, **details})
            updated = True
            break
    if not updated:
        row = {"phase": phase, "status": status, **details}
        if status == "running":
            row["started_at"] = now
        if status in {"complete", "failed", "skipped", "needs_review", "cancelled"}:
            row["completed_at"] = now
        phases.append(row)
    debug["phases"] = phases
    metadata["zero_touch_pipeline"] = debug
    reliability = dict(metadata.get("pipeline_reliability") or {})
    timing = dict(reliability.get("phase_timing") or {})
    timing_row = dict(timing.get(phase) or {})
    if status == "running" and "started_at" not in timing_row:
        timing_row["started_at"] = now
    if status in {"complete", "failed", "skipped", "needs_review", "cancelled"}:
        timing_row["completed_at"] = now
        started_at = RenderService._parse_iso(str(timing_row.get("started_at") or ""))
        completed_at = RenderService._parse_iso(now)
        if started_at and completed_at:
            timing_row["duration_ms"] = int((completed_at - started_at).total_seconds() * 1000)
    if details:
        timing_row["details"] = {k: v for k, v in details.items() if k in {"provider", "model", "error", "reason", "error_type"}}
    timing[phase] = timing_row
    reliability["phase_timing"] = timing
    metadata["pipeline_reliability"] = reliability
    job.metadata = metadata
    if job.input_payload and isinstance(job.input_payload.parameters, dict) and not _is_contract_only(job):
        job.input_payload.parameters["zero_touch_debug"] = debug


_PERMANENT_PROVIDER_ERROR_TYPES = {
    "provider_disabled",
    "missing_api_key",
    "invalid_api_key",
    "revoked_key",
    "missing_credits",
    "missing_org_access",
    "unsupported_model",
    "invalid_payload",
    "test_mode_not_allowed",
}

_TEMPORARY_PROVIDER_ERROR_TYPES = {
    "timeout",
    "rate_limit",
    "request_error",
    "ssl_verification_error",
    "task_failed",
    "missing_task_id",
    "missing_video_url",
}


def _provider_error_payload(job: RenderJobModel) -> dict[str, Any]:
    output_metadata = (
        job.output_payload.metadata
        if job.output_payload and isinstance(job.output_payload.metadata, dict)
        else {}
    )
    normalized = output_metadata.get("provider_response_normalized")
    if not isinstance(normalized, dict):
        return {}
    metadata = normalized.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    error = metadata.get("error") or metadata.get("timeout")
    return error if isinstance(error, dict) else {}


def _classify_provider_failure(job: RenderJobModel, fallback_message: str = "") -> dict[str, Any]:
    error_payload = _provider_error_payload(job)
    error_type = str(error_payload.get("error_type") or "").strip()
    message = str(error_payload.get("message") or fallback_message or job.error_message or "").strip()
    status_code = error_payload.get("status_code")
    try:
        status_code_int = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_code_int = None

    if not error_type:
        text = message.lower()
        if status_code_int == 429 or "rate limit" in text or "too many request" in text or "throttl" in text:
            error_type = "rate_limit"
        elif "api key" in text or "credential" in text or "unauthorized" in text:
            error_type = "missing_api_key" if "missing" in text or "not configured" in text else "invalid_api_key"
        elif "billing" in text or "credit" in text or "payment" in text:
            error_type = "missing_credits"
        elif "disabled" in text and "provider" in text:
            error_type = "provider_disabled"
        elif "unsupported" in text and "model" in text:
            error_type = "unsupported_model"
        elif "timeout" in text or "timed out" in text:
            error_type = "timeout"
        elif "without output url" in text or "without video_url" in text:
            error_type = "missing_video_url"
        else:
            error_type = "provider_failure"

    permanent = error_type in _PERMANENT_PROVIDER_ERROR_TYPES
    retryable = error_type in _TEMPORARY_PROVIDER_ERROR_TYPES and not permanent
    if error_type == "provider_failure":
        retryable = False

    category = "permanent" if permanent else ("temporary" if retryable else "unknown")
    policy_reason = (
        "requires configuration, billing, tenant, or request correction before another spend"
        if permanent
        else ("transient provider/runtime failure may be retried by an explicit retry policy" if retryable else "provider failure is not classified as safely retryable")
    )
    return {
        "category": category,
        "error_type": error_type,
        "message": message,
        "status_code": status_code,
        "retryable": retryable,
        "policy_reason": policy_reason,
    }


def _record_provider_failure_policy(job: RenderJobModel, fallback_message: str = "") -> None:
    classification = _classify_provider_failure(job, fallback_message)
    metadata = dict(job.metadata or {})
    metadata["provider_failure"] = classification
    job.metadata = metadata
    _record_failure_location(
        job,
        phase="render",
        reason=classification["message"],
        error_type=classification["error_type"],
        category=classification["category"],
    )
    if not classification["retryable"] and not _is_contract_only(job):
        _set_zero_touch_phase(
            job,
            "retry",
            "skipped",
            reason=classification["policy_reason"],
            error_type=classification["error_type"],
        )


def _detect_prompt_contradictions(prompt: str) -> list[dict[str, Any]]:
    """Detect only high-confidence provider prompt contradictions before spend."""
    import re

    text = f" {str(prompt or '').lower()} "
    checks: list[tuple[str, str, str, str, str]] = [
        (
            "framing_closeup_full_body",
            r"\b(close[- ]?up|tight close|extreme close[- ]?up)\b",
            r"\b(full[- ]?body|head[- ]to[- ]toe|entire body)\b",
            "Close-up framing conflicts with full-body framing.",
            "Choose either close-up emphasis or full-body visibility.",
        ),
        (
            "position_left_center",
            r"\b(on the left|left side|frame left|screen left|to the left)\b",
            r"\b(centered|centre|center frame|dead center|in the center|in center)\b",
            "Left-side placement conflicts with centered placement.",
            "Choose one screen position for the subject.",
        ),
        (
            "lighting_day_night",
            r"\b(daylight|daytime|midday|sunlit|bright day)\b",
            r"\b(nighttime|night time|at night|after dark|moonlit)\b",
            "Daylight instructions conflict with nighttime instructions.",
            "Choose one time-of-day lighting condition.",
        ),
        (
            "camera_static_tracking",
            r"\b(static camera|locked[- ]off|locked off|fixed camera|stationary camera)\b",
            r"\b(rapid tracking|fast tracking|quick tracking|tracking shot)\b",
            "Static camera instructions conflict with tracking movement.",
            "Choose either a static camera or a moving tracking shot.",
        ),
        (
            "empty_room_visible_characters",
            r"\b(empty room|empty hallway|empty space|no people|no characters)\b",
            r"\b(multiple visible characters|two visible characters|three visible characters|crowd|group of people|characters visible)\b",
            "Empty-room instructions conflict with visible-character requirements.",
            "Choose either an empty environment or visible characters.",
        ),
    ]
    contradictions: list[dict[str, Any]] = []
    for code, first_pattern, second_pattern, message, recommendation in checks:
        first = re.search(first_pattern, text)
        second = re.search(second_pattern, text)
        if first and second:
            contradictions.append(
                {
                    "code": code,
                    "message": message,
                    "signals": [first.group(0).strip(), second.group(0).strip()],
                    "recommendation": recommendation,
                }
            )
    return contradictions


_APP_SERVED_REFERENCE_PREFIXES = (
    "/outputs/",
    "/previs-assets/",
    "/static/",
    "outputs/",
    "previs-assets/",
    "static/",
)


def _missing_local_reference_assets(reference_assets: list[str] | None) -> list[str]:
    missing: list[str] = []
    backend_root = Path(__file__).resolve().parents[2]
    for raw in reference_assets or []:
        value = str(raw or "").strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "data"}:
            continue
        if value.startswith(_APP_SERVED_REFERENCE_PREFIXES):
            continue
        path = Path(parsed.path if parsed.scheme == "file" else value).expanduser()
        candidates = [path] if path.is_absolute() else [backend_root / path, Path.cwd() / path]
        if not any(candidate.exists() and candidate.is_file() for candidate in candidates):
            missing.append(value)
    return missing


class RenderService:
    """Service for managing render jobs across providers"""

    def __init__(self):
        self._provider_configs: dict[str, ProviderConfig] = {}
        self._jobs: dict[str, RenderJobModel] = {}
        self._submit_locks: set[str] = set()
        # In-memory batch store: batch_id -> batch metadata dict
        self._batches: dict[str, dict] = {}
        self._initialize_providers()

    def _build_reference_consistency_payload(self, project_id: str) -> ConsistencyPayload | None:
        """Build an identity-lock payload from confirmed project reference assets."""
        try:
            storage = _storage
            if storage is None:
                from app.data.storage import get_storage

                storage = get_storage("sqlite")
            if storage is None or not hasattr(storage, "list_reference_assets"):
                return None
            raw_refs = storage.list_reference_assets(project_id=project_id, limit=12)
        except Exception as exc:
            logger.debug("Reference consistency lookup skipped for %s: %s", project_id, exc)
            return None

        refs: list[ReferenceAsset] = []
        weights: dict[str, float] = {}
        fallback_text: dict[str, str] = {}
        kind_weights = {
            "character_full": 1.0,
            "character_face": 0.55,
            "environment": 0.25,
            "style": 0.15,
        }
        for raw in raw_refs:
            if not isinstance(raw, dict):
                continue
            ref_id = str(raw.get("ref_id") or "").strip()
            kind = str(raw.get("kind") or "").strip()
            image_url = str(raw.get("image_url") or "").strip()
            # Candidate/rejected library rows are intentionally not generation
            # inputs. Legacy rows without review metadata remain confirmed.
            if raw.get("approval_state") in {"candidate", "rejected"}:
                continue
            if not ref_id or not image_url or kind not in kind_weights:
                continue
            try:
                ref = ReferenceAsset(
                    ref_id=ref_id,
                    kind=kind,  # type: ignore[arg-type]
                    image_url=image_url,
                    embedding=raw.get("embedding") if isinstance(raw.get("embedding"), list) else None,
                    source_shot_id=raw.get("source_shot_id"),
                    project_id=project_id,
                    target_type=raw.get("target_type"),
                    target_id=raw.get("target_id"),
                    category=raw.get("category"),
                    approval_state=raw.get("approval_state", "approved"),
                    canonical=bool(raw.get("canonical")),
                    source_kind=raw.get("source_kind", "confirmed"),
                )
            except Exception:
                continue
            refs.append(ref)
            weights[ref.ref_id] = kind_weights[kind]
            if kind == "character_face":
                fallback_text[ref.ref_id] = "preserve facial identity from confirmed character reference"
            elif kind == "character_full":
                fallback_text[ref.ref_id] = "preserve full-body character silhouette and wardrobe continuity"
            elif kind == "environment":
                fallback_text[ref.ref_id] = "preserve environment layout, lighting, and spatial continuity"
            elif kind == "style":
                fallback_text[ref.ref_id] = "preserve project visual style reference"

        if not refs:
            return None
        return ConsistencyPayload(
            project_id=project_id,
            refs=refs,
            weights=weights,
            mode="identity_lock",
            fallback_text=fallback_text,
        )

    def _initialize_providers(self):
        """Initialize default provider configurations"""
        runway_api_key = (
            os.getenv("RUNWAYML_API_SECRET", "").strip()
            or os.getenv("RUNWAY_API_KEY", "").strip()
            or os.getenv("VIDEO_PROVIDER_API_KEY", "").strip()
        )
        runway_api_endpoint = os.getenv("RUNWAY_API_BASE_URL", "").strip() or os.getenv("VIDEO_PROVIDER_BASE_URL", "").strip()
        runway_key_source = (
            "RUNWAYML_API_SECRET"
            if os.getenv("RUNWAYML_API_SECRET", "").strip()
            else ("RUNWAY_API_KEY" if os.getenv("RUNWAY_API_KEY", "").strip() else ("VIDEO_PROVIDER_API_KEY" if os.getenv("VIDEO_PROVIDER_API_KEY", "").strip() else "none"))
        )
        logger.info(
            "Runway key source=%s configured=%s",
            runway_key_source,
            bool(runway_api_key),
        )

        # Runway primary path for active video requests.
        self._provider_configs["runway"] = ProviderConfig(
            provider_id="runway",
            name="Runway",
            enabled=True,
            is_simulated=False,
            api_key=runway_api_key or None,
            api_endpoint=runway_api_endpoint or "https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"],
        )
        # Additive direct-model Runway path (provider id "runway_direct").
        # Same concrete-model Dev API contract as "runway" (POST
        # /v1/image_to_video + /v1/text_to_video, Bearer auth,
        # X-Runway-Version 2024-11-06), sharing the Runway credential and
        # endpoint. The legacy "runway" id stays behind its fail-closed
        # submit_job gate (exact-match); "runway_direct" bypasses that gate
        # by identity, never by weakening it. Router behavior unchanged.
        self._provider_configs["runway_direct"] = ProviderConfig(
            provider_id="runway_direct",
            name="Runway Direct",
            enabled=True,
            is_simulated=False,
            api_key=runway_api_key or None,
            api_endpoint=runway_api_endpoint or "https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"],
        )
        # Runway Model Router path — the model-agnostic execution provider.
        # Shares Runway's credential; routes by configId (the saved routing
        # config slug, default "studio-production-router"); never carries a
        # concrete model. Additive: direct "runway" behavior is unchanged.
        self._provider_configs["runway_router"] = ProviderConfig(
            provider_id="runway_router",
            name="Runway Model Router",
            enabled=True,
            is_simulated=False,
            api_key=runway_api_key or None,
            api_endpoint=os.getenv("RUNWAY_ROUTER_API_BASE_URL", "").strip()
            or runway_api_endpoint
            or "https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["model_routing", "video_generation", "image_generation"],
        )

        # Retired DashScope video providers (HappyHorse / Wan). Purged as part
        # of the Runway-canonical enforcement: no DashScope credential is read,
        # no endpoint is configured, and new submissions cannot select them.
        # Entries remain (disabled) so historical jobs still resolve; the
        # canonical engine for all new image/video work is Runway.
        self._provider_configs["happyhorse"] = ProviderConfig(
            provider_id="happyhorse",
            name="HappyHorse (retired — use Runway)",
            enabled=False,
            is_simulated=False,
            api_key=None,
            api_endpoint="",
            requires=["api_key"],
            capabilities=["video_generation", "text_to_video"],
        )
        self._provider_configs["happyhorse-r2v"] = ProviderConfig(
            provider_id="happyhorse-r2v",
            name="HappyHorse Reference-to-Video (retired — use Runway)",
            enabled=False,
            is_simulated=False,
            api_key=None,
            api_endpoint="",
            requires=["api_key"],
            capabilities=["video_generation", "reference_to_video", "image_conditioning"],
        )
        self._provider_configs["wan"] = ProviderConfig(
            provider_id="wan",
            name="Alibaba Wan (retired — use Runway)",
            enabled=False,
            is_simulated=False,
            api_key=None,
            api_endpoint="",
            requires=["api_key"],
            capabilities=["video_generation", "text_to_video", "multi_shot", "audio_generation"],
        )

        # Simulated provider remains available fallback.
        self._provider_configs["simulated"] = ProviderConfig(
            provider_id="simulated",
            name="Simulated Provider",
            enabled=True,
            is_simulated=True,
            requires=[],
            capabilities=["video_generation", "image_to_video", "style_transfer"]
        )

        # Local provider for fallback when Runway is not configured
        self._provider_configs["local"] = ProviderConfig(
            provider_id="local",
            name="Local (Simulated)",
            enabled=True,
            is_simulated=True,
            requires=[],
            capabilities=["video_generation", "image_to_video"]
        )

        # Higgsfield placeholder
        self._provider_configs["higgsfield"] = ProviderConfig(
            provider_id="higgsfield",
            name="Higgsfield",
            enabled=False,  # Disabled until API key provided
            is_simulated=False,
            api_key=None,
            api_endpoint=None,
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"]
        )

        # Generic video provider placeholder
        self._provider_configs["generic"] = ProviderConfig(
            provider_id="generic",
            name="Generic Video Provider",
            enabled=False,
            is_simulated=False,
            api_key=None,
            api_endpoint=None,
            requires=["api_key", "api_endpoint"],
            capabilities=["video_generation"]
        )

        # MiniMax H3 local pipeline (Pinokio-managed ComfyUI). Scaffold only:
        # disabled by default so existing behavior is unchanged. Requires an
        # NVIDIA/CUDA host plus a verified API-format H3 graph before it
        # can generate. No API key is required for the local path.
        from app.adapters.minimax_h3_local import build_default_config as _minimax_h3_default_config
        self._provider_configs["minimax_h3_local"] = _minimax_h3_default_config()

        # Local LTX via Phosphene (Pinokio-managed, Apple Silicon/MLX).
        # Disabled by default so existing behavior is unchanged. No API key
        # is required for the local path.
        from app.adapters.local_ltx import build_default_config as _local_ltx_default_config
        self._provider_configs["local_ltx"] = _local_ltx_default_config()

        # AMD MI300X ROCm provider for LTX-2 and HunyuanVideo
        self._provider_configs["amd"] = ProviderConfig(
            provider_id="amd",
            name="AMD MI300X",
            enabled=False,
            is_simulated=True,  # Mock for Phase 1
            api_key=None,
            api_endpoint=None,
            requires=["api_key", "api_endpoint"],
            capabilities=["video_generation", "image_to_video"],
            gpu="MI300X",
            runtime="ROCm",
            models=["ltx-2", "hunyuan-video"]
        )

    def list_providers(self) -> list[ProviderStatus]:
        """List all available providers with status"""
        statuses = []
        test_mode = str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()
        for provider_id, config in self._provider_configs.items():
            missing_requirements: list[str] = []
            if "api_key" in config.requires and not (config.api_key or "").strip():
                missing_requirements.append("api_key")
            if "api_endpoint" in config.requires and not (config.api_endpoint or "").strip():
                missing_requirements.append("api_endpoint")

            provider_mode = "hosted_api"
            if provider_id in {"runway", "runway_direct"} and test_mode == "mock_success":
                provider_mode = "mock_success"
            elif config.is_simulated:
                provider_mode = "mock_success"
            elif not config.enabled or missing_requirements:
                provider_mode = "unavailable"

            api_key_configured = "api_key" not in missing_requirements
            ready_for_hosted_generation = bool(
                config.enabled
                and not config.is_simulated
                and api_key_configured
                and not (provider_id in {"runway", "runway_direct"} and test_mode == "mock_success")
            )
            is_mock = provider_mode == "mock_success" or config.is_simulated

            if provider_mode == "mock_success":
                display_label = f"{config.name}: Mock Success Mode"
            elif ready_for_hosted_generation:
                display_label = f"{config.name}: Real provider mode active"
            elif missing_requirements:
                joined = ", ".join(missing_requirements)
                display_label = f"{config.name}: hosted unavailable ({joined} required)"
            elif not config.enabled:
                display_label = f"{config.name}: disabled"
            else:
                display_label = f"{config.name}: unavailable"

            # Add AMD-specific metadata if available
            gpu = getattr(config, 'gpu', None)
            runtime = getattr(config, 'runtime', None)
            models = getattr(config, 'models', [])
            
            # Enhance display label for AMD with ROCm badge
            if provider_id == "amd":
                display_label = f"{config.name}: ROCm / Open Source"
                if missing_requirements:
                    joined = ", ".join(missing_requirements)
                    display_label = f"{config.name}: ROCm / Open Source (hosted unavailable - {joined} required)"
                elif not config.enabled:
                    display_label = f"{config.name}: ROCm / Open Source (disabled)"

            # MiniMax H3 local reflects host capability, not just config.
            # Never claim readiness from config alone: the installed H3
            # implementation requires an NVIDIA/CUDA runtime. This provider
            # is local, so it is never "hosted" generation.
            status_value = "available" if config.enabled else "disabled"
            if provider_id == "minimax_h3_local":
                ready_for_hosted_generation = False
                try:
                    from app.adapters.minimax_h3_local import detect_h3_runtime_support as _detect_h3
                    _h3_support = _detect_h3()
                except Exception:
                    _h3_support = {"supported": False, "reason": "H3 capability probe failed."}
                if not config.enabled:
                    display_label = f"{config.name}: disabled"
                elif not _h3_support.get("supported"):
                    status_value = "unsupported"
                    provider_mode = "unavailable"
                    display_label = f"{config.name}: unsupported ({_h3_support.get('reason', '')})"
                    if "cuda_runtime" not in missing_requirements:
                        missing_requirements.append("cuda_runtime")
                else:
                    provider_mode = "local"
                    display_label = f"{config.name}: local service (Pinokio ComfyUI)"

            # Local LTX via Phosphene reflects service reachability, which is
            # probed asynchronously in LocalLTXAdapter.get_status. This sync
            # listing only mirrors config (disabled vs configured) and never
            # claims the service is reachable. Local, so never hosted.
            if provider_id == "local_ltx":
                ready_for_hosted_generation = False
                if not config.enabled:
                    display_label = f"{config.name}: disabled"
                else:
                    provider_mode = "local"
                    display_label = f"{config.name}: local service (Pinokio Phosphene)"

            statuses.append(ProviderStatus(
                provider_key=provider_id,
                provider_id=provider_id,
                name=config.name,
                status=status_value,
                is_simulated=config.is_simulated,
                is_mock=is_mock,
                enabled=config.enabled,
                ready_for_hosted_generation=ready_for_hosted_generation,
                api_key_configured=api_key_configured,
                provider_mode=provider_mode,
                missing_requirements=missing_requirements,
                display_label=display_label,
                capabilities=config.capabilities,
                active_jobs=0,
                queued_jobs=0,
                gpu=gpu,
                runtime=runtime,
                models=models
            ))
        return statuses

    def get_provider_config(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get configuration for a provider"""
        if provider_id in {"openrouter", "openrouter-video"}:
            return None
        return self._provider_configs.get(provider_id)

    def set_provider_config(self, config: ProviderConfig) -> ProviderConfig:
        """Update provider configuration"""
        if config.provider_id in {"openrouter", "openrouter-video"}:
            raise ValueError(f"Video provider '{config.provider_id}' is retired and cannot be registered")
        self._provider_configs[config.provider_id] = config
        return config

    def _find_idempotent_job(
        self,
        *,
        project_id: str,
        shot_id: str,
        provider: str,
        idempotency_key: str,
        explicit_key: bool,
    ) -> RenderJobModel | None:
        candidates = self.list_jobs(project_id=project_id)
        for existing in candidates:
            if existing.project_id != project_id or existing.shot_id != shot_id or existing.provider != provider:
                continue
            metadata = existing.metadata if isinstance(existing.metadata, dict) else {}
            reliability = metadata.get("pipeline_reliability") if isinstance(metadata.get("pipeline_reliability"), dict) else {}
            if reliability.get("idempotency_key") == idempotency_key:
                return existing
            if not explicit_key and existing.status in {"pending", "rendering"}:
                return existing
        return None

    def get_default_provider(self) -> str:
        """Get the env-selected default render provider."""
        selected = os.getenv("RENDER_VIDEO_PROVIDER", get_settings().render_video_provider or "runway").strip().lower()
        if selected in {"openrouter", "openrouter-video"}:
            raise ValueError(
                f"Video provider '{selected}' is retired; configure RENDER_VIDEO_PROVIDER=runway"
            )
        if selected not in self._provider_configs:
            raise ValueError(f"Unsupported RENDER_VIDEO_PROVIDER '{selected}'")
        return selected

    async def create_and_submit_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list = None,
        parameters: dict = None
    ) -> RenderJobModel:
        """Create and submit a job in one call"""
        job = self.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        return await self.submit_job(job.id)

    async def create_and_submit_job_with_polling(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None,
        max_polls: int = 3,
        poll_interval: float = 0.25,
    ) -> RenderJobModel:
        """Create and submit a render job with polling for completion"""
        created_job = self.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        submitted_job = await self.submit_job(created_job.id)
        polled_job = submitted_job
        
        for _ in range(max_polls):
            if polled_job.is_terminal():
                break
            await asyncio.sleep(poll_interval)
            polled_job = await self.get_job_status(created_job.id)
            
        return polled_job

    @preserve_generation_facts
    def create_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None,
        generation_contract: dict[str, Any] | None = None,
        generation_context_id: str = "",
        creative_manifest_fingerprint: str = "",
        creative_manifest: dict[str, Any] | None = None,
        dialogue_handoff: dict[str, Any] | None = None,
        frozen_reference_binding: list[dict[str, Any]] | None = None,
        prepared_generation_contract: dict[str, Any] | None = None,
        execution_mode: str | None = None,
        scene002_execution_contract: dict[str, Any] | None = None,
        source_authority_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RenderJobModel:
        """Create a new render job with validation"""
        # Validate shot_id is not empty
        if not shot_id or not shot_id.strip():
            raise ValueError("shot_id cannot be empty")
        if execution_mode is not None:
            from app.services.scene002_contract_only import MODE, verify_execution_contract

            if execution_mode != MODE or scene002_execution_contract is None or not source_authority_id:
                raise ValueError("Scene 002 contract-only jobs require a durable execution contract and authority identity")
            if shot_id.split("_shot_", 1)[0] != "scene_002" or provider != "runway_router":
                raise ValueError("Scene 002 contract-only mode is restricted to its authorized Runway Router shot")
            protected_payload = verify_execution_contract(scene002_execution_contract)
            if protected_payload.get("shot_id") != shot_id or protected_payload.get("provider") != provider:
                raise ValueError("Scene 002 execution contract does not match the requested job")
            if protected_payload.get("source_authority", {}).get("authority_id") != source_authority_id:
                raise ValueError("Scene 002 execution contract authority identity does not match")

        # ── Per-scene provider override ───────────────────────────────────────
        # If the project has a per-scene override for this shot's scene, use it
        # instead of the caller-supplied provider (unless the caller explicitly
        # passed one, which takes precedence).
        if provider is None and execution_mode is None:
            try:
                _scene_id_for_override = derive_scene_id_from_shot_id(shot_id)
                _project = project_store.get_project(project_id)
                if isinstance(_project, dict):
                    _overrides = _project.get("provider_overrides") or {}
                    if isinstance(_overrides, dict):
                        _override_mode = _overrides.get(_scene_id_for_override)
                        if _override_mode == "hosted_api":
                            provider = self.get_default_provider()
                        elif _override_mode in ("simulated", "mock_success"):
                            provider = "simulated"
            except Exception:
                pass  # Never block a render due to override lookup failure
        
        # Normalize provider for consistent lookup
        if provider:
            provider = provider.strip().lower()
            if provider == "simulated provider":
                provider = "simulated"

        if provider == "runway_router":
            if execution_mode is None and generation_contract is None:
                raise ValueError("Runway Router jobs require a frozen contract from the canonical production pipeline")
            from app.access_context import access_user_id

            _metadata = dict(metadata or {})
            request_actor_id = str(access_user_id.get() or "").strip()
            _metadata["production_request_actor_id"] = request_actor_id
            metadata = _metadata
            if not request_actor_id:
                raise ValueError("Runway Router jobs require an authenticated project owner")
            authority_storage = _storage
            if authority_storage is None:
                from app.data.storage import get_storage as _get_authority_storage

                authority_storage = _get_authority_storage("sqlite")
            try:
                actor_project_owner = authority_storage.access_project_owner(project_id)
            except Exception as exc:
                raise ValueError("Runway Router owner authority could not be verified") from exc
            if actor_project_owner != request_actor_id:
                raise ValueError("Runway Router job creation requires the current project owner")

        # The direct-model escape hatch is historical/read-only. New production
        # work must use the canonical scene pipeline and its frozen Router
        # contract; preserve the legacy `runway` alias for old pending records,
        # which submit_job independently fails closed.
        if provider == "runway_direct":
            raise ValueError(
                "Runway provider 'runway_direct' is not an authorized production "
                "path. Use the canonical scene production pipeline and its "
                "frozen Runway Model Router contract."
            )
        
        # Validate provider against known providers
        if provider:
            if provider in {"openrouter", "openrouter-video"}:
                raise ValueError(f"Video provider '{provider}' is retired and cannot be used for Studio video generation")
            if provider not in self._provider_configs:
                raise ValueError(f"Unknown provider '{provider}'. Available providers: {list(self._provider_configs.keys())}")
        else:
            provider = self.get_default_provider()

        _initial_parameters = deepcopy(parameters) if isinstance(parameters, dict) else {}
        _frozen_reference_binding = deepcopy(frozen_reference_binding) if frozen_reference_binding is not None else None
        _reference_binding_digest = ""
        _prepared_contract_record = deepcopy(prepared_generation_contract)
        _prepared_contract_payload: dict[str, Any] | None = None
        _prepared_manifest = deepcopy(creative_manifest)
        if _frozen_reference_binding is not None:
            from app.services.reference_validation import frozen_reference_payload, reference_binding_digest

            if _prepared_contract_record is None:
                raise ValueError("Frozen canonical references require the prepared generation contract")
            if not all(isinstance(row, dict) for row in _frozen_reference_binding):
                raise ValueError("Prepared canonical reference binding is malformed")
            expected_uris = [str(row.get("uri") or "") for row in _frozen_reference_binding]
            if (
                not all(expected_uris)
                or not all(str(row.get("ref_id") or "").strip() for row in _frozen_reference_binding)
                or list(reference_assets or []) != expected_uris
            ):
                raise ValueError("Prepared canonical reference binding does not match reference_assets")
            _reference_binding_digest = reference_binding_digest(_frozen_reference_binding)
            _initial_parameters["reference_roles"] = [str(row.get("role") or "reference") for row in _frozen_reference_binding]
            _initial_parameters["frozen_reference_binding"] = deepcopy(_frozen_reference_binding)
            _frozen_consistency_payload = frozen_reference_payload(_frozen_reference_binding, project_id=project_id)
        else:
            _frozen_consistency_payload = None

        if execution_mode is not None:
            if not isinstance(scene002_execution_contract, dict):
                raise ValueError("Protected execution contract is missing")
            protected_payload = verify_execution_contract(scene002_execution_contract)
            if protected_payload.get("generation_contract") != _prepared_contract_record:
                raise ValueError("Protected execution proof does not bind the prepared generation contract")
            if protected_payload.get("source_authority", {}).get("authority_id") != source_authority_id:
                raise ValueError("Protected execution proof does not bind the authority identity")

        if _prepared_contract_record is not None:
            from app.services.generation_contract import FrozenGenerationContract
            from app.services.shot_manifest import recompute_manifest_fingerprint

            frozen_prepared_contract = FrozenGenerationContract.from_record(_prepared_contract_record)
            _prepared_contract_payload = frozen_prepared_contract.payload()
            if frozen_prepared_contract.shot_id != shot_id or frozen_prepared_contract.prompt != prompt:
                raise ValueError("Prepared generation contract does not match the requested shot and prompt")
            if _frozen_reference_binding is None:
                raise ValueError("Prepared generation contract requires its canonical reference binding")
            expected_contract_refs = [
                {
                    "uri": str(row.get("uri") or ""),
                    "role": "reference",
                    "studio_role": str(row.get("role") or "reference"),
                    "category": str(row.get("category") or ""),
                    "source": "canonical_reference_binding",
                    "ref_id": str(row.get("ref_id") or ""),
                    "target_type": str(row.get("target_type") or ""),
                    "target_id": str(row.get("target_id") or ""),
                    "canonical": bool(row.get("canonical")),
                    "approval_state": str(row.get("approval_state") or "approved"),
                    "source_kind": str(row.get("source_kind") or "confirmed"),
                    **({"kind": str(row["kind"])} if row.get("kind") else {}),
                }
                for row in _frozen_reference_binding
            ]
            if frozen_prepared_contract.payload().get("references") is not None:
                _canonical_frozen_refs = [
                    row for row in (frozen_prepared_contract.payload().get("references") or [])
                    if isinstance(row, dict) and row.get("source") == "canonical_reference_binding"
                ]
            else:
                _canonical_frozen_refs = []
            if _canonical_frozen_refs != expected_contract_refs:
                raise ValueError("Prepared generation contract references do not match the canonical binding")
            if (
                frozen_prepared_contract.payload().get("camera_plan") != _initial_parameters.get("camera_plan")
                or frozen_prepared_contract.payload().get("camera_provenance") != _initial_parameters.get("camera_provenance")
                or frozen_prepared_contract.payload().get("camera_source_digest") != _initial_parameters.get("camera_source_digest")
                or frozen_prepared_contract.payload().get("camera_source_project_id") != _initial_parameters.get("camera_source_project_id", "")
                or frozen_prepared_contract.payload().get("camera_source_scene_id") != _initial_parameters.get("camera_source_scene_id", "")
                or frozen_prepared_contract.payload().get("camera_source_shot_id") != _initial_parameters.get("camera_source_shot_id", "")
                or frozen_prepared_contract.payload().get("camera_source_storyboard_shot_id") != _initial_parameters.get("camera_source_storyboard_shot_id", "")
                or frozen_prepared_contract.payload().get("camera_instructions") != _initial_parameters.get("camera_instructions", [])
                or frozen_prepared_contract.payload().get("camera_target_project_id") != _initial_parameters.get("camera_target_project_id", "")
                or frozen_prepared_contract.payload().get("camera_target_scene_id") != _initial_parameters.get("camera_target_scene_id", "")
                or frozen_prepared_contract.payload().get("camera_target_shot_id") != _initial_parameters.get("camera_target_shot_id", "")
            ):
                raise ValueError("Prepared camera provenance does not match the frozen generation contract")
            from app.services.generation_contract import creative_parameter_values

            if creative_parameter_values(_initial_parameters) != frozen_prepared_contract.payload().get("creative_parameters", {}):
                raise ValueError("Prepared render parameters do not match the frozen generation contract")
            frozen_payload = frozen_prepared_contract.payload()
            if (
                _initial_parameters.get("scene_coverage") != frozen_payload.get("scene_coverage")
                or _initial_parameters.get("scene_coverage_shot") != frozen_payload.get("scene_coverage_shot")
            ):
                raise ValueError("Prepared render coverage does not match the frozen generation contract")
            if not isinstance(_prepared_manifest, dict):
                raise ValueError("Prepared generation contract requires its creative manifest")
            manifest_fingerprint = str(creative_manifest_fingerprint or "")
            if (
                not manifest_fingerprint
                or _prepared_manifest.get("manifest_fingerprint") != manifest_fingerprint
                or frozen_prepared_contract.manifest_fingerprint != manifest_fingerprint
                or recompute_manifest_fingerprint(_prepared_manifest) != manifest_fingerprint
            ):
                raise ValueError("Prepared generation contract manifest fingerprint is invalid")
            manifest_rows = [
                row for row in (_prepared_manifest.get("shots") or [])
                if isinstance(row, dict) and row.get("shot_id") == shot_id
            ]
            manifest_scene = _prepared_manifest.get("scene") if isinstance(_prepared_manifest.get("scene"), dict) else {}
            from app.services.scene_coverage_contract import verify_scene_coverage_contract
            try:
                prepared_coverage = verify_scene_coverage_contract(frozen_prepared_contract.payload().get("scene_coverage"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Prepared scene coverage is invalid: {exc}") from exc
            if (
                frozen_prepared_contract.camera_target_project_id != project_id
                or frozen_prepared_contract.camera_target_scene_id != str(manifest_scene.get("scene_id") or "")
                or frozen_prepared_contract.camera_target_shot_id != shot_id
                or prepared_coverage.get("project_id") != project_id
                or prepared_coverage.get("scene_id") != str(manifest_scene.get("scene_id") or "")
                or prepared_coverage.get("canonical_script_sha256") != manifest_scene.get("canonical_script_sha256")
                or prepared_coverage.get("scene_source_identity") != manifest_scene.get("scene_source_identity")
                or prepared_coverage.get("scene_source_start") != manifest_scene.get("scene_source_start")
                or prepared_coverage.get("scene_source_end") != manifest_scene.get("scene_source_end")
            ):
                raise ValueError("Prepared camera target identity does not match the render job and manifest")
            expected_manifest_reference_binding = [
                {
                    key: row.get(key)
                    for key in ("ref_id", "project_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind")
                    if key in row
                }
                for row in _frozen_reference_binding
            ]
            if (
                len(manifest_rows) != 1
                or manifest_rows[0].get("reference_binding") != expected_manifest_reference_binding
                or manifest_rows[0].get("references") != [row["uri"] for row in _frozen_reference_binding]
                or manifest_rows[0].get("reference_roles") != [row["role"] for row in _frozen_reference_binding]
                or manifest_rows[0].get("generation_contract_digest") != frozen_prepared_contract.creative_digest()
                or manifest_rows[0].get("camera_plan") != frozen_prepared_contract.payload().get("camera_plan")
                or manifest_rows[0].get("camera_provenance") != frozen_prepared_contract.payload().get("camera_provenance")
                or manifest_rows[0].get("camera_instructions") != frozen_prepared_contract.payload().get("camera_instructions")
                or manifest_rows[0].get("camera_source_digest") != frozen_prepared_contract.payload().get("camera_source_digest")
                or manifest_rows[0].get("camera_source_project_id") != frozen_prepared_contract.payload().get("camera_source_project_id")
                or manifest_rows[0].get("camera_source_scene_id") != frozen_prepared_contract.payload().get("camera_source_scene_id")
                or manifest_rows[0].get("camera_source_shot_id") != frozen_prepared_contract.payload().get("camera_source_shot_id")
                or manifest_rows[0].get("camera_source_storyboard_shot_id") != frozen_prepared_contract.payload().get("camera_source_storyboard_shot_id")
                or manifest_rows[0].get("camera_target_project_id") != frozen_prepared_contract.payload().get("camera_target_project_id")
                or manifest_rows[0].get("camera_target_scene_id") != frozen_prepared_contract.payload().get("camera_target_scene_id")
                or manifest_rows[0].get("camera_target_shot_id") != frozen_prepared_contract.payload().get("camera_target_shot_id")
                or manifest_rows[0].get("scene_coverage") != prepared_coverage
                or manifest_rows[0].get("scene_coverage_shot") != frozen_prepared_contract.payload().get("scene_coverage_shot")
            ):
                raise ValueError("Prepared generation contract references do not match the creative manifest")
        if execution_mode is not None and (
            not isinstance(_prepared_contract_record, dict)
            or not isinstance(_prepared_manifest, dict)
            or _frozen_reference_binding is None
            or not isinstance(dialogue_handoff, dict)
        ):
            raise ValueError("Protected job creation requires the complete prepared contract, manifest, reference binding, and dialogue proof")
        if dialogue_handoff is not None:
            from app.services.generation_contract import verify_dialogue_handoff
            from app.services.shot_manifest import recompute_manifest_fingerprint

            try:
                handoff = verify_dialogue_handoff(
                    dialogue_handoff,
                    scene_id=derive_scene_id_from_shot_id(shot_id),
                    shot_id=shot_id,
                )
                if _initial_parameters.get("dialogue_lines") != handoff["lines"]:
                    raise ValueError("Render parameters dialogue_lines do not match the frozen handoff")
                fingerprint = str(creative_manifest_fingerprint or "")
                if (
                    not isinstance(creative_manifest, dict)
                    or not fingerprint
                    or creative_manifest.get("manifest_fingerprint") != fingerprint
                    or recompute_manifest_fingerprint(creative_manifest) != fingerprint
                ):
                    raise ValueError("Frozen dialogue handoff creative manifest is missing or invalid")
                rows = [
                    row for row in creative_manifest.get("shots", [])
                    if isinstance(row, dict) and row.get("shot_id") == shot_id
                ]
                if len(rows) != 1 or rows[0].get("dialogue_handoff") != dialogue_handoff:
                    raise ValueError("Frozen dialogue handoff does not match the creative manifest")
            except (TypeError, KeyError, ValueError) as exc:
                raise ValueError(f"Frozen dialogue handoff validation failed: {exc}") from exc
        if provider == "runway_router" and generation_contract is None:
            raise ValueError("Runway Router jobs require a frozen contract from the canonical scene production pipeline")
        if provider == "runway_router" and _prepared_contract_payload is not None:
            if (
                not _prepared_contract_payload.get("camera_plan")
                or _prepared_contract_payload.get("camera_provenance") not in {"APPROVED", "USER_SPECIFIED"}
            ):
                raise ValueError("Runway Router requires an authoritative frozen camera plan before job creation")
        if _initial_parameters.get("storyboard_frame_url") and provider not in {"runway", "runway_router"}:
            from app.services.stability import ValidationError
            raise ValidationError(
                "This provider integration cannot use the approved storyboard as a first frame. Choose Runway for storyboard rendering.",
                stage="storyboard_conditioning", metadata={"provider": provider},
            )
        if generation_contract is None:
            _validate_model_override(provider, _initial_parameters)
        if generation_contract is not None:
            if provider != "runway_router":
                raise ValueError("Frozen manifest contracts are currently accepted only by the Runway Router boundary")
            from app.services.generation_contract import FrozenGenerationContract
            from app.services.shot_manifest import recompute_manifest_fingerprint

            frozen = FrozenGenerationContract.from_record(generation_contract)
            if frozen.shot_id != shot_id:
                raise ValueError("Frozen generation contract shot_id does not match the render job")
            manifest = json.loads(json.dumps(creative_manifest)) if isinstance(creative_manifest, dict) else None
            if manifest is None:
                raise ValueError("Runway Router jobs require the canonical persisted creative manifest")
            manifest_fingerprint = str(creative_manifest_fingerprint or "")
            if (
                not manifest_fingerprint
                or manifest.get("manifest_fingerprint") != manifest_fingerprint
                or frozen.manifest_fingerprint != manifest_fingerprint
            ):
                raise ValueError("Frozen generation contract manifest fingerprint is missing or mismatched")
            try:
                if recompute_manifest_fingerprint(manifest) != manifest_fingerprint:
                    raise ValueError("Creative manifest fingerprint verification failed")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Creative manifest is invalid: {exc}") from exc
            manifest_shots = manifest.get("shots")
            matching_manifest_entries = [
                row for row in manifest_shots
                if isinstance(row, dict) and row.get("shot_id") == shot_id
            ] if isinstance(manifest_shots, list) else []
            if len(matching_manifest_entries) != 1:
                raise ValueError("Creative manifest must contain exactly one Router shot identity")
            manifest_entry = matching_manifest_entries[0]
            manifest_scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
            if (
                frozen.camera_target_project_id != project_id
                or frozen.camera_target_scene_id != str(manifest_scene.get("scene_id") or "")
                or frozen.camera_target_shot_id != shot_id
            ):
                raise ValueError("Frozen camera target identity does not match the render job and manifest")
            contract_digest = frozen.creative_digest()
            approved = frozen.payload()
            if provider == "runway_router" and execution_mode is None:
                from app.services.generation_contract import ROUTER_SELECTION_EVIDENCE_KEYS as _router_evidence_keys

                selection_evidence = (metadata or {}).get("router_selection_evidence")
                if selection_evidence is not None:
                    # R4.5-B1 (F8, owner decision 3). Selection evidence is
                    # digest-linked at creation: a tampered entry or a
                    # mismatched digest fails closed here, and any post-persist
                    # mutation is denied by the durable-identity check at
                    # submit. Evidence never substitutes for frozen creative
                    # state: it is only valid alongside empty creative params.
                    if not isinstance(selection_evidence, dict) or not isinstance(
                        selection_evidence.get("selection"), dict
                    ):
                        raise ValueError("Router selection evidence is malformed")
                    if selection_evidence.get("contract_digest") != contract_digest:
                        raise ValueError(
                            "Router selection evidence does not match the frozen generation contract"
                        )
                    unknown_evidence_keys = set(selection_evidence["selection"]) - set(_router_evidence_keys)
                    if unknown_evidence_keys:
                        raise ValueError(
                            "Router selection evidence carries non-selection keys"
                        )
                    if approved.get("creative_parameters"):
                        raise ValueError(
                            "Router selection evidence requires empty frozen creative parameters"
                        )
            if dialogue_handoff is not None and approved.get("dialogue_handoff") != dialogue_handoff:
                raise ValueError("Frozen contract dialogue does not match the prepared handoff")
            manifest_references = manifest_entry.get("references")
            manifest_reference_roles = manifest_entry.get("reference_roles")
            approved_references = approved["references"]
            canonical_approved_references = [
                reference for reference in approved_references
                if isinstance(reference, dict) and reference.get("source") == "canonical_reference_binding"
            ]
            from app.services.reference_validation import (
                assert_setting_project_scope,
                contract_comparison_binding,
            )
            expected_binding = contract_comparison_binding(canonical_approved_references)
            assert_setting_project_scope(_frozen_reference_binding, project_id)
            if (
                (dialogue_handoff is not None and manifest_entry.get("dialogue_handoff") != approved.get("dialogue_handoff"))
                or manifest_entry.get("shot_prompt") != frozen.prompt
                or manifest_entry.get("negative_prompt", "") != frozen.negative_prompt
                or manifest_entry.get("generation_contract_digest") != contract_digest
                or manifest_entry.get("shot_duration_seconds") != (approved.get("duration") or 0)
                or manifest_entry.get("audio_intent") is not approved.get("audio")
                or manifest_entry.get("aspect_ratio") != approved.get("aspect_ratio")
                or manifest_entry.get("resolution") != approved.get("resolution")
                or manifest_entry.get("seed") != approved.get("seed")
                or manifest_entry.get("camera_plan") != approved.get("camera_plan")
                or manifest_entry.get("camera_provenance") != approved.get("camera_provenance")
                or manifest_entry.get("camera_instructions") != approved.get("camera_instructions")
                or manifest_entry.get("camera_source_digest") != approved.get("camera_source_digest")
                or manifest_entry.get("camera_source_project_id") != approved.get("camera_source_project_id")
                or manifest_entry.get("camera_source_scene_id") != approved.get("camera_source_scene_id")
                or manifest_entry.get("camera_source_shot_id") != approved.get("camera_source_shot_id")
                or manifest_entry.get("camera_source_storyboard_shot_id") != approved.get("camera_source_storyboard_shot_id")
                or manifest_entry.get("camera_target_project_id") != approved.get("camera_target_project_id")
                or manifest_entry.get("camera_target_scene_id") != approved.get("camera_target_scene_id")
                or manifest_entry.get("camera_target_shot_id") != approved.get("camera_target_shot_id")
                or manifest_entry.get("parameters") != approved.get("creative_parameters")
                or manifest_entry.get("scene_coverage") != approved.get("scene_coverage")
                or manifest_entry.get("scene_coverage_shot") != approved.get("scene_coverage_shot")
                or manifest_scene.get("project_id") != project_id
                or manifest_scene.get("scene_id") != approved.get("scene_coverage", {}).get("scene_id")
                or manifest_scene.get("canonical_script_sha256") != approved.get("scene_coverage", {}).get("canonical_script_sha256")
                or manifest_scene.get("scene_source_identity") != approved.get("scene_coverage", {}).get("scene_source_identity")
                or manifest_scene.get("scene_source_start") != approved.get("scene_coverage", {}).get("scene_source_start")
                or manifest_scene.get("scene_source_end") != approved.get("scene_coverage", {}).get("scene_source_end")
                or manifest_references != [reference["uri"] for reference in approved_references]
                or manifest_reference_roles != [reference["studio_role"] for reference in approved_references]
                or (
                    _frozen_reference_binding is not None
                    and (
                        contract_comparison_binding(manifest_entry.get("reference_binding")) != expected_binding
                        or expected_binding != contract_comparison_binding(_frozen_reference_binding)
                    )
                )
                or (dialogue_handoff is not None and approved.get("dialogue_handoff") != dialogue_handoff)
            ):
                raise ValueError("Frozen contract creative values do not match the manifest")
            frozen_parameters = dict(approved.get("creative_parameters") or {})
            frozen_parameters.update(
                duration=approved.get("duration"),
                aspect_ratio=approved.get("aspect_ratio"),
                resolution=approved.get("resolution"),
                seed=approved.get("seed"),
            )
            if approved.get("content_moderation") is not None:
                frozen_parameters["content_moderation"] = approved["content_moderation"]
            for key in ("reference_videos", "reference_audio", "keyframes"):
                frozen_parameters[key] = approved.get(key) or []
            storyboard_identity = manifest.get("storyboard") if isinstance(manifest.get("storyboard"), dict) else {}
            if manifest_entry.get("storyboard_shot_id") and storyboard_identity.get("storyboard_version"):
                frozen_parameters["storyboard"] = {
                    "storyboard_shot_id": str(manifest_entry["storyboard_shot_id"]),
                    "version_id": str(storyboard_identity["storyboard_version"]),
                }
            if provider == "runway_router" and execution_mode is None:
                # R4.5-B1 (F7, owner decision 1: store more, router jobs only).
                # The adapter's mutable-input gate compares these three values
                # against the frozen contract, so persist them from the frozen
                # contract at creation. Non-router jobs are untouched, and the
                # Scene 002 contract-only branch (execution_mode set) keeps its
                # authority-pinned shape: its verifier requires persisted
                # inputs to equal provider_input_parameters exactly.
                if approved.get("scene_coverage") is not None:
                    frozen_parameters["scene_coverage"] = deepcopy(approved["scene_coverage"])
                if approved.get("scene_coverage_shot") is not None:
                    frozen_parameters["scene_coverage_shot"] = deepcopy(approved["scene_coverage_shot"])
                if approved.get("dialogue_handoff") is not None:
                    frozen_parameters["dialogue_handoff"] = deepcopy(approved["dialogue_handoff"])
            job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}-{shot_id}"
            now = datetime.now().isoformat()
            job = RenderJobModel(
                id=job_id,
                project_id=project_id,
                shot_id=shot_id,
                provider=provider,
                status="pending",
                input_payload=RenderJobInput(
                    shot_id=shot_id,
                    prompt=approved["prompt"],
                    negative_prompt=approved.get("negative_prompt", ""),
                    referenceAssets=[ref["uri"] for ref in approved["references"]],
                    parameters=frozen_parameters,
                    consistency_payload=_frozen_consistency_payload,
                ),
            metadata={
                **({
                    "execution_mode": execution_mode,
                        "scene002_execution_contract": deepcopy(scene002_execution_contract),
                        "source_authority_id": source_authority_id,
                    } if execution_mode else {}),
                    "creative_generation_contract": generation_contract,
                    "generation_context": {"generation_context_id": generation_context_id} if generation_context_id else {},
                    "creative_manifest_fingerprint": manifest_fingerprint,
                    "creative_generation_manifest": manifest,
                    "creative_dialogue_handoff": approved.get("dialogue_handoff"),
                    "creative_contract_digest": contract_digest,
                    **({
                        "frozen_reference_binding": deepcopy(_frozen_reference_binding),
                        "frozen_reference_binding_sha256": _reference_binding_digest,
                    } if _frozen_reference_binding is not None else {}),
                    **(deepcopy(metadata) if isinstance(metadata, dict) else {}),
                    "creative_generation_identity": {
                        "job_id": job_id,
                        "project_id": project_id,
                        "shot_id": shot_id,
                        "provider": provider,
                    },
                    **({
                        "production_request_actor_id": __import__("app.access_context", fromlist=["access_user_id"]).access_user_id.get() or ""
                    } if provider == "runway_router" else {}),
                    "pipeline_reliability": {
                        "correlation_id": f"corr-{uuid.uuid4().hex[:16]}",
                        "idempotency_key": hashlib.sha256(
                            json.dumps(generation_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
                        ).hexdigest(),
                        "idempotency_key_source": "frozen_generation_contract",
                        "created_at": now,
                        "phase_timing": {},
                    },
                },
                created_at=now,
                updated_at=now,
            )
            if provider == "runway_router" and execution_mode is None:
                from app.services.production_authorization_service import authorize_runway_submission

                creation_authority = authorize_runway_submission(
                    job,
                    storage=_storage,
                    require_durable=False,
                )
                if not creation_authority.allowed:
                    raise ValueError(
                        f"Runway Router job creation denied: {creation_authority.reason}"
                    )
                job.metadata["production_authorization"] = {
                    "allowed": True,
                    "reason": creation_authority.reason,
                    "project_id": creation_authority.project_id,
                    "job_id": creation_authority.job_id,
                    "actor_id": creation_authority.actor_id,
                    "stage": "job_creation",
                }
            if _storage is None:
                raise RuntimeError("Runway Router contract cannot be created without durable render-job storage")
            if not _persist_job(job):
                raise RuntimeError("Runway Router contract could not be durably persisted")
            reloaded = _storage.get_job(job_id)
            if reloaded is None or not isinstance(reloaded.metadata, dict):
                raise RuntimeError("Persisted Runway Router job could not be reloaded")
            if (
                (execution_mode is not None and reloaded.metadata.get("scene002_execution_contract") != scene002_execution_contract)
                or (execution_mode is not None and reloaded.metadata.get("source_authority_id") != source_authority_id)
                or reloaded.metadata.get("creative_generation_contract") != generation_contract
                or reloaded.metadata.get("creative_generation_manifest") != manifest
                or reloaded.metadata.get("creative_manifest_fingerprint") != manifest_fingerprint
                or reloaded.metadata.get("creative_contract_digest") != contract_digest
                or (
                    _frozen_reference_binding is not None
                    and reloaded.metadata.get("frozen_reference_binding") != _frozen_reference_binding
                )
                or (
                    _frozen_reference_binding is not None
                    and reloaded.metadata.get("frozen_reference_binding_sha256") != _reference_binding_digest
                )
                or (isinstance(metadata, dict) and any(reloaded.metadata.get(key) != value for key, value in metadata.items()))
                or reloaded.metadata.get("creative_generation_identity") != {
                    "job_id": job_id,
                    "project_id": project_id,
                    "shot_id": shot_id,
                    "provider": provider,
                }
            ):
                raise RuntimeError("Persisted Runway Router contract metadata failed round-trip verification")
            if _frozen_reference_binding is not None:
                from app.services.reference_validation import verify_frozen_reference_payload

                verify_frozen_reference_payload(
                    job=reloaded,
                    binding=reloaded.metadata.get("frozen_reference_binding"),
                )
            if (
                reloaded.input_payload.prompt != approved["prompt"]
                or reloaded.input_payload.negative_prompt != approved.get("negative_prompt", "")
                or list(reloaded.input_payload.referenceAssets or []) != [row["uri"] for row in approved["references"]]
                or (execution_mode is not None and reloaded.input_payload.parameters != _initial_parameters)
            ):
                raise RuntimeError("Persisted Runway Router payload failed creative/reference round-trip verification")
            self._jobs[job_id] = reloaded
            return reloaded

        _idempotency_key, _explicit_idempotency_key = _request_idempotency_key(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=_initial_parameters,
        )
        _existing = self._find_idempotent_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            idempotency_key=_idempotency_key,
            explicit_key=_explicit_idempotency_key,
        )
        if _existing is not None:
            _ensure_reliability_metadata(_existing)["duplicate_request_reused_at"] = _now_iso()
            # G-7: hydrate the reused row into this instance. Without this the
            # returned job is absent from _jobs and a same-instance submit
            # fails with "not found" despite create_job succeeding.
            self._jobs[_existing.id] = _existing
            _persist_job(_existing)
            logger.info(
                "DUPLICATE_RENDER_REQUEST_REUSED | job_id=%s | project_id=%s | shot_id=%s | provider=%s | status=%s",
                _existing.id,
                project_id,
                shot_id,
                provider,
                _existing.status,
            )
            return _existing

        # ── Replace generic prompts with real scene descriptions ──────────────
        # If prompt is generic or too short, fetch the actual scene description
        _scene_id = derive_scene_id_from_shot_id(shot_id)
        job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}-{shot_id}"
        _is_generic = execution_mode is None and _prepared_contract_record is None and not _initial_parameters.get("preserve_shot_prompt") and (
            not prompt.strip()
            or len(prompt.strip()) < 50
            or "Generate scene" in prompt
            or "Cinematic quality" in prompt
        )
        _prompt_slots_for_adherence: dict[str, str] | None = None
        _intent_fidelity_report: dict | None = None
        _render_scene_data: dict[str, Any] = {}
        _render_scene_chars: list[str] = []
        _render_knowledge_context = None
        _department_render_context = None
        _render_context_storage = None
        _knowledge_prompt_applied = False
        _identity_prompt_applied = False
        
        if _is_generic:
            try:
                _project = project_store.get_project(project_id)
                if isinstance(_project, dict):
                    _summary = _project.get("execution_summary") or {}
                    _scenes = _summary.get("scenes") or []
                    _scene = next(
                        (s for s in _scenes if isinstance(s, dict) and s.get("scene_id") == _scene_id),
                        None
                    )
                    if _scene:
                        _render_scene_data = dict(_scene)
                        _heading = str(_scene.get("heading") or "").strip()
                        # Pull scene text from any of the supported fields so the full
                        # scene block (action lines + dialogue) feeds the render prompt,
                        # not just the heading.
                        _scene_text = (
                            str(_scene.get("text") or "")
                            or str(_scene.get("content") or "")
                            or str(_scene.get("description") or "")
                            or str(_scene.get("scene_text") or "")
                        ).strip()
                        _full_content = f"{_heading}\n{_scene_text}".strip() if _heading else _scene_text
                        _location = str(_scene.get("location") or "").strip()
                        _time_of_day = str(_scene.get("time_of_day") or "").strip()
                        _tone = str(_scene.get("emotional_tone") or "").strip()

                        # Fall back to project-level script_text when the scene record
                        # itself has no content — this keeps the Board from showing
                        # "No description yet" while the script clearly has content.
                        if not _scene_text:
                            try:
                                _script_text = str(_project.get("script_text") or "").strip()
                                if _script_text:
                                    _scene_text = _script_text
                                    _full_content = (
                                        f"{_heading}\n{_scene_text}".strip()
                                        if _heading
                                        else _scene_text
                                    )
                            except Exception:
                                pass

                        if _full_content:
                            # ── Slotted prompt assembly via build_slotted_prompt() ──
                            # Replaces the old monolithic string concatenation with
                            # the fixed-slot builder that enforces per-slot character
                            # budgets (character_state/action/environment/camera/lighting)
                            # and guarantees the assembled prompt never exceeds 512 chars.

                            # 1. Build character visual descriptions from storage
                            _char_visuals = ""
                            try:
                                from app.data.storage import get_storage as _get_storage
                                _active_storage = _get_storage()
                            except Exception:
                                _active_storage = _storage
                            _render_context_storage = _active_storage
                            # 2. Extract visual action (strip dialogue). This
                            # also gives us shot-local text for cast inference
                            # when the scene's saved characters list is empty.
                            from app.services.shot_prompt_builder import SLOT_BUDGETS
                            _cast_probe_text = _extract_initial_visual_beat(
                                _scene_text, max_chars=360
                            ) if _scene_text else ""
                            _action_text = _extract_visual_action(
                                _scene_text, max_chars=SLOT_BUDGETS["action"]
                            ) if _scene_text else ""

                            _scene_chars = _normalize_character_names(
                                _scene.get("characters") or _scene.get("character_appearances") or []
                            )
                            if _scene_chars and _active_storage:
                                from app.services.character_staging_service import (
                                    resolve_character_prompt as _resolve_char_prompt,
                                )
                                _char_summaries: list[str] = []
                                for _char_name in _scene_chars:
                                    _char_name_str = str(_char_name).strip()
                                    if _char_name_str:
                                        _char_record = _active_storage.get_character_by_name(
                                            project_id, _char_name_str
                                        )
                                        if _char_record:
                                            try:
                                                _resolved = _resolve_char_prompt(
                                                    _char_record,
                                                    _scene_id,
                                                    shot_id,
                                                    _active_storage,
                                                )
                                            except Exception:
                                                _vps = (
                                                    _char_record.get("visual_prompt_summary")
                                                    or ""
                                                ).strip()
                                                _resolved = (
                                                    f"{_char_name_str}: {_vps}"
                                                    if _vps
                                                    else ""
                                                )
                                            if _resolved and _resolved != _char_name_str:
                                                _char_summaries.append(_resolved)
                                if _char_summaries:
                                    _cast_constraint = _format_visible_cast_constraint(_scene_chars)
                                    _char_visuals = "; ".join(
                                        [part for part in [_cast_constraint, *_char_summaries] if part]
                                    )
                                    logger.info(
                                        "CHARACTER_PROMPT_INJECTION | scene=%s | chars=%d",
                                        _scene_id,
                                        len(_char_summaries),
                                    )
                            elif _active_storage:
                                try:
                                    _all_chars = _active_storage.get_characters(project_id)
                                    _scene_chars = _infer_scene_characters_from_text(
                                        _all_chars,
                                        primary_text=_cast_probe_text,
                                        fallback_text=_full_content,
                                    )
                                    if _scene_chars:
                                        from app.services.character_staging_service import (
                                            resolve_character_prompt as _resolve_char_prompt,
                                        )
                                        _char_summaries = []
                                        for _char_name_str in _scene_chars:
                                            _char_record = _active_storage.get_character_by_name(
                                                project_id, _char_name_str
                                            )
                                            if not _char_record:
                                                continue
                                            try:
                                                _resolved = _resolve_char_prompt(
                                                    _char_record,
                                                    _scene_id,
                                                    shot_id,
                                                    _active_storage,
                                                )
                                            except Exception:
                                                _vps = (
                                                    _char_record.get("visual_prompt_summary")
                                                    or ""
                                                ).strip()
                                                _resolved = (
                                                    f"{_char_name_str}: {_vps}"
                                                    if _vps
                                                    else ""
                                                )
                                            if _resolved and _resolved != _char_name_str:
                                                _char_summaries.append(_resolved)
                                        if _char_summaries:
                                            _cast_constraint = _format_visible_cast_constraint(_scene_chars)
                                            _char_visuals = "; ".join(
                                                [part for part in [_cast_constraint, *_char_summaries] if part]
                                            )
                                            logger.info(
                                                "CHARACTER_PROMPT_INFERRED | scene=%s | chars=%d",
                                                _scene_id,
                                                len(_char_summaries),
                                            )
                                except Exception:
                                    pass
                            _render_scene_chars = list(_scene_chars)

                            # 3. Derive shot_number from shot_id for camera defaults
                            #    e.g. "scene_001_shot_003" → 3
                            _shot_number = 1
                            try:
                                _shot_suffix = shot_id.rsplit("_shot_", 1)
                                if len(_shot_suffix) == 2:
                                    _shot_number = int(_shot_suffix[1])
                            except (ValueError, IndexError):
                                pass

                            # 4. Map scene data to the 5 slots
                            #    environment: location (or heading if no location)
                            _environment = _location or _heading or ""
                            #    lighting: time_of_day + tone (lighting implied by time)
                            _lighting = " ".join(
                                p for p in [_time_of_day, _tone] if p
                            ).strip()

                            # 4b. Per-shot staging override.
                            #
                            # Everything above fills the slots from scene-level
                            # fallbacks -- location and time-of-day -- which are
                            # identical for every shot in the scene. When the
                            # shot carries reviewed staging in its visual_plan
                            # (an AD pass the director approved), it replaces
                            # those fallbacks with real light, a real action
                            # line, and a real camera. Absent staging leaves the
                            # fallbacks untouched, so this only ever adds
                            # specificity -- it can never blank a slot that had
                            # content. This is the wire that carries the
                            # director's shot into the prompt; without it the
                            # staging sits in the database unread.
                            _camera_direction = ""
                            try:
                                _shot_staging = {}
                                if _render_context_storage is not None and hasattr(
                                    _render_context_storage, "get_shot_visual_plan"
                                ):
                                    _shot_staging = (
                                        _render_context_storage.get_shot_visual_plan(
                                            project_id, shot_id
                                        )
                                        or {}
                                    )
                                if _shot_staging.get("action"):
                                    _action_text = str(_shot_staging["action"])
                                if _shot_staging.get("lighting"):
                                    _lighting = str(_shot_staging["lighting"])
                                _camera_direction = "; ".join(
                                    part for part in (
                                        _shot_staging.get("camera_angle"),
                                        _shot_staging.get("lens_language"),
                                        _shot_staging.get("composition"),
                                    ) if part
                                )
                                _staging_props = _shot_staging.get("props")
                                if _staging_props:
                                    _environment = (
                                        f"{_environment}. {_staging_props}"
                                        if _environment else str(_staging_props)
                                    )
                            except Exception as _staging_exc:
                                logger.debug(
                                    "Shot staging override skipped for %s/%s: %s",
                                    project_id, shot_id, _staging_exc,
                                )

                            # 5. Build the slotted prompt
                            from app.services.shot_prompt_builder import build_slotted_prompt
                            _slotted = build_slotted_prompt(
                                scene_data=_scene,
                                shot_number=_shot_number,
                                character_visual_canon=_char_visuals,
                                action_text=_action_text,
                                environment_motifs=_environment,
                                camera_direction=_camera_direction,
                                lighting_direction=_lighting,
                            )
                            prompt = _slotted["prompt"]

                            # ── Standing corrections injection (Phase 3) ─────
                            # Mutates _slotted["slots"] in place. Only re-assembles
                            # the prompt if corrections were actually applied —
                            # no change to prompt construction when no corrections
                            # match.
                            from app.services.standing_corrections_service import (
                                standing_corrections_service as _sc_svc,
                            )
                            from app.services.shot_prompt_builder import (
                                SLOT_BUDGETS, _truncate_to_budget,
                                reassemble_prompt_from_slots, _SLOT_ASSEMBLY_ORDER,
                            )
                            from app.services.script_parser import sanitize_render_slot
                            _sc_applied = _sc_svc.inject_into_slots(
                                project_id=project_id,
                                slots=_slotted["slots"],
                                shot_context={
                                    "shot_id": shot_id,
                                    "shot_number": _shot_number,
                                },
                                job_id=job_id,
                            )
                            if _sc_applied:
                                for _slot_name in _SLOT_ASSEMBLY_ORDER:
                                    _slot_val = _slotted["slots"].get(_slot_name, "")
                                    if _slot_val:
                                        _slot_val = sanitize_render_slot(_slot_name, _slot_val)
                                        _slotted["slots"][_slot_name] = _truncate_to_budget(
                                            _slot_val, SLOT_BUDGETS[_slot_name]
                                        )
                                _reassembled = reassemble_prompt_from_slots(_slotted["slots"])
                                if _reassembled != "Cinematic shot. Film quality.":
                                    prompt = _reassembled
                            _prompt_slots_for_adherence = {
                                str(_slot_name): str(_slot_value or "")
                                for _slot_name, _slot_value in (_slotted.get("slots") or {}).items()
                                if _slot_name != "reserve"
                            }
                            _intent_fidelity_report = _build_intent_fidelity(_slotted, shot_id)

                            logger.info(
                                "RENDER_PROMPT_FROM_SCENE | scene=%s | content_length=%d | action_length=%d | prompt_length=%d | slots=%s",
                                _scene_id,
                                len(_full_content),
                                len(_action_text),
                                len(prompt),
                                {k: len(v) for k, v in _slotted["slots"].items()},
                            )
            except Exception as _exc:
                logger.warning("Failed to fetch scene description for prompt: %s", _exc)

        _knowledge_started = time.perf_counter()
        if execution_mode is not None:
            _render_scene_data = {}
            _render_scene_chars = []
            _render_context_storage = None
            _render_knowledge_context = None
        try:
            if execution_mode is not None:
                raise StopIteration
            if not _render_scene_data:
                _project_for_context = project_store.get_project(project_id)
                if isinstance(_project_for_context, dict):
                    _summary_for_context = _project_for_context.get("execution_summary") or {}
                    _scenes_for_context = _summary_for_context.get("scenes") or []
                    _found_for_context = next(
                        (
                            scene
                            for scene in _scenes_for_context
                            if isinstance(scene, dict)
                            and scene.get("scene_id") == _scene_id
                        ),
                        None,
                    )
                    if isinstance(_found_for_context, dict):
                        _render_scene_data = dict(_found_for_context)
            if not _render_scene_chars and _render_scene_data:
                _render_scene_chars = _normalize_character_names(
                    _render_scene_data.get("characters")
                    or _render_scene_data.get("character_appearances")
                    or []
                )
            if _render_context_storage is None:
                _render_context_storage = _storage
                if _render_context_storage is None:
                    from app.data.storage import get_storage as _get_context_storage

                    _render_context_storage = _get_context_storage("sqlite")
            if not _render_scene_chars and _render_context_storage is not None:
                _all_context_characters = _render_context_storage.get_characters(project_id)
                _context_scene_text = " ".join(
                    str(_render_scene_data.get(key) or "")
                    for key in ("text", "content", "description", "scene_text")
                )
                _render_scene_chars = _infer_scene_characters_from_text(
                    _all_context_characters,
                    primary_text=prompt,
                    fallback_text=_context_scene_text,
                )

            from app.services.render_context_enrichment_service import (
                render_context_enrichment_service as _render_context_svc,
            )

            _render_knowledge_context = _render_context_svc.build_context(
                project_id=project_id,
                scene_id=_scene_id,
                shot_id=shot_id,
                scene_data=_render_scene_data,
                character_names=_render_scene_chars,
                storage=_render_context_storage,
            )
            if (
                _frozen_reference_binding is None
                and _render_knowledge_context is not None
                and not _render_knowledge_context.is_empty
                and _prompt_slots_for_adherence
                and "_slotted" in locals()
            ):
                from app.services.shot_prompt_builder import (
                    merge_knowledge_guidance_into_slots,
                    reassemble_prompt_from_slots,
                )

                merge_knowledge_guidance_into_slots(
                    _slotted["slots"],
                    _render_knowledge_context.slot_guidance,
                )
                _knowledge_prompt_applied = True
                prompt = reassemble_prompt_from_slots(_slotted["slots"])
                _prompt_slots_for_adherence = {
                    str(_slot_name): str(_slot_value or "")
                    for _slot_name, _slot_value in (_slotted.get("slots") or {}).items()
                    if _slot_name != "reserve"
                }
        except Exception as _exc:
            logger.warning(
                "Render knowledge context unavailable for %s/%s: %s",
                project_id,
                shot_id,
                _exc,
            )
        finally:
            from app.services.stability import log_stage_event

            log_stage_event(
                project_id=project_id,
                job_id=job_id,
                provider=provider,
                stage="render_context_enrichment",
                duration_ms=int((time.perf_counter() - _knowledge_started) * 1000),
                extra={
                    "selected_atom_count": (
                        len(_render_knowledge_context.selected_atom_ids)
                        if _render_knowledge_context is not None
                        else 0
                    ),
                },
            )

        _consistency_payload = _frozen_consistency_payload
        _canonical_identity_context = None
        _resolved_identity_characters: list[dict[str, Any]] = []
        try:
            if execution_mode is not None or _frozen_reference_binding is not None:
                raise StopIteration
            _active_storage_for_refs = _storage
            if _active_storage_for_refs is None:
                from app.data.storage import get_storage as _get_storage

                _active_storage_for_refs = _get_storage("sqlite")
            if _active_storage_for_refs is not None:
                from app.services.character_visual_reference_service import (
                    character_visual_reference_service as _char_ref_svc,
                )

                _resolved_identity_characters = _char_ref_svc.resolve_shot_characters(
                    project_id=project_id,
                    shot_id=shot_id,
                    storage=_active_storage_for_refs,
                    prompt=prompt,
                )
                _consistency_payload = _char_ref_svc.build_consistency_payload_for_shot(
                    project_id=project_id,
                    shot_id=shot_id,
                    storage=_active_storage_for_refs,
                    prompt=prompt,
                    ensure_provisional_locks=provider != "local_ltx",
                )
        except StopIteration:
            # The prepared binding is authoritative; do not independently
            # select or enrich character references from mutable state.
            pass
        except Exception as _exc:
            logger.debug("Character reference consistency lookup skipped for %s/%s: %s", project_id, shot_id, _exc)

        if _consistency_payload is not None:
            logger.info(
                "CHARACTER_REFERENCE_CONSISTENCY_ATTACHED | project=%s | shot=%s | refs=%d",
                project_id,
                shot_id,
                len(_consistency_payload.refs),
            )
            if provider == "happyhorse":
                provider = "happyhorse-r2v"
                logger.info(
                    "CHARACTER_REFERENCE_PROVIDER_ROUTED | project=%s | shot=%s | provider=happyhorse-r2v",
                    project_id,
                    shot_id,
                )

        try:
            if execution_mode is not None or _frozen_reference_binding is not None:
                raise StopIteration
            _active_storage_for_identity = _active_storage_for_refs if "_active_storage_for_refs" in locals() else _storage
            if _active_storage_for_identity is not None:
                from app.services.character_identity_memory_service import (
                    character_identity_memory_service as _identity_svc,
                )
                from app.services.character_visual_reference_service import (
                    character_visual_reference_service as _identity_char_ref_svc,
                )
                from app.services.render_executor import get_render_provider_capability as _provider_capability

                _identity_characters = []
                try:
                    _identity_characters = _identity_char_ref_svc.resolve_shot_characters(
                        project_id=project_id,
                        shot_id=shot_id,
                        storage=_active_storage_for_identity,
                        prompt=prompt,
                    )
                except Exception:
                    _identity_characters = []
                _identity_character_ids = [
                    str(character.get("id") or "").strip()
                    for character in _identity_characters
                    if isinstance(character, dict) and str(character.get("id") or "").strip()
                ]
                _identity_scene = {"scene_id": _scene_id, "characters": []}
                try:
                    _project = project_store.get_project(project_id)
                    if isinstance(_project, dict):
                        _summary = _project.get("execution_summary") or {}
                        _scenes = _summary.get("scenes") or []
                        _found_scene = next(
                            (
                                scene
                                for scene in _scenes
                                if isinstance(scene, dict) and scene.get("scene_id") == _scene_id
                            ),
                            None,
                        )
                        if isinstance(_found_scene, dict):
                            _identity_scene = dict(_found_scene)
                except Exception:
                    pass
                if (
                    not _normalize_character_names(
                        _identity_scene.get("characters")
                        or _identity_scene.get("character_appearances")
                        or []
                    )
                    and _identity_characters
                ):
                    _identity_scene["characters"] = [
                        str(character.get("name") or "").strip()
                        for character in _identity_characters
                        if isinstance(character, dict)
                        and str(character.get("name") or "").strip()
                    ]
                _identity_records = (
                    _identity_svc.build_records_from_storage(
                        project_id=project_id,
                        storage=_active_storage_for_identity,
                        character_ids=_identity_character_ids,
                    )
                    if _identity_character_ids
                    else []
                )
                if _identity_records:
                    _canonical_identity_context = _identity_svc.build_provider_context_from_records(
                        _identity_records,
                        _identity_scene,
                        shot_id=shot_id,
                        provider_capability=_provider_capability(provider),
                    )
        except Exception as _exc:
            logger.debug("Canonical character identity context skipped for %s/%s: %s", project_id, shot_id, _exc)

        if _frozen_reference_binding is not None:
            _resolved_identity_characters = [
                {"id": str(row.get("target_id") or ""), "name": ""}
                for row in _frozen_reference_binding
                if row.get("target_type") == "character" and str(row.get("target_id") or "").strip()
            ]

        _identity_prompt_guidance = ""
        if isinstance(_canonical_identity_context, dict):
            _constraint = _canonical_identity_context.get("constraint_injection")
            if isinstance(_constraint, dict):
                _identity_prompt_guidance = _compact_prompt_guidance(
                    [
                        str(line).strip()
                        for line in (_constraint.get("text_constraints") or [])
                        if str(line).strip()
                        and not (
                            "not yet verified" in str(line).lower()
                            and "current appearance:" not in str(line).lower()
                        )
                    ],
                    150,
                )
        if _frozen_reference_binding is None and _identity_prompt_guidance and _prompt_slots_for_adherence and "_slotted" in locals():
            from app.services.shot_prompt_builder import (
                merge_identity_guidance_into_slots,
                reassemble_prompt_from_slots,
            )

            merge_identity_guidance_into_slots(
                _slotted["slots"],
                _identity_prompt_guidance,
            )
            _identity_prompt_applied = True
            prompt = reassemble_prompt_from_slots(_slotted["slots"])
            _prompt_slots_for_adherence = {
                str(_slot_name): str(_slot_value or "")
                for _slot_name, _slot_value in (_slotted.get("slots") or {}).items()
                if _slot_name != "reserve"
            }

        if (
            _frozen_reference_binding is None
            and _prompt_slots_for_adherence
            and "_slotted" in locals()
            and isinstance(parameters, dict)
            and parameters.get("structured_prompt")
            and not parameters.get("preserve_shot_prompt")
        ):
            try:
                from app.services.department_render_context_service import (
                    department_render_context_service as _dept_context_svc,
                )
                from app.services.shot_prompt_builder import (
                    merge_knowledge_guidance_into_slots,
                    reassemble_prompt_from_slots,
                )

                _department_scene_context = dict(_render_scene_data or {})
                if isinstance(parameters, dict):
                    _shot_planning = parameters.get("shot_planning")
                    if isinstance(_shot_planning, dict):
                        _department_scene_context["shot_planning"] = _shot_planning
                    _department_scene_context["prompt_text"] = prompt
                _department_render_context = _dept_context_svc.build_slot_guidance(
                    project_id=project_id,
                    scene_id=_scene_id,
                    shot_id=shot_id,
                    render_job_id=job_id,
                    scene_context=_department_scene_context,
                    parameters=parameters if isinstance(parameters, dict) else {},
                )
                merge_knowledge_guidance_into_slots(
                    _slotted["slots"],
                    _department_render_context.get("slot_guidance") or {},
                )
                prompt = reassemble_prompt_from_slots(_slotted["slots"])
                _prompt_slots_for_adherence = {
                    str(_slot_name): str(_slot_value or "")
                    for _slot_name, _slot_value in (_slotted.get("slots") or {}).items()
                    if _slot_name != "reserve"
                }
            except Exception as _exc:
                logger.debug("Department render context skipped for %s/%s: %s", project_id, shot_id, _exc)

        _input_parameters = deepcopy(parameters) if isinstance(parameters, dict) else {}
        if provider == "local_ltx":
            # Provider projection consumes only the explicit structured shot plan;
            # do not infer framing from prose or prompt keywords. The library's
            # multi-reference consistency set remains intact as canonical truth.
            _shot_context = {
                "scene_id": _scene_id,
                "shot_id": shot_id,
                "setting_id": (
                    str((_render_scene_data or {}).get("setting_id")
                        or (_render_scene_data or {}).get("location_id")
                        or "").strip()
                ),
            }
            try:
                if _frozen_reference_binding is None and _render_context_storage is not None and hasattr(_render_context_storage, "get_shot_visual_plan"):
                    _visual_plan = _render_context_storage.get_shot_visual_plan(project_id, shot_id) or {}
                    if isinstance(_visual_plan, dict):
                        for _key in ("framing", "lighting"):
                            if _visual_plan.get(_key):
                                _shot_context[_key] = _visual_plan[_key]
            except Exception as _exc:
                logger.debug("Local LTX shot context lookup skipped for %s/%s: %s", project_id, shot_id, _exc)
            _frozen_setting_ids = [
                str(row.get("target_id") or "")
                for row in (_frozen_reference_binding or [])
                if row.get("target_type") == "setting" and str(row.get("target_id") or "").strip()
            ]
            if _frozen_setting_ids:
                _shot_context["setting_id"] = _frozen_setting_ids[0]
            _input_parameters["local_ltx_scene_context"] = _shot_context
        if _prompt_slots_for_adherence:
            identity_lines = []
            if isinstance(_canonical_identity_context, dict):
                constraint = _canonical_identity_context.get("constraint_injection")
                if isinstance(constraint, dict) and isinstance(constraint.get("text_constraints"), list):
                    identity_lines.extend(
                        str(line).strip()
                        for line in constraint.get("text_constraints") or []
                        if str(line).strip()
                    )
            if _consistency_payload is not None:
                identity_lines.extend([
                    str(line).strip()
                    for line in (_consistency_payload.fallback_text or {}).values()
                    if str(line).strip()
                ])
            if identity_lines:
                _prompt_slots_for_adherence["identity_continuity"] = " ".join(identity_lines)
            _input_parameters["prompt_slots"] = _prompt_slots_for_adherence
        if _canonical_identity_context is not None:
            _input_parameters["character_identity_context"] = _canonical_identity_context
        if (
            _prepared_contract_record is None
            and _render_knowledge_context is not None
            and not _render_knowledge_context.is_empty
        ):
            _input_parameters["render_knowledge_context"] = (
                _render_knowledge_context.as_metadata()
            )
        if _prepared_contract_record is None and _department_render_context is not None:
            _input_parameters["department_render_context"] = (
                _department_render_context.get("metadata") or {}
            )
        _validate_model_override(provider, _input_parameters)
        # Creator-selected model capability enforcement: a concrete model that
        # cannot satisfy this shot's requirements fails closed here (before
        # persistence), never silently downgraded. The validated selection is
        # recorded below as requested/validated/effective identity.
        _creator_model_selection = _validate_user_model_capabilities(
            provider, _input_parameters, reference_assets
        )

        _environment_context = None
        try:
            if execution_mode is not None or _frozen_reference_binding is not None:
                raise StopIteration
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )

            _environment_scene_data: dict[str, Any] = {}
            try:
                _project = project_store.get_project(project_id)
                if isinstance(_project, dict):
                    _summary = _project.get("execution_summary") or {}
                    _scenes = _summary.get("scenes") or []
                    _found_scene = next(
                        (
                            scene
                            for scene in _scenes
                            if isinstance(scene, dict)
                            and scene.get("scene_id") == _scene_id
                        ),
                        {},
                    )
                    if isinstance(_found_scene, dict):
                        _environment_scene_data = dict(_found_scene)
            except Exception:
                _environment_scene_data = {}

            _environment_context = _cont_svc.resolve_environment_context(
                scene_id=_scene_id,
                film_id=project_id,
                shot_id=shot_id,
                prompt=prompt,
                scene_data=_environment_scene_data,
                parameters=_input_parameters,
            )
            _environment_lines = [
                str(line).strip()
                for line in (_environment_context.get("prompt_lines") or [])
                if str(line).strip()
            ]
            if _environment_lines:
                prompt = prompt + _ENVIRONMENT_CONTEXT_BLOCK.format(
                    environment_lines="\n".join(_environment_lines[:8])
                )
                _input_parameters["environment_continuity_context"] = _environment_context
                _input_parameters["environment_continuity_warnings"] = (
                    _environment_context.get("warnings") or []
                )
                logger.info(
                    "ENVIRONMENT_CONTINUITY_CONTEXT | project=%s | shot=%s | location=%s | warnings=%d | refs=%d",
                    project_id,
                    shot_id,
                    _environment_context.get("location_id") or "",
                    len(_environment_context.get("warnings") or []),
                    len(_environment_context.get("selected_references") or []),
                )
        except StopIteration:
            # Setting identity and its exact references were resolved during
            # preparation and are not reselected from mutable continuity state.
            pass
        except Exception as _exc:
            logger.debug("Environment continuity context skipped for %s/%s: %s", project_id, shot_id, _exc)

        # Environment references are part of the same final payload safety
        # boundary as character references. Keep their ownership explicit so a
        # later submit cannot accidentally reuse a previous scene's setting.
        if _frozen_reference_binding is None and isinstance(_environment_context, dict):
            _setting_id = str(_environment_context.get("location_id") or "").strip()
            _selected_environment_refs = _environment_context.get("selected_references") or []
            if _setting_id and isinstance(_selected_environment_refs, list):
                _environment_refs = []
                for _environment_ref in _selected_environment_refs:
                    if not isinstance(_environment_ref, dict):
                        continue
                    _image_url = str(_environment_ref.get("image_url") or "").strip()
                    if not _image_url:
                        continue
                    _environment_refs.append(ReferenceAsset(
                        ref_id=str(_environment_ref.get("ref_id") or _environment_ref.get("source_shot_id") or f"setting:{_setting_id}"),
                        kind="environment",
                        image_url=_image_url,
                        source_shot_id=_environment_ref.get("source_shot_id"),
                        project_id=project_id,
                        target_type="setting",
                        target_id=_setting_id,
                        category=str(_environment_ref.get("category") or "canonical"),
                        approval_state=str(_environment_ref.get("approval_state") or "approved"),
                        canonical=bool(_environment_ref.get("canonical", True)),
                        source_kind=str(_environment_ref.get("source_kind") or "confirmed"),
                        reference_created_at=str(_environment_ref.get("created_at") or ""),
                    ))
                if _environment_refs:
                    _existing_refs = list(_consistency_payload.refs) if _consistency_payload is not None else []
                    _existing_weights = dict(_consistency_payload.weights) if _consistency_payload is not None else {}
                    _existing_fallback = dict(_consistency_payload.fallback_text) if _consistency_payload is not None else {}
                    for _ref in _environment_refs:
                        if not any(existing.ref_id == _ref.ref_id for existing in _existing_refs):
                            _existing_refs.append(_ref)
                            _existing_weights[_ref.ref_id] = 0.35
                            _existing_fallback[_ref.ref_id] = "preserve the approved canonical environment layout and visual identity"
                    _consistency_payload = ConsistencyPayload(
                        project_id=project_id,
                        refs=_existing_refs,
                        weights=_existing_weights,
                        mode="identity_lock",
                        fallback_text=_existing_fallback,
                    )

        if provider == "local_ltx" and execution_mode is None:
            _local_ltx_scene_context = dict(_input_parameters.get("local_ltx_scene_context") or {})
            _local_ltx_scene_context["character_ids"] = sorted({
                str(character.get("id") or "").strip()
                for character in _resolved_identity_characters
                if isinstance(character, dict) and str(character.get("id") or "").strip()
            })
            _frozen_setting_ids = [
                str(row.get("target_id") or "")
                for row in (_frozen_reference_binding or [])
                if row.get("target_type") == "setting" and str(row.get("target_id") or "").strip()
            ]
            if _frozen_setting_ids:
                _local_ltx_scene_context["setting_id"] = _frozen_setting_ids[0]
            elif isinstance(_environment_context, dict) and _environment_context.get("location_id"):
                _local_ltx_scene_context["setting_id"] = str(_environment_context["location_id"])
            _input_parameters["local_ltx_scene_context"] = _local_ltx_scene_context

        _zero_touch_debug = _zero_touch_debug_metadata(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            parameters=_input_parameters,
            prompt=prompt,
            consistency_payload=_consistency_payload,
        )
        if _canonical_identity_context is not None:
            _zero_touch_debug["character_identity_context"] = _canonical_identity_context
            _zero_touch_debug["identity_conflict_warnings"] = _canonical_identity_context.get("conflict_warnings", [])
        _input_parameters["zero_touch_debug"] = _zero_touch_debug

        # ── Negative prompt (separate channel, not part of the 512-char budget) ──
        # Built here rather than in the slot builder because it needs the resolved
        # cast and the selected provider. Providers without a negative prompt
        # field get an empty string and are unaffected.
        _negative_prompt = str((_prepared_contract_payload or {}).get("negative_prompt") or "")
        try:
            from app.services.negative_prompt_builder import (
                build_negative_prompt as _build_negative_prompt,
                provider_supports_negative_prompt as _provider_supports_negative,
            )

            if _prepared_contract_record is None and _provider_supports_negative(provider):
                # The director's "what to avoid" belongs here, not in the
                # positive prompt. Asking a video model to honour "Avoid:
                # melodrama" inside the positive prompt relies on it processing
                # a negation, which is unreliable — naming the thing can summon
                # it. In the negative channel an exclusion actually excludes.
                _intent_avoid_terms: list[str] = []
                try:
                    from app.utils.director_intent_injection import (
                        director_intent_negative_terms as _intent_negatives,
                    )
                    from app.data.storage import get_storage as _get_storage_for_intent

                    _intent_avoid_terms = _intent_negatives(
                        _get_storage_for_intent().load_director_intent(project_id)
                    )
                except Exception as _intent_exc:
                    logger.debug("Director intent negatives skipped for %s: %s", project_id, _intent_exc)

                _input_parameters["required_negative_terms"] = list(_input_parameters.get("negative_prompt_terms") or []) + _intent_avoid_terms
                _negative_prompt = _build_negative_prompt(
                    cast_names=_render_scene_chars or [],
                    extra_terms=[
                        str(term)
                        for term in (_input_parameters.get("negative_prompt_terms") or [])
                        if str(term or "").strip()
                    ] + _intent_avoid_terms,
                    disabled_groups=[
                        str(group)
                        for group in (_input_parameters.get("negative_prompt_disabled_groups") or [])
                        if str(group or "").strip()
                    ],
                )
                if _negative_prompt:
                    logger.info(
                        "RENDER_NEGATIVE_PROMPT_BUILT | project=%s | shot=%s | provider=%s | length=%d",
                        project_id,
                        shot_id,
                        provider,
                        len(_negative_prompt),
                    )
        except Exception as _exc:
            logger.debug("Negative prompt build skipped for %s/%s: %s", project_id, shot_id, _exc)

        # Record what budget compression removed from the director's intent, so a
        # silent loss is visible before the render is paid for rather than never.
        if _intent_fidelity_report:
            _input_parameters["intent_fidelity"] = _intent_fidelity_report

        # Capture the project's cinematic identity so revisions can be traced
        # against the visual language that was in force when this job was created.
        _identity_snapshot = None
        try:
            if execution_mode is not None:
                raise StopIteration
            from app.services.identity_snapshot_service import identity_snapshot_service

            _identity_snapshot = identity_snapshot_service.capture(project_id)
        except StopIteration:
            pass
        except Exception as exc:  # noqa: BLE001 — identity snapshot is advisory only
            logger.warning("identity snapshot capture failed for %s: %s", project_id, exc)
            _identity_snapshot = None

        if _frozen_reference_binding is not None:
            _input_parameters["reference_roles"] = [str(row.get("role") or "reference") for row in _frozen_reference_binding]
            _input_parameters["frozen_reference_binding"] = deepcopy(_frozen_reference_binding)

        job = RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=prompt,
                negative_prompt=_negative_prompt,
                referenceAssets=reference_assets or [],
                parameters=_input_parameters,
                consistency_payload=_consistency_payload,
            ),                metadata={
                    "zero_touch_pipeline": _zero_touch_debug,
                    **({
                        "prepared_generation_contract": deepcopy(_prepared_contract_record),
                        "prepared_creative_manifest": deepcopy(_prepared_manifest),
                        "prepared_reference_binding_sha256": _reference_binding_digest,
                    } if _prepared_contract_record is not None else {}),

                "character_identity_warnings": (
                    _canonical_identity_context.get("conflict_warnings", [])
                    if isinstance(_canonical_identity_context, dict)
                    else []
                ),
                "environment_continuity_context": _environment_context or {},
                **({
                    "frozen_reference_binding": deepcopy(_frozen_reference_binding),
                    "frozen_reference_binding_sha256": _reference_binding_digest,
                } if _frozen_reference_binding is not None else {}),
                "environment_continuity_warnings": (
                    (_environment_context or {}).get("warnings") or []
                    if isinstance(_environment_context, dict)
                    else []
                ),
                "pipeline_reliability": {
                    "correlation_id": f"corr-{uuid.uuid4().hex[:16]}",
                    "idempotency_key": _idempotency_key,
                    "idempotency_key_source": "caller" if _explicit_idempotency_key else "request_hash",
                    "created_at": datetime.now().isoformat(),
                    "phase_timing": {},
                },
                **(_generation_context_metadata(job_id, provider, _initial_parameters, reference_assets, prompt)),
                **(
                    {
                        "creator_model_identity": {
                            "requested": str(_input_parameters.get("model") or "").strip(),
                            "validated": _creator_model_selection.get("selection_mode", "USER_SELECTED"),
                            "effective": _creator_model_selection.get("model_id"),
                            "selection_reason": _creator_model_selection.get("selection_reason", ""),
                        }
                    }
                    if _creator_model_selection is not None
                    else {}
                ),
                **(deepcopy(metadata) if isinstance(metadata, dict) else {}),
                **({
                    "production_request_actor_id": __import__("app.access_context", fromlist=["access_user_id"]).access_user_id.get() or ""
                } if provider == "runway_router" else {}),
                **({"creative_dialogue_handoff": dialogue_handoff} if dialogue_handoff is not None else {}),
                **(
                    {"cinematic_identity_snapshot": _identity_snapshot}
                    if _identity_snapshot
                    else {}
                ),
            },
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )

        # ── Character visual description injection (non-generic prompts) ──────
        # For prompts that already have content (e.g., from Previs Room's
        # Generation Settings panel with duration/fps/resolution/seed), inject
        # character visual descriptions so the video provider generates the
        # correct character appearance.  This mirrors the storyboard/Pollinations
        # fix but for the video render path.  Generic prompts are already
        # handled by the block above; this covers the Previs Room render path.
        _skip_character_injection = bool(
            isinstance(parameters, dict)
            and parameters.get("skip_character_injection")
        )
        if execution_mode is None and not _is_generic and not _skip_character_injection and _frozen_reference_binding is None:
            try:
                from app.data.storage import get_storage as _get_storage
                _active_storage = _get_storage()
                _project = project_store.get_project(project_id)
                _scene_chars: list[str] = []
                if isinstance(_project, dict):
                    _summary = _project.get("execution_summary") or {}
                    _scenes = _summary.get("scenes") or []
                    _scene = next(
                        (s for s in _scenes if isinstance(s, dict) and s.get("scene_id") == _scene_id),
                        None,
                    )
                    if _scene:
                        _scene_chars = _normalize_character_names(
                            _scene.get("characters") or _scene.get("character_appearances") or []
                        )
                        # If no characters array, try to identify from scene text
                        if not _scene_chars:
                            try:
                                _all_chars = _active_storage.get_characters(project_id)
                                _scene_text = (
                                    str(_scene.get("text") or "")
                                    or str(_scene.get("content") or "")
                                    or str(_scene.get("description") or "")
                                    or str(_scene.get("scene_text") or "")
                                )
                                _scene_chars = _infer_scene_characters_from_text(
                                    _all_chars,
                                    primary_text=job.input_payload.prompt or "",
                                    fallback_text=_scene_text,
                                )
                            except Exception:
                                pass

                if _scene_chars and _active_storage:
                    from app.services.character_staging_service import (
                        resolve_character_prompt as _resolve_char_prompt,
                    )
                    _char_summaries: list[str] = []
                    for _char_name in _scene_chars:
                        _char_name_str = str(_char_name).strip()
                        if _char_name_str:
                            _char_record = _active_storage.get_character_by_name(
                                project_id, _char_name_str
                            )
                            if _char_record:
                                try:
                                    _resolved = _resolve_char_prompt(
                                        _char_record,
                                        _scene_id,
                                        shot_id,
                                        _active_storage,
                                    )
                                except Exception:
                                    _vps = (
                                        _char_record.get("visual_prompt_summary")
                                        or ""
                                    ).strip()
                                    _resolved = (
                                        f"{_char_name_str}: {_vps}"
                                        if _vps
                                        else ""
                                    )
                                if _resolved and _resolved != _char_name_str:
                                    _char_summaries.append(_resolved)
                    if _char_summaries:
                        _cast_constraint = _format_visible_cast_constraint(_scene_chars)
                        _char_state = "; ".join(
                            [part for part in [_cast_constraint, *_char_summaries] if part]
                        )
                        from app.services.shot_prompt_builder import (
                            SLOT_BUDGETS,
                            _fit_character_state_to_budget,
                            merge_identity_guidance_into_slots,
                        )

                        _char_state = _fit_character_state_to_budget(
                            _char_state,
                            SLOT_BUDGETS["character_state"],
                        )
                        if _identity_prompt_guidance:
                            _identity_slots = {"character_state": _char_state}
                            merge_identity_guidance_into_slots(
                                _identity_slots,
                                _identity_prompt_guidance,
                            )
                            _char_state = _identity_slots["character_state"]
                        _char_block = "Characters: " + _char_state
                        _current_prompt = job.input_payload.prompt or ""
                        # Skip if characters already present (e.g., generic prompt path)
                        if "Characters:" not in _current_prompt:
                            _new_prompt = _prepend_bounded_prompt_context(
                                _current_prompt,
                                _char_block,
                            )
                            job.input_payload.prompt = _new_prompt
                            _identity_prompt_applied = bool(
                                _identity_prompt_applied
                                or _identity_prompt_guidance
                            )
                            logger.info(
                                "CHARACTER_PROMPT_INJECTION | scene=%s | chars=%d | source=previs_prompt",
                                _scene_id,
                                len(_char_summaries),
                            )
            except Exception as _exc:
                logger.debug("Character injection for non-generic prompt skipped: %s", _exc)

        if (
            execution_mode is None
            and _frozen_reference_binding is None
            and isinstance(parameters, dict)
            and parameters.get("structured_prompt")
            and not job.input_payload.parameters.get("prompt_slots")
            and not parameters.get("preserve_shot_prompt")
        ):
            try:
                from app.services.shot_prompt_builder import build_slotted_prompt

                _current_prompt = job.input_payload.prompt or ""
                _shot_planning = parameters.get("shot_planning") if isinstance(parameters, dict) else None
                _planned_action = _join_shot_planning_values(
                    _shot_planning,
                    ["blocking", "purpose", "rationale"],
                )
                _action_text = _planned_action or _current_prompt
                _char_visuals = ""
                if "Characters:" in _current_prompt:
                    _prompt_action, _char_visuals = _current_prompt.split("Characters:", 1)
                    if not _planned_action:
                        _action_text = _prompt_action.strip()
                    _char_visuals = _char_visuals.strip()

                _scene_for_slots: dict[str, Any] = {}
                try:
                    _project = project_store.get_project(project_id)
                    if isinstance(_project, dict):
                        _summary = _project.get("execution_summary") or {}
                        _scenes = _summary.get("scenes") or []
                        _scene_for_slots = next(
                            (
                                s for s in _scenes
                                if isinstance(s, dict)
                                and s.get("scene_id") == _scene_id
                            ),
                            {},
                        )
                except Exception:
                    _scene_for_slots = {}

                _shot_number = 1
                try:
                    _shot_suffix = shot_id.rsplit("_shot_", 1)
                    if len(_shot_suffix) == 2:
                        _shot_number = int(_shot_suffix[1])
                except (ValueError, IndexError):
                    pass

                _planned_environment = _shot_planning_value(_shot_planning, "production")
                _environment = _planned_environment or (
                    str(_scene_for_slots.get("location") or "").strip()
                    or str(_scene_for_slots.get("heading") or "").strip()
                )
                _planned_lighting = _shot_planning_value(_shot_planning, "atmosphere")
                _lighting = _planned_lighting or " ".join(
                    p for p in [
                        str(_scene_for_slots.get("time_of_day") or "").strip(),
                        str(_scene_for_slots.get("emotional_tone") or "").strip(),
                    ]
                    if p
                )
                _camera_direction = _join_shot_planning_values(
                    _shot_planning,
                    ["framing", "camera", "composition"],
                )
                _slotted = build_slotted_prompt(
                    scene_data=_scene_for_slots,
                    shot_number=_shot_number,
                    character_visual_canon=_char_visuals,
                    action_text=_action_text,
                    environment_motifs=_environment,
                    camera_direction=_camera_direction,
                    lighting_direction=_lighting,
                )
                from app.services.shot_prompt_builder import (
                    merge_identity_guidance_into_slots,
                    merge_knowledge_guidance_into_slots,
                )

                if (
                    _render_knowledge_context is not None
                    and not _render_knowledge_context.is_empty
                ):
                    merge_knowledge_guidance_into_slots(
                        _slotted["slots"],
                        _render_knowledge_context.slot_guidance,
                    )
                    _knowledge_prompt_applied = True
                if _identity_prompt_guidance:
                    merge_identity_guidance_into_slots(
                        _slotted["slots"],
                        _identity_prompt_guidance,
                    )
                    _identity_prompt_applied = True
                try:
                    from app.services.department_render_context_service import (
                        department_render_context_service as _dept_context_svc,
                    )

                    _department_scene_context = dict(_scene_for_slots or {})
                    if isinstance(_shot_planning, dict):
                        _department_scene_context["shot_planning"] = _shot_planning
                    _department_scene_context["prompt_text"] = _current_prompt
                    _department_render_context = _dept_context_svc.build_slot_guidance(
                        project_id=project_id,
                        scene_id=_scene_id,
                        shot_id=shot_id,
                        render_job_id=job_id,
                        scene_context=_department_scene_context,
                        parameters=parameters if isinstance(parameters, dict) else {},
                    )
                    merge_knowledge_guidance_into_slots(
                        _slotted["slots"],
                        _department_render_context.get("slot_guidance") or {},
                    )
                except Exception as _exc:
                    logger.debug("Department structured prompt context skipped for %s: %s", job_id, _exc)
                from app.services.standing_corrections_service import (
                    standing_corrections_service as _sc_svc,
                )
                from app.services.shot_prompt_builder import (
                    SLOT_BUDGETS, _truncate_to_budget,
                    reassemble_prompt_from_slots, _SLOT_ASSEMBLY_ORDER,
                )
                from app.services.script_parser import sanitize_render_slot

                _sc_applied = _sc_svc.inject_into_slots(
                    project_id=project_id,
                    slots=_slotted["slots"],
                    shot_context={
                        "shot_id": shot_id,
                        "shot_number": _shot_number,
                    },
                    job_id=job_id,
                )
                if _sc_applied:
                    for _slot_name in _SLOT_ASSEMBLY_ORDER:
                        _slot_val = _slotted["slots"].get(_slot_name, "")
                        if _slot_val:
                            _slot_val = sanitize_render_slot(_slot_name, _slot_val)
                            _slotted["slots"][_slot_name] = _truncate_to_budget(
                                _slot_val, SLOT_BUDGETS[_slot_name]
                            )

                _reassembled = reassemble_prompt_from_slots(_slotted["slots"])
                if _reassembled != "Cinematic shot. Film quality.":
                    job.input_payload.prompt = _reassembled
                else:
                    job.input_payload.prompt = _slotted["prompt"]
                job.input_payload.parameters["prompt_slots"] = {
                    str(_slot): str(_value or "")
                    for _slot, _value in (_slotted.get("slots") or {}).items()
                    if _slot != "reserve"
                }
                # This path rebuilds the prompt after job creation, so the
                # fidelity record from job creation is stale — recompute against
                # what is actually going out.
                _structured_fidelity = _build_intent_fidelity(_slotted, shot_id)
                if _structured_fidelity:
                    job.input_payload.parameters["intent_fidelity"] = _structured_fidelity
                if _department_render_context is not None:
                    job.input_payload.parameters["department_render_context"] = (
                        _department_render_context.get("metadata") or {}
                    )
                logger.info(
                    "STRUCTURED_PREVIS_PROMPT_APPLIED | job=%s | scene=%s | shot_planning=%s | slots=%s",
                    job_id,
                    _scene_id,
                    isinstance(_shot_planning, dict),
                    {k: len(v) for k, v in job.input_payload.parameters["prompt_slots"].items()},
                )
            except Exception as _exc:
                logger.debug("Structured prompt assembly skipped for job %s: %s", job_id, _exc)

        if job.input_payload and job.input_payload.prompt:
            prompt = job.input_payload.prompt

        if execution_mode is not None:
            job.input_payload.prompt = str((_prepared_contract_payload or {}).get("prompt") or "")
            _input_parameters = deepcopy(_initial_parameters)
        _missing_provider_context: list[str] = []
        if _identity_prompt_guidance and not _identity_prompt_applied:
            _missing_provider_context.append(
                f"Identity canon: {_identity_prompt_guidance}"
            )
        if (
            _render_knowledge_context is not None
            and not _render_knowledge_context.is_empty
            and not _knowledge_prompt_applied
        ):
            _knowledge_lines = [
                str(_render_knowledge_context.slot_guidance.get(slot_name) or "").strip()
                for slot_name in (
                    "character_state",
                    "action",
                    "environment_persistence",
                    "camera",
                    "lighting",
                )
                if str(_render_knowledge_context.slot_guidance.get(slot_name) or "").strip()
            ]
            _creative_canon = _compact_prompt_guidance(_knowledge_lines, 132)
            if _creative_canon:
                _missing_provider_context.append(
                    f"Bible and Creative Spine canon: {_creative_canon}"
                )
        if _missing_provider_context and _prepared_contract_record is None and execution_mode is None:
            job.input_payload.prompt = _prepend_bounded_prompt_context(
                job.input_payload.prompt or "",
                _compact_prompt_guidance(_missing_provider_context, 220),
            )

        # ── Continuity context injection ──────────────────────────────────────
        # Derive scene_id from shot_id (e.g. "scene_001_shot_001" → "scene_001").
        # film_id is the project_id — they are the same identifier here.
        try:
            if execution_mode is not None:
                raise StopIteration
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            from app.utils.director_intent_injection import (
                build_director_intent_render_guidance,
            )
            from app.data.storage import get_storage
            
            _scene_id = derive_scene_id_from_shot_id(shot_id)
            _ctx = _cont_svc.build_prompt_context(scene_id=_scene_id, film_id=project_id)
            _has_context = bool(
                _ctx.get("emotional_register")
                or _ctx.get("active_motifs")
                or _ctx.get("tonal_direction")
                or _ctx.get("continuity_anchors")
            )
            
            # Director intent, in render-facing form.
            #
            # This used to prepend the multi-line prose block built for Claude
            # system prompts. Because the provider weights early tokens most
            # heavily (POSITIONAL_WEIGHTING_FINDING.md), that put project-level
            # abstractions — genre, "what success looks like" — ahead of who is
            # on screen and what they do, and with a realistic intent the prefix
            # ran longer than the entire slotted prompt it was prefixing.
            #
            # The shot leads now; standing project context trails it, bounded.
            _director_storage = get_storage()
            _intent = _director_storage.load_director_intent(project_id)
            _intent_guidance = build_director_intent_render_guidance(_intent)

            if _prepared_contract_record is None and _intent_guidance:
                _existing_prompt = (job.input_payload.prompt or "").rstrip()
                _separator = " " if _existing_prompt.endswith(".") else ". "
                job.input_payload.prompt = f"{_existing_prompt}{_separator}Tone: {_intent_guidance}."
                logger.info(
                    "DIRECTOR_INTENT_INJECTION | project=%s | guidance_chars=%d",
                    project_id,
                    len(_intent_guidance),
                )
            
            # Append continuity context if it exists
            if _prepared_contract_record is None and _has_context:
                _motifs = _ctx["active_motifs"]
                _anchors = _ctx["continuity_anchors"]
                _block = _CONTINUITY_CONTEXT_BLOCK.format(
                    emotional_register=_ctx["emotional_register"] or "unspecified",
                    active_motifs=", ".join(_motifs) if _motifs else "none",
                    tonal_direction=_ctx["tonal_direction"] or "unspecified",
                    continuity_anchors=", ".join(_anchors) if _anchors else "none",
                )
                job.input_payload.prompt = (job.input_payload.prompt or "") + _block
                job.continuity_context_injected = True
                logger.info(
                    "CONTINUITY_PROMPT_INJECTION | scene=%s | motifs=%d | anchors=%d",
                    _scene_id,
                    len(_motifs),
                    len(_anchors),
                )
        except Exception as _exc:  # never block a render
            logger.debug("Continuity context injection skipped: %s", _exc)

        # Authoritative provider budgeting happens after all shot context and
        # corrections are collected, preserving whole required facts.
        if _prepared_contract_payload is not None:
            # The prepared contract is the creative authority. Enforce the
            # provider ceiling without reassembling or compressing its prompt.
            from app.services.prompt_budget_service import validate_provider_text

            try:
                validate_provider_text(
                    job,
                    str(_prepared_contract_payload.get("prompt") or ""),
                    _provider_model_for_job(provider, _input_parameters),
                )
                _budget_ready = True
                _budget_message = ""
            except ValueError as exc:
                _budget_ready = False
                _budget_message = str(exc)
            _budget_result = type("FrozenPromptBudget", (), {"ready": _budget_ready, "omitted_ids": []})()
            job.metadata = dict(job.metadata or {})
            if execution_mode is None:
                job.metadata["prepared_prompt_budget"] = {
                    "ready": _budget_ready,
                    "prompt_preserved": job.input_payload.prompt == _prepared_contract_payload.get("prompt"),
                    "message": _budget_message,
                }
            if not _budget_ready:
                job.status = "needs_review"
                job.error_message = _budget_message
        else:
            from app.services.prompt_budget_service import budget_job
            _budget_result = budget_job(job)
        log_stage_event(
            project_id=project_id, job_id=job_id, provider=provider,
            stage="prompt_budget", duration_ms=0,
            extra={"ready": _budget_result.ready, "omitted_fact_count": len(_budget_result.omitted_ids)},
        )

        _zero_touch_debug = _zero_touch_debug_metadata(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            parameters=job.input_payload.parameters,
            prompt=job.input_payload.prompt or "",
            consistency_payload=_consistency_payload,
        )
        if _canonical_identity_context is not None:
            _zero_touch_debug["character_identity_context"] = _canonical_identity_context
            _zero_touch_debug["identity_conflict_warnings"] = _canonical_identity_context.get("conflict_warnings", [])
        if execution_mode is None:
            job.input_payload.parameters["zero_touch_debug"] = _zero_touch_debug
            job.metadata = dict(job.metadata or {})
            job.metadata["zero_touch_pipeline"] = _zero_touch_debug
        _prompt_contradictions = _detect_prompt_contradictions(job.input_payload.prompt or "") if execution_mode is None else []
        if _prompt_contradictions:
            job.status = "needs_review"
            job.error_message = "Prompt contains contradictory instructions that require review before rendering."
            job.metadata["prompt_contradictions"] = _prompt_contradictions
            _set_zero_touch_phase(
                job,
                "prepare_provider_request",
                "needs_review",
                reason="contradictory prompt instructions",
                contradictions=_prompt_contradictions,
            )
            _set_zero_touch_phase(job, "render", "skipped", reason="needs review before provider submission")
            _set_zero_touch_phase(job, "evaluate", "skipped", reason="render not submitted")
            _set_zero_touch_phase(job, "retry", "skipped", reason="render not submitted")

        # Diagnostic logging for provider status
        config = self._provider_configs.get(provider)
        runway_api_key = (
            os.getenv("RUNWAYML_API_SECRET", "").strip()
            or os.getenv("RUNWAY_API_KEY", "").strip()
        )
        test_mode = str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()
        use_mock_success = bool(parameters and parameters.get("use_mock_success"))
        
        # Calculate ready_for_hosted_generation for this provider
        missing_requirements = []
        if config and "api_key" in config.requires and not (config.api_key or "").strip():
            missing_requirements.append("api_key")
        
        ready_for_hosted = bool(
            config
            and config.enabled
            and not config.is_simulated
            and not missing_requirements
            and not (provider in {"runway", "runway_direct"} and test_mode == "mock_success")
            and not use_mock_success
        )
        
        logger.info(
            "RENDER_JOB_CREATED | job_id=%s | provider=%s | hosted=%s | key_present=%s | test_mode=%s | use_mock=%s | missing=%s",
            job_id,
            provider,
            ready_for_hosted,
            bool(runway_api_key),
            test_mode or "none",
            use_mock_success,
            missing_requirements or "none"
        )
        
        # Log final prompt to verify description is included
        final_prompt = job.input_payload.prompt or ""
        logger.info(
            "FINAL_RENDER_PROMPT | scene=%s | prompt=%s",
            _scene_id,
            final_prompt[:150]
        )

        if execution_mode is not None:
            from app.services.scene002_contract_only import MODE
            job.input_payload.prompt = str((_prepared_contract_payload or {}).get("prompt") or "")
            job.input_payload.negative_prompt = str((_prepared_contract_payload or {}).get("negative_prompt") or "")
            job.input_payload.parameters = deepcopy(_initial_parameters)
            job.input_payload.consistency_payload = None
            if job.metadata.get("creative_generation_contract") != _prepared_contract_record:
                raise RuntimeError("Protected job metadata no longer matches its prepared contract")
            # Generic render setup is intentionally bypassed at the durable
            # boundary: only frozen proof and result/runtime bookkeeping survive.
            job.metadata = {
                "execution_mode": MODE,
                "scene002_execution_contract": deepcopy(scene002_execution_contract),
                "source_authority_id": source_authority_id,
                "creative_generation_contract": deepcopy(_prepared_contract_record),
                "creative_generation_manifest": deepcopy(_prepared_manifest),
                "creative_manifest_fingerprint": str(creative_manifest_fingerprint or ""),
                "creative_contract_digest": __import__("app.services.generation_contract", fromlist=["FrozenGenerationContract"]).FrozenGenerationContract.from_record(_prepared_contract_record).creative_digest(),
                "creative_generation_identity": {
                    "job_id": job_id,
                    "project_id": project_id,
                    "shot_id": shot_id,
                    "provider": provider,
                },
                "frozen_reference_binding": deepcopy(_frozen_reference_binding),
                "frozen_reference_binding_sha256": _reference_binding_digest,
                "creative_dialogue_handoff": deepcopy(dialogue_handoff),
                "pipeline_reliability": {
                    "correlation_id": f"corr-{uuid.uuid4().hex[:16]}",
                    "idempotency_key": hashlib.sha256(
                        json.dumps(scene002_execution_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest(),
                    "idempotency_key_source": "scene002_execution_contract",
                    "created_at": job.created_at,
                    "phase_timing": {},
                },
            }
        if provider == "runway_router" and execution_mode is None:
            from app.data.storage import get_storage as _get_authority_storage
            from app.services.production_authorization_service import authorize_runway_submission

            creation_storage = _storage or _get_authority_storage("sqlite")
            creation_authority = authorize_runway_submission(
                job,
                storage=creation_storage,
                require_durable=False,
            )
            if not creation_authority.allowed:
                raise ValueError(
                    f"Runway Router job creation denied: {creation_authority.reason}"
                )
            job.metadata["production_authorization"] = {
                "allowed": True,
                "reason": creation_authority.reason,
                "project_id": creation_authority.project_id,
                "job_id": creation_authority.job_id,
                "actor_id": creation_authority.actor_id,
                "stage": "job_creation",
            }

        self._jobs[job_id] = job
        persisted = _persist_job(job)
        if execution_mode is not None:
            from app.services.scene002_contract_only import verify_job_contract, verify_submission_boundary
            if not persisted or _storage is None:
                raise RuntimeError("Protected Scene 002 job must be durably persisted")
            reloaded = _storage.get_job(job_id)
            if reloaded is None:
                raise RuntimeError("Protected Scene 002 job could not be recovered after persistence")
            from app.services.providers.runway_router_provider import get_router_config_id
            from app.services.project_persistence_service import project_persistence_service
            verify_submission_boundary(
                reloaded,
                storage=_storage,
                project=project_persistence_service.load_readonly_existing(project_id),
                router_config_id=get_router_config_id(),
                backend_root=Path(__file__).resolve().parents[2],
            )
            if reloaded.metadata.get("scene002_execution_contract") != scene002_execution_contract:
                raise RuntimeError("Persisted Scene 002 execution contract changed during round-trip")
            self._jobs[job_id] = reloaded
            return reloaded
        if _prepared_contract_record is not None:
            if not persisted or _storage is None:
                raise RuntimeError("Prepared generation contracts require durable render-job storage")
            reloaded = _storage.get_job(job_id)
            if reloaded is None or not isinstance(getattr(reloaded, "metadata", None), dict):
                raise RuntimeError("Prepared render job could not be reloaded after persistence")
            if (
                reloaded.metadata.get("prepared_generation_contract") != _prepared_contract_record
                or reloaded.metadata.get("prepared_creative_manifest") != _prepared_manifest
                or reloaded.metadata.get("frozen_reference_binding") != _frozen_reference_binding
                or reloaded.metadata.get("frozen_reference_binding_sha256") != _reference_binding_digest
                or reloaded.input_payload.prompt != (_prepared_contract_payload or {}).get("prompt")
                or reloaded.input_payload.negative_prompt != (_prepared_contract_payload or {}).get("negative_prompt", "")
                or list(reloaded.input_payload.referenceAssets or []) != [row.get("uri") for row in (_prepared_contract_payload or {}).get("references", [])]
            ):
                raise RuntimeError("Persisted prepared render job failed frozen contract round-trip verification")
            from app.services.reference_validation import verify_frozen_reference_payload

            verify_frozen_reference_payload(
                job=reloaded,
                binding=reloaded.metadata.get("frozen_reference_binding"),
            )
            self._jobs[job_id] = reloaded
            return reloaded
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        """Submit a job to its provider with error handling"""
        job = self._jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for submission")
            raise ValueError(f"Job {job_id} not found")
        assert_queue_execution_lease_current()
        if job_id in self._submit_locks:
            logger.info("Duplicate submit blocked for %s", job_id)
            return job
        if job.status in {"rendering", "complete", "needs_review"}:
            logger.info("Submit skipped for %s because status=%s", job_id, job.status)
            return job
        from app.services.scene002_contract_only import is_contract_only as _submit_is_contract_only
        # Creator-selected capability gate first: a concrete model that cannot
        # satisfy the persisted shot requirements fails closed here with the
        # specific capability conflict (before the generic provider-identity
        # block below), catching post-creation payload mutation.
        if not _submit_is_contract_only(job):
            _submit_params = job.input_payload.parameters if job.input_payload and isinstance(job.input_payload.parameters, dict) else {}
            _submit_refs = list(job.input_payload.referenceAssets or []) if job.input_payload else []
            try:
                _validate_model_override(job.provider, _submit_params)
                _validate_user_model_capabilities(job.provider, _submit_params, _submit_refs)
            except ValueError as _model_capability_exc:
                job.status = "failed"
                job.error_message = str(_model_capability_exc)
                job.metadata = dict(job.metadata or {})
                job.metadata["model_capability_failure"] = {
                    "reason": "creator_model_capability_unsupported",
                    "message": str(_model_capability_exc),
                }
                _record_failure_location(
                    job,
                    phase="model_validation",
                    reason=str(_model_capability_exc),
                    error_type="creator_model_capability_unsupported",
                    category="permanent",
                )
                _persist_job(job)
                raise
        if job.provider in {"runway", "runway_direct"} and not _submit_is_contract_only(job):
            # Historical direct-provider jobs remain available to safe status,
            # output, and cancellation reads, but neither provider identity may
            # reach an adapter. Rebuild only from the canonical frozen-contract
            # Runway Router path.
            blocked_provider = job.provider
            job.status = "failed"
            job.error_message = (
                f"Direct Runway provider '{blocked_provider}' is disabled for "
                "production submission; rebuild through the Runway Model "
                "Router with a frozen contract."
            )
            job.metadata = dict(job.metadata or {})
            job.metadata["provider_boundary_failure"] = {
                "reason": "direct_runway_submission_disabled",
                "blocked_provider": blocked_provider,
                "required_provider": "runway_router",
            }
            _record_failure_location(
                job,
                phase="provider_resolution",
                reason=f"Direct Runway provider '{blocked_provider}' submission is disabled; use the frozen Model Router path.",
                error_type="direct_runway_submission_disabled",
                category="permanent",
            )
            _persist_job(job)
            return job
        if job.status == "failed":
            metadata = job.metadata if isinstance(job.metadata, dict) else {}
            reliability = metadata.get("pipeline_reliability") if isinstance(metadata.get("pipeline_reliability"), dict) else {}
            failure = reliability.get("failure_location") if isinstance(reliability.get("failure_location"), dict) else {}
            if failure.get("category") == "permanent" and not _submit_is_contract_only(job):

                logger.info(
                    "Submit skipped for permanent failed job %s phase=%s error_type=%s",
                    job_id,
                    failure.get("phase") or "",
                    failure.get("error_type") or "",
                )
                return job
        if job.status == "failed" and job.retry_count >= MAX_RETRIES and not _submit_is_contract_only(job):
            _record_failure_location(
                job,
                phase="retry",
                reason=f"Job {job_id} exceeded max retries",
                error_type="retry_limit_reached",
                category="permanent",
            )
            _set_zero_touch_phase(job, "retry", "failed", error="retry limit reached", error_type="retry_limit_reached")
            _persist_job(job)
            raise ValueError(f"Job {job_id} exceeded max retries")
        if (
            job.provider == "runway_router"
            and not _submit_is_contract_only(job)
            and str(job.provider_job_id or "").strip()
            and job.status in {"failed", "pending"}
        ):
            # R4.3E: a router job carrying an upstream task id may already
            # exist upstream (retry and re-dispatch both land here with a task
            # id; initial submits never do). Reconcile before any
            # resubmission; an unresolved ambiguity returns the job
            # un-submitted (worker-safe: no raise, no new task).
            _decision, job = await self._router_resubmit_decision(job)
            self._jobs[job_id] = job
            if _decision == "adopted":
                return job
            if _decision == "blocked":
                job.status = "failed"
                _detail = ((job.metadata or {}).get("router_reconciliation") or {}).get("detail")
                job.error_message = f"Router resubmission blocked: {_detail or 'unresolved upstream task'}"
                job.updated_at = _now_iso()
                self._jobs[job_id] = job
                _persist_job(job)
                return job
        if (
            job.provider == "runway_router"
            and not str(job.provider_job_id or "").strip()
            and not _submit_is_contract_only(job)
            and (
                job.status == "failed"
                # Retry resets failed → pending before submitting; a pending
                # job carrying ambiguity evidence is a resubmission, never an
                # initial submit (initial submits carry no evidence).
                or (job.status == "pending" and self._router_submission_attempted(job))
            )
        ):
            # R4.3E: no task id, but the recorded failure may still follow a
            # sent POST (e.g. connection loss before the response). Block only
            # on positive ambiguity evidence; pre-send failures proceed.
            _decision, job = await self._router_resubmit_decision(job)
            self._jobs[job_id] = job
            if _decision == "blocked":
                job.status = "failed"
                _detail = ((job.metadata or {}).get("router_reconciliation") or {}).get("detail")
                job.error_message = f"Router resubmission blocked: {_detail or 'unresolved submission'}"
                job.updated_at = _now_iso()
                self._jobs[job_id] = job
                _persist_job(job)
                return job
        self._submit_locks.add(job_id)
        adapter: RenderProviderAdapter | None = None
        submission_started = time.perf_counter()

        try:
            config = self._provider_configs.get(job.provider)
            if not config:
                raise ProviderError(
                    f"Provider configuration unavailable for {job.provider!r}",
                    stage="provider_resolution",
                    metadata={"provider": job.provider},
                )
            if not config.enabled:
                raise ProviderError(
                    f"Provider '{job.provider}' is disabled and cannot execute generation requests.",
                    stage="provider_authorization",
                    metadata={"provider": job.provider, "enabled": False},
                )
            if not isinstance(job.metadata, dict):
                job.metadata = {}

            from app.services.scene002_contract_only import is_contract_only, verify_job_contract, verify_submission_boundary
            if is_contract_only(job):
                try:
                    if _storage is None:
                        raise ValueError("Durable protected execution storage is unavailable")
                    from app.services.providers.runway_router_provider import get_router_config_id
                    from app.services.project_persistence_service import project_persistence_service
                    current_project = project_persistence_service.load_readonly_existing(job.project_id)
                    payload = verify_submission_boundary(
                        job, storage=_storage, project=current_project,
                        router_config_id=get_router_config_id(),
                        backend_root=Path(__file__).resolve().parents[2],
                    )
                    persisted_job = _storage.get_job(job_id)
                    if persisted_job is None or persisted_job.metadata != job.metadata or persisted_job.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json"):
                        raise ValueError("Durable protected job proof changed before provider submission")
                    job = persisted_job
                    verify_job_contract(job, project=current_project, router_config_id=get_router_config_id())
                except Exception as exc:
                    job.status = "failed"
                    job.error_message = f"Scene 002 contract-only verification failed: {exc}"
                    job.updated_at = datetime.now().isoformat()
                    self._jobs[job_id] = job
                    _persist_job(job)
                    return job
            if job.provider == "runway_router" and not is_contract_only(job):
                # SQLite is the submission authority for Router jobs. Never allow a
                # cache-only job to reach the adapter with mutable input as a substitute.
                try:
                    persisted_job = _storage.get_job(job_id) if _storage is not None else None
                except Exception as exc:
                    persisted_job = None
                    logger.warning("Unable to reload persisted Router contract for %s: %s", job_id, exc)
                if persisted_job is None or persisted_job.provider != "runway_router":
                    job.status = "failed"
                    job.error_message = "Runway Router submission requires a reloadable persisted frozen contract"
                    job.metadata = dict(job.metadata or {})
                    job.metadata["router_execution"] = {"reason": "frozen_generation_contract_unavailable"}
                    self._jobs[job_id] = job
                    _persist_job(job)
                    return job
                if is_contract_only(job):
                    from app.services.scene002_contract_only import verify_job_contract
                    try:
                        verify_job_contract(persisted_job)
                    except Exception as exc:
                        raise ValueError(f"Persisted protected job proof is invalid: {exc}") from exc
                job = persisted_job
                self._jobs[job_id] = job

            if job.provider == "runway_router":
                router_metadata = job.metadata if isinstance(job.metadata, dict) else {}
                router_contract_record = router_metadata.get("creative_generation_contract")
                router_manifest = router_metadata.get("creative_generation_manifest")
                router_identity = router_metadata.get("creative_generation_identity")
                if (
                    not isinstance(router_contract_record, dict)
                    or not isinstance(router_manifest, dict)
                    or not isinstance(router_identity, dict)
                    or not router_metadata.get("creative_manifest_fingerprint")
                    or not router_metadata.get("creative_contract_digest")
                ):
                    job.status = "failed"
                    job.error_message = "Runway Router submission requires complete persisted frozen contract metadata"
                    job.metadata = dict(router_metadata)
                    job.metadata["router_execution"] = {"reason": "frozen_generation_contract_unavailable"}
                    self._jobs[job_id] = job
                    _persist_job(job)
                    return job
            params = job.input_payload.parameters if job.input_payload and isinstance(job.input_payload.parameters, dict) else {}
            _validate_model_override(job.provider, params)
            # Re-validate creator-selected capabilities against the persisted
            # payload so a mutation between creation and submission fails
            # closed here (the submit handler marks the job failed and raises).
            _validate_user_model_capabilities(
                job.provider, params, list(job.input_payload.referenceAssets or []) if job.input_payload else []
            )
            # ── Recovery lineage gate (added after the 2026-09-27 incident) ──
            # A database that was replaced/restored onto the live path after the
            # app registered its identity must not silently feed renders.
            # Fail closed with a permanent, non-retryable classification so the
            # retry loop never hammers the provider from a wrong lineage.
            try:
                if not is_contract_only(job):
                    from app.services.recovery_lineage_guard import verify_render_lineage

                    if _storage is not None and getattr(_storage, "db_path", None):
                        _lineage_report = verify_render_lineage(Path(_storage.db_path))
                        if not _lineage_report.get("ok"):
                            _lineage_reason = str(_lineage_report.get("reason", "lineage verification failed"))
                            job.status = "failed"
                            job.error_message = f"Render lineage verification failed: {_lineage_reason}"
                            job.metadata = dict(job.metadata or {})
                            job.metadata["render_lineage_failure"] = {
                                "error_type": "database_lineage_changed",
                                "category": "permanent",
                                "reason": _lineage_reason,
                                "message": "Refusing to render against a database whose file identity changed since registration. Resolve the lineage manually, restart to re-register, then retry.",
                            }
                            _set_zero_touch_phase(job, "render", "skipped", reason="database lineage verification failed")
                            _record_failure_location(
                                job,
                                phase="lineage_verification",
                                reason=_lineage_reason,
                                error_type="database_lineage_changed",
                                category="permanent",
                            )
                            _persist_job(job)
                            return job
            except Exception as _lineage_exc:  # noqa: BLE001 — a broken guard must also fail closed
                job.status = "failed"
                job.error_message = f"Render lineage guard error: {_lineage_exc}"
                _persist_job(job)
                return job
            # ── end recovery lineage gate ──
            if not is_contract_only(job) and job.metadata.get("frozen_reference_binding") is None:
                _apply_visual_model_reference(job)
            _validation_storage = _storage
            if _validation_storage is None:
                from app.data.storage import get_storage as _get_validation_storage

                _validation_storage = _get_validation_storage("sqlite")
            # A first character shot may intentionally bootstrap the canonical
            # lock after a successful render. Once a reference set is supplied,
            # or the caller explicitly requires identity anchors, validation is
            # strict and fail-closed before the provider boundary.
            _requires_canonical_references = bool(
                job.input_payload
                and (
                    job.input_payload.consistency_payload is not None
                    or bool(job.input_payload.referenceAssets)
                    or params.get("require_canonical_references") is True
                )
            )
            if job.metadata.get("frozen_reference_binding") is not None:
                from app.services.reference_validation import verify_frozen_reference_payload

                verify_frozen_reference_payload(
                    job=job,
                    binding=job.metadata.get("frozen_reference_binding"),
                )
            _prepared_record = (
                job.metadata.get("creative_generation_contract")
                or job.metadata.get("prepared_generation_contract")
            ) if isinstance(job.metadata, dict) else None
            if _prepared_record is not None and not is_contract_only(job):
                from app.services.generation_contract import FrozenGenerationContract
                from app.services.shot_manifest import recompute_manifest_fingerprint

                _prepared_contract = FrozenGenerationContract.from_record(_prepared_record)
                _prepared_payload = _prepared_contract.payload()
                _prepared_binding = (job.metadata or {}).get("frozen_reference_binding")
                _prepared_manifest = (
                    (job.metadata or {}).get("creative_generation_manifest")
                    or (job.metadata or {}).get("prepared_creative_manifest")
                )
                _prepared_fingerprint = str(_prepared_payload.get("manifest_fingerprint") or "")
                _prepared_manifest_row = [
                    row for row in ((_prepared_manifest or {}).get("shots") or [])
                    if isinstance(row, dict) and row.get("shot_id") == job.shot_id
                ] if isinstance(_prepared_manifest, dict) else []
                _expected_prepared_uris = [str(row.get("uri") or "") for row in _prepared_payload.get("references") or []]
                if (
                    not isinstance(_prepared_binding, list)
                    or not isinstance(_prepared_manifest, dict)
                    or _prepared_contract.shot_id != job.shot_id
                    or (_prepared_manifest.get("scene") or {}).get("scene_id") != derive_scene_id_from_shot_id(job.shot_id)
                    or _prepared_contract.prompt != (job.input_payload.prompt or "")
                    or _prepared_contract.negative_prompt != (job.input_payload.negative_prompt or "")
                    or list(job.input_payload.referenceAssets or []) != _expected_prepared_uris
                    or not _prepared_fingerprint
                    or _prepared_manifest.get("manifest_fingerprint") != _prepared_fingerprint
                    or recompute_manifest_fingerprint(_prepared_manifest) != _prepared_fingerprint
                    or len(_prepared_manifest_row) != 1
                    or _prepared_manifest_row[0].get("reference_binding") != _prepared_binding
                    or _prepared_manifest_row[0].get("references") != _expected_prepared_uris
                    or _prepared_manifest_row[0].get("generation_contract_digest") != _prepared_contract.creative_digest()
                ):
                    raise ValueError("Prepared generation contract or provider payload changed after preflight")
                _expected_semantics = [
                    (ref["ref_id"], ref["uri"], ref["target_type"], ref["target_id"], ref["studio_role"], ref["category"], ref["canonical"], ref["approval_state"], ref["source_kind"], ref["kind"])
                    for ref in _prepared_payload.get("references") or []
                    if isinstance(ref, dict) and ref.get("source") == "canonical_reference_binding"
                ]
                _binding_semantics = [
                    (row.get("ref_id"), row.get("uri"), row.get("target_type"), row.get("target_id"), row.get("role"), row.get("category"), row.get("canonical"), row.get("approval_state"), row.get("source_kind"), row.get("kind"))
                    for row in _prepared_binding
                ]
                if _binding_semantics != _expected_semantics:
                    raise ValueError("Prepared reference binding no longer matches the frozen generation contract")
            # Local file existence fails closed FIRST (provider-independent,
            # returns a failed job with 200): a nonexistent reference path must
            # never reach the canonical reference-authority gate below, which
            # raises ValidationError (HTTP 409) for unresolvable projects.
            # This preserves the LTX i2v fail-closed contract: invalid image
            # payloads fail without T2V fallback and without a provider_job_id.
            _missing_reference_assets = _missing_local_reference_assets(
                list(job.input_payload.referenceAssets or []) if job.input_payload else []
            )
            if _missing_reference_assets and not is_contract_only(job):
                job.status = "failed"
                job.error_message = "Reference file missing before provider submission"
                job.metadata = dict(job.metadata or {})
                job.metadata["reference_asset_failure"] = {
                    "error_type": "reference_file_missing",
                    "missing_references": _missing_reference_assets,
                    "message": job.error_message,
                }
                _set_zero_touch_phase(
                    job,
                    "resolve_references",
                    "failed",
                    error=job.error_message,
                    error_type="reference_file_missing",
                    missing_references=_missing_reference_assets,
                )
                _set_zero_touch_phase(job, "render", "skipped", reason="reference file missing before provider submission")
                _set_zero_touch_phase(job, "evaluate", "skipped", reason="render not submitted")
                _set_zero_touch_phase(job, "retry", "skipped", reason="render not submitted")
                _record_failure_location(
                    job,
                    phase="resolve_references",
                    reason=job.error_message,
                    error_type="reference_file_missing",
                    category="permanent",
                )
                _persist_job(job)
                return job
            if not is_contract_only(job):
                validate_generation_payload(
                    job=job,
                    storage=_validation_storage,
                    require_setting_reference=True,
                    require_canonical_references=_requires_canonical_references,
                )
            if is_contract_only(job):
                from app.services.providers.runway_router_provider import get_router_config_id
                from app.services.project_persistence_service import project_persistence_service
                from app.services.scene002_contract_only import verify_submission_boundary
                verify_submission_boundary(
                    job,
                    storage=_storage,
                    project=project_persistence_service.load_readonly_existing(job.project_id),
                    router_config_id=get_router_config_id(),
                    backend_root=Path(__file__).resolve().parents[2],
                )
            if not is_contract_only(job):
                _set_zero_touch_phase(
                    job,
                    "render",
                    "running",
                    provider=job.provider,
                    model=_provider_model_for_job(job.provider, params),
                )
            _persist_job(job)
            adapter = get_adapter(job.provider, config)
            previous_status = job.status
            logger.info(f"Submitting job {job_id} to provider {job.provider}")

            # ── Seed locking: generate on first render, reuse on subsequent ──
            try:
                if not is_contract_only(job) and _storage and (job.input_payload.parameters or {}).get("seed") is None:
                    shot_seed = _storage.get_shot_seed(job.project_id, job.shot_id)
                    if shot_seed and shot_seed.get("seed") is not None:
                        seed_val = int(shot_seed["seed"])
                        logger.info(
                            "SEED_REUSED | job=%s | shot=%s | seed=%d | locked=%s",
                            job_id, job.shot_id, seed_val,
                            bool(shot_seed.get("seed_locked")),
                        )
                    else:
                        seed_val = int.from_bytes(os.urandom(4), byteorder="big", signed=False) % (2**31)
                        _storage.save_shot_seed(job.project_id, job.shot_id, seed_val)
                        logger.info(
                            "SEED_GENERATED | job=%s | shot=%s | seed=%d",
                            job_id, job.shot_id, seed_val,
                        )
                    if job.input_payload and job.input_payload.parameters:
                        job.input_payload.parameters["seed"] = seed_val
                    elif job.input_payload:
                        job.input_payload.parameters = {"seed": seed_val}
            except Exception as _exc:
                logger.debug("Seed injection skipped for %s: %s", job_id, _exc)
            
            job.recovery_status = "active"
            execution_provider = job.provider
            assert_queue_execution_lease_current()
            if job.provider == "runway_router" and not is_contract_only(job):
                submitted_job = await asyncio.wait_for(
                    adapter.submit_job(job, reference_storage=_validation_storage),
                    timeout=PROVIDER_CALL_TIMEOUT_SECONDS,
                )
            else:
                submitted_job = await asyncio.wait_for(
                    adapter.submit_job(job),
                    timeout=PROVIDER_CALL_TIMEOUT_SECONDS,
                )
            assert_queue_execution_lease_current()

            # An adapter may update job state, but it may not rewrite the
            # provider identity of the generation intent currently executing.
            if submitted_job.provider != execution_provider:
                job.provider = execution_provider
                raise ProviderError(
                    f"Provider identity changed during execution of generation job {job_id}; "
                    f"expected '{execution_provider}'.",
                    stage="provider_identity",
                    metadata={
                        "provider": execution_provider,
                        "returned_provider": submitted_job.provider,
                    },
                )
            
            submitted_job.recovery_status = "active"
            submitted_job.updated_at = datetime.now().isoformat()
            
            self._jobs[job_id] = submitted_job
            if not is_contract_only(submitted_job):
                _set_zero_touch_phase(
                    submitted_job,
                    "render",
                    "complete" if submitted_job.status == "complete" else submitted_job.status,
                    provider_job_id=submitted_job.provider_job_id or "",
                )
            if submitted_job.status == "failed" and not is_contract_only(submitted_job):
                _record_provider_failure_policy(submitted_job)
            _persist_job(submitted_job)
            _log_audit("submit_job", "render_job", job_id, details=f"provider={submitted_job.provider}")

            if submitted_job.status == "complete" and previous_status != "complete" and not is_contract_only(submitted_job):
                await _run_continuity_review(submitted_job)
                await _run_render_quality_check(submitted_job)
                await _run_character_reference_lock(submitted_job)
            
            await _notify_update(job_id, submitted_job.model_dump())
            return submitted_job
            
        except Exception as e:
            if isinstance(e, QueueExecutionLeaseLost):
                if _current_queue_execution_fence() is not None and _storage is not None:
                    try:
                        durable_job = _storage.get_job(job_id)
                    except Exception:
                        logger.exception("Unable to restore render cache after queue lease loss job_id=%s", job_id)
                    else:
                        if durable_job is None:
                            self._jobs.pop(job_id, None)
                        else:
                            self._jobs[job_id] = durable_job
                raise
            if _current_queue_execution_fence() is not None and not queue_execution_lease_is_current():
                raise QueueExecutionLeaseLost("Production queue lease was lost during provider execution") from e
            error_message = (
                f"Provider call timed out after {PROVIDER_CALL_TIMEOUT_SECONDS}s"
                if isinstance(e, TimeoutError)
                else str(e)
            )
            if isinstance(e, ProviderError):
                error_message = e.message
            log_stage_event(
                project_id=job.project_id, job_id=job.id, provider=job.provider,
                stage="provider_resolution" if isinstance(e, ProviderError) else "provider_submission",
                duration_ms=int((time.perf_counter() - submission_started) * 1000),
                extra={"error_type": "provider_error"},
            )
            logger.error(f"Failed to submit job {job_id}: {error_message}")
            job.status = "failed"
            job.error_message = error_message
            job.updated_at = datetime.now().isoformat()
            if not _submit_is_contract_only(job):
                _set_zero_touch_phase(job, "render", "failed", error=error_message)
                _record_provider_failure_policy(job, error_message)
            else:
                job.metadata = dict(job.metadata or {})
                job.metadata["provider_failure"] = {"category": "unknown", "message": error_message, "retryable": False}
            self._jobs[job_id] = job
            _persist_job(job)
            raise
        finally:
            await _close_provider_adapter(adapter)
            self._submit_locks.discard(job_id)

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        """Get job status with storage fallback, caching, and recovery

        For non-terminal jobs, delegates to the provider adapter so simulated
        providers can progress through stages (pending → rendering → complete).
        """
        job = self._jobs.get(job_id)
        if not job and _storage:
            job = _storage.get_job(job_id)
            if job:
                self._jobs[job_id] = job

        if not job:
            raise ValueError(f"Job {job_id} not found")
        if _is_contract_only(job):
            if _storage is None:
                raise ValueError("Protected polling requires durable render-job storage")
            durable = _storage.get_job(job_id)
            if durable is None:
                raise ValueError("Protected job contract cannot be recovered from durable storage")
            from app.services.scene002_contract_only import verify_job_contract
            verify_job_contract(durable, require_project=False)
            if durable.metadata != job.metadata or durable.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json"):
                raise ValueError("Protected in-memory job differs from the durable execution record")
            job = durable
            self._jobs[job_id] = durable

        # Delegate to adapter for live status on non-terminal jobs
        if not job.is_terminal():
            try:
                from app.services.scene002_contract_only import is_contract_only, verify_submission_boundary
                if is_contract_only(job):
                        if _storage is None:
                            raise ValueError("Durable protected execution storage is unavailable")
                        from app.services.providers.runway_router_provider import get_router_config_id
                        from app.services.project_persistence_service import project_persistence_service
                        current_project = project_persistence_service.load_readonly_existing(job.project_id)
                        verify_submission_boundary(
                            job,
                            storage=_storage,
                            project=current_project,
                            router_config_id=get_router_config_id(),
                            backend_root=Path(__file__).resolve().parents[2],
                        )
                        durable = _storage.get_job(job.id)
                        if (
                            durable is None
                            or durable.metadata != job.metadata
                            or durable.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json")
                        ):
                            raise ValueError("Durable protected job changed before status polling")

                config = self._provider_configs.get(job.provider)
                if not config:
                    raise ProviderError(
                        f"Provider configuration unavailable for {job.provider!r}",
                        stage="provider_resolution",
                        metadata={"provider": job.provider},
                    )
                if config:
                    previous_status = job.status
                    adapter = get_adapter(job.provider, config)
                    try:
                        updated = await asyncio.wait_for(
                            adapter.get_job_status(job),
                            timeout=PROVIDER_CALL_TIMEOUT_SECONDS,
                        )
                    finally:
                        await _close_provider_adapter(adapter)
                    updated.last_polled_at = datetime.now().isoformat()

                    updated.updated_at = datetime.now().isoformat()
                    if is_contract_only(job) and updated.metadata != job.metadata:
                        raise ValueError("Provider status poll attempted to mutate protected job metadata")
                    if is_contract_only(job) and (
                        updated.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json")
                        or updated.project_id != job.project_id
                        or updated.shot_id != job.shot_id
                        or updated.provider != job.provider
                    ):
                        raise ValueError("Provider status poll attempted to mutate protected creative input")
                    if updated.status == "complete":
                        has_url = (
                            updated.output_payload
                            and isinstance(updated.output_payload.asset_url, str)
                            and updated.output_payload.asset_url.strip()
                        )
                        if not has_url:
                            logger.warning(
                                "JOB_COMPLETE_WITHOUT_URL | job=%s | project=%s | shot=%s | demoting to failed",
                                updated.id,
                                updated.project_id,
                                updated.shot_id,
                            )
                            updated.status = "failed"
                            updated.error_message = "Job completed without output URL"
                            if not is_contract_only(updated):
                                _set_zero_touch_phase(updated, "render", "failed", error=updated.error_message, error_type="missing_video_url")
                                _record_failure_location(
                                    updated,
                                    phase="render",
                                    reason=updated.error_message,
                                    error_type="missing_video_url",
                                    category="temporary",
                                )
                    
                    # Detect transition to complete status
                    transitioned_to_complete = (
                        previous_status != "complete" and updated.status == "complete"
                    )
                    
                    self._jobs[job_id] = updated
                    if updated.status == "failed" and not is_contract_only(updated):
                        _record_provider_failure_policy(updated)
                    _persist_job(updated)
                    
                    # Run completion hooks on status transition
                    if transitioned_to_complete and not is_contract_only(updated):
                        await _run_continuity_review(updated)
                        await _run_render_quality_check(updated)
                        await _run_character_reference_lock(updated)
                    
                    if updated.status != previous_status:
                        await _notify_update(job_id, updated.model_dump())
                    return updated
            except Exception as _exc:
                if is_contract_only(job):
                    job.status = "failed"
                    job.error_message = f"Scene 002 contract-only polling failed closed: {_exc}"
                    job.metadata = dict(job.metadata or {})
                    job.metadata["scene002_contract_failure"] = str(_exc)
                    job.last_polled_at = datetime.now().isoformat()
                    job.updated_at = job.last_polled_at
                    self._jobs[job_id] = job
                    _persist_job(job)
                    return job
                poll_error = (
                    f"Provider status poll timed out after {PROVIDER_CALL_TIMEOUT_SECONDS}s"
                    if isinstance(_exc, TimeoutError)
                    else (_exc.message if isinstance(_exc, ProviderError) else str(_exc))
                )
                job.status = "failed"
                job.error_message = f"Provider status poll failed: {poll_error}"
                job.last_polled_at = datetime.now().isoformat()
                job.updated_at = job.last_polled_at
                if not is_contract_only(job):
                    _set_zero_touch_phase(job, "render", "failed", error=poll_error, error_type="polling_failure")
                    _record_failure_location(
                        job,
                        phase="render",
                        reason=job.error_message,
                        error_type="polling_failure",
                        category="temporary",
                    )
                self._jobs[job_id] = job
                _persist_job(job)
                logger.info("ADAPTER_STATUS_POLL_FAILED | job=%s | provider=%s | error=%s", job_id, job.provider, _exc)
                return job

        # Safeguard: if a job reports "complete" but has no output URL, demote to "failed"
        # so the UI doesn't show false COMPLETE badges with no playable video.
        if job.status == "complete":
            has_url = (
                job.output_payload
                and isinstance(job.output_payload.asset_url, str)
                and job.output_payload.asset_url.strip()
            )
            if not has_url:
                logger.warning(
                    "JOB_COMPLETE_WITHOUT_URL | job=%s | project=%s | shot=%s | demoting to failed",
                    job.id, job.project_id, job.shot_id,
                )
                job.status = "failed"
                job.error_message = "Job completed without output URL"
                if not _is_contract_only(job):
                    _set_zero_touch_phase(job, "render", "failed", error=job.error_message, error_type="missing_video_url")
                    _record_failure_location(
                        job,
                        phase="render",
                        reason=job.error_message,
                        error_type="missing_video_url",
                        category="temporary",
                    )
                self._jobs[job_id] = job
                _persist_job(job)

        return job

    def delete_job(self, job_id: str) -> bool:
        """Delete a render job record from both memory and storage."""
        started = time.perf_counter()
        job = self.get_job(job_id)
        if job is None:
            return False
        if job.status in {"pending", "queued", "submitted", "rendering", "processing", "running", "retrying"}:
            raise StateError("Cancel this render before deleting it.", stage="render_delete")
        if _storage:
            try:
                _storage.delete_job(job_id)
            except Exception as exc:
                raise PersistenceError("The render could not be deleted. Please try again.", stage="render_delete") from exc
        self._jobs.pop(job_id, None)
        log_stage_event(project_id=job.project_id, job_id=job_id, provider=job.provider,
                        stage="render_delete", duration_ms=int((time.perf_counter() - started) * 1000))
        return True

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        job = self._jobs.get(job_id)
        if not job:
            return False

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        try:
            result = await adapter.cancel_job(job)
        finally:
            await _close_provider_adapter(adapter)
        
        if result:
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            self._jobs[job_id] = job
            _persist_job(job)
            await _notify_update(job_id, job.model_dump())
        
        return result

    async def retry_job(self, job_id: str) -> RenderJobModel:
        """Retry a failed job using the exact persisted request proof."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        from app.services.scene002_contract_only import is_contract_only, verify_job_contract
        if is_contract_only(job):
            verify_job_contract(job, require_project=False)
            if _storage is None:
                raise ValueError("Protected ordinary retry requires the durable original job")
            persisted = _storage.get_job(job_id)
            if persisted is None:
                raise ValueError("Protected ordinary retry contract cannot be recovered")
            from app.services.scene002_contract_only import assert_ordinary_retry_matches
            from app.services.providers.runway_router_provider import get_router_config_id
            from app.services.project_persistence_service import project_persistence_service
            current_project = project_persistence_service.load_readonly_existing(job.project_id)
            assert_ordinary_retry_matches(
                job, persisted, project=current_project, router_config_id=get_router_config_id()
            )
            job = persisted
        if is_contract_only(job):
            if job.status != "failed":
                raise ValueError("Protected ordinary retry is allowed only for failed jobs")
            # Job retries reuse the same durable row, contract and provider input.
            # Keep the transition narrow; recovery/status metadata is noncreative.
        job.retry_count += 1
        job.status = "pending"
        job.error_message = None
        job.recovery_status = "retrying"
        job.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = job
        _persist_job(job)

        submitted = await self.submit_job(job_id)
        if submitted.provider == "runway_router":
            # R4.3E: surface a blocked resubmission explicitly (route → 409)
            # instead of silently returning the un-submitted job. The gate
            # overwrites this evidence on every trigger, so it is always fresh
            # when read here.
            _evidence = (submitted.metadata or {}).get("router_reconciliation") or {}
            if _evidence.get("retry_permitted") is False and _evidence.get("verdict") in {
                "upstream_active",
                "reconcile_inconclusive",
                "reconcile_unavailable",
                "ambiguous_without_task_id",
                "upstream_success_without_output",
            }:
                raise ValueError(
                    f"Router retry blocked for job {job_id}: {submitted.error_message or _evidence.get('detail')}; "
                    "resolve the recorded upstream task before resubmitting."
                )
        return submitted

    async def retry_with_continuity_context(
        self,
        job_id: str,
        film_id: str,
        scene_id: str,
    ) -> dict:
        """
        Retry a failed render job with a graph-informed prompt adjustment.

        Keeps the original shot description unchanged, replaces the previous
        continuity context block with a fresh one (the graph may have been
        updated since the original render), and appends a retry note that
        highlights the dominant motif or emotional register.

        Caps retries at 3.  When the cap is reached, returns the failed job
        unchanged with retry_advisory set.

        Args:
            job_id:   The ID of the failed job to retry.
            film_id:  The film/project identifier (used for graph lookup).
            scene_id: The scene identifier (used for context lookup).

        Returns:
            dict with the new job (or the original job when cap is reached),
            plus an "advisory" key.
        """
        MAX_RETRIES = 3

        # ── Load the failed job ───────────────────────────────────────────────
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        from app.services.scene002_contract_only import reject_altered_retry
        reject_altered_retry(job)

        current_retry_count = job.retry_count or 0

        # ── Enforce cap ───────────────────────────────────────────────────────
        if current_retry_count >= MAX_RETRIES:
            advisory = "Maximum retries reached. Manual review recommended."
            job.retry_advisory = advisory
            self._jobs[job_id] = job
            _persist_job(job)
            return {
                "job": job.model_dump(),
                "advisory": advisory,
                "capped": True,
            }

        # ── Load fresh continuity context ─────────────────────────────────────
        fresh_context: dict = {}
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            fresh_context = _cont_svc.build_prompt_context(
                scene_id=scene_id,
                film_id=film_id,
            )
        except Exception as _exc:
            logger.debug("Continuity context unavailable for retry %s: %s", job_id, _exc)

        # ── Strip old context blocks from the original prompt ─────────────────
        original_prompt = ""
        if job.input_payload and job.input_payload.prompt:
            original_prompt = job.input_payload.prompt

        # Remove any existing [CINEMATIC CONTEXT] and [SHOT POSITION] blocks
        # so we can replace them with fresh ones.
        clean_prompt = original_prompt
        for marker in ("[CINEMATIC CONTEXT]", "[SHOT POSITION]", "[RETRY CONTEXT]"):
            if marker in clean_prompt:
                clean_prompt = clean_prompt[: clean_prompt.index(marker)].rstrip()

        # ── Build fresh context block ─────────────────────────────────────────
        _motifs = fresh_context.get("active_motifs") or []
        _anchors = fresh_context.get("continuity_anchors") or []
        _has_ctx = bool(
            fresh_context.get("emotional_register")
            or _motifs
            or fresh_context.get("tonal_direction")
            or _anchors
        )
        fresh_block = ""
        if _has_ctx:
            fresh_block = _CONTINUITY_CONTEXT_BLOCK.format(
                emotional_register=fresh_context.get("emotional_register") or "unspecified",
                active_motifs=", ".join(_motifs) if _motifs else "none",
                tonal_direction=fresh_context.get("tonal_direction") or "unspecified",
                continuity_anchors=", ".join(_anchors) if _anchors else "none",
            )

        # ── Build retry note ──────────────────────────────────────────────────
        # Use dominant_motif from motif analysis if available, else emotional_register.
        priority_signal = ""
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc2,
            )
            motif_analysis = _cont_svc2.get_motif_thread_analysis(film_id)
            priority_signal = motif_analysis.get("dominant_motif") or ""
        except Exception:
            pass
        if not priority_signal:
            priority_signal = fresh_context.get("emotional_register") or "established visual language"

        retry_note = (
            f"\n\n[RETRY CONTEXT]"
            f"\nPrevious attempt failed. "
            f"Prioritize: {priority_signal}. "
            f"Keep composition consistent with established visual language."
        )

        new_prompt = clean_prompt + fresh_block + retry_note

        # ── R4.3E: continuity retries create a new upstream task, so an
        # ambiguous source submission must be reconciled first. ───────────────
        from app.services.scene002_contract_only import is_contract_only as _continuity_is_contract_only
        if (
            job.provider == "runway_router"
            and str(job.provider_job_id or "").strip()
            and not _continuity_is_contract_only(job)
        ):
            _continuity_decision, _continuity_job = await self._router_resubmit_decision(job)
            self._jobs[job_id] = _continuity_job
            job = _continuity_job
            if _continuity_decision == "adopted":
                return {
                    "job": job.model_dump(),
                    "advisory": "Upstream task output was adopted on reconciliation; no continuity retry was created.",
                    "capped": False,
                }
            if _continuity_decision == "blocked":
                _continuity_detail = ((job.metadata or {}).get("router_reconciliation") or {}).get("detail")
                return {
                    "job": job.model_dump(),
                    "advisory": (
                        "Continuity retry refused: "
                        f"{_continuity_detail or 'unresolved upstream task'} "
                        "Resolve the recorded upstream task before retrying."
                    ),
                    "capped": False,
                }

        # ── Create new job ────────────────────────────────────────────────────
        new_job = self.create_job(
            project_id=film_id,
            shot_id=job.shot_id,
            provider=job.provider,
            prompt=new_prompt,
            reference_assets=list(job.input_payload.referenceAssets or []),
            parameters=dict(job.input_payload.parameters or {}),
        )
        new_job.retry_of = job_id
        new_job.retry_count = current_retry_count + 1
        new_job.batch_id = job.batch_id  # preserve batch membership
        self._jobs[new_job.id] = new_job
        _persist_job(new_job)

        # Submit the new job.
        try:
            submitted = await self.submit_job(new_job.id)
        except Exception as _exc:
            logger.warning("Retry job %s submit failed: %s", new_job.id, _exc)
            submitted = new_job

        advisory = (
            f"Retry {current_retry_count + 1} of {MAX_RETRIES} submitted "
            f"with fresh continuity context."
        )
        return {
            "job": submitted.model_dump(),
            "advisory": advisory,
            "capped": False,
        }

    def _get_jobs_by_status(self, statuses: list[str]) -> list[RenderJobModel]:
        """Get all jobs matching any of the given statuses"""
        return [job for job in self._jobs.values() if job.status in statuses]

    def get_job(self, job_id: str) -> Optional[RenderJobModel]:
        """Get a job by ID; Router contract-bearing jobs are reloaded from storage."""
        job = self._jobs.get(job_id)
        if job and job.provider != "runway_router":
            return job
        if _storage:
            persisted_job = _storage.get_job(job_id)
            if persisted_job:
                self._jobs[job_id] = persisted_job
                return persisted_job
        if job and job.provider == "runway_router":
            return None
        return job

    def list_persisted_jobs(self, project_id: Optional[str] = None) -> list[RenderJobModel]:
        """Read the complete persisted job history without cache fallbacks.

        Cost enforcement uses this strict path so storage failures cannot be
        hidden by an in-memory subset of render jobs.
        """
        storage = _storage
        page_reader = getattr(storage, "list_jobs_page", None) if storage is not None else None
        if not callable(page_reader):
            raise RuntimeError("Persisted render-job history reader is unavailable")

        jobs: list[RenderJobModel] = []
        cursor = None
        seen_cursors: set[str] = set()
        while True:
            page = page_reader(project_id=project_id, cursor=cursor, limit=200)
            if (
                not isinstance(page, dict)
                or not isinstance(page.get("items"), list)
                or not isinstance(page.get("has_more"), bool)
            ):
                raise RuntimeError("Persisted render-job history page is incomplete")
            items = page["items"]
            if any(not isinstance(job, RenderJobModel) for job in items):
                raise RuntimeError("Persisted render-job history contains an invalid row")
            jobs.extend(items)
            if page["has_more"] is False:
                return jobs
            next_cursor = page.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                raise RuntimeError("Persisted render-job history pagination is incomplete")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def list_jobs(self, project_id: Optional[str] = None) -> list[RenderJobModel]:
        """List all jobs, optionally filtered by project.
        
        In-memory jobs take priority over persisted ones — this ensures
        the output_payload from a just-completed job (e.g. simulated provider)
        is not overwritten by a stale DB record that hasn't been updated yet.
        """
        jobs_by_id: dict[str, RenderJobModel] = {}

        # Always load persisted jobs first as the baseline.
        if _storage:
            try:
                persisted = _storage.list_jobs(project_id=project_id, limit=5000)
                for job in persisted:
                    jobs_by_id[job.id] = job
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load persisted jobs for list_jobs: %s", exc)

        # Then overlay in-memory jobs — these have the freshest state.
        for job in self._jobs.values():
            jobs_by_id[job.id] = job

        jobs = list(jobs_by_id.values())
        if project_id:
            jobs = [j for j in jobs if j.project_id == project_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def get_job_outputs(self, job_id: str) -> list[RenderAsset]:
        """Get outputs for a completed job, preserving provider provenance."""
        job = self.get_job(job_id)
        if not job:
            return []

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        try:
            assets = await adapter.fetch_outputs(job)
        finally:
            await _close_provider_adapter(adapter)

        if job.provider != "runway_router" or not assets:
            return assets

        from app.services.video_asset_service import VideoAssetService

        if _storage is None or not job.provider_job_id or not job.output_payload:
            return []
        output_url = str(job.output_payload.asset_url or "").strip()
        if not output_url:
            return []
        service = VideoAssetService(_storage)
        existing = service.find_generated_output_for_render_job(
            project_id=job.project_id,
            render_job_id=job.id,
            provider_task_id=job.provider_job_id,
            source_url=output_url,
        )
        if existing is None:
            try:
                registered = service.register_generated_output(
                    project_id=job.project_id,
                    source_url=output_url,
                    title=f"Runway Router render {job.shot_id}",
                    description="Generated output registered from its matching Runway Router task",
                    metadata={
                        "render_job_id": job.id,
                        "provider_task_id": job.provider_job_id,
                        "provider": job.provider,
                        "shot_id": job.shot_id,
                        "association_source": "runway_router_polled_task",
                    },
                )
            except (ValueError, OSError):
                logger.exception(
                    "RUNWAY_OUTPUT_REGISTRATION_FAILED project_id=%s job_id=%s provider=%s stage=asset_registration duration_ms=0",
                    job.project_id,
                    job.id,
                    job.provider,
                )
                return []
            existing = service.find_generated_output_for_render_job(
                project_id=job.project_id,
                render_job_id=job.id,
                provider_task_id=job.provider_job_id,
                source_url=output_url,
            )
            if existing is None or existing.asset_id != registered.asset_id:
                return []
        assets[0].metadata = {
            **(assets[0].metadata if isinstance(assets[0].metadata, dict) else {}),
            "video_asset_id": existing.asset_id,
            "runway_output_identity": {
                "render_job_id": job.id,
                "provider_task_id": job.provider_job_id,
                "source_url": output_url,
            },
        }
        return assets

    async def reconcile_completed_runway_task(self, job_id: str) -> RenderJobModel:
        """Reconcile a runway job against upstream Runway task status.

        Works for any job status (pending, rendering, complete, failed):
        - If task succeeded: attach output_url and mark complete
        - If task still running/pending: preserve running state with clear status
        - If task failed: preserve structured failure
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.provider != "runway":
            return job

        if _is_contract_only(job):
            raise ValueError("Protected Scene 002 jobs do not use direct Runway task reconciliation")

        task_id = job.provider_job_id
        if not task_id and job.output_payload and isinstance(job.output_payload.metadata, dict):
            normalized = job.output_payload.metadata.get("provider_response_normalized") or {}
            metadata = normalized.get("metadata") if isinstance(normalized, dict) else {}
            if isinstance(metadata, dict):
                task_id = metadata.get("task_id")

        if not isinstance(task_id, str) or not task_id.strip():
            return job

        job.provider_job_id = task_id.strip()
        config = self._provider_configs.get("runway")
        if not config:
            return job

        adapter = get_adapter("runway", config)
        try:
            updated = await adapter.get_job_status(job)
        finally:
            await _close_provider_adapter(adapter)
        updated.last_polled_at = datetime.now().isoformat()
        updated.updated_at = updated.last_polled_at

        if updated.status == "complete":
            # Safeguard: verify the completed job has an output URL before persisting
            has_url = (
                updated.output_payload
                and isinstance(updated.output_payload.asset_url, str)
                and updated.output_payload.asset_url.strip()
            )
            if not has_url:
                logger.warning(
                    "RECONCILE_COMPLETE_WITHOUT_URL | job=%s | project=%s | shot=%s | demoting to failed",
                    job_id, job.project_id, job.shot_id,
                )
                updated.status = "failed"
                updated.error_message = "Reconciled job completed without output URL"
                updated.recovery_status = "recovery_failed"
                self._jobs[job_id] = updated
                _persist_job(updated)
                return updated

            normalized = (
                ((updated.output_payload or RenderJobOutput(asset_url="", thumbnail_url="", metadata={})).metadata or {})
                .get("provider_response_normalized", {})
            )
            if isinstance(normalized, dict):
                output = normalized.get("output") if isinstance(normalized.get("output"), dict) else {}
                metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
                output["status"] = "completed"
                normalized["output"] = output
                metadata["provider_status"] = "completed"
                normalized["metadata"] = metadata
                if updated.output_payload:
                    updated.output_payload.metadata["provider_response_normalized"] = normalized
            updated.recovery_status = "orphan_reconciled"
            if not updated.completed_at:
                updated.completed_at = updated.last_polled_at

            if not _is_contract_only(updated):
                await _run_continuity_review(updated)
                await _run_render_quality_check(updated)
                await _run_character_reference_lock(updated)
            self._jobs[job_id] = updated
            _persist_job(updated)
            await _notify_update(job_id, updated.model_dump())
            return updated

        if updated.status == "failed":
            updated.recovery_status = "recovery_failed"
        elif updated.is_terminal():
            updated.recovery_status = "recovered_terminal"
        else:
            updated.recovery_status = "active"
        self._jobs[job_id] = updated
        _persist_job(updated)
        await _notify_update(job_id, updated.model_dump())
        return updated

    # ── R4.3E: router submission reconciliation ─────────────────────────
    # An ambiguous router submission (a recorded upstream task id with no
    # confirmed outcome) must never trigger an automatic resubmission that
    # could create a duplicate upstream task. Reconcile first with a single
    # bounded provider read, then adopt, preserve, or fail closed.

    def _record_router_reconciliation(
        self,
        job: RenderJobModel,
        *,
        task_id: str,
        upstream_status: str | None,
        verdict: str,
        retry_permitted: bool,
        detail: str,
    ) -> RenderJobModel:
        """Persist reconcile evidence on the job without changing its outcome."""
        job.metadata = dict(job.metadata or {})
        job.metadata["router_reconciliation"] = {
            "task_id": task_id,
            "upstream_status": upstream_status,
            "verdict": verdict,
            "retry_permitted": bool(retry_permitted),
            "detail": detail,
            "checked_at": _now_iso(),
        }
        job.updated_at = _now_iso()
        self._jobs[job.id] = job
        _persist_job(job)
        return job

    async def reconcile_runway_router_task(self, job_id: str) -> RenderJobModel:
        """Reconcile one router job against its recorded upstream task.

        Exactly one bounded ``GET /v1/tasks/{id}`` is issued; this method never
        submits, polls, sleeps, or retries. Verdicts recorded in
        ``metadata["router_reconciliation"]``:

        - ``adopted_completed_task`` — upstream succeeded with an output URL;
          the outcome is adopted through the existing integrity reviews.
        - ``upstream_active`` — task still running; state preserved.
        - ``upstream_terminal_failure`` — task terminally failed; a later
          retry may submit a replacement task (the recorded one is dead).
        - ``reconcile_inconclusive`` / ``reconcile_unavailable`` /
          ``upstream_success_without_output`` — unresolved; retry is blocked
          until explicit resolution.
        - ``skipped_no_task_id`` — nothing was ever recorded; nothing to do.
        """
        from app.services.scene002_contract_only import is_contract_only as _reconcile_is_contract_only

        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.provider != "runway_router" or _reconcile_is_contract_only(job):
            return job
        if job.status == "complete":
            return job
        task_id = str(job.provider_job_id or "").strip()
        if not task_id:
            return self._record_router_reconciliation(
                job,
                task_id="",
                upstream_status=None,
                verdict="skipped_no_task_id",
                retry_permitted=False,
                detail="No upstream task id was ever recorded; nothing to reconcile.",
            )
        from app.services.providers import runway_router_provider as _router_provider

        config = self._provider_configs.get("runway_router") if isinstance(self._provider_configs, dict) else None
        adapter_key = getattr(config, "api_key", None)
        if not _router_provider.get_runway_router_api_key() and not (
            isinstance(adapter_key, str) and adapter_key.strip()
        ):
            return self._record_router_reconciliation(
                job,
                task_id=task_id,
                upstream_status=None,
                verdict="reconcile_unavailable",
                retry_permitted=False,
                detail="No Runway credential is available for the task lookup; explicit resolution is required.",
            )
        try:
            task = _router_provider.fetch_runway_router_task_status(task_id, api_key=adapter_key)
        except Exception as exc:  # noqa: BLE001 — a failed lookup is evidence, not a crash
            return self._record_router_reconciliation(
                job,
                task_id=task_id,
                upstream_status=None,
                verdict="reconcile_inconclusive",
                retry_permitted=False,
                detail=f"Task lookup failed ({type(exc).__name__}); non-creation is not established.",
            )
        if not isinstance(task, dict) or str(task.get("id") or "").strip() != task_id:
            return self._record_router_reconciliation(
                job,
                task_id=task_id,
                upstream_status=None,
                verdict="reconcile_inconclusive",
                retry_permitted=False,
                detail="Task lookup returned a malformed or mismatched identity; non-creation is not established.",
            )
        status = str(task.get("status") or "").strip().upper()
        if status == _router_provider._TASK_TERMINAL_SUCCESS:
            output_url = _router_provider._parse_task_output_url(task)
            if not output_url:
                job.status = "failed"
                job.error_message = f"Upstream router task {task_id} succeeded without an output URL"
                job.recovery_status = "recovery_failed"
                return self._record_router_reconciliation(
                    job,
                    task_id=task_id,
                    upstream_status=status,
                    verdict="upstream_success_without_output",
                    retry_permitted=False,
                    detail="Upstream success carries no output; resubmission would duplicate a completed generation.",
                )
            return await self._adopt_reconciled_router_task(job, task_id, task, output_url)
        if status in _router_provider._TASK_TERMINAL_FAILURES:
            failure = str(task.get("failure") or "").strip()
            job.error_message = f"Upstream router task {task_id} reported terminal status '{status}'" + (
                f": {failure}" if failure else ""
            )
            job.recovery_status = "recovery_failed"
            return self._record_router_reconciliation(
                job,
                task_id=task_id,
                upstream_status=status,
                verdict="upstream_terminal_failure",
                retry_permitted=True,
                detail="The recorded upstream task is terminally failed; a later retry may submit a replacement task.",
            )
        if status in _router_provider._TASK_IN_PROGRESS:
            return self._record_router_reconciliation(
                job,
                task_id=task_id,
                upstream_status=status,
                verdict="upstream_active",
                retry_permitted=False,
                detail="The recorded upstream task is still active; resubmission would duplicate it.",
            )
        return self._record_router_reconciliation(
            job,
            task_id=task_id,
            upstream_status=status or None,
            verdict="reconcile_inconclusive",
            retry_permitted=False,
            detail=f"Upstream task reported unrecognized status '{status or 'missing'}'; non-creation is not established.",
        )

    async def _adopt_reconciled_router_task(
        self,
        job: RenderJobModel,
        task_id: str,
        task: dict,
        output_url: str,
    ) -> RenderJobModel:
        """Adopt a reconciled-as-succeeded upstream task onto the job.

        The adopted outcome passes through the same post-completion integrity
        reviews as a live-polled success and carries a reconciled (not polled)
        output identity so delivery gates can verify provenance.
        """
        from app.services.providers import runway_router_provider as _router_provider

        execution = dict((job.metadata or {}).get("router_execution") or {})
        output_identity = {
            "render_job_id": job.id,
            "provider_task_id": task_id,
            "output_url": output_url,
            "association_source": "runway_router_reconciled_task",
        }
        execution["runway_task_id"] = task_id
        execution["output_identity"] = output_identity
        execution["realized_cost_credits"] = _router_provider.extract_runway_task_cost(task)
        generation_context = (job.metadata or {}).get("generation_context")
        generation_context = generation_context if isinstance(generation_context, dict) else {}
        job.output_payload = RenderJobOutput(
            asset_url=output_url,
            thumbnail_url=None,
            metadata={
                "provider_response_normalized": {
                    "provider": "runway_router",
                    "task": "video_generation",
                    "status": "completed",
                    "output": {"video_url": output_url, "status": "completed"},
                    "metadata": {
                        "task_id": task_id,
                        "render_job_id": job.id,
                        "runway_output_identity": output_identity,
                        "router_config_id": execution.get("router_config_id"),
                        "resolved_model": execution.get("resolved_model"),
                        "routing_provider": execution.get("routing_provider"),
                        "provider_mode": "model_router",
                        "generation_context_id": generation_context.get("generation_context_id"),
                        "estimated_cost_credits": execution.get("estimated_cost_credits"),
                        "realized_cost_credits": execution.get("realized_cost_credits"),
                        "reconciled": True,
                    },
                },
            },
        )
        job.metadata = dict(job.metadata or {})
        job.metadata["router_execution"] = execution
        job.status = "complete"
        job.progress = 100
        job.error_message = None
        job.completed_at = _now_iso()
        job.recovery_status = "orphan_reconciled"
        self._record_router_reconciliation(
            job,
            task_id=task_id,
            upstream_status="SUCCEEDED",
            verdict="adopted_completed_task",
            retry_permitted=False,
            detail="Adopted the confirmed upstream task output; no replacement task was created.",
        )
        job.metadata["router_reconciliation"]["reviews_applied"] = True
        await _run_continuity_review(job)
        await _run_render_quality_check(job)
        await _run_character_reference_lock(job)
        self._jobs[job.id] = job
        _persist_job(job)
        await _notify_update(job.id, job.model_dump())
        return job

    @staticmethod
    def _router_failure_reason(job: RenderJobModel) -> str | None:
        output = job.output_payload
        metadata = getattr(output, "metadata", None) if output is not None else None
        if isinstance(metadata, dict):
            normalized = metadata.get("provider_response_normalized")
            if isinstance(normalized, dict):
                inner = normalized.get("metadata")
                if isinstance(inner, dict) and isinstance(inner.get("reason"), str):
                    return inner["reason"]
        return None

    @staticmethod
    def _router_submission_attempted(job: RenderJobModel) -> bool:
        execution = (job.metadata or {}).get("router_execution")
        return isinstance(execution, dict) and execution.get("submission_attempted") is True

    async def _router_resubmit_decision(self, job: RenderJobModel) -> tuple[str, RenderJobModel]:
        """Decide whether a failed router job may be resubmitted.

        Returns ``(verdict, job)`` where verdict is ``"adopted"`` (reconcile
        completed the job — no resubmission), ``"proceed"`` (non-creation or
        upstream death is established — resubmission permitted), or
        ``"blocked"`` (ambiguity unresolved — the caller must not submit).
        """
        from app.services.providers import runway_router_provider as _router_provider

        task_id = str(job.provider_job_id or "").strip()
        if task_id:
            reconciled = await self.reconcile_runway_router_task(job.id)
            evidence = (reconciled.metadata or {}).get("router_reconciliation") or {}
            if reconciled.status == "complete":
                return ("adopted", reconciled)
            if evidence.get("retry_permitted") is True:
                return ("proceed", reconciled)
            return ("blocked", reconciled)
        reason = self._router_failure_reason(job)
        conclusive = {
            _router_provider.RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE,
            _router_provider.RUNWAY_ROUTER_CONFIG_NOT_FOUND_CODE,
            _router_provider.RUNWAY_ROUTER_MISSING_KEY_CODE,
            "required_reference_incompatible",
        }
        if reason in conclusive or (job.metadata or {}).get("model_capability_failure") is not None:
            return ("proceed", job)
        if self._router_submission_attempted(job):
            self._record_router_reconciliation(
                job,
                task_id="",
                upstream_status=None,
                verdict="ambiguous_without_task_id",
                retry_permitted=False,
                detail="A submission was attempted but no task id was recovered; non-creation is not established.",
            )
            return ("blocked", job)
        return ("proceed", job)

    async def refresh_output_url(self, job_id: str) -> Optional[str]:
        """Refresh an expired hosted output URL from the upstream Runway task."""
        job = self.get_job(job_id)
        if not job or job.provider != "runway" or not job.provider_job_id:
            return None

        config = self._provider_configs.get("runway")
        if not config:
            return None

        adapter = get_adapter("runway", config)
        try:
            refreshed = await adapter.get_job_status(job)
        finally:
            await _close_provider_adapter(adapter)
        fresh_url = ""
        if refreshed.output_payload:
            fresh_url = str(refreshed.output_payload.asset_url or "").strip()
            if not fresh_url and isinstance(refreshed.output_payload.metadata, dict):
                normalized = refreshed.output_payload.metadata.get("provider_response_normalized")
                if isinstance(normalized, dict):
                    output = normalized.get("output")
                    if isinstance(output, dict):
                        fresh_url = str(output.get("video_url") or "").strip()

        if not fresh_url:
            return None

        refreshed.output_payload = refreshed.output_payload or RenderJobOutput(asset_url=fresh_url, thumbnail_url=None, metadata={})
        refreshed.output_payload.asset_url = fresh_url
        refreshed.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = refreshed
        _persist_job(refreshed)
        await _notify_update(job_id, refreshed.model_dump())
        return fresh_url

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @classmethod
    def _is_stale(cls, job: RenderJobModel) -> bool:
        baseline = cls._parse_iso(job.last_polled_at) or cls._parse_iso(job.updated_at) or cls._parse_iso(job.created_at)
        if baseline is None:
            return False
        return (datetime.now(baseline.tzinfo) - baseline).total_seconds() >= STALE_RENDER_THRESHOLD_SECONDS

    async def create_scene_batch(
        self,
        film_id: str,
        scene_id: str,
        scene_data: dict,
        shots: list,
        provider: Optional[str] = None,
    ) -> dict:
        """
        Create a coordinated batch of render jobs for all shots in a scene.

        Calls build_prompt_context() once for the scene so every shot in the
        batch shares the same visual continuity context.  Each shot also
        receives a position note (opening / continuation / closing) so the
        provider understands its role in the sequence.

        Jobs are created in order and submitted in parallel.

        Args:
            film_id:    The film/project identifier.
            scene_id:   The scene identifier.
            scene_data: Scene metadata dict (description, emotional_tone, etc.).
            shots:      Ordered list of shot dicts.  Each dict should contain at
                        least a ``shot_id`` and optionally ``description``,
                        ``camera``, ``prompt``.
            provider:   Optional provider override; falls back to default.

        Returns:
            {
                "batch_id":       str,
                "scene_id":       str,
                "job_ids":        list[str],
                "shared_context": dict,   # continuity context applied to all shots
                "status":         "pending"
            }
        """
        import uuid as _uuid

        batch_id = f"batch-{_uuid.uuid4().hex[:16]}"
        total = len(shots)

        # ── Build shared continuity context once for the whole scene ─────────
        shared_context: dict = {}
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            shared_context = _cont_svc.build_prompt_context(
                scene_id=scene_id,
                film_id=film_id,
            )
        except Exception as _exc:
            logger.debug("Batch shared context unavailable for scene %s: %s", scene_id, _exc)

        # ── Build the shared context block string ─────────────────────────────
        _motifs = shared_context.get("active_motifs") or []
        _anchors = shared_context.get("continuity_anchors") or []
        _has_ctx = bool(
            shared_context.get("emotional_register")
            or _motifs
            or shared_context.get("tonal_direction")
            or _anchors
        )
        shared_context_block = ""
        if _has_ctx:
            shared_context_block = _CONTINUITY_CONTEXT_BLOCK.format(
                emotional_register=shared_context.get("emotional_register") or "unspecified",
                active_motifs=", ".join(_motifs) if _motifs else "none",
                tonal_direction=shared_context.get("tonal_direction") or "unspecified",
                continuity_anchors=", ".join(_anchors) if _anchors else "none",
            )

        # ── Create one job per shot ───────────────────────────────────────────
        job_ids: list[str] = []
        for index, shot in enumerate(shots):
            shot_id = str(shot.get("shot_id") or f"{scene_id}_shot_{index + 1:03d}")
            base_prompt = str(
                shot.get("prompt")
                or shot.get("description")
                or shot.get("visual_description")
                or ""
            ).strip()
            camera = str(shot.get("camera") or shot.get("camera_notes") or "").strip()
            if camera:
                base_prompt = f"{base_prompt}. Camera: {camera}".strip(". ")

            # Shot position note
            if total == 1:
                position_note = "Single shot — establish the space and carry the full emotional register."
            elif index == 0:
                position_note = f"Shot 1 of {total} in scene. Opening shot — establish the space."
            elif index == total - 1:
                position_note = f"Shot {index + 1} of {total} in scene. Closing shot — carry emotional register forward."
            else:
                position_note = f"Shot {index + 1} of {total} in scene. Continuation — maintain visual consistency with prior shot."

            full_prompt = base_prompt
            if shared_context_block:
                full_prompt = full_prompt + shared_context_block
            full_prompt = full_prompt + f"\n\n[SHOT POSITION]\n{position_note}"

            job = self.create_job(
                project_id=film_id,
                shot_id=shot_id,
                provider=provider,
                prompt=full_prompt,
                reference_assets=shot.get("reference_assets") or [],
                parameters=shot.get("parameters") or {},
            )
            # Tag the job with the batch_id
            job.batch_id = batch_id
            self._jobs[job.id] = job
            _persist_job(job)
            job_ids.append(job.id)

        # ── Submit all jobs in parallel when a provider is explicitly chosen ──
        if provider:
            submit_tasks = [self.submit_job(jid) for jid in job_ids]
            results = await asyncio.gather(*submit_tasks, return_exceptions=True)
            for jid, result in zip(job_ids, results):
                if isinstance(result, Exception):
                    logger.warning("Batch job %s submit failed: %s", jid, result)

        # ── Store batch metadata ──────────────────────────────────────────────
        batch = {
            "batch_id": batch_id,
            "scene_id": scene_id,
            "film_id": film_id,
            "job_ids": job_ids,
            "shared_context": shared_context,
            "status": "pending",
        }
        self._batches[batch_id] = batch
        logger.info(
            "SCENE_BATCH_CREATED | batch=%s | scene=%s | shots=%d",
            batch_id, scene_id, total,
        )
        return batch

    def get_batch_status(self, batch_id: str) -> Optional[dict]:
        """
        Return the current status of a render batch.

        Counts jobs by terminal state and returns a summary.

        Args:
            batch_id: The batch identifier.

        Returns:
            {
                "batch_id":  str,
                "scene_id":  str,
                "total":     int,
                "complete":  int,
                "pending":   int,
                "failed":    int,
                "jobs":      list[dict]
            }
            or None if the batch_id is not found.
        """
        batch = self._batches.get(batch_id)
        if not batch:
            return None

        job_dicts: list[dict] = []
        complete = pending = failed = 0
        for jid in batch["job_ids"]:
            job = self.get_job(jid)
            if job:
                d = job.model_dump()
                job_dicts.append(d)
                if job.status == "complete":
                    complete += 1
                elif job.status in ("failed", "cancelled"):
                    failed += 1
                else:
                    pending += 1
            else:
                pending += 1

        return {
            "batch_id": batch_id,
            "scene_id": batch.get("scene_id", ""),
            "total": len(batch["job_ids"]),
            "complete": complete,
            "pending": pending,
            "failed": failed,
            "jobs": job_dicts,
        }

    async def recover_jobs_after_restart(self) -> dict:
        """Recover rendering/pending jobs and reconcile orphaned provider tasks after restart."""
        recovered = 0
        stale_recovered = 0
        orphan_reconciled = 0
        hydrated = 0
        errors: list[str] = []

        if _storage:
            try:
                try:
                    from app.config import get_settings

                    hydration_limit = int(getattr(get_settings(), "render_recovery_hydration_limit", 1000) or 1000)
                except Exception:
                    hydration_limit = 1000
                persisted_jobs = _storage.list_jobs(limit=max(1, min(hydration_limit, 5000)))
                for persisted_job in persisted_jobs:
                    self._jobs[persisted_job.id] = persisted_job
                hydrated = len(persisted_jobs)
            except Exception as exc:
                errors.append(f"hydrate: {exc}")

        for job in list(self._jobs.values()):
            try:
                from app.services.scene002_contract_only import is_contract_only, verify_job_contract, verify_submission_boundary
                if is_contract_only(job):
                    try:
                        if _storage is None:
                            raise ValueError("Durable protected execution storage is unavailable")
                        persisted = _storage.get_job(job.id)
                        if persisted is None:
                            raise ValueError("Durable protected contract cannot be recovered after restart")
                        verify_job_contract(persisted, require_project=False)
                        if persisted.metadata != job.metadata or persisted.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json"):
                            raise ValueError("Recovered protected job differs from its durable record")
                        from app.services.providers.runway_router_provider import get_router_config_id
                        from app.services.project_persistence_service import project_persistence_service
                        verify_submission_boundary(
                            persisted,
                            storage=_storage,
                            project=project_persistence_service.load_readonly_existing(persisted.project_id),
                            router_config_id=get_router_config_id(),
                            backend_root=Path(__file__).resolve().parents[2],
                        )
                        job = persisted
                        self._jobs[job.id] = persisted
                    except Exception as exc:
                        if job.status not in {"complete", "failed", "cancelled"}:
                            job.status = "failed"
                            job.error_message = f"Scene 002 contract-only recovery failed closed: {exc}"
                            job.metadata = dict(job.metadata or {})
                            job.metadata["scene002_contract_failure"] = str(exc)
                            job.updated_at = datetime.now().isoformat()
                            self._jobs[job.id] = job
                            _persist_job(job)
                        errors.append(f"{job.id}: {exc}")
                        continue
                if job.status in {"pending", "rendering"}:
                    if not job.provider_job_id and self._is_stale(job):
                        job.status = "failed"
                        job.error_message = "Stale job with no provider task id after restart"
                        job.recovery_status = "stale_recovered"
                        job.updated_at = datetime.now().isoformat()
                        if not is_contract_only(job):
                            _set_zero_touch_phase(job, "render", "failed", error=job.error_message, error_type="abandoned_without_provider_job_id")
                            _record_failure_location(
                                job,
                                phase="render",
                                reason=job.error_message,
                                error_type="abandoned_without_provider_job_id",
                                category="permanent",
                            )
                        _persist_job(job)
                        stale_recovered += 1
                        continue
                    if job.provider_job_id:
                        from app.services.scene002_contract_only import is_contract_only, verify_submission_boundary
                        if is_contract_only(job):
                            if _storage is None:
                                raise ValueError("Protected recovery requires durable render storage")
                            from app.services.providers.runway_router_provider import get_router_config_id
                            from app.services.project_persistence_service import project_persistence_service
                            recovery_project = project_persistence_service.load_readonly_existing(job.project_id)
                            verify_submission_boundary(
                                job,
                                storage=_storage,
                                project=recovery_project,
                                router_config_id=get_router_config_id(),
                                backend_root=Path(__file__).resolve().parents[2],
                            )
                            durable = _storage.get_job(job.id)
                            if (
                                durable is None
                                or durable.metadata != job.metadata
                                or durable.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json")
                            ):
                                raise ValueError("Protected recovery cannot trust a cache-only job snapshot")
                        if (
                            job.provider == "runway_router"
                            and str(job.provider_job_id or "").strip()
                            and not is_contract_only(job)
                        ):
                            # R4.3E: the router adapter has no status read
                            # (get_job_status is a no-op by design), so an
                            # in-flight router job is reconciled against its
                            # recorded upstream task instead of polled.
                            updated = await self.reconcile_runway_router_task(job.id)
                        else:
                            config = self._provider_configs.get(job.provider) or self._provider_configs.get("simulated")
                            adapter = get_adapter(job.provider, config)
                            try:
                                updated = await adapter.get_job_status(job)
                            finally:
                                await _close_provider_adapter(adapter)
                        if is_contract_only(job) and (
                            updated.metadata != job.metadata
                            or updated.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json")
                            or updated.project_id != job.project_id
                            or updated.shot_id != job.shot_id
                            or updated.provider != job.provider
                        ):
                            raise ValueError("Protected recovery status poll attempted to mutate frozen creative input")
                        updated.updated_at = datetime.now().isoformat()
                        if updated.status == "complete" and not updated.completed_at:
                            updated.completed_at = updated.updated_at
                        if updated.status == "complete":
                            updated.recovery_status = "recovered_terminal"
                            _recovery_reconcile_evidence = (updated.metadata or {}).get("router_reconciliation") or {}
                            if not is_contract_only(updated) and not _recovery_reconcile_evidence.get("reviews_applied"):
                                await _run_continuity_review(updated)
                                await _run_render_quality_check(updated)
                                await _run_character_reference_lock(updated)
                        elif updated.is_terminal():
                            updated.recovery_status = "recovery_failed"
                        else:
                            updated.recovery_status = "active"
                        self._jobs[job.id] = updated
                        _persist_job(updated)
                        if self._is_stale(updated) and not updated.is_terminal():
                            updated.status = "failed"
                            updated.error_message = "Stale job — exceeded render timeout after restart"
                            updated.recovery_status = "stale_recovered"
                            updated.updated_at = datetime.now().isoformat()
                            if not is_contract_only(updated):
                                _set_zero_touch_phase(updated, "render", "failed", error=updated.error_message, error_type="render_timeout")
                                _record_failure_location(
                                    updated,
                                    phase="render",
                                    reason=updated.error_message,
                                    error_type="render_timeout",
                                    category="temporary",
                                )
                            _persist_job(updated)
                            stale_recovered += 1
                        recovered += 1

                if job.status == "failed" and job.provider == "runway" and job.provider_job_id and not is_contract_only(job):
                    updated = await self.reconcile_completed_runway_task(job.id)
                    if updated.status == "complete":
                        orphan_reconciled += 1
                if (
                    job.status == "failed"
                    and job.provider == "runway_router"
                    and job.provider_job_id
                    and not is_contract_only(job)
                ):
                    # R4.3E: extend orphan reconciliation to router tasks; a
                    # failed router job may still have a live upstream task.
                    updated = await self.reconcile_runway_router_task(job.id)
                    if updated.status == "complete":
                        orphan_reconciled += 1
            except Exception as exc:
                errors.append(f"{job.id}: {exc}")

        return {
            "hydrated_jobs": hydrated,
            "recovered_jobs": recovered,
            "stale_recovered_jobs": stale_recovered,
            "orphan_reconciled_jobs": orphan_reconciled,
            "error_count": len(errors),
            "errors": errors,
        }

    async def poll_active_runway_jobs(self) -> None:
        """
        Background loop that polls all providers for jobs in incomplete states.
        Runs every 10 seconds. Never raises — logs errors and continues.

        Runway jobs are reconciled against upstream task status; local_ltx
        jobs are polled directly via get_job_status which delegates to the
        LocalLTXAdapter. All other providers are covered by stale-timeout
        detection above and may poll on demand through their routes.
        """
        POLL_STATUSES = ["queued", "pending", "rendering", "processing", "submitted"]
        logger.info("POLLING_LOOP_STARTED | interval=10s | statuses=%s", POLL_STATUSES)

        while True:
            try:
                active_jobs = self._get_jobs_by_status(POLL_STATUSES)
                logger.info("POLLING_CYCLE | checking=%d jobs", len(active_jobs))

                for job in active_jobs:
                    try:
                        # Hard timeout: any active job older than threshold is stuck
                        created = self._parse_iso(job.created_at)
                        if created and (datetime.now(created.tzinfo) - created).total_seconds() >= STALE_RENDER_THRESHOLD_SECONDS:
                            job.status = "failed"
                            job.error_message = "Stale job — exceeded render timeout"
                            job.recovery_status = "stale_recovered"
                            job.updated_at = datetime.now().isoformat()
                            if not _is_contract_only(job):
                                _set_zero_touch_phase(job, "render", "failed", error=job.error_message, error_type="polling_timeout")
                                _record_failure_location(
                                    job,
                                    phase="render",
                                    reason=job.error_message,
                                    error_type="polling_timeout",
                                    category="temporary",
                                )
                            self._jobs[job.id] = job
                            _persist_job(job)
                            logger.info("POLLING_STALE_CANCEL | job=%s | provider=%s", job.id, job.provider)
                            continue
                        if job.provider == "runway" and not _is_contract_only(job):
                            await self.reconcile_completed_runway_task(job.id)
                        elif job.provider == "runway_router" and isinstance(job.metadata, dict) and job.metadata.get("execution_mode") == "SCENE_002_CONTRACT_ONLY":
                            await self.get_job_status(job.id)
                        elif job.provider == "local_ltx":
                            await self.get_job_status(job.id)
                    except Exception as e:
                        logger.debug("Polling error for job %s: %s", job.id, e)
            except Exception as e:
                logger.error("Polling loop error: %s", e)
            await asyncio.sleep(10)


# Global service instance
render_service = RenderService()

# Router quote enforcement needs access to today's persisted render history for
# the per-project daily budget. Inject only after the singleton exists to keep
# module initialization acyclic.
from app.services.generation_cost_gate import generation_cost_gate

generation_cost_gate.set_renderer(render_service)


def backfill_render_jobs_from_project_state() -> dict:
    """Backfill canonical render_jobs rows from project_state_store.json."""
    if _storage is None:
        return {
            "created_count": 0,
            "skipped_count": 0,
            "created_job_ids": [],
            "skipped_job_ids": [],
            "errors": ["Render job storage is not initialized"],
        }

    from app.services.render_job_backfill import (
        backfill_render_jobs_from_project_state as _backfill_render_jobs_from_project_state,
    )

    result = _backfill_render_jobs_from_project_state(
        storage=_storage,
        render_service=render_service,
    )
    return {
        **result,
        "backfilled_count": result.get("created_count", 0),
        "already_exists_count": result.get("skipped_count", 0),
        "errors": result.get("errors", []),
    }
