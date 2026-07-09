"""
Creative Spine Model - Phase 2 of Film Co-Direction System.

The Creative Spine is the governing creative constitution for a film.
It defines and protects the film's identity across structure, memory,
agent collaboration, and scoring.

IMPORTANT: This is a GOVERNANCE layer, not a data layer.
- FilmLevelMemory holds the actual field values (story_thesis, emotional_contract, etc.)
- CreativeSpine holds the GOVERNANCE around those fields (versions, thresholds, audit)

Three-Layer Distinction:
- FilmStructure = organizational hierarchy (acts, sequences, scenes, beats)
- FilmLevelMemory = parsed/observed content (themes, motifs, tensions, trajectory)
- CreativeSpine = governing constraints and rules (what must NOT be violated)

Usage:
    spine = CreativeSpine(
        film_id="film_123",
        frozen_fields=["story_thesis", "emotional_contract", "genre_lane"],
        constraint_weights={
            "story_thesis": 1.0,
            "emotional_contract": 0.9,
            "visual_philosophy": 0.5
        }
    )
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ConstraintSeverity(str, Enum):
    """How severe a constraint violation is."""
    ERROR = "error"      # Immutable field violated - must fix
    WARNING = "warning"  # Revisable field deviated - should review
    ADVISORY = "advisory"  # Guidance not followed - informational


class ConstraintType(str, Enum):
    """Type of constraint being checked."""
    IMMUTABLE = "immutable"    # Cannot be violated (story_thesis, etc.)
    REVISABLE = "revisable"    # Can change with process (visual_philosophy, etc.)
    RESTRAINT = "restraint"    # Explicit "do not do" rule
    GENRE = "genre"            # Genre convention check


class SpineConstraint(BaseModel):
    """
    A single constraint in the creative spine.
    
    Constraints define what agents must or should do, and what they must not do.
    """
    constraint_id: str
    field_name: str = ""  # Which FilmLevelMemory field this governs
    constraint_type: ConstraintType
    description: str = ""  # Human-readable description
    severity: ConstraintSeverity
    weight: float = 1.0  # How much this matters for scoring (0.0-1.0)
    rationale: str = ""  # Why this constraint exists
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "field_name": self.field_name,
            "constraint_type": self.constraint_type.value,
            "description": self.description,
            "severity": self.severity.value,
            "weight": self.weight,
            "rationale": self.rationale
        }


class ConstraintViolation(BaseModel):
    """
    A single violation of a spine constraint.
    """
    constraint_id: str
    field_name: str
    expected_value: str = ""  # What the spine requires
    actual_value: str = ""    # What was actually produced
    severity: ConstraintSeverity
    message: str = ""
    agent_id: str = ""
    scene_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "field_name": self.field_name,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "severity": self.severity.value,
            "message": self.message,
            "agent_id": self.agent_id,
            "scene_id": self.scene_id,
            "timestamp": self.timestamp.isoformat()
        }


class DriftReport(BaseModel):
    """
    Report of drift from the creative spine.
    
    Drift occurs when the actual film content deviates from what the
    spine governs. This is different from a violation - drift is about
    accumulated deviation, not a single decision.
    """
    film_id: str
    field_name: str
    drift_score: float = 0.0  # 0.0 = no drift, 1.0 = maximum drift
    threshold: float = 0.2    # When does this become a problem
    current_value: str = ""
    spine_value: str = ""
    affected_scenes: List[str] = []
    recommendation: str = ""
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    
    def is_above_threshold(self) -> bool:
        return self.drift_score > self.threshold
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "film_id": self.film_id,
            "field_name": self.field_name,
            "drift_score": self.drift_score,
            "threshold": self.threshold,
            "current_value": self.current_value,
            "spine_value": self.spine_value,
            "affected_scenes": self.affected_scenes,
            "recommendation": self.recommendation,
            "detected_at": self.detected_at.isoformat(),
            "is_above_threshold": self.is_above_threshold()
        }


class OverrideRecord(BaseModel):
    """
    Record of a human override to the creative spine.
    
    Overrides allow authorized humans to change spine constraints
    with proper documentation.
    """
    override_id: str
    field_name: str
    old_value: str = ""
    new_value: str = ""
    reason: str = ""
    overridden_by: str = ""  # Human user ID
    override_type: str = ""  # "correction", "update", "relaxation"
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "override_id": self.override_id,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "overridden_by": self.overridden_by,
            "override_type": self.override_type,
            "approved_at": self.approved_at.isoformat()
        }


class ApprovedDeviation(BaseModel):
    """
    A deviation from the spine that has been explicitly approved.
    
    Unlike a violation (which is an error), an approved deviation
    is a intentional exception with documented rationale.
    """
    deviation_id: str
    field_name: str
    original_constraint: str = ""
    approved_value: str = ""
    scope: str = ""  # "scene_45", "act_2", "film-wide"
    reason: str = ""
    approved_by: str = ""
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def is_active(self) -> bool:
        if self.expires_at is None:
            return True
        return datetime.utcnow() < self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "deviation_id": self.deviation_id,
            "field_name": self.field_name,
            "original_constraint": self.original_constraint,
            "approved_value": self.approved_value,
            "scope": self.scope,
            "reason": self.reason,
            "approved_by": self.approved_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active()
        }


class CreativeSpine(BaseModel):
    """
    The governing creative constitution for a film.
    
    The Creative Spine defines what the film IS at its core, and what it
    must NOT become. It protects the film's identity while allowing
    appropriate evolution.
    
    Key Design Decisions:
    - The spine REFERENCES FilmLevelMemory fields, doesn't copy them
    - Immutable fields (story_thesis, emotional_contract, genre_lane) cannot be violated
    - Revisable fields (visual_philosophy, pacing_philosophy) can evolve with process
    - All changes are audit-logged via override_history
    
    Inheritance:
    - FilmLevelMemory provides the actual values the spine governs
    - CreativeSpine provides the governance around those values
    - ActMemory and SequenceMemory inherit from FilmLevelMemory and
      are subject to spine governance
    
    Usage:
        # Create spine from film memory
        spine = CreativeSpine(film_id="film_123")
        spine.initialize_from_memory(film_memory)
        
        # Check a decision against the spine
        violations = spine.validate_decision(
            decision={"type": "lighting", "value": "harsh"},
            context={"scene_id": "scene_45"}
        )
    """
    film_id: str
    
    # Version tracking
    spine_version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Frozen canonical fields - these are IMMUTABLE
    # Values are field NAMES from FilmLevelMemory that cannot be contradicted
    frozen_fields: List[str] = [
        "story_thesis",      # The governing question
        "emotional_contract", # The emotional promise to audience
        "genre_lane",         # Genre conventions
    ]
    
    # Revisable fields - can evolve with proper process
    revisable_fields: List[str] = [
        "visual_philosophy",   # How the film looks
        "pacing_philosophy",   # How the film节奏
        "restraint_rules",     # What NOT to do
    ]
    
    # Drift detection
    drift_threshold: float = 0.2  # 20% deviation allowed before flagging
    
    # Constraint weights for scoring (field_name -> weight 0.0-1.0)
    # Higher weight = more important for scoring validation
    constraint_weights: Dict[str, float] = {
        "story_thesis": 1.0,
        "emotional_contract": 0.95,
        "genre_lane": 0.9,
        "visual_philosophy": 0.5,
        "pacing_philosophy": 0.4,
        "restraint_rules": 0.7,
    }
    
    # Override audit trail
    override_history: List[OverrideRecord] = []
    
    # Approved deviations (intentional exceptions)
    approved_deviations: List[ApprovedDeviation] = []
    
    # Active constraints (built from frozen + revisable fields)
    constraints: List[SpineConstraint] = []
    
    # Metadata
    notes: str = ""  # General notes about this spine
    created_by: str = ""  # Who created this spine
    
    def initialize_from_memory(self, memory: 'FilmLevelMemory') -> None:
        """
        Initialize spine constraints from FilmLevelMemory.
        
        This populates the constraints list based on the actual
        values in FilmLevelMemory. The spine then governs those values.
        
        Args:
            memory: FilmLevelMemory to initialize from
        """
        from app.models.memory import FilmLevelMemory
        
        self.constraints = []
        
        # Add constraints for frozen fields
        for field_name in self.frozen_fields:
            value = getattr(memory, field_name, "")
            constraint = SpineConstraint(
                constraint_id=f"{self.film_id}_{field_name}",
                field_name=field_name,
                constraint_type=ConstraintType.IMMUTABLE,
                description=f"Immutable: {field_name} cannot be contradicted",
                severity=ConstraintSeverity.ERROR,
                weight=self.constraint_weights.get(field_name, 1.0),
                rationale=f"Core identity field - {value[:50]}..." if value else ""
            )
            self.constraints.append(constraint)
        
        # Add constraints for revisable fields
        for field_name in self.revisable_fields:
            value = getattr(memory, field_name, "")
            constraint = SpineConstraint(
                constraint_id=f"{self.film_id}_{field_name}",
                field_name=field_name,
                constraint_type=ConstraintType.REVISABLE,
                description=f"Revisable: {field_name} can evolve with justification",
                severity=ConstraintSeverity.WARNING,
                weight=self.constraint_weights.get(field_name, 0.5),
                rationale=f"Guidance field - current: {value[:50]}..." if value else ""
            )
            self.constraints.append(constraint)
        
        self.updated_at = datetime.utcnow()
    
    def get_constraint_for_field(self, field_name: str) -> Optional[SpineConstraint]:
        """Get the constraint governing a specific field."""
        for c in self.constraints:
            if c.field_name == field_name:
                return c
        return None
    
    def is_frozen(self, field_name: str) -> bool:
        """Check if a field is frozen (immutable)."""
        return field_name in self.frozen_fields
    
    def get_constraint_weights(self) -> Dict[str, float]:
        """Get constraint weights for scoring."""
        return self.constraint_weights.copy()
    
    def record_override(
        self,
        field_name: str,
        old_value: str,
        new_value: str,
        reason: str,
        overridden_by: str
    ) -> None:
        """
        Record a human override to the spine.
        
        Args:
            field_name: Which field is being overridden
            old_value: Previous value
            new_value: New value
            reason: Why this override is happening
            overridden_by: User ID of person making the override
        """
        override = OverrideRecord(
            override_id=f"override_{len(self.override_history) + 1}",
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            overridden_by=overridden_by,
            override_type="update" if field_name in self.revisable_fields else "correction"
        )
        self.override_history.append(override)
        self.updated_at = datetime.utcnow()
    
    def add_approved_deviation(
        self,
        field_name: str,
        approved_value: str,
        scope: str,
        reason: str,
        approved_by: str,
        expires_at: Optional[datetime] = None
    ) -> None:
        """
        Add an approved deviation from the spine.
        
        Args:
            field_name: Which field is being deviated from
            approved_value: The approved alternative value
            scope: Where this deviation applies ("scene_45", "act_2", "film-wide")
            reason: Why this deviation is approved
            approved_by: User ID who approved
            expires_at: Optional expiration time
        """
        deviation = ApprovedDeviation(
            deviation_id=f"deviation_{len(self.approved_deviations) + 1}",
            field_name=field_name,
            original_constraint=self._get_current_constraint(field_name),
            approved_value=approved_value,
            scope=scope,
            reason=reason,
            approved_by=approved_by,
            expires_at=expires_at
        )
        self.approved_deviations.append(deviation)
        self.updated_at = datetime.utcnow()
    
    def _get_current_constraint(self, field_name: str) -> str:
        """Get string representation of current constraint for a field."""
        constraint = self.get_constraint_for_field(field_name)
        if constraint:
            return constraint.description
        return ""
    
    def get_active_deviations_for_scene(self, scene_id: str) -> List[ApprovedDeviation]:
        """Get all active deviations that apply to a specific scene."""
        active = []
        for d in self.approved_deviations:
            if d.is_active():
                # Check if scope matches
                if d.scope == "film-wide" or d.scope == scene_id:
                    active.append(d)
        return active
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "film_id": self.film_id,
            "spine_version": self.spine_version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "frozen_fields": self.frozen_fields,
            "revisable_fields": self.revisable_fields,
            "drift_threshold": self.drift_threshold,
            "constraint_weights": self.constraint_weights,
            "constraint_count": len(self.constraints),
            "override_count": len(self.override_history),
            "approved_deviation_count": len(self.approved_deviations),
            "notes": self.notes,
            "created_by": self.created_by
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the spine for display."""
        return {
            "film_id": self.film_id,
            "version": self.spine_version,
            "frozen_field_count": len(self.frozen_fields),
            "revisable_field_count": len(self.revisable_fields),
            "constraint_count": len(self.constraints),
            "override_count": len(self.override_history),
            "active_deviation_count": len([d for d in self.approved_deviations if d.is_active()]),
            "drift_threshold": self.drift_threshold
        }