from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.performance_intelligence import (
    CharacterPerformanceBrief,
    PerformanceAnalysisRequest,
    PerformanceAnalysisResponse,
    PerformanceContextBundle,
    PerformanceDecisionMemoryProjection,
    PerformanceSaveDecisionRequest,
    PerformanceUpdateDecisionRequest,
)
from app.services.performance_intelligence_service import performance_intelligence_service
from app.services.stability import StateError, ValidationError


router = APIRouter(prefix="/api/projects", tags=["performance-intelligence"])


@router.post("/{project_id}/performance-intelligence/analyze", response_model=PerformanceAnalysisResponse)
async def analyze_performance(project_id: str, request: PerformanceAnalysisRequest):
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    try:
        if request.scope == "project":
            return await performance_intelligence_service.analyze_project_performance(
                project_id,
                persist=request.persist,
            )
        if not request.scene_id:
            raise ValidationError("scene_id required for scene performance analysis")
        return await performance_intelligence_service.analyze_scene_performance(
            project_id,
            request.scene_id,
            character_ids=request.character_ids,
            persist=request.persist,
            include_context_bundles=request.include_context_bundles,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StateError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{project_id}/performance-intelligence/scenes/{scene_id}", response_model=PerformanceAnalysisResponse)
async def get_scene_performance(project_id: str, scene_id: str):
    try:
        analysis = await performance_intelligence_service.get_scene_performance(project_id, scene_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Performance analysis not found")
        return analysis
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{project_id}/performance-intelligence/characters/{character_id}/history",
    response_model=list[CharacterPerformanceBrief],
)
async def get_character_performance_history(
    project_id: str,
    character_id: str,
    limit: int = Query(20, ge=1, le=100),
):
    try:
        return await performance_intelligence_service.get_character_performance_history(project_id, character_id, limit=limit)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{project_id}/performance-intelligence/scenes/{scene_id}/prompt-context",
    response_model=PerformanceContextBundle,
)
async def get_performance_prompt_context(
    project_id: str,
    scene_id: str,
    shot_id: str | None = None,
):
    try:
        return await performance_intelligence_service.build_prompt_context(project_id, scene_id, shot_id=shot_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{project_id}/performance-intelligence/scenes/{scene_id}/voice-context/{character_id}",
    response_model=PerformanceContextBundle,
)
async def get_performance_voice_context(project_id: str, scene_id: str, character_id: str):
    try:
        return await performance_intelligence_service.build_voice_context(project_id, scene_id, character_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{project_id}/performance-intelligence/scenes/{scene_id}/screening-context",
    response_model=PerformanceContextBundle,
)
async def get_performance_screening_context(project_id: str, scene_id: str):
    try:
        return await performance_intelligence_service.build_screening_context(project_id, scene_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/{project_id}/performance-intelligence/decisions",
    response_model=PerformanceDecisionMemoryProjection,
)
async def save_performance_decision(project_id: str, request: PerformanceSaveDecisionRequest):
    try:
        return await performance_intelligence_service.save_performance_decision(project_id, request)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch(
    "/{project_id}/performance-intelligence/decisions/{decision_id}",
    response_model=PerformanceDecisionMemoryProjection,
)
async def update_performance_decision(project_id: str, decision_id: str, request: PerformanceUpdateDecisionRequest):
    try:
        return await performance_intelligence_service.update_performance_decision(project_id, decision_id, request)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StateError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete(
    "/{project_id}/performance-intelligence/decisions/{decision_id}",
    response_model=PerformanceDecisionMemoryProjection,
)
async def forget_performance_decision(project_id: str, decision_id: str):
    try:
        return await performance_intelligence_service.forget_performance_decision(project_id, decision_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StateError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
