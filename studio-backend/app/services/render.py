from typing import Any, Optional, Callable, Awaitable
from datetime import datetime
import hashlib
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse
from app.models import (
    RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset,
    ProviderConfig, ProviderStatus, StudioProject
)
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.adapters import RenderProviderAdapter, get_adapter, ADAPTER_REGISTRY
from app.config import get_settings
from app.services.project_store import project_store
from app.services.shared.dashscope_client import DashScopeConfigError, get_dashscope_config
from app.utils.helpers import derive_scene_id_from_shot_id
import logging
import asyncio

logger = logging.getLogger("studio-render")

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

        locks = _char_ref_svc.lock_first_references_for_completed_job(
            job=job,
            storage=storage,
        )
        if locks:
            job.metadata = dict(job.metadata or {})
            job.metadata["character_reference_locks_created"] = [
                lock.model_dump(mode="json") for lock in locks
            ]
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
            _storage.save_job(job)
            return True
        except Exception as e:
            error_text = str(e)
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
    if len(result) > max_chars:
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
    if len(result) > max_chars:
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
            index = text_lower.find(name_lower)
            if index >= 0:
                seen.add(name_lower)
                matches.append((index, name))
        for _, name in sorted(matches, key=lambda item: item[0]):
            if name not in candidates:
                candidates.append(name)
        if candidates:
            return candidates
    return []


def _format_visible_cast_constraint(character_names: list[str]) -> str:
    names = _normalize_character_names(character_names)
    if not names:
        return ""
    joined = " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + f", and {names[-1]}"
    return f"Only {joined} visible; no extras."


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
    if provider == "runway":
        return os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5"
    if provider == "happyhorse-r2v":
        return "happyhorse-1.1-r2v"
    if provider == "happyhorse":
        return "happyhorse-1.1-t2v"
    if provider == "wan":
        return "wan2.6-t2v"
    return str(parameters.get("model") or provider or "default")


def _validate_model_override(provider: str, parameters: dict[str, Any]) -> None:
    requested = str(parameters.get("model") or "").strip()
    if not requested:
        return
    if provider == "runway":
        from app.adapters import ALLOWED_RUNWAY_MODELS

        if requested not in ALLOWED_RUNWAY_MODELS:
            raise ValueError(
                f"Unsupported Runway model '{requested}'. Allowed models: {sorted(ALLOWED_RUNWAY_MODELS)}"
            )
    elif provider == "happyhorse" and requested != "happyhorse-1.1-t2v":
        raise ValueError("HappyHorse text-to-video does not support this model override")
    elif provider == "happyhorse-r2v" and requested != "happyhorse-1.1-r2v":
        raise ValueError("HappyHorse reference-to-video does not support this model override")
    elif provider == "wan" and requested != "wan2.6-t2v":
        raise ValueError("Wan text-to-video does not support this model override")


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
    supports_images = provider in {"runway", "happyhorse-r2v", "simulated", "local"}
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
                "injected_into_request": supports_images,
                "fallback_prompt_constraint": fallback if not supports_images else "",
            }
        )
    return rows


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
    if job.input_payload and isinstance(job.input_payload.parameters, dict):
        job.input_payload.parameters["zero_touch_debug"] = debug


_PERMANENT_PROVIDER_ERROR_TYPES = {
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
    if not classification["retryable"]:
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
            "Runway key source=%s exists=%s length=%s first4=%s last4=%s",
            runway_key_source,
            bool(runway_api_key),
            len(runway_api_key),
            runway_api_key[:4] if runway_api_key else "",
            runway_api_key[-4:] if runway_api_key else "",
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

        try:
            dashscope_config = get_dashscope_config()
            dashscope_api_key = dashscope_config.api_key
            dashscope_api_endpoint = dashscope_config.workspace_base_url or dashscope_config.native_api_base_url
        except DashScopeConfigError:
            dashscope_api_key = ""
            dashscope_region = os.getenv("DASHSCOPE_REGION", "intl").strip().lower()
            dashscope_api_endpoint = (
                "https://dashscope.aliyuncs.com/api/v1"
                if dashscope_region == "beijing"
                else "https://dashscope-intl.aliyuncs.com/api/v1"
            )
        self._provider_configs["happyhorse"] = ProviderConfig(
            provider_id="happyhorse",
            name="HappyHorse",
            enabled=True,
            is_simulated=False,
            api_key=dashscope_api_key or None,
            api_endpoint=dashscope_api_endpoint,
            requires=["api_key"],
            capabilities=["video_generation", "text_to_video"],
        )
        self._provider_configs["happyhorse-r2v"] = ProviderConfig(
            provider_id="happyhorse-r2v",
            name="HappyHorse Reference-to-Video",
            enabled=True,
            is_simulated=False,
            api_key=dashscope_api_key or None,
            api_endpoint=dashscope_api_endpoint,
            requires=["api_key"],
            capabilities=["video_generation", "reference_to_video", "image_conditioning"],
        )
        self._provider_configs["wan"] = ProviderConfig(
            provider_id="wan",
            name="Alibaba Wan",
            enabled=True,
            is_simulated=False,
            api_key=dashscope_api_key or None,
            api_endpoint=dashscope_api_endpoint,
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
            if provider_id == "runway" and test_mode == "mock_success":
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
                and not (provider_id == "runway" and test_mode == "mock_success")
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
            
            statuses.append(ProviderStatus(
                provider_key=provider_id,
                provider_id=provider_id,
                name=config.name,
                status="available" if config.enabled else "disabled",
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
        return self._provider_configs.get(provider_id)

    def set_provider_config(self, config: ProviderConfig) -> ProviderConfig:
        """Update provider configuration"""
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
        selected = os.getenv("RENDER_VIDEO_PROVIDER", get_settings().render_video_provider or "happyhorse").strip().lower()
        if selected in self._provider_configs:
            return selected
        return "happyhorse"

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

    def create_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None
    ) -> RenderJobModel:
        """Create a new render job with validation"""
        # Validate shot_id is not empty
        if not shot_id or not shot_id.strip():
            raise ValueError("shot_id cannot be empty")

        # ── Per-scene provider override ───────────────────────────────────────
        # If the project has a per-scene override for this shot's scene, use it
        # instead of the caller-supplied provider (unless the caller explicitly
        # passed one, which takes precedence).
        if provider is None:
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
        
        # Validate provider against known providers
        if provider:
            if provider not in self._provider_configs:
                raise ValueError(f"Unknown provider '{provider}'. Available providers: {list(self._provider_configs.keys())}")
        else:
            provider = self.get_default_provider()

        _initial_parameters = dict(parameters or {})
        _validate_model_override(provider, _initial_parameters)
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
        _is_generic = (
            not prompt.strip()
            or len(prompt.strip()) < 50
            or "Generate scene" in prompt
            or "Cinematic quality" in prompt
        )
        _prompt_slots_for_adherence: dict[str, str] | None = None
        
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

                            # 5. Build the slotted prompt
                            from app.services.shot_prompt_builder import build_slotted_prompt
                            _slotted = build_slotted_prompt(
                                scene_data=_scene,
                                shot_number=_shot_number,
                                character_visual_canon=_char_visuals,
                                action_text=_action_text,
                                environment_motifs=_environment,
                                camera_direction="",  # let builder default from shot_number
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

        _consistency_payload = None
        _canonical_identity_context = None
        try:
            _active_storage_for_refs = _storage
            if _active_storage_for_refs is None:
                from app.data.storage import get_storage as _get_storage

                _active_storage_for_refs = _get_storage("sqlite")
            if _active_storage_for_refs is not None:
                from app.services.character_visual_reference_service import (
                    character_visual_reference_service as _char_ref_svc,
                )

                _consistency_payload = _char_ref_svc.build_consistency_payload_for_shot(
                    project_id=project_id,
                    shot_id=shot_id,
                    storage=_active_storage_for_refs,
                    prompt=prompt,
                )
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
                _identity_records = _identity_svc.build_records_from_storage(
                    project_id=project_id,
                    storage=_active_storage_for_identity,
                    character_ids=_identity_character_ids or None,
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

        _input_parameters = dict(parameters or {})
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
        _validate_model_override(provider, _input_parameters)

        _environment_context = None
        try:
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
        except Exception as _exc:
            logger.debug("Environment continuity context skipped for %s/%s: %s", project_id, shot_id, _exc)

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

        job = RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=prompt,
                referenceAssets=reference_assets or [],
                parameters=_input_parameters,
                consistency_payload=_consistency_payload,
            ),
            metadata={
                "zero_touch_pipeline": _zero_touch_debug,
                "character_identity_warnings": (
                    _canonical_identity_context.get("conflict_warnings", [])
                    if isinstance(_canonical_identity_context, dict)
                    else []
                ),
                "environment_continuity_context": _environment_context or {},
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
        if not _is_generic and not _skip_character_injection:
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
                        _char_block = "Characters: " + "; ".join(
                            [part for part in [_cast_constraint, *_char_summaries] if part]
                        )
                        _current_prompt = job.input_payload.prompt or ""
                        # Skip if characters already present (e.g., generic prompt path)
                        if "Characters:" not in _current_prompt:
                            _sep = ". " if not _current_prompt.rstrip().endswith((".", "!", "?")) else " "
                            _new_prompt = f"{_current_prompt}{_sep}{_char_block}"
                            # If over budget, truncate original prompt to fit characters
                            if len(_new_prompt) > _PROMPT_BUDGET:
                                _char_len = len(_sep) + len(_char_block)
                                _orig_budget = _PROMPT_BUDGET - _char_len
                                if _orig_budget > 50:
                                    _truncated_orig = _current_prompt[:_orig_budget]
                                    _last_sp = _truncated_orig.rfind(" ")
                                    if _last_sp > int(_orig_budget * 0.6):
                                        _truncated_orig = _truncated_orig[:_last_sp]
                                    _new_prompt = f"{_truncated_orig}{_sep}{_char_block}"
                                else:
                                    # Not enough room for both; prioritize characters
                                    _new_prompt = _char_block[:_PROMPT_BUDGET]
                            job.input_payload.prompt = _new_prompt
                            logger.info(
                                "CHARACTER_PROMPT_INJECTION | scene=%s | chars=%d | source=previs_prompt",
                                _scene_id,
                                len(_char_summaries),
                            )
            except Exception as _exc:
                logger.debug("Character injection for non-generic prompt skipped: %s", _exc)

        if (
            isinstance(parameters, dict)
            and parameters.get("structured_prompt")
            and not job.input_payload.parameters.get("prompt_slots")
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

                job.input_payload.prompt = _slotted["prompt"]
                if _sc_applied:
                    _reassembled = reassemble_prompt_from_slots(_slotted["slots"])
                    if _reassembled != "Cinematic shot. Film quality.":
                        job.input_payload.prompt = _reassembled
                job.input_payload.parameters["prompt_slots"] = {
                    str(_slot): str(_value or "")
                    for _slot, _value in (_slotted.get("slots") or {}).items()
                    if _slot != "reserve"
                }
                logger.info(
                    "STRUCTURED_PREVIS_PROMPT_APPLIED | job=%s | scene=%s | shot_planning=%s | slots=%s",
                    job_id,
                    _scene_id,
                    isinstance(_shot_planning, dict),
                    {k: len(v) for k, v in job.input_payload.parameters["prompt_slots"].items()},
                )
            except Exception as _exc:
                logger.debug("Structured prompt assembly skipped for job %s: %s", job_id, _exc)

        # ── Continuity context injection ──────────────────────────────────────
        # Derive scene_id from shot_id (e.g. "scene_001_shot_001" → "scene_001").
        # film_id is the project_id — they are the same identifier here.
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            from app.utils.director_intent_injection import build_director_intent_prefix
            from app.data.storage import get_storage
            
            _scene_id = derive_scene_id_from_shot_id(shot_id)
            _ctx = _cont_svc.build_prompt_context(scene_id=_scene_id, film_id=project_id)
            _has_context = bool(
                _ctx.get("emotional_register")
                or _ctx.get("active_motifs")
                or _ctx.get("tonal_direction")
                or _ctx.get("continuity_anchors")
            )
            
            # Build director intent prefix
            _director_storage = get_storage()
            _intent = _director_storage.load_director_intent(project_id)
            _intent_prefix = build_director_intent_prefix(_intent)
            
            # Prepend director intent if it exists
            if _intent_prefix:
                job.input_payload.prompt = _intent_prefix + (job.input_payload.prompt or "")
                logger.info("DIRECTOR_INTENT_INJECTION | project=%s", project_id)
            
            # Append continuity context if it exists
            if _has_context:
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
        job.input_payload.parameters["zero_touch_debug"] = _zero_touch_debug
        job.metadata = dict(job.metadata or {})
        job.metadata["zero_touch_pipeline"] = _zero_touch_debug
        _prompt_contradictions = _detect_prompt_contradictions(job.input_payload.prompt or "")
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
            and not (provider == "runway" and test_mode == "mock_success")
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

        self._jobs[job_id] = job
        _persist_job(job)
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        """Submit a job to its provider with error handling"""
        job = self._jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for submission")
            raise ValueError(f"Job {job_id} not found")
        if job_id in self._submit_locks:
            logger.info("Duplicate submit blocked for %s", job_id)
            return job
        if job.status in {"rendering", "complete", "needs_review"}:
            logger.info("Submit skipped for %s because status=%s", job_id, job.status)
            return job
        if job.status == "failed":
            metadata = job.metadata if isinstance(job.metadata, dict) else {}
            reliability = metadata.get("pipeline_reliability") if isinstance(metadata.get("pipeline_reliability"), dict) else {}
            failure = reliability.get("failure_location") if isinstance(reliability.get("failure_location"), dict) else {}
            if failure.get("category") == "permanent":
                logger.info(
                    "Submit skipped for permanent failed job %s phase=%s error_type=%s",
                    job_id,
                    failure.get("phase") or "",
                    failure.get("error_type") or "",
                )
                return job
        if job.status == "failed" and job.retry_count >= MAX_RETRIES:
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
        self._submit_locks.add(job_id)
        adapter: RenderProviderAdapter | None = None

        try:
            config = self._provider_configs.get(job.provider)
            if not config:
                config = self._provider_configs["simulated"]
                job.provider = "simulated"
                logger.warning(f"Provider {job.provider} not found, falling back to simulated")

            params = job.input_payload.parameters if job.input_payload and isinstance(job.input_payload.parameters, dict) else {}
            _validate_model_override(job.provider, params)
            _missing_reference_assets = _missing_local_reference_assets(
                list(job.input_payload.referenceAssets or []) if job.input_payload else []
            )
            if _missing_reference_assets:
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
                if _storage:
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
            submitted_job = await asyncio.wait_for(
                adapter.submit_job(job),
                timeout=PROVIDER_CALL_TIMEOUT_SECONDS,
            )
            
            # Ensure provider is set on the returned job
            if not submitted_job.provider or submitted_job.provider.strip() == "":
                submitted_job.provider = job.provider
                logger.info(f"Provider field set to {job.provider} for job {job_id}")
            
            submitted_job.recovery_status = "active"
            submitted_job.updated_at = datetime.now().isoformat()
            
            self._jobs[job_id] = submitted_job
            _set_zero_touch_phase(
                submitted_job,
                "render",
                "complete" if submitted_job.status == "complete" else submitted_job.status,
                provider_job_id=submitted_job.provider_job_id or "",
            )
            if submitted_job.status == "failed":
                _record_provider_failure_policy(submitted_job)
            _persist_job(submitted_job)
            _log_audit("submit_job", "render_job", job_id, details=f"provider={submitted_job.provider}")

            if submitted_job.status == "complete" and previous_status != "complete":
                await _run_continuity_review(submitted_job)
                await _run_render_quality_check(submitted_job)
                await _run_character_reference_lock(submitted_job)
            
            await _notify_update(job_id, submitted_job.model_dump())
            return submitted_job
            
        except Exception as e:
            error_message = (
                f"Provider call timed out after {PROVIDER_CALL_TIMEOUT_SECONDS}s"
                if isinstance(e, TimeoutError)
                else str(e)
            )
            logger.error(f"Failed to submit job {job_id}: {error_message}")
            job.status = "failed"
            job.error_message = error_message
            job.updated_at = datetime.now().isoformat()
            _set_zero_touch_phase(job, "render", "failed", error=error_message)
            _record_provider_failure_policy(job, error_message)
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

        # Delegate to adapter for live status on non-terminal jobs
        if not job.is_terminal():
            try:
                config = self._provider_configs.get(job.provider)
                if config:
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
                        job.status != "complete" and updated.status == "complete"
                    )
                    
                    self._jobs[job_id] = updated
                    if updated.status == "failed":
                        _record_provider_failure_policy(updated)
                    _persist_job(updated)
                    
                    # Run completion hooks on status transition
                    if transitioned_to_complete:
                        await _run_continuity_review(updated)
                        await _run_render_quality_check(updated)
                        await _run_character_reference_lock(updated)
                    
                    if updated.status != job.status:
                        await _notify_update(job_id, updated.model_dump())
                    return updated
            except Exception as _exc:
                poll_error = (
                    f"Provider status poll timed out after {PROVIDER_CALL_TIMEOUT_SECONDS}s"
                    if isinstance(_exc, TimeoutError)
                    else str(_exc)
                )
                job.status = "failed"
                job.error_message = f"Provider status poll failed: {poll_error}"
                job.last_polled_at = datetime.now().isoformat()
                job.updated_at = job.last_polled_at
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
        existed = job_id in self._jobs
        self._jobs.pop(job_id, None)
        if _storage:
            try:
                _storage.delete_job(job_id)
            except Exception as e:
                logger.error(f"Failed to delete job {job_id} from storage: {e}")
        return existed

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
        """Retry a failed job"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.retry_count += 1
        job.status = "pending"
        job.error_message = None
        job.recovery_status = "retrying"
        job.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = job
        _persist_job(job)
        
        return await self.submit_job(job_id)

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
        """Get a job by ID"""
        job = self._jobs.get(job_id)
        if job:
            return job
        if _storage:
            job = _storage.get_job(job_id)
            if job:
                self._jobs[job_id] = job
            return job
        return None

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
        """Get outputs for a completed job"""
        job = self.get_job(job_id)
        if not job:
            return []

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        try:
            return await adapter.fetch_outputs(job)
        finally:
            await _close_provider_adapter(adapter)

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
                if job.status in {"pending", "rendering"}:
                    if not job.provider_job_id and self._is_stale(job):
                        job.status = "failed"
                        job.error_message = "Stale job with no provider task id after restart"
                        job.recovery_status = "stale_recovered"
                        job.updated_at = datetime.now().isoformat()
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
                        config = self._provider_configs.get(job.provider) or self._provider_configs.get("simulated")
                        adapter = get_adapter(job.provider, config)
                        try:
                            updated = await adapter.get_job_status(job)
                        finally:
                            await _close_provider_adapter(adapter)
                        updated.updated_at = datetime.now().isoformat()
                        if updated.status == "complete" and not updated.completed_at:
                            updated.completed_at = updated.updated_at
                        if updated.status == "complete":
                            updated.recovery_status = "recovered_terminal"
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

                if job.status == "failed" and job.provider == "runway" and job.provider_job_id:
                    updated = await self.reconcile_completed_runway_task(job.id)
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
        Background loop that polls Runway for all jobs in incomplete states.
        Runs every 10 seconds. Never raises — logs errors and continues.
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
                        if job.provider == "runway":
                            await self.reconcile_completed_runway_task(job.id)
                    except Exception as e:
                        logger.debug("Polling error for job %s: %s", job.id, e)
            except Exception as e:
                logger.error("Polling loop error: %s", e)
            await asyncio.sleep(10)


# Global service instance
render_service = RenderService()


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
