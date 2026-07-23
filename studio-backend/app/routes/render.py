from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timezone
import logging
import shutil

logger = logging.getLogger(__name__)

from app.services import render_service
from app.services import render as render_module
from app.services.render_job_backfill import backfill_render_jobs_from_project_state
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
    reference_assets: Optional[list[str]] = None,
    parameters: Optional[dict] = None
):
    """Create a new render job"""
    try:
        job = render_service.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        return job
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/submit")
async def submit_render_job(job_id: str):
    """Submit a render job to the provider"""
    job = await render_service.submit_job(job_id)
    return job


@router.get("/jobs/{job_id}")
def get_render_job(job_id: str):
    """Get render job details"""
    job = render_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/status")
async def get_render_job_status(job_id: str):
    """Poll render job status"""
    job = await render_service.get_job_status(job_id)
    return job


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
    return job


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
def list_render_jobs(project_id: Optional[str] = None):
    """List all render jobs, optionally filtered by project"""
    rows = []
    for job in render_service.list_jobs(project_id):
        payload = job.model_dump()
        output_payload = payload.get("output_payload") if isinstance(payload.get("output_payload"), dict) else {}
        output_url = payload.get("output_url") or output_payload.get("asset_url")
        preview_url = payload.get("preview_url") or output_payload.get("thumbnail_url")
        rows.append(
            {
                **payload,
                "job_id": payload.get("id"),
                "output_url": output_url,
                "preview_url": preview_url,
            }
        )

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

    storage_health = "uninitialized"
    storage_detail = "storage_not_set"
    if render_module._storage is not None:
        try:
            _ = render_module._storage.list_jobs(limit=1)
            storage_health = "ok"
            storage_detail = "query_ok"
        except Exception as exc:  # pragma: no cover - defensive
            storage_health = "degraded"
            storage_detail = str(exc)

    persistence_path = ""
    if render_module._storage is not None and hasattr(render_module._storage, "db_path"):
        persistence_path = str(getattr(render_module._storage, "db_path"))

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
            "storage_initialized": render_module._storage is not None,
        },
        "persistence_health": {
            "status": storage_health,
            "detail": storage_detail,
            "db_path": persistence_path,
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
    if render_module._storage is None:
        raise HTTPException(status_code=503, detail="Render job storage is not initialized")
    return backfill_render_jobs_from_project_state(
        storage=render_module._storage,
        render_service=render_service,
    )


@router.post("/recover-output-urls")
async def recover_render_output_urls():
    """Find and fix render jobs with status='complete' but no output URL.
    
    For simulated/local jobs: regenerate the placeholder URL immediately.
    For real provider jobs: set status to 'failed' since the URL is genuinely lost.
    """
    if render_module._storage is None:
        raise HTTPException(status_code=503, detail="Render job storage is not initialized")
    
    SIMULATED_PLACEHOLDER = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
    
    jobs = render_module._storage.list_jobs(limit=5000)
    recovered = 0
    demoted = 0
    skipped = 0
    
    for job in jobs:
        if job.status != "complete":
            continue
        
        has_url = (
            job.output_payload
            and isinstance(job.output_payload.asset_url, str)
            and job.output_payload.asset_url.strip()
        )
        if has_url:
            continue
        
        job_id = job.id
        is_simulated = job.provider in ("simulated", "local")
        
        if is_simulated:
            from app.models import RenderJobOutput
            job.output_payload = RenderJobOutput(
                asset_url=SIMULATED_PLACEHOLDER,
                thumbnail_url=None,
                metadata={"simulated": True, "provider": job.provider, "url": SIMULATED_PLACEHOLDER, "recovered": True},
            )
            job.error_message = None
            job.completed_at = job.completed_at or datetime.now(timezone.utc).isoformat()
            job.updated_at = datetime.now(timezone.utc).isoformat()
            render_module._storage.save_job(job)
            if job_id in render_service._jobs:
                render_service._jobs[job_id] = job
            recovered += 1
            logger.info("RENDER_URL_RECOVERED | job=%s | provider=%s", job_id, job.provider)
        else:
            job.status = "failed"
            job.error_message = "Job completed without output URL — demoted by recovery"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            render_module._storage.save_job(job)
            if job_id in render_service._jobs:
                render_service._jobs[job_id] = job
            demoted += 1
            logger.info("RENDER_URL_DEMOTED | job=%s | provider=%s", job_id, job.provider)
    
    return {
        "recovered": recovered,
        "demoted": demoted,
        "skipped": skipped,
        "total_checked": recovered + demoted + skipped,
    }


# ── Seed lock/unlock ──────────────────────────────────────────────────────────

@router.patch("/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}/seed")
def update_shot_seed(project_id: str, scene_id: str, shot_id: str, payload: ShotSeedPayload):
    """Lock or unlock a seed for a shot. Body: {"seed": integer or null}.
    
    - If seed is provided (non-null): sets that seed and locks it (seed_locked=true).
    - If seed is null: sets seed_locked=false (unlocks), keeps existing seed.
    - Returns the current shot seed state.
    """
    if render_module._storage is None:
        raise HTTPException(status_code=503, detail="Render storage not initialized")

    # Normalize shot_id: if caller passed just the short name, combine with scene_id
    # e.g. shot_id="shot_001", scene_id="scene_001" => "scene_001_shot_001"
    full_shot_id = shot_id
    if not shot_id.startswith(scene_id) and scene_id:
        full_shot_id = f"{scene_id}_{shot_id}"

    if payload.seed is not None:
        # Lock seed: set both seed and locked
        render_module._storage.save_shot_seed(project_id, full_shot_id, payload.seed, seed_locked=True)
        logger.info(
            "SEED_LOCKED | project=%s | shot=%s | seed=%d",
            project_id, full_shot_id, payload.seed,
        )
    else:
        # Unlock: keep existing seed (if any), just unlock
        existing = render_module._storage.get_shot_seed(project_id, full_shot_id)
        current_seed = existing["seed"] if existing and existing.get("seed") is not None else None
        render_module._storage.update_shot_seed_lock(project_id, full_shot_id, seed=current_seed, seed_locked=False)
        logger.info(
            "SEED_UNLOCKED | project=%s | shot=%s | seed=%s",
            project_id, full_shot_id, current_seed,
        )

    result = render_module._storage.get_shot_seed(project_id, full_shot_id)
    if not result:
        return {"project_id": project_id, "shot_id": full_shot_id, "seed": None, "seed_locked": False}
    return {
        "project_id": result["project_id"],
        "shot_id": result["shot_id"],
        "seed": result["seed"],
        "seed_locked": bool(result["seed_locked"]),
    }

