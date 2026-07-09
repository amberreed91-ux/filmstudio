"""
Stitching Routes

POST /api/f51/studio/projects/{project_id}/stitch          — trigger stitch
GET  /api/f51/studio/projects/{project_id}/stitch/status   — job status + progress
GET  /api/f51/studio/projects/{project_id}/stitch/download — final MP4 URL
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("stitching-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["stitching"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service():
    from app.services.ffmpeg_stitching_service import ffmpeg_stitching_service
    return ffmpeg_stitching_service


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/stitch")
async def trigger_stitch(project_id: str) -> Dict[str, Any]:
    """
    Trigger a full film stitch for the project.

    Collects all approved scenes in film_cut order, mixes audio tracks
    (dialogue 100%, score 40%, ambient 60%), applies transition_advisory
    transitions, and outputs final MP4 to outputs/final_films/{project_id}_final.mp4.

    Returns immediately with job info — poll /stitch/status for progress.
    """
    service = _get_service()

    # If a job is already running, return it
    existing = service.get_job(project_id)
    if existing and existing.get("status") in ("pending", "running"):
        logger.info("STITCH_ALREADY_RUNNING | project=%s", project_id)
        return {
            "job": existing,
            "advisory": "A stitch is already in progress for this project.",
        }

    logger.info("STITCH_START | project=%s | ffmpeg=%s", project_id, service.capabilities()["ffmpeg_available"])

    try:
        job = await service.start_stitch(project_id)
        return {
            "job": job,
            "advisory": job.get("advisory", "Stitching started."),
        }
    except Exception as exc:
        logger.error("STITCH_TRIGGER_FAILED | project=%s | %s", project_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to start stitch: {exc}") from exc


@router.get("/projects/{project_id}/stitch/status")
async def get_stitch_status(project_id: str) -> Dict[str, Any]:
    """
    Return current stitching job status and progress.

    status: pending | running | complete | failed
    progress: 0-100
    """
    service = _get_service()
    job = service.get_job(project_id)

    if not job:
        return {
            "status": "not_started",
            "progress": 0,
            "advisory": "No stitch job found for this project. POST /stitch to begin.",
            "mock_mode": service.capabilities()["mock_mode"],
        }

    return {
        **job,
        "mock_mode": service.capabilities()["mock_mode"],
    }


@router.get("/projects/{project_id}/stitch/download")
async def download_stitched_film(project_id: str) -> Any:
    """
    Stream the final stitched MP4 for download.

    Returns 404 if stitching is not complete.
    Returns 202 if still in progress.
    """
    service = _get_service()
    job = service.get_job(project_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="No stitch job found. POST /stitch to begin.",
        )

    status = job.get("status")

    if status in ("pending", "running"):
        raise HTTPException(
            status_code=202,
            detail=f"Stitching in progress ({job.get('progress', 0)}%). Check back soon.",
        )

    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Stitching failed: {job.get('error', 'unknown error')}",
        )

    output_path = job.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="Output file path not recorded.")

    from pathlib import Path
    p = Path(output_path)
    if not p.exists():
        # Return the URL for client-side download (mock mode or remote)
        output_url = job.get("output_url")
        if output_url:
            return {
                "output_url": output_url,
                "download_url": output_url,
                "mock_mode": service.capabilities()["mock_mode"],
                "advisory": "File served via static URL.",
            }
        raise HTTPException(status_code=404, detail="Output file not found on disk.")

    return FileResponse(
        path=str(p),
        media_type="video/mp4",
        filename=f"{project_id}_final.mp4",
        headers={"Content-Disposition": f'attachment; filename="{project_id}_final.mp4"'},
    )
