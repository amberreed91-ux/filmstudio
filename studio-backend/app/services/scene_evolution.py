"""
Scene Evolution Tracker - Creative Growth Analysis

This module tracks how scenes evolve over time, enabling the system to
understand its own creative growth and improvement.

Key Features:
1. Scene Evolution Model - tracks iteration, alignment, quality
2. Improvement Analysis - measures creative growth
3. Pattern Evolution - shows how patterns develop
4. Diversity Metrics - tracks creative variety

Metrics:
- improvement_rate: How quality changes over iterations
- consistency_score: How well intent is maintained
- diversity_score: Creative variety in approaches
"""

import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("studio-evolution")

# ============================================================================
# CONTEXT CLASSES
# ============================================================================

@dataclass
class SceneContext:
    """
    Structured context for cross-scene similarity matching.

    Captures semantic attributes of a scene that influence whether
    a pattern will be effective. Used for context-aware pattern reuse.

    All fields are optional to maintain backward compatibility with
    scenes that don't have full context metadata.
    """
    scene_id: str = ""

    # Core context fields (most important for similarity)
    scene_type: str = ""      # INT, EXT, INT/EXT
    emotion: str = ""         # tense, dramatic, mysterious, action, calm
    visual_goal: str = ""     # dark, bright, moody, dynamic, ethereal
    genre: str = ""           # noir, horror, action, romance, comedy

    # Extended context fields
    emotional_goal: str = ""  # tension, joy, sadness, suspense, wonder
    time_of_day: str = ""     # day, night, dawn, dusk, golden_hour
    location_type: str = ""   # urban, rural, indoor, outdoor, enclosed
    pacing: str = ""          # slow, medium, fast
    lighting_quality: str = ""  # natural, artificial, mixed, dramatic
    color_palette: str = ""   # warm, cool, neutral, high_contrast, desaturated

    def to_tag_set(self) -> Set[str]:
        """Convert to set of non-empty tags for Jaccard similarity."""
        tags = set()
        for field_name in ['scene_type', 'emotion', 'visual_goal', 'genre',
                          'emotional_goal', 'time_of_day', 'location_type',
                          'pacing', 'lighting_quality', 'color_palette']:
            val = getattr(self, field_name, "")
            if val:
                tags.add(f"{field_name}:{val.lower()}")
        return tags

    def is_empty(self) -> bool:
        """Check if context has any meaningful data."""
        return len(self.to_tag_set()) == 0


# Context field weights for similarity calculation
CONTEXT_FIELD_WEIGHTS = {
    'emotion': 0.20,
    'scene_type': 0.15,
    'visual_goal': 0.15,
    'genre': 0.12,
    'emotional_goal': 0.12,
    'pacing': 0.08,
    'time_of_day': 0.06,
    'location_type': 0.06,
    'lighting_quality': 0.04,
    'color_palette': 0.02,
}


def calculate_context_similarity(ctx1: SceneContext, ctx2: SceneContext) -> float:
    """
    Calculate similarity between two scene contexts (0.0 to 1.0).

    Uses weighted Jaccard similarity on tag sets.
    Returns 0.0 if either context has no tags.
    """
    tags1 = ctx1.to_tag_set()
    tags2 = ctx2.to_tag_set()

    if not tags1 or not tags2:
        return 0.0

    # Jaccard similarity
    intersection = len(tags1 & tags2)
    union = len(tags1 | tags2)

    return intersection / union if union > 0 else 0.0


def find_similar_scenes(
    target_context: SceneContext,
    all_contexts: List[SceneContext],
    min_similarity: float = 0.3,
    max_results: int = 10
) -> List[Tuple[str, float]]:
    """
    Find scenes similar to target, return (scene_id, similarity) pairs.

    Args:
        target_context: The scene to find matches for
        all_contexts: List of candidate scene contexts
        min_similarity: Minimum similarity threshold (0.0-1.0)
        max_results: Maximum number of results to return

    Returns:
        List of (scene_id, similarity) tuples, sorted by similarity descending
    """
    if target_context.is_empty():
        return []

    similarities = []
    for scene_ctx in all_contexts:
        if scene_ctx.scene_id == target_context.scene_id:
            continue  # Don't match self
        sim = calculate_context_similarity(target_context, scene_ctx)
        if sim >= min_similarity:
            similarities.append((scene_ctx.scene_id, sim))

    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:max_results]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SceneIteration:
    """Single iteration of a scene with evaluation data"""
    scene_id: str
    iteration_number: int
    timestamp: str
    
    # Alignment & Quality
    intent_alignment_score: float = 0.0  # 0.0-1.0 How well intent was executed
    quality_score: float = 0.0            # 0.0-1.0 Overall quality rating
    
    # Pattern Usage
    patterns_used: List[Dict] = field(default_factory=list)  # [{type, value, weight}]
    deviations_used: List[Dict] = field(default_factory=list)  # [{type, value, reason}]
    
    # Context
    scene_intent: Optional[Dict] = None
    render_job_id: Optional[str] = None
    approved: bool = False
    notes: str = ""
    
    # Decision source tracking
    decision_sources: Dict[str, str] = field(default_factory=dict)  # type -> source
    conflicts_resolved: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "scene_id": self.scene_id,
            "iteration_number": self.iteration_number,
            "timestamp": self.timestamp,
            "intent_alignment_score": self.intent_alignment_score,
            "quality_score": self.quality_score,
            "patterns_used": self.patterns_used,
            "deviations_used": self.deviations_used,
            "scene_intent": self.scene_intent,
            "render_job_id": self.render_job_id,
            "approved": self.approved,
            "notes": self.notes,
            "decision_sources": self.decision_sources,
            "conflicts_resolved": self.conflicts_resolved
        }


@dataclass
class SceneEvolution:
    """Full evolution history for a scene"""
    scene_id: str
    project_id: str
    
    iterations: List[SceneIteration] = field(default_factory=list)
    
    # Calculated metrics
    improvement_rate: float = 0.0
    consistency_score: float = 0.0
    diversity_score: float = 0.0
    
    # Pattern evolution
    pattern_evolution: List[Dict] = field(default_factory=list)
    deviation_count: int = 0
    
    # Current state
    current_iteration: int = 0
    best_quality: float = 0.0
    best_iteration: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "scene_id": self.scene_id,
            "project_id": self.project_id,
            "iterations": [i.to_dict() for i in self.iterations],
            "metrics": {
                "improvement_rate": round(self.improvement_rate, 4),
                "consistency_score": round(self.consistency_score, 4),
                "diversity_score": round(self.diversity_score, 4)
            },
            "pattern_evolution": self.pattern_evolution,
            "deviation_count": self.deviation_count,
            "current_iteration": self.current_iteration,
            "best_quality": round(self.best_quality, 4),
            "best_iteration": self.best_iteration
        }


@dataclass  
class ProjectEvolution:
    """Project-level evolution summary"""
    project_id: str
    
    # Scene-level summaries
    scenes: Dict[str, SceneEvolution] = field(default_factory=dict)
    
    # Aggregate metrics
    total_improvement_rate: float = 0.0
    avg_consistency: float = 0.0
    avg_diversity: float = 0.0
    total_iterations: int = 0
    total_deviations: int = 0
    
    # Pattern learning
    learned_patterns: int = 0
    established_patterns: int = 0
    
    # Creative growth phase
    growth_phase: str = "learning"
    
    def to_dict(self) -> Dict:
        return {
            "project_id": self.project_id,
            "scene_count": len(self.scenes),
            "metrics": {
                "total_improvement_rate": round(self.total_improvement_rate, 4),
                "avg_consistency": round(self.avg_consistency, 4),
                "avg_diversity": round(self.avg_diversity, 4),
                "total_iterations": self.total_iterations,
                "total_deviations": self.total_deviations
            },
            "patterns": {
                "learned": self.learned_patterns,
                "established": self.established_patterns
            },
            "growth_phase": self.growth_phase
        }


# ============================================================================
# SCENE EVOLUTION TRACKER
# ============================================================================

class SceneEvolutionTracker:
    """
    Tracks how scenes evolve over time.
    
    Enables the system to understand improvement, not just store feedback.
    
    Usage:
        tracker = SceneEvolutionTracker()
        
        # Record iteration
        tracker.record_iteration(project_id, scene_id, iteration_data)
        
        # Get evolution
        evolution = tracker.get_scene_evolution(project_id, scene_id)
        
        # Get metrics
        metrics = tracker.get_metrics(project_id)
    """
    
    def __init__(self):
        # Scene evolutions: project_id -> scene_id -> SceneEvolution
        self._evolutions: Dict[str, Dict[str, SceneEvolution]] = defaultdict(dict)
        
        # Iteration storage for quick lookup
        self._iterations: Dict[str, List[SceneIteration]] = defaultdict(list)
        
        # Pattern history for diversity calculation
        self._pattern_history: Dict[str, List[str]] = defaultdict(list)
        
        logger.info("Scene Evolution Tracker initialized")
    
    # ========================================================================
    # RECORDING
    # ========================================================================
    
    def record_iteration(
        self,
        project_id: str,
        scene_id: str,
        intent_alignment: float = 0.0,
        quality_score: float = 0.0,
        patterns_used: Optional[List[Dict]] = None,
        deviations_used: Optional[List[Dict]] = None,
        scene_intent: Optional[Dict] = None,
        render_job_id: Optional[str] = None,
        approved: bool = False,
        notes: str = "",
        decision_sources: Optional[Dict[str, str]] = None,
        conflicts_resolved: int = 0
    ) -> SceneIteration:
        """
        Record a new iteration for a scene.
        
        Returns the created iteration.
        """
        # Get or create evolution
        if scene_id not in self._evolutions[project_id]:
            self._evolutions[project_id][scene_id] = SceneEvolution(
                scene_id=scene_id,
                project_id=project_id
            )
        
        evolution = self._evolutions[project_id][scene_id]
        
        # Calculate iteration number
        iteration_number = len(evolution.iterations) + 1
        
        # Create iteration
        iteration = SceneIteration(
            scene_id=scene_id,
            iteration_number=iteration_number,
            timestamp=datetime.now().isoformat(),
            intent_alignment_score=intent_alignment,
            quality_score=quality_score,
            patterns_used=patterns_used or [],
            deviations_used=deviations_used or [],
            scene_intent=scene_intent,
            render_job_id=render_job_id,
            approved=approved,
            notes=notes,
            decision_sources=decision_sources or {},
            conflicts_resolved=conflicts_resolved
        )
        
        # Add to evolution
        evolution.iterations.append(iteration)
        evolution.current_iteration = iteration_number
        evolution.deviation_count += len(deviations_used or [])
        
        # Track patterns for diversity
        for pattern in (patterns_used or []):
            ptype = pattern.get("type", "unknown")
            pvalue = pattern.get("value", "")
            self._pattern_history[f"{project_id}:{ptype}"].append(pvalue)
        
        # Update best quality
        if quality_score > evolution.best_quality:
            evolution.best_quality = quality_score
            evolution.best_iteration = iteration_number
        
        # Recalculate metrics
        self._recalculate_metrics(project_id, scene_id)
        
        # Update pattern evolution
        self._update_pattern_evolution(project_id, scene_id)
        
        logger.info(
            f"ITERATION RECORDED: {scene_id} iter={iteration_number} "
            f"quality={quality_score:.2f} alignment={intent_alignment:.2f}"
        )
        
        return iteration

    def _normalize_patterns(
        self,
        patterns: Optional[List[Dict]]
    ) -> List[Dict]:
        """
        Normalize pattern dicts to canonical form: {pattern_type, pattern_value}.
        
        Handles backward compatibility with old keys:
        - Old: {type, value}
        - New: {pattern_type, pattern_value}
        
        Returns empty list if patterns is None or not a list.
        """
        if not patterns:
            return []
        if not isinstance(patterns, list):
            return []
        
        normalized = []
        for p in patterns:
            if not isinstance(p, dict):
                continue
            # Support both old and new key formats
            pattern_type = p.get("pattern_type") or p.get("type")
            pattern_value = p.get("pattern_value") or p.get("value")
            if pattern_type and pattern_value:
                normalized.append({
                    "pattern_type": pattern_type,
                    "pattern_value": pattern_value
                })
        return normalized

    def record_evolution(
        self,
        scene_id: str,
        iteration_number: int,
        intent_alignment_score: float,
        quality_score: float,
        patterns_used: Optional[List[Dict]] = None,
        deviations_used: Optional[List[Dict]] = None
    ) -> SceneIteration:
        """
        Record evolution data for a scene.

        Args:
            scene_id: The scene identifier
            iteration_number: Iteration number
            intent_alignment_score: Alignment score (0.0-1.0)
            quality_score: Quality score (0.0-1.0)
            patterns_used: Optional list of patterns
            deviations_used: Optional list of deviations
        """
        # Find project_id from existing evolutions or use default
        project_id = None
        for pid, scenes in self._evolutions.items():
            if scene_id in scenes:
                project_id = pid
                break

        if project_id is None:
            # Default project if not found - create minimal evolution
            project_id = "default"
            self._evolutions[project_id][scene_id] = SceneEvolution(
                scene_id=scene_id,
                project_id=project_id
            )

        evolution = self._evolutions[project_id][scene_id]

        # Normalize patterns to canonical form: {pattern_type, pattern_value}
        # Handles both old keys (type/value) and new keys (pattern_type/pattern_value)
        normalized_patterns = self._normalize_patterns(patterns_used)
        normalized_deviations = self._normalize_patterns(deviations_used)

        iteration = SceneIteration(
            scene_id=scene_id,
            iteration_number=iteration_number,
            timestamp=datetime.now().isoformat(),
            intent_alignment_score=intent_alignment_score,
            quality_score=quality_score,
            patterns_used=normalized_patterns,
            deviations_used=normalized_deviations
        )

        evolution.iterations.append(iteration)
        logger.info(
            f"RECORD_EVOLUTION: scene_id={scene_id} iter={iteration_number} "
            f"alignment={intent_alignment_score:.2f} quality={quality_score:.2f} "
            f"stored_count={len(evolution.iterations)}"
        )
        return iteration

    def record_approval(
        self,
        project_id: str,
        scene_id: str,
        render_job_id: Optional[str] = None,
        notes: str = ""
    ) -> SceneIteration:
        """Record approval for current iteration"""
        evolution = self._evolutions[project_id].get(scene_id)
        
        if not evolution or not evolution.iterations:
            # Create new iteration with approval
            return self.record_iteration(
                project_id=project_id,
                scene_id=scene_id,
                quality_score=1.0,
                approved=True,
                render_job_id=render_job_id,
                notes=notes
            )
        
        # Update current iteration
        current = evolution.iterations[-1]
        current.approved = True
        current.quality_score = max(current.quality_score, 0.8)
        current.render_job_id = render_job_id or current.render_job_id
        current.notes = notes
        
        return current
    
    # ========================================================================
    # RETRIEVAL
    # ========================================================================
    
    def get_scene_evolution(
        self,
        project_id: str,
        scene_id: str
    ) -> Optional[Dict]:
        """Get full evolution history for a scene"""
        evolution = self._evolutions[project_id].get(scene_id)
        
        if not evolution:
            return None
        
        return evolution.to_dict()
    
    def get_iteration(
        self,
        project_id: str,
        scene_id: str,
        iteration_number: int
    ) -> Optional[SceneIteration]:
        """Get specific iteration"""
        evolution = self._evolutions[project_id].get(scene_id)
        
        if not evolution:
            return None
        
        for iteration in evolution.iterations:
            if iteration.iteration_number == iteration_number:
                return iteration
        
        return None
    
    def get_latest_iteration(
        self,
        project_id: str,
        scene_id: str
    ) -> Optional[SceneIteration]:
        """Get most recent iteration"""
        evolution = self._evolutions[project_id].get(scene_id)
        
        if not evolution or not evolution.iterations:
            return None
        
        return evolution.iterations[-1]

    def get_evolution_data(
        self,
        scene_id: str,
        limit: Optional[int] = None
    ) -> Optional[List[Dict]]:
        """
        Get evolution data for a scene.

        Args:
            scene_id: The scene identifier
            limit: Optional limit on number of iterations to return
        """
        # Find project_id containing this scene
        for project_id, scenes in self._evolutions.items():
            if scene_id in scenes:
                evolution = scenes[scene_id]
                iterations = evolution.iterations
                if limit:
                    iterations = iterations[-limit:]
                logger.info(
                    f"GET_EVOLUTION_DATA: scene_id={scene_id} "
                    f"found={len(iterations)} iterations"
                )
                return [i.to_dict() for i in iterations]
        logger.info(f"GET_EVOLUTION_DATA: scene_id={scene_id} not found")
        return None

    # ========================================================================
    # METRICS CALCULATION
    # ========================================================================
    
    def _recalculate_metrics(self, project_id: str, scene_id: str):
        """Recalculate evolution metrics"""
        evolution = self._evolutions[project_id][scene_id]
        iterations = evolution.iterations
        
        if len(iterations) < 2:
            evolution.improvement_rate = 0.0
            evolution.consistency_score = 0.5
            evolution.diversity_score = 0.5
            return
        
        # Improvement Rate: Compare first to latest quality
        first_quality = iterations[0].quality_score
        last_quality = iterations[-1].quality_score
        
        if first_quality > 0:
            evolution.improvement_rate = (last_quality - first_quality) / first_quality
        else:
            evolution.improvement_rate = last_quality
        
        # Consistency Score: Variance in alignment scores
        alignments = [i.intent_alignment_score for i in iterations]
        mean_alignment = sum(alignments) / len(alignments)
        
        if len(alignments) > 1:
            variance = sum((a - mean_alignment) ** 2 for a in alignments) / len(alignments)
            std_dev = variance ** 0.5
            # Lower variance = higher consistency
            evolution.consistency_score = max(0.0, 1.0 - std_dev)
        else:
            evolution.consistency_score = 0.5
        
        # Diversity Score: Unique patterns / total patterns
        all_patterns = []
        for iteration in iterations:
            for pattern in iteration.patterns_used:
                all_patterns.append(f"{pattern.get('type')}:{pattern.get('value')}")
        
        if all_patterns:
            unique_patterns = len(set(all_patterns))
            total_patterns = len(all_patterns)
            evolution.diversity_score = unique_patterns / total_patterns
        else:
            evolution.diversity_score = 0.5
    
    def _update_pattern_evolution(self, project_id: str, scene_id: str):
        """Track how patterns evolve over iterations"""
        evolution = self._evolutions[project_id][scene_id]
        
        pattern_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        for iteration in evolution.iterations:
            for pattern in iteration.patterns_used:
                ptype = pattern.get("type", "unknown")
                pvalue = pattern.get("value", "")
                pattern_counts[ptype][pvalue] += 1
        
        # Convert to evolution format
        evolution.pattern_evolution = []
        for ptype, values in pattern_counts.items():
            evolution.pattern_evolution.append({
                "pattern_type": ptype,
                "usage_over_time": dict(values),
                "dominant_pattern": max(values, key=values.get) if values else None
            })
    
    def get_improvement_rate(
        self,
        project_id: str,
        scene_id: Optional[str] = None
    ) -> float:
        """Get improvement rate for scene or project"""
        if scene_id:
            evolution = self._evolutions[project_id].get(scene_id)
            return evolution.improvement_rate if evolution else 0.0
        
        # Project-level improvement
        scenes = self._evolutions[project_id]
        if not scenes:
            return 0.0
        
        total_rate = sum(s.improvement_rate for s in scenes.values())
        return total_rate / len(scenes)
    
    def get_consistency_score(
        self,
        project_id: str,
        scene_id: Optional[str] = None
    ) -> float:
        """Get consistency score for scene or project"""
        if scene_id:
            evolution = self._evolutions[project_id].get(scene_id)
            return evolution.consistency_score if evolution else 0.0
        
        scenes = self._evolutions[project_id]
        if not scenes:
            return 0.0
        
        return sum(s.consistency_score for s in scenes.values()) / len(scenes)
    
    def get_diversity_score(
        self,
        project_id: str,
        pattern_type: Optional[str] = None
    ) -> float:
        """Get diversity score for pattern type or all patterns"""
        key = f"{project_id}:{pattern_type}" if pattern_type else project_id
        history = self._pattern_history.get(key, [])
        
        if len(history) < 2:
            return 0.5
    
        unique = len(set(history))
        return unique / len(history)
    
                            # ========================================================================
                            # PROJECT-LEVEL AGGREGATION
                            # ========================================================================
                        
    def compute_improvement_metrics(self, scene_id: str) -> Dict:
                                """
                                Compute improvement metrics for a scene.
                        
                                Args:
                                    scene_id: The scene identifier
                        
                                Returns:
                                    Dict with improvement metrics
                                """
                                for project_id, scenes in self._evolutions.items():
                                    if scene_id in scenes:
                                        evolution = scenes[scene_id]
                                        logger.info(
                                            f"COMPUTE_IMPROVEMENT_METRICS: scene_id={scene_id} "
                                            f"iterations={len(evolution.iterations)} "
                                            f"improvement_rate={evolution.improvement_rate:.4f}"
                                        )
                                        return {
                                            "improvement_rate": evolution.improvement_rate,
                                            "consistency_score": evolution.consistency_score,
                                            "diversity_score": evolution.diversity_score
                                        }
                                logger.info(f"COMPUTE_IMPROVEMENT_METRICS: scene_id={scene_id} not found, returning zeros")
                                return {"improvement_rate": 0.0, "consistency_score": 0.0, "diversity_score": 0.0}
                        
                            # ========================================================================
                            # PROJECT-LEVEL AGGREGATION
                            # ========================================================================
                        
    def get_project_evolution(self, project_id: str) -> Dict:
                                """Get project-level evolution summary"""
                                scenes = self._evolutions.get(project_id, {})
                        
                                if not scenes:
                                    return {
                                        "project_id": project_id,
                                        "scene_count": 0,
                                        "metrics": {},
                                        "growth_phase": "learning"
                                    }
                        
                                total_improvement = sum(s.improvement_rate for s in scenes.values())
                                avg_consistency = sum(s.consistency_score for s in scenes.values()) / len(scenes)
                                avg_diversity = sum(s.diversity_score for s in scenes.values()) / len(scenes)
                        
                                total_iterations = sum(len(s.iterations) for s in scenes.values())
                                total_deviations = sum(s.deviation_count for s in scenes.values())
                        
                                # Determine growth phase
                                total_its = total_iterations
                                if total_its < 5:
                                    phase = "learning"
                                elif total_its < 20:
                                    phase = "adapting"
                                elif total_its < 50:
                                    phase = "refining"
                                else:
                                    phase = "optimized"
                        
                                return {
                                    "project_id": project_id,
                                    "scene_count": len(scenes),
                                    "metrics": {
                                        "total_improvement_rate": round(total_improvement / len(scenes), 4),
                                        "avg_consistency": round(avg_consistency, 4),
                                        "avg_diversity": round(avg_diversity, 4),
                                        "total_iterations": total_iterations,
                                        "total_deviations": total_deviations
                                    },
                                    "growth_phase": phase,
                                    "scenes": {sid: s.to_dict() for sid, s in scenes.items()}
                                }
    
    def get_metrics(self, project_id: str) -> Dict:
        """Get concise metrics for a project"""
        evolution = self.get_project_evolution(project_id)
        
        return {
            "project_id": project_id,
            "improvement_rate": evolution["metrics"].get("total_improvement_rate", 0.0),
            "consistency_score": evolution["metrics"].get("avg_consistency", 0.0),
            "diversity_score": evolution["metrics"].get("avg_diversity", 0.0),
            "total_iterations": evolution["metrics"].get("total_iterations", 0),
            "growth_phase": evolution["growth_phase"]
        }
    
    # ========================================================================
    # COMPARISON & ANALYSIS
    # ========================================================================
    
    def compare_iterations(
        self,
        project_id: str,
        scene_id: str,
        iteration_a: int,
        iteration_b: int
    ) -> Dict:
        """Compare two iterations of a scene"""
        iter_a = self.get_iteration(project_id, scene_id, iteration_a)
        iter_b = self.get_iteration(project_id, scene_id, iteration_b)
        
        if not iter_a or not iter_b:
            return {"error": "One or both iterations not found"}
        
        quality_diff = iter_b.quality_score - iter_a.quality_score
        alignment_diff = iter_b.intent_alignment_score - iter_a.intent_alignment_score
        
        # Pattern changes
        patterns_a = {f"{p.get('type')}:{p.get('value')}" for p in iter_a.patterns_used}
        patterns_b = {f"{p.get('type')}:{p.get('value')}" for p in iter_b.patterns_used}
        
        new_patterns = patterns_b - patterns_a
        dropped_patterns = patterns_a - patterns_b
        
        return {
            "scene_id": scene_id,
            "comparison": f"Iteration {iteration_a} vs {iteration_b}",
            "quality_change": round(quality_diff, 4),
            "alignment_change": round(alignment_diff, 4),
            "pattern_changes": {
                "new_patterns": list(new_patterns),
                "dropped_patterns": list(dropped_patterns),
                "stable_patterns": list(patterns_a & patterns_b)
            },
            "deviation_change": len(iter_b.deviations_used) - len(iter_a.deviations_used)
        }
    
    def get_improvement_trajectory(self, project_id: str, scene_id: str) -> Dict:
        """Get improvement trajectory for a scene"""
        evolution = self._evolutions[project_id].get(scene_id)
        
        if not evolution or len(evolution.iterations) < 2:
            return {"error": "Not enough data for trajectory"}
        
        iterations = evolution.iterations
        
        # Quality trajectory
        quality_trajectory = [
            {"iteration": i.iteration_number, "quality": i.quality_score}
            for i in iterations
        ]
        
        # Alignment trajectory
        alignment_trajectory = [
            {"iteration": i.iteration_number, "alignment": i.intent_alignment_score}
            for i in iterations
        ]
        
        # Overall trend
        first_q = iterations[0].quality_score
        last_q = iterations[-1].quality_score
        trend = "improving" if last_q > first_q else "declining" if last_q < first_q else "stable"
        
        return {
            "scene_id": scene_id,
            "iterations": len(iterations),
            "trend": trend,
            "quality_trajectory": quality_trajectory,
            "alignment_trajectory": alignment_trajectory,
            "best_iteration": evolution.best_iteration,
            "best_quality": round(evolution.best_quality, 4),
            "improvement_rate": round(evolution.improvement_rate, 4)
        }


    # Global instance
evolution_tracker = SceneEvolutionTracker()
