from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.colorist import (
    ColorFinalVerificationRequest,
    ColorFinalVerificationResponse,
    ColorGradeObservationRequest,
    ColorGradeObservationResponse,
    ColorLookBibleRequest,
    ColorLookBibleResponse,
    ColorMatchAssessmentRequest,
    ColorMatchAssessmentResponse,
    ColorRenderContext,
    ColorRenderContextRequest,
    ColorStoryArcRequest,
    ColorStoryArcResponse,
    ColoristDecisionProjection,
    ColoristDecisionSaveRequest,
    ColoristDepartmentSignal,
    ColoristLookPlanRequest,
    ColoristLookPlanResponse,
)
from app.services.colorist_intelligence_service import colorist_intelligence_service
from app.services.stability import PersistenceError, StateError, ValidationError


router = APIRouter(prefix="/api/projects", tags=["colorist"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, StateError):
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/{project_id}/colorist/look-bibles", response_model=ColorLookBibleResponse)
def create_color_look_bible(project_id: str, request: ColorLookBibleRequest):
    try:
        return colorist_intelligence_service.create_or_update_look_bible(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/look-bibles")
def list_color_look_bibles(
    project_id: str,
    scope: str | None = None,
    sequence_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    look_bibles = colorist_intelligence_service.list_look_bibles(
        project_id,
        scope=scope,
        sequence_id=sequence_id,
        status=status,
        limit=limit,
    )
    return {"look_bibles": [item.model_dump(mode="json") for item in look_bibles]}


@router.get("/{project_id}/colorist/look-bibles/{look_bible_id}")
def get_color_look_bible(project_id: str, look_bible_id: str):
    try:
        look_bible = colorist_intelligence_service.get_look_bible(project_id, look_bible_id)
        return {"look_bible": look_bible.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/colorist/plans", response_model=ColoristLookPlanResponse)
def create_colorist_look_plan(project_id: str, request: ColoristLookPlanRequest):
    try:
        return colorist_intelligence_service.create_look_plan(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/plans")
def list_colorist_look_plans(
    project_id: str,
    look_bible_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    status: str | None = None,
    stale: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    plans = colorist_intelligence_service.list_look_plans(
        project_id,
        look_bible_id=look_bible_id,
        scene_id=scene_id,
        shot_id=shot_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        status=status,
        stale=stale,
        limit=limit,
    )
    return {"plans": [plan.model_dump(mode="json") for plan in plans]}


@router.get("/{project_id}/colorist/plans/{plan_id}")
def get_colorist_look_plan(project_id: str, plan_id: str):
    try:
        plan = colorist_intelligence_service.get_look_plan(project_id, plan_id)
        return {"plan": plan.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/palette-continuity")
def list_color_palette_continuity(
    project_id: str,
    scope: str | None = None,
    scene_id: str | None = None,
    sequence_id: str | None = None,
    character_id: str | None = None,
    location_id: str | None = None,
    prop_id: str | None = None,
    motif_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    records = colorist_intelligence_service.list_palette_continuity_records(
        project_id,
        scope=scope,
        scene_id=scene_id,
        sequence_id=sequence_id,
        character_id=character_id,
        location_id=location_id,
        prop_id=prop_id,
        motif_id=motif_id,
        limit=limit,
    )
    return {"records": [record.model_dump(mode="json") for record in records]}


@router.post("/{project_id}/colorist/story-arcs", response_model=ColorStoryArcResponse)
def create_color_story_arc(project_id: str, request: ColorStoryArcRequest):
    try:
        return colorist_intelligence_service.create_color_story_arc(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/story-arcs")
def list_color_story_arcs(
    project_id: str,
    look_bible_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    arcs = colorist_intelligence_service.list_color_story_arcs(project_id, look_bible_id=look_bible_id, status=status, limit=limit)
    return {"story_arcs": [arc.model_dump(mode="json") for arc in arcs]}


@router.post("/{project_id}/colorist/observations", response_model=ColorGradeObservationResponse)
def create_color_grade_observation(project_id: str, request: ColorGradeObservationRequest):
    try:
        return colorist_intelligence_service.create_observation(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/observations")
def list_color_grade_observations(
    project_id: str,
    plan_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    observations = colorist_intelligence_service.list_observations(
        project_id,
        plan_id=plan_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        status=status,
        limit=limit,
    )
    return {"observations": [observation.model_dump(mode="json") for observation in observations]}


@router.post("/{project_id}/colorist/assessments", response_model=ColorMatchAssessmentResponse)
def create_color_match_assessment(project_id: str, request: ColorMatchAssessmentRequest):
    try:
        return colorist_intelligence_service.create_assessment(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/assessments")
def list_color_match_assessments(
    project_id: str,
    plan_id: str | None = None,
    observation_id: str | None = None,
    look_bible_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    assessments = colorist_intelligence_service.list_assessments(
        project_id,
        plan_id=plan_id,
        observation_id=observation_id,
        look_bible_id=look_bible_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        status=status,
        limit=limit,
    )
    return {"assessments": [assessment.model_dump(mode="json") for assessment in assessments]}


@router.post("/{project_id}/colorist/render-context", response_model=ColorRenderContext)
def build_color_render_context(project_id: str, request: ColorRenderContextRequest):
    try:
        return colorist_intelligence_service.build_render_context(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/colorist/final-verifications", response_model=ColorFinalVerificationResponse)
def create_color_final_verification(project_id: str, request: ColorFinalVerificationRequest):
    try:
        return colorist_intelligence_service.verify_final_package(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/final-verifications")
def list_color_final_verifications(
    project_id: str,
    package_id: str | None = None,
    asset_id: str | None = None,
    look_bible_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    verifications = colorist_intelligence_service.list_final_verifications(
        project_id,
        package_id=package_id,
        asset_id=asset_id,
        look_bible_id=look_bible_id,
        status=status,
        limit=limit,
    )
    return {"verifications": [verification.model_dump(mode="json") for verification in verifications]}


@router.post("/{project_id}/colorist/decisions/save", response_model=ColoristDecisionProjection)
def save_explicit_color_decision(project_id: str, request: ColoristDecisionSaveRequest):
    try:
        return colorist_intelligence_service.save_explicit_color_decision(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/colorist/signal", response_model=ColoristDepartmentSignal)
def get_colorist_signal(
    project_id: str,
    scene_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
):
    try:
        return colorist_intelligence_service.department_signal(project_id, scene_id=scene_id, asset_id=asset_id, render_job_id=render_job_id)
    except Exception as exc:
        raise _map_error(exc) from exc
