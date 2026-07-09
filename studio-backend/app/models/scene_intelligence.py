from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


MediaStatus = Literal["metadata_only", "video_uploaded"]
SourceType = Literal["json_metadata", "video", "hybrid"]


class SceneIntelligenceRecord(BaseModel):
    scene_id: str
    film_title: str
    scene_name: str
    intent: str = ""
    emotional_beat_arc: List[str] = Field(default_factory=list)
    camera_logic: List[str] = Field(default_factory=list)
    pacing_curve: List[str] = Field(default_factory=list)
    director_notes: str = ""
    media_status: MediaStatus = "metadata_only"
    video_file: Optional[str] = None
    source_type: SourceType = "json_metadata"
    created_at: str
    updated_at: str


class SceneIntelligenceImportResult(BaseModel):
    imported: int
    created: int
    updated: int
    records: List[SceneIntelligenceRecord]
