from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ColoristScope = Literal["project", "act", "sequence", "scene", "shot", "take", "asset", "package"]
ColoristStatus = Literal["draft", "active", "low_data", "stale", "superseded", "failed", "verified"]
ColoristConfidenceLabel = Literal["low_data", "emerging", "consistent", "strong"]
ColorAxis = Literal[
    "palette",
    "contrast",
    "exposure",
    "saturation",
    "temperature",
    "hue_bias",
    "skin_tone",
    "density",
    "highlight_rolloff",
    "shadow_detail",
    "emotional_color",
    "motif_color",
    "reference_match",
]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class ColorEvidenceRef(BaseModel):
    ref_type: str
    ref_id: str = ""
    label: str = ""
    summary: str = ""
    source_service: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    scope: str = ""
    source_service: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    summary: str = ""


class ColorSpineRef(BaseModel):
    constraint_id: str = ""
    field_name: str = ""
    severity: str = ""
    summary: str = ""
    applied: bool = True


class ColorStyleRef(BaseModel):
    style_id: str = ""
    style_type: str = ""
    summary: str = ""
    source_service: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorContinuityRef(BaseModel):
    continuity_id: str = ""
    category: str = ""
    summary: str = ""
    source_service: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorReferenceAssetRef(BaseModel):
    reference_id: str = ""
    asset_id: str = ""
    label: str = ""
    allowed_use: str = ""
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorDepartmentHandoffRef(BaseModel):
    target_department: str
    summary: str
    requirement: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorPaletteFamily(BaseModel):
    family_id: str
    name: str
    colors: list[str] = Field(default_factory=list)
    emotional_use: str = ""
    allowed_variations: list[str] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorEmotionalRule(BaseModel):
    rule_id: str
    emotional_state: str
    color_direction: str
    rationale: str = ""
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorMotifRule(BaseModel):
    rule_id: str
    motif_id: str = ""
    motif_name: str = ""
    color_obligation: str
    allowed_evolution: str = ""
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorGradeAxisPlan(BaseModel):
    axis: ColorAxis
    intent: str
    rationale: str = ""
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "emerging"


class ColorRenderSlotSuggestion(BaseModel):
    slot: Literal["color", "lighting", "style"] = "color"
    suggestion: str
    rationale: str = ""
    budget_limit: int = 0
    budget_used: int = 0
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorRisk(BaseModel):
    risk_id: str
    category: str
    severity: Literal["advisory", "needs_attention"] = "advisory"
    summary: str
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    downstream_impact: list[str] = Field(default_factory=list)
    requires_creator_decision: bool = False


class ColorRevisionSuggestion(BaseModel):
    suggestion_id: str
    target_axis: ColorAxis
    summary: str
    rationale: str
    render_slot: Literal["color", "lighting", "style"] | None = "color"
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorArcBeat(BaseModel):
    beat_id: str
    scope: ColoristScope
    scope_id: str = ""
    emotional_turn: str = ""
    color_direction: str = ""
    rationale: str = ""
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorSceneVerificationRead(BaseModel):
    scene_id: str
    status: ColoristStatus = "low_data"
    summary: str = ""
    held_axes: list[ColorAxis] = Field(default_factory=list)
    drift_axes: list[ColorAxis] = Field(default_factory=list)
    assessment_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)


class ColorLookBible(BaseModel):
    look_bible_id: str
    project_id: str
    scope: ColoristScope = "project"
    act_id: str | None = None
    sequence_id: str | None = None
    status: ColoristStatus = "active"
    source_fingerprint: str = ""
    look_fingerprint: str = ""
    title: str = "Project Color Look"
    show_lut_intent: str = ""
    palette_families: list[ColorPaletteFamily] = Field(default_factory=list)
    contrast_philosophy: str = ""
    saturation_philosophy: str = ""
    temperature_philosophy: str = ""
    skin_tone_protection: str = ""
    highlight_behavior: str = ""
    shadow_behavior: str = ""
    grain_or_texture_intent: str = ""
    emotional_color_rules: list[ColorEmotionalRule] = Field(default_factory=list)
    motif_color_rules: list[ColorMotifRule] = Field(default_factory=list)
    allowed_evolution: list[str] = Field(default_factory=list)
    forbidden_drift: list[str] = Field(default_factory=list)
    reference_asset_refs: list[ColorReferenceAssetRef] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ColorMemoryRef] = Field(default_factory=list)
    spine_refs: list[ColorSpineRef] = Field(default_factory=list)
    style_refs: list[ColorStyleRef] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "emerging"
    creator_note: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColoristLookPlan(BaseModel):
    plan_id: str
    project_id: str
    look_bible_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    take_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scope: ColoristScope = "scene"
    status: ColoristStatus = "active"
    source_fingerprint: str = ""
    look_fingerprint: str = ""
    source_summary: str = ""
    intended_palette: list[str] = Field(default_factory=list)
    palette_rationale: str = ""
    contrast_intent: str = ""
    exposure_intent: str = ""
    saturation_intent: str = ""
    temperature_intent: str = ""
    hue_bias_intent: str = ""
    density_intent: str = ""
    skin_tone_intent: str = ""
    highlight_intent: str = ""
    shadow_intent: str = ""
    emotional_color_intent: str = ""
    motif_color_obligations: list[ColorMotifRule] = Field(default_factory=list)
    reference_match_targets: list[ColorReferenceAssetRef] = Field(default_factory=list)
    grade_axes: list[ColorGradeAxisPlan] = Field(default_factory=list)
    render_slot_suggestions: list[ColorRenderSlotSuggestion] = Field(default_factory=list)
    revision_guardrails: list[str] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ColorMemoryRef] = Field(default_factory=list)
    spine_refs: list[ColorSpineRef] = Field(default_factory=list)
    style_refs: list[ColorStyleRef] = Field(default_factory=list)
    continuity_refs: list[ColorContinuityRef] = Field(default_factory=list)
    department_handoffs: list[ColorDepartmentHandoffRef] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "emerging"
    creator_note: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    stale: bool = False
    stale_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorPaletteContinuityRecord(BaseModel):
    palette_record_id: str
    project_id: str
    scope: ColoristScope = "project"
    scene_id: str | None = None
    sequence_id: str | None = None
    character_id: str | None = None
    location_id: str | None = None
    prop_id: str | None = None
    motif_id: str | None = None
    source_type: str = "project"
    source_id: str = ""
    canonical_color_description: str = ""
    allowed_variations: list[str] = Field(default_factory=list)
    story_motivated_changes: list[str] = Field(default_factory=list)
    continuity_risks: list[ColorRisk] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ColorMemoryRef] = Field(default_factory=list)
    spine_refs: list[ColorSpineRef] = Field(default_factory=list)
    style_refs: list[ColorStyleRef] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "emerging"
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorStoryArc(BaseModel):
    color_arc_id: str
    project_id: str
    look_bible_id: str | None = None
    status: ColoristStatus = "active"
    source_fingerprint: str = ""
    arc_summary: str = ""
    act_color_beats: list[ColorArcBeat] = Field(default_factory=list)
    sequence_color_beats: list[ColorArcBeat] = Field(default_factory=list)
    scene_color_beats: list[ColorArcBeat] = Field(default_factory=list)
    motif_evolution: list[ColorMotifRule] = Field(default_factory=list)
    emotional_turn_color_map: list[ColorEmotionalRule] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    allowed_breaks: list[str] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ColorMemoryRef] = Field(default_factory=list)
    spine_refs: list[ColorSpineRef] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "emerging"
    creator_note: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorGradeObservation(BaseModel):
    observation_id: str
    project_id: str
    plan_id: str | None = None
    look_bible_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    scope: ColoristScope = "asset"
    status: ColoristStatus = "active"
    observed_palette: list[str] = Field(default_factory=list)
    observed_palette_summary: str = ""
    observed_contrast: str = ""
    observed_exposure: str = ""
    observed_saturation: str = ""
    observed_temperature: str = ""
    observed_hue_bias: str = ""
    observed_density: str = ""
    observed_skin_tone_notes: str = ""
    observed_highlight_behavior: str = ""
    observed_shadow_behavior: str = ""
    observed_mood_tags: list[str] = Field(default_factory=list)
    observed_lighting_tags: list[str] = Field(default_factory=list)
    keyframe_ids: list[str] = Field(default_factory=list)
    analysis_ids: list[str] = Field(default_factory=list)
    cinematic_memory_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "low_data"
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorMatchAssessment(BaseModel):
    assessment_id: str
    project_id: str
    plan_id: str
    observation_id: str
    look_bible_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    status: ColoristStatus = "active"
    match_summary: str = ""
    held_axes: list[ColorAxis] = Field(default_factory=list)
    drift_axes: list[ColorAxis] = Field(default_factory=list)
    emotional_color_read: str = ""
    continuity_read: str = ""
    scene_matching_read: str = ""
    risks: list[ColorRisk] = Field(default_factory=list)
    revision_suggestions: list[ColorRevisionSuggestion] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ColorMemoryRef] = Field(default_factory=list)
    spine_refs: list[ColorSpineRef] = Field(default_factory=list)
    style_refs: list[ColorStyleRef] = Field(default_factory=list)
    continuity_refs: list[ColorContinuityRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    requires_creator_attention: bool = False
    confidence_label: ColoristConfidenceLabel = "emerging"
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorRenderContext(BaseModel):
    plan_id: str
    project_id: str
    look_bible_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    color_direction: str = ""
    style_direction: str = ""
    lighting_color_notes: str = ""
    slot_suggestions: list[ColorRenderSlotSuggestion] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    reference_asset_refs: list[ColorReferenceAssetRef] = Field(default_factory=list)
    budget: dict[str, int] = Field(default_factory=dict)
    advisory_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorFinalVerification(BaseModel):
    verification_id: str
    project_id: str
    package_id: str | None = None
    asset_id: str | None = None
    look_bible_id: str | None = None
    status: ColoristStatus = "active"
    source_fingerprint: str = ""
    coverage_summary: str = ""
    scene_verification_reads: list[ColorSceneVerificationRead] = Field(default_factory=list)
    sequence_matching_risks: list[ColorRisk] = Field(default_factory=list)
    final_revision_suggestions: list[ColorRevisionSuggestion] = Field(default_factory=list)
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    assessment_ids: list[str] = Field(default_factory=list)
    confidence_label: ColoristConfidenceLabel = "emerging"
    creator_note: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColoristDecisionProjection(BaseModel):
    decision_id: str
    project_id: str
    decision_text: str
    inferred_tradeoff: str = ""
    scene_id: str | None = None
    plan_id: str | None = None
    assessment_id: str | None = None
    look_bible_id: str | None = None
    saved_by: str = "creator"
    saved_at: str = Field(default_factory=_now)
    memory_entry_id: str | None = None
    editable: bool = True
    forgotten_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorLookBibleRequest(BaseModel):
    scope: ColoristScope = "project"
    act_id: str | None = None
    sequence_id: str | None = None
    title: str = "Project Color Look"
    project_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColoristLookPlanRequest(BaseModel):
    look_bible_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    take_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scope: ColoristScope = "scene"
    scene_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorGradeObservationRequest(BaseModel):
    plan_id: str | None = None
    look_bible_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    keyframe_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorMatchAssessmentRequest(BaseModel):
    plan_id: str
    observation_id: str
    create_crew_reasoning: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorRenderContextRequest(BaseModel):
    plan_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    provider: str = "internal"
    max_prompt_length: int = 512


class ColorStoryArcRequest(BaseModel):
    look_bible_id: str | None = None
    project_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorFinalVerificationRequest(BaseModel):
    package_id: str | None = None
    asset_id: str | None = None
    look_bible_id: str | None = None
    assessment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColoristDecisionSaveRequest(BaseModel):
    decision_text: str
    inferred_tradeoff: str = ""
    scene_id: str | None = None
    plan_id: str | None = None
    assessment_id: str | None = None
    look_bible_id: str | None = None
    saved_by: str = "creator"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColorLookBibleResponse(BaseModel):
    look_bible: ColorLookBible
    reasoning_record_id: str = ""
    stale_existing_look_bible_ids: list[str] = Field(default_factory=list)
    advisory_only: bool = True


class ColoristLookPlanResponse(BaseModel):
    plan: ColoristLookPlan
    reasoning_record_id: str = ""
    stale_existing_plan_ids: list[str] = Field(default_factory=list)
    advisory_only: bool = True


class ColorGradeObservationResponse(BaseModel):
    observation: ColorGradeObservation
    advisory_only: bool = True


class ColorMatchAssessmentResponse(BaseModel):
    assessment: ColorMatchAssessment
    advisory_only: bool = True


class ColorStoryArcResponse(BaseModel):
    story_arc: ColorStoryArc
    reasoning_record_id: str = ""
    advisory_only: bool = True


class ColorFinalVerificationResponse(BaseModel):
    verification: ColorFinalVerification
    reasoning_record_id: str = ""
    advisory_only: bool = True


class ColoristDepartmentSignal(BaseModel):
    project_id: str
    scene_id: str | None = None
    asset_id: str | None = None
    latest_plan_id: str | None = None
    latest_assessment_id: str | None = None
    latest_verification_id: str | None = None
    state: str = "idle"
    summary: str = ""
    needs_creator_attention: bool = False
    confidence_label: ColoristConfidenceLabel = "low_data"
    evidence_refs: list[ColorEvidenceRef] = Field(default_factory=list)
    advisory_only: bool = True
