"""
Creative Authority Hierarchy - Decision Priority System

This module implements a clear authority hierarchy for creative decisions,
ensuring the system behaves like a directed production rather than chaotic AI.

PRIORITY ORDER (highest to lowest):
1. USER_OVERRIDE - Direct user commands always win
2. SCENE_INTENT - Story-driven scene requirements
3. ESTABLISHED_PATTERNS - Proven patterns from successful renders
4. ADAPTIVE_SUGGESTIONS - Learned preferences (lowest priority)

Key Features:
- resolve_decision_conflict(): Resolves conflicts between decision sources
- Authority-aware decision making
- Comprehensive logging of decision sources and conflicts
- Integration with all agents via hierarchy resolver
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("studio-authority")

# ============================================================================
# ENUMS
# ============================================================================

class DecisionSource(Enum):
    """Source of a creative decision, ordered by authority"""
    USER_OVERRIDE = "user_override"      # Priority 1: User command
    SCENE_INTENT = "scene_intent"       # Priority 2: Story requirements
    ESTABLISHED_PATTERN = "established_pattern"  # Priority 3: Proven patterns
    ADAPTIVE_SUGGESTION = "adaptive_suggestion"   # Priority 4: Learned preferences
    DEFAULT = "default"                 # No specific source


# Priority mapping for comparison
AUTHORITY_PRIORITY = {
    DecisionSource.USER_OVERRIDE: 1,
    DecisionSource.SCENE_INTENT: 2,
    DecisionSource.ESTABLISHED_PATTERN: 3,
    DecisionSource.ADAPTIVE_SUGGESTION: 4,
    DecisionSource.DEFAULT: 5
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DecisionInput:
    """A single decision input with source authority"""
    value: Any
    source: DecisionSource
    confidence: float = 1.0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """Compare based on authority priority"""
        return AUTHORITY_PRIORITY[self.source] < AUTHORITY_PRIORITY[other.source]


@dataclass
class ResolvedDecision:
    """Result of resolving decision conflict"""
    final_value: Any
    decision_source: str  # "intent", "pattern", "override", etc.
    conflict_resolved: bool
    authority_used: str
    overridden_sources: List[str] = field(default_factory=list)
    reasoning: str = ""
    all_inputs: List[Dict] = field(default_factory=list)


@dataclass
class SceneIntent:
    """
    Scene intent represents the story-driven requirements for a scene.
    This is Priority 2 in the authority hierarchy.
    """
    scene_id: str = ""
    scene_type: str = ""        # INT, EXT, etc.
    emotion: str = ""           # tense, dramatic, mysterious, etc.
    genre: str = ""             # noir, horror, action, etc.
    visual_goal: str = ""      # dark, bright, moody, etc.
    emotional_goal: str = ""   # tension, suspense, joy, etc.
    pacing: str = "medium"      # slow, measured, fast
    intensity: float = 0.5      # 0.0 to 1.0
    is_turning_point: bool = False
    narrative_beat: str = ""    # setup, climax, resolution
    key_moments: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "scene_id": self.scene_id,
            "scene_type": self.scene_type,
            "emotion": self.emotion,
            "genre": self.genre,
            "visual_goal": self.visual_goal,
            "emotional_goal": self.emotional_goal,
            "pacing": self.pacing,
            "intensity": self.intensity,
            "is_turning_point": self.is_turning_point,
            "narrative_beat": self.narrative_beat,
            "key_moments": self.key_moments
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SceneIntent':
        return cls(
            scene_id=data.get("scene_id", ""),
            scene_type=data.get("scene_type", ""),
            emotion=data.get("emotion", ""),
            genre=data.get("genre", ""),
            visual_goal=data.get("visual_goal", ""),
            emotional_goal=data.get("emotional_goal", ""),
            pacing=data.get("pacing", "medium"),
            intensity=data.get("intensity", 0.5),
            is_turning_point=data.get("is_turning_point", False),
            narrative_beat=data.get("narrative_beat", ""),
            key_moments=data.get("key_moments", [])
        )


# ============================================================================
# CREATIVE AUTHORITY HIERARCHY
# ============================================================================

class CreativeAuthorityHierarchy:
    """
    Decision priority resolver for creative decisions.
    
    Ensures decisions follow the production hierarchy:
    1. User Override (highest)
    2. Scene Intent (story requirements)
    3. Established Patterns (proven success)
    4. Adaptive Suggestions (learned preferences)
    
    Usage:
        hierarchy = CreativeAuthorityHierarchy()
        result = hierarchy.resolve_decision_conflict(
            project_id=project_id,
            decision_type="camera_angle",
            inputs=[
                DecisionInput(user_value, DecisionSource.USER_OVERRIDE),
                DecisionInput(pattern_value, DecisionSource.ADAPTIVE_SUGGESTION)
            ]
        )
    """
    
    def __init__(self):
        # User overrides per project
        self._user_overrides: Dict[str, Dict[str, Any]] = {}
        
        # Scene intents per project/scene
        self._scene_intents: Dict[str, Dict[str, SceneIntent]] = {}
        
        # Decision logs for debugging
        self._decision_log: List[Dict] = []
        
        # Import services for checking patterns
        self._adaptation_engine = None
        self._deviation_engine = None
        
        logger.info("Creative Authority Hierarchy initialized")
    
    def _get_adaptation_engine(self):
        """Lazy import of adaptation engine"""
        if self._adaptation_engine is None:
            try:
                from app.services.adaptation import adaptation_engine
                self._adaptation_engine = adaptation_engine
            except ImportError:
                pass
        return self._adaptation_engine
    
    def _get_deviation_engine(self):
        """Lazy import of deviation engine"""
        if self._deviation_engine is None:
            try:
                from app.services.deviation_engine import deviation_engine
                self._deviation_engine = deviation_engine
            except ImportError:
                pass
        return self._deviation_engine
    
    # ========================================================================
    # USER OVERRIDE MANAGEMENT
    # ========================================================================
    
    def set_user_override(
        self,
        project_id: str,
        decision_type: str,
        value: Any,
        reason: str = ""
    ):
        """Set a user override for a decision type"""
        if project_id not in self._user_overrides:
            self._user_overrides[project_id] = {}
        
        self._user_overrides[project_id][decision_type] = {
            "value": value,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"USER_OVERRIDE set: {project_id}/{decision_type} = {value}")
    
    def get_user_override(
        self,
        project_id: str,
        decision_type: str
    ) -> Optional[Any]:
        """Get user override for a decision type"""
        return self._user_overrides.get(project_id, {}).get(decision_type, {}).get("value")
    
    def clear_user_override(self, project_id: str, decision_type: str):
        """Clear a user override"""
        if project_id in self._user_overrides:
            self._user_overrides[project_id].pop(decision_type, None)
        logger.info(f"USER_OVERRIDE cleared: {project_id}/{decision_type}")
    
    # ========================================================================
    # SCENE INTENT MANAGEMENT
    # ========================================================================
    
    def set_scene_intent(
        self,
        project_id: str,
        scene_id: str,
        intent: SceneIntent
    ):
        """Set scene intent for a scene"""
        if project_id not in self._scene_intents:
            self._scene_intents[project_id] = {}
        self._scene_intents[project_id][scene_id] = intent
        logger.info(f"SCENE_INTENT set: {project_id}/{scene_id}")
    
    def get_scene_intent(
        self,
        project_id: str,
        scene_id: str
    ) -> Optional[SceneIntent]:
        """Get scene intent for a scene"""
        return self._scene_intents.get(project_id, {}).get(scene_id)
    
    def get_scene_value(
        self,
        project_id: str,
        scene_id: str,
        intent_key: str
    ) -> Optional[Any]:
        """Get specific value from scene intent"""
        intent = self.get_scene_intent(project_id, scene_id)
        if intent:
            return getattr(intent, intent_key, None)
        return None
    
    # ========================================================================
    # CORE RESOLUTION
    # ========================================================================
    
    def resolve_decision_conflict(
        self,
        project_id: str,
        decision_type: str,
        scene_id: Optional[str] = None,
        inputs: Optional[List[DecisionInput]] = None,
        default_value: Any = None,
        check_deviation: bool = False,
        scene_intensity: float = 0.5
    ) -> ResolvedDecision:
        """
        Resolve decision conflict using authority hierarchy.
        
        Args:
            project_id: Project identifier
            decision_type: Type of decision (camera_angle, lighting, etc.)
            scene_id: Scene identifier for scene intent lookup
            inputs: List of decision inputs with sources
            default_value: Default value if no inputs
            check_deviation: Whether to check deviation engine
            scene_intensity: Intensity for deviation check
        
        Returns:
            ResolvedDecision with final_value and debug info
        """
        resolved = ResolvedDecision(
            final_value=default_value,
            decision_source="default",
            conflict_resolved=False,
            authority_used="default"
        )
        
        # Collect all inputs with their sources
        all_inputs_list = []
        
        # Priority 1: USER OVERRIDE
        user_override = self.get_user_override(project_id, decision_type)
        if user_override is not None:
            all_inputs_list.append({
                "value": user_override,
                "source": DecisionSource.USER_OVERRIDE.value,
                "reason": "User override"
            })
            resolved.final_value =user_override
            resolved.decision_source = "override"
            resolved.conflict_resolved = True
            resolved.authority_used = "user_override"
        
        # Priority 2: SCENE INTENT
        scene_value = None
        if scene_id:
            # Map decision types to scene intent attributes
            intent_mapping = {
                "camera_angle": "visual_goal",
                "lighting": "emotion",
                "pacing": "pacing",
                "intensity": "intensity"
            }
            intent_key = intent_mapping.get(decision_type)
            if intent_key:
                scene_value = self.get_scene_value(project_id, scene_id, intent_key)
            
            # Also check if scene has explicit overrides
            intent = self.get_scene_intent(project_id, scene_id)
            if intent and hasattr(intent, decision_type):
                scene_value = getattr(intent, decision_type)
        
        if scene_value is not None:
            all_inputs_list.append({
                "value": scene_value,
                "source": DecisionSource.SCENE_INTENT.value,
                "reason": f"Scene intent: {scene_value}"
            })
            
            # Scene intent only overrides if higher than current
            if resolved.decision_source in ["default", "adaptive"]:
                resolved.final_value = scene_value
                resolved.decision_source = "intent"
                resolved.conflict_resolved = True
                resolved.authority_used = "scene_intent"
        
        # Priority 3: ESTABLISHED PATTERNS
        adaptation = self._get_adaptation_engine()
        established_pattern = None
        if adaptation:
            try:
                established_pattern = adaptation.get_recommended_pattern(
                    project_id, decision_type
                )
            except Exception:
                pass
        
        if established_pattern:
            all_inputs_list.append({
                "value": established_pattern,
                "source": DecisionSource.ESTABLISHED_PATTERN.value,
                "reason": "Established pattern from feedback"
            })
            
            # Only use if no higher authority has decided
            if resolved.decision_source == "default":
                resolved.final_value = established_pattern
                resolved.decision_source = "pattern"
                resolved.authority_used = "established_pattern"
        
        # Priority 4: ADAPTIVE SUGGESTIONS (from inputs)
        if inputs:
            for inp in sorted(inputs):  # Sorted by authority priority
                all_inputs_list.append({
                    "value": inp.value,
                    "source": inp.source.value,
                    "confidence": inp.confidence,
                    "reason": inp.reason
                })
                
                # Only apply if no higher authority has decided
                current_priority = AUTHORITY_PRIORITY[DecisionSource(resolved.decision_source) if resolved.decision_source != "default" else DecisionSource.DEFAULT]
                input_priority = AUTHORITY_PRIORITY[inp.source]
                
                if input_priority < current_priority:
                    resolved.final_value = inp.value
                    resolved.decision_source = inp.source.value
                    resolved.authority_used = inp.source.value
        
        # Check for conflicts (multiple sources with different values)
        unique_sources = set(inp["source"] for inp in all_inputs_list)
        resolved.conflict_resolved = len(all_inputs_list) > 1
        
        if resolved.conflict_resolved:
            resolved.overridden_sources = [
                inp["source"] for inp in all_inputs_list[1:]
                if inp["source"] != resolved.decision_source
            ]
            logger.info(
                f"CONFLICT_RESOLVED: {decision_type} = {resolved.final_value} "
                f"(source: {resolved.decision_source}, "
                f"overridden: {resolved.overridden_sources})"
            )
        
        # Check deviation engine (can override established patterns only)
        if check_deviation and resolved.decision_source in ["pattern", "default"]:
            deviation = self._get_deviation_engine()
            if deviation:
                try:
                    scene_context = {"scene_id": scene_id} if scene_id else {}
                    dev_result = deviation.should_apply_deviation(
                        project_id, scene_context, scene_intensity
                    )
                    
                    if dev_result.deviation_applied:
                        all_inputs_list.append({
                            "value": dev_result.deviated_pattern,
                            "source": "deviation",
                            "reason": dev_result.deviation_reason
                        })
                        resolved.final_value = dev_result.deviated_pattern
                        resolved.decision_source = "deviation"
                        resolved.conflict_resolved = True
                        resolved.overridden_sources.append(resolved.authority_used)
                        resolved.authority_used = "deviation_engine"
                        
                        logger.info(
                            f"DEVIATION OVERRIDE: {decision_type} = {dev_result.deviated_pattern} "
                            f"({dev_result.deviation_reason})"
                        )
                except Exception:
                    pass
        
        # Log the decision
        resolved.all_inputs = all_inputs_list
        self._log_decision(project_id, decision_type, resolved)
        
        # Debug log
        logger.debug(
            f"DECISION: {decision_type} = {resolved.final_value} "
            f"(source: {resolved.decision_source}, "
            f"conflict: {resolved.conflict_resolved})"
        )
        
        return resolved
    
    # ========================================================================
    # CONVENIENCE METHODS
    # ========================================================================
    
    def resolve_camera_angle(
        self,
        project_id: str,
        scene_id: Optional[str] = None,
        adaptive_inputs: Optional[List[DecisionInput]] = None
    ) -> ResolvedDecision:
        """Resolve camera angle decision"""
        return self.resolve_decision_conflict(
            project_id=project_id,
            decision_type="camera_angle",
            scene_id=scene_id,
            inputs=adaptive_inputs,
            default_value="medium",
            check_deviation=True
        )
    
    def resolve_lighting(
        self,
        project_id: str,
        scene_id: Optional[str] = None,
        adaptive_inputs: Optional[List[DecisionInput]] = None
    ) -> ResolvedDecision:
        """Resolve lighting decision"""
        return self.resolve_decision_conflict(
            project_id=project_id,
            decision_type="lighting",
            scene_id=scene_id,
            inputs=adaptive_inputs,
            default_value="cinematic",
            check_deviation=True
        )
    
    def resolve_framing(
        self,
        project_id: str,
        scene_id: Optional[str] = None,
        adaptive_inputs: Optional[List[DecisionInput]] = None
    ) -> ResolvedDecision:
        """Resolve framing decision"""
        return self.resolve_decision_conflict(
            project_id=project_id,
            decision_type="framing",
            scene_id=scene_id,
            inputs=adaptive_inputs,
            default_value="standard"
        )
    
    def resolve_pacing(
        self,
        project_id: str,
        scene_id: Optional[str] = None,
        adaptive_inputs: Optional[List[DecisionInput]] = None
    ) -> ResolvedDecision:
        """Resolve pacing decision"""
        return self.resolve_decision_conflict(
            project_id=project_id,
            decision_type="pacing",
            scene_id=scene_id,
            inputs=adaptive_inputs,
            default_value="medium"
        )
    
    def resolve_prompt_style(
        self,
        project_id: str,
        scene_id: Optional[str] = None,
        adaptive_inputs: Optional[List[DecisionInput]] = None
    ) -> ResolvedDecision:
        """Resolve prompt style decision"""
        return self.resolve_decision_conflict(
            project_id=project_id,
            decision_type="prompt_style",
            scene_id=scene_id,
            inputs=adaptive_inputs,
            default_value="cinematic"
        )
    
    # ========================================================================
    # LOGGING & DEBUGGING
    # ========================================================================
    
    def _log_decision(self, project_id: str, decision_type: str, resolved: ResolvedDecision):
        """Log decision for analysis"""
        self._decision_log.append({
            "timestamp": datetime.now().isoformat(),
            "project_id": project_id,
            "decision_type": decision_type,
            "final_value": resolved.final_value,
            "decision_source": resolved.decision_source,
            "conflict_resolved": resolved.conflict_resolved,
            "overridden_sources": resolved.overridden_sources,
            "authority_used": resolved.authority_used
        })
        
        # Keep log bounded
        if len(self._decision_log) > 5000:
            self._decision_log = self._decision_log[-2500:]
    
    def get_decision_log(
        self,
        project_id: Optional[str] = None,
        decision_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get decision log entries"""
        entries = self._decision_log
        
        if project_id:
            entries = [e for e in entries if e.get("project_id") == project_id]
        
        if decision_type:
            entries = [e for e in entries if e.get("decision_type") == decision_type]
        
        return entries[-limit:]
    
    def get_hierarchy_debug(
        self,
        project_id: str,
        decision_type: str,
        scene_id: Optional[str] = None
    ) -> Dict:
        """Get full hierarchy debug info for a decision"""
        debug = {
            "project_id": project_id,
            "decision_type": decision_type,
            "scene_id": scene_id,
            "hierarchy_order": [
                "1. USER_OVERRIDE (highest)",
                "2. SCENE_INTENT",
                "3. ESTABLISHED_PATTERNS",
                "4. ADAPTIVE_SUGGESTIONS (lowest)"
            ],
            "sources_active": []
        }
        
        # Check each source
        user_override = self.get_user_override(project_id, decision_type)
        if user_override is not None:
            debug["sources_active"].append({
                "source": "user_override",
                "priority": 1,
                "value": user_override
            })
        
        scene_value = self.get_scene_value(project_id, scene_id, decision_type) if scene_id else None
        if scene_value is not None:
            debug["sources_active"].append({
                "source": "scene_intent",
                "priority": 2,
                "value": scene_value
            })
        
        adaptation = self._get_adaptation_engine()
        if adaptation:
            try:
                pattern = adaptation.get_recommended_pattern(project_id, decision_type)
                if pattern:
                    debug["sources_active"].append({
                        "source": "established_pattern",
                        "priority": 3,
                        "value": pattern
                    })
            except Exception:
                pass
        
        return debug


# Global instance
authority_hierarchy = CreativeAuthorityHierarchy()
