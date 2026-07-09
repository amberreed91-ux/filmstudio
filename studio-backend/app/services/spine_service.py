"""
Spine Service - Governance logic for the Creative Spine.

This service provides the consumption API for agents to interact with
the creative spine. It handles:
- Constraint retrieval (role-filtered)
- Decision validation against spine
- Drift detection
- Override management
- Guidance generation

Usage:
    service = SpineService()
    
    # Get constraints for a role
    constraints = service.get_constraints_for_role("film_123", AgentRole.DIRECTOR)
    
    # Validate a decision
    violations = service.check_decision("film_123", decision, context)
    
    # Get guidance
    guidance = service.get_guidance("film_123", "pacing", context)
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime

from pydantic import BaseModel

from app.models.spine import (
    CreativeSpine,
    SpineConstraint,
    ConstraintViolation,
    ConstraintSeverity,
    ConstraintType,
    DriftReport,
    OverrideRecord,
    ApprovedDeviation,
)
from app.models.memory import FilmLevelMemory
from app.models.crew import AgentRole

if TYPE_CHECKING:
    from app.services.film_structure_service import FilmStructureService


class ValidationResult(BaseModel):
    """Result of validating a decision against the spine."""
    is_valid: bool
    violations: List[ConstraintViolation] = []
    warnings: List[ConstraintViolation] = []
    advisories: List[ConstraintViolation] = []
    
    def has_errors(self) -> bool:
        return len(self.violations) > 0
    
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class SpineService:
    """
    Service for managing CreativeSpine governance.
    
    This service provides the API through which agents consume
    spine constraints and validate decisions.
    """
    
    def __init__(self):
        """Initialize the spine service."""
        # In-memory storage for spines (would be persisted in real implementation)
        self._spines: Dict[str, CreativeSpine] = {}
        self._memory_cache: Dict[str, FilmLevelMemory] = {}
    
    # =========================================================================
    # Spine Lifecycle
    # =========================================================================
    
    def get_or_create_spine(
        self,
        film_id: str,
        memory: Optional[FilmLevelMemory] = None
    ) -> CreativeSpine:
        """
        Get existing spine or create new one from memory.
        
        Args:
            film_id: Film identifier
            memory: Optional FilmLevelMemory to initialize from
            
        Returns:
            CreativeSpine for this film
        """
        if film_id in self._spines:
            return self._spines[film_id]
        
        spine = CreativeSpine(film_id=film_id)
        
        if memory:
            spine.initialize_from_memory(memory)
            self._memory_cache[film_id] = memory
        
        self._spines[film_id] = spine
        return spine
    
    def get_spine(self, film_id: str) -> Optional[CreativeSpine]:
        """Get spine for a film if it exists."""
        return self._spines.get(film_id)
    
    def create_spine_from_memory(
        self,
        film_id: str,
        memory: FilmLevelMemory
    ) -> CreativeSpine:
        """
        Create a new spine initialized from FilmLevelMemory.
        
        Args:
            film_id: Film identifier
            memory: FilmLevelMemory to initialize from
            
        Returns:
            New CreativeSpine initialized from memory
        """
        spine = CreativeSpine(film_id=film_id)
        spine.initialize_from_memory(memory)
        
        self._spines[film_id] = spine
        self._memory_cache[film_id] = memory
        
        return spine
    
    def update_spine_from_memory(
        self,
        film_id: str,
        memory: FilmLevelMemory
    ) -> CreativeSpine:
        """
        Update existing spine with new memory values.
        
        This is used when FilmLevelMemory has been updated and
        the spine needs to reflect those changes.
        
        Args:
            film_id: Film identifier
            memory: Updated FilmLevelMemory
            
        Returns:
            Updated CreativeSpine
        """
        spine = self.get_or_create_spine(film_id, memory)
        spine.initialize_from_memory(memory)
        self._memory_cache[film_id] = memory
        return spine
    
    # =========================================================================
    # Constraint Consumption API
    # =========================================================================
    
    def get_constraints_for_role(
        self,
        film_id: str,
        role: AgentRole
    ) -> Dict[str, Any]:
        """
        Get constraints relevant to a specific agent role.
        
        This is the primary way agents fetch spine constraints.
        Different roles get different constraints based on what
        they need to know.
        
        Args:
            film_id: Film identifier
            role: Agent role requesting constraints
            
        Returns:
            Dict with constraint categories:
            - immutable: Constraints that cannot be violated
            - revisable: Constraints that can evolve
            - restraint_rules: Explicit "do not do" rules
            - genre_conventions: Genre-specific requirements
        """
        spine = self.get_spine(film_id)
        if not spine:
            return {"error": "Spine not found"}
        
        memory = self._memory_cache.get(film_id)
        
        # Role-based filtering
        if role == AgentRole.DIRECTOR:
            # Directors need everything (creative authority)
            return self._get_all_constraints(spine, memory)
        elif role == AgentRole.CINEMATOGRAPHER:
            # Cinematographers need visual and restraint
            return self._get_cinematographer_constraints(spine, memory)
        elif role == AgentRole.QUALITY_REVIEWER:
            # Reviewers need all constraints for validation
            return self._get_reviewer_constraints(spine, memory)
        else:
            # Default: basic constraints
            return self._get_basic_constraints(spine, memory)
    
    def _get_all_constraints(
        self,
        spine: CreativeSpine,
        memory: Optional[FilmLevelMemory]
    ) -> Dict[str, Any]:
        """Get all constraints for director-level access."""
        result = {
            "immutable": {},
            "revisable": {},
            "restraint_rules": [],
            "genre_conventions": {},
        }
        
        # Immutable fields
        for field in spine.frozen_fields:
            value = getattr(memory, field, "") if memory else ""
            result["immutable"][field] = {
                "value": value,
                "weight": spine.constraint_weights.get(field, 1.0),
                "severity": "ERROR"
            }
        
        # Revisable fields
        for field in spine.revisable_fields:
            value = getattr(memory, field, "") if memory else ""
            result["revisable"][field] = {
                "value": value,
                "weight": spine.constraint_weights.get(field, 0.5),
                "severity": "WARNING"
            }
        
        # Restraint rules
        if memory and hasattr(memory, 'restraint_rules'):
            result["restraint_rules"] = memory.restraint_rules
        
        # Genre conventions
        if memory and hasattr(memory, 'genre_lane'):
            result["genre_conventions"] = {
                "genre_lane": memory.genre_lane,
                "weight": spine.constraint_weights.get("genre_lane", 0.9)
            }
        
        return result
    
    def _get_cinematographer_constraints(
        self,
        spine: CreativeSpine,
        memory: Optional[FilmLevelMemory]
    ) -> Dict[str, Any]:
        """Get constraints relevant to cinematographer."""
        return {
            "visual_philosophy": getattr(memory, "visual_philosophy", "") if memory else "",
            "restraint_rules": getattr(memory, "restraint_rules", []) if memory else [],
            "genre_lane": getattr(memory, "genre_lane", "") if memory else "",
            "pacing_philosophy": getattr(memory, "pacing_philosophy", "") if memory else "",
        }
    
    def _get_reviewer_constraints(
        self,
        spine: CreativeSpine,
        memory: Optional[FilmLevelMemory]
    ) -> Dict[str, Any]:
        """Get constraints relevant to quality reviewer."""
        return self._get_all_constraints(spine, memory)
    
    def _get_basic_constraints(
        self,
        spine: CreativeSpine,
        memory: Optional[FilmLevelMemory]
    ) -> Dict[str, Any]:
        """Get basic constraints for other roles."""
        return {
            "story_thesis": getattr(memory, "story_thesis", "") if memory else "",
            "emotional_contract": getattr(memory, "emotional_contract", "") if memory else "",
            "restraint_rules": getattr(memory, "restraint_rules", []) if memory else [],
        }
    
    # =========================================================================
    # Decision Validation
    # =========================================================================
    
    def check_decision(
        self,
        film_id: str,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Check a decision against the spine.
        
        This is how agents validate decisions before committing.
        Returns violations, warnings, and advisories.
        
        Args:
            film_id: Film identifier
            decision: Decision to validate (type, value, etc.)
            context: Optional context (scene_id, agent_id, etc.)
            
        Returns:
            ValidationResult with any violations found
        """
        spine = self.get_spine(film_id)
        if not spine:
            return ValidationResult(is_valid=True, violations=[])
        
        memory = self._memory_cache.get(film_id)
        context = context or {}
        
        result = ValidationResult(is_valid=True)
        
        decision_type = decision.get("type", "")
        decision_value = decision.get("value", "")
        
        # Check immutable fields
        if decision_type in spine.frozen_fields:
            spine_value = getattr(memory, decision_type, "") if memory else ""
            if decision_value != spine_value and spine_value:
                violation = ConstraintViolation(
                    constraint_id=f"{film_id}_{decision_type}",
                    field_name=decision_type,
                    expected_value=spine_value,
                    actual_value=decision_value,
                    severity=ConstraintSeverity.ERROR,
                    message=f"Decision violates immutable field: {decision_type}",
                    agent_id=context.get("agent_id", ""),
                    scene_id=context.get("scene_id", "")
                )
                result.violations.append(violation)
                result.is_valid = False
        
        # Check revisable fields (warnings, not errors)
        if decision_type in spine.revisable_fields:
            spine_value = getattr(memory, decision_type, "") if memory else ""
            if decision_value != spine_value and spine_value:
                warning = ConstraintViolation(
                    constraint_id=f"{film_id}_{decision_type}",
                    field_name=decision_type,
                    expected_value=spine_value,
                    actual_value=decision_value,
                    severity=ConstraintSeverity.WARNING,
                    message=f"Decision deviates from revisable field: {decision_type}",
                    agent_id=context.get("agent_id", ""),
                    scene_id=context.get("scene_id", "")
                )
                result.warnings.append(warning)
        
        # Check restraint rules
        if memory and hasattr(memory, 'restraint_rules'):
            for rule in memory.restraint_rules:
                rule_text = rule.get("rule", "").lower()
                if rule_text and rule_text in str(decision_value).lower():
                    advisory = ConstraintViolation(
                        constraint_id=f"restraint_{rule.get('rule', 'unknown')}",
                        field_name="restraint_rules",
                        expected_value=rule.get("rule", ""),
                        actual_value=decision_value,
                        severity=ConstraintSeverity.ADVISORY,
                        message=f"Decision matches restraint rule: {rule.get('reason', '')}",
                        agent_id=context.get("agent_id", ""),
                        scene_id=context.get("scene_id", "")
                    )
                    result.advisories.append(advisory)
        
        return result
    
    def validate_against_spine(
        self,
        film_id: str,
        agent_output: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> List[ConstraintViolation]:
        """
        Validate agent output against the spine.
        
        This is used by story-level scoring to check if agent
        outputs conform to spine constraints.
        
        Args:
            film_id: Film identifier
            agent_output: Output from an agent
            context: Optional context
            
        Returns:
            List of violations found
        """
        spine = self.get_spine(film_id)
        if not spine:
            return []
        
        violations = []
        context = context or {}
        
        # Check each field in the output against spine
        for field_name in spine.frozen_fields:
            if field_name in agent_output:
                value = agent_output[field_name]
                memory = self._memory_cache.get(film_id)
                spine_value = getattr(memory, field_name, "") if memory else ""
                
                if value != spine_value and spine_value:
                    violations.append(ConstraintViolation(
                        constraint_id=f"{film_id}_{field_name}",
                        field_name=field_name,
                        expected_value=spine_value,
                        actual_value=value,
                        severity=ConstraintSeverity.ERROR,
                        message=f"Output violates immutable: {field_name}",
                        agent_id=context.get("agent_id", ""),
                        scene_id=context.get("scene_id", "")
                    ))
        
        return violations
    
    # =========================================================================
    # Guidance API
    # =========================================================================
    
    def get_guidance(
        self,
        film_id: str,
        topic: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get guidance on a topic from the spine.
        
        This is advisory only - agents can ignore guidance
        but should be aware of it.
        
        Args:
            film_id: Film identifier
            topic: Topic to get guidance on (pacing, visual, etc.)
            context: Optional context (act, scene_count, etc.)
            
        Returns:
            Guidance dict with recommendation, rationale, and flexibility
        """
        spine = self.get_spine(film_id)
        memory = self._memory_cache.get(film_id)
        
        if not spine or not memory:
            return {"recommendation": None, "rationale": "", "flexible": True}
        
        context = context or {}
        
        if topic == "pacing":
            pacing = getattr(memory, "pacing_philosophy", "")
            act = context.get("act", 0)
            
            # Act-specific pacing guidance
            if act == 2 and "slow_burn" in pacing:
                return {
                    "recommendation": "Build tension gradually in Act 2",
                    "rationale": "Pacing philosophy calls for slow_burn approach",
                    "flexible": True
                }
            elif act == 3 and "accelerated" in pacing:
                return {
                    "recommendation": "Accelerate pacing toward climax",
                    "rationale": "Pacing philosophy calls for accelerated finale",
                    "flexible": True
                }
            return {
                "recommendation": pacing or "Follow natural story rhythm",
                "rationale": "No specific pacing guidance",
                "flexible": True
            }
        
        elif topic == "visual":
            visual = getattr(memory, "visual_philosophy", "")
            return {
                "recommendation": visual or "Match scene tone",
                "rationale": "Visual philosophy guides aesthetic choices",
                "flexible": True
            }
        
        elif topic == "tone":
            emotional = getattr(memory, "emotional_contract", "")
            return {
                "recommendation": f"Maintain tone consistent with: {emotional}",
                "rationale": "Emotional contract governs audience experience",
                "flexible": False
            }
        
        return {
            "recommendation": None,
            "rationale": "No specific guidance for this topic",
            "flexible": True
        }
    
    # =========================================================================
    # Drift Detection
    # =========================================================================
    
    def check_drift(
        self,
        film_id: str,
        current_memory: FilmLevelMemory
    ) -> List[DriftReport]:
        """
        Check for drift between spine and current memory.
        
        Drift occurs when the actual film content has deviated
        from what the spine governs. This is different from
        a single violation - drift is about accumulated deviation.
        
        Args:
            film_id: Film identifier
            current_memory: Current FilmLevelMemory state
            
        Returns:
            List of DriftReports for fields that have drifted
        """
        spine = self.get_spine(film_id)
        if not spine:
            return []
        
        reports = []
        
        for field_name in spine.frozen_fields + spine.revisable_fields:
            current_value = getattr(current_memory, field_name, "")
            spine_constraint = spine.get_constraint_for_field(field_name)
            
            if not spine_constraint:
                continue
            
            # Calculate drift score (simplified - real implementation
            # would analyze actual content)
            drift_score = self._calculate_drift_score(
                current_value,
                spine_constraint.description
            )
            
            if drift_score > spine.drift_threshold:
                report = DriftReport(
                    film_id=film_id,
                    field_name=field_name,
                    drift_score=drift_score,
                    threshold=spine.drift_threshold,
                    current_value=str(current_value)[:100],
                    spine_value=spine_constraint.description[:100],
                    recommendation=f"Review {field_name} alignment with spine"
                )
                reports.append(report)
        
        return reports
    
    def _calculate_drift_score(
        self,
        current_value: str,
        spine_description: str
    ) -> float:
        """
        Calculate drift score between current value and spine.
        
        This is a simplified heuristic. Real implementation would
        use semantic similarity or content analysis.
        """
        if not current_value or not spine_description:
            return 0.0
        
        # Simple word overlap heuristic
        current_words = set(current_value.lower().split())
        spine_words = set(spine_description.lower().split())
        
        if not current_words or not spine_words:
            return 0.0
        
        overlap = len(current_words & spine_words)
        total = len(spine_words)
        
        # High overlap = low drift
        return 1.0 - (overlap / total) if total > 0 else 0.0
    
    # =========================================================================
    # Override Management
    # =========================================================================
    
    def record_override(
        self,
        film_id: str,
        field_name: str,
        old_value: str,
        new_value: str,
        reason: str,
        overridden_by: str
    ) -> bool:
        """
        Record a human override to the spine.
        
        Args:
            film_id: Film identifier
            field_name: Which field is being overridden
            old_value: Previous value
            new_value: New value
            reason: Why this override is happening
            overridden_by: User ID of person making the override
            
        Returns:
            True if override was recorded
        """
        spine = self.get_spine(film_id)
        if not spine:
            return False
        
        spine.record_override(field_name, old_value, new_value, reason, overridden_by)
        
        # Update memory cache if needed
        if film_id in self._memory_cache:
            memory = self._memory_cache[film_id]
            setattr(memory, field_name, new_value)
        
        return True
    
    def add_approved_deviation(
        self,
        film_id: str,
        field_name: str,
        approved_value: str,
        scope: str,
        reason: str,
        approved_by: str,
        expires_at: Optional[datetime] = None
    ) -> bool:
        """
        Add an approved deviation from the spine.
        
        Args:
            film_id: Film identifier
            field_name: Which field is being deviated from
            approved_value: The approved alternative value
            scope: Where this deviation applies
            reason: Why this deviation is approved
            approved_by: User ID who approved
            expires_at: Optional expiration
            
        Returns:
            True if deviation was added
        """
        spine = self.get_spine(film_id)
        if not spine:
            return False
        
        spine.add_approved_deviation(
            field_name, approved_value, scope, reason, approved_by, expires_at
        )
        return True
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_spince_summary(self, film_id: str) -> Dict[str, Any]:
        """Get a summary of the spine for display."""
        spine = self.get_spine(film_id)
        if not spine:
            return {"error": "Spine not found"}
        return spine.get_summary()
    
    def list_spines(self) -> List[str]:
        """List all film IDs with spines."""
        return list(self._spines.keys())


# Global instance
spine_service = SpineService()