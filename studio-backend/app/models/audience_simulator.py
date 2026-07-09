from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field

class AudienceReaction(BaseModel):
    """Reaction from a specific audience perspective."""
    audience_type: str # Casual audience, Cinephiles, Genre fans, Festival juries
    likely_reaction: str
    reasoning: str
    watch_out: str

class SceneAudienceSimulation(BaseModel):
    """Emotional audience simulation for a single scene."""
    scene_id: str
    audience_reactions: List[AudienceReaction] = Field(default_factory=list)
    interpretation_variance: str
    co_director_note: str

class ProjectAudienceSimulation(BaseModel):
    """Emotional audience simulation for the entire project sequence."""
    project_id: str
    audience_reactions: List[AudienceReaction] = Field(default_factory=list)
    scene_simulations: List[SceneAudienceSimulation] = Field(default_factory=list)
    co_director_note: str
