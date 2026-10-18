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


class WorkflowProviderRequest(BaseModel):
    # Previs ignores provider; Checkpoint 5 previs is simulated-only. Provider applies to production renders / revisions only.
    provider: str | None = Field(default=None, min_length=1, pattern=r"^\S+$")


class RenderWorkflowRequest(WorkflowProviderRequest):
    retry_confirmed: bool = False
    # D5 guarded single-shot render (additive; whole-package callers omit these).
    # When storyboard_shot_ids is present it must name EXACTLY the package shots
    # to render; more than one shot, or an omitted filter, additionally requires
    # allow_full_package=True. acknowledge_unknown_cost=True is required when no
    # Runway estimate is available for a selected shot.
    storyboard_shot_ids: list[str] | None = None
    allow_full_package: bool = False
    acknowledge_unknown_cost: bool = False
    duration_seconds: int | None = None


class RenderEstimateRequest(BaseModel):
    # Dry-run cost probe. Never creates jobs and never submits; contacts Runway
    # with dryRun:true only when called (the UI calls it solely from Check cost).
    storyboard_shot_ids: list[str] | None = None
    duration_seconds: int | None = None


class RenderEstimateShot(BaseModel):
    storyboard_shot_id: str
    shot_id: str = ""
    planned_duration_seconds: int | None = None
    effective_duration_seconds: int | None = None
    estimated_credits: float | None = None
    resolved_model: str | None = None
    estimate_available: bool = False


class RenderEstimateResponse(BaseModel):
    run_id: str
    ceiling_credits: float
    ceiling_env_var: str = "RUNWAY_RENDER_MAX_CREDITS"
    estimates: list[RenderEstimateShot] = Field(default_factory=list)


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


class RevisionRenderWorkflowRequest(WorkflowProviderRequest):
    pass


class MemoryWorkflowRequest(BaseModel):
    confirmed: bool = False
    saved_by: str = "creator"
    summary: str = ""


class CanonicalWorkflowResponse(BaseModel):
    run: CanonicalWorkflowRun
    transitions: list[CanonicalWorkflowTransition] = Field(default_factory=list)


class CanonicalWorkflowSceneContext(BaseModel):
    script_id: str
    sequence_id: str = ""
    beat_ids: list[str] = Field(default_factory=list)


class CanonicalWorkflowListResponse(BaseModel):
    runs: list[CanonicalWorkflowRun] = Field(default_factory=list)
    current_blueprint_version_id: str = ""
    scene_context: CanonicalWorkflowSceneContext | None = None
