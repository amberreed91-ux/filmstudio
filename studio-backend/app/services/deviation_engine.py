"""
Pattern Deviation Engine - Intentional Contrast System

This module enables the autonomous system to intentionally break from
established patterns to create contrast and emotional impact.

Deviation Triggers:
1. High intensity scenes (> 0.7)
2. Narrative turning points
3. Repeated pattern saturation

Deviation Types:
- invert_pattern: Opposite of established preference
- disrupt_composition: Break visual continuity
- change_pacing: Abrupt rhythm shift

Safety Constraints:
- Must respect style boundaries
- Must log deviation reason
- Returns deviation_applied flag for traceability
"""

import logging
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field

from app.services.adaptation import adaptation_engine, SceneIntent

logger = logging.getLogger("studio-deviation")

# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class DeviationType(Enum):
    """Types of deviation from established patterns"""
    INVERT_PATTERN = "invert_pattern"
    DISRUPT_COMPOSITION = "disrupt_composition"
    CHANGE_PACING = "change_pacing"
    CONTRAST_COLOR = "contrast_color"
    BREAK_RHYTHM = "break_rhythm"


class DeviationTrigger(Enum):
    """Conditions that trigger deviation"""
    HIGH_INTENSITY = "high_intensity"
    NARRATIVE_TURNING_POINT = "narrative_turning_point"
    PATTERN_SATURATION = "pattern_saturation"
    EMOTIONAL_PEAK = "emotional_peak"
    CONTRAST_REQUIRED = "contrast_required"


@dataclass
class DeviationOpportunity:
    """Analysis of when and how to deviate"""
    should_deviate: bool = False
    trigger: Optional[DeviationTrigger] = None
    deviation_type: Optional[DeviationType] = None
    target_pattern_type: Optional[str] = None
    proposed_value: Optional[str] = None
    inversion_map: Optional[Dict[str, str]] = None
    intensity_score: float = 0.0
    saturation_level: float = 0.0
    reason: str = ""
    safety_check_passed: bool = False


@dataclass
class DeviationResult:
    """Result of applying deviation"""
    deviation_applied: bool = False
    deviation_reason: str = ""
    original_pattern: Optional[str] = None
    deviated_pattern: Optional[str] = None
    deviation_type: Optional[DeviationType] = None
    trigger: Optional[DeviationTrigger] = None
    safety_respected: bool = True
    within_boundaries: bool = True
    emotional_impact_expected: float = 0.0


# ============================================================================
# INVERSION MAPS
# ============================================================================

STANDARD_INVERSIONS: Dict[str, Dict[str, str]] = {
    "camera_angle": {
        "wide": "close",
        "medium": "extreme_close",
        "close": "wide",
        "overhead": "low_angle",
        "low_angle": "overhead",
        "dutch": "level",
        "extreme_close": "medium"
    },
    "lighting": {
        "low_key": "high_key",
        "high_key": "low_key",
        "natural": "dramatic",
        "dramatic": "natural",
        "chiaroscuro": "flat",
        "flat": "chiaroscuro",
        "rim": "broad",
        "broad": "rim"
    },
    "prompt_style": {
        "dark": "bright",
        "moody": "vibrant",
        "noir": "warm",
        "vintage": "futuristic",
        "muted": "saturated",
        "gritty": "polished"
    },
    "framing": {
        "centered": "rule_of_thirds",
        "symmetric": "asymmetric",
        "tight": "wide",
        "isolated": "crowded",
        "static": "dynamic",
        "balanced": "imbalanced"
    },
    "pacing": {
        "slow": "fast",
        "measured": "staccato",
        "flowing": "choppy",
        "steady": "erratic"
    },
    "color": {
        "monochrome": "vivid",
        "cool": "warm",
        "desaturated": "saturated",
        "muted": "bright",
        "dark_tones": "light_tones"
    },
    "composition": {
        "static": "dynamic",
        "centered": "peripheral",
        "orderly": "chaotic",
        "minimal": "complex",
        "simple": "layered"
    }
}


# ============================================================================
# DEVIATION ENGINE
# ============================================================================

class DeviationEngine:
    """
    Pattern Deviation Engine - Creates intentional contrast.
    
    The engine analyzes scene context and determines when to break
    from established patterns for dramatic effect, while still
    respecting style boundaries.
    """
    
    def __init__(self):
        # Thresholds
        self._high_intensity_threshold = 0.7
        self._saturation_threshold = 0.8  # Pattern used 4+ times consecutively
        self._saturation_window = 5  # Look back 5 decisions
        
        # Deviation cooldown (don't deviate twice in a row)
        self._deviation_cooldown: Dict[str, int] = {}
        self._cooldown_frames = 2
        
        # Inversion maps (customizable per project)
        self._custom_inversions: Dict[str, Dict[str, Dict[str, str]]] = {}
        
        # Deviation logs for analysis
        self._deviation_log: List[Dict] = []
        
        logger.info("Deviation Engine initialized")
    
    # =========================================================================
    # TRIGGER ANALYSIS
    # =========================================================================
    
    def analyze_deviation_opportunity(
        self,
        project_id: str,
        scene_context: Dict,
        scene_intensity: float = 0.5
    ) -> DeviationOpportunity:
        """
        Analyze if current scene presents a deviation opportunity.
        
        Args:
            project_id: Project identifier
            scene_context: Current scene metadata
            scene_intensity: Emotional intensity (0.0-1.0)
        
        Returns:
            DeviationOpportunity with analysis
        """
        opportunity = DeviationOpportunity()
        
        # Check cooldown
        if self._is_in_cooldown(project_id):
            opportunity.reason = "Deviation in cooldown period"
            return opportunity
        
        # Trigger 1: High intensity
        if scene_intensity >= self._high_intensity_threshold:
            opportunity.trigger = DeviationTrigger.HIGH_INTENSITY
            opportunity.intensity_score = scene_intensity
            logger.info(f"High intensity detected: {scene_intensity}")
        
        # Trigger 2: Narrative turning point
        elif scene_context.get("is_turning_point", False) or \
             scene_context.get("narrative_beat") in ["climax", "revelation", "turn"]:
            opportunity.trigger = DeviationTrigger.NARRATIVE_TURNING_POINT
            opportunity.reason = "Narrative turning point detected"
            logger.info("Narrative turning point detected")
        
        # Trigger 3: Pattern saturation
        saturation = self._calculate_saturation(project_id)
        if saturation >= self._saturation_threshold:
            opportunity.trigger = DeviationTrigger.PATTERN_SATURATION
            opportunity.saturation_level = saturation
            opportunity.reason = f"Pattern saturation: {saturation:.1%}"
            logger.info(f"Pattern saturation: {saturation:.1%}")
        
        # Trigger 4: Emotional peak in notes
        elif any(keyword in scene_context.get("notes", "").lower() 
                 for keyword in ["peak", "climax", "shock", "surprise"]):
            opportunity.trigger = DeviationTrigger.EMOTIONAL_PEAK
            opportunity.reason = "Emotional peak keyword detected"
        
        # If no trigger, no deviation
        if opportunity.trigger is None:
            opportunity.reason = "No deviation trigger active"
            return opportunity
        
        # Determine deviation type
        deviation = self._determine_deviation_type(
            project_id, 
            scene_context,
            opportunity.trigger
        )
        opportunity.should_deviate = deviation is not None
        
        if deviation:
            opportunity.deviation_type = deviation["type"]
            opportunity.target_pattern_type = deviation["pattern_type"]
            opportunity.proposed_value = deviation["proposed_value"]
            opportunity.inversion_map = deviation.get("inversion_map")
            opportunity.reason = deviation.get("reason", "")
            
            # Safety check
            opportunity.safety_check_passed = self._check_safety(
                project_id,
                deviation["pattern_type"],
                deviation["proposed_value"]
            )
        
        return opportunity
    
    def _is_in_cooldown(self, project_id: str) -> bool:
        """Check if project is in deviation cooldown"""
        frames = self._deviation_cooldown.get(project_id, 0)
        if frames > 0:
            self._deviation_cooldown[project_id] = frames - 1
            return True
        return False
    
    def _calculate_saturation(self, project_id: str) -> float:
        """Calculate how saturated the recent patterns are"""
        decisions = adaptation_engine.get_decision_log(project_id, limit=self._saturation_window)
        
        if len(decisions) < 3:
            return 0.0
        
        # Count pattern type occurrences
        pattern_counts: Dict[str, int] = {}
        for decision in decisions:
            decision_type = decision.get("decision_type")
            if decision_type:
                pattern_counts[decision_type] = pattern_counts.get(decision_type, 0) + 1
        
        if not pattern_counts:
            return 0.0
        
        # Saturation = max repetition / window size
        max_count = max(pattern_counts.values())
        return max_count / len(decisions)
    
    def _determine_deviation_type(
        self,
        project_id: str,
        scene_context: Dict,
        trigger: DeviationTrigger
    ) -> Optional[Dict[str, Any]]:
        """Determine which pattern to deviate and how"""
        
        # Get established patterns
        established = adaptation_engine.get_project_established_patterns(project_id)
        
        if not established:
            # No established patterns, can't deviate meaningfully
            return None
        
        # Choose target pattern based on trigger
        if trigger == DeviationTrigger.HIGH_INTENSITY:
            # High intensity: invert visual style
            target_pattern = "lighting"
            if target_pattern not in established:
                target_pattern = "prompt_style"
        elif trigger == DeviationTrigger.PATTERN_SATURATION:
            # Saturation: pick the saturated pattern type
            # Find most repeated pattern type
            decisions = adaptation_engine.get_decision_log(project_id, limit=self._saturation_window)
            pattern_counts: Dict[str, int] = {}
            for d in decisions:
                dt = d.get("decision_type")
                if dt:
                    pattern_counts[dt] = pattern_counts.get(dt, 0) + 1
            if pattern_counts:
                target_pattern = max(pattern_counts, key=pattern_counts.get)
            else:
                target_pattern = list(established.keys())[0]
        else:
            # Default: pick first available pattern
            target_pattern = list(established.keys())[0]
        
        current_value = established.get(target_pattern, "")
        
        # Get inversion map
        inversions = self._get_inversion_map(project_id, target_pattern)
        
        if current_value not in inversions:
            # No inversion defined, use composition disruption
            return {
                "type": DeviationType.DISRUPT_COMPOSITION,
                "pattern_type": target_pattern,
                "proposed_value": self._disrupt_composition(target_pattern, current_value),
                "inversion_map": {},
                "reason": f"No inversion for '{current_value}', using composition disruption"
            }
        
        proposed_value = inversions[current_value]
        
        reason_map = {
            DeviationTrigger.HIGH_INTENSITY: "High intensity scene - invert established style",
            DeviationTrigger.NARRATIVE_TURNING_POINT: "Narrative turning point - break visual continuity",
            DeviationTrigger.PATTERN_SATURATION: f"Pattern saturation on {target_pattern} - deviate for contrast",
            DeviationTrigger.EMOTIONAL_PEAK: "Emotional peak - surprise with visual contrast",
            DeviationTrigger.CONTRAST_REQUIRED: "Scene requires visual contrast"
        }
        
        return {
            "type": DeviationType.INVERT_PATTERN,
            "pattern_type": target_pattern,
            "proposed_value": proposed_value,
            "inversion_map": inversions,
            "reason": reason_map.get(trigger, "Deviation for contrast")
        }
    
    def _get_inversion_map(self, project_id: str, pattern_type: str) -> Dict[str, str]:
        """Get inversion map for pattern type (custom or standard)"""
        if project_id in self._custom_inversions:
            return self._custom_inversions[project_id].get(pattern_type, {})
        return STANDARD_INVERSIONS.get(pattern_type, {})
    
    def _disrupt_composition(
        self,
        pattern_type: str,
        current_value: str
    ) -> str:
        """Generate a disruptive alternative"""
        disruptions = {
            "camera_angle": ["dutch_angle", "cant_frame", "tilted"],
            "framing": ["unconventional", "fragmented", "split"],
            "pacing": ["freeze", "slow_motion", "time_lapse"],
            "color": ["inverted", "negated", "shifting"]
        }
        return disruptions.get(pattern_type, ["contrast"])[0]
    
    def _check_safety(
        self,
        project_id: str,
        pattern_type: str,
        proposed_value: str
    ) -> bool:
        """Check if deviation respects style boundaries"""
        
        # Get style boundaries
        boundaries = adaptation_engine._style_boundaries.get(project_id, {})
        
        if pattern_type in boundaries:
            allowed = boundaries[pattern_type].get("allowed_values", [])
            if allowed and proposed_value not in allowed:
                logger.warning(
                    f"Deviation SAFETY CHECK FAILED: '{proposed_value}' "
                    f"not in allowed values for {pattern_type}"
                )
                return False
        
        return True
    
    # =========================================================================
    # DEVIATION APPLICATION
    # =========================================================================
    
    def should_apply_deviation(
        self,
        project_id: str,
        scene_context: Dict,
        scene_intensity: float = 0.5
    ) -> DeviationResult:
        """
        Main entry point: determine and apply deviation if appropriate.
        
        Returns DeviationResult with:
        - deviation_applied: bool
        - deviation_reason: str
        """
        
        # Analyze opportunity
        opportunity = self.analyze_deviation_opportunity(
            project_id,
            scene_context,
            scene_intensity
        )
        
        result = DeviationResult()
        
        if not opportunity.should_deviate:
            result.deviation_applied = False
            result.deviation_reason = opportunity.reason
            return result
        
        if not opportunity.safety_check_passed:
            result.deviation_applied = False
            result.deviation_reason = "Safety check failed - would violate style boundaries"
            result.safety_respected = True  # We respected safety by not deviating
            return result
        
        # Get original pattern
        established = adaptation_engine.get_project_established_patterns(project_id)
        original_pattern = established.get(opportunity.target_pattern_type, "")
        
        # Log the deviation decision
        adaptation_engine.log_adaptive_decision(
            project_id=project_id,
            agent_role="deviation_engine",
            decision_type=f"deviation_{opportunity.target_pattern_type}",
            decision=opportunity.proposed_value,
            memory_used={
                "trigger": opportunity.trigger.value if opportunity.trigger else None,
                "deviation_type": opportunity.deviation_type.value if opportunity.deviation_type else None,
                "scene_intensity": opportunity.intensity_score,
                "saturation": opportunity.saturation_level
            },
            reason=opportunity.reason,
            based_on_feedback=True,
            contradicted=True  # We are contradicting established pattern
        )
        
        # Set cooldown
        self._deviation_cooldown[project_id] = self._cooldown_frames
        
        # Build result
        result.deviation_applied = True
        result.deviation_reason = opportunity.reason
        result.original_pattern = original_pattern
        result.deviated_pattern = opportunity.proposed_value
        result.deviation_type = opportunity.deviation_type
        result.trigger = opportunity.trigger
        result.safety_respected = True
        result.within_boundaries = True
        result.emotional_impact_expected = self._estimate_impact(
            opportunity.trigger,
            opportunity.intensity_score
        )
        
        # Log to internal deviation log
        self._log_deviation(result, project_id)
        
        logger.info(
            f"DEVIATION APPLIED | {project_id} | "
            f"{opportunity.target_pattern_type}: {original_pattern} → {opportunity.proposed_value} | "
            f"trigger: {opportunity.trigger.value if opportunity.trigger else 'unknown'}"
        )
        
        return result
    
    def _estimate_impact(
        self,
        trigger: DeviationTrigger,
        intensity: float
    ) -> float:
        """Estimate expected emotional impact of deviation"""
        base_impact = {
            DeviationTrigger.HIGH_INTENSITY: 0.8,
            DeviationTrigger.NARRATIVE_TURNING_POINT: 0.9,
            DeviationTrigger.PATTERN_SATURATION: 0.6,
            DeviationTrigger.EMOTIONAL_PEAK: 0.95,
            DeviationTrigger.CONTRAST_REQUIRED: 0.7
        }.get(trigger, 0.5)
        
        return base_impact * intensity
    
    def _log_deviation(self, result: DeviationResult, project_id: str):
        """Log deviation for analysis"""
        from datetime import datetime
        self._deviation_log.append({
            "timestamp": datetime.now().isoformat(),
            "project_id": project_id,
            "deviation_applied": result.deviation_applied,
            "deviation_reason": result.deviation_reason,
            "original": result.original_pattern,
            "deviated": result.deviated_pattern,
            "type": result.deviation_type.value if result.deviation_type else None,
            "trigger": result.trigger.value if result.trigger else None,
            "impact_expected": result.emotional_impact_expected
        })
        
        # Keep log bounded
        if len(self._deviation_log) > 1000:
            self._deviation_log = self._deviation_log[-500:]
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    def set_custom_inversions(
        self,
        project_id: str,
        pattern_type: str,
        inversions: Dict[str, str]
    ):
        """Set custom inversion map for a project/pattern type"""
        if project_id not in self._custom_inversions:
            self._custom_inversions[project_id] = {}
        self._custom_inversions[project_id][pattern_type] = inversions
        logger.info(f"Custom inversions set for {project_id}/{pattern_type}")
    
    def set_thresholds(
        self,
        high_intensity: float = 0.7,
        saturation: float = 0.8
    ):
        """Configure deviation thresholds"""
        self._high_intensity_threshold = high_intensity
        self._saturation_threshold = saturation
        logger.info(
            f"Thresholds updated: intensity={high_intensity}, saturation={saturation}"
        )
    
    def get_deviation_history(
        self,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get deviation history for analysis"""
        history = self._deviation_log
        
        if project_id:
            history = [d for d in history if d.get("project_id") == project_id]
        
        return history[-limit:]
    
    def get_deviation_stats(self, project_id: str) -> Dict:
        """Get deviation statistics"""
        project_deviations = [
            d for d in self._deviation_log 
            if d.get("project_id") == project_id
        ]
        
        if not project_deviations:
            return {
                "total_deviations": 0,
                "deviation_rate": 0.0,
                "avg_impact": 0.0,
                "triggers_used": {},
                "types_used": {}
            }
        
        applied = [d for d in project_deviations if d.get("deviation_applied")]
        
        triggers = {}
        types_used = {}
        for d in applied:
            t = d.get("trigger", "unknown")
            triggers[t] = triggers.get(t, 0) + 1
            tp = d.get("type", "unknown")
            types_used[tp] = types_used.get(tp, 0) + 1
        
        return {
            "total_deviations": len(project_deviations),
            "deviation_applied": len(applied),
            "deviation_rate": len(applied) / len(project_deviations),
            "avg_impact": sum(d.get("impact_expected", 0) for d in applied) / len(applied) if applied else 0,
            "triggers_used": triggers,
            "types_used": types_used
        }


# Global deviation engine instance
deviation_engine = DeviationEngine()
