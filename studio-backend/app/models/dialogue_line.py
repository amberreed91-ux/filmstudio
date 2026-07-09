from __future__ import annotations

from pydantic import BaseModel


class DialogueLine(BaseModel):
    line_id: str
    scene_id: str
    character_id: str
    character_name: str
    text: str
    emotional_subtext: str = ""
    pacing_tag: str = "balanced"
    voice_style_hint: str = ""
