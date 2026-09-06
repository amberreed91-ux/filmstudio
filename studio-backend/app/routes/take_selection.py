from fastapi import APIRouter, Depends, HTTPException, Path

from app.models.take_selection import TakeChoiceRequest, SceneTakeChoices
from app.services.take_selection_service import TakeSelectionService
from app.services.stability import StabilityError

router = APIRouter(prefix="/api/f51/studio/projects")


def get_take_selection_service() -> TakeSelectionService:
    return TakeSelectionService()


@router.get("/{project_id}/scenes/{scene_id}/take-choices", response_model=SceneTakeChoices)
async def get_take_choices(project_id: str, scene_id: str, service: TakeSelectionService = Depends(get_take_selection_service)):
    return service.choices(project_id, scene_id)


@router.put("/{project_id}/scenes/{scene_id}/take-choices/{shot_number}", response_model=SceneTakeChoices)
async def choose_take(project_id: str, scene_id: str, payload: TakeChoiceRequest, shot_number: int = Path(ge=1), service: TakeSelectionService = Depends(get_take_selection_service)):
    try:
        return service.choose(project_id, scene_id, shot_number, payload.job_id)
    except StabilityError as exc:
        raise HTTPException(status_code=400 if exc.error_type == "validation_error" else 409 if exc.error_type == "state_error" else 500, detail=exc.to_dict()) from exc
