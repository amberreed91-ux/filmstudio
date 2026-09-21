"""
Co-Director Models - Phase 10.4.1

Session and critique models for Co-Director collaboration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID


class SessionMode(str, Enum):
    """Co-Director operational modes."""
    
    PASSIVE = "passive"
    ADVISORY = "advisory"
    COLLABORATIVE = "collaborative"
    EXPERIMENTAL = "experimental"


# Confidence labels follow AGENTS.md tendency language — never numeric.
CONFIDENCE_EMERGING = "emerging"
CONFIDENCE_CONSISTENT = "consistent"
CONFIDENCE_STRONG = "strong"


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class CoDirectorSession:
    """
    Session-level context for Co-Director collaboration.
    
    Tracks mode, active scene, revision state, and acceptance patterns.
    """
    
    session_id: UUID
    project_id: UUID
    film_id: UUID
    current_mode: SessionMode = SessionMode.PASSIVE
    active_scene_id: Optional[UUID] = None
    revision_count: int = 0
    repeated_critique_count: int = 0
    last_accepted_suggestion: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = _utc_now()
    
    def set_active_scene(self, scene_id: UUID) -> None:
        """Set the active scene for this session."""
        self.active_scene_id = scene_id
        self.touch()
    
    def increment_revision(self) -> None:
        """Increment the revision counter."""
        self.revision_count += 1
        self.touch()
    
    def increment_repeated_critique(self) -> None:
        """Increment the repeated critique counter."""
        self.repeated_critique_count += 1
        self.touch()
    
    def record_accepted_suggestion(self, suggestion_type: str) -> None:
        """Record an accepted suggestion type."""
        self.last_accepted_suggestion = suggestion_type
        self.touch()
    
    def set_mode(self, mode: SessionMode) -> None:
        """Set the session mode."""
        self.current_mode = mode
        self.touch()


class CoDirectorCritiqueCategory(str, Enum):
    """Categories for Co-Director critique issues."""

    DIRECTOR_INSTANT_REJECTION = "director_instant_rejection"
    DIRECTOR_PILLAR_LOW = "director_pillar_low"
    CONTINUITY_ALERT = "continuity_alert"
    STORY_LEVEL_ISSUE = "story_level_issue"
    FILM_SCALE_ISSUE = "film_scale_issue"
    RENDER_ISSUE = "render_issue"
    CINEMATIC_LANGUAGE_ISSUE = "cinematic_language_issue"
    TASTE_LEARNING_ISSUE = "taste_learning_issue"


class CoDirectorCritiquePriority(str, Enum):
    """Priority levels for Co-Director critiques."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class CoDirectorCritiqueSource(str, Enum):
    """Source systems that can generate Co-Director critiques."""

    DIRECTOR_EVALUATOR = "director_evaluator"
    MEMORY_ARCHIVIST = "memory_archivist"
    STORY_SCORING = "story_scoring"
    FILM_INTELLIGENCE = "film_intelligence"
    CINEMATIC_LANGUAGE = "cinematic_language"
    TASTE_LEARNING = "taste_learning"
    RENDER_VALIDATION = "render_validation"


@dataclass
class CoDirectorCritique:
    """
    Individual critique from Co-Director analysis.

    Represents a single issue or recommendation identified during
    Co-Director evaluation of a scene or element.
    """

    critique_id: str
    category: CoDirectorCritiqueCategory
    priority: CoDirectorCritiquePriority
    title: str
    description: str
    recommendation: str
    grounded_signals: List[str]
    heuristic_signals: List[str]
    source_systems: List[CoDirectorCritiqueSource]
    overall_confidence: str
    grounded_confidence: str
    heuristic_confidence: str
    provenance: List[str]
    canonical_sources: Dict[str, bool]
    affected_scene_ids: List[str]
    affected_elements: List[str]
    created_at: datetime = field(default_factory=_utc_now)
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE


@dataclass
class CoDirectorCritiqueReport:
    """
    Container for Co-Director critique results.

    Aggregates critiques from multiple source systems into a
    unified report for a given session and mode.
    """

    critique: Optional[CoDirectorCritique] = None
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE
    sources_consulted: List[CoDirectorCritiqueSource] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    provenance: Dict[str, Any] = field(default_factory=dict)


class CoDirectorProposalCategory(str, Enum):
    """Categories for Co-Director proposal strategies."""

    DIRECTOR_REJECTION_RECOVERY = "director_rejection_recovery"
    DIRECTOR_PILLAR_RECOVERY = "director_pillar_recovery"
    CREATIVE_DISAGREEMENT = "creative_disagreement"
    ALTERNATE_SCENE_SUGGESTION = "alternate_scene_suggestion"
    VISUAL_EXPERIMENTATION = "visual_experimentation"
    THEMATIC_PROPOSAL = "thematic_proposal"


@dataclass
class CoDirectorProposal:
    """
    Single bounded proposal derived from a dominant critique.

    Proposal output is advisory-only and does not mutate canonical truth.
    """

    proposal_id: str
    category: CoDirectorProposalCategory
    priority: CoDirectorCritiquePriority
    title: str
    description: str
    recommendation: str
    critique_id: Optional[str]
    grounded_signals: List[str]
    heuristic_signals: List[str]
    source_systems: List[CoDirectorCritiqueSource]
    overall_confidence: str
    grounded_confidence: str
    heuristic_confidence: str
    provenance: List[str]
    canonical_sources: Dict[str, bool]
    affected_scene_ids: List[str]
    affected_elements: List[str]
    created_at: datetime = field(default_factory=_utc_now)
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE
    advisory_only: bool = True


@dataclass
class CoDirectorProposalReport:
    """
    Container for Co-Director proposal results.

    Holds one dominant proposal at most, with bounded provenance.
    """

    proposal: Optional[CoDirectorProposal] = None
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE
    sources_consulted: List[CoDirectorCritiqueSource] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    provenance: Dict[str, Any] = field(default_factory=dict)


class CoDirectorComparisonCategory(str, Enum):
    """Categories for critique-to-proposal comparison outcomes."""

    DIRECTOR_REJECTION_RECOVERY_ALIGNMENT = "director_rejection_recovery_alignment"
    DIRECTOR_PILLAR_RECOVERY_ALIGNMENT = "director_pillar_recovery_alignment"


@dataclass
class CoDirectorComparison:
    """
    Dominant comparison artifact between current director state and proposal.

    Advisory-only and bounded; contains no execution directives.
    """

    comparison_id: str
    category: CoDirectorComparisonCategory
    title: str
    description: str
    recommendation: str
    critique_id: Optional[str]
    proposal_id: Optional[str]
    grounded_signals: List[str]
    heuristic_signals: List[str]
    source_systems: List[CoDirectorCritiqueSource]
    overall_confidence: str
    grounded_confidence: str
    heuristic_confidence: str
    dominance_reason: str
    provenance: List[str]
    canonical_sources: Dict[str, bool]
    affected_scene_ids: List[str]
    affected_elements: List[str]
    created_at: datetime = field(default_factory=_utc_now)
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE


@dataclass
class CoDirectorComparisonReport:
    """Container for Co-Director comparison output."""

    comparison: Optional[CoDirectorComparison] = None
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE
    sources_consulted: List[CoDirectorCritiqueSource] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    provenance: Dict[str, Any] = field(default_factory=dict)


class CoDirectorIntensityLevel(str, Enum):
    """Bounded guidance intensity levels for co-director orchestration."""

    SILENT = "silent"
    LIGHT = "light"
    FOCUSED = "focused"
    DEEP = "deep"


@dataclass
class CoDirectorIntensityProfile:
    """Derived, advisory intensity profile from session and critique state."""

    level: CoDirectorIntensityLevel
    rationale: str
    critique_repetition_risk: str
    escalation_required: bool
    recommended_mode: SessionMode
    grounded_signals: List[str]
    heuristic_signals: List[str]
    overall_confidence: str
    grounded_confidence: str
    heuristic_confidence: str
    created_at: datetime = field(default_factory=_utc_now)
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE


@dataclass
class CoDirectorIntensityReport:
    """Container for co-director intensity profile output."""

    intensity_profile: Optional[CoDirectorIntensityProfile] = None
    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE
    sources_consulted: List[CoDirectorCritiqueSource] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoDirectorCollaborationReport:
    """
    Unified co-director orchestration report for advisory/collaborative modes.

    Bundles dominant critique/proposal/comparison plus intensity guidance.
    """

    session_id: Optional[str] = None
    mode: SessionMode = SessionMode.PASSIVE
    critique: Optional[CoDirectorCritique] = None
    proposal: Optional[CoDirectorProposal] = None
    comparison: Optional[CoDirectorComparison] = None
    intensity_profile: Optional[CoDirectorIntensityProfile] = None
    dominant_focus: Optional[str] = None
    advisory_notes: List[str] = field(default_factory=list)
    creative_disagreements: List[str] = field(default_factory=list)
    alternate_scene_suggestions: List[str] = field(default_factory=list)
    visual_experiments: List[str] = field(default_factory=list)
    thematic_proposals: List[str] = field(default_factory=list)
    advisory_only: bool = True
    sources_consulted: List[CoDirectorCritiqueSource] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    provenance: Dict[str, Any] = field(default_factory=dict)
