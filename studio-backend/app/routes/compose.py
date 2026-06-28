import logging

from fastapi import APIRouter, HTTPException

from app.services.compose_service import compose_scene, get_scene_composition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects")


@router.post("/{project_id}/scenes/{scene_id}/compose")
async def compose_scene_endpoint(project_id: str, scene_id: str):
    """Compose all completed shots for a scene into a single video using FFmpeg."""
    try:
        result = await compose_scene(project_id, scene_id)
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
        raise HTTPException(status_code=404, detail="No composition found for this scene")
    return result
