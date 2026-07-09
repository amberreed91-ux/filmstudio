from __future__ import annotations

from pydantic import BaseModel


class EmotionalArcProfile(BaseModel):
    scene_id: str
    emotional_intensity: float = 0.5
    tension: float = 0.5
    vulnerability: float = 0.5
    escalation: float = 0.5
    catharsis: float = 0.0
