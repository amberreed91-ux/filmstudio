from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Shared timestamp helper for derived film-intelligence models."""
    return datetime.utcnow().isoformat() + "Z"


class SetupPayoffSummary(BaseModel):
    """
    Derived setup/payoff summary.

    This is intentionally not a canonical source of truth. It is a conservative
    rollup from film memory, structure, and optional recurrence metadata.
    """

    source_type: str = ""
    source_id: str = ""
    label: str = ""
    introduced_scene: str = ""
    expected_payoff_scope: str = ""
    status: str = "tracked"
    grounded: bool = True
    supporting_scene_ids: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TensionIntelligenceSummary(BaseModel):
    """Derived summary for an unresolved tension."""

    tension_id: str = ""
    description: str = ""
    introduced_scene: str = ""
    expected_resolution_act: int = 0
    urgency_level: float = 0.5
    status: str = "open"
    grounded: bool = True
    notes: List[str] = Field(default_factory=list)


class MotifIntelligenceSummary(BaseModel):
    """Derived summary for a film motif's film-scale state."""

    motif_id: str = ""
    name: str = ""
    first_appearance_scene: str = ""
    recurrence_count: int = 0
    associated_theme: str = ""
    status: str = "tracked"
    grounded: bool = True
    notes: List[str] = Field(default_factory=list)


class CharacterArcProgressSummary(BaseModel):
    """
    Conservative character arc rollup.

    These summaries are grounded by explicit structure and character-presence
    data first. Any interpretation beyond simple coverage is labeled in notes.
    """

    character_id: str = ""
    scene_count: int = 0
    first_scene: str = ""
    last_scene: str = ""
    progression_status: str = "insufficient_data"
    grounded: bool = True
    notes: List[str] = Field(default_factory=list)


class SequenceIntelligenceSummary(BaseModel):
    """Derived sequence-level intelligence summary."""

    film_id: str
    sequence_id: str
    act_number: int = 0
    sequence_number: int = 0
    scene_count: int = 0
    progression_status: str = "insufficient_data"
    thematic_focus: str = ""
    emotional_contract: str = ""
    setup_payoff_summaries: List[SetupPayoffSummary] = Field(default_factory=list)
    tension_summaries: List[TensionIntelligenceSummary] = Field(default_factory=list)
    motif_summaries: List[MotifIntelligenceSummary] = Field(default_factory=list)
    arc_progression_summaries: List[CharacterArcProgressSummary] = Field(default_factory=list)
    grounding_sources: List[str] = Field(default_factory=list)
    heuristic_notes: List[str] = Field(default_factory=list)
    derived_only: bool = True
    generated_at: str = Field(default_factory=utc_now_iso)


class ActIntelligenceSummary(BaseModel):
    """Derived act-level intelligence summary."""

    film_id: str
    act_number: int
    act_type: str = ""
    scene_count: int = 0
    sequence_count: int = 0
    progression_status: str = "insufficient_data"
    thematic_focus: str = ""
    emotional_contract: str = ""
    setup_payoff_summaries: List[SetupPayoffSummary] = Field(default_factory=list)
    tension_summaries: List[TensionIntelligenceSummary] = Field(default_factory=list)
    motif_summaries: List[MotifIntelligenceSummary] = Field(default_factory=list)
    arc_progression_summaries: List[CharacterArcProgressSummary] = Field(default_factory=list)
    grounding_sources: List[str] = Field(default_factory=list)
    heuristic_notes: List[str] = Field(default_factory=list)
    derived_only: bool = True
    generated_at: str = Field(default_factory=utc_now_iso)


class FilmIntelligenceReport(BaseModel):
    """Derived full-film intelligence report."""

    film_id: str
    act_count: int = 0
    sequence_count: int = 0
    total_scenes: int = 0
    progression_status: str = "insufficient_data"
    act_summaries: List[ActIntelligenceSummary] = Field(default_factory=list)
    setup_payoff_summaries: List[SetupPayoffSummary] = Field(default_factory=list)
    tension_summaries: List[TensionIntelligenceSummary] = Field(default_factory=list)
    motif_summaries: List[MotifIntelligenceSummary] = Field(default_factory=list)
    arc_progression_summaries: List[CharacterArcProgressSummary] = Field(default_factory=list)
    emotional_trajectory_summary: Dict[str, object] = Field(default_factory=dict)
    grounding_sources: List[str] = Field(default_factory=list)
    heuristic_notes: List[str] = Field(default_factory=list)
    derived_only: bool = True
    generated_at: str = Field(default_factory=utc_now_iso)
