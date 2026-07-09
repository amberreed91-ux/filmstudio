from __future__ import annotations

from pydantic import BaseModel


class AmbientAudioTrack(BaseModel):
    track_id: str
    scene_id: str
    layer: int = 1
    ambience_type: str
    intensity: float = 0.5
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    provider_hint: str = "local"
