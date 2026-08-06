from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.services.screening_room_service import screening_room_service
from app.services.stability import PersistenceError, PlaybackError, StabilityError, StateError, ValidationError

router = APIRouter(prefix="/api/f51/studio/projects", tags=["screening-room"])


class ApproveScreeningOutputRequest(BaseModel):
    confirmed: bool = False
    approved_by: str = "creator"


def _raise_http(exc: StabilityError) -> None:
    if isinstance(exc, ValidationError):
        code = 422
    elif isinstance(exc, (StateError, PlaybackError)):
        code = 404 if "not found" in exc.message.lower() or "missing" in exc.message.lower() else 409
    elif isinstance(exc, PersistenceError):
        code = 500
    else:
        code = 500
    raise HTTPException(status_code=code, detail=exc.to_dict()) from exc


@router.get("/{project_id}/screening/manifest")
def get_screening_manifest(project_id: str, refresh: bool = True) -> dict:
    try:
        return (
            screening_room_service.sync_manifest(project_id)
            if refresh
            else screening_room_service.get_manifest(project_id)
        )
    except StabilityError as exc:
        _raise_http(exc)


@router.post("/{project_id}/screening/sync")
def sync_screening_manifest(project_id: str) -> dict:
    try:
        return screening_room_service.sync_manifest(project_id)
    except StabilityError as exc:
        _raise_http(exc)


@router.post("/{project_id}/screening/outputs/{screening_output_id}/approve")
def approve_screening_output(
    project_id: str,
    screening_output_id: str,
    body: ApproveScreeningOutputRequest,
) -> dict:
    try:
        return screening_room_service.approve_output(
            project_id,
            screening_output_id,
            confirmed=body.confirmed,
            approved_by=body.approved_by,
        )
    except StabilityError as exc:
        _raise_http(exc)


@router.get("/{project_id}/screening/media/{screening_output_id}")
def stream_screening_media(project_id: str, screening_output_id: str):
    try:
        media = screening_room_service.resolve_media(project_id, screening_output_id)
    except StabilityError as exc:
        _raise_http(exc)
    if media["kind"] == "remote":
        return RedirectResponse(media["url"], status_code=307)
    return FileResponse(
        path=media["path"],
        media_type=media["mime_type"],
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"},
    )
