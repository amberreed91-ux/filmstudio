from fastapi import APIRouter, HTTPException
from typing import Optional

from app.services import render_service
from app.models import ProviderConfig, RenderJobModel

router = APIRouter()


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


@router.get("/jobs/{job_id}/outputs")
async def get_render_job_outputs(job_id: str):
    """Get generated assets for a job"""
    return await render_service.get_job_outputs(job_id)


@router.get("/jobs")
def list_render_jobs(project_id: Optional[str] = None):
    """List all render jobs, optionally filtered by project"""
    return render_service.list_jobs(project_id)
