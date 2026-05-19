from __future__ import annotations

from pydantic import BaseModel


class EditingSuggestion(BaseModel):
    suggestion_type: str
    priority: str = "medium"
    title: str
    recommendation: str
    rationale: str = ""
    target_scene_id: str = ""
    advisory_only: bool = True

