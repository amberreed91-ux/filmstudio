from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def editorial_utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


EditorialAnalysisDepth = Literal["preview", "standard", "deep"]
EditorialApplyMode = Literal["metadata_only", "update_cut", "next_stitch"]
EditorialDecisionType = Literal[
    "trim",
    "hold",
    "extend_reaction",
    "reorder_scene",
    "replace_transition",
    "protect_silence",
    "compress_escalation",
    "delay_reveal",
    "restore_motif_callback",
    "flag_manual_review",
]
EditorialTargetType = Literal["scene", "shot", "transition", "sequence", "final_package"]


class EditorialEvidenceRef(BaseModel):
    source_type: str
    source_id: str
    project_id: str
    scene_id: str = ""
    shot_id: str = ""
    timestamp_seconds: float | None = None
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorialTimelineClip(BaseModel):
    clip_id: str
    scene_id: str = ""
    shot_id: str = ""
    output_url: str = ""
    status: str = ""
    duration_seconds: float | None = None
    order_index: int = 0
    evidence_refs: list[EditorialEvidenceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorialPacingDiagnostic(BaseModel):
    diagnostic_id: str
    section_id: str = ""
    read: str
    recommendation: str = ""
    evidence_refs: list[EditorialEvidenceRef] = Field(default_factory=list)
    uncertainty_note: str = ""
    advisory_only: bool = True


class EditorialRhythmDiagnostic(BaseModel):
    diagnostic_id: str
    read: str
    rhythm_pattern: str = ""
    risk: str = ""
    evidence_refs: list[EditorialEvidenceRef] = Field(default_factory=list)
    uncertainty_note: str = ""
    advisory_only: bool = True


class EditorialEmotionalFlowDiagnostic(BaseModel):
    read: str
    tension_curve: str = ""
    emotional_residue: str = ""
    risk_points: list[str] = Field(default_factory=list)
    evidence_refs: list[EditorialEvidenceRef] = Field(default_factory=list)
    uncertainty_note: str = ""
    advisory_only: bool = True


class EditorialTransitionAdvisory(BaseModel):
    transition_id: str
    from_scene_id: str
    to_scene_id: str
    recommended_transition_type: str = "cut"
    duration_seconds: float | None = None
    rationale: str
    continuity_impact: str = ""
    emotional_impact: str = ""
    rhythm_impact: str = ""
    evidence_refs: list[EditorialEvidenceRef] = Field(default_factory=list)
    stitching_hint: dict[str, Any] = Field(default_factory=dict)
    advisory_only: bool = True


class EditorialDecision(BaseModel):
    decision_id: str
    decision_type: EditorialDecisionType
    target_type: EditorialTargetType
    target_id: str
    from_scene_id: str = ""
    to_scene_id: str = ""
    recommendation: str
    rationale: str
    expected_story_effect: str = ""
    risk_if_ignored: str = ""
    evidence_refs: list[EditorialEvidenceRef] = Field(default_factory=list)
    uncertainty_note: str = ""
    application_status: str = "advisory"
    metadata: dict[str, Any] = Field(default_factory=dict)
    advisory_only: bool = True


class EditorialAnalysisRequest(BaseModel):
    source_package_id: str = ""
    source_cut_id: str = ""
    analysis_depth: EditorialAnalysisDepth = "standard"
    include_shot_boundaries: bool = True
    include_frame_analysis: bool = True
    revision_emphasis: Literal["emotional_residue", "structural_clarity", "balanced"] = "balanced"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorialAnalysisRecord(BaseModel):
    analysis_id: str
    project_id: str
    source_cut_id: str = "default"
    source_package_id: str = ""
    context_hash: str
    analysis_status: str = "complete"
    analysis_scope: str = "project"
    overall_read: str
    pacing_diagnostics: list[EditorialPacingDiagnostic] = Field(default_factory=list)
    rhythm_diagnostics: list[EditorialRhythmDiagnostic] = Field(default_factory=list)
    emotional_flow: EditorialEmotionalFlowDiagnostic
    transition_advisories: list[EditorialTransitionAdvisory] = Field(default_factory=list)
    edit_decisions: list[EditorialDecision] = Field(default_factory=list)
    reasoning_trace: list[str] = Field(default_factory=list)
    low_data_reasons: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=editorial_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)
    advisory_only: bool = True


class EditorialApplyRequest(BaseModel):
    decision_ids: list[str] = Field(default_factory=list)
    apply_mode: EditorialApplyMode = "metadata_only"
    expected_context_hash: str = ""
    creator_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorialApplyResult(BaseModel):
    application_id: str
    project_id: str
    analysis_id: str
    decision_ids: list[str] = Field(default_factory=list)
    source_cut_id: str = "default"
    result_cut_id: str = ""
    application_status: str = "applied"
    applied_effects: list[str] = Field(default_factory=list)
    skipped_decisions: list[str] = Field(default_factory=list)
    advisory_notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=editorial_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)
    advisory_only: bool = True
