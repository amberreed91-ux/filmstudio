from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from app.models.studio_workflow import (
    StudioApprovalDecision,
    StudioApprovalDecisionCreate,
    StudioApprovalGate,
    StudioApprovalGateCreate,
    StudioArtifactVersion,
    StudioArtifactVersionCreate,
    StudioCollaborator,
    StudioCollaboratorUpsert,
    StudioWorkflowPhase,
    StudioWorkflowComment,
    StudioWorkflowCommentCreate,
    StudioWorkflowProjectState,
    StudioWorkflowStatus,
    StudioWorkflowSummary,
    StudioWorkflowTask,
)
from app.services.stability import PersistenceError, StateError, StabilityError, ValidationError
from app.services.studio_workflow_service import studio_workflow_service


router = APIRouter(prefix="/api/f51/studio/projects/{project_id}/workflow", tags=["studio-workflow"])


class ResolveCommentPayload(BaseModel):
    actor_id: str = "owner"


class WorkflowPhasePayload(BaseModel):
    actor_id: str = "owner"
    phase: StudioWorkflowPhase
    workflow_status: StudioWorkflowStatus | None = None


def _http_error(exc: Exception) -> HTTPException:
    message = getattr(exc, "message", str(exc))
    if isinstance(exc, ValidationError):
        lowered = message.lower()
        if "not found" in lowered:
            return HTTPException(status_code=404, detail=exc.to_dict())
        if "cannot decide" in lowered or "cannot close" in lowered:
            return HTTPException(status_code=403, detail=exc.to_dict())
        return HTTPException(status_code=422, detail=exc.to_dict())
    if isinstance(exc, StateError):
        return HTTPException(status_code=409, detail=exc.to_dict())
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=503, detail=exc.to_dict())
    if isinstance(exc, StabilityError):
        return HTTPException(status_code=500, detail=exc.to_dict())
    return HTTPException(status_code=500, detail="Internal server error")


@router.get("", response_model=StudioWorkflowSummary)
def get_project_workflow(project_id: str):
    try:
        return studio_workflow_service.workflow_summary(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/collaborators", response_model=StudioCollaborator)
def upsert_workflow_collaborator(project_id: str, payload: StudioCollaboratorUpsert):
    try:
        return studio_workflow_service.upsert_collaborator(project_id, payload)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/phase", response_model=StudioWorkflowProjectState)
def update_workflow_phase(project_id: str, payload: WorkflowPhasePayload):
    try:
        return studio_workflow_service.update_project_phase(
            project_id,
            phase=payload.phase,
            actor_id=payload.actor_id,
            status=payload.workflow_status,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/collaborators", response_model=list[StudioCollaborator])
def list_workflow_collaborators(project_id: str, limit: int = Query(default=200, ge=1, le=500)):
    try:
        return studio_workflow_service.list_collaborators(project_id, limit=limit)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/versions", response_model=StudioArtifactVersion)
def create_workflow_version(project_id: str, payload: StudioArtifactVersionCreate):
    try:
        return studio_workflow_service.create_artifact_version(project_id, payload)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/versions", response_model=list[StudioArtifactVersion])
def list_workflow_versions(
    project_id: str,
    artifact_type: str | None = None,
    artifact_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        return studio_workflow_service.list_artifact_versions(
            project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            status=status,
            limit=limit,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/versions/{version_id}")
def get_workflow_version(project_id: str, version_id: str) -> dict[str, Any]:
    try:
        return studio_workflow_service.get_artifact_version_with_lineage(project_id, version_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/gates", response_model=StudioApprovalGate)
def create_workflow_gate(project_id: str, payload: StudioApprovalGateCreate):
    try:
        return studio_workflow_service.create_approval_gate(project_id, payload)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/gates", response_model=list[StudioApprovalGate])
def list_workflow_gates(
    project_id: str,
    status: str | None = None,
    gate_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        return studio_workflow_service.list_approval_gates(
            project_id,
            status=status,
            gate_type=gate_type,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/gates/{gate_id}")
def get_workflow_gate(project_id: str, gate_id: str) -> dict[str, Any]:
    try:
        return studio_workflow_service.get_approval_gate_with_decisions(project_id, gate_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/gates/{gate_id}/evaluate", response_model=StudioApprovalGate)
def evaluate_workflow_gate(project_id: str, gate_id: str):
    try:
        return studio_workflow_service.evaluate_gate(project_id, gate_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/gates/{gate_id}/decisions", response_model=StudioApprovalDecision)
def record_workflow_decision(project_id: str, gate_id: str, payload: StudioApprovalDecisionCreate):
    try:
        return studio_workflow_service.record_approval_decision(project_id, gate_id, payload)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/comments", response_model=StudioWorkflowComment)
def post_workflow_comment(project_id: str, payload: StudioWorkflowCommentCreate):
    try:
        return studio_workflow_service.post_comment(project_id, payload)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/comments", response_model=list[StudioWorkflowComment])
def list_workflow_comments(
    project_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
    version_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        return studio_workflow_service.list_comments(
            project_id,
            target_type=target_type,
            target_id=target_id,
            version_id=version_id,
            status=status,
            limit=limit,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/tasks", response_model=list[StudioWorkflowTask])
def list_workflow_tasks(
    project_id: str,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        return studio_workflow_service.list_tasks(project_id, status=status, limit=limit)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/comments/{comment_id}/resolve", response_model=StudioWorkflowComment)
def resolve_workflow_comment(
    project_id: str,
    comment_id: str,
    payload: ResolveCommentPayload = Body(default_factory=ResolveCommentPayload),
):
    try:
        return studio_workflow_service.resolve_comment(project_id, comment_id, payload.actor_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/events")
def list_workflow_events(
    project_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
    gate_id: str | None = None,
    version_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        events = studio_workflow_service.list_events(
            project_id,
            target_type=target_type,
            target_id=target_id,
            gate_id=gate_id,
            version_id=version_id,
            limit=limit,
        )
        return {"events": [event.model_dump(mode="json") for event in events]}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/compatibility")
def get_workflow_compatibility(project_id: str):
    try:
        return {"legacy_projection": studio_workflow_service.compatibility_projection(project_id)}
    except Exception as exc:
        raise _http_error(exc) from exc
