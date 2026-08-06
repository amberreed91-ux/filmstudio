from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CanonicalWorkflowStatus = Literal[
    "blueprint_approved",
    "previs_generated",
    "previs_approved",
    "package_ready",
    "render_queued",
    "render_completed",
    "render_failed",
    "screening_ready",
    "screening_approved",
    "editorial_analyzed",
    "editorial_decided",
    "cut_updated",
    "cut_approved",
    "revision_pending",
    "revision_completed",
    "revision_failed",
]


class CanonicalWorkflowRun(BaseModel):
    run_id: str
    project_id: str
    script_id: str
    scene_id: str
    blueprint_id: str
    blueprint_version_id: str
    status: CanonicalWorkflowStatus
    context_hash: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class CanonicalWorkflowTransition(BaseModel):
    transition_id: str
    run_id: str
    idempotency_key: str
    from_status: CanonicalWorkflowStatus
    to_status: CanonicalWorkflowStatus
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class BeginCanonicalWorkflowRequest(BaseModel):
    script_id: str
    sequence_id: str = ""
    beat_ids: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    confirmed: bool = False
    approved_by: str = "creator"
    artifact_ids: list[str] = Field(default_factory=list)


class RenderWorkflowRequest(BaseModel):
    provider: str = "simulated"
    retry_confirmed: bool = False


class EditorialWorkflowRequest(BaseModel):
    revision_emphasis: Literal["emotional_residue", "structural_clarity", "balanced"] = "balanced"


class EditorialDecisionWorkflowRequest(BaseModel):
    analysis_id: str
    decision_id: str
    confirmed: bool = False


class FilmCutWorkflowRequest(BaseModel):
    confirmed: bool = False


class RevisionWorkflowRequest(BaseModel):
    original_job_id: str
    revision_prompt: str
    revision_reason: str
    changed_fields: list[str] = Field(default_factory=list)
    confirmed: bool = False


class RevisionRenderWorkflowRequest(BaseModel):
    provider: str = "simulated"


class MemoryWorkflowRequest(BaseModel):
    confirmed: bool = False
    saved_by: str = "creator"
    summary: str = ""


class CanonicalWorkflowResponse(BaseModel):
    run: CanonicalWorkflowRun
    transitions: list[CanonicalWorkflowTransition] = Field(default_factory=list)
