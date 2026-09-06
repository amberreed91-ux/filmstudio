from fastapi import APIRouter, Depends, HTTPException

from app.models.scene_direction import SaveSceneDirection, SceneDirection
from app.services.scene_direction_service import SceneDirectionService
from app.services.stability import StabilityError

router = APIRouter(prefix='/api/f51/studio/projects', tags=['scene-direction'])


def get_service() -> SceneDirectionService:
    return SceneDirectionService()


def http_error(exc: StabilityError) -> HTTPException:
    return HTTPException(status_code=422 if exc.error_type == 'validation_error' else 404 if 'not found' in exc.message.lower() else 409 if exc.error_type == 'state_error' else 503, detail=exc.to_dict())


@router.get('/{project_id}/scenes/{scene_id}/direction', response_model=SceneDirection)
async def get_direction(project_id: str, scene_id: str, service: SceneDirectionService = Depends(get_service)):
    try:
        return service.get(project_id, scene_id)
    except StabilityError as exc:
        raise http_error(exc) from exc


@router.put('/{project_id}/scenes/{scene_id}/direction', response_model=SceneDirection)
async def save_direction(project_id: str, scene_id: str, payload: SaveSceneDirection, service: SceneDirectionService = Depends(get_service)):
    try:
        return service.save(project_id, scene_id, payload)
    except StabilityError as exc:
        raise http_error(exc) from exc
