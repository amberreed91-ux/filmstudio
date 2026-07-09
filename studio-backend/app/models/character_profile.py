from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    """
    Additive character consistency profile used by prompt/context services.
    """

    character_id: str
    name: str = ""
    appearance_traits: List[str] = Field(default_factory=list)
    wardrobe: List[str] = Field(default_factory=list)
    visual_references: List[str] = Field(default_factory=list)
    voice_tone: str = ""
    emotional_baseline: str = ""
    facial_identity: str = ""
    silhouette: str = ""
    movement_style: str = ""
    emotional_behavior: str = ""
    speech_rhythm: str = ""
