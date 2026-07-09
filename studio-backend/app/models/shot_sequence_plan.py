from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ShotSequenceStep(BaseModel):
    shot_type: str
    order: int
    pacing_weight: float = 0.5
    emotional_intensity: float = 0.5
    transition_hint: str = ""


class ShotSequencePlan(BaseModel):
    scene_id: str
    pacing_profile: str = "balanced"
    emotional_curve: str = "escalating"
    cinematic_flow: str = "establish_to_detail"
    steps: List[ShotSequenceStep] = Field(default_factory=list)
