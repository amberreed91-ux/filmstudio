"""
Final Export Routes

POST /api/f51/studio/projects/{project_id}/export          — trigger export with options
GET  /api/f51/studio/projects/{project_id}/export/status   — export job status
GET  /api/f51/studio/projects/{project_id}/export/download — stream final file
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.export_service import ExportOptions

logger = logging.getLogger("export-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["export"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service():
    from app.services.export_service import final_export_service
    return final_export_service


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/export")
async def trigger_export(
    project_id: str,
    options: ExportOptions = ExportOptions(),
) -> Dict[str, Any]:
    """
    Trigger a final export for the project.

    Takes the stitched MP4, optionally prepends a title card and appends an
    end card, scales to the requested resolution, encodes at the chosen
    quality, and embeds MP4 metadata (title, director, year).

    Export is ADDITIVE — the stitched source is never modified.
    Returns immediately; poll /export/status for progress.
    """
    service = _get_service()

    # If a job is already running, return it
    existing = service.get_job(project_id)
    if existing and existing.get("status") in ("pending", "running"):
        logger.info("EXPORT_ALREADY_RUNNING | project=%s", project_id)
        return {
            "job": existing,
            "advisory": "An export is already in progress for this project.",
        }

    logger.info(
        "EXPORT_START | project=%s | resolution=%s | format=%s | quality=%s | mock=%s",
        project_id,
        options.resolution,
        options.format,
        options.quality,
        service.capabilities()["mock_mode"],
    )

    try:
        job = await service.start_export(project_id, options)
        return {
            "job": job,
            "advisory": job.get("advisory", "Export started."),
        }
    except Exception as exc:
        logger.error("EXPORT_TRIGGER_FAILED | project=%s | %s", project_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to start export: {exc}") from exc


@router.get("/projects/{project_id}/export/status")
async def get_export_status(project_id: str) -> Dict[str, Any]:
    """
    Return current export job status and progress.

    status: pending | running | complete | failed
    progress: 0-100
    """
    service = _get_service()
    job = service.get_job(project_id)

    if not job:
        return {
            "status": "not_started",
            "progress": 0,
            "advisory": "No export job found. POST /export to begin.",
            "mock_mode": service.capabilities()["mock_mode"],
        }

    return {
        **job,
        "mock_mode": service.capabilities()["mock_mode"],
    }


@router.get("/projects/{project_id}/export/download")
async def download_export(project_id: str) -> Any:
    """
    Stream the final exported film for download.

    Returns 404 if export has not been run.
    Returns 202 if still in progress.
    Returns 500 if export failed.
    """
    service = _get_service()
    job = service.get_job(project_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="No export job found. POST /export to begin.",
        )

    status = job.get("status")

    if status in ("pending", "running"):
        raise HTTPException(
            status_code=202,
            detail=f"Export in progress ({job.get('progress', 0)}%). Check back soon.",
        )

    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {job.get('error', 'unknown error')}",
        )

    output_path = job.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="Output file path not recorded.")

    p = Path(output_path)
    if not p.exists():
        # Return URL for client-side download (mock mode or remote)
        output_url = job.get("output_url")
        if output_url:
            return {
                "output_url": output_url,
                "download_url": output_url,
                "mock_mode": service.capabilities()["mock_mode"],
                "advisory": "File served via static URL.",
            }
        raise HTTPException(status_code=404, detail="Export file not found on disk.")

    ext = p.suffix.lstrip(".")
    media_type = "video/mp4" if ext == "mp4" else "video/quicktime"
    filename = f"{project_id}_export.{ext}"

    return FileResponse(
        path=str(p),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
