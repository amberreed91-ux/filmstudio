from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class SceneAssembly(BaseModel):
    assembly_id: str
    ordered_shots: List[str] = Field(default_factory=list)
    runtime: float = 0.0
    transition_map: Dict[str, Dict[str, str | float]] = Field(default_factory=dict)
