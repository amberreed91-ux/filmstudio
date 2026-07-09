"""
Memory Routes - API for project and scene memory

Required Endpoints:
- GET /memory/{project_id} - Read project memory
- POST /memory/{project_id}/update - Update memory
- GET /memory/{project_id}/debug - Debug/inspection endpoint
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Any
from pydantic import BaseModel
from datetime import datetime

from app.services.memory import memory_service
from app.services.memory_store import memory_store
from app.models.memory import MemoryType, MemoryScope, FeedbackType

router = APIRouter(prefix="/api/f51/studio/memory", tags=["memory"])


def get_current_user_id() -> str:
    return "user-demo"


# ==================== REQUEST MODELS ====================

class InitializeMemoryRequest(BaseModel):
    tone: str = ""
    genre: str = ""
    visual_style: List[str] = []
    color_grade: str = ""
    lighting_mood: List[str] = []
    reference_urls: List[str] = []


class UpdateMemoryRequest(BaseModel):
    memory_type: str  # project, scene, character, style, review
    data: dict  # Memory data to update
    agent_id: str = "system"
    task_id: Optional[str] = None


class SceneMemoryRequest(BaseModel):
    scene_id: str
    scene_number: int = 0
    location_name: Optional[str] = None
    time_of_day: Optional[str] = None
    weather: Optional[str] = None
    camera_choice: Optional[str] = None
    lighting_note: Optional[str] = None
    color_palette: Optional[List[str]] = None
    generated_shot: Optional[str] = None
    approved_shot: Optional[str] = None


class CharacterMemoryRequest(BaseModel):
    character_id: str
    character_name: str = ""
    appearance_traits: List[str] = []
    personality_traits: List[str] = []
    mannerisms: List[str] = []
    wardrobe: List[str] = []
    speech_patterns: List[str] = []
    relationships: dict = {}


class StyleMemoryRequest(BaseModel):
    camera_language: Optional[str] = None
    lighting_approach: Optional[str] = None
    color_palette: Optional[List[str]] = None
    pacing_notes: Optional[str] = None
    frame_composition: Optional[str] = None
    movement_style: Optional[str] = None
    lens_preferences: List[str] = []


class ReviewMemoryRequest(BaseModel):
    scene_id: Optional[str] = None
    shot_id: Optional[str] = None
    feedback_type: str = "agent"  # director, qc, user, agent
    feedback_text: str = ""
    quality_score: Optional[int] = None
    issues: List[str] = []
    recommendations: List[str] = []


class ReferenceAnalysisStoreRequest(BaseModel):
    project_id: str
    reference_analysis: dict


class ReferenceMemoryRetrieveRequest(BaseModel):
    project_id: str
    context: Optional[dict] = None


class ReferenceMemoryDeleteRequest(BaseModel):
    project_id: str
    reference_id: str


# ==================== CORE ENDPOINTS ====================

@router.get("/{project_id}")
def get_project_memory(
    project_id: str,
    memory_type: Optional[str] = None,
    scene_id: Optional[str] = None,
    character_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    GET /memory/{project_id} - Read project memory
    
    Agents MUST call this before acting to ensure continuity.
    """
    mem_type = None
    if memory_type:
        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            pass
    
    return memory_service.read_memory(
        project_id=project_id,
        memory_type=mem_type,
        scene_id=scene_id,
        character_id=character_id
    )


@router.post("/{project_id}/update")
def update_project_memory(
    project_id: str,
    request: UpdateMemoryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    POST /memory/{project_id}/update - Update memory
    
    Agents MUST call this after completing tasks to maintain continuity.
    """
    try:
        mem_type = MemoryType(request.memory_type)
    except ValueError:
        raise HTTPException(400, f"Invalid memory type: {request.memory_type}")
    
    result = memory_service.update_memory(
        project_id=project_id,
        memory_type=mem_type,
        data=request.data,
        agent_id=request.agent_id,
        task_id=request.task_id
    )
    
    return result


# ==================== INITIALIZATION ====================

@router.post("/{project_id}/init")
def initialize_memory(
    project_id: str,
    request: InitializeMemoryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Initialize memory for a project with foundational elements"""
    return memory_service._update_project_memory(
        project_id=project_id,
        data={
            "tone": request.tone,
            "genre": request.genre,
            "visual_style": request.visual_style,
            "color_grade": request.color_grade,
            "lighting_mood": request.lighting_mood,
            "reference_urls": request.reference_urls
        },
        agent_id=user_id,
        task_id=None
    )


# ==================== SCENE MEMORY ====================

@router.post("/{project_id}/scene")
def update_scene_memory(
    project_id: str,
    request: SceneMemoryRequest,
    agent_id: str = "system",
    user_id: str = Depends(get_current_user_id)
):
    """Update scene-specific memory"""
    
    data = {
        "scene_id": request.scene_id
    }
    
    if request.location_name:
        data["location_name"] = request.location_name
    if request.time_of_day:
        data["time_of_day"] = request.time_of_day
    if request.weather:
        data["weather"] = request.weather
    if request.camera_choice:
        data["camera_choice"] = request.camera_choice
    if request.lighting_note:
        data["lighting_note"] = request.lighting_note
    if request.color_palette:
        data["color_palette"] = request.color_palette
    if request.generated_shot:
        data["generated_shot"] = request.generated_shot
    if request.approved_shot:
        data["approved_shot"] = request.approved_shot
    
    return memory_service.update_memory(
        project_id=project_id,
        memory_type=MemoryType.SCENE,
        data=data,
        agent_id=agent_id
    )


# ==================== CHARACTER MEMORY ====================

@router.post("/{project_id}/character")
def update_character_memory(
    project_id: str,
    request: CharacterMemoryRequest,
    agent_id: str = "system",
    user_id: str = Depends(get_current_user_id)
):
    """Update character-specific memory"""
    
    data = request.model_dump()
    
    return memory_service.update_memory(
        project_id=project_id,
        memory_type=MemoryType.CHARACTER,
        data=data,
        agent_id=agent_id
    )


@router.post("/reference-analysis/store")
def store_reference_analysis(request: ReferenceAnalysisStoreRequest):
    return memory_store.store_reference_analysis(
        request.project_id,
        request.reference_analysis if isinstance(request.reference_analysis, dict) else {},
    )


@router.post("/reference-analysis/retrieve")
def retrieve_reference_memory(request: ReferenceMemoryRetrieveRequest):
    return memory_store.retrieve_relevant_memory(
        request.project_id,
        request.context if isinstance(request.context, dict) else {},
    )


@router.post("/reference-analysis/delete")
def delete_reference_memory(request: ReferenceMemoryDeleteRequest):
    return memory_store.delete_reference(
        request.project_id,
        request.reference_id,
    )


# ==================== STYLE MEMORY ====================

@router.post("/{project_id}/style")
def update_style_memory(
    project_id: str,
    request: StyleMemoryRequest,
    agent_id: str = "system",
    user_id: str = Depends(get_current_user_id)
):
    """Update style memory"""
    
    data = request.model_dump(exclude_none=True)
    
    return memory_service.update_memory(
        project_id=project_id,
        memory_type=MemoryType.STYLE,
        data=data,
        agent_id=agent_id
    )


# ==================== REVIEW MEMORY ====================

@router.post("/{project_id}/review")
def update_review_memory(
    project_id: str,
    request: ReviewMemoryRequest,
    agent_id: str = "system",
    user_id: str = Depends(get_current_user_id)
):
    """Store review/feedback memory"""
    
    data = request.model_dump()
    data["feedback_type"] = data.get("feedback_type", "agent")
    
    return memory_service.update_memory(
        project_id=project_id,
        memory_type=MemoryType.REVIEW,
        data=data,
        agent_id=agent_id
    )


# ==================== CONTRADICTION CHECK ====================

@router.get("/{project_id}/check-contradiction")
def check_contradiction(
    project_id: str,
    key: str,
    value: Any,
    user_id: str = Depends(get_current_user_id)
):
    """Check if a value would contradict existing memory"""
    return memory_service.check_contradiction(project_id, key, value)


# ==================== AGENT CONTEXT ====================

@router.get("/{project_id}/agent-context")
def get_agent_context(
    project_id: str,
    agent_role: str,
    scene_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Get relevant memory context for an agent"""
    return memory_service.get_context_for_agent(project_id, agent_role, scene_id)


# ==================== VERSION HISTORY ====================

@router.get("/{project_id}/versions")
def get_memory_versions(
    project_id: str,
    key: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Get version history for memory"""
    return memory_service.get_versions(project_id, key)


# ==================== DEBUG ENDPOINT ====================

@router.get("/{project_id}/debug")
def debug_memory(
    project_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Optional debug endpoint for memory inspection
    
    Returns:
    - All memory entries
    - Version history
    - Cached state
    - Storage state
    """
    all_memory = memory_service.get_all_memory(project_id)
    
    return {
        "project_id": project_id,
        "memory": all_memory,
        "cache_stats": {
            "project_cached": project_id in memory_service._cache,
            "scene_cache_count": len(memory_service._scene_cache.get(project_id, {})),
            "character_cache_count": len(memory_service._character_cache.get(project_id, {})),
            "style_cached": project_id in memory_service._style_cache
        },
        "storage_connected": memory_service.storage is not None
    }
