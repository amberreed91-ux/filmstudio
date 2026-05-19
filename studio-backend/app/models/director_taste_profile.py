from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class DirectorTasteProfile(BaseModel):
    preferred_pacing: str = "balanced"
    preferred_framing: str = "mixed"
    emotional_tendencies: List[str] = Field(default_factory=list)
    dialogue_density: str = "medium"
    lighting_tendencies: List[str] = Field(default_factory=list)
    transition_preferences: List[str] = Field(default_factory=list)
    favorite_providers: List[str] = Field(default_factory=list)
    accepted_shots: int = 0
    regenerated_shots: int = 0
    preferred_emotional_arcs: List[str] = Field(default_factory=list)
    preferred_visual_styles: List[str] = Field(default_factory=list)
    creator_override_authority: str = "preserved"
    recommendations: List[Dict[str, str]] = Field(default_factory=list)

