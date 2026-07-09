import logging

from fastapi import APIRouter, Body, HTTPException

from app.services.compose_service import compose_scene, compose_scene_with_audio, get_scene_composition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects")


@router.post("/{project_id}/scenes/{scene_id}/compose")
async def compose_scene_endpoint(
    project_id: str,
    scene_id: str,
    use_audio_director: bool = Body(False),
):
    """Compose all completed shots for a scene into a single video using FFmpeg."""
    try:
        if use_audio_director:
            from app.services.audio_director_service import generate_scene_audio_brief
            brief = await generate_scene_audio_brief(project_id, scene_id, None)
            result = await compose_scene_with_audio(
                project_id, scene_id, audio_brief=brief.model_dump()
            )
        else:
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
