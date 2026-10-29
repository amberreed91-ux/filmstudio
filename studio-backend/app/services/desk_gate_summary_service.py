"""Production Desk gate-summary aggregate — read-only.

One GET backing the visual status board. Answers, per scene and per shot:
D4 image-prompt status, D6 send-text readiness, setting-anchor state, batch
readiness/blockers, approval state, latest job status, and a single
``next_action`` enum per scene.

Side-effect contract (STEP 1b): this module calls ONLY pure read paths.
It deliberately does NOT call
``SceneProductionPipelineService.prepare_scene_batch`` (that method calls
``_register_prepared_scene_batch`` — a write to the service's in-memory
registry — and runs the cost gate), does NOT touch the universe graph
(which lazily auto-populates), does NOT refresh anything, creates no jobs,
and invokes no provider. See READ_CALLS below; every entry is a SELECT or
an in-memory derivation over already-loaded rows.

``setting_anchor`` is ``set`` (verified), ``blocked`` (gate evaluated and
failed), or ``unknown`` (the anchor could not be evaluated because the
project/scene record itself is unresolvable — never a gate verdict). The
scene record the board already loaded is injected into the resolution so
evaluation does not depend on the global project store.

The single ``CREATE TABLE IF NOT EXISTS`` reachable from here lives inside
``DatabaseStorage.get_storyboard_image_prompt`` (via
``_ensure_image_prompts_table``). It is a no-op when the table already
exists — which is always the case for any project that has ever derived a
prompt — and the test suite asserts the DB fingerprint is identical before
and after calling this endpoint.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.data.storage import get_storage
from app.services.project_persistence_service import project_persistence_service
from app.services.reference_asset_service import ReferenceAssetService
from app.services.stability import StateError
from app.services.storyboard_image_prompt_service import StoryboardImagePromptService

logger = logging.getLogger("desk-gate-summary-service")

# Every storage/service call this module makes. All reads; no writes, no
# table creation of its own, no refresh, no provider, no job creation.
READ_CALLS = [
    "project_persistence_service.load_readonly_existing "
    "(read existing project JSON, no hydration/normalization/sync)",
    "storage.get_storyboard_blueprint (SELECT storyboard_blueprints)",
    "storage.list_storyboard_shots (SELECT storyboard_shots)",
    "read-only sqlite_master probe for storyboard_image_prompts (mode=ro; "
    "gates the prompt reads so an absent table is never CREATEed)",
    "storyboard_image_prompt_service.status_for_shot "
    "(D4 states over SELECTed image-prompt row; no derive/edit/approve)",
    "storyboard_image_prompt_service.resolve_provider_send_text "
    "(D6 fail-closed verdict over the same SELECTed row; raises, never sends)",
    "reference_validation.resolve_scene_reference_requirements "
    "(documented read-only: no provisional locks, no approval change)",
    "reference_asset_service.list_scene_confirmations "
    "(revalidates durable rows against current bindings; creates nothing)",
    "storage.list_jobs (SELECT render_jobs, newest-first per shot)",
    "storage.list_cinematic_memory_for_project "
    "(SELECT cinematic memory visual tags for scene-level motif_ref)",
]

# Per-scene next actions. Exactly one per scene; plain language for the board.
NEXT_ADD_SCENES = "add_scenes"
NEXT_CREATE_BOARD = "create_board"
NEXT_APPROVE_PROMPTS = "approve_image_prompts"
NEXT_REAPPROVE_STALE = "reapprove_stale_prompts"
NEXT_CONFIRM_ANCHOR = "confirm_setting_anchor"
NEXT_CHECK_PROJECT_DATA = "check_project_data"
NEXT_RETRY_JOBS = "retry_failed_jobs"
NEXT_AWAIT_MEDIA = "await_media"
NEXT_READY = "ready"


def _image_prompts_table_present(storage: Any) -> bool:
    """DDL-free existence check for the image-prompts table (read-only).

    ``get_storyboard_image_prompt`` runs ``CREATE TABLE IF NOT EXISTS`` as
    a side effect, which would materialize the table on databases that
    predate it. A ``mode=ro`` URI connection can never create anything, so
    when the table is absent every shot honestly reports ``missing`` and no
    schema change occurs. Any lookup failure fails open to the historical
    behavior (the resolver path) rather than inventing a verdict.
    """
    try:
        from app.data.db_guard import open_db_readonly

        db_path = getattr(storage, "db_path", None)
        if db_path is None:
            return True
        conn = open_db_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'storyboard_image_prompts'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return True


# Failure types that mean the anchor could not be evaluated at all (missing
# project/scene record), as opposed to a gate that evaluated and failed.
# ``reference_validation._failure`` reports these in ``exc.metadata``.
_UNEVALUATABLE_FAILURES = frozenset({"project_not_found", "unknown_scene"})

ANCHOR_SET = "set"
ANCHOR_BLOCKED = "blocked"
ANCHOR_UNKNOWN = "unknown"


def _anchor_failure_kind(exc: BaseException) -> str:
    """Classify an anchor-resolution failure as evaluatable or not.

    Returns :data:`ANCHOR_UNKNOWN` when the project/scene record itself is
    unresolvable (nothing was judged), else :data:`ANCHOR_BLOCKED`.
    """
    metadata = getattr(exc, "metadata", None)
    failure_type = metadata.get("failure_type") if isinstance(metadata, dict) else None
    if failure_type in _UNEVALUATABLE_FAILURES:
        return ANCHOR_UNKNOWN
    return ANCHOR_BLOCKED


def _shot_sort_key(shot: Any) -> tuple[int, str]:
    try:
        number = int(getattr(shot, "shot_number", 0) or 0)
    except (TypeError, ValueError):
        number = 0
    return (number, str(getattr(shot, "shot_id", "") or ""))


def _latest_job_for_shot(jobs: list[Any], shot_id: str) -> Any | None:
    matches = [job for job in jobs if str(getattr(job, "shot_id", "") or "") == shot_id]
    if not matches:
        return None
    def _created(job: Any) -> str:
        return str(getattr(job, "created_at", "") or "")
    matches.sort(key=_created)
    return matches[-1]


def _job_output_url(job: Any) -> str:
    payload = getattr(job, "output_payload", None)
    if payload is not None:
        asset_url = getattr(payload, "asset_url", None)
        if asset_url:
            return str(asset_url)
    for attr in ("output_url", "output_uri", "video_url"):
        value = getattr(job, attr, None)
        if value:
            return str(value)
    try:
        raw = job.get("output_payload", {}) if isinstance(job, dict) else {}
        if isinstance(raw, dict) and raw.get("asset_url"):
            return str(raw["asset_url"])
    except Exception:
        pass
    return ""


# ── Authored narrative fields ──────────────────────────────────────────
#
# The aggregate carries a shot's purpose and motif tags through to the Desk,
# but it never invents them. Every helper below returns ``None`` when the
# record holds nothing authored, so an untagged shot stays honestly empty
# instead of inheriting a synthetic default.


def _authored_text(value: Any) -> str | None:
    """A non-empty, whitespace-normalized string, or ``None``.

    Only a string counts. Lists, dicts, and numeric ids are never coerced
    into prose — a structured ``intent`` object is not an authored sentence.
    """
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    return text or None


def _authored_refs(value: Any) -> str | None:
    """Join motif tags with ``", "``, preserving order and dropping repeats.

    Accepts a string reference or a list of tags. Empty input, blank entries,
    and non-tag values resolve to ``None``.
    """
    if isinstance(value, str):
        return _authored_text(value)
    if not isinstance(value, (list, tuple)):
        return None
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _authored_text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(text)
    return ", ".join(tags) or None


def _shot_intent_text(shot: Any) -> str | None:
    """The shot's stored rationale, in authored-first order.

    ``intent.purpose`` is a camera label (``close_up``) and
    ``intent.narrative_function`` is scene text, so neither is a shot purpose
    here. Only rationale fields carry the why.
    """
    intent = getattr(shot, "intent", None)
    metadata = getattr(shot, "metadata", None)
    candidates: list[Any] = []
    if isinstance(metadata, dict):
        candidates.extend([metadata.get("intent_rationale"), metadata.get("shot_intent")])
    if intent is not None:
        candidates.append(getattr(intent, "rationale", None))
    candidates.append(getattr(shot, "rationale", None))
    for candidate in candidates:
        text = _authored_text(candidate)
        if text:
            return text
    return None


def _shot_motif_ref(shot: Any) -> str | None:
    """Motif tags authored on the shot: intent obligations, then continuity."""
    intent = getattr(shot, "intent", None)
    continuity = getattr(shot, "continuity_plan", None)
    metadata = getattr(shot, "metadata", None)
    candidates: list[Any] = []
    if intent is not None:
        candidates.append(getattr(intent, "motif_obligations", None))
    if continuity is not None:
        candidates.append(getattr(continuity, "motif_continuity", None))
    if isinstance(metadata, dict):
        candidates.extend([metadata.get("motif_ref"), metadata.get("motifs")])
    for candidate in candidates:
        refs = _authored_refs(candidate)
        if refs:
            return refs
    return None


def _scene_motif_refs(storage: Any, project_id: str) -> dict[str, str]:
    """Scene-level motif tags from the project's cinematic memory.

    These are the same visual tags the motif-threads read uses, so the Desk
    reports the motif vocabulary the continuity panel already shows. A failed
    read leaves every scene unauthored rather than inventing tags.
    """
    try:
        memories = storage.list_cinematic_memory_for_project(project_id) or []
    except Exception:
        return {}
    collected: dict[str, list[str]] = {}
    for memory in memories:
        metadata = getattr(memory, "metadata", None)
        scene_id = ""
        if isinstance(metadata, dict):
            scene_id = str(metadata.get("scene_id") or "").strip()
        if not scene_id:
            continue
        tags = getattr(memory, "visual_tags", None)
        if not isinstance(tags, (list, tuple)):
            continue
        bucket = collected.setdefault(scene_id, [])
        for tag in tags:
            text = _authored_text(tag)
            if text and text not in bucket:
                bucket.append(text)
    return {scene_id: ", ".join(tags) for scene_id, tags in collected.items() if tags}


def _scene_narrative(entry: dict[str, Any], motif_refs: dict[str, str], scene_id: str) -> dict[str, Any]:
    """Scene-level ``shot_intent`` / ``motif_ref``, or ``None`` when unauthored."""
    shot_intent = _authored_text(entry.get("shot_intent")) or _authored_text(entry.get("intent"))
    motif_ref = (
        _authored_refs(entry.get("motif_ref"))
        or _authored_refs(entry.get("motifs"))
        or _authored_refs(entry.get("visual_tags"))
        or motif_refs.get(scene_id)
    )
    return {"shot_intent": shot_intent, "motif_ref": motif_ref}


def _summarize(
    *,
    project_id: str,
    storage: Any,
    prompt_service: StoryboardImagePromptService,
    reference_service: ReferenceAssetService,
) -> dict[str, Any]:
    project = project_persistence_service.load_readonly_existing(project_id)
    if project is None:
        raise LookupError(f"Project {project_id} not found")
    summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
    raw_scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    scenes_payload: list[dict[str, Any]] = []
    # One read for the whole board: scene-level motif tags keyed by scene_id.
    scene_motif_refs = _scene_motif_refs(storage, project_id)

    for entry in raw_scenes:
        if not isinstance(entry, dict):
            continue
        scene_id = str(entry.get("scene_id") or "").strip()
        if not scene_id:
            continue
        scene_name = str(entry.get("scene_name") or entry.get("heading") or scene_id)
        approval = entry.get("approval") if isinstance(entry.get("approval"), dict) else {}
        approval_status = str(approval.get("status") or entry.get("status") or "draft")

        blueprint = storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None:
            scenes_payload.append(
                {
                    "scene_id": scene_id,
                    "scene_name": scene_name,
                    "approval_status": approval_status,
                    "board_state": "missing_board",
                    "shots": [],
                    "next_action": NEXT_CREATE_BOARD,
                    "blockers": ["No storyboard board exists for this scene yet."],
                    **_scene_narrative(entry, scene_motif_refs, scene_id),
                }
            )
            continue
        version_id = getattr(blueprint, "current_version_id", None)
        try:
            shots = storage.list_storyboard_shots(blueprint.blueprint_id, version_id) if version_id else []
        except Exception:
            shots = []
        shots = sorted(shots or [], key=_shot_sort_key)

        # Setting-anchor state: single read-only resolution per scene. The
        # already-loaded scene record is injected (as prepare_scene_batch
        # does) so evaluation never depends on the global project store;
        # whatever store the board itself read is sufficient.
        try:
            from app.services.reference_validation import resolve_scene_reference_requirements

            requirements = resolve_scene_reference_requirements(
                project_id=project_id,
                scene_id=scene_id,
                storage=storage,
                scene=entry,
            )
            anchor_state = ANCHOR_SET
            anchor_reason: str | None = None
            _ = requirements
        except Exception as exc:
            anchor_state = _anchor_failure_kind(exc)
            if anchor_state == ANCHOR_UNKNOWN:
                anchor_reason = "Project data is unavailable for anchor evaluation."
            else:
                anchor_reason = str(exc)[:300] or "Setting anchor is not confirmed."

        # Confirmation display state: read-only revalidation, never writes.
        try:
            confirmations = reference_service.list_scene_confirmations(project_id, scene_id)
            confirm_by_shot = {
                str(item.get("shot_id") or ""): str(item.get("status") or "missing")
                for item in (confirmations.get("confirmations") or [])
                if isinstance(item, dict)
            }
        except Exception:
            confirm_by_shot = {}

        try:
            jobs = storage.list_jobs(project_id, limit=500) or []
        except Exception:
            jobs = []

        prompts_table_present = _image_prompts_table_present(storage)

        shot_rows: list[dict[str, Any]] = []
        scene_blockers: list[str] = []
        has_d4_hard_blocker = False
        has_stale = False
        for shot in shots:
            shot_id = str(getattr(shot, "shot_id", "") or "")
            storyboard_shot_id = str(getattr(shot, "storyboard_shot_id", "") or "")
            if not prompts_table_present:
                # No prompt row can exist: report missing without touching
                # the resolver (which would lazily CREATE the table).
                d4_state, d4_ready = "missing", False
                d4_message = "No Runway image prompt yet."
                d6_state, d6_ready = "missing", False
                d6_message = "No Runway image prompt yet."
            else:
                # D4: pure status derivation, no derive/edit/approve.
                try:
                    d4 = prompt_service.status_for_shot(shot)
                    d4_state = str(d4.get("state") or "unapproved")
                    d4_ready = bool(d4.get("render_ready"))
                    d4_message = str(d4.get("message") or "")
                except Exception as exc:
                    d4_state = "unresolvable"
                    d4_ready = False
                    d4_message = str(exc)[:300]
                # D6: existing pure resolver; fail-closed verdict only.
                try:
                    prompt_service.resolve_provider_send_text(shot)
                    d6_state = "ready"
                    d6_ready = True
                    d6_message = ""
                except StateError as exc:
                    metadata = exc.metadata if isinstance(exc.metadata, dict) else {}
                    d6_state = str(metadata.get("condition") or "unapproved")
                    d6_ready = False
                    d6_message = str(exc.message or "")[:300]
                except Exception as exc:
                    d6_state = "unresolvable"
                    d6_ready = False
                    d6_message = str(exc)[:300]

            status_value = getattr(getattr(shot, "status", ""), "value", getattr(shot, "status", ""))
            contract = getattr(shot, "render_contract", None)
            readiness = str(getattr(contract, "render_readiness", "") or "") if contract is not None else ""
            approval_state = str(status_value or readiness or "draft")

            job = _latest_job_for_shot(list(jobs or []), shot_id)
            if job is None:
                job_status: str | None = None
                job_id: str | None = None
                has_media = False
            else:
                job_status = str(getattr(job, "status", "") or "")
                job_id = str(getattr(job, "id", "") or "")
                has_media = job_status == "complete" and bool(_job_output_url(job))

            blockers: list[str] = []
            if not d4_ready:
                blockers.append(f"D4 image prompt {d4_state}: {d4_message}" if d4_message else f"D4 image prompt {d4_state}.")
                if d4_state == "stale":
                    has_stale = True
                else:
                    has_d4_hard_blocker = True
            if not d6_ready:
                blockers.append(f"Send-text gate {d6_state}." if not d6_message else f"Send-text gate {d6_state}: {d6_message}")
            if approval_state.lower() not in {"approved", "ready"} and d4_ready:
                blockers.append(f"Shot approval is {approval_state}.")
            if job_status == "failed":
                blockers.append("Latest render job failed.")
            elif not has_media:
                blockers.append("No completed media with a saved URL.")
            scene_blockers.extend([f"{shot_id}: {item}" for item in blockers])

            # list_storyboard_shots selects every storyboard_shots column, so
            # intent_json, continuity_plan_json, rationale, and metadata are
            # already on the row object; the narrative fields read from those.
            shot_rows.append(
                {
                    "shot_id": shot_id,
                    "shot_number": getattr(shot, "shot_number", None),
                    "storyboard_shot_id": storyboard_shot_id,
                    "d4_state": d4_state,
                    "d4_ready": d4_ready,
                    "d6_state": d6_state,
                    "d6_ready": d6_ready,
                    "setting_anchor": anchor_state,
                    "approval_state": approval_state,
                    "latest_job_status": job_status,
                    "latest_job_id": job_id,
                    "has_media": has_media,
                    "binding_confirmation": confirm_by_shot.get(shot_id, "missing"),
                    "blockers": blockers,
                    "shot_intent": _shot_intent_text(shot),
                    "motif_ref": _shot_motif_ref(shot),
                }
            )

        if not shot_rows:
            next_action = NEXT_CREATE_BOARD
            scene_blockers.append("Board exists but has no shots.")
        elif has_d4_hard_blocker:
            next_action = NEXT_APPROVE_PROMPTS
        elif has_stale:
            next_action = NEXT_REAPPROVE_STALE
        elif anchor_state == ANCHOR_UNKNOWN:
            next_action = NEXT_CHECK_PROJECT_DATA
            if anchor_reason:
                scene_blockers.append(f"Setting anchor: {anchor_reason}")
        elif anchor_state == "blocked":
            next_action = NEXT_CONFIRM_ANCHOR
            if anchor_reason:
                scene_blockers.append(f"Setting anchor: {anchor_reason}")
        elif any(row["latest_job_status"] == "failed" for row in shot_rows):
            next_action = NEXT_RETRY_JOBS
        elif any(not row["has_media"] for row in shot_rows):
            next_action = NEXT_AWAIT_MEDIA
        else:
            next_action = NEXT_READY

        ready_count = sum(1 for row in shot_rows if row["d4_ready"] and row["d6_ready"] and row["has_media"])
        scenes_payload.append(
            {
                "scene_id": scene_id,
                "scene_name": scene_name,
                "approval_status": approval_status,
                "board_state": "ready" if next_action == NEXT_READY else "blocked",
                "shot_count": len(shot_rows),
                "ready_shot_count": ready_count,
                "shots": shot_rows,
                "next_action": next_action,
                "blockers": scene_blockers,
                **_scene_narrative(entry, scene_motif_refs, scene_id),
            }
        )

    return {
        "project_id": project_id,
        "scene_count": len(scenes_payload),
        "scenes": scenes_payload,
        "next_action": NEXT_ADD_SCENES if not scenes_payload else None,
    }


class DeskGateSummaryService:
    """Read-only aggregate for the Production Desk board."""

    def get_summary(self, project_id: str) -> dict[str, Any]:
        started = perf_counter()
        cleaned = str(project_id or "").strip()
        if not cleaned:
            raise ValueError("project_id is required")
        storage = get_storage("sqlite")
        # Per-call instances bound to one shared store: no global mutation,
        # no writes, and test monkeypatches of get_storage keep working.
        prompt_service = StoryboardImagePromptService(storage=storage)
        reference_service = ReferenceAssetService(storage=storage)
        try:
            result = _summarize(
                project_id=cleaned,
                storage=storage,
                prompt_service=prompt_service,
                reference_service=reference_service,
            )
        except LookupError:
            raise
        except ValueError:
            raise
        except Exception as exc:
            from app.services.stability import PersistenceError

            raise PersistenceError(
                f"Desk gate summary lookup failed: {exc}",
                stage="desk_gate_summary",
            ) from exc
        logger.info(
            "project_id=%s job_id=%s provider=%s stage=%s duration_ms=%d",
            cleaned,
            f"scenes={len(result.get('scenes') or [])}",
            "none",
            "desk_gate_summary",
            int((perf_counter() - started) * 1000),
        )
        return result


desk_gate_summary_service = DeskGateSummaryService()
