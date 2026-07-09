from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class FilmVisualStyleProfile(BaseModel):
    """
    Additive film-level visual style lock profile for prompt/context services.
    """

    style_id: str
    style_name: str
    color_palette: List[str] = Field(default_factory=list)
    lighting_language: List[str] = Field(default_factory=list)
    lens_style: List[str] = Field(default_factory=list)
    camera_movement_style: List[str] = Field(default_factory=list)
    framing_patterns: List[str] = Field(default_factory=list)
    texture_keywords: List[str] = Field(default_factory=list)
