from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.script_intelligence_service import script_intelligence_service
from app.services.character_mind_simulator import character_mind_simulator
from app.services.memory import memory_service
from app.services.stability import ValidationError, StateError
from app.models.memory import MemoryType
from app.models.script_intelligence import (
    SceneBreakdownAnalysis,
    CharacterArcAnalysis,
    ToneConsistencyAnalysis,
    PromptGenerationResult,
    SceneTransitionIntelligence,
    SceneSoundIntelligence,
    CharacterMindSimulation,
    CharacterSimulationHistory,
)

router = APIRouter(prefix="/api/projects", tags=["script-intelligence"])


# ── Feature 1: Scene Breakdown Endpoint ────────────────────────────

@router.get("/{project_id}/script-analysis/breakdown", response_model=SceneBreakdownAnalysis)
async def get_scene_breakdown(project_id: str):
    """
    Analyze screenplay structure: act structure, pacing, transitions.
    
    Phase 1 implementation.
    
    Args:
        project_id: Project identifier
        
    Returns:
        SceneBreakdownAnalysis with act structure, pacing insights,
        and transition warnings (all using co-director voice).
        
    Raises:
        HTTPException 400: If project not found or insufficient scenes
        HTTPException 500: If analysis fails
    """
    # Validate input
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        # Call service (business logic)
        analysis = await script_intelligence_service.analyze_scene_breakdown(project_id)
        return analysis
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except StateError as e:
        # Server error (analysis failed)
        raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Feature 2: Character Arc Endpoint ──────────────────────────────

@router.get("/{project_id}/script-analysis/characters", response_model=CharacterArcAnalysis)
async def get_character_arcs(project_id: str):
    """
    Analyze character presence, arcs, and relationships.
    
    Phase 2 implementation.
    
    Args:
        project_id: Project identifier
        
    Returns:
        CharacterArcAnalysis with character inventory, arc gaps,
        and relationship matrix (all using co-director voice).
        
    Raises:
        HTTPException 400: If project not found or no characters detected
        HTTPException 500: If analysis fails
    """
    # Validate input
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        # Call service (business logic)
        analysis = await script_intelligence_service.analyze_character_arcs(project_id)
        return analysis
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except StateError as e:
        # Server error (analysis failed)
        raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Placeholder Endpoints for Future Phases ────────────────────────
# Phase 3: Tone Consistency Check
# Phase 4: Prompt Generation

@router.get("/{project_id}/script-analysis/tone", response_model=ToneConsistencyAnalysis)
async def get_tone_consistency(project_id: str):
    """
    Analyze tone consistency across scenes and detect jarring shifts.
    
    Phase 3 implementation.
    
    Args:
        project_id: Project identifier
        
    Returns:
        ToneConsistencyAnalysis with tone map, shift warnings,
        and consistency assessment (all using co-director voice).
        
    Raises:
        HTTPException 400: If project not found or insufficient scenes
        HTTPException 500: If analysis fails
    """
    # Validate input
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        # Call service (business logic)
        analysis = await script_intelligence_service.analyze_tone_consistency(project_id)
        return analysis
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except StateError as e:
        # Server error (analysis failed)
        raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Feature 4: Prompt Generation Endpoint ──────────────────────────

class PromptGenerationRequest(BaseModel):
    """Request body for prompt generation."""
    scene_ids: Optional[List[str]] = None  # If None, generate for all scenes


@router.post("/{project_id}/script-analysis/prompts", response_model=PromptGenerationResult)
async def generate_scene_prompts(project_id: str, request: PromptGenerationRequest):
    """
    Generate enhanced Runway-ready render prompts from scene descriptions.
    
    Phase 4 implementation.
    
    Args:
        project_id: Project identifier
        request: Optional scene_ids to generate prompts for (None = all scenes)
        
    Returns:
        PromptGenerationResult with enhanced prompts and style consistency note.
        
    Raises:
        HTTPException 400: If project not found or no scenes available
        HTTPException 500: If prompt generation fails
    """
    # Validate input
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        # Call service (business logic)
        result = await script_intelligence_service.generate_prompts(
            project_id=project_id,
            scene_ids=request.scene_ids
        )
        return result
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except StateError as e:
        # Server error (prompt generation failed)
        raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Feature 5: Transition Intelligence Endpoint ────────────────────────

@router.get("/{project_id}/script-analysis/transitions", response_model=SceneTransitionIntelligence)
async def get_transition_intelligence(project_id: str):
    """
    Analyze transition intelligence between consecutive scene pairs.
    
    Phase 5 implementation (Batch I).
    
    Args:
        project_id: Project identifier
        
    Returns:
        SceneTransitionIntelligence with transition advisories for all scene pairs.
        
    Raises:
        HTTPException 400: If project not found or insufficient scenes
        HTTPException 500: If analysis fails
    """
    # Validate input
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        # Call service (business logic)
        result = await script_intelligence_service.analyze_transition_intelligence(project_id)
        return result
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except StateError as e:
        # Server error (transition analysis failed)
        raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Feature 6: Sound Intelligence Endpoint ──────────────────────────────

@router.get("/{project_id}/script-analysis/sound", response_model=SceneSoundIntelligence)
async def get_sound_intelligence(project_id: str):
    """
    Analyze sound intelligence for all scenes.
    
    Phase 6 implementation (Batch I).
    
    Args:
        project_id: Project identifier
        
    Returns:
        SceneSoundIntelligence with sound advisories for all scenes.
        
    Raises:
        HTTPException 400: If project not found or no scenes
        HTTPException 500: If analysis fails
    """
    # Validate input
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        # Call service (business logic)
        result = await script_intelligence_service.analyze_sound_intelligence(project_id)
        return result
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Feature 7: Character Mind Simulator Endpoints ───────────────────

class CharacterSimRequest(BaseModel):
    query: str


@router.post("/{project_id}/characters/{character_id}/simulate", response_model=CharacterMindSimulation)
async def simulate_character(project_id: str, character_id: str, request: CharacterSimRequest):
    """
    Simulate character reaction to a specific situation.
    """
    try:
        return await character_mind_simulator.simulate(project_id, character_id, request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")


@router.get("/{project_id}/characters/{character_id}/history", response_model=CharacterSimulationHistory)
async def get_character_sim_history(project_id: str, character_id: str):
    """
    Retrieve last 5 simulation queries for a character.
    """
    return character_mind_simulator.get_history(character_id)


@router.post("/{project_id}/characters/{character_id}/notes")
async def save_sim_to_notes(project_id: str, character_id: str, simulation: CharacterMindSimulation):
    """
    Save simulation response to Director's Notes.
    """
    try:
        note_text = (
            f"Character Simulation: {simulation.character_name}\n"
            f"Reaction: {simulation.likely_reaction}\n"
            f"Reasoning: {simulation.reasoning}"
        )
        
        memory_service.update_memory(
            project_id=project_id,
            memory_type=MemoryType.REVIEW,
            data={
                "feedback_type": "director",
                "feedback_text": note_text,
                "character_id": character_id
            },
            agent_id="character-simulator"
        )
        return {"status": "success", "message": "Saved to Director's Notes"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save note: {str(e)}")
