from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


WORKFLOW_STAGES: List[str] = [
    "concept",
    "screenplay_outline",
    "scene_generation",
    "shot_sequencing",
    "render_orchestration",
    "audio_generation",
    "film_assembly",
    "final_export",
]


class WorkflowStageState(BaseModel):
    stage: str
    status: str = "queued"
    progress: int = 0
    activity: str = ""
    updated_by: str = ""


class GenerateShortFilmWorkflow(BaseModel):
    workflow_id: str
    concept: str
    manual_override: bool = False
    manual_overrides: Dict[str, Any] = Field(default_factory=dict)
    stages: List[WorkflowStageState] = Field(default_factory=list)
    crew_updates: List[Dict[str, str]] = Field(default_factory=list)
    runtime_metadata: Dict[str, Any] = Field(default_factory=dict)

