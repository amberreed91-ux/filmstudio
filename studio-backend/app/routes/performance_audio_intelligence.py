from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.performance_audio import (
    AudioExecutionRequest,
    AudioIntelligenceAssessment,
    AudioIntelligenceAssessmentRequest,
    PerformanceAudioDecisionProjection,
    PerformanceAudioDecisionRequest,
    PerformanceAudioDecisionUpdateRequest,
    PerformanceAudioDepartmentSignal,
    PerformanceAudioPlanRequest,
    PerformanceAudioPlanResponse,
)
from app.services.performance_audio_intelligence_service import performance_audio_intelligence_service
from app.services.stability import PersistenceError, StateError, ValidationError


router = APIRouter(prefix="/api/f51/studio/projects", tags=["performance-audio-intelligence"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, StateError):
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/{project_id}/audio-intelligence/plans", response_model=PerformanceAudioPlanResponse)
def create_performance_audio_plan(project_id: str, request: PerformanceAudioPlanRequest):
    try:
        return performance_audio_intelligence_service.create_plan(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/audio-intelligence/plans")
def list_performance_audio_plans(
    project_id: str,
    scene_id: str | None = None,
    shot_id: str | None = None,
    status: str | None = None,
    stale: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    plans = performance_audio_intelligence_service.list_plans(
        project_id,
        scene_id=scene_id,
        shot_id=shot_id,
        status=status,
        stale=stale,
        limit=limit,
    )
    return {"plans": [plan.model_dump(mode="json") for plan in plans]}


@router.get("/{project_id}/audio-intelligence/plans/{plan_id}")
def get_performance_audio_plan(project_id: str, plan_id: str):
    try:
        plan = performance_audio_intelligence_service.get_plan(project_id, plan_id)
        return {"plan": plan.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/audio-intelligence/plans/{plan_id}/execution-request", response_model=AudioExecutionRequest)
def build_performance_audio_execution_request(project_id: str, plan_id: str):
    try:
        return performance_audio_intelligence_service.build_execution_request(project_id, plan_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/audio-intelligence/plans/{plan_id}/generate")
async def generate_performance_audio_from_plan(project_id: str, plan_id: str):
    try:
        return await performance_audio_intelligence_service.generate_from_plan(project_id, plan_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/audio-intelligence/voice-profiles")
def list_performance_audio_voice_profiles(
    project_id: str,
    character_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    profiles = performance_audio_intelligence_service.list_voice_profiles(project_id, character_id=character_id, limit=limit)
    return {"voice_profiles": [profile.model_dump(mode="json") for profile in profiles]}


@router.get("/{project_id}/audio-intelligence/dialogue-cues")
def list_performance_audio_dialogue_cues(
    project_id: str,
    plan_id: str | None = None,
    scene_id: str | None = None,
    character_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        cues = performance_audio_intelligence_service.list_dialogue_cues(
            project_id,
            plan_id=plan_id,
            scene_id=scene_id,
            character_id=character_id,
            limit=limit,
        )
        return {"dialogue_cues": [cue.model_dump(mode="json") for cue in cues]}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/audio-intelligence/soundscape-layers")
def list_performance_audio_soundscape_layers(
    project_id: str,
    plan_id: str | None = None,
    scene_id: str | None = None,
    track_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        layers = performance_audio_intelligence_service.list_soundscape_layers(
            project_id,
            plan_id=plan_id,
            scene_id=scene_id,
            track_type=track_type,
            limit=limit,
        )
        return {"soundscape_layers": [layer.model_dump(mode="json") for layer in layers]}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/audio-intelligence/assessments", response_model=AudioIntelligenceAssessment)
def create_performance_audio_assessment(project_id: str, request: AudioIntelligenceAssessmentRequest):
    try:
        return performance_audio_intelligence_service.create_assessment(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/audio-intelligence/assessments")
def list_performance_audio_assessments(
    project_id: str,
    plan_id: str | None = None,
    asset_id: str | None = None,
    render_job_id: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    readiness_label: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    assessments = performance_audio_intelligence_service.list_assessments(
        project_id,
        plan_id=plan_id,
        asset_id=asset_id,
        render_job_id=render_job_id,
        scene_id=scene_id,
        shot_id=shot_id,
        readiness_label=readiness_label,
        limit=limit,
    )
    return {"assessments": [assessment.model_dump(mode="json") for assessment in assessments]}


@router.post("/{project_id}/audio-intelligence/decisions", response_model=PerformanceAudioDecisionProjection)
def save_performance_audio_decision(project_id: str, request: PerformanceAudioDecisionRequest):
    try:
        return performance_audio_intelligence_service.save_decision(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/{project_id}/audio-intelligence/decisions/{decision_id}", response_model=PerformanceAudioDecisionProjection)
def update_performance_audio_decision(project_id: str, decision_id: str, request: PerformanceAudioDecisionUpdateRequest):
    try:
        return performance_audio_intelligence_service.update_decision(project_id, decision_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.delete("/{project_id}/audio-intelligence/decisions/{decision_id}", response_model=PerformanceAudioDecisionProjection)
def forget_performance_audio_decision(project_id: str, decision_id: str):
    try:
        return performance_audio_intelligence_service.forget_decision(project_id, decision_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/audio-intelligence/department-signal", response_model=PerformanceAudioDepartmentSignal)
def get_performance_audio_department_signal(project_id: str):
    try:
        return performance_audio_intelligence_service.department_signal(project_id)
    except Exception as exc:
        raise _map_error(exc) from exc
