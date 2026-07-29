import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException

from app.services.compose_service import compose_scene_for_delivery, get_scene_composition
from app.services.project_persistence_service import project_persistence_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects")


def _load_project(project_id: str) -> dict | None:
    return project_persistence_service.load(project_id)


def _composition_from_scene_pipeline_assembly(project_id: str, scene_id: str) -> dict | None:
    project = _load_project(project_id)
    if not project:
        return None
    summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
    rows = summary.get("scene_pipeline_assemblies")
    if not isinstance(rows, list):
        return None

    matches: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("scene_id") or "") != scene_id:
            continue
        if row.get("status") not in {"complete", "completed", "existing"}:
            continue
        if not str(row.get("output_url") or "").strip():
            continue
        matches.append(row)
    if not matches:
        return None

    matches.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    assembly = matches[0]
    updated_at = str(assembly.get("updated_at") or datetime.now(timezone.utc).isoformat())
    return {
        "id": str(assembly.get("assembly_id") or f"{project_id}_{scene_id}_scene_pipeline"),
        "project_id": project_id,
        "scene_id": scene_id,
        "composed_url": str(assembly.get("output_url") or ""),
        "shot_count": int(assembly.get("clip_count") or len(assembly.get("shot_ids") or []) or 1),
        "duration_seconds": assembly.get("duration_seconds"),
        "created_at": updated_at,
        "updated_at": updated_at,
    }


@router.post("/{project_id}/scenes/{scene_id}/compose")
async def compose_scene_endpoint(
    project_id: str,
    scene_id: str,
    use_audio_director: bool = Body(False),
):
    """Compose all completed shots for a scene into a single video using FFmpeg."""
    try:
        result = await compose_scene_for_delivery(project_id, scene_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Compose failed for %s / %s: %s", project_id, scene_id, e)
        raise HTTPException(status_code=500, detail=f"Compose failed: {str(e)}")


@router.get("/{project_id}/scenes/{scene_id}/composition")
async def get_composition_endpoint(project_id: str, scene_id: str):
    """Get the composed video for a scene if it exists."""
    result = await get_scene_composition(project_id, scene_id)
    if not result:
        result = _composition_from_scene_pipeline_assembly(project_id, scene_id)
    if not result:
        raise HTTPException(status_code=404, detail="No composition found for this scene")
    return result
