from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class VoiceDirectionCommand(BaseModel):
    raw_command: str
    normalized_command: str = ""
    emotional_changes: Dict[str, str] = Field(default_factory=dict)
    pacing_changes: Dict[str, str] = Field(default_factory=dict)
    visual_style_updates: Dict[str, str] = Field(default_factory=dict)
    advisory_only: bool = True
    requires_creator_approval: bool = True

