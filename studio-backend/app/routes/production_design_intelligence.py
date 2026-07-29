from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.production_design import (
    CostumeContinuityRecord,
    CostumeContinuityRecordRequest,
    EnvironmentDesignProfile,
    EnvironmentDesignProfileRequest,
    PropContinuityRecord,
    PropContinuityRecordRequest,
    ProductionDesignAssessmentRequest,
    ProductionDesignAssessmentResponse,
    ProductionDesignDecisionProjection,
    ProductionDesignDecisionRequest,
    ProductionDesignDecisionUpdateRequest,
    ProductionDesignDepartmentSignal,
    ProductionDesignObservationRequest,
    ProductionDesignObservationResponse,
    ProductionDesignPlanRequest,
    ProductionDesignPlanResponse,
    ProductionDesignRenderContext,
    ProductionDesignRenderContextRequest,
)
from app.services.production_design_intelligence_service import production_design_intelligence_service
from app.services.stability import PersistenceError, StateError, ValidationError


router = APIRouter(prefix="/api/f51/studio/projects", tags=["production-design-intelligence"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, StateError):
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/{project_id}/production-design/plans", response_model=ProductionDesignPlanResponse)
def create_production_design_plan(project_id: str, request: ProductionDesignPlanRequest):
    try:
        return production_design_intelligence_service.create_plan(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/plans")
def list_production_design_plans(
    project_id: str,
    scene_id: str | None = None,
    shot_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    status: str | None = None,
    stale: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    plans = production_design_intelligence_service.list_plans(
        project_id,
        scene_id=scene_id,
        shot_id=shot_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        status=status,
        stale=stale,
        limit=limit,
    )
    return {"plans": [plan.model_dump(mode="json") for plan in plans]}


@router.get("/{project_id}/production-design/plans/{plan_id}")
def get_production_design_plan(project_id: str, plan_id: str):
    try:
        plan = production_design_intelligence_service.get_plan(project_id, plan_id)
        return {"plan": plan.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/production-design/environment-profiles", response_model=EnvironmentDesignProfile)
def create_production_design_environment_profile(project_id: str, request: EnvironmentDesignProfileRequest):
    try:
        return production_design_intelligence_service.create_environment_profile(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/environment-profiles")
def list_production_design_environment_profiles(
    project_id: str,
    location_name: str | None = None,
    location_id: str | None = None,
    stale: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    profiles = production_design_intelligence_service.list_environment_profiles(
        project_id,
        location_name=location_name,
        location_id=location_id,
        stale=stale,
        limit=limit,
    )
    return {"environment_profiles": [profile.model_dump(mode="json") for profile in profiles]}


@router.post("/{project_id}/production-design/prop-records", response_model=PropContinuityRecord)
def create_production_design_prop_record(project_id: str, request: PropContinuityRecordRequest):
    try:
        return production_design_intelligence_service.create_prop_record(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/prop-records")
def list_production_design_prop_records(
    project_id: str,
    prop_id: str | None = None,
    prop_name: str | None = None,
    stale: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    records = production_design_intelligence_service.list_prop_records(
        project_id,
        prop_id=prop_id,
        prop_name=prop_name,
        stale=stale,
        limit=limit,
    )
    return {"prop_records": [record.model_dump(mode="json") for record in records]}


@router.post("/{project_id}/production-design/costume-records", response_model=CostumeContinuityRecord)
def create_production_design_costume_record(project_id: str, request: CostumeContinuityRecordRequest):
    try:
        return production_design_intelligence_service.create_costume_record(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/costume-records")
def list_production_design_costume_records(
    project_id: str,
    character_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    stale: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    records = production_design_intelligence_service.list_costume_records(
        project_id,
        character_id=character_id,
        scene_id=scene_id,
        shot_id=shot_id,
        stale=stale,
        limit=limit,
    )
    return {"costume_records": [record.model_dump(mode="json") for record in records]}


@router.post("/{project_id}/production-design/observations", response_model=ProductionDesignObservationResponse)
def create_production_design_observation(project_id: str, request: ProductionDesignObservationRequest):
    try:
        observation = production_design_intelligence_service.create_observation(project_id, request)
        return ProductionDesignObservationResponse(observation=observation)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/observations")
def list_production_design_observations(
    project_id: str,
    plan_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    observations = production_design_intelligence_service.list_observations(
        project_id,
        plan_id=plan_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        limit=limit,
    )
    return {"observations": [observation.model_dump(mode="json") for observation in observations]}


@router.post("/{project_id}/production-design/assessments", response_model=ProductionDesignAssessmentResponse)
def create_production_design_assessment(project_id: str, request: ProductionDesignAssessmentRequest):
    try:
        assessment = production_design_intelligence_service.create_assessment(project_id, request)
        return ProductionDesignAssessmentResponse(assessment=assessment)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/assessments")
def list_production_design_assessments(
    project_id: str,
    plan_id: str | None = None,
    observation_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    assessments = production_design_intelligence_service.list_assessments(
        project_id,
        plan_id=plan_id,
        observation_id=observation_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        status=status,
        limit=limit,
    )
    return {"assessments": [assessment.model_dump(mode="json") for assessment in assessments]}


@router.post("/{project_id}/production-design/render-context", response_model=ProductionDesignRenderContext)
def build_production_design_render_context(project_id: str, request: ProductionDesignRenderContextRequest):
    try:
        return production_design_intelligence_service.build_render_context(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/production-design/department-signal", response_model=ProductionDesignDepartmentSignal)
def get_production_design_department_signal(project_id: str):
    try:
        return production_design_intelligence_service.department_signal(project_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/production-design/decisions", response_model=ProductionDesignDecisionProjection)
def save_production_design_decision(project_id: str, request: ProductionDesignDecisionRequest):
    try:
        return production_design_intelligence_service.save_decision(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/{project_id}/production-design/decisions/{decision_id}", response_model=ProductionDesignDecisionProjection)
def update_production_design_decision(project_id: str, decision_id: str, request: ProductionDesignDecisionUpdateRequest):
    try:
        return production_design_intelligence_service.update_decision(project_id, decision_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc
