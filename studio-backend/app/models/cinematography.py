from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CameraGrammarScope = Literal["scene", "shot", "take", "asset"]
CameraGrammarStatus = Literal["draft", "active", "low_data", "stale", "superseded", "failed"]
CameraGrammarConfidenceLabel = Literal["low_data", "emerging", "consistent", "strong"]


class CameraGrammarEvidenceRef(BaseModel):
    ref_type: str
    ref_id: str = ""
    label: str = ""
    summary: str = ""
    source_service: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    source_service: str = ""
    scene_id: str | None = None
    summary: str = ""


class CameraGrammarSpineRef(BaseModel):
    constraint_id: str = ""
    field_name: str = ""
    severity: str = ""
    summary: str = ""
    applied: bool = True


class CameraGrammarAxis(BaseModel):
    axis: str
    intent: str
    rationale: str = ""
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)
    confidence_label: CameraGrammarConfidenceLabel = "emerging"


class CameraGrammarRenderSlotSuggestion(BaseModel):
    slot: Literal["camera", "lighting"]
    suggestion: str
    rationale: str = ""
    budget_limit: int = 0
    budget_used: int = 0
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)


class CameraGrammarRisk(BaseModel):
    risk_id: str
    category: str
    severity: Literal["advisory", "needs_attention"] = "advisory"
    summary: str
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)
    requires_creator_decision: bool = False


class CameraGrammarRevisionSuggestion(BaseModel):
    suggestion_id: str
    target_axis: str
    summary: str
    rationale: str
    render_slot: Literal["camera", "lighting"] | None = None
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)


class CameraGrammarPlan(BaseModel):
    plan_id: str
    project_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    take_id: str | None = None
    render_job_id: str | None = None
    plan_scope: CameraGrammarScope = "scene"
    status: CameraGrammarStatus = "active"
    source_fingerprint: str = ""
    source_summary: str = ""
    grammar_axes: list[CameraGrammarAxis] = Field(default_factory=list)
    composition_intent: str = "neutral"
    lens_intent: str = "unspecified"
    movement_intent: str = "none"
    lighting_intent: str = "unspecified"
    framing_intent: str = "medium"
    depth_strategy: str = ""
    blocking_strategy: str = ""
    screen_direction_strategy: str = ""
    visual_storytelling_rationale: str = ""
    render_slot_suggestions: list[CameraGrammarRenderSlotSuggestion] = Field(default_factory=list)
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CameraGrammarMemoryRef] = Field(default_factory=list)
    spine_refs: list[CameraGrammarSpineRef] = Field(default_factory=list)
    confidence_label: CameraGrammarConfidenceLabel = "emerging"
    creator_note: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarObservation(BaseModel):
    observation_id: str
    project_id: str
    plan_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    status: CameraGrammarStatus = "active"
    observation_scope: CameraGrammarScope = "asset"
    observed_composition: str = ""
    observed_lighting: str = ""
    observed_camera_notes: str = ""
    observed_framing_tags: list[str] = Field(default_factory=list)
    observed_lighting_tags: list[str] = Field(default_factory=list)
    observed_movement_evidence: str = ""
    keyframe_ids: list[str] = Field(default_factory=list)
    analysis_ids: list[str] = Field(default_factory=list)
    cinematic_memory_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)
    confidence_label: CameraGrammarConfidenceLabel = "low_data"
    limitations: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarAssessment(BaseModel):
    assessment_id: str
    project_id: str
    plan_id: str
    observation_id: str
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    status: CameraGrammarStatus = "active"
    alignment_summary: str = ""
    matched_axes: list[str] = Field(default_factory=list)
    drift_axes: list[str] = Field(default_factory=list)
    risks: list[CameraGrammarRisk] = Field(default_factory=list)
    revision_suggestions: list[CameraGrammarRevisionSuggestion] = Field(default_factory=list)
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CameraGrammarMemoryRef] = Field(default_factory=list)
    spine_refs: list[CameraGrammarSpineRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    requires_creator_attention: bool = False
    confidence_label: CameraGrammarConfidenceLabel = "emerging"
    advisory_only: bool = True
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarRenderContext(BaseModel):
    plan_id: str
    project_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    camera_direction: str = ""
    lighting_direction: str = ""
    slot_suggestions: list[CameraGrammarRenderSlotSuggestion] = Field(default_factory=list)
    evidence_refs: list[CameraGrammarEvidenceRef] = Field(default_factory=list)
    budget: dict[str, int] = Field(default_factory=dict)
    advisory_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarPlanRequest(BaseModel):
    scene_id: str | None = None
    shot_id: str | None = None
    take_id: str | None = None
    render_job_id: str | None = None
    plan_scope: CameraGrammarScope = "scene"
    scene_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarObservationRequest(BaseModel):
    plan_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    keyframe_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarAssessmentRequest(BaseModel):
    plan_id: str
    observation_id: str
    create_crew_reasoning: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGrammarRenderContextRequest(BaseModel):
    plan_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    provider: str = "internal"
    max_prompt_length: int = 512


class CameraGrammarPlanResponse(BaseModel):
    plan: CameraGrammarPlan
    reasoning_record_id: str = ""
    stale_existing_plan_ids: list[str] = Field(default_factory=list)
    advisory_only: bool = True


class CameraGrammarObservationResponse(BaseModel):
    observation: CameraGrammarObservation
    advisory_only: bool = True


class CameraGrammarAssessmentResponse(BaseModel):
    assessment: CameraGrammarAssessment
    advisory_only: bool = True
