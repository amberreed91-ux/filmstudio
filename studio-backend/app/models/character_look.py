from __future__ import annotations

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CharacterLookCandidate(BaseModel):
    image_url: str
    role: str
    source: str
    generation_id: str | None = None
    matches_current_profile: bool = True


class CharacterCastingGeneration(BaseModel):
    id: str
    status: Literal["queued", "running", "complete", "partial", "failed"]
    requested_count: int
    completed_count: int
    direction: str
    error: str | None = None
    created_at: str
    matches_current_profile: bool


class CharacterCastingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_profile_revision: str = Field(min_length=1, max_length=100)
    request_id: UUID
    direction: str = Field(default="", max_length=1200)


class CharacterLook(BaseModel):
    character_id: str
    project_id: str
    name: str
    age: str | None
    description: str
    physical_description: str
    visual_prompt_summary: str
    status: Literal["draft", "locked"]
    version: int
    profile_revision: str
    face_image_url: str | None
    body_image_url: str | None
    approved_at: str | None
    candidates: list[CharacterLookCandidate]
    casting_generations: list[CharacterCastingGeneration] = Field(default_factory=list)


class CharacterLookList(BaseModel):
    looks: list[CharacterLook]


class CharacterLookApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_profile_revision: str = Field(min_length=1, max_length=100)
    face_image_url: str = Field(min_length=1, max_length=4096)
    body_image_url: str | None = Field(default=None, max_length=4096)


class CharacterLookRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_profile_revision: str = Field(min_length=1, max_length=100)


class CharacterLookUploadResponse(BaseModel):
    image_url: str
