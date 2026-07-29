from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.studio_brain import (
    StudioBrainDispatchDirectiveRequest,
    StudioBrainOpenSessionRequest,
    StudioBrainResolveConflictRequest,
    StudioBrainSessionResponse,
)
from app.services.stability import PersistenceError, StateError, ValidationError
from app.services.studio_brain_executive_service import studio_brain_executive_service


router = APIRouter(prefix="/api/f51/studio/projects/{project_id}/brain", tags=["studio-brain"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        status = 404 if "not found" in exc.message.lower() else 400
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, StateError):
        return HTTPException(status_code=409, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions", response_model=StudioBrainSessionResponse)
def create_studio_brain_session(project_id: str, request: StudioBrainOpenSessionRequest):
    try:
        session = studio_brain_executive_service.open_session(project_id, request)
        return studio_brain_executive_service.get_session_response(session.session_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/sessions")
def list_studio_brain_sessions(project_id: str, limit: int = Query(default=20, ge=1, le=100)):
    sessions = studio_brain_executive_service.list_sessions(project_id, limit=limit)
    return {"sessions": [session.model_dump(mode="json") for session in sessions]}


@router.get("/sessions/{session_id}", response_model=StudioBrainSessionResponse)
def get_studio_brain_session(project_id: str, session_id: str):
    try:
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_get_session")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/signals/refresh", response_model=StudioBrainSessionResponse)
def refresh_studio_brain_signals(project_id: str, session_id: str):
    try:
        studio_brain_executive_service.gather_department_signals(session_id, refresh=True)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_refresh_signals")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/plan", response_model=StudioBrainSessionResponse)
def generate_studio_brain_plan(project_id: str, session_id: str):
    try:
        studio_brain_executive_service.generate_production_plan(session_id)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_generate_plan")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/conflicts/detect", response_model=StudioBrainSessionResponse)
def detect_studio_brain_conflicts(project_id: str, session_id: str):
    try:
        studio_brain_executive_service.detect_conflicts(session_id)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_detect_conflicts")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/conflicts/{conflict_id}/resolve", response_model=StudioBrainSessionResponse)
def resolve_studio_brain_conflict(
    project_id: str,
    session_id: str,
    conflict_id: str,
    request: StudioBrainResolveConflictRequest,
):
    try:
        studio_brain_executive_service.resolve_conflict(session_id, conflict_id, request)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_resolve_conflict")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/readiness", response_model=StudioBrainSessionResponse)
def create_studio_brain_readiness(project_id: str, session_id: str):
    try:
        studio_brain_executive_service.create_readiness_snapshot(session_id)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_readiness")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/directives", response_model=StudioBrainSessionResponse)
def propose_studio_brain_directives(project_id: str, session_id: str):
    try:
        studio_brain_executive_service.propose_directives(session_id)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_directives")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sessions/{session_id}/directives/{directive_id}/dispatch", response_model=StudioBrainSessionResponse)
def dispatch_studio_brain_directive(
    project_id: str,
    session_id: str,
    directive_id: str,
    request: StudioBrainDispatchDirectiveRequest,
):
    try:
        studio_brain_executive_service.dispatch_directive(session_id, directive_id, request)
        response = studio_brain_executive_service.get_session_response(session_id)
        if response.session.project_id != project_id:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_dispatch")
        return response
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/latest", response_model=StudioBrainSessionResponse | None)
def get_latest_studio_brain_session(project_id: str):
    return studio_brain_executive_service.latest_session_response(project_id)
