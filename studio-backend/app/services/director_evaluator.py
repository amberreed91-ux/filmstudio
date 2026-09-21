"""
Director Evaluator - Phase 3.3

Deterministic director evaluation path using SpineConsumptionService.
Provides structured scene evaluation with scoring pillars and instant rejection rules.

Evaluation Pillars (weights):
- intent_alignment: 0.30
- emotional_consistency: 0.30
- visual_coherence: 0.20
- continuity: 0.20

Decision Thresholds:
- score >= 0.80 → APPROVE
- 0.60 to 0.79 → REVISE
- score < 0.60 → REJECT

Instant Rejection Rules:
1. over-explaining dialogue
2. tone violation against spine
3. generic visuals (2+ of: interchangeable, emotionally neutral, default coverage, unmotivated style)

Director Constraints:
- prefer_subtext_over_exposition
- reject_obvious_dialogue
- enforce_tone_consistency
- require_visual_intent
"""

from typing import Dict, List, Optional, Any
from enum import Enum
import logging

from app.models.taste_learning import TasteDimension

logger = logging.getLogger("studio-director-evaluator")


class Decision(str, Enum):
    """Director evaluation decision"""
    APPROVE = "APPROVE"
    REVISE = "REVISE"
    REJECT = "REJECT"


class DirectorEvaluator:
    """
    Deterministic director evaluation using spine, structure, and memory context.
    
    This evaluator:
    1. Validates required inputs
    2. Runs instant rejection rules first
    3. If not rejected, runs deterministic scoring
    4. Returns structured decision with reasoning
    """

    # Scoring weights
    WEIGHTS = {
        "intent_alignment": 0.30,
        "emotional_consistency": 0.30,
        "visual_coherence": 0.20,
        "continuity": 0.20,
    }

    # Decision thresholds
    APPROVE_THRESHOLD = 0.80
    REVISE_THRESHOLD = 0.60
    MAX_TASTE_SCORE_DELTA = 0.05
    MAX_TASTE_DIMENSION_DELTA = 0.02
    MAX_CINEMATIC_SCORE_DELTA = 0.05
    MAX_CINEMATIC_DIMENSION_DELTA = 0.02

    # Generic visual indicators
    GENERIC_VISUAL_INDICATORS = [
        "interchangeable",
        "emotionally_neutral",
        "default_coverage",
        "unmotivated_style",
    ]

    def __init__(self):
        """Initialize the director evaluator."""
        pass

    def evaluate(
        self,
        scene_data: Dict[str, Any],
        spine: Optional[Dict[str, Any]] = None,
        structure: Optional[Dict[str, Any]] = None,
        memory: Optional[Dict[str, Any]] = None,
        taste_calibration: Optional[Dict[str, Any]] = None,
        cinematic_language_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a scene against spine, structure, and memory context.

        Args:
            scene_data: Scene data to evaluate (dialogue, visuals, actions, etc.)
            spine: Spine constraint context (from SpineConsumptionService)
            structure: Film structure context (from SpineConsumptionService)
            memory: Film memory context (from SpineConsumptionService)

        Returns:
            Structured evaluation result with decision, score, and reasoning
        """
        result = {
            "decision": None,
            "score": 0.0,
            "pillars": {
                "intent_alignment": 0.0,
                "emotional_consistency": 0.0,
                "visual_coherence": 0.0,
                "continuity": 0.0,
            },
            "rejection_reasons": [],
            "revision_notes": [],
            "approved": False,
            "requires_revision": False,
            "taste_influence": {
                "applied": False,
                "affected_dimensions": [],
                "total_score_delta": 0.0,
                "adjustments": {},
                "confidence": {},
                "signal_counts": {},
            },
            "cinematic_influence": {
                "applied": False,
                "affected_signals": [],
                "total_score_delta": 0.0,
                "adjustments": {},
                "confidence": {},
                "generated_notes": [],
            },
        }

        # Step 1: Validate required inputs
        if not scene_data:
            result["decision"] = Decision.REJECT
            result["rejection_reasons"].append("Missing scene data")
            result["notes"] = "Cannot evaluate: scene data is required"
            return result

        # Step 2: If spine is missing, fail safely (do not silently approve)
        if not spine or not spine.get("available"):
            result["decision"] = Decision.REJECT
            result["rejection_reasons"].append("Spine context unavailable")
            result["notes"] = "Cannot approve without spine context - requires revision"
            return result

        # Step 3: Run instant rejection rules first
        rejection_reasons = self._check_instant_rejection(scene_data, spine, structure)
        if rejection_reasons:
            result["decision"] = Decision.REJECT
            result["rejection_reasons"] = rejection_reasons
            result["approved"] = False
            result["requires_revision"] = True
            result["notes"] = self._format_rejection_notes(rejection_reasons)
            return result

        # Step 4: Run deterministic scoring
        scores = self._calculate_scores(scene_data, spine, structure, memory)
        result["pillars"] = scores

        # Calculate weighted total
        total_score = (
            scores["intent_alignment"] * self.WEIGHTS["intent_alignment"] +
            scores["emotional_consistency"] * self.WEIGHTS["emotional_consistency"] +
            scores["visual_coherence"] * self.WEIGHTS["visual_coherence"] +
            scores["continuity"] * self.WEIGHTS["continuity"]
        )
        taste_influence = self._calculate_taste_influence(scene_data, taste_calibration)
        total_score += taste_influence["total_score_delta"]
        cinematic_influence = self._calculate_cinematic_influence(scene_data, cinematic_language_context)
        total_score += cinematic_influence["total_score_delta"]
        total_score = max(0.0, min(1.0, total_score))
        result["score"] = round(total_score, 3)
        result["taste_influence"] = taste_influence
        result["cinematic_influence"] = cinematic_influence
        style_conflict = scene_data.get("style_conflict") if isinstance(scene_data, dict) else None
        if isinstance(style_conflict, dict) and style_conflict.get("conflict") is True:
            conflict_reason = (
                style_conflict.get("reason")
                if isinstance(style_conflict.get("reason"), str) and style_conflict.get("reason").strip()
                else "Scene conflicts with established studio style patterns."
            )
            result["revision_notes"].append(
                f"You are breaking your established pattern: slow burn pacing. This scene introduces fast escalation. Confirm or revise. ({conflict_reason})"
            )

        # Step 5: Apply decision thresholds
        if total_score >= self.APPROVE_THRESHOLD:
            result["decision"] = Decision.APPROVE
            result["approved"] = True
            result["requires_revision"] = False
            result["notes"] = "Scene approved"
        elif total_score >= self.REVISE_THRESHOLD:
            result["decision"] = Decision.REVISE
            result["approved"] = False
            result["requires_revision"] = True
            result["revision_notes"] = self._generate_revision_notes(scene_data, spine, scores)
            result["notes"] = "Scene requires revision"
        else:
            result["decision"] = Decision.REJECT
            result["approved"] = False
            result["requires_revision"] = True
            result["revision_notes"] = self._generate_revision_notes(scene_data, spine, scores)
            result["notes"] = "Scene rejected"

        if result["requires_revision"]:
            for note in cinematic_influence.get("generated_notes", []):
                if note not in result["revision_notes"]:
                    result["revision_notes"].append(note)
        elif isinstance(style_conflict, dict) and style_conflict.get("conflict") is True:
            result["notes"] = f"{result['notes']} | Style conflict warning: {style_conflict.get('reason')}"

        return result

    def _calculate_cinematic_influence(
        self,
        scene_data: Dict[str, Any],
        cinematic_language_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply tiny bounded cinematic-language calibration with explicit provenance."""
        if not isinstance(cinematic_language_context, dict):
            return {
                "applied": False,
                "affected_signals": [],
                "total_score_delta": 0.0,
                "adjustments": {},
                "confidence": {},
                "generated_notes": [],
            }

        summary = cinematic_language_context.get("summary") or {}
        heuristic_outputs = cinematic_language_context.get("heuristic_outputs") or {}
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(heuristic_outputs, dict):
            heuristic_outputs = {}
        if not cinematic_language_context.get("available"):
            return {
                "applied": False,
                "affected_signals": [],
                "total_score_delta": 0.0,
                "adjustments": {},
                "confidence": {},
                "generated_notes": [],
            }

        confidence = summary.get("confidence") or {}
        if not isinstance(confidence, dict):
            confidence = {}

        total_delta = 0.0
        adjustments: Dict[str, float] = {}
        confidence_used: Dict[str, float] = {}
        generated_notes: List[str] = []

        visual_intent = summary.get("visual_intent", heuristic_outputs.get("visual_intent_category", "none_detected"))
        visual_intent_confidence = self._coerce_float(
            heuristic_outputs.get("visual_intent_confidence", confidence.get("visual_intent", 0.0))
        )
        restraint_score = self._coerce_float(
            summary.get("restraint_score", heuristic_outputs.get("restraint_score", 0.5))
        )
        dialogue_substitution = self._coerce_float(
            summary.get(
                "dialogue_to_visual_substitution_opportunity",
                heuristic_outputs.get("dialogue_substitution_opportunity", 0.5),
            )
        )

        if visual_intent == "none_detected" and visual_intent_confidence >= 0.8:
            delta = self._cap_cinematic_delta(-0.015)
            total_delta += delta
            adjustments["missing_visual_intent_penalty"] = round(delta, 4)
            confidence_used["missing_visual_intent_penalty"] = round(visual_intent_confidence, 4)

        if (
            visual_intent not in {"", "none_detected"}
            and visual_intent_confidence >= 0.7
            and restraint_score >= 0.75
        ):
            delta = self._cap_cinematic_delta(0.015)
            total_delta += delta
            adjustments["restrained_visual_intent_support"] = round(delta, 4)
            confidence_used["restrained_visual_intent_support"] = round(
                min(visual_intent_confidence, restraint_score), 4
            )

        if dialogue_substitution >= 0.8 and self._has_mild_on_the_nose_dialogue(scene_data):
            generated_notes.append("Let the frame carry more of the meaning before the dialogue states it")
            confidence_used["dialogue_to_visual_substitution_note"] = round(dialogue_substitution, 4)

        total_delta = max(-self.MAX_CINEMATIC_SCORE_DELTA, min(self.MAX_CINEMATIC_SCORE_DELTA, total_delta))
        affected_signals = list(adjustments.keys())
        if generated_notes:
            affected_signals.append("dialogue_to_visual_substitution_note")

        return {
            "applied": bool(affected_signals),
            "affected_signals": affected_signals,
            "total_score_delta": round(total_delta, 4),
            "adjustments": adjustments,
            "confidence": confidence_used,
            "generated_notes": generated_notes,
        }

    def _calculate_taste_influence(
        self,
        scene_data: Dict[str, Any],
        taste_calibration: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply small bounded taste calibration with explicit debug provenance."""
        if not isinstance(taste_calibration, dict):
            return {
                "applied": False,
                "affected_dimensions": [],
                "total_score_delta": 0.0,
                "adjustments": {},
                "confidence": {},
                "signal_counts": {},
            }

        raw_adjustments = taste_calibration.get("dimension_adjustments") or {}
        raw_confidence = taste_calibration.get("dimension_confidence") or {}
        raw_signal_counts = taste_calibration.get("signal_counts") or {}
        if not isinstance(raw_adjustments, dict):
            raw_adjustments = {}
        if not isinstance(raw_confidence, dict):
            raw_confidence = {}
        if not isinstance(raw_signal_counts, dict):
            raw_signal_counts = {}

        total_delta = 0.0
        applied_adjustments: Dict[str, float] = {}
        confidence_used: Dict[str, float] = {}
        signal_counts_used: Dict[str, int] = {}

        subtext_adjustment = self._get_taste_adjustment(raw_adjustments, TasteDimension.SUBTEXT_LEVEL)
        if subtext_adjustment and self._has_mild_on_the_nose_dialogue(scene_data):
            delta = self._cap_taste_delta(-subtext_adjustment)
            total_delta += delta
            applied_adjustments[TasteDimension.SUBTEXT_LEVEL.value] = round(delta, 4)
            confidence_used[TasteDimension.SUBTEXT_LEVEL.value] = float(
                raw_confidence.get(TasteDimension.SUBTEXT_LEVEL.value, raw_confidence.get(TasteDimension.SUBTEXT_LEVEL, 0.0))
            )
            signal_counts_used[TasteDimension.SUBTEXT_LEVEL.value] = int(
                raw_signal_counts.get(TasteDimension.SUBTEXT_LEVEL.value, raw_signal_counts.get(TasteDimension.SUBTEXT_LEVEL, 0))
            )

        visual_adjustment = self._get_taste_adjustment(raw_adjustments, TasteDimension.VISUAL_RESTRAINT)
        if visual_adjustment and self._has_generic_visual_language(scene_data):
            delta = self._cap_taste_delta(-visual_adjustment)
            total_delta += delta
            applied_adjustments["generic_visual_penalty_bias"] = round(delta, 4)
            confidence_used["generic_visual_penalty_bias"] = float(
                raw_confidence.get(TasteDimension.VISUAL_RESTRAINT.value, raw_confidence.get(TasteDimension.VISUAL_RESTRAINT, 0.0))
            )
            signal_counts_used["generic_visual_penalty_bias"] = int(
                raw_signal_counts.get(TasteDimension.VISUAL_RESTRAINT.value, raw_signal_counts.get(TasteDimension.VISUAL_RESTRAINT, 0))
            )

        if visual_adjustment and self._has_restrained_visual_intent(scene_data):
            delta = self._cap_taste_delta(visual_adjustment)
            total_delta += delta
            applied_adjustments["restrained_visual_intent_bonus_bias"] = round(delta, 4)
            confidence_used["restrained_visual_intent_bonus_bias"] = float(
                raw_confidence.get(TasteDimension.VISUAL_RESTRAINT.value, raw_confidence.get(TasteDimension.VISUAL_RESTRAINT, 0.0))
            )
            signal_counts_used["restrained_visual_intent_bonus_bias"] = int(
                raw_signal_counts.get(TasteDimension.VISUAL_RESTRAINT.value, raw_signal_counts.get(TasteDimension.VISUAL_RESTRAINT, 0))
            )

        total_delta = max(-self.MAX_TASTE_SCORE_DELTA, min(self.MAX_TASTE_SCORE_DELTA, total_delta))
        return {
            "applied": abs(total_delta) > 0.0,
            "affected_dimensions": list(applied_adjustments.keys()),
            "total_score_delta": round(total_delta, 4),
            "adjustments": applied_adjustments,
            "confidence": confidence_used,
            "signal_counts": signal_counts_used,
        }

    def _get_taste_adjustment(
        self,
        raw_adjustments: Dict[Any, Any],
        dimension: TasteDimension,
    ) -> float:
        """Extract a numeric taste adjustment safely from enum or string keyed dicts."""
        value = raw_adjustments.get(dimension.value, raw_adjustments.get(dimension, 0.0))
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _cap_taste_delta(self, adjustment: float) -> float:
        """Keep each taste adjustment very small and bounded."""
        return max(-self.MAX_TASTE_DIMENSION_DELTA, min(self.MAX_TASTE_DIMENSION_DELTA, adjustment))

    def _cap_cinematic_delta(self, adjustment: float) -> float:
        """Keep each cinematic adjustment very small and bounded."""
        return max(-self.MAX_CINEMATIC_DIMENSION_DELTA, min(self.MAX_CINEMATIC_DIMENSION_DELTA, adjustment))

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        """Coerce numeric-like values safely for bounded influence math."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _has_mild_on_the_nose_dialogue(self, scene_data: Dict[str, Any]) -> bool:
        """Detect dialogue that is a little too explicit without triggering hard rejection."""
        dialogue = str(scene_data.get("dialogue", "")).lower()
        mild_markers = [
            "i keep pretending",
            "i'm trying my best",
            "i am trying my best",
            "what i'm saying is",
            "what i am saying is",
            "i guess this is the part",
            "i just need you to know",
        ]
        return any(marker in dialogue for marker in mild_markers)

    def _has_generic_visual_language(self, scene_data: Dict[str, Any]) -> bool:
        """Detect visually generic/default language that may merit a small taste penalty."""
        visual_desc = str(scene_data.get("visual_description", "")).lower()
        camera_work = str(scene_data.get("camera_work", "")).lower()
        coverage_text = f"{visual_desc} {camera_work}"
        default_framing_markers = ["two-shot", "medium shot", "wide shot"]
        generic_markers = ["simple", "plain", "basic", "standard", "generic"]
        has_default_framing = any(marker in coverage_text for marker in default_framing_markers)
        has_generic_language = any(marker in coverage_text for marker in generic_markers)
        return has_default_framing or has_generic_language

    def _has_restrained_visual_intent(self, scene_data: Dict[str, Any]) -> bool:
        """Detect restrained but clearly motivated visual language."""
        visual_desc = str(scene_data.get("visual_description", "")).lower()
        camera_work = str(scene_data.get("camera_work", "")).lower()
        coverage_text = f"{visual_desc} {camera_work}"
        restrained_intent_markers = [
            "reflection",
            "reframing",
            "reframe",
            "isolates",
            "without cutting",
            "static frame",
            "fractures",
        ]
        plain_visual_markers = ["simple", "plain", "basic"]
        restrained_markers_found = sum(
            1 for marker in restrained_intent_markers if marker in coverage_text
        )
        has_plain_language = any(marker in visual_desc for marker in plain_visual_markers)
        return restrained_markers_found >= 2 and not has_plain_language

    def _check_instant_rejection(
        self,
        scene_data: Dict[str, Any],
        spine: Dict[str, Any],
        structure: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Check instant rejection rules.
        
        Returns list of rejection reasons if any rule is triggered, empty list otherwise.
        """
        rejection_reasons = []

        # Rule 1: Over-explaining dialogue
        if self._is_over_explaining_dialogue(scene_data, spine):
            rejection_reasons.append("over_explaining_dialogue")

        # Rule 2: Tone violation against spine
        if self._is_tone_violation(scene_data, spine):
            rejection_reasons.append("tone_violation")

        # Rule 3: Generic visuals (2+ indicators)
        if self._is_generic_visuals(scene_data):
            rejection_reasons.append("generic_visuals")

        return rejection_reasons

    def _is_over_explaining_dialogue(self, scene_data: Dict[str, Any], spine: Dict[str, Any]) -> bool:
        """Check if dialogue is over-explaining (telling instead of showing)."""
        dialogue = scene_data.get("dialogue", "")
        actions = scene_data.get("actions", "")
        
        # Check for obvious exposition markers in dialogue
        exposition_markers = [
            "as you know",  # "As you know, I was born..."
            "let me explain",  # "Let me explain what happened"
            "i want you to know",  # "I want you to know that..."
            "the truth is",  # "The truth is, I never loved you"
            "as i said before",  # "As I said before, we have a problem"
            "to be honest",  # "To be honest, I never trusted you"
            "i think we should",  # "I think we should talk about..."
            "remember when",  # "Remember when we used to..."
        ]
        
        dialogue_lower = dialogue.lower()
        for marker in exposition_markers:
            if marker in dialogue_lower:
                return True
        
        # Check for on-the-nose dialogue (characters saying exactly what they feel)
        on_the_nose_patterns = [
            "i feel",  # "I feel like we should..."
            "i'm feeling",  # "I'm feeling really angry"
            "makes me feel",  # "That makes me feel sad"
            "i'm going to",  # "I'm going to tell you the truth"
        ]
        
        for pattern in on_the_nose_patterns:
            if pattern in dialogue_lower:
                return True
        
        # If actions are empty but dialogue is long, likely over-explaining
        if len(dialogue) > 200 and len(actions) < 50:
            return True
        
        return False

    def _is_tone_violation(self, scene_data: Dict[str, Any], spine: Dict[str, Any]) -> bool:
        """Check if scene tone violates spine constraints."""
        scene_tone = scene_data.get("tone", "").lower()
        spine_tone = spine.get("tone", "").lower()
        
        if not scene_tone or not spine_tone:
            return False
        
        # Get spine constraints
        constraints = spine.get("constraints", {})
        enforce_tone = constraints.get("enforce_tone_consistency", True)
        
        if not enforce_tone:
            return False
        
        # Check for incompatible tones
        # These are simplified examples - in production would be more nuanced
        incompatible_tones = {
            "dark": ["light", "comedic", "whimsical"],
            "light": ["dark", "tragic", "horror"],
            "comedic": ["tragic", "dark", "horror"],
            "dramatic": ["comedic", "whimsical"],
            "horror": ["comedic", "light", "whimsical"],
        }
        
        if scene_tone in incompatible_tones:
            if spine_tone in incompatible_tones[scene_tone]:
                return True
        
        # Direct tone mismatch
        if scene_tone != spine_tone:
            # Check if they're clearly incompatible
            if scene_tone in ["dark", "horror", "tragic"] and spine_tone in ["light", "comedic", "whimsical"]:
                return True
            if scene_tone in ["light", "comedic", "whimsical"] and spine_tone in ["dark", "horror", "tragic"]:
                return True
        
        return False

    def _is_generic_visuals(self, scene_data: Dict[str, Any]) -> bool:
        """Check if visuals are generic (2+ indicators required for rejection)."""
        visual_description = scene_data.get("visual_description", "").lower()
        camera_work = scene_data.get("camera_work", "").lower()
        lighting = scene_data.get("lighting", "").lower()
        
        indicators_found = []
        
        # Check each generic visual indicator
        # 1. Interchangeable (could be any scene)
        generic_scene_markers = [
            "generic", "standard", "typical", "ordinary", "unremarkable",
            "nothing special", "everyday", "normal", "average"
        ]
        for marker in generic_scene_markers:
            if marker in visual_description:
                indicators_found.append("interchangeable")
                break
        
        # 2. Emotionally neutral (no emotional visual intent)
        neutral_markers = [
            "neutral", "flat", "balanced", "no mood", "undefined",
            "standard lighting", "average", "nothing distinctive"
        ]
        for marker in neutral_markers:
            if marker in visual_description or marker in lighting:
                indicators_found.append("emotionally_neutral")
                break
        
        # 3. Default coverage (only basic shots)
        default_shots = ["medium shot", "wide shot", "establishing shot"]
        coverage_text = camera_work + " " + visual_description
        if all(shot in coverage_text for shot in default_shots[:2]):
            # Only if no interesting angles or movements
            interesting_markers = ["dolly", "crane", "tracking", "主观", "POV", "dramatic angle"]
            if not any(marker in coverage_text for marker in interesting_markers):
                indicators_found.append("default_coverage")
        
        # 4. Unmotivated style (style doesn't serve story)
        unmotivated_markers = [
            "just because", "for no reason", "arbitrary", "random",
            "style choice", "looked cool", "visually interesting only"
        ]
        for marker in unmotivated_markers:
            if marker in visual_description:
                indicators_found.append("unmotivated_style")
                break
        
        # Need 2+ indicators for rejection
        return len(indicators_found) >= 2

    def _calculate_scores(
        self,
        scene_data: Dict[str, Any],
        spine: Dict[str, Any],
        structure: Optional[Dict[str, Any]],
        memory: Optional[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Calculate scores for each pillar (0.0 to 1.0)."""
        return {
            "intent_alignment": self._score_intent_alignment(scene_data, spine),
            "emotional_consistency": self._score_emotional_consistency(scene_data, spine, structure),
            "visual_coherence": self._score_visual_coherence(scene_data, spine),
            "continuity": self._score_continuity(scene_data, spine, memory),
        }

    def _score_intent_alignment(self, scene_data: Dict[str, Any], spine: Dict[str, Any]) -> float:
        """Score how well scene aligns with creative intent."""
        scene_intent = scene_data.get("intent", "").lower()
        spine_intent = spine.get("story_thesis", "").lower()
        spine_constraints = spine.get("constraints", {})
        
        if not scene_intent:
            return 0.5  # Neutral if no intent specified
        
        # Check if scene intent aligns with spine thesis
        alignment_score = 0.7 # Base score - higher for scenes with intent
    
        # Strong positive indicators
        positive_markers = [
            "advances", "supports", "reinforces", "builds", "develops",
            "explores", "reveals", "deepens", "dramatizes", "illustrates"
        ]
        for marker in positive_markers:
            if marker in scene_intent:
                alignment_score += 0.15
                break
        
        # Check director constraints
        if spine_constraints.get("prefer_subtext_over_exposition"):
            # Penalize obvious intent statements
            obvious_intent_markers = ["the point is", "this shows", "means", "represents"]
            for marker in obvious_intent_markers:
                if marker in scene_intent:
                    alignment_score -= 0.2
                    break
        
        return max(0.0, min(1.0, alignment_score))

    def _score_emotional_consistency(
        self,
        scene_data: Dict[str, Any],
        spine: Dict[str, Any],
        structure: Optional[Dict[str, Any]],
    ) -> float:
        """Score emotional consistency with spine and structure."""
        scene_emotion = scene_data.get("emotional_tone", "").lower()
        spine_emotion = spine.get("emotional_contract", "").lower()
        
        if not scene_emotion:
            return 0.5  # Neutral if no emotion specified
        
        # Base score
        score = 0.5
        
        # Check if scene emotion matches expected act emotion
        if structure and structure.get("current_act"):
            act_type = structure["current_act"].get("act_type", "").lower()
            
            # Expected emotions per act type
            act_emotions = {
                "setup": ["curiosity", "anticipation", "introduction", "establishing"],
                "confrontation": ["tension", "conflict", "urgency", "rising"],
                "resolution": ["catharsis", "release", "conclusion", "settling"],
            }
            
            if act_type in act_emotions:
                if any(emo in scene_emotion for emo in act_emotions[act_type]):
                    score += 0.2
        
        # Check spine constraints
        spine_constraints = spine.get("constraints", {})
        if spine_constraints.get("enforce_tone_consistency"):
            if spine_emotion and scene_emotion:
                # Simple emotional consistency check
                if scene_emotion == spine_emotion:
                    score += 0.2
                elif scene_emotion in spine_emotion or spine_emotion in scene_emotion:
                    score += 0.1
                else:
                    # Emotionally inconsistent
                    score -= 0.2
        
        return max(0.0, min(1.0, score))

    def _score_visual_coherence(self, scene_data: Dict[str, Any], spine: Dict[str, Any]) -> float:
        """Score visual coherence with spine constraints."""
        visual_desc = scene_data.get("visual_description", "").lower()
        camera_work = scene_data.get("camera_work", "").lower()
        spine_style = spine.get("visual_style", "").lower()
        coverage_text = f"{visual_desc} {camera_work}"

        score = 0.7 # Base score - higher for scenes with visual description
    
        # Check for visual intent
        if not visual_desc:
            return 0.3 # Penalize missing visual description
    
        # Check if visuals are motivated (serve the story)
        motivated_markers = [
            "reveals", "emphasizes", "highlights", "underscores",
            "reflects", "contrasts", "mirrors", "foreshadows", "dramatizes"
        ]
        for marker in motivated_markers:
            if marker in visual_desc:
                score += 0.15
                break
        
        # Check spine constraints
        spine_constraints = spine.get("constraints", {})
        if spine_constraints.get("require_visual_intent"):
            # Penalize generic or unmotivated visuals
            generic_markers = ["standard", "typical", "generic", "unremarkable"]
            for marker in generic_markers:
                if marker in visual_desc:
                    score -= 0.2
                    break

            # Mildly penalize default framing language in scenes that otherwise
            # avoid instant rejection but still lack enough visual specificity.
            default_framing_markers = ["two-shot", "medium shot", "wide shot"]
            plain_visual_markers = ["simple", "plain", "basic"]
            has_default_framing = any(marker in coverage_text for marker in default_framing_markers)
            has_plain_language = any(marker in visual_desc for marker in plain_visual_markers)
            if has_default_framing and has_plain_language:
                score -= 0.25

            # Restrained scenes can still be visually intentional when the
            # framing language shows deliberate compositional control.
            restrained_intent_markers = [
                "reflection",
                "reframing",
                "reframe",
                "isolates",
                "without cutting",
                "static frame",
                "fractures",
            ]
            restrained_markers_found = sum(
                1 for marker in restrained_intent_markers if marker in coverage_text
            )
            if restrained_markers_found >= 2 and not has_plain_language:
                score += 0.30

        # Check style alignment
        if spine_style and visual_desc:
            if spine_style in visual_desc:
                score += 0.15
        
        return max(0.0, min(1.0, score))

    def _score_continuity(
        self,
        scene_data: Dict[str, Any],
        spine: Dict[str, Any],
        memory: Optional[Dict[str, Any]],
    ) -> float:
        """Score continuity with previous scenes and established patterns."""
        scene_id = scene_data.get("scene_id", "")
        character_appearances = scene_data.get("character_appearances", [])
        
        score = 0.7 # Base score - higher for scenes with character info
    
        # Check character continuity
        if memory and memory.get("characters"):
            characters_in_memory = set(memory["characters"].keys())
            characters_in_scene = set(character_appearances) if character_appearances else set()
    
            # If characters appear that weren't established, penalize
            if characters_in_scene and not characters_in_memory.intersection(characters_in_scene):
                score -= 0.2
            # If established characters appear properly, reward
            elif characters_in_scene and characters_in_memory.intersection(characters_in_scene):
                score += 0.1
    
        # Check scene flow (scene_id suggests proper sequencing)
        if scene_id:
            # Simple continuity check - scene should have proper ID format
            if "_" in scene_id or "scene" in scene_id.lower():
                score += 0.1
        
        # Check for continuity errors in the scene data itself
        continuity_notes = scene_data.get("continuity_notes", [])
        if continuity_notes:
            # Penalize if there are known continuity issues
            score -= len(continuity_notes) * 0.1
        
        return max(0.0, min(1.0, score))

    def _generate_revision_notes(
        self,
        scene_data: Dict[str, Any],
        spine: Dict[str, Any],
        scores: Dict[str, float],
    ) -> List[str]:
        """Generate specific revision notes based on low scores."""
        notes = []
        
        if scores["intent_alignment"] < 0.7:
            notes.append("Strengthen scene intent alignment with story thesis")
        
        if scores["emotional_consistency"] < 0.7:
            notes.append("Improve emotional consistency with act and spine")
        
        if scores["visual_coherence"] < 0.7:
            notes.append("Add visual intent - visuals should serve the story")
        
        if scores["continuity"] < 0.7:
            notes.append("Review continuity with established characters and scenes")
        
        return notes

    def _format_rejection_notes(self, rejection_reasons: List[str]) -> str:
        """Format rejection reasons into a readable note."""
        formatted = []
        for reason in rejection_reasons:
            if reason == "over_explaining_dialogue":
                formatted.append("Dialogue over-explains - use subtext instead of exposition")
            elif reason == "tone_violation":
                formatted.append("Scene tone violates spine constraints")
            elif reason == "generic_visuals":
                formatted.append("Visuals are generic and unmotivated")
            else:
                formatted.append(f"Rejection reason: {reason}")
        
        return "; ".join(formatted)


# Global instance
director_evaluator = DirectorEvaluator()


def build_agent_disagreements(
    scene_data: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]] = None,
    scene_metrics: Optional[Dict[str, Any]] = None,
    visual_language: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build deterministic multi-agent disagreements for creative tension surfacing."""
    if not isinstance(scene_data, dict):
        scene_data = {}
    if not isinstance(memory_context, dict):
        memory_context = {}
    if not isinstance(scene_metrics, dict):
        scene_metrics = {}
    if not isinstance(visual_language, dict):
        visual_language = {}

    scene_text = str(scene_data.get("text") or scene_data.get("description") or "").lower()
    heading_text = str(scene_data.get("heading") or "").lower()
    combined_text = f"{heading_text} {scene_text}".strip()

    flow_score_raw = scene_metrics.get("flow_score")
    flow_score = float(flow_score_raw) if isinstance(flow_score_raw, (int, float)) else None
    coherence_score_raw = scene_metrics.get("coherence_score")
    coherence_score = float(coherence_score_raw) if isinstance(coherence_score_raw, (int, float)) else None
    continuity_score_raw = scene_metrics.get("continuity_score")
    continuity_score = float(continuity_score_raw) if isinstance(continuity_score_raw, (int, float)) else None
    flow_pattern = str(scene_metrics.get("flow_pattern") or "").strip().lower()

    memory_patterns = [
        str(pattern).strip().lower()
        for pattern in (memory_context.get("pacing_patterns") or [])
        if isinstance(pattern, str) and pattern.strip()
    ]
    visual_patterns = [
        str(pattern).strip().lower()
        for pattern in (memory_context.get("visual_patterns") or [])
        if isinstance(pattern, str) and pattern.strip()
    ]

    has_memory_conflict = (
        any("slow burn" in pattern for pattern in memory_patterns)
        and any(token in combined_text for token in ["rushes", "rapid", "chaos", "sprints"])
    )
    has_visual_conflict = (
        any("static framing" in pattern or "locked frame" in pattern for pattern in visual_patterns)
        and any(token in combined_text for token in ["handheld", "whip pan", "frenetic", "shaky"])
    )
    has_narrative_conflict = (
        (flow_score is not None and flow_score < 0.64)
        or flow_pattern in {"flat", "broken"}
    )
    has_pacing_conflict = (
        (coherence_score is not None and coherence_score < 0.7)
        or (continuity_score is not None and continuity_score < 0.75)
        or any(token in combined_text for token in ["sudden cut", "abrupt jump", "hard break"])
    )

    disagreements: List[Dict[str, Any]] = []
    if has_narrative_conflict:
        disagreements.append(
            {
                "agent": "director",
                "severity": "high" if (flow_score is not None and flow_score < 0.55) else "medium",
                "issue": "Emotional beat is not landing cleanly",
                "recommendation": "Refocus the central emotional turn and hold one tension beat longer",
                "conflict_with": "narrative_flow",
            }
        )
    if has_pacing_conflict:
        disagreements.append(
            {
                "agent": "editor",
                "severity": "high" if (coherence_score is not None and coherence_score < 0.6) else "medium",
                "issue": "Pacing drop in mid-scene",
                "recommendation": "Trim transitional dialogue or add a sharper escalation beat",
                "conflict_with": "narrative_flow",
            }
        )
    if has_visual_conflict:
        disagreements.append(
            {
                "agent": "cinematographer",
                "severity": "medium",
                "issue": "Visual language drift from established framing style",
                "recommendation": "Re-anchor camera grammar to the established visual bible",
                "conflict_with": "visual_language",
            }
        )
    if has_memory_conflict:
        disagreements.append(
            {
                "agent": "story_analyst",
                "severity": "low",
                "issue": "Scene pacing contradicts remembered pattern direction",
                "recommendation": "Either justify the break as intentional or re-align to memory rhythm",
                "conflict_with": "memory_pattern",
            }
        )

    return disagreements
