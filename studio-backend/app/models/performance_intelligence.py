from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceSourceType = Literal[
    "script_scene",
    "script_character",
    "character_memory",
    "creative_memory",
    "director_memory",
    "film_memory",
    "continuity",
    "emotional_arc",
    "creative_spine",
    "prior_performance",
    "review",
]

UncertaintyLabel = Literal["insufficient_context", "emerging", "supported", "conflicted"]


class PerformanceEvidenceRef(BaseModel):
    evidence_id: str
    source_type: EvidenceSourceType
    source_id: str
    field_path: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    excerpt: str = ""
    relevance: str = ""
    reliability_label: UncertaintyLabel = "emerging"


class PerformanceUncertainty(BaseModel):
    label: UncertaintyLabel = "emerging"
    reason: str = ""


class SubtextRead(BaseModel):
    spoken_intent: str = ""
    hidden_intent: str = ""
    mask: str = ""
    contradiction: str = ""
    risk: str = ""
    evidence_refs: list[PerformanceEvidenceRef] = Field(default_factory=list)


class EmotionalContinuityRead(BaseModel):
    prior_state: str = ""
    current_state: str = ""
    transition_rationale: str = ""
    continuity_risk: str = ""
    suggested_restraint: str = ""
    evidence_refs: list[PerformanceEvidenceRef] = Field(default_factory=list)


class PerformanceBeat(BaseModel):
    beat_id: str
    beat_index: int
    beat_label: str = ""
    visible_action: str = ""
    internal_action: str = ""
    dialogue_subtext: str = ""
    physical_direction: str = ""
    voice_direction: str = ""
    camera_relevance: str = ""
    evidence_refs: list[PerformanceEvidenceRef] = Field(default_factory=list)


class RelationshipPerformanceRead(BaseModel):
    relationship_read_id: str
    scene_id: str
    character_a: str
    character_b: str
    relationship_state: str = ""
    pressure: str = ""
    power_shift: str = ""
    trust_state: str = ""
    conflict_residue: str = ""
    uncertainty: PerformanceUncertainty = Field(default_factory=PerformanceUncertainty)
    evidence_refs: list[PerformanceEvidenceRef] = Field(default_factory=list)


class CharacterPerformanceBrief(BaseModel):
    brief_id: str
    scene_id: str
    character_id: str
    character_name: str
    objective: str = ""
    obstacle: str = ""
    tactic: str = ""
    emotional_start: str = ""
    emotional_end: str = ""
    mask: str = ""
    reveal: str = ""
    subtext_summary: str = ""
    continuity_note: str = ""
    uncertainty: PerformanceUncertainty = Field(default_factory=PerformanceUncertainty)
    subtext: SubtextRead = Field(default_factory=SubtextRead)
    emotional_continuity: EmotionalContinuityRead = Field(default_factory=EmotionalContinuityRead)
    beats: list[PerformanceBeat] = Field(default_factory=list)
    evidence_refs: list[PerformanceEvidenceRef] = Field(default_factory=list)
    advisory_only: bool = True


class PerformanceContextBundle(BaseModel):
    project_id: str
    scene_id: str
    shot_id: str | None = None
    character_ids: list[str] = Field(default_factory=list)
    prompt_lines: list[str] = Field(default_factory=list)
    voice_lines: list[str] = Field(default_factory=list)
    audio_lines: list[str] = Field(default_factory=list)
    screening_lines: list[str] = Field(default_factory=list)
    evidence_refs: list[PerformanceEvidenceRef] = Field(default_factory=list)
    advisory_only: bool = True


class PerformanceAnalysisRequest(BaseModel):
    scene_id: str | None = None
    character_ids: list[str] | None = None
    scope: Literal["scene", "project"] = "scene"
    persist: bool = False
    include_context_bundles: bool = True


class PerformanceAnalysisResponse(BaseModel):
    analysis_id: str
    project_id: str
    scene_id: str | None = None
    analysis_scope: Literal["scene", "project"] = "scene"
    status: Literal["complete", "partial", "stale"] = "complete"
    generated_at: str
    source_signature: str
    model_version: str = "performance-intelligence-v1"
    summary: str = ""
    briefs: list[CharacterPerformanceBrief] = Field(default_factory=list)
    relationship_reads: list[RelationshipPerformanceRead] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    guardrail_report: dict[str, Any] = Field(default_factory=dict)
    context_bundle: PerformanceContextBundle | None = None
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class PerformanceSaveDecisionRequest(BaseModel):
    scene_id: str | None = None
    character_id: str | None = None
    source_brief_id: str | None = None
    decision_text: str
    inferred_tradeoff: str = ""
    saved_by: str = "creator"
    save_to_project_memory: bool = False


class PerformanceUpdateDecisionRequest(BaseModel):
    decision_text: str | None = None
    inferred_tradeoff: str | None = None


class PerformanceDecisionMemoryProjection(BaseModel):
    decision_id: str
    project_id: str
    scene_id: str | None = None
    character_id: str | None = None
    source_brief_id: str | None = None
    decision_text: str
    inferred_tradeoff: str = ""
    saved_by: str = "creator"
    saved_at: str
    memory_entry_id: str | None = None
    editable: bool = True
    forgotten_at: str | None = None


class PerformanceDepartmentSignal(BaseModel):
    role: str = "Performance Intelligence"
    status: Literal["active", "standby"] = "standby"
    signal: str = "performance context pending"
    evidence_count: int = 0
    advisory: str = ""
    advisory_only: bool = True
