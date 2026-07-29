"""
Adaptive Behavior System - Weighted Memory Implementation

This module implements adaptive behavior with weighted memory for the autonomous studio.

Key Features:
1. Weighted Pattern Memory - patterns ranked by weight_score, not recency
2. Context Tags - patterns tagged with scene type, emotion, genre
3. Context Relevance - patterns boosted based on alignment with current scene intent
4. Decay Mechanism - unused patterns lose weight over time
5. Preference Hierarchy - system develops priority ordering for patterns

Weight Calculation:
weight_score = (success_rate * usage_count) * context_relevance * decay_factor

Components:
- WeightedPattern: Pattern with full metadata and weight calculations
- SceneIntent: Context for scene matching (emotion, genre, type)
- AdaptationEngine: Central coordinator with weighted memory
"""

import json
import logging
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from app.services.scene_evolution import evolution_tracker, SceneContext
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("studio-adaptation")

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SceneIntent:
    """
    Context for scene matching - used to calculate relevance of patterns.

    Attributes:
    scene_type: INT, EXT, etc.
    emotion: tense, dramatic, mysterious, action, etc.
    genre: noir, horror, action, romance, etc.
    visual_goal: dark, bright, moody, dynamic, etc.
    emotional_goal: tension, joy, sadness, suspense, etc.
    time_of_day: day, night, dawn, dusk, etc.
    """
    scene_type: str = ""
    emotion: str = ""
    genre: str = ""
    visual_goal: str = ""
    emotional_goal: str = ""
    time_of_day: str = ""

    def to_tags(self) -> List[str]:
        """Convert to list of tag strings for matching"""
        tags = []
        if self.scene_type:
            tags.append(f"type:{self.scene_type.lower()}")
        if self.emotion:
            tags.append(f"emotion:{self.emotion.lower()}")
        if self.genre:
            tags.append(f"genre:{self.genre.lower()}")
        if self.visual_goal:
            tags.append(f"visual:{self.visual_goal.lower()}")
        if self.emotional_goal:
            tags.append(f"emotional:{self.emotional_goal.lower()}")
        if self.time_of_day:
            tags.append(f"time:{self.time_of_day.lower()}")
        return tags

    @classmethod
    def from_dict(cls, data: Dict) -> 'SceneIntent':
        return cls(
            scene_type=data.get("scene_type", ""),
            emotion=data.get("emotion", ""),
            genre=data.get("genre", ""),
            visual_goal=data.get("visual_goal", ""),
            emotional_goal=data.get("emotional_goal", ""),
            time_of_day=data.get("time_of_day", "")
        )


@dataclass
class WeightedPattern:
    """
    Pattern with weighted scoring based on:
    - Success rate (how often this pattern works)
    - Usage count (how many times it's been tried)
    - Context relevance (how well it matches current scene)
    - Decay factor (loses weight if unused)

    Weight Formula:
    weight_score = (success_rate * usage_count * context_relevance) * decay_factor
    """
    pattern_id: str
    pattern_type: str # camera, lighting, prompt, etc.
    pattern_value: str # wide, low_key, film_noir, etc.

    # Feedback data
    success_count: int = 0 # Times approved
    failure_count: int = 0 # Times rejected
    total_count: int = 0 # Total feedback count

    # Calculated fields
    success_rate: float = 0.5 # success_count / total_count
    weight_score: float = 0.0 # Final weighted score

    # Context matching
    context_tags: List[str] = field(default_factory=list) # Scene tags this pattern worked for
    genre_tags: List[str] = field(default_factory=list) # Genre associations

    # Temporal tracking
    first_used: Optional[str] = None
    last_used: Optional[str] = None
    last_successful: Optional[str] = None

    # Hierarchy
    priority_rank: int = 0 # Rank within pattern_type
    is_established: bool = False # High weight, stable

    def calculate_success_rate(self) -> float:
        """Calculate success rate from counts"""
        if self.total_count == 0:
            return 0.5
        return self.success_count / self.total_count

    def calculate_weight_score(
        self,
        context_relevance: float = 1.0,
        decay_factor: float = 1.0
    ) -> float:
        """
        Calculate weighted score.

        Formula: weight = (success_rate * usage_count * context_relevance) * decay

        Context relevance: 0.0 to 2.0 (1.0 = neutral, >1.0 = boost)
        Decay factor: 0.0 to 1.0 (reduces over time if unused)
        """
        sr = self.calculate_success_rate()
        usage = min(self.total_count, 50) # Cap at 50 to prevent dominance

        # Base weight from success rate and usage
        base_weight = sr * usage

        # Apply context relevance boost
        weighted = base_weight * context_relevance

        # Apply decay
        self.weight_score = weighted * decay_factor

        return self.weight_score

    def calculate_decay(self, hours_until_stale: int = 168) -> float:
        """
        Calculate decay factor based on time since last use.

        Decay curve: Starts at 1.0, decreases over time.
        After hours_until_stale (default 7 days), drops to 0.5
        """
        if not self.last_used:
            return 1.0

        try:
            last = datetime.fromisoformat(self.last_used)
            age_hours = (datetime.now() - last).total_seconds() / 3600

            # Linear decay: 1.0 -> 0.5 over hours_until_stale
            decay = max(0.5, 1.0 - (age_hours / hours_until_stale * 0.5))
            return decay
        except Exception:
            return 1.0

    def add_context_tag(self, tag: str):
        """Add a context tag where this pattern succeeded"""
        if tag not in self.context_tags:
            self.context_tags.append(tag)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AdaptiveDecision:
    """Log entry for an adaptive decision"""
    timestamp: str
    agent_role: str
    decision_type: str
    decision: str
    memory_used: Dict[str, Any] # Now includes weight_score, context_relevance
    reason: str
    weight_applied: float = 0.0
    context_relevance: float = 0.0
    based_on_feedback: bool = False
    feedback_id: Optional[str] = None
    contradicted: bool = False
    user_override: bool = False


# ============================================================================
# ADAPTATION ENGINE
# ============================================================================

class AdaptationEngine:
    """
    Central engine for adaptive behavior with weighted memory.

    Key improvements over flat feedback:
    1. Patterns ranked by weight_score (not recency)
    2. Context tags enable scene-specific matching
    3. Decay prevents stale patterns from dominating
    4. Priority hierarchy shows pattern preferences
    """

    # =========================================================================
    # EVOLUTION BOOST CONSTANTS (class-level for weighted scoring)
    # =========================================================================
    # Weights for weighted scoring: must sum to 0.75 (MAX_BOOST)
    _BOOST_WEIGHT_FREQUENCY = 0.10 # match_count contribution
    _BOOST_WEIGHT_QUALITY = 0.25 # avg_quality contribution
    _BOOST_WEIGHT_ALIGNMENT = 0.25 # avg_alignment contribution
    _BOOST_WEIGHT_RECENCY = 0.15 # recency_sum contribution
    _MAX_BOOST = 0.75 # maximum boost above 1.0
    # Penalty weights for negative learning
    _PENALTY_WEIGHT_QUALITY = 0.20 # (1.0 - avg_quality) contribution
    _PENALTY_WEIGHT_ALIGNMENT = 0.20 # (1.0 - avg_alignment) contribution
    _PENALTY_WEIGHT_RECENCY = 0.10 # negative_recency_sum contribution
    _MIN_MULTIPLIER = 0.9 # floor for multiplier

    # =========================================================================
    # CROSS-SCENE PATTERN REUSE CONSTANTS
    # =========================================================================
    _ENABLE_CROSS_SCENE_REUSE = False # Feature flag for live mode
    _ENABLE_CROSS_SCENE_SHADOW_MODE = True # Shadow mode (log but don't apply)
    _CROSS_SCENE_MIN_SIMILARITY = 0.3 # Minimum similarity threshold
    _CROSS_SCENE_MIN_SIMILAR_SCENES = 2 # Minimum similar scenes required
    _CROSS_SCENE_AVG_SIMILARITY_THRESHOLD = 0.45 # Minimum avg similarity
    _CROSS_SCENE_BLEND_RATIO = 0.15 # 15% cross-scene, 85% same-scene
    _CROSS_SCENE_BOOST_FLOOR = 0.95 # Clamp cross-scene boost to [0.95, 1.05]
    _CROSS_SCENE_BOOST_CEILING = 1.05
    _CROSS_SCENE_ONLY_FLOOR = 0.92 # When no same-scene data, tiny nudge
    _CROSS_SCENE_ONLY_CEILING = 1.08
    _MAX_SIMILAR_SCENES = 20 # Maximum similar scenes to consider

    def __init__(self):
        # Pattern storage: project_id -> pattern_type -> pattern_id -> WeightedPattern
        self._patterns: Dict[str, Dict[str, Dict[str, WeightedPattern]]] = defaultdict(
            lambda: defaultdict(dict)
        )

        # Decision log for traceability
        self._decision_log: List[AdaptiveDecision] = []

        # Project style boundaries
        self._style_boundaries: Dict[str, Dict[str, Any]] = {}

        # User overrides (always take priority)
        self._user_overrides: Dict[str, Dict[str, Any]] = {}

        # Project memory references
        self._project_memories: Dict[str, Dict] = {}

        # Project creative intent (for context matching)
        self._project_intents: Dict[str, SceneIntent] = {}

        # Cross-scene similarity cache: (scene_id, pattern_type, pattern_value) -> similar_scenes
        self._similar_scenes_cache: Dict[str, List[Tuple[str, float]]] = {}

        # Configuration
        self._decay_hours = 168 # 7 days until significant decay
        self._established_threshold = 0.7 # Weight score for "established" status
        self._boost_factor = 1.5 # Multiplier for perfect context match

        logger.info("Weighted AdaptationEngine initialized")

    # =========================================================================
    # SCENE INTENT MANAGEMENT
    # =========================================================================

    def set_project_intent(self, project_id: str, intent: SceneIntent):
        """Set the creative intent for a project (used for context matching)"""
        self._project_intents[project_id] = intent
        logger.info(f"Scene intent set for {project_id}: {intent.to_tags()}")

    def get_project_intent(self, project_id: str) -> SceneIntent:
        """Get creative intent for a project"""
        return self._project_intents.get(project_id, SceneIntent())

    def calculate_context_relevance(
        self,
        pattern_tags: List[str],
        scene_intent: SceneIntent
    ) -> float:
        """
        Calculate how relevant a pattern is to the current scene context.

        Returns multiplier from 0.5 to 2.0:
        - 0.5 = no relevance (penalized)
        - 1.0 = neutral
        - 1.5+ = strong match (boosted)

        Based on tag overlap between pattern and scene intent.
        """
        if not pattern_tags or not scene_intent.to_tags():
            return 1.0

        pattern_set = set(tag.lower() for tag in pattern_tags)
        intent_set = set(scene_intent.to_tags())

        overlap = pattern_set & intent_set
        union = pattern_set | intent_set

        if not union:
            return 1.0

        # Jaccard similarity
        jaccard = len(overlap) / len(union)

        # Map to relevance score (0.5 to 2.0)
        # Jaccard 0 -> 0.5, Jaccard 0.5 -> 1.0, Jaccard 1.0 -> 2.0
        relevance = 0.5 + (jaccard * 1.5)

        return relevance

    def set_style_boundaries(self, project_id: str, boundaries: Dict[str, Any]):
        """Set style boundaries for a project (hard constraints)"""
        self._style_boundaries[project_id] = boundaries
        logger.info(f"Style boundaries set for {project_id}: {list(boundaries.keys())}")

    def set_user_override(self, project_id: str, key: str, value: Any):
        """Set a user override - takes absolute priority over adaptive system"""
        if project_id not in self._user_overrides:
            self._user_overrides[project_id] = {}
        self._user_overrides[project_id][key] = value
        logger.info(f"User override set for {project_id}/{key}: {value}")

    def check_user_override(self, project_id: str, key: str) -> Tuple[bool, Any]:
        """Check if user has overridden a decision"""
        if project_id in self._user_overrides:
            if key in self._user_overrides[project_id]:
                return True, self._user_overrides[project_id][key]
        return False, None

    def is_within_boundaries(self, project_id: str, pattern_type: str, value: str) -> bool:
        """Check if a pattern value is within project style boundaries"""
        if project_id not in self._style_boundaries:
            return True

        boundaries = self._style_boundaries[project_id]
        if pattern_type not in boundaries:
            return True

        allowed = boundaries[pattern_type]
        if isinstance(allowed, list):
            return value in allowed
        return True

    # =========================================================================
    # FEEDBACK PROCESSING
    # =========================================================================

    def record_feedback(
        self,
        project_id: str,
        pattern_type: str,
        pattern_value: str,
        approved: bool,
        scene_id: Optional[str] = None,
        scene_intent: Optional[SceneIntent] = None
    ) -> str:
        """
        Record feedback for a pattern decision.

        Returns feedback_id for tracking.
        """
        feedback_id = f"fb-{hashlib.md5(f'{project_id}{pattern_type}{pattern_value}{datetime.now().isoformat()}'.encode()).hexdigest()[:12]}"

        # Get or create pattern
        pattern = self._get_or_create_pattern(project_id, pattern_type, pattern_value)

        # Update counts
        pattern.total_count += 1
        if approved:
            pattern.success_count += 1
            pattern.last_successful = datetime.now().isoformat()
            if scene_id:
                pattern.add_context_tag(f"scene:{scene_id}")
        else:
            pattern.failure_count += 1

        # Update temporal data
        pattern.last_used = datetime.now().isoformat()

        # Recalculate success rate
        pattern.success_rate = pattern.calculate_success_rate()

        # Recalculate weight with context relevance
        intent = scene_intent or self.get_project_intent(project_id)
        relevance = self.calculate_context_relevance(pattern.context_tags, intent)
        decay = pattern.calculate_decay(self._decay_hours)
        pattern.calculate_weight_score(context_relevance=relevance, decay_factor=decay)

        # Update hierarchy
        self._update_pattern_hierarchy(project_id, pattern_type)

        # Log
        logger.info(
            f"Feedback: {feedback_id} | {pattern_type}:{pattern_value} | "
            f"approved={approved} | weight={pattern.weight_score:.3f} | "
            f"success_rate={pattern.success_rate:.1%}"
        )

        return feedback_id

    def _generate_pattern_id(self, pattern_type: str, pattern_value: str) -> str:
        """Generate unique pattern ID"""
        raw = f"{pattern_type}:{pattern_value}"
        return f"pt-{hashlib.md5(raw.encode()).hexdigest()[:12]}"

    def _get_genre_tags(self, project_id: str) -> List[str]:
        """Get genre tags from project intent"""
        intent = self._project_intents.get(project_id)
        if intent and intent.genre:
            return [f"genre:{intent.genre.lower()}"]
        return []

    def _update_pattern_hierarchy(self, project_id: str, pattern_type: str):
        """
        Update priority ranking within pattern type.
        Patterns ranked by weight_score descending.
        """
        patterns = self._patterns.get(project_id, {}).get(pattern_type, {})

        if not patterns:
            return

        # Sort by weight score
        sorted_patterns = sorted(
            patterns.values(),
            key=lambda p: p.weight_score,
            reverse=True
        )

        # Assign ranks
        for rank, pattern in enumerate(sorted_patterns, 1):
            pattern.priority_rank = rank
            pattern.is_established = pattern.weight_score >= self._established_threshold

        logger.debug(
            f"Hierarchy updated for {project_id}/{pattern_type}: "
            f"{len(sorted_patterns)} patterns ranked"
        )

    # =========================================================================
    # WEIGHTED PATTERN RETRIEVAL
    # =========================================================================

    def _get_evolution_boost(
        self,
        scene_id: Optional[str],
        pattern_type: str,
        pattern_value: str,
        similarity_context: Optional['SceneContext'] = None
    ) -> float:
        """
        Get a small boost multiplier based on scene evolution data.

        Returns a multiplier between 0.9 and 1.1 based on:
        - If the pattern was used in iterations with high quality scores
        - If the pattern was used in iterations with high intent alignment

        When similarity_context is provided, also considers cross-scene patterns
        from similar scenes for context-aware pattern reuse.

        Returns 1.0 if no evolution data exists (no change to weight).

        Safe against:
        - Missing or None evolution data
        - Iteration data missing expected fields (uses `or 0` defaults)
        - Pattern entries missing pattern_type or pattern_value
        """
        if not scene_id:
            return 1.0

        try:
            # Calculate same-scene boost (existing logic)
            same_scene_boost = self._calculate_same_scene_boost(
                scene_id, pattern_type, pattern_value
            )

            # If no similarity context, return same-scene only (backward compatible)
            if not similarity_context or similarity_context.is_empty():
                logger.debug(
                    f"Evolution boost for {pattern_type}:{pattern_value} in scene '{scene_id}': "
                    f"same_scene={same_scene_boost:.3f} (no similarity context)"
                )
                return same_scene_boost

            # Calculate cross-scene boost if enabled
            cross_scene_boost = self._calculate_cross_scene_boost(
                scene_id, pattern_type, pattern_value, similarity_context
            )

            # Blend: 85% same-scene, 15% cross-scene (conservative)
            final_boost = (
                (1.0 - self._CROSS_SCENE_BLEND_RATIO) * same_scene_boost +
                self._CROSS_SCENE_BLEND_RATIO * cross_scene_boost
            )

            # Clamp to safe range [0.95, 1.05] in live mode
            if self._ENABLE_CROSS_SCENE_REUSE:
                final_boost = max(
                    self._CROSS_SCENE_BOOST_FLOOR,
                    min(self._CROSS_SCENE_BOOST_CEILING, final_boost)
                )

            logger.debug(
                f"Evolution boost for {pattern_type}:{pattern_value} in scene '{scene_id}': "
                f"same_scene={same_scene_boost:.3f}, cross_scene={cross_scene_boost:.3f}, "
                f"final={final_boost:.3f}"
            )

            return final_boost

        except Exception as e:
            logger.warning(f"Failed to get evolution boost: {e}")
            return 1.0

    def _calculate_same_scene_boost(
        self,
        scene_id: str,
        pattern_type: str,
        pattern_value: str
    ) -> float:
        """
        Calculate boost based on same-scene pattern history.

        This is the original evolution boost logic extracted for reuse
        in the blended cross-scene calculation.
        """
        evolution_data = evolution_tracker.get_evolution_data(scene_id)
        if not evolution_data:
            return 1.0

        # Find iterations where this pattern was used
        # Match on both pattern_type AND pattern_value for precision
        pattern_uses = []
        for iteration in evolution_data:
            # Safely extract iteration metrics with defaults (handle None)
            quality = iteration.get("quality_score", 0) or 0
            alignment = iteration.get("intent_alignment_score", 0) or 0

            patterns_used = iteration.get("patterns_used") or []
            if not isinstance(patterns_used, list):
                continue

            for p in patterns_used:
                if not isinstance(p, dict):
                    continue
                # Support both old keys (type/value) and new keys (pattern_type/pattern_value)
                # Since scene_evolution now normalizes to pattern_type/pattern_value,
                # this handles both normalized data and legacy records
                p_type = p.get("pattern_type") or p.get("type")
                p_value = p.get("pattern_value") or p.get("value")
                if p_value == pattern_value and p_type == pattern_type:
                    pattern_uses.append({
                        "quality": quality,
                        "alignment": alignment
                    })

        if not pattern_uses:
            return 1.0

        # Split matches into positive (quality >= 0.75 AND alignment >= 0.75)
        # and negative (everything else)
        positive_matches = []
        negative_matches = []
        for i, u in enumerate(pattern_uses):
            if u["quality"] >= 0.75 and u["alignment"] >= 0.75:
                positive_matches.append({"quality": u["quality"], "alignment": u["alignment"], "age_index": i})
            else:
                negative_matches.append({"quality": u["quality"], "alignment": u["alignment"], "age_index": i})

        # Calculate positive score components
        positive_count = len(positive_matches)
        positive_recency_sum = sum(1.0 / (1.0 + m["age_index"]) for m in positive_matches) if positive_matches else 0.0
        avg_positive_quality = sum(m["quality"] for m in positive_matches) / positive_count if positive_count > 0 else 0.0
        avg_positive_alignment = sum(m["alignment"] for m in positive_matches) / positive_count if positive_count > 0 else 0.0

        # Calculate negative score components
        negative_count = len(negative_matches)
        negative_recency_sum = sum(1.0 / (1.0 + m["age_index"]) for m in negative_matches) if negative_matches else 0.0
        avg_negative_quality = sum(m["quality"] for m in negative_matches) / negative_count if negative_count > 0 else 0.0
        avg_negative_alignment = sum(m["alignment"] for m in negative_matches) / negative_count if negative_count > 0 else 0.0

        # Positive score: rewards good performance
        positive_score = (
            self._BOOST_WEIGHT_FREQUENCY * positive_count +
            self._BOOST_WEIGHT_QUALITY * avg_positive_quality +
            self._BOOST_WEIGHT_ALIGNMENT * avg_positive_alignment +
            self._BOOST_WEIGHT_RECENCY * positive_recency_sum
        )

        # Penalty score: penalizes poor performance
        # Higher penalty when quality/alignment are low
        penalty_score = (
            self._PENALTY_WEIGHT_QUALITY * (1.0 - avg_negative_quality) +
            self._PENALTY_WEIGHT_ALIGNMENT * (1.0 - avg_negative_alignment) +
            self._PENALTY_WEIGHT_RECENCY * negative_recency_sum
        )

        # Net score and final multiplier
        net_score = positive_score - penalty_score
        multiplier = 1.0 + net_score

        # Clamp to valid range
        multiplier = max(self._MIN_MULTIPLIER, min(1.0 + self._MAX_BOOST, multiplier))

        logger.debug(
            f"Same-scene boost for {pattern_type}:{pattern_value} in scene '{scene_id}': "
            f"pos_count={positive_count}, neg_count={negative_count}, "
            f"pos_score={positive_score:.3f}, penalty={penalty_score:.3f}, "
            f"net={net_score:.3f}, multiplier={multiplier:.3f}"
        )

        return multiplier

    def _calculate_cross_scene_boost(
        self,
        scene_id: str,
        pattern_type: str,
        pattern_value: str,
        similarity_context: 'SceneContext'
    ) -> float:
        """
        Calculate boost based on cross-scene pattern reuse from similar scenes.

        In shadow mode: computes and logs cross-scene boost but doesn't apply it.
        In live mode: applies cross-scene boost only if:
        - At least 2 similar scenes exist
        - Average similarity >= 0.45

        When same-scene data is missing, allows tiny bounded nudge [0.92, 1.08].
        """
        # Check if feature is enabled
        if not self._ENABLE_CROSS_SCENE_REUSE and not self._ENABLE_CROSS_SCENE_SHADOW_MODE:
            logger.debug(
                f"Cross-scene reuse disabled for {pattern_type}:{pattern_value}"
            )
            return 1.0

        # Get similar scenes from cache or compute
        cache_key = f"{scene_id}:{pattern_type}:{pattern_value}"
        if cache_key in self._similar_scenes_cache:
            similar_scenes = self._similar_scenes_cache[cache_key]
        else:
            # Get all scene contexts from evolution tracker
            # This would need to be implemented based on how scenes store their context
            # For now, we'll use a placeholder that can be enhanced later
            similar_scenes = self._find_similar_scenes_for_context(
                scene_id, similarity_context
            )
            self._similar_scenes_cache[cache_key] = similar_scenes

        # Check minimum similar scenes threshold
        if len(similar_scenes) < self._CROSS_SCENE_MIN_SIMILAR_SCENES:
            logger.debug(
                f"Cross-scene boost skipped for {pattern_type}:{pattern_value}: "
                f"only {len(similar_scenes)} similar scenes (need {self._CROSS_SCENE_MIN_SIMILAR_SCENES})"
            )
            return 1.0

        # Calculate average similarity
        avg_similarity = sum(sim for _, sim in similar_scenes) / len(similar_scenes)

        # Check average similarity threshold
        if avg_similarity < self._CROSS_SCENE_AVG_SIMILARITY_THRESHOLD:
            logger.debug(
                f"Cross-scene boost skipped for {pattern_type}:{pattern_value}: "
                f"avg_similarity={avg_similarity:.3f} < {self._CROSS_SCENE_AVG_SIMILARITY_THRESHOLD}"
            )
            return 1.0

        # Calculate cross-scene boost from similar scenes
        cross_scene_score = 0.0
        total_weight = 0.0

        for similar_scene_id, similarity in similar_scenes:
            # Get evolution data from similar scene
            similar_evolution = evolution_tracker.get_evolution_data(similar_scene_id)
            if not similar_evolution:
                continue

            # Find pattern uses in similar scene
            pattern_found = False
            for iteration in similar_evolution:
                quality = iteration.get("quality_score", 0) or 0
                alignment = iteration.get("intent_alignment_score", 0) or 0

                patterns_used = iteration.get("patterns_used") or []
                if not isinstance(patterns_used, list):
                    continue

                for p in patterns_used:
                    if not isinstance(p, dict):
                        continue
                    p_type = p.get("pattern_type") or p.get("type")
                    p_value = p.get("pattern_value") or p.get("value")
                    if p_value == pattern_value and p_type == pattern_type:
                        # Weight by similarity
                        # Only count if positive match (quality >= 0.75 AND alignment >= 0.75)
                        if quality >= 0.75 and alignment >= 0.75:
                            cross_scene_score += similarity * (quality + alignment) / 2
                            total_weight += similarity
                        pattern_found = True
                        break
            if pattern_found:
                break

        if total_weight == 0:
            logger.debug(
                f"Cross-scene boost for {pattern_type}:{pattern_value}: "
                f"no positive matches in {len(similar_scenes)} similar scenes"
            )
            return 1.0

        # Normalize by total weight
        normalized_score = cross_scene_score / total_weight

        # Convert to boost multiplier (0.9 to 1.1 range)
        cross_scene_boost = 1.0 + (normalized_score - 0.5) * 0.4  # Maps 0.5->1.0, 0.0->0.9, 1.0->1.1

        # In shadow mode, log but don't apply
        if self._ENABLE_CROSS_SCENE_SHADOW_MODE and not self._ENABLE_CROSS_SCENE_REUSE:
            logger.info(
                f"SHADOW MODE - Cross-scene boost for {pattern_type}:{pattern_value}: "
                f"scenes={len(similar_scenes)}, avg_sim={avg_similarity:.3f}, "
                f"score={normalized_score:.3f}, boost={cross_scene_boost:.3f} (not applied)"
            )
            return 1.0  # Don't apply in shadow mode

        # Clamp to safe range
        cross_scene_boost = max(
            self._CROSS_SCENE_ONLY_FLOOR,
            min(self._CROSS_SCENE_ONLY_CEILING, cross_scene_boost)
        )

        logger.debug(
            f"Cross-scene boost for {pattern_type}:{pattern_value}: "
            f"scenes={len(similar_scenes)}, avg_sim={avg_similarity:.3f}, "
            f"boost={cross_scene_boost:.3f}"
        )

        return cross_scene_boost

    def _find_similar_scenes_for_context(
        self,
        scene_id: str,
        similarity_context: 'SceneContext'
    ) -> List[Tuple[str, float]]:
        """
        Find scenes similar to the given context.
    
        This method queries the evolution tracker for all scenes and
        finds those with similar context. Results are cached.
    
        Uses existing data sources only:
        - evolution_tracker._evolutions: project_id -> scene_id -> SceneEvolution
        - SceneIteration.scene_intent: Optional[Dict] with context fields
        """
        # Use the already-imported SceneContext from scene_evolution
        # (imported at top of file to avoid circular imports issues)
        from app.services.scene_evolution import find_similar_scenes
    
        # Build list of all known scene contexts from evolution data
        all_contexts: List[SceneContext] = []
    
        # Iterate through all projects and scenes in evolution tracker
        for project_id, scenes in evolution_tracker._evolutions.items():
            for other_scene_id, evolution in scenes.items():
                # Skip the same scene
                if other_scene_id == scene_id:
                    continue
    
                # Get latest iteration's scene_intent
                if not evolution.iterations:
                    continue
    
                latest = evolution.iterations[-1]
                intent_dict = getattr(latest, 'scene_intent', None)
    
                if not intent_dict or not isinstance(intent_dict, dict):
                    continue
    
                # Convert dict to SceneContext
                other_context = SceneContext(
                    scene_id=other_scene_id,
                    scene_type=intent_dict.get('scene_type', ''),
                    emotion=intent_dict.get('emotion', ''),
                    visual_goal=intent_dict.get('visual_goal', ''),
                    genre=intent_dict.get('genre', ''),
                    emotional_goal=intent_dict.get('emotional_goal', ''),
                    time_of_day=intent_dict.get('time_of_day', ''),
                    location_type=intent_dict.get('location_type', ''),
                    pacing=intent_dict.get('pacing', ''),
                    lighting_quality=intent_dict.get('lighting_quality', ''),
                    color_palette=intent_dict.get('color_palette', '')
                )
    
                # Only include if has meaningful context
                if not other_context.is_empty():
                    all_contexts.append(other_context)
    
        # Use the existing find_similar_scenes function
        if not all_contexts:
            logger.debug(f"_find_similar_scenes_for_context({scene_id}): no contexts found")
            return []
    
        results = find_similar_scenes(
            target_context=similarity_context,
            all_contexts=all_contexts,
            min_similarity=self._MIN_CROSS_SCENE_SIMILARITY,
            max_results=self._MAX_CROSS_SCENE_CANDIDATES
        )
    
        logger.debug(
            f"_find_similar_scenes_for_context({scene_id}): "
            f"found {len(results)} similar scenes from {len(all_contexts)} candidates"
        )
    
        return results

    def get_weighted_patterns(
        self,
        project_id: str,
        pattern_type: str,
        scene_intent: Optional[SceneIntent] = None,
        scene_id: Optional[str] = None,
        limit: int = 10
    ) -> List[WeightedPattern]:
        """
        Get patterns ranked by weight_score with context relevance boost.

        This is the main retrieval method - returns patterns ordered by:
        weight_score = (success_rate * usage_count * context_relevance) * decay

        If scene_id is provided, patterns used in high-quality iterations
        get a slight boost (0.9-1.1 multiplier).
        """
        # Check user override first
        override_found, _ = self.check_user_override(project_id, pattern_type)
        if override_found:
            return []

        patterns = self._patterns.get(project_id, {}).get(pattern_type, {})

        if not patterns:
            return []

        # Use provided intent or project default
        intent = scene_intent or self.get_project_intent(project_id)

        # Calculate weighted scores with current context
        weighted_patterns = []
        # Store boosts separately to avoid mutating cached pattern objects
        boosts = {}
        for pattern in patterns.values():
            # Recalculate with current context
            relevance = self.calculate_context_relevance(pattern.context_tags, intent)
            decay = pattern.calculate_decay(self._decay_hours)
            pattern.calculate_weight_score(context_relevance=relevance, decay_factor=decay)

            # Apply evolution boost if scene_id provided
            boost = 1.0
            if scene_id:
                # Build SceneContext from scene_intent for cross-scene matching
                similarity_context = None
                # Enable context building if either live mode OR shadow mode is active
                if intent and (self._ENABLE_CROSS_SCENE_REUSE or self._ENABLE_CROSS_SCENE_SHADOW_MODE):
                    similarity_context = SceneContext(
                        scene_id=scene_id,
                        scene_type=intent.scene_type,
                        emotion=intent.emotion,
                        visual_goal=intent.visual_goal,
                        genre=intent.genre,
                        emotional_goal=intent.emotional_goal,
                        time_of_day=intent.time_of_day
                    )
                boost = self._get_evolution_boost(
                    scene_id, pattern_type, pattern.pattern_value,
                    similarity_context=similarity_context
                )
            boosts[pattern.pattern_id] = boost

            weighted_patterns.append(pattern)

        # Sort by weight_score descending
        weighted_patterns.sort(key=lambda p: p.weight_score, reverse=True)

        # Apply evolution boost to weight scores
        for pattern in weighted_patterns:
            if pattern.pattern_id in boosts:
                pattern.weight_score *= boosts[pattern.pattern_id]

        # Re-sort after boost
        weighted_patterns.sort(key=lambda p: p.weight_score, reverse=True)

        return weighted_patterns[:limit]

    def get_recommended_pattern(
        self,
        project_id: str,
        pattern_type: str,
        scene_intent: Optional[SceneIntent] = None,
        scene_id: Optional[str] = None
    ) -> Optional[WeightedPattern]:
        """Get the top pattern for a given type and context"""
        patterns = self.get_weighted_patterns(project_id, pattern_type, scene_intent, scene_id, limit=1)
        return patterns[0] if patterns else None

    def get_pattern_hierarchy(self, project_id: str, pattern_type: str) -> List[WeightedPattern]:
        """Get all patterns of a type, ordered by priority rank"""
        patterns = self._patterns.get(project_id, {}).get(pattern_type, {})
        return sorted(patterns.values(), key=lambda p: p.priority_rank)

    def get_context_matches(
        self,
        project_id: str,
        pattern_type: str,
        scene_intent: SceneIntent
    ) -> List[WeightedPattern]:
        """Get patterns that match the given scene context"""
        patterns = self._patterns.get(project_id, {}).get(pattern_type, {})

        if not patterns:
            return []

        # Find patterns with matching context tags
        matching = []
        for pattern in patterns.values():
            relevance = self.calculate_context_relevance(pattern.context_tags, scene_intent)
            if relevance > 1.0:  # Only include if better than neutral
                pattern.weight_score *= relevance
                matching.append(pattern)

        matching.sort(key=lambda p: p.weight_score, reverse=True)
        return matching

    def get_recommended_pattern_legacy(
        self,
        project_id: str,
        pattern_type: str
    ) -> Optional[WeightedPattern]:
        """Legacy method - returns top pattern by priority_rank"""
        patterns = self._patterns.get(project_id, {}).get(pattern_type, {})
        if not patterns:
            return None
        return min(patterns.values(), key=lambda p: p.priority_rank)

    def get_pattern_suggestions(
        self,
        project_id: str,
        pattern_type: str,
        scene_intent: Optional[SceneIntent] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get pattern suggestions with reasoning.

        Returns list of:
        - pattern_value: the actual pattern
        - weight_score: calculated weight
        - success_rate: historical success rate
        - context_relevance: how well it matches current scene
        - established: whether it's a stable, trusted pattern
        """
        patterns = self.get_weighted_patterns(
            project_id, pattern_type, scene_intent, limit=limit
        )

        suggestions = []
        for p in patterns:
            intent = scene_intent or self.get_project_intent(project_id)
            relevance = self.calculate_context_relevance(p.context_tags, intent)

            suggestions.append({
                "pattern_value": p.pattern_value,
                "weight_score": round(p.weight_score, 3),
                "success_rate": round(p.success_rate, 3),
                "context_relevance": round(relevance, 2),
                "established": p.is_established,
                "usage_count": p.total_count
            })

        return suggestions

    def check_consistency(
        self,
        project_id: str,
        pattern_type: str,
        expected_value: str
    ) -> Dict[str, Any]:
        """
        Check if the current top pattern is consistent with expectations.

        Returns:
        - is_consistent: bool
        - current_top: the current top pattern value
        - expected: what was expected
        - deviation_detected: bool
        """
        current = self.get_recommended_pattern(project_id, pattern_type)
        current_value = current.pattern_value if current else None

        return {
            "is_consistent": current_value == expected_value,
            "current_top": current_value,
            "expected": expected_value,
            "deviation_detected": current_value != expected_value
        }

    def get_project_established_patterns(self, project_id: str) -> Dict[str, str]:
        """
        Get all established patterns for a project.

        Returns: {pattern_type: pattern_value} for patterns where is_established=True
        """
        result = {}
        for pattern_type, patterns in self._patterns.get(project_id, {}).items():
            for pattern in patterns.values():
                if pattern.is_established:
                    result[pattern_type] = pattern.pattern_value
        return result

    def apply_decay_to_all(self, project_id: str):
        """Apply time-based decay to all patterns in a project"""
        for pattern_type, patterns in self._patterns.get(project_id, {}).items():
            for pattern in patterns.values():
                decay = pattern.calculate_decay(self._decay_hours)
                if decay < 1.0:
                    pattern.weight_score *= decay
                    logger.debug(
                        f"Decay applied to {project_id}/{pattern_type}/{pattern.pattern_value}: "
                        f"weight={pattern.weight_score:.3f} (decay={decay:.2f})"
                    )

    def log_adaptive_decision(
        self,
        agent_role: str,
        decision_type: str,
        decision: str,
        memory_used: Dict[str, Any],
        reason: str,
        weight_applied: float = 0.0,
        context_relevance: float = 0.0,
        based_on_feedback: bool = False,
        feedback_id: Optional[str] = None
    ):
        """Log an adaptive decision for traceability"""
        entry = AdaptiveDecision(
            timestamp=datetime.now().isoformat(),
            agent_role=agent_role,
            decision_type=decision_type,
            decision=decision,
            memory_used=memory_used,
            reason=reason,
            weight_applied=weight_applied,
            context_relevance=context_relevance,
            based_on_feedback=based_on_feedback,
            feedback_id=feedback_id
        )
        self._decision_log.append(entry)

    def get_decision_log(
        self,
        project_id: Optional[str] = None,
        agent_role: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get recent adaptive decisions, optionally filtered"""
        results = self._decision_log

        if agent_role:
            results = [d for d in results if d.agent_role == agent_role]

        # Sort by timestamp descending and limit
        results = sorted(results, key=lambda d: d.timestamp, reverse=True)[:limit]

        return [
            {
                "timestamp": d.timestamp,
                "agent_role": d.agent_role,
                "decision_type": d.decision_type,
                "decision": d.decision,
                "reason": d.reason,
                "weight_applied": d.weight_applied,
                "context_relevance": d.context_relevance,
                "based_on_feedback": d.based_on_feedback
            }
            for d in results
        ]

    def get_project_context(self, project_id: str) -> Dict[str, Any]:
        """Get all context info for a project"""
        return {
            "intent": self.get_project_intent(project_id).to_tags(),
            "established_patterns": self.get_project_established_patterns(project_id),
            "style_boundaries": self._style_boundaries.get(project_id, {}),
            "user_overrides": list(self._user_overrides.get(project_id, {}).keys())
        }

    def get_shot_planner_adaptations(self, project_id: str) -> Dict[str, Any]:
        """Get adaptation data specific to shot planning"""
        return {
            "camera_patterns": self.get_project_established_patterns(project_id).get("camera", ""),
            "context": self.get_project_context(project_id)
        }

    def get_prompt_engineer_adaptations(self, project_id: str) -> Dict[str, Any]:
        """Get adaptation data specific to prompt engineering"""
        return {
            "prompt_patterns": self.get_project_established_patterns(project_id).get("prompt", ""),
            "context": self.get_project_context(project_id)
        }

    def get_quality_reviewer_adaptations(self, project_id: str) -> Dict[str, Any]:
        """Get adaptation data specific to quality review"""
        return {
            "quality_patterns": self.get_project_established_patterns(project_id).get("quality", ""),
            "context": self.get_project_context(project_id)
        }

    def get_evolution_metrics(self, project_id: str) -> Dict[str, Any]:
        """Get evolution metrics for a project"""
        total_patterns = sum(
            len(patterns) for patterns in self._patterns.get(project_id, {}).values()
        )
        established = len(self.get_project_established_patterns(project_id))

        return {
            "total_patterns": total_patterns,
            "established_patterns": established,
            "establishment_rate": established / total_patterns if total_patterns > 0 else 0.0
        }

    def _get_evolution_phase(self, established_count: int) -> str:
        """Determine evolution phase based on established patterns"""
        if established_count < 3:
            return "initial"
        elif established_count < 10:
            return "learning"
        elif established_count < 20:
            return "refining"
        else:
            return "optimized"

    def get_preference_hierarchy_summary(self, project_id: str) -> Dict[str, Any]:
        """Get summary of preference hierarchies across all pattern types"""
        summary = {}
        for pattern_type, patterns in self._patterns.get(project_id, {}).items():
            if patterns:
                top = max(patterns.values(), key=lambda p: p.weight_score)
                summary[pattern_type] = {
                    "top_pattern": top.pattern_value,
                    "top_weight": round(top.weight_score, 3),
                    "total_variants": len(patterns),
                    "established": top.is_established
                }
        return summary

    def _get_or_create_pattern(
        self,
        project_id: str,
        pattern_type: str,
        pattern_value: str
    ) -> WeightedPattern:
        """Get existing pattern or create new one"""
        pattern_id = self._generate_pattern_id(pattern_type, pattern_value)

        if pattern_id not in self._patterns[project_id][pattern_type]:
            self._patterns[project_id][pattern_type][pattern_id] = WeightedPattern(
                pattern_id=pattern_id,
                pattern_type=pattern_type,
                pattern_value=pattern_value,
                first_used=datetime.now().isoformat()
            )

        return self._patterns[project_id][pattern_type][pattern_id]


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

# Global adaptation engine instance for cross-module access
adaptation_engine = AdaptationEngine()

