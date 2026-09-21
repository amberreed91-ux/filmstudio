from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MediaStatus = Literal["metadata_only", "video_uploaded"]
SourceType = Literal["json_metadata", "video", "hybrid"]


class SceneEmotionalGuidance(BaseModel):
    """Advisory, one-sentence scene-level emotional guidance.

    Co-director voice — no scores or percentages. ``guidance`` and ``risk``
    stay empty when the available signals are too thin to say anything
    concrete.
    """

    scene_id: str
    project_id: str = ""
    rationale: str = ""
    emotional_work: str = ""
    guidance: str = ""
    risk: str = ""
    callbacks: list[dict[str, Any]] = Field(default_factory=list)
    advisory_only: bool = True
    auto_regeneration_triggered: bool = False


class SceneIntelligenceRecord(BaseModel):
    scene_id: str
    film_title: str
    scene_name: str
    intent: str = ""
    emotional_beat_arc: list[str] = Field(default_factory=list)
    camera_logic: list[str] = Field(default_factory=list)
    pacing_curve: list[str] = Field(default_factory=list)
    director_notes: str = ""
    media_status: MediaStatus = "metadata_only"
    video_file: str | None = None
    source_type: SourceType = "json_metadata"
    emotional_guidance: SceneEmotionalGuidance | None = None
    created_at: str
    updated_at: str


class SceneIntelligenceImportResult(BaseModel):
    imported: int
    created: int
    updated: int
    records: list[SceneIntelligenceRecord]
