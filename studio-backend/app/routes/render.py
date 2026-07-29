from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timezone
import json
import logging
import shutil

logger = logging.getLogger(__name__)

from app.services import render_service
from app.services.render_maintenance_service import render_maintenance_service
from app.services.project_store import project_store
from app.models import ProviderConfig, RenderJobModel
from pydantic import BaseModel, Field
from typing import Any, Dict, List

router = APIRouter()


# ── Batch request model ───────────────────────────────────────────────────────

class RenderBatchRequest(BaseModel):
    shots: List[Dict[str, Any]] = Field(default_factory=list)
    provider: Optional[str] = None


# ── Seed locking models ───────────────────────────────────────────────────────

class ShotSeedPayload(BaseModel):
    """Seed lock/unlock payload: provide seed (integer) or null to clear."""
    seed: Optional[int] = None


class AdherenceRetryRequest(BaseModel):
    """Explicit active adherence retry request."""
    max_attempts: int = Field(default=3, ge=1, le=5)
    submission_strategy: str = "combined_reorder_and_fresh_seeds"


class QueueRenderJobRequest(BaseModel):
    priority: int = Field(default=50, ge=0, le=100)
    idempotency_key: str | None = None


def _parse_query_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return fallback
        try:
            return json.loads(clean)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON query value: {exc.msg}") from exc
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _job_payload(job: Any) -> dict[str, Any]:
    payload = job.model_dump() if hasattr(job, "model_dump") else dict(job or {})
    output_payload = _as_dict(payload.get("output_payload"))
    output_url = payload.get("output_url") or output_payload.get("asset_url")
    preview_url = payload.get("preview_url") or output_payload.get("thumbnail_url") or output_url
    payload["job_id"] = payload.get("id")
    payload["output_url"] = output_url
    payload["preview_url"] = preview_url
    payload["zero_touch_status"] = _zero_touch_status_summary(payload)
    return payload


def _zero_touch_status_summary(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = _as_dict(payload.get("metadata"))
    zero_touch = _as_dict(metadata.get("zero_touch_pipeline"))
    phases = zero_touch.get("phases") if isinstance(zero_touch.get("phases"), list) else []
    clean_phases = [row for row in phases if isinstance(row, dict)]
    phase_statuses = {
        str(row.get("phase")): str(row.get("status") or "")
        for row in clean_phases
        if row.get("phase")
    }
    active_phase = ""
    for row in clean_phases:
        status = str(row.get("status") or "")
        if status in {"running", "pending", "needs_review", "failed"}:
            active_phase = str(row.get("phase") or "")
            break

    provider_selection = _as_dict(zero_touch.get("provider_selection"))
    references = zero_touch.get("references") if isinstance(zero_touch.get("references"), list) else []
    reference_rows = [row for row in references if isinstance(row, dict)]
    staging = _as_dict(zero_touch.get("staging"))
    retry_debug = _as_dict(zero_touch.get("retry"))
    retry_cascade = _as_dict(metadata.get("adherence_retry_cascade"))
    jobs_submitted = retry_cascade.get("jobs_submitted") if isinstance(retry_cascade.get("jobs_submitted"), list) else []
    adherence_review = _as_dict(metadata.get("adherence_review"))
    prompt_contradictions = metadata.get("prompt_contradictions") if isinstance(metadata.get("prompt_contradictions"), list) else []
    environment_context = _as_dict(metadata.get("environment_continuity_context"))
    environment_warnings = (
        metadata.get("environment_continuity_warnings")
        if isinstance(metadata.get("environment_continuity_warnings"), list)
        else []
    )
    if not environment_warnings:
        environment_warnings = (
            environment_context.get("warnings")
            if isinstance(environment_context.get("warnings"), list)
            else []
        )
    environment_recognizability = _as_dict(environment_context.get("recognizability"))
    environment_reference_explanations = (
        environment_context.get("reference_explanations")
        if isinstance(environment_context.get("reference_explanations"), list)
        else []
    )
    identity_warnings = (
        metadata.get("character_identity_warnings")
        if isinstance(metadata.get("character_identity_warnings"), list)
        else metadata.get("identity_conflict_warnings")
        if isinstance(metadata.get("identity_conflict_warnings"), list)
        else zero_touch.get("identity_conflict_warnings")
        if isinstance(zero_touch.get("identity_conflict_warnings"), list)
        else []
    )
    provider_failure = _as_dict(metadata.get("provider_failure"))

    output_url = payload.get("output_url")
    preview_url = payload.get("preview_url")
    status = str(payload.get("status") or "")
    adherence_verdict = str(adherence_review.get("verdict") or adherence_review.get("outcome") or "")
    retry_count = len(jobs_submitted)
    human_review_required = bool(
        status == "needs_review"
        or prompt_contradictions
        or identity_warnings
        or environment_warnings
        or environment_recognizability.get("status") == "needs_review"
        or adherence_verdict in {"needs_review", "manual_review", "fail"}
    )

    return {
        "status": status,
        "active_phase": active_phase,
        "phases": clean_phases,
        "phase_statuses": phase_statuses,
        "provider": provider_selection.get("provider") or payload.get("provider"),
        "model": provider_selection.get("model") or "",
        "provider_selection_reason": provider_selection.get("reason") or "",
        "staging_applied": bool(staging.get("applied")),
        "staging_characters": staging.get("characters") if isinstance(staging.get("characters"), list) else [],
        "references_applied": any(bool(row.get("injected_into_request")) for row in reference_rows),
        "reference_count": len(reference_rows),
        "references": reference_rows,
        "adherence": {
            "verdict": adherence_verdict,
            "passed": adherence_verdict == "pass",
            "failed_slots": adherence_review.get("failed_slots") if isinstance(adherence_review.get("failed_slots"), list) else [],
            "note": adherence_review.get("advisory_note") or "",
        },
        "retry": {
            "occurred": retry_count > 0,
            "count": retry_count,
            "max_attempts": retry_cascade.get("max_retries") or retry_debug.get("max_attempts") or 0,
            "jobs_submitted": jobs_submitted,
        },
        "provider_failure": provider_failure,
        "prompt_contradictions": prompt_contradictions,
        "character_identity_warnings": identity_warnings,
        "environment_continuity": {
            "location_id": environment_context.get("location_id") or "",
            "warnings": environment_warnings,
            "human_review_required": bool(
                environment_warnings
                or environment_recognizability.get("status") == "needs_review"
            ),
            "recognizability": environment_recognizability,
            "reference_explanations": environment_reference_explanations,
        },
        "output_url": output_url,
        "preview_url": preview_url,
        "human_review_required": human_review_required,
    }


# Provider management
@router.get("/providers")
def list_providers():
    """List all available render providers with status"""
    return render_service.list_providers()


@router.get("/providers/{provider_id}")
def get_provider(provider_id: str):
    """Get provider configuration"""
    config = render_service.get_provider_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")
    return config


@router.post("/providers/{provider_id}/enable")
def enable_provider(provider_id: str):
    """Enable a provider"""
    config = render_service.get_provider_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")
    config.enabled = True
    return render_service.set_provider_config(config)


@router.post("/providers/{provider_id}/disable")
def disable_provider(provider_id: str):
    """Disable a provider"""
    config = render_service.get_provider_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")
    config.enabled = False
    return render_service.set_provider_config(config)


@router.post("/providers")
def configure_provider(config: ProviderConfig):
    """Update provider configuration"""
    return render_service.set_provider_config(config)


# Render jobs
@router.post("/jobs")
def create_render_job(
    project_id: str,
    shot_id: str,
    provider: Optional[str] = None,
    prompt: str = "",
    reference_assets: Optional[Any] = None,
    parameters: Optional[Any] = None,
    queue: bool = False,
    queue_priority: int = 50,
):
    """Create a new render job"""
    try:
        parsed_reference_assets = _parse_query_json(reference_assets, [])
        parsed_parameters = _parse_query_json(parameters, {})
        if not isinstance(parsed_reference_assets, list):
            raise HTTPException(status_code=400, detail="reference_assets must be a JSON array")
        if not isinstance(parsed_parameters, dict):
            raise HTTPException(status_code=400, detail="parameters must be a JSON object")
        job = render_service.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=parsed_reference_assets,
            parameters=parsed_parameters
        )
        storyboard_meta = parsed_parameters.get("storyboard") if isinstance(parsed_parameters, dict) else None
        if isinstance(storyboard_meta, dict):
            try:
                from app.services.storyboard_blueprint_service import storyboard_blueprint_service

                storyboard_shot_id = str(storyboard_meta.get("storyboard_shot_id") or "").strip()
                shot = storyboard_blueprint_service.get_storyboard_shot(storyboard_shot_id)
                if shot is not None:
                    storyboard_blueprint_service.link_render_job(
                        shot=shot,
                        render_job_id=job.id,
                        link_type=str(storyboard_meta.get("link_type") or "initial_render"),
                    )
            except Exception as exc:
                logger.debug("Storyboard render provenance link skipped for %s: %s", job.id, exc)
        payload = _job_payload(job)
        if queue:
            try:
                from app.services.production_queue_service import production_queue_service

                queue_item = production_queue_service.enqueue_existing_render_job(
                    job_id=job.id,
                    priority=max(0, min(int(queue_priority), 100)),
                    idempotency_key=f"render_route:{project_id}:{job.id}",
                )
                payload["production_queue_item"] = queue_item.model_dump()
            except Exception as exc:
                logger.warning("Render job queue attachment failed for %s: %s", job.id, exc)
                payload["production_queue_error"] = str(exc)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/queue")
def queue_existing_render_job(job_id: str, payload: QueueRenderJobRequest = QueueRenderJobRequest()):
    """Attach an existing render job to the durable production queue."""
    try:
        from app.services.production_queue_service import production_queue_service

        return production_queue_service.enqueue_existing_render_job(
            job_id=job_id,
            priority=payload.priority,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/jobs/{job_id}/submit")
async def submit_render_job(job_id: str):
    """Submit a render job to the provider"""
    job = await render_service.submit_job(job_id)
    return _job_payload(job)


@router.get("/jobs/{job_id}")
def get_render_job(job_id: str):
    """Get render job details"""
    job = render_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_payload(job)


@router.get("/jobs/{job_id}/status")
async def get_render_job_status(job_id: str):
    """Poll render job status"""
    job = await render_service.get_job_status(job_id)
    return _job_payload(job)


@router.delete("/jobs/{job_id}")
async def delete_render_job(job_id: str):
    """Delete a render job"""
    result = render_service.delete_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_render_job(job_id: str):
    """Cancel a render job"""
    result = await render_service.cancel_job(job_id)
    if not result:
        raise HTTPException(status_code=400, detail="Cannot cancel job in current state")
    return {"status": "cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_render_job(job_id: str):
    """Retry a failed render job"""
    job = await render_service.retry_job(job_id)
    return _job_payload(job)


@router.post("/jobs/{job_id}/adherence-retry")
async def retry_render_job_for_adherence(
    job_id: str,
    payload: AdherenceRetryRequest = AdherenceRetryRequest(),
):
    """Run the explicit prompt-adherence retry loop for a completed render."""
    job = render_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    parameters = job.input_payload.parameters if job.input_payload else {}
    slots = parameters.get("prompt_slots") if isinstance(parameters, dict) else None
    if not isinstance(slots, dict) or not slots:
        raise HTTPException(
            status_code=422,
            detail="Render job does not have structured prompt_slots for adherence retry",
        )

    from app.services.render_retry_service import render_retry_service

    return await render_retry_service.evaluate_and_select_best(
        shot_id=job.shot_id,
        project_id=job.project_id,
        original_slots={str(key): str(value or "") for key, value in slots.items()},
        max_attempts=payload.max_attempts,
        submission_strategy=payload.submission_strategy,
    )


@router.post("/jobs/{job_id}/reconcile")
async def reconcile_render_job(job_id: str):
    """Reconcile historical failed runway job against upstream task status."""
    try:
        job = await render_service.reconcile_completed_runway_task(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return job


@router.post("/jobs/{job_id}/refresh-url")
async def refresh_render_job_output_url(job_id: str):
    """Refresh a potentially expired hosted output URL for a render job."""
    output_url = await render_service.refresh_output_url(job_id)
    return {"output_url": output_url}


@router.get("/jobs/{job_id}/outputs")
async def get_render_job_outputs(job_id: str):
    """Get generated assets for a job"""
    return await render_service.get_job_outputs(job_id)


@router.get("/projects/{project_id}/shots/{shot_id}/recommended-duration")
def get_recommended_shot_duration(
    project_id: str,
    shot_id: str,
    pacing: Optional[str] = None,
):
    """Recommend a render duration for a shot based on its scene dialogue.

    Advisory-only: surfaces the number without changing any existing render
    behaviour. See ShotDurationEstimatorService for the estimation method.
    """
    from app.services.shot_duration_estimator_service import shot_duration_estimator_service
    try:
        return shot_duration_estimator_service.estimate_for_shot(
            project_id=project_id, shot_id=shot_id, pacing=pacing,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/jobs")
def list_render_jobs(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 50,
    paginated: bool = False,
):
    """List all render jobs, optionally filtered by project"""
    if paginated:
        try:
            page = render_maintenance_service.list_jobs_page(
                project_id=project_id,
                status=status,
                cursor=cursor,
                limit=limit,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return {
            **page,
            "items": [_job_payload(job) for job in page["items"]],
        }

    rows = []
    for job in render_service.list_jobs(project_id):
        rows.append(_job_payload(job))

    # Compatibility fallback for seeded demo/runtime rows that currently live in
    # project execution summaries but are not yet hydrated into canonical job rows.
    if project_id and not rows:
        project = project_store.get_project(project_id)
        execution_summary = project.get("execution_summary") if isinstance(project, dict) else None
        summary_jobs = execution_summary.get("one_button_render_jobs") if isinstance(execution_summary, dict) else None
        if isinstance(summary_jobs, list):
            for summary_job in summary_jobs:
                if not isinstance(summary_job, dict):
                    continue
                output_url = summary_job.get("output_url") or ""
                preview_url = summary_job.get("preview_url") or output_url
                rows.append(
                    {
                        "job_id": summary_job.get("job_id"),
                        "id": summary_job.get("job_id"),
                        "project_id": project_id,
                        "shot_id": summary_job.get("shot_id"),
                        "provider": summary_job.get("provider") or "runway",
                        "provider_job_id": summary_job.get("task_id"),
                        "status": summary_job.get("status") or "complete",
                        "progress": 100,
                        "output_url": output_url,
                        "preview_url": preview_url,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
    return rows


@router.get("/diagnostics")
def get_render_diagnostics(project_id: Optional[str] = None):
    """Internal diagnostics snapshot for DevTools."""
    jobs = render_service.list_jobs(project_id)
    status_counts: dict[str, int] = {}
    for job in jobs:
        status_counts[job.status] = status_counts.get(job.status, 0) + 1

    storage_diagnostics = render_maintenance_service.storage_diagnostics()

    provider_status = render_service.list_providers()
    provider_snapshot = [
        {
            "provider_id": p.provider_id,
            "name": p.name,
            "status": p.status,
            "is_simulated": p.is_simulated,
            "active_jobs": p.active_jobs,
            "queued_jobs": p.queued_jobs,
        }
        for p in provider_status
    ]
    provider_available = {
        row["provider_id"]: row["status"] == "available"
        for row in provider_snapshot
    }

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id or "",
        "provider_status": provider_snapshot,
        "provider_availability": provider_available,
        "render_queue": {
            "total": len(jobs),
            "status_counts": status_counts,
            "recent_jobs": [job.model_dump() for job in jobs[:10]],
        },
        "hydration_state": {
            "in_memory_job_count": len(getattr(render_service, "_jobs", {})),
            "storage_initialized": storage_diagnostics["initialized"],
        },
        "persistence_health": {
            "status": storage_diagnostics["status"],
            "detail": storage_diagnostics["detail"],
            "db_path": storage_diagnostics["db_path"],
        },
        "environment": {
            "ffmpeg_available": bool(ffmpeg_path),
            "ffmpeg_path": ffmpeg_path or "",
            "ffprobe_available": bool(ffprobe_path),
            "ffprobe_path": ffprobe_path or "",
        },
    }


@router.post("/backfill-project-state")
def backfill_project_state_render_jobs():
    """Backfill canonical render_jobs rows from project_state_store.json."""
    try:
        return render_maintenance_service.backfill_project_state()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/recover-output-urls")
async def recover_render_output_urls():
    """Find and fix render jobs with status='complete' but no output URL.
    
    For simulated/local jobs: regenerate the placeholder URL immediately.
    For real provider jobs: set status to 'failed' since the URL is genuinely lost.
    """
    try:
        return render_maintenance_service.recover_output_urls()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ── Seed lock/unlock ──────────────────────────────────────────────────────────

@router.patch("/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}/seed")
def update_shot_seed(project_id: str, scene_id: str, shot_id: str, payload: ShotSeedPayload):
    """Lock or unlock a seed for a shot. Body: {"seed": integer or null}.
    
    - If seed is provided (non-null): sets that seed and locks it (seed_locked=true).
    - If seed is null: sets seed_locked=false (unlocks), keeps existing seed.
    - Returns the current shot seed state.
    """
    try:
        return render_maintenance_service.update_shot_seed(
            project_id,
            scene_id,
            shot_id,
            payload.seed,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
