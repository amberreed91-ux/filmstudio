from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class VideoAsset(BaseModel):
    asset_id: str
    project_id: str
    source_type: str
    source_url: Optional[str] = None
    local_path: Optional[str] = None
    title: str
    description: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    status: str = "registered"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}


class VideoMetadataMatch(BaseModel):
    match_id: str
    asset_id: str
    metadata_id: str
    project_id: Optional[str] = None
    match_status: str = "proposed"
    match_confidence: float = 0.0
    match_reason: str = ""
    matched_fields: List[str] = []
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}
