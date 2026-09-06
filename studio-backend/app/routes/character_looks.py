from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.models.character_look import CharacterLook, CharacterLookApprovalRequest, CharacterLookList, CharacterLookRevisionRequest, CharacterLookUploadResponse
from app.services.character_look_service import MAX_REFERENCE_BYTES, CharacterLookService, get_character_look_service
from app.services.stability import StabilityError
from app.models.character_look import CharacterCastingRequest
from app.services.character_casting_service import CharacterCastingService, get_character_casting_service

router = APIRouter(prefix="/api/f51/studio/projects", tags=["character-looks"])


@router.post("/{project_id}/characters/{character_id}/look/casting", response_model=CharacterLook, status_code=202)
async def generate_casting(project_id: str, character_id: str, payload: CharacterCastingRequest, background_tasks: BackgroundTasks, service: CharacterCastingService = Depends(get_character_casting_service)):
    try:
        look = service.start(project_id, character_id, payload)
        background_tasks.add_task(service.run, project_id, character_id, str(payload.request_id))
        return look
    except (LookupError, StabilityError) as exc:
        raise _http_error(exc) from exc


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(status_code=404, detail=str(error))
    assert isinstance(error, StabilityError)
    return HTTPException(status_code={"state_error": 409, "validation_error": 400}.get(error.error_type, 503), detail=error.to_dict())


@router.get("/{project_id}/character-looks", response_model=CharacterLookList)
async def list_looks(project_id: str, service: CharacterLookService = Depends(get_character_look_service)):
    try:
        return CharacterLookList(looks=service.list(project_id))
    except (LookupError, StabilityError) as exc:
        raise _http_error(exc) from exc


@router.get("/{project_id}/characters/{character_id}/look", response_model=CharacterLook)
async def get_look(project_id: str, character_id: str, service: CharacterLookService = Depends(get_character_look_service)):
    try:
        return service.get(project_id, character_id)
    except (LookupError, StabilityError) as exc:
        raise _http_error(exc) from exc


@router.post("/{project_id}/characters/{character_id}/look/approve", response_model=CharacterLook)
async def approve_look(project_id: str, character_id: str, payload: CharacterLookApprovalRequest, service: CharacterLookService = Depends(get_character_look_service)):
    try:
        return service.approve(project_id, character_id, payload)
    except (LookupError, StabilityError) as exc:
        raise _http_error(exc) from exc


@router.post("/{project_id}/characters/{character_id}/look/revise", response_model=CharacterLook)
async def revise_look(project_id: str, character_id: str, payload: CharacterLookRevisionRequest, service: CharacterLookService = Depends(get_character_look_service)):
    try:
        return service.revise(project_id, character_id, payload.expected_profile_revision)
    except (LookupError, StabilityError) as exc:
        raise _http_error(exc) from exc


@router.post("/{project_id}/characters/{character_id}/look/reference", response_model=CharacterLookUploadResponse)
async def upload_reference(project_id: str, character_id: str, file: UploadFile = File(...), service: CharacterLookService = Depends(get_character_look_service)):
    try:
        return CharacterLookUploadResponse(image_url=service.upload(project_id, character_id, await file.read(MAX_REFERENCE_BYTES + 1)))
    except (LookupError, StabilityError) as exc:
        raise _http_error(exc) from exc
