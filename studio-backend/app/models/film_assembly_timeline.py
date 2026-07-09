from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class FilmAssemblyTimeline(BaseModel):
    timeline_id: str
    ordered_scenes: List[str] = Field(default_factory=list)
    audio_tracks: List[Dict[str, str | float | int]] = Field(default_factory=list)
    subtitles: List[Dict[str, str | float]] = Field(default_factory=list)
    transitions: List[Dict[str, str | float]] = Field(default_factory=list)
    title_cards: List[Dict[str, str | float]] = Field(default_factory=list)
    credits: List[Dict[str, str | float]] = Field(default_factory=list)
