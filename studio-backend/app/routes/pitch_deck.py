"""
Pitch Deck API Routes.

Endpoints for generating and retrieving pitch decks.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.pitch_deck_service import pitch_deck_service

logger = logging.getLogger("studio-pitch-deck-routes")

router = APIRouter(prefix="/api/f51/studio/projects", tags=["pitch-deck"])

class GeneratePitchDeckRequest(BaseModel):
    """Request body for generating a pitch deck."""
    target_audience: str = "general"  # "festival" | "investor" | "general"


@router.post("/{project_id}/pitch-deck")
async def generate_pitch_deck(project_id: str, request: GeneratePitchDeckRequest):
    """
    Generate a pitch deck for a project.
    
    Args:
        project_id: The project identifier.
        request:    Pitch deck options (target audience).
    
    Returns:
        The generated pitch deck with slides and metadata.
    """
    # Validate target audience
    if request.target_audience not in ["festival", "investor", "general"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_audience: {request.target_audience}. Must be 'festival', 'investor', or 'general'."
        )
    
    try:
        deck = await pitch_deck_service.generate_pitch_deck(
            project_id=project_id,
            target_audience=request.target_audience,
        )
        
        return deck
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate pitch deck: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate pitch deck: {str(e)}")


@router.get("/{project_id}/pitch-decks")
async def list_pitch_decks(project_id: str, limit: int = 10):
    """
    List pitch decks for a project, most recent first.
    
    Args:
        project_id: The project identifier.
        limit:      Maximum number of decks to return (default 10).
    
    Returns:
        List of deck summaries.
    """
    try:
        decks = pitch_deck_service.list_pitch_decks(project_id, limit=limit)
        return {"decks": decks}
    
    except Exception as e:
        logger.error(f"Failed to list pitch decks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list pitch decks: {str(e)}")


@router.get("/{project_id}/pitch-decks/{deck_id}")
async def get_pitch_deck(project_id: str, deck_id: str):
    """
    Get a specific pitch deck.
    
    Args:
        project_id: The project identifier.
        deck_id:    The deck identifier.
    
    Returns:
        The full pitch deck.
    """
    try:
        return pitch_deck_service.get_pitch_deck(project_id, deck_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pitch deck: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get pitch deck: {str(e)}")
