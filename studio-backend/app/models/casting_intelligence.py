from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CastingModality = Literal["human", "ai", "hybrid", "voice_only", "visual_only", "placeholder"]
CastingDecisionStatus = Literal["draft", "recommended", "approved", "superseded", "rejected", "stale"]
CastingReadinessLabel = Literal["ready", "needs_review", "blocked", "not_requested"]
ConsentStatus = Literal["not_required", "pending", "granted", "limited", "revoked", "expired", "blocked"]
CastingUncertaintyLabel = Literal["insufficient_context", "emerging", "supported", "conflicted"]
CastingEvidenceSourceType = Literal[
    "script_character",
    "script_scene",
    "role_breakdown",
    "talent_profile",
    "consent_record",
    "audition_submission",
    "audition_evaluation",
    "performance_brief",
    "performance_audio_profile",
    "character_identity",
    "continuity",
    "creative_spine",
    "creative_memory",
    "director_memory",
    "film_memory",
    "manual_note",
    "render_job",
    "screening_assessment",
]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class CastingEvidenceRef(BaseModel):
    evidence_id: str
    source_type: CastingEvidenceSourceType
    source_id: str
    field_path: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    role_id: str | None = None
    talent_id: str | None = None
    audition_id: str | None = None
    excerpt: str = ""
    relevance: str = ""
    reliability_label: CastingUncertaintyLabel = "emerging"


class CastingMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    scope: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    summary: str = ""
    source_service: str = ""


class CastingSpineRef(BaseModel):
    constraint_id: str = ""
    field_name: str = ""
    summary: str = ""
    applied: bool = True
    risk_if_ignored: str = ""


class CastingRoleBreakdown(BaseModel):
    role_id: str
    project_id: str
    character_id: str
    character_name: str
    role_label: str = ""
    scene_ids: list[str] = Field(default_factory=list)
    role_size: Literal["lead", "supporting", "day_player", "background", "unknown"] = "unknown"
    performance_demands: list[str] = Field(default_factory=list)
    voice_requirements: list[str] = Field(default_factory=list)
    visual_requirements: list[str] = Field(default_factory=list)
    consent_requirements: list[str] = Field(default_factory=list)
    audition_sides: list[str] = Field(default_factory=list)
    source_signature: str = ""
    status: CastingDecisionStatus = "draft"
    readiness_label: CastingReadinessLabel = "needs_review"
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CastingMemoryRef] = Field(default_factory=list)
    spine_refs: list[CastingSpineRef] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class TalentConsentRecord(BaseModel):
    consent_id: str
    project_id: str
    talent_id: str
    modality: str
    status: ConsentStatus = "pending"
    scope: list[str] = Field(default_factory=list)
    evidence_ref_id: str | None = None
    granted_by: str = ""
    granted_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    limitations: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class TalentProfile(BaseModel):
    talent_id: str
    project_id: str
    display_name: str
    modality: CastingModality = "human"
    capabilities: list[str] = Field(default_factory=list)
    vocal_characteristics: list[str] = Field(default_factory=list)
    visual_characteristics: list[str] = Field(default_factory=list)
    performance_strengths: list[str] = Field(default_factory=list)
    availability_label: Literal["available", "limited", "unknown", "unavailable"] = "unknown"
    provider_bindings: list[dict[str, Any]] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    consent_records: list[TalentConsentRecord] = Field(default_factory=list)
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class AuditionPackage(BaseModel):
    package_id: str
    project_id: str
    role_id: str
    character_id: str
    title: str = ""
    instructions: str = ""
    sides: list[str] = Field(default_factory=list)
    required_media: list[str] = Field(default_factory=list)
    performance_intent: str = ""
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    status: Literal["draft", "open", "closed", "stale"] = "open"
    advisory_only: bool = True


class AuditionSubmission(BaseModel):
    audition_id: str
    project_id: str
    package_id: str
    role_id: str
    talent_id: str
    media_refs: list[dict[str, Any]] = Field(default_factory=list)
    submitted_text: str = ""
    submitted_at: str = Field(default_factory=_now)
    consent_snapshot: list[TalentConsentRecord] = Field(default_factory=list)
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    status: Literal["submitted", "evaluated", "withdrawn", "stale"] = "submitted"
    advisory_only: bool = True


class AuditionEvaluation(BaseModel):
    evaluation_id: str
    project_id: str
    audition_id: str
    role_id: str
    talent_id: str
    fit_read: str = ""
    performance_alignment: str = ""
    voice_alignment: str = ""
    visual_alignment: str = ""
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    uncertainty_label: CastingUncertaintyLabel = "emerging"
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    advisory_only: bool = True


class CastingRecommendation(BaseModel):
    recommendation_id: str
    project_id: str
    role_id: str
    talent_id: str
    audition_id: str | None = None
    evaluation_id: str | None = None
    recommendation: str = ""
    rationale: str = ""
    creative_fit_read: str = ""
    consent_readiness: CastingReadinessLabel = "needs_review"
    readiness_label: CastingReadinessLabel = "needs_review"
    blockers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    uncertainty_label: CastingUncertaintyLabel = "emerging"
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CastingMemoryRef] = Field(default_factory=list)
    spine_refs: list[CastingSpineRef] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    source_signature: str = ""
    created_at: str = Field(default_factory=_now)
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class HybridCastingAssignment(BaseModel):
    assignment_id: str
    project_id: str
    role_id: str
    contributors: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    readiness_label: CastingReadinessLabel = "needs_review"


class CastingDecision(BaseModel):
    decision_id: str
    project_id: str
    role_id: str
    character_id: str
    talent_id: str
    recommendation_id: str | None = None
    audition_id: str | None = None
    evaluation_id: str | None = None
    status: CastingDecisionStatus = "approved"
    active: bool = True
    approved_by: str = "creator"
    approved_at: str = Field(default_factory=_now)
    decision_rationale: str = ""
    hybrid_assignment: HybridCastingAssignment | None = None
    provider_requirements: list[str] = Field(default_factory=list)
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CastingMemoryRef] = Field(default_factory=list)
    readiness_label: CastingReadinessLabel = "needs_review"
    blockers: list[str] = Field(default_factory=list)
    source_signature: str = ""
    supersedes_decision_id: str | None = None
    superseded_by_decision_id: str | None = None
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class CastingProjection(BaseModel):
    projection_id: str
    project_id: str
    role_id: str | None = None
    character_id: str | None = None
    active_decisions: list[CastingDecision] = Field(default_factory=list)
    talent_profiles: list[TalentProfile] = Field(default_factory=list)
    readiness_label: CastingReadinessLabel = "not_requested"
    blockers: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=_now)
    advisory_only: bool = True


class CastingReadinessReport(BaseModel):
    report_id: str
    project_id: str
    scope: Literal["project", "role"] = "project"
    role_id: str | None = None
    readiness_label: CastingReadinessLabel = "needs_review"
    covered_roles: int = 0
    total_roles: int = 0
    stale_decision_count: int = 0
    consent_blocker_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_refs: list[CastingEvidenceRef] = Field(default_factory=list)
    generated_at: str = Field(default_factory=_now)
    advisory_only: bool = True


class CastingDecisionMemoryProjection(BaseModel):
    decision_id: str
    project_id: str
    role_id: str | None = None
    character_id: str | None = None
    talent_id: str | None = None
    casting_decision_id: str | None = None
    decision_text: str
    inferred_tradeoff: str = ""
    saved_by: str = "creator"
    saved_at: str = Field(default_factory=_now)
    memory_entry_id: str | None = None
    editable: bool = True
    forgotten_at: str | None = None


class CastingDepartmentSignal(BaseModel):
    role: str = "Casting Intelligence"
    status: Literal["active", "standby"] = "standby"
    signal: str = "casting coverage pending"
    readiness_label: CastingReadinessLabel = "not_requested"
    covered_roles: int = 0
    total_roles: int = 0
    blocker_count: int = 0
    stale_decision_count: int = 0
    evidence_count: int = 0
    advisory: str = ""
    advisory_only: bool = True


class RoleBreakdownBuildRequest(BaseModel):
    force_refresh: bool = False
    persist: bool = True


class RoleBreakdownBuildResponse(BaseModel):
    roles: list[CastingRoleBreakdown]
    stale_role_ids: list[str] = Field(default_factory=list)
    advisory_only: bool = True


class TalentProfileRequest(BaseModel):
    display_name: str
    modality: CastingModality = "human"
    capabilities: list[str] = Field(default_factory=list)
    vocal_characteristics: list[str] = Field(default_factory=list)
    visual_characteristics: list[str] = Field(default_factory=list)
    performance_strengths: list[str] = Field(default_factory=list)
    availability_label: Literal["available", "limited", "unknown", "unavailable"] = "unknown"
    provider_bindings: list[dict[str, Any]] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    consent_records: list[TalentConsentRecord] = Field(default_factory=list)
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TalentProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    modality: CastingModality | None = None
    capabilities: list[str] | None = None
    vocal_characteristics: list[str] | None = None
    visual_characteristics: list[str] | None = None
    performance_strengths: list[str] | None = None
    availability_label: Literal["available", "limited", "unknown", "unavailable"] | None = None
    provider_bindings: list[dict[str, Any]] | None = None
    reference_asset_ids: list[str] | None = None
    consent_records: list[TalentConsentRecord] | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class AuditionPackageRequest(BaseModel):
    title: str = ""
    instructions: str = ""
    sides: list[str] = Field(default_factory=list)
    required_media: list[str] = Field(default_factory=list)
    performance_intent: str = ""


class AuditionSubmissionRequest(BaseModel):
    talent_id: str
    media_refs: list[dict[str, Any]] = Field(default_factory=list)
    submitted_text: str = ""


class CastingRecommendationRequest(BaseModel):
    candidate_talent_ids: list[str] | None = None
    persist: bool = True


class CastingDecisionRequest(BaseModel):
    role_id: str
    talent_id: str
    recommendation_id: str | None = None
    audition_id: str | None = None
    evaluation_id: str | None = None
    approved_by: str = "creator"
    decision_rationale: str = ""
    hybrid_assignment: HybridCastingAssignment | None = None
    provider_requirements: list[str] = Field(default_factory=list)
    allow_blocked_consent: bool = False
    save_to_project_memory: bool = False


class CastingReadinessRequest(BaseModel):
    scope: Literal["project", "role"] = "project"
    role_id: str | None = None


class CastingSaveDecisionRequest(BaseModel):
    decision_text: str
    inferred_tradeoff: str = ""
    role_id: str | None = None
    character_id: str | None = None
    talent_id: str | None = None
    casting_decision_id: str | None = None
    saved_by: str = "creator"
    save_to_project_memory: bool = False


class CastingDecisionUpdateRequest(BaseModel):
    decision_text: str | None = None
    inferred_tradeoff: str | None = None
