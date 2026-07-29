from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProductionDesignScope = Literal["project", "sequence", "scene", "shot", "asset"]
ProductionDesignStatus = Literal["draft", "active", "ready", "needs_creator_review", "low_data", "stale", "superseded", "failed"]
ProductionDesignConfidenceLabel = Literal["low_data", "emerging", "consistent", "strong", "conflicted"]
ProductionDesignReadinessLabel = Literal["ready", "needs_review", "blocked", "low_data"]
ProductionDesignEvidenceType = Literal[
    "script_scene",
    "scene_package",
    "project_memory",
    "film_memory",
    "character_memory",
    "creative_spine",
    "symbolism_node",
    "reference_asset",
    "character_reference_lock",
    "cinematic_language",
    "continuity_issue",
    "frame_analysis",
    "cinematic_memory",
    "render_job",
    "video_asset",
    "manual_note",
]
DesignAxisName = Literal[
    "environment",
    "architecture",
    "set_dressing",
    "props",
    "costume",
    "palette",
    "materials",
    "symbolism",
    "continuity",
    "negative_space",
]
DesignRenderSlot = Literal["environment", "style", "negative", "character"]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class ProductionDesignEvidenceRef(BaseModel):
    evidence_id: str
    source_type: ProductionDesignEvidenceType
    source_id: str
    field_path: str = ""
    scene_id: str | None = None
    shot_id: str | None = None
    character_id: str | None = None
    asset_id: str | None = None
    excerpt: str = ""
    relevance: str = ""
    reliability_label: ProductionDesignConfidenceLabel = "emerging"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    scope: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    summary: str = ""
    source_service: str = ""


class ProductionDesignSpineRef(BaseModel):
    constraint_id: str = ""
    field_name: str = ""
    severity: str = ""
    summary: str = ""
    applied: bool = True
    risk_if_ignored: str = ""


class SymbolicDesignRef(BaseModel):
    symbol_id: str
    motif: str = ""
    object_name: str = ""
    color: str = ""
    emotional_meaning: str = ""
    recurrence_context: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    confidence_label: ProductionDesignConfidenceLabel = "emerging"
    advisory_only: bool = True


class DesignMaterialPalette(BaseModel):
    palette_id: str
    color_family: list[str] = Field(default_factory=list)
    texture_family: list[str] = Field(default_factory=list)
    material_family: list[str] = Field(default_factory=list)
    light_response: str = ""
    emotional_rationale: str = ""
    continuity_notes: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class SetDressingElement(BaseModel):
    element_id: str
    label: str
    category: str = "background"
    placement: str = ""
    story_function: str = ""
    continuity_rule: str = ""
    should_appear: bool = True
    should_not_appear_reason: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class PropState(BaseModel):
    state_id: str
    prop_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    owner_character_id: str | None = None
    location: str = ""
    condition: str = "unchanged"
    visibility: str = "optional"
    handoff_state: str = ""
    meaning_in_this_beat: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class CostumeElement(BaseModel):
    element_id: str
    label: str
    garment_type: str = ""
    color: str = ""
    material: str = ""
    silhouette: str = ""
    condition: str = "clean"
    continuity_rule: str = ""
    story_reason_for_change: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class EnvironmentDesignProfile(BaseModel):
    profile_id: str
    project_id: str
    location_id: str | None = None
    location_name: str
    environment_type: str = ""
    era_logic: str = ""
    architecture: str = ""
    geography: str = ""
    weathering: str = ""
    practical_function: str = ""
    emotional_function: str = ""
    palette: DesignMaterialPalette | None = None
    set_dressing_rules: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    spine_refs: list[ProductionDesignSpineRef] = Field(default_factory=list)
    source_signature: str = ""
    status: ProductionDesignStatus = "ready"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PropContinuityRecord(BaseModel):
    prop_record_id: str
    project_id: str
    prop_id: str
    prop_name: str
    prop_type: str = "background"
    canonical_description: str = ""
    symbolic_refs: list[SymbolicDesignRef] = Field(default_factory=list)
    states: list[PropState] = Field(default_factory=list)
    recurrence_rule: str = ""
    continuity_constraints: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    source_signature: str = ""
    status: ProductionDesignStatus = "ready"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostumeContinuityRecord(BaseModel):
    costume_record_id: str
    project_id: str
    character_id: str
    character_name: str = ""
    scene_id: str | None = None
    shot_id: str | None = None
    costume_label: str = ""
    continuity_phase: str = "baseline"
    elements: list[CostumeElement] = Field(default_factory=list)
    palette_notes: str = ""
    silhouette_notes: str = ""
    deterioration_notes: str = ""
    identity_constraints: list[str] = Field(default_factory=list)
    reference_lock_ids: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    source_signature: str = ""
    status: ProductionDesignStatus = "ready"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignAxis(BaseModel):
    axis: DesignAxisName
    intent: str
    rationale: str = ""
    continuity_rule: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    confidence_label: ProductionDesignConfidenceLabel = "emerging"


class ProductionDesignRisk(BaseModel):
    risk_id: str
    category: str
    severity: Literal["advisory", "needs_attention"] = "advisory"
    summary: str
    downstream_impact: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    requires_creator_decision: bool = False


class ProductionDesignRevisionSuggestion(BaseModel):
    suggestion_id: str
    target_axis: DesignAxisName
    summary: str
    rationale: str
    render_slot: DesignRenderSlot | None = None
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class ProductionDesignRenderSlotSuggestion(BaseModel):
    slot: DesignRenderSlot
    suggestion: str
    rationale: str = ""
    budget_limit: int = 0
    budget_used: int = 0
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class ProductionDesignPlan(BaseModel):
    plan_id: str
    project_id: str
    scope: ProductionDesignScope = "scene"
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    status: ProductionDesignStatus = "ready"
    generated_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    model_version: str = "production-design-v1"
    source_signature: str = ""
    source_summary: str = ""
    environment_profile: EnvironmentDesignProfile | None = None
    prop_records: list[PropContinuityRecord] = Field(default_factory=list)
    costume_records: list[CostumeContinuityRecord] = Field(default_factory=list)
    set_dressing: list[SetDressingElement] = Field(default_factory=list)
    symbolic_refs: list[SymbolicDesignRef] = Field(default_factory=list)
    design_axes: list[ProductionDesignAxis] = Field(default_factory=list)
    material_palette: DesignMaterialPalette | None = None
    render_slot_suggestions: list[ProductionDesignRenderSlotSuggestion] = Field(default_factory=list)
    negative_design_constraints: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    spine_refs: list[ProductionDesignSpineRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    readiness_label: ProductionDesignReadinessLabel = "needs_review"
    blockers: list[str] = Field(default_factory=list)
    creator_note: str = ""
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignObservation(BaseModel):
    observation_id: str
    project_id: str
    plan_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    status: ProductionDesignStatus = "ready"
    observation_scope: ProductionDesignScope = "asset"
    observed_environment: str = ""
    observed_set_dressing_tags: list[str] = Field(default_factory=list)
    observed_prop_candidates: list[str] = Field(default_factory=list)
    observed_costume_candidates: list[str] = Field(default_factory=list)
    observed_palette_tags: list[str] = Field(default_factory=list)
    observed_material_tags: list[str] = Field(default_factory=list)
    observed_symbolic_candidates: list[str] = Field(default_factory=list)
    keyframe_ids: list[str] = Field(default_factory=list)
    analysis_ids: list[str] = Field(default_factory=list)
    cinematic_memory_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence_label: ProductionDesignConfidenceLabel = "low_data"
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignAssessment(BaseModel):
    assessment_id: str
    project_id: str
    plan_id: str
    observation_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    status: ProductionDesignStatus = "ready"
    generated_at: str = Field(default_factory=_now)
    source_signature: str = ""
    alignment_summary: str = ""
    matched_axes: list[DesignAxisName] = Field(default_factory=list)
    drift_axes: list[DesignAxisName] = Field(default_factory=list)
    missing_required_elements: list[str] = Field(default_factory=list)
    unexpected_elements: list[str] = Field(default_factory=list)
    prop_state_conflicts: list[str] = Field(default_factory=list)
    costume_continuity_conflicts: list[str] = Field(default_factory=list)
    environment_continuity_conflicts: list[str] = Field(default_factory=list)
    palette_material_drift: list[str] = Field(default_factory=list)
    symbolic_risks: list[str] = Field(default_factory=list)
    risks: list[ProductionDesignRisk] = Field(default_factory=list)
    revision_suggestions: list[ProductionDesignRevisionSuggestion] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    spine_refs: list[ProductionDesignSpineRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    requires_creator_attention: bool = False
    confidence_label: ProductionDesignConfidenceLabel = "emerging"
    advisory_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignRenderContext(BaseModel):
    plan_id: str
    project_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    environment_direction: str = ""
    style_direction: str = ""
    character_direction: str = ""
    negative_design_direction: str = ""
    slot_suggestions: list[ProductionDesignRenderSlotSuggestion] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    budget: dict[str, int] = Field(default_factory=dict)
    advisory_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignPlanRequest(BaseModel):
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scope: ProductionDesignScope = "scene"
    scene_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvironmentDesignProfileRequest(BaseModel):
    location_name: str
    location_id: str | None = None
    scene_id: str | None = None
    scene_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PropContinuityRecordRequest(BaseModel):
    prop_name: str
    prop_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    scene_context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostumeContinuityRecordRequest(BaseModel):
    character_id: str
    character_name: str = ""
    scene_id: str | None = None
    shot_id: str | None = None
    scene_context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignObservationRequest(BaseModel):
    plan_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    keyframe_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignAssessmentRequest(BaseModel):
    plan_id: str
    observation_id: str
    create_crew_reasoning: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignRenderContextRequest(BaseModel):
    plan_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    provider: str = "internal"
    max_prompt_length: int = 512


class ProductionDesignDecisionRequest(BaseModel):
    decision_text: str
    inferred_tradeoff: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    plan_id: str | None = None
    prop_record_id: str | None = None
    costume_record_id: str | None = None
    environment_profile_id: str | None = None
    assessment_id: str | None = None
    saved_by: str = "creator"
    explicit_save: bool = True


class ProductionDesignDecisionUpdateRequest(BaseModel):
    decision_text: str | None = None
    inferred_tradeoff: str | None = None
    forgotten_at: str | None = None


class ProductionDesignDecisionProjection(BaseModel):
    decision_id: str
    project_id: str
    decision_text: str
    inferred_tradeoff: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    plan_id: str | None = None
    prop_record_id: str | None = None
    costume_record_id: str | None = None
    environment_profile_id: str | None = None
    assessment_id: str | None = None
    saved_by: str = "creator"
    saved_at: str = Field(default_factory=_now)
    memory_entry_id: str | None = None
    editable: bool = True
    forgotten_at: str | None = None


class ProductionDesignPlanResponse(BaseModel):
    plan: ProductionDesignPlan
    reasoning_record_id: str = ""
    stale_existing_plan_ids: list[str] = Field(default_factory=list)
    advisory_only: bool = True


class ProductionDesignObservationResponse(BaseModel):
    observation: ProductionDesignObservation
    advisory_only: bool = True


class ProductionDesignAssessmentResponse(BaseModel):
    assessment: ProductionDesignAssessment
    advisory_only: bool = True


class ProductionDesignDepartmentSignal(BaseModel):
    project_id: str
    state: str = "idle"
    active_plan_count: int = 0
    stale_plan_count: int = 0
    recent_assessment_count: int = 0
    needs_creator_attention: bool = False
    summary: str = ""
    last_plan_id: str | None = None
    last_assessment_id: str | None = None
    advisory_only: bool = True
