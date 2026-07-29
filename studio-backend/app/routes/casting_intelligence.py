from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.casting_intelligence import (
    AuditionEvaluation,
    AuditionPackage,
    AuditionPackageRequest,
    AuditionSubmission,
    AuditionSubmissionRequest,
    CastingDecision,
    CastingDecisionMemoryProjection,
    CastingDecisionRequest,
    CastingDecisionUpdateRequest,
    CastingDepartmentSignal,
    CastingProjection,
    CastingReadinessReport,
    CastingReadinessRequest,
    CastingRecommendation,
    CastingRecommendationRequest,
    CastingRoleBreakdown,
    CastingSaveDecisionRequest,
    RoleBreakdownBuildRequest,
    RoleBreakdownBuildResponse,
    TalentProfile,
    TalentProfileRequest,
    TalentProfileUpdateRequest,
)
from app.services.casting_intelligence_service import casting_intelligence_service
from app.services.stability import PersistenceError, StateError, ValidationError


router = APIRouter(prefix="/api/f51/studio/projects", tags=["casting-intelligence"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, StateError):
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/{project_id}/casting/roles/build", response_model=RoleBreakdownBuildResponse)
def build_casting_role_breakdowns(project_id: str, request: RoleBreakdownBuildRequest):
    try:
        return casting_intelligence_service.build_role_breakdowns(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/roles", response_model=list[CastingRoleBreakdown])
def list_casting_role_breakdowns(
    project_id: str,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return casting_intelligence_service.list_role_breakdowns(project_id, status=status, limit=limit)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/roles/{role_id}", response_model=CastingRoleBreakdown)
def get_casting_role_breakdown(project_id: str, role_id: str):
    try:
        return casting_intelligence_service.get_role_breakdown(project_id, role_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/talent", response_model=TalentProfile)
def create_talent_profile(project_id: str, request: TalentProfileRequest):
    try:
        return casting_intelligence_service.create_talent_profile(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/talent", response_model=list[TalentProfile])
def list_talent_profiles(
    project_id: str,
    modality: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return casting_intelligence_service.list_talent_profiles(project_id, modality=modality, limit=limit)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/talent/{talent_id}", response_model=TalentProfile)
def get_talent_profile(project_id: str, talent_id: str):
    try:
        return casting_intelligence_service.get_talent_profile(project_id, talent_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/{project_id}/casting/talent/{talent_id}", response_model=TalentProfile)
def update_talent_profile(project_id: str, talent_id: str, request: TalentProfileUpdateRequest):
    try:
        return casting_intelligence_service.update_talent_profile(project_id, talent_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/roles/{role_id}/audition-packages", response_model=AuditionPackage)
def create_audition_package(project_id: str, role_id: str, request: AuditionPackageRequest):
    try:
        return casting_intelligence_service.create_audition_package(project_id, role_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/audition-packages", response_model=list[AuditionPackage])
def list_audition_packages(
    project_id: str,
    role_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return casting_intelligence_service.list_audition_packages(project_id, role_id=role_id, limit=limit)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/audition-packages/{package_id}/submissions", response_model=AuditionSubmission)
def submit_audition(project_id: str, package_id: str, request: AuditionSubmissionRequest):
    try:
        return casting_intelligence_service.submit_audition(project_id, package_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/auditions", response_model=list[AuditionSubmission])
def list_auditions(
    project_id: str,
    role_id: str | None = None,
    talent_id: str | None = None,
    package_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return casting_intelligence_service.list_audition_submissions(
            project_id,
            role_id=role_id,
            talent_id=talent_id,
            package_id=package_id,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/auditions/{audition_id}/evaluate", response_model=AuditionEvaluation)
def evaluate_audition(project_id: str, audition_id: str):
    try:
        return casting_intelligence_service.evaluate_audition(project_id, audition_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/roles/{role_id}/recommendations", response_model=list[CastingRecommendation])
def recommend_casting(project_id: str, role_id: str, request: CastingRecommendationRequest):
    try:
        return casting_intelligence_service.recommend_casting(project_id, role_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/recommendations", response_model=list[CastingRecommendation])
def list_casting_recommendations(
    project_id: str,
    role_id: str | None = None,
    talent_id: str | None = None,
    stale: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return casting_intelligence_service.list_casting_recommendations(
            project_id,
            role_id=role_id,
            talent_id=talent_id,
            stale=stale,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/decisions", response_model=CastingDecision)
def approve_casting_decision(project_id: str, request: CastingDecisionRequest):
    try:
        return casting_intelligence_service.approve_casting_decision(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/decisions/active", response_model=list[CastingDecision])
def list_active_casting_decisions(
    project_id: str,
    role_id: str | None = None,
    character_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return casting_intelligence_service.list_casting_decisions(
            project_id,
            role_id=role_id,
            character_id=character_id,
            active=True,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/projection", response_model=CastingProjection)
def get_casting_projection(
    project_id: str,
    role_id: str | None = None,
    character_id: str | None = None,
):
    try:
        return casting_intelligence_service.get_active_casting_projection(project_id, role_id=role_id, character_id=character_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/readiness", response_model=CastingReadinessReport)
def create_casting_readiness_report(project_id: str, request: CastingReadinessRequest):
    try:
        return casting_intelligence_service.create_readiness_report(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/casting/department-signal", response_model=CastingDepartmentSignal)
def get_casting_department_signal(project_id: str):
    try:
        return casting_intelligence_service.department_signal(project_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/casting/memory-decisions", response_model=CastingDecisionMemoryProjection)
def save_casting_memory_decision(project_id: str, request: CastingSaveDecisionRequest):
    try:
        return casting_intelligence_service.save_casting_decision_memory(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/{project_id}/casting/memory-decisions/{decision_id}", response_model=CastingDecisionMemoryProjection)
def update_casting_memory_decision(project_id: str, decision_id: str, request: CastingDecisionUpdateRequest):
    try:
        return casting_intelligence_service.update_casting_decision_memory(project_id, decision_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.delete("/{project_id}/casting/memory-decisions/{decision_id}", response_model=CastingDecisionMemoryProjection)
def forget_casting_memory_decision(project_id: str, decision_id: str):
    try:
        return casting_intelligence_service.forget_casting_decision_memory(project_id, decision_id)
    except Exception as exc:
        raise _map_error(exc) from exc
