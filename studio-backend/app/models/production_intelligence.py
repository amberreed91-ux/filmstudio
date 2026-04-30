from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Shared timestamp helper for production-intelligence models."""
    return datetime.utcnow().isoformat() + "Z"


class ProductionPackageProvenance(BaseModel):
    """
    Provenance for a scene production package.

    Canonical package fields should trace back to explicit inputs or existing
    film-truth models. Derived guidance remains separate and is labeled here.
    """

    canonical_sources: Dict[str, bool] = Field(
        default_factory=lambda: {
            "scene_input": False,
            "creative_spine": False,
            "film_memory": False,
            "film_structure": False,
            "director_evaluation": False,
        }
    )
    derived_sources: Dict[str, bool] = Field(
        default_factory=lambda: {
            "film_intelligence": False,
            "cinematic_language": False,
            "taste_context": False,
        }
    )
    grounded_fields: List[str] = Field(default_factory=list)
    derived_fields: List[str] = Field(default_factory=list)
    advisory_fields: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ScenePackageDerivedGuidance(BaseModel):
    """
    Derived production guidance.

    This is explicitly non-canonical. It may sharpen packaging decisions,
    but it does not replace scene truth.
    """

    film_intelligence: Dict[str, object] = Field(default_factory=dict)
    cinematic_language: Dict[str, object] = Field(default_factory=dict)
    taste_guidance: Dict[str, object] = Field(default_factory=dict)


class SceneProductionPackage(BaseModel):
    """
    Canonical production package for a single scene.

    The package is built from explicit scene inputs and existing film-brain
    context. Derived guidance is included separately so provider-facing logic
    can inspect it later without promoting it to canonical truth.
    """

    scene_id: str
    film_id: str
    narrative_purpose: str = ""
    emotional_target: str = ""
    visual_target: str = ""
    motif_obligations: List[str] = Field(default_factory=list)
    continuity_constraints: List[str] = Field(default_factory=list)
    restraint_rules: List[str] = Field(default_factory=list)
    forbidden_moves: List[str] = Field(default_factory=list)
    provider_neutral_execution_brief: str = ""
    derived_guidance: ScenePackageDerivedGuidance = Field(default_factory=ScenePackageDerivedGuidance)
    provenance: ProductionPackageProvenance = Field(default_factory=ProductionPackageProvenance)
    derived_only: bool = False
    generated_at: str = Field(default_factory=utc_now_iso)


# =============================================================================
# Phase 9.4: Provider Request Models (Derived)
# =============================================================================
# These models are explicitly derived from SceneProductionPackage.
# They do NOT modify or re-interpret canonical package truth.
# =============================================================================


class ProviderRequestProvenance(BaseModel):
    """
    Provenance for a derived ProviderRenderRequest.

    Tracks which canonical and derived package fields were used to
    build each major request section, so the request can be traced
    back to its source without ambiguity.
    """

    scene_package_id: str = ""
    scene_id: str = ""
    film_id: str = ""
    prompt_sources: List[str] = Field(
        default_factory=list,
        description="List of package fields used to derive the main prompt text",
    )
    negative_prompt_sources: List[str] = Field(
        default_factory=list,
        description="List of package fields used to derive exclusions",
    )
    structured_params_sources: List[str] = Field(
        default_factory=list,
        description="List of package fields used for structured parameters",
    )
    reference_hint_sources: List[str] = Field(
        default_factory=list,
        description="List of package fields used for reference hints",
    )
    execution_notes_sources: List[str] = Field(
        default_factory=list,
        description="List of package fields used for execution notes",
    )
    advisory_sources: List[str] = Field(
        default_factory=list,
        description="Derived guidance fields used (advisory weight only)",
    )
    notes: List[str] = Field(default_factory=list)


class ProviderRenderRequest(BaseModel):
    """
    Derived provider-specific render request.

    Phase 9.4: This model is built from a SceneProductionPackage and
    translates canonical/advisory package fields into a provider-ready
    request structure. It is explicitly derived — canonical package
    truth is never mutated or reinterpreted.

    The request is organized around provider-facing concerns:
    - prompt text
    - exclusions (negative prompt guidance)
    - structured parameters
    - reference hints
    - execution notes

    Advisory influence (taste, cinematic language) remains low-weight
    and clearly labeled as non-canonical.
    """

    scene_id: str
    film_id: str
    provider_name: str = "default"
    generated_at: str = Field(default_factory=utc_now_iso)

    # Core prompt derived from narrative purpose + emotional + visual targets
    prompt: str = Field(
        default="",
        description="Main positive prompt text for the render provider",
    )
    prompt_components: List[str] = Field(
        default_factory=list,
        description="Ordered prompt components (for audit/inspect)",
    )

    # Exclusions derived from forbidden_moves + restraint_rules
    exclusions: str = Field(
        default="",
        description="Negative prompt or exclusion guidance for the provider",
    )
    exclusion_components: List[str] = Field(
        default_factory=list,
        description="Ordered exclusion components (for audit/inspect)",
    )

    # Structured parameters derived from visual_target and package fields
    structured_params: Dict[str, object] = Field(
        default_factory=dict,
        description="Provider-interpretable structured parameters",
    )

    # Reference hints derived from motif_obligations
    reference_hints: List[str] = Field(
        default_factory=list,
        description="Visual or thematic references to reinforce",
    )

    # Execution notes derived from continuity_constraints
    execution_notes: List[str] = Field(
        default_factory=list,
        description="Guidance notes for execution without mutating package truth",
    )

    # Advisory shaping notes (low-weight, clearly labeled non-canonical)
    advisory_shaping_notes: List[str] = Field(
        default_factory=list,
        description="Notes from derived guidance (taste, cinematic language) — advisory only",
    )

    # Provenance: trace request back to package fields
    provenance: ProviderRequestProvenance = Field(
        default_factory=ProviderRequestProvenance,
    )

    @property
    def is_empty(self) -> bool:
        """True when the request has no meaningful content."""
        return (
            not self.prompt
            and not self.prompt_components
            and not self.exclusions
            and not self.exclusion_components
            and not self.structured_params
            and not self.reference_hints
            and not self.execution_notes
        )


# =============================================================================
# Phase 12.1: Render Execution Record (Observational Foundation)
# =============================================================================
# This model captures bounded execution observability from provider-request
# outputs. It is explicitly non-authoritative and does not control routing,
# retries, failover, or runtime decision logic.
# =============================================================================


class RenderExecutionRecord(BaseModel):
    """
    Derived render execution observability record.

    This record tracks minimal execution facts for audit/inspection only.
    It must never be treated as canonical scene truth or runtime authority.
    """

    execution_id: str
    scene_id: str
    film_id: str
    provider_name: str
    adapter_payload_fingerprint: Optional[str] = None
    submission_state: str = "constructed"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    inspection_metadata: Dict[str, object] = Field(default_factory=dict)
    provenance_notes: List[str] = Field(default_factory=list)
    observed_execution_facts: Dict[str, object] = Field(default_factory=dict)


class RenderExecutionState(str, Enum):
    """Bounded observational lifecycle states for RenderExecutionRecord."""

    CONSTRUCTED = "constructed"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RenderExecutionSummary(BaseModel):
    """
    Derived read-only execution visibility summary.

    This summary is observational only and must not be used as an execution
    control or authority object.
    """

    execution_id: str
    provider_name: str
    lifecycle_state: str
    provider_status: Optional[str] = None
    has_output_artifacts: bool = False
    has_error: bool = False
    latest_updated_at: str = ""
    inspection_flags: Dict[str, object] = Field(default_factory=dict)


# =============================================================================
# Phase 9.5: Render Validation Models (Derived / Advisory)
# =============================================================================
# These models evaluate a provider render output against the canonical
# SceneProductionPackage. They are explicitly advisory — they do NOT block,
# reject, or retry renders. They do NOT modify package truth.
# =============================================================================


class ValidationIssue(BaseModel):
    """
    A single validation issue found during render output evaluation.

    Issues are grounded in explicit canonical package mismatches first.
    Heuristic signals are labeled as advisory.
    """

    severity: str = Field(
        default="warning",
        description="Issue severity: warning | critical | advisory",
    )
    category: str = Field(
        default="",
        description="Category: package_fidelity | tone | motif | continuity | cinematic",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the issue",
    )
    package_field: Optional[str] = Field(
        default=None,
        description="Canonical package field involved (if grounded)",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Evidence from render output supporting the issue",
    )
    is_advisory: bool = Field(
        default=False,
        description="True when the issue is heuristic/advisory rather than grounded",
    )


class RenderValidationProvenance(BaseModel):
    """
    Provenance for a RenderValidationReport.

    Tracks which canonical package fields and provider request fields were
    evaluated, and which film-brain context was consulted.
    """

    scene_id: str = ""
    film_id: str = ""
    package_fields_evaluated: List[str] = Field(
        default_factory=list,
        description="Canonical package fields checked during validation",
    )
    provider_request_fields_evaluated: List[str] = Field(
        default_factory=list,
        description="Provider request fields checked during validation",
    )
    film_brain_context_used: List[str] = Field(
        default_factory=list,
        description="Film-brain context keys consulted (e.g., motifs, tensions)",
    )
    grounding_notes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RenderValidationReport(BaseModel):
    """
    Advisory render validation report.

    Phase 9.5: This report evaluates whether a provider render output
    aligns with the canonical SceneProductionPackage and existing film-brain
    context. It is explicitly advisory — it does NOT block renders, does NOT
    trigger automatic retries, and does NOT modify any package or render state.

    Validation is organized around alignment dimensions:
    - package_fidelity: does the output reflect the scene's core intent?
    - tone_alignment: does the output's emotional tenor match the emotional target?
    - motif_alignment: are required motif references present?
    - continuity_alignment: are continuity constraints respected?
    - cinematic_alignment: does the output reflect the intended visual language?

    Severity guide:
    - critical: explicit canonical mismatch (e.g., missing required motif)
    - warning: likely mismatch based on grounded evidence
    - advisory: heuristic signal that warrants attention but lacks grounding
    """

    scene_id: str
    film_id: str
    generated_at: str = Field(default_factory=utc_now_iso)

    # Overall advisory disposition
    advisory_disposition: str = Field(
        default="review",
        description="Overall disposition: pass | review | concern",
    )
    advisory_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in the advisory disposition (0.0–1.0)",
    )

    # Alignment dimension scores (0.0–1.0, 1.0 = fully aligned)
    package_fidelity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Does the output reflect the scene's core intent?",
    )
    tone_alignment: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Does the output's emotional tenor match the emotional target?",
    )
    motif_alignment: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Are required motif references present?",
    )
    continuity_alignment: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Are continuity constraints respected?",
    )
    cinematic_alignment: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Does the output reflect the intended visual language?",
    )

    # Issues found (empty if no problems)
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="Validation issues found during evaluation",
    )

    # Provenance: trace validation back to package fields and context
    provenance: RenderValidationProvenance = Field(
        default_factory=RenderValidationProvenance,
    )

    @property
    def has_critical_issues(self) -> bool:
        """True when any issue has severity 'critical'."""
        return any(issue.severity == "critical" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """True when any issue has severity 'warning'."""
        return any(issue.severity == "warning" for issue in self.issues)

    @property
    def has_issues(self) -> bool:
        """True when any issue exists at any severity level."""
        return len(self.issues) > 0


# =============================================================================
# Phase 9.6: Render Comparison Foundation
# =============================================================================


class RenderComparisonEntry(BaseModel):
    """
    A single entry in a render comparison, referencing one render option.

    Phase 9.6: Comparison entries are derived from validation reports.
    They summarize key scores and issues for ranking purposes.

    This model does NOT mutate validation reports or render outputs.
    """

    entry_index: int = Field(
        default=0,
        description="Zero-based index of this entry in the comparison list",
    )
    scene_id: str = Field(default="", description="Scene identifier")
    film_id: str = Field(default="", description="Film identifier")

    # Key alignment scores from validation report (0.0–1.0)
    package_fidelity: float = Field(default=0.5, ge=0.0, le=1.0)
    tone_alignment: float = Field(default=0.5, ge=0.0, le=1.0)
    motif_alignment: float = Field(default=0.5, ge=0.0, le=1.0)
    continuity_alignment: float = Field(default=0.5, ge=0.0, le=1.0)
    cinematic_alignment: float = Field(default=0.5, ge=0.0, le=1.0)

    # Issue summary
    critical_issue_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    advisory_count: int = Field(default=0, ge=0)

    # Derived ranking score (0.0–1.0, higher = better)
    ranking_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Derived ranking score: package fidelity first, critical issues second, etc.",
    )

    # Explanation of ranking
    ranking_explanation: str = Field(
        default="",
        description="Human-readable explanation of why this entry ranked where it did",
    )

    # Advisory disposition from validation
    advisory_disposition: str = Field(default="review")

    # Reference info (not the full validation report, just refs)
    validation_report_ref: Optional[str] = Field(
        default=None,
        description="Identifier for the source validation report",
    )
    provider_request_ref: Optional[str] = Field(
        default=None,
        description="Identifier for the source provider request",
    )


class RenderComparisonReport(BaseModel):
    """
    Advisory comparison report for multiple render outputs.

    Phase 9.6: This report compares multiple render outputs against the same
    SceneProductionPackage. It is explicitly advisory — it does NOT select a
    winner for execution, does NOT trigger automatic retries, and does NOT
    modify any render state.

    Comparison is organized around derived ranking:
    - Entries are sorted by ranking_score (highest first)
    - Rankings are based on: package fidelity > critical issues > tone/motif > cinematic
    - All entries retain full provenance for explainability

    This model does NOT re-run validation. It uses validation reports as the
    source of truth and produces a derived comparison layer.
    """

    scene_id: str
    film_id: str
    generated_at: str = Field(default_factory=utc_now_iso)

    # Number of renders compared
    render_count: int = Field(default=0, ge=0)

    # Sorted entries (by ranking_score descending)
    entries: List[RenderComparisonEntry] = Field(
        default_factory=list,
        description="Comparison entries sorted by ranking score (best first)",
    )

    # Comparison metadata
    comparison_notes: List[str] = Field(
        default_factory=list,
        description="Notes about the comparison methodology",
    )

    # Provenance for the comparison
    comparison_provenance: List[str] = Field(
        default_factory=list,
        description="Sources used for comparison (validation report IDs, etc.)",
    )

    @property
    def has_multiple_renders(self) -> bool:
        """True when comparing 2 or more renders."""
        return self.render_count >= 2

    @property
    def best_entry(self) -> Optional[RenderComparisonEntry]:
        """Return the top-ranked entry, or None if no entries."""
        return self.entries[0] if self.entries else None

    @property
    def best_score(self) -> float:
        """Return the ranking score of the best entry, or 0.0 if no entries."""
        return self.best_entry.ranking_score if self.best_entry else 0.0


# =============================================================================
# Phase 12: Execution Timeline Foundation (Observational)
# =============================================================================
# This model captures a derived execution timeline from existing execution
# records. It is explicitly non-authoritative and does not control routing,
# retries, failover, or runtime decision logic.
# =============================================================================


class ExecutionTimelineEvent(BaseModel):
    """
    A single event in a bounded execution timeline.

    Each event captures minimal observable facts from execution records:
    - event type (constructed, submitted, completed, failed, cancelled)
    - provider name (from explicit provider config, not advisory)
    - lifecycle transition (from observed state changes)
    - provider status (from observed execution facts)
    - error presence (from observed facts)
    - artifact presence (from observed facts)
    - timestamp (derived from execution record updates)

    This event is derived, read-only, and must never mutate canonical truth.
    Advisory or Co-Director metadata does not influence event authority.
    """

    event_type: str = Field(
        default="",
        description="Event type: constructed, submitted, completed, failed, cancelled",
    )
    provider_name: str = Field(
        default="",
        description="Provider name from explicit provider config only",
    )
    lifecycle_transition: Optional[str] = Field(
        default=None,
        description="State transition observed (e.g., 'constructed->submitted')",
    )
    provider_status: Optional[str] = Field(
        default=None,
        description="Provider-reported status (e.g., 'rendering', 'complete')",
    )
    has_error: bool = Field(
        default=False,
        description="True when error summary is present in observed facts",
    )
    has_artifact: bool = Field(
        default=False,
        description="True when output artifact refs are present",
    )
    timestamp: str = Field(
        default="",
        description="Event timestamp (ISO format with Z suffix)",
    )
    event_index: int = Field(
        default=0,
        description="Zero-based index in timeline sequence",
    )


class ExecutionTimeline(BaseModel):
    """
    Derived read-only execution timeline for a single scene.

    Phase 12: This timeline is built from existing RenderExecutionRecord
    instances. It provides bounded visibility into execution events without
    being an authority object.

    Properties:
    - event_type: derived from submission_state transitions
    - provider_name: derived from explicit provider config (never advisory)
    - lifecycle_transition: derived from state changes
    - provider_status: derived from observed_execution_facts
    - error presence: derived from observed_execution_facts.error_summary
    - artifact presence: derived from observed_execution_facts.output_artifact_refs
    - timestamp: derived from created_at/updated_at

    This model does NOT:
    - Control execution flow
    - Trigger retries
    - Implement failover
    - Influence provider selection
    - Mutate canonical FilmLevelMemory, FilmStructure, CreativeSpine
    - Elevate advisory/Co-Director metadata to authority
    """

    scene_id: str = Field(default="", description="Scene identifier")
    film_id: str = Field(default="", description="Film identifier")
    timeline_id: str = Field(default="", description="Unique timeline identifier")
    generated_at: str = Field(default_factory=utc_now_iso)

    # Derived events in chronological order
    events: List[ExecutionTimelineEvent] = Field(
        default_factory=list,
        description="Timeline events in chronological order",
    )

    # Bounded summary derived from events
    event_count: int = Field(
        default=0,
        description="Total number of events in timeline",
    )
    has_errors: bool = Field(
        default=False,
        description="True when any event has an error",
    )
    has_artifacts: bool = Field(
        default=False,
        description="True when any event has an artifact",
    )

    # Timeline metadata (observational only)
    timeline_metadata: Dict[str, object] = Field(
        default_factory=dict,
        description="Metadata for timeline derivation context",
    )

    # Provenance tracking
    provenance_notes: List[str] = Field(
        default_factory=list,
        description="Notes about timeline derivation sources",
    )

    @property
    def latest_event(self) -> Optional[ExecutionTimelineEvent]:
        """Return the most recent event, or None if timeline is empty."""
        return self.events[-1] if self.events else None

    @property
    def is_complete(self) -> bool:
        """True when the latest event indicates completion."""
        latest = self.latest_event
        return latest is not None and latest.event_type == "completed"

    @property
    def is_failed(self) -> bool:
        """True when the latest event indicates failure."""
        latest = self.latest_event
        return latest is not None and latest.event_type == "failed"

    def to_event_summary(self) -> Dict[str, Any]:
        """Return a simple event summary for debugging."""
        return {
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "event_count": self.event_count,
            "has_errors": self.has_errors,
            "has_artifacts": self.has_artifacts,
            "latest_event": (
                self.latest_event.event_type if self.latest_event else None
            ),
        }
