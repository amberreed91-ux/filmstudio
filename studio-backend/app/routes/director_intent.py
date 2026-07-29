"""
Director Intent router.

GET /api/f51/studio/projects/{project_id}/director-intent
POST /api/f51/studio/projects/{project_id}/director-intent

Exposes the director's creative intent for a project — the north star that
guides all downstream intelligence services.

Lightweight intake at project creation. Everything downstream uses this as
a north star.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.director_intent_service import director_intent_service

router = APIRouter(
    prefix="/api/f51/studio",
    tags=["director-intent"],
)


# ── Request/Response models ───────────────────────────────────────────────────

class DirectorIntentRequest(BaseModel):
    """Request model for updating director intent."""
    genre: Optional[str] = None
    tone_references: Optional[List[str]] = None
    emotional_target: Optional[str] = None
    visual_references: Optional[List[str]] = None
    what_success_looks_like: Optional[str] = None
    what_to_avoid: Optional[List[str]] = None


class DirectorIntentResponse(BaseModel):
    """Response model for director intent."""
    genre: Optional[str] = None
    tone_references: List[str] = Field(default_factory=list)
    emotional_target: Optional[str] = None
    visual_references: List[str] = Field(default_factory=list)
    what_success_looks_like: Optional[str] = None
    what_to_avoid: List[str] = Field(default_factory=list)
    captured_at: str = ""
    last_updated: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/director-intent", response_model=DirectorIntentResponse)
async def get_director_intent(project_id: str) -> DirectorIntentResponse:
    """
    Return the director intent for a project.

    Returns empty intent if none exists.
    """
    intent = director_intent_service.get(project_id)

    if intent is None:
        # Return empty intent structure
        return DirectorIntentResponse()

    return DirectorIntentResponse(**intent)


@router.post("/projects/{project_id}/director-intent", response_model=DirectorIntentResponse)
async def update_director_intent(
    project_id: str,
    intent_update: DirectorIntentRequest,
) -> DirectorIntentResponse:
    """
    Update director intent for a project.

    Merges with existing intent rather than replacing entirely.
    Only updates fields that are provided in the request.

    Returns the merged intent.
    """
    intent_dict = intent_update.model_dump(exclude_none=True)
    try:
        return DirectorIntentResponse(**director_intent_service.update(project_id, intent_dict))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
