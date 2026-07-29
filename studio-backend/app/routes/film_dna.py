"""
Film DNA router.

GET /api/f51/studio/projects/{project_id}/film-dna
POST /api/f51/studio/projects/{project_id}/film-dna/refresh

Exposes the persistent Film DNA profile that captures the film's established
visual language, emotional arc, tonal identity, and character trajectory.

Advisory only: does not mutate canonical project state.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.film_dna_service import film_dna_service

router = APIRouter(
    prefix="/api/f51/studio",
    tags=["film-dna"],
)


# ── Response models ───────────────────────────────────────────────────────────

class VisualLanguage(BaseModel):
    dominant_motifs: List[str] = Field(default_factory=list)
    color_palette_notes: str = ""
    recurring_shot_types: List[str] = Field(default_factory=list)
    lighting_character: str = ""


class EmotionalArc(BaseModel):
    opening_register: str = ""
    closing_register: str = ""
    peak_tension_scene: str = ""
    arc_shape: str = ""


class TonalIdentity(BaseModel):
    primary_tone: str = ""
    secondary_tone: Optional[str] = None
    tone_consistency: str = ""
    genre_signals: List[str] = Field(default_factory=list)


class CharacterRosterEntry(BaseModel):
    name: str
    scenes_present: int
    first_appearance: str
    last_appearance: str
    emotional_trajectory: str


class FilmDNAResponse(BaseModel):
    film_id: str
    visual_language: VisualLanguage
    emotional_arc: EmotionalArc
    tonal_identity: TonalIdentity
    character_roster: List[CharacterRosterEntry]
    character_journeys: Dict[str, Any]
    arc_completeness: Dict[str, Any]
    production_notes: List[str]
    uncertainty_notes: List[str]
    generated_at: str
    scene_count: int
    version_id: str


class RefreshResponse(BaseModel):
    status: str = "rebuilding"
    message: str = "Film DNA rebuild triggered. Poll GET endpoint for updated DNA."


# ── Background rebuild task ───────────────────────────────────────────────────

async def _rebuild_film_dna_task(project_id: str):
    """Background task to rebuild Film DNA from current graph state."""
    await film_dna_service.rebuild_background(project_id)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/film-dna", response_model=FilmDNAResponse)
async def get_film_dna(project_id: str) -> FilmDNAResponse:
    """
    Return the current Film DNA profile for a project.

    Returns an honest empty state if fewer than 3 scenes exist.
    Advisory only — does not mutate project state.
    """
    try:
        return FilmDNAResponse(**(await film_dna_service.get(project_id)))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/projects/{project_id}/film-dna/refresh", response_model=RefreshResponse)
async def refresh_film_dna(
    project_id: str,
    background_tasks: BackgroundTasks,
) -> RefreshResponse:
    """
    Trigger a fresh rebuild of the Film DNA from current graph state.

    Returns immediately with status "rebuilding".
    Client should poll GET endpoint for updated DNA.

    Advisory only — does not mutate canonical project state.
    """
    try:
        film_dna_service.ensure_project_exists(project_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Project not found")

    # Trigger background rebuild.
    background_tasks.add_task(_rebuild_film_dna_task, project_id)

    return RefreshResponse(
        status="rebuilding",
        message="Film DNA rebuild triggered. Poll GET endpoint for updated DNA.",
    )


@router.get("/projects/{project_id}/character-journeys")
async def get_character_journeys(project_id: str) -> Dict[str, Any]:
    """
    Return character journey map for a project.

    Traces each named character's emotional and knowledge state across every
    scene they appear in. Shows dramatic irony, knowledge gaps, and unresolved
    knowledge.

    Uses cached version from Film DNA if available, otherwise builds fresh.

    Advisory only — does not mutate project state.
    """
    try:
        return await film_dna_service.character_journeys(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/projects/{project_id}/arc-completeness")
async def get_arc_completeness(project_id: str) -> Dict[str, Any]:
    """
    Return arc completeness analysis for a project.

    Analyzes whether the film's emotional arc resolves across all scenes in order.
    Assesses tension curve shape and resolution quality.

    Uses cached version from Film DNA if available, otherwise builds fresh.

    Advisory only — does not mutate project state.
    """
    try:
        return await film_dna_service.arc_completeness(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
