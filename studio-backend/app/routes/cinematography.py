from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.cinematography import (
    CameraGrammarAssessmentRequest,
    CameraGrammarAssessmentResponse,
    CameraGrammarObservationRequest,
    CameraGrammarObservationResponse,
    CameraGrammarPlanRequest,
    CameraGrammarPlanResponse,
    CameraGrammarRenderContext,
    CameraGrammarRenderContextRequest,
)
from app.services.cinematographer_intelligence_service import cinematographer_intelligence_service
from app.services.stability import PersistenceError, StateError, ValidationError


router = APIRouter(prefix="/api/projects", tags=["cinematography"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, StateError):
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/{project_id}/cinematography/plans", response_model=CameraGrammarPlanResponse)
def create_camera_grammar_plan(project_id: str, request: CameraGrammarPlanRequest):
    try:
        return cinematographer_intelligence_service.create_plan(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/cinematography/plans")
def list_camera_grammar_plans(
    project_id: str,
    scene_id: str | None = None,
    shot_id: str | None = None,
    render_job_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    plans = cinematographer_intelligence_service.list_plans(
        project_id,
        scene_id=scene_id,
        shot_id=shot_id,
        render_job_id=render_job_id,
        status=status,
        limit=limit,
    )
    return {"plans": [plan.model_dump(mode="json") for plan in plans]}


@router.get("/{project_id}/cinematography/plans/{plan_id}")
def get_camera_grammar_plan(project_id: str, plan_id: str):
    try:
        plan = cinematographer_intelligence_service.get_plan(project_id, plan_id)
        return {"plan": plan.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/cinematography/observations", response_model=CameraGrammarObservationResponse)
def create_camera_grammar_observation(project_id: str, request: CameraGrammarObservationRequest):
    try:
        observation = cinematographer_intelligence_service.create_observation(project_id, request)
        return CameraGrammarObservationResponse(observation=observation)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/cinematography/observations")
def list_camera_grammar_observations(
    project_id: str,
    plan_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    observations = cinematographer_intelligence_service.list_observations(
        project_id,
        plan_id=plan_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        limit=limit,
    )
    return {"observations": [observation.model_dump(mode="json") for observation in observations]}


@router.post("/{project_id}/cinematography/assessments", response_model=CameraGrammarAssessmentResponse)
def create_camera_grammar_assessment(project_id: str, request: CameraGrammarAssessmentRequest):
    try:
        assessment = cinematographer_intelligence_service.create_assessment(project_id, request)
        return CameraGrammarAssessmentResponse(assessment=assessment)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/cinematography/assessments")
def list_camera_grammar_assessments(
    project_id: str,
    plan_id: str | None = None,
    observation_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    assessments = cinematographer_intelligence_service.list_assessments(
        project_id,
        plan_id=plan_id,
        observation_id=observation_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        limit=limit,
    )
    return {"assessments": [assessment.model_dump(mode="json") for assessment in assessments]}


@router.post("/{project_id}/cinematography/render-context", response_model=CameraGrammarRenderContext)
def build_camera_grammar_render_context(project_id: str, request: CameraGrammarRenderContextRequest):
    try:
        return cinematographer_intelligence_service.build_render_context(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc
