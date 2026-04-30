"""
Story-Level Scoring Service - Phase 4.3

Provides film-aware story-level scoring beyond scene-level evaluation.

This service evaluates:
- Thesis alignment across the film
- Tone coherence (scene/sequence/act/film)
- Character progression integrity
- Emotional trajectory health
- Motif continuity and payoff
- Unresolved tension handling
- Originality vs formula risk
- Continuity debt accumulation trajectory
- Overall film health

Usage:
service = StoryLevelScoringService()

# Scene-level scoring (in film context)
score = service.score_scene(film_id, scene_id, scene_data, context)

# Sequence-level scoring
score = service.score_sequence(film_id, sequence_id, context)

# Act-level scoring
score = service.score_act(film_id, act_number, context)

# Film-level scoring
score = service.score_film(film_id, context)

Phase 4.3: Implemented real analyzer logic for all 8 dimensions.
Each analyzer uses available data sources and falls back to conservative
scores when data is insufficient.
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass

from app.models.crew import (
    StoryScore,
    StoryRecommendation,
    RecommendationCategory,
    RevisionPriority,
    FilmStructure,
    DirectorContinuityDecision,
)
from app.services.film_intelligence_service import film_intelligence_service

# Type checking imports to avoid circular dependencies
if TYPE_CHECKING:
    from app.models.spine import CreativeSpine
    from app.models.memory import FilmLevelMemory, ActMemory, SequenceMemory
    from app.services.conflicts import FilmContinuityTracker
    from app.services.spine_consumption_service import SpineConsumptionService


# =============================================================================
# Dimension Analyzer Interfaces (Scaffolded for Phase 4.2)
# =============================================================================

class BaseDimensionAnalyzer:
    """
    Base class for dimension analyzers.
    
    Phase 4.2: These are scaffolded - they return placeholder values.
    Phase 4.3: Full analyzer logic will be implemented.
    """
    
    def analyze(self, context: Dict[str, Any]) -> float:
        """
        Analyze the given context and return a score from 0.0 to 1.0.
        
        Phase 4.2: Returns 0.5 (placeholder)
        Phase 4.3: Returns actual computed score
        """
        return 0.5  # Placeholder - implement in Phase 4.3


class ThesisAlignmentAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes thesis alignment - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_memory.themes and scene content matching.
    HEURISTIC: Uses simple keyword matching for theme detection.
    
    Scoring logic:
    - 0.5: No thesis data available (conservative fallback)
    - 0.6-0.9: Scene content mentions film themes
    - 0.5: Scene content does not mention themes
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_memory = context.get("film_memory")
        film_structure = context.get("film_structure")
        scene_data = context.get("scene_data", {})
        scene_content = scene_data.get("content", "") if scene_data else ""
        
        # Get themes from film_memory or film_structure
        themes = []
        if film_memory:
            themes = getattr(film_memory, "themes", []) or []
        if not themes and film_structure:
            themes = getattr(film_structure, "themes", []) or []
        
        if not themes:
            return 0.5  # Conservative fallback - no thesis data
        
        # Count theme mentions in scene content
        content_lower = scene_content.lower()
        theme_mentions = sum(1 for theme in themes if theme.lower() in content_lower)
        
        if theme_mentions == 0:
            return 0.5  # No theme alignment detected
        
        # Score based on theme coverage (capped at 0.9)
        alignment_ratio = min(theme_mentions / max(len(themes), 1), 1.0)
        return 0.5 + (0.4 * alignment_ratio)  # Range: 0.5-0.9


class ToneCoherenceAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes tone coherence - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_structure.tone_shifts count.
    HEURISTIC: Assumes fewer tone shifts = more coherent tone.
    
    Scoring logic:
    - 0.5: No tone data available
    - 0.7-0.9: Few tone shifts (good coherence)
    - 0.5: Many tone shifts (poor coherence)
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_structure = context.get("film_structure")
        
        if not film_structure:
            return 0.5  # Conservative fallback
        
        tone_shifts = getattr(film_structure, "tone_shifts", []) or []
        
        if not tone_shifts:
            return 0.8  # No shifts = perfect coherence
        
        # Fewer shifts = higher coherence
        shift_count = len(tone_shifts)
        
        if shift_count <= 3:
            return 0.85  # Very few shifts
        elif shift_count <= 7:
            return 0.7   # Moderate shifts
        elif shift_count <= 12:
            return 0.55  # Many shifts
        else:
            return 0.4   # Excessive shifts


class CharacterProgressionAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes character progression - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_structure.character_scenes distribution.
    HEURISTIC: Assures characters appear consistently throughout film.
    
    Scoring logic:
    - 0.5: No character data available
    - 0.6-0.9: Good character scene distribution
    - 0.3-0.5: Poor distribution (characters appear in clusters)
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_structure = context.get("film_structure")
        scene_decisions = context.get("scene_decisions", [])
        
        if not film_structure:
            return 0.5  # Conservative fallback
        
        character_scenes = getattr(film_structure, "character_scenes", {}) or {}
        total_scenes = getattr(film_structure, "total_scenes", 0) or 10
        
        if not character_scenes:
            return 0.5  # No character data
        
        # Calculate character distribution score
        char_count = len(character_scenes)
        if char_count == 0:
            return 0.5
        
        # Check if characters have reasonable screen time distribution
        scene_ids = set()
        for scenes in character_scenes.values():
            scene_ids.update(scenes)
        
        coverage = len(scene_ids) / max(total_scenes, 1)
        
        # Characters appearing in more scenes = better progression
        avg_appearances = sum(len(scenes) for scenes in character_scenes.values()) / char_count
        expected_appearances = total_scenes / char_count
        
        if expected_appearances == 0:
            return 0.5
        
        distribution_ratio = min(avg_appearances / expected_appearances, 1.5)
        
        # Combine coverage and distribution (capped at 0.9)
        score = 0.5 + (0.2 * min(coverage, 1.0)) + (0.2 * min(distribution_ratio, 1.0))
        return min(score, 0.9)


class EmotionalTrajectoryAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes emotional trajectory - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_structure.acts count for structural validation.
    HEURISTIC: Assumes 3-act structure is the baseline for emotional arcs.
    
    Scoring logic:
    - 0.5: No structure data available
    - 0.7-0.9: Proper 3-act structure with emotional trajectory
    - 0.5-0.6: Missing acts or incomplete trajectory
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_structure = context.get("film_structure")
        film_memory = context.get("film_memory")
        
        if not film_structure:
            return 0.5  # Conservative fallback
        
        acts = getattr(film_structure, "acts", []) or []
        emotional_trajectory = getattr(film_structure, "emotional_trajectory", []) or []
        
        # Also check film_memory for emotional data
        if not emotional_trajectory and film_memory:
            emotional_trajectory = getattr(film_memory, "emotional_trajectory", []) or []
        
        act_count = len(acts)
        
        # Base score on structural completeness
        if act_count >= 3:
            base_score = 0.75
        elif act_count == 2:
            base_score = 0.6
        else:
            base_score = 0.5
        
        # Bonus for having emotional trajectory data
        if emotional_trajectory:
            trajectory_bonus = min(len(emotional_trajectory) / 10, 0.15)
            return base_score + trajectory_bonus
        
        return base_score


class MotifContinuityAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes motif continuity - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_memory.motifs and scene content matching.
    HEURISTIC: Simple keyword matching for motif detection.
    
    Scoring logic:
    - 0.5: No motif data available
    - 0.6-0.9: Scene references established motifs
    - 0.5: No motif references in scene
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_memory = context.get("film_memory")
        scene_data = context.get("scene_data", {})
        scene_content = scene_data.get("content", "") if scene_data else ""
        
        if not film_memory:
            return 0.5  # Conservative fallback
        
        motifs = getattr(film_memory, "motifs", []) or []
        
        if not motifs:
            return 0.5  # No motifs defined
        
        # Check if scene references any motifs
        content_lower = scene_content.lower()
        motif_references = 0
        
        for motif in motifs:
            motif_name = getattr(motif, "name", None) or (motif.get("name") if isinstance(motif, dict) else None)
            if motif_name and motif_name.lower() in content_lower:
                motif_references += 1
        
        if motif_references == 0:
            return 0.5  # No motif references
        
        # Score based on motif reference ratio (capped at 0.9)
        reference_ratio = min(motif_references / max(len(motifs), 1), 1.0)
        return 0.5 + (0.4 * reference_ratio)


class TensionResolutionAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes tension resolution - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_memory.unresolved_tensions.
    HEURISTIC: High urgency unresolved tensions = lower score.
    
    Scoring logic:
    - 0.5: No tension data available
    - 0.7-0.9: No or low-urgency unresolved tensions
    - 0.3-0.5: High-urgency unresolved tensions
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_memory = context.get("film_memory")
        
        if not film_memory:
            return 0.5  # Conservative fallback
        
        unresolved_tensions = getattr(film_memory, "unresolved_tensions", []) or []
        
        if not unresolved_tensions:
            return 0.85  # No tensions = perfect resolution health
        
        # Calculate urgency-weighted tension score
        total_urgency = 0
        max_possible_urgency = 0
        
        for tension in unresolved_tensions:
            urgency = getattr(tension, "urgency_level", 5) or 5
            total_urgency += urgency
            max_possible_urgency += 10  # Max urgency is 10
        
        if max_possible_urgency == 0:
            return 0.85
        
        # Lower score for higher total urgency
        urgency_ratio = total_urgency / max_possible_urgency
        return 0.85 - (0.5 * urgency_ratio)  # Range: 0.35-0.85


class OriginalityAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes originality vs formula - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses film_memory.restraint_rules.
    HEURISTIC: Detects common cliché patterns in content.
    
    Scoring logic:
    - 0.5: No restraint data available
    - 0.6-0.9: Content follows restraint rules (original)
    - 0.3-0.5: Content violates restraint rules (formulaic)
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        film_memory = context.get("film_memory")
        scene_data = context.get("scene_data", {})
        scene_content = scene_data.get("content", "") if scene_data else ""
        
        if not film_memory:
            return 0.5  # Conservative fallback
        
        restraint_rules = getattr(film_memory, "restraint_rules", []) or []
        
        # Cliché patterns to detect (simple heuristic)
        cliche_patterns = [
            "deus ex machina",
            "it was all a dream",
            "suddenly",
            "meanwhile",
            "little did they know",
            "and then",
            "happened suddenly",
            "to be continued",
        ]
        
        content_lower = scene_content.lower()
        cliche_count = sum(1 for pattern in cliche_patterns if pattern in content_lower)
        
        # Base score on restraint rule compliance
        if restraint_rules:
            # Check if content follows restraint rules
            rule_violations = 0
            for rule in restraint_rules:
                rule_text = str(rule).lower()
                if rule_text in content_lower:
                    rule_violations += 1
            
            rule_score = 1.0 - (rule_violations / max(len(restraint_rules), 1))
            cliche_penalty = min(cliche_count * 0.1, 0.3)
            return max(0.3, min(rule_score - cliche_penalty, 0.9))
        
        # No restraint rules - penalize obvious clichés
        if cliche_count > 0:
            return max(0.4, 0.7 - (cliche_count * 0.15))
        
        return 0.7  # Default to good originality when no data


class ContinuityDebtTrajectoryAnalyzer(BaseDimensionAnalyzer):
    """
    Analyzes continuity debt trajectory - Phase 4.3 implementation.
    
    STRONGLY GROUNDED: Uses FilmContinuityTracker for debt tracking.
    HEURISTIC: Assumes increasing alerts = increasing debt.
    
    Scoring logic:
    - 0.5: No tracker data available
    - 0.7-0.9: Low or decreasing continuity debt
    - 0.3-0.5: High or increasing continuity debt
    """

    def analyze(self, context: Dict[str, Any]) -> float:
        continuity_tracker = context.get("continuity_tracker")
        film_id = context.get("film_id")
        
        if not continuity_tracker or not film_id:
            return 0.5  # Conservative fallback
        
        try:
            # Get continuity debt from tracker
            debt_data = continuity_tracker.get_film_continuity_debt(film_id)
            
            if not debt_data:
                return 0.8  # No debt recorded
            
            # Check alert count and severity
            alert_count = debt_data.get("alert_count", 0)
            severity = debt_data.get("severity", "none")
            
            # Calculate debt score
            if alert_count == 0:
                return 0.9  # No debt
            elif alert_count <= 3:
                return 0.75 if severity == "low" else 0.65
            elif alert_count <= 7:
                return 0.6 if severity == "medium" else 0.5
            else:
                return 0.4 if severity == "high" else 0.5
                
        except Exception:
            return 0.5  # Safe fallback on error
@dataclass
class StoryScoringContext:
    """
    Context passed to story scoring methods.
    
    Contains all the inputs needed for story-level scoring.
    """
    film_id: str
    film_structure: Optional[FilmStructure] = None
    film_memory: Optional["FilmLevelMemory"] = None
    act_memory: Optional["ActMemory"] = None
    sequence_memory: Optional["SequenceMemory"] = None
    creative_spine: Optional["CreativeSpine"] = None
    continuity_tracker: Optional["FilmContinuityTracker"] = None
    spine_consumption: Optional["SpineConsumptionService"] = None
    
    # Scene-specific data
    scene_id: Optional[str] = None
    scene_data: Optional[Dict[str, Any]] = None
    director_decision: Optional[DirectorContinuityDecision] = None
    
    # Historical data
    scene_decisions: List[DirectorContinuityDecision] = None
    
    def __post_init__(self):
        if self.scene_decisions is None:
            self.scene_decisions = []


# =============================================================================
# Story Level Scoring Service
# =============================================================================

class StoryLevelScoringService:
    """
    Service for film-aware story-level scoring.
    
    Phase 4.2: This is the service shell with scaffolded dimension analyzers.
    Full analyzer logic will be implemented in Phase 4.3.
    
    Responsibilities (Phase 4.2):
    - Accept film-level inputs
    - Return StoryScore with proper structure
    - Define scoring flow for all dimensions
    - Keep clear boundaries from DirectorEvaluator and MemoryArchivistEvaluator
    
    Responsibilities (Phase 4.3):
    - Full dimension analyzer implementation
    """
    
    def __init__(self):
        """Initialize the story scoring service."""
        # Initialize dimension analyzers (scaffolded for Phase 4.2)
        self._analyzers = {
            "thesis_alignment": ThesisAlignmentAnalyzer(),
            "tone_coherence": ToneCoherenceAnalyzer(),
            "character_progression": CharacterProgressionAnalyzer(),
            "emotional_trajectory": EmotionalTrajectoryAnalyzer(),
            "motif_continuity": MotifContinuityAnalyzer(),
            "tension_resolution_rate": TensionResolutionAnalyzer(),
            "originality_score": OriginalityAnalyzer(),
            "continuity_debt_trajectory": ContinuityDebtTrajectoryAnalyzer(),
        }
        
        # Default dimension weights (can be overridden per film)
        self._default_weights = {
            "thesis_alignment": 0.15,
            "tone_coherence": 0.10,
            "character_progression": 0.15,
            "emotional_trajectory": 0.15,
            "motif_continuity": 0.10,
            "tension_resolution_rate": 0.15,
            "originality_score": 0.10,
            "continuity_debt_trajectory": 0.10,
        }
        self._max_film_intelligence_total_delta = 0.06
        self._max_film_intelligence_dimension_delta = 0.025
    
    # =========================================================================
    # Public Scoring API
    # =========================================================================
    
    def score_scene(
        self,
        film_id: str,
        scene_id: str,
        scene_data: Dict[str, Any],
        context: StoryScoringContext
    ) -> StoryScore:
        """
        Score a single scene in film context.
        
        This evaluates the scene against film-level criteria, not just
        scene-level quality (which is DirectorEvaluator's job).
        
        Args:
            film_id: The film identifier
            scene_id: The scene identifier
            scene_data: The scene content/analysis
            context: Full story scoring context
            
        Returns:
            StoryScore at scene scope
        """
        # Build context for analyzers
        analyzer_context = self._build_scene_context(
            film_id, scene_id, scene_data, context
        )
        
        # Run all dimension analyzers
        dimension_scores = self._run_analyzers(analyzer_context)
        dimension_scores, film_intelligence_influence = self._apply_film_intelligence_evidence(
            dimension_scores,
            analyzer_context,
        )
        
        # Calculate overall health
        overall_health = self._calculate_overall_health(
            dimension_scores, self._default_weights
        )
        
        # Determine revision priority
        revision_priority = self._determine_revision_priority(dimension_scores)
        
        # Generate recommendations (Phase 4.2: placeholder)
        recommendations = self._generate_recommendations(
            dimension_scores, "scene", scene_id, film_intelligence_influence
        )
        
        return StoryScore(
            film_id=film_id,
            scope="scene",
            scope_id=scene_id,
            thesis_alignment=dimension_scores["thesis_alignment"],
            tone_coherence=dimension_scores["tone_coherence"],
            character_progression=dimension_scores["character_progression"],
            emotional_trajectory=dimension_scores["emotional_trajectory"],
            motif_continuity=dimension_scores["motif_continuity"],
            tension_resolution_rate=dimension_scores["tension_resolution_rate"],
            originality_score=dimension_scores["originality_score"],
            continuity_debt_trajectory=dimension_scores["continuity_debt_trajectory"],
            overall_health=overall_health,
            dimension_weights=self._default_weights.copy(),
            scene_count=1,
            act_count=len(context.film_structure.acts) if context.film_structure else 0,
            sequence_count=len(context.film_structure.all_sequences) if context.film_structure else 0,
            warnings=self._generate_warnings(dimension_scores),
            recommendations=recommendations,
            revision_priority=revision_priority,
            timestamp=datetime.utcnow().isoformat(),
            based_on_scenes=[scene_id],
            debug_metadata={"film_intelligence_influence": film_intelligence_influence},
        )
    
    def score_sequence(
        self,
        film_id: str,
        sequence_id: str,
        context: StoryScoringContext
    ) -> StoryScore:
        """
        Score a sequence (group of scenes).
        
        Aggregates scene-level scores within the sequence and adds
        sequence-level analysis.
        
        Args:
            film_id: The film identifier
            sequence_id: The sequence identifier
            context: Full story scoring context
            
        Returns:
            StoryScore at sequence scope
        """
        # Get scenes in this sequence
        scenes = self._get_sequence_scenes(sequence_id, context)
        
        # Build context for analyzers
        analyzer_context = self._build_sequence_context(
            film_id, sequence_id, scenes, context
        )
        
        # Run all dimension analyzers
        dimension_scores = self._run_analyzers(analyzer_context)
        dimension_scores, film_intelligence_influence = self._apply_film_intelligence_evidence(
            dimension_scores,
            analyzer_context,
        )
        
        # Calculate overall health
        overall_health = self._calculate_overall_health(
            dimension_scores, self._default_weights
        )
        
        # Determine revision priority
        revision_priority = self._determine_revision_priority(dimension_scores)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            dimension_scores, "sequence", sequence_id, film_intelligence_influence
        )
        
        return StoryScore(
            film_id=film_id,
            scope="sequence",
            scope_id=sequence_id,
            thesis_alignment=dimension_scores["thesis_alignment"],
            tone_coherence=dimension_scores["tone_coherence"],
            character_progression=dimension_scores["character_progression"],
            emotional_trajectory=dimension_scores["emotional_trajectory"],
            motif_continuity=dimension_scores["motif_continuity"],
            tension_resolution_rate=dimension_scores["tension_resolution_rate"],
            originality_score=dimension_scores["originality_score"],
            continuity_debt_trajectory=dimension_scores["continuity_debt_trajectory"],
            overall_health=overall_health,
            dimension_weights=self._default_weights.copy(),
            scene_count=len(scenes),
            act_count=len(context.film_structure.acts) if context.film_structure else 0,
            sequence_count=1,
            warnings=self._generate_warnings(dimension_scores),
            recommendations=recommendations,
            revision_priority=revision_priority,
            timestamp=datetime.utcnow().isoformat(),
            based_on_scenes=scenes,
            debug_metadata={"film_intelligence_influence": film_intelligence_influence},
        )
    
    def score_act(
        self,
        film_id: str,
        act_number: int,
        context: StoryScoringContext
    ) -> StoryScore:
        """
        Score an act (group of sequences).
        
        Aggregates sequence-level scores within the act and adds
        act-level analysis.
        
        Args:
            film_id: The film identifier
            act_number: The act number (1, 2, or 3)
            context: Full story scoring context
            
        Returns:
            StoryScore at act scope
        """
        # Get sequences in this act
        sequences = self._get_act_sequences(act_number, context)
        
        # Build context for analyzers
        analyzer_context = self._build_act_context(
            film_id, act_number, sequences, context
        )
        
        # Run all dimension analyzers
        dimension_scores = self._run_analyzers(analyzer_context)
        dimension_scores, film_intelligence_influence = self._apply_film_intelligence_evidence(
            dimension_scores,
            analyzer_context,
        )
        
        # Calculate overall health
        overall_health = self._calculate_overall_health(
            dimension_scores, self._default_weights
        )
        
        # Determine revision priority
        revision_priority = self._determine_revision_priority(dimension_scores)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            dimension_scores, "act", f"act_{act_number}", film_intelligence_influence
        )
        
        return StoryScore(
            film_id=film_id,
            scope="act",
            scope_id=f"act_{act_number}",
            thesis_alignment=dimension_scores["thesis_alignment"],
            tone_coherence=dimension_scores["tone_coherence"],
            character_progression=dimension_scores["character_progression"],
            emotional_trajectory=dimension_scores["emotional_trajectory"],
            motif_continuity=dimension_scores["motif_continuity"],
            tension_resolution_rate=dimension_scores["tension_resolution_rate"],
            originality_score=dimension_scores["originality_score"],
            continuity_debt_trajectory=dimension_scores["continuity_debt_trajectory"],
            overall_health=overall_health,
            dimension_weights=self._default_weights.copy(),
            scene_count=sum(len(seq.get("scenes", [])) for seq in sequences),
            act_count=1,
            sequence_count=len(sequences),
            warnings=self._generate_warnings(dimension_scores),
            recommendations=recommendations,
            revision_priority=revision_priority,
            timestamp=datetime.utcnow().isoformat(),
            based_on_scenes=self._get_act_scene_ids(act_number, context),
            debug_metadata={"film_intelligence_influence": film_intelligence_influence},
        )
    
    def score_film(
        self,
        film_id: str,
        context: StoryScoringContext
    ) -> StoryScore:
        """
        Score the full film.
        
        Aggregates all act-level scores and provides complete
        film health assessment.
        
        Args:
            film_id: The film identifier
            context: Full story scoring context
            
        Returns:
            StoryScore at film scope
        """
        # Build context for analyzers
        analyzer_context = self._build_film_context(film_id, context)
        
        # Run all dimension analyzers
        dimension_scores = self._run_analyzers(analyzer_context)
        dimension_scores, film_intelligence_influence = self._apply_film_intelligence_evidence(
            dimension_scores,
            analyzer_context,
        )
        
        # Calculate overall health
        overall_health = self._calculate_overall_health(
            dimension_scores, self._default_weights
        )
        
        # Determine revision priority
        revision_priority = self._determine_revision_priority(dimension_scores)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            dimension_scores, "film", film_id, film_intelligence_influence
        )
        
        return StoryScore(
            film_id=film_id,
            scope="film",
            scope_id=None,
            thesis_alignment=dimension_scores["thesis_alignment"],
            tone_coherence=dimension_scores["tone_coherence"],
            character_progression=dimension_scores["character_progression"],
            emotional_trajectory=dimension_scores["emotional_trajectory"],
            motif_continuity=dimension_scores["motif_continuity"],
            tension_resolution_rate=dimension_scores["tension_resolution_rate"],
            originality_score=dimension_scores["originality_score"],
            continuity_debt_trajectory=dimension_scores["continuity_debt_trajectory"],
            overall_health=overall_health,
            dimension_weights=self._default_weights.copy(),
            scene_count=context.film_structure.total_scenes if context.film_structure else 0,
            act_count=len(context.film_structure.acts) if context.film_structure else 0,
            sequence_count=len(context.film_structure.all_sequences) if context.film_structure else 0,
            warnings=self._generate_warnings(dimension_scores),
            recommendations=recommendations,
            revision_priority=revision_priority,
            timestamp=datetime.utcnow().isoformat(),
            based_on_scenes=self._get_all_scene_ids(context),
            debug_metadata={"film_intelligence_influence": film_intelligence_influence},
        )
    
    # =========================================================================
    # Internal Helper Methods
    # =========================================================================
    
    def _build_scene_context(
        self,
        film_id: str,
        scene_id: str,
        scene_data: Dict[str, Any],
        context: StoryScoringContext
    ) -> Dict[str, Any]:
        """Build context dict for scene-level analyzers."""
        return {
            "film_id": film_id,
            "scope": "scene",
            "scope_id": scene_id,
            "scene_data": scene_data,
            "film_structure": context.film_structure,
            "film_memory": context.film_memory,
            "creative_spine": context.creative_spine,
            "continuity_tracker": context.continuity_tracker,
            "director_decision": context.director_decision,
            "scene_decisions": context.scene_decisions,
            "film_intelligence": self._derive_film_intelligence_context(
                film_id=film_id,
                scope="scene",
                scope_id=scene_id,
                film_structure=context.film_structure,
                film_memory=context.film_memory,
                creative_spine=context.creative_spine,
            ),
        }
    
    def _build_sequence_context(
        self,
        film_id: str,
        sequence_id: str,
        scenes: List[str],
        context: StoryScoringContext
    ) -> Dict[str, Any]:
        """Build context dict for sequence-level analyzers."""
        return {
            "film_id": film_id,
            "scope": "sequence",
            "scope_id": sequence_id,
            "scenes": scenes,
            "film_structure": context.film_structure,
            "film_memory": context.film_memory,
            "sequence_memory": context.sequence_memory,
            "creative_spine": context.creative_spine,
            "continuity_tracker": context.continuity_tracker,
            "scene_decisions": context.scene_decisions,
            "film_intelligence": self._derive_film_intelligence_context(
                film_id=film_id,
                scope="sequence",
                scope_id=sequence_id,
                film_structure=context.film_structure,
                film_memory=context.film_memory,
                creative_spine=context.creative_spine,
            ),
        }
    
    def _build_act_context(
        self,
        film_id: str,
        act_number: int,
        sequences: List[Dict[str, Any]],
        context: StoryScoringContext
    ) -> Dict[str, Any]:
        """Build context dict for act-level analyzers."""
        return {
            "film_id": film_id,
            "scope": "act",
            "scope_id": f"act_{act_number}",
            "act_number": act_number,
            "sequences": sequences,
            "film_structure": context.film_structure,
            "film_memory": context.film_memory,
            "act_memory": context.act_memory,
            "creative_spine": context.creative_spine,
            "continuity_tracker": context.continuity_tracker,
            "scene_decisions": context.scene_decisions,
            "film_intelligence": self._derive_film_intelligence_context(
                film_id=film_id,
                scope="act",
                scope_id=f"act_{act_number}",
                film_structure=context.film_structure,
                film_memory=context.film_memory,
                creative_spine=context.creative_spine,
                act_number=act_number,
            ),
        }
    
    def _build_film_context(
        self,
        film_id: str,
        context: StoryScoringContext
    ) -> Dict[str, Any]:
        """Build context dict for film-level analyzers."""
        return {
            "film_id": film_id,
            "scope": "film",
            "scope_id": None,
            "film_structure": context.film_structure,
            "film_memory": context.film_memory,
            "creative_spine": context.creative_spine,
            "continuity_tracker": context.continuity_tracker,
            "scene_decisions": context.scene_decisions,
            "film_intelligence": self._derive_film_intelligence_context(
                film_id=film_id,
                scope="film",
                scope_id=None,
                film_structure=context.film_structure,
                film_memory=context.film_memory,
                creative_spine=context.creative_spine,
            ),
        }
    
    def _run_analyzers(self, analyzer_context: Dict[str, Any]) -> Dict[str, float]:
        """Run all dimension analyzers and return scores."""
        scores = {}
        for dimension, analyzer in self._analyzers.items():
            try:
                scores[dimension] = analyzer.analyze(analyzer_context)
            except Exception as e:
                # Safe fallback - don't let one analyzer failure break scoring
                scores[dimension] = 0.5
        return scores
    
    def _calculate_overall_health(
        self,
        dimension_scores: Dict[str, float],
        weights: Dict[str, float]
    ) -> float:
        """Calculate weighted overall health score."""
        total_weight = sum(weights.values())
        weighted_sum = sum(
            dimension_scores.get(dim, 0.0) * weights.get(dim, 0.0)
            for dim in weights.keys()
        )
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _determine_revision_priority(
        self,
        dimension_scores: Dict[str, float]
    ) -> RevisionPriority:
        """
        Determine revision priority based on dimension scores.
        
        Phase 4.2: Simple threshold-based logic
        Phase 4.3: May incorporate more sophisticated logic
        """
        min_score = min(dimension_scores.values()) if dimension_scores else 1.0
        
        if min_score < 0.3:
            return RevisionPriority.CRITICAL
        elif min_score < 0.5:
            return RevisionPriority.HIGH
        elif min_score < 0.7:
            return RevisionPriority.MEDIUM
        else:
            return RevisionPriority.LOW
    
    def _generate_warnings(
        self,
        dimension_scores: Dict[str, float]
    ) -> List[str]:
        """Generate warnings for low-scoring dimensions."""
        warnings = []
        for dimension, score in dimension_scores.items():
            if score < 0.5:
                warnings.append(
                    f"{dimension.replace('_', ' ').title()} score is low: {score:.2f}"
                )
        return warnings
    
    def _generate_recommendations(
        self,
        dimension_scores: Dict[str, float],
        scope: str,
        scope_id: str,
        film_intelligence_influence: Optional[Dict[str, Any]] = None,
    ) -> List[StoryRecommendation]:
        """
        Generate recommendations for low-scoring dimensions.
        
        Phase 4.2: Placeholder implementation
        Phase 4.3: Will provide more specific recommendations
        """
        recommendations = []
        for dimension, score in dimension_scores.items():
            if score < 0.5:
                description = f"{dimension.replace('_', ' ').title()} needs attention"
                suggested_fix = None
                rationale = f"Score of {score:.2f} is below threshold"

                if film_intelligence_influence:
                    description, rationale, suggested_fix = self._enhance_recommendation_from_film_intelligence(
                        dimension=dimension,
                        base_description=description,
                        base_rationale=rationale,
                        film_intelligence_influence=film_intelligence_influence,
                    )

                recommendations.append(StoryRecommendation(
                    category=self._dimension_to_category(dimension),
                    priority=RevisionPriority.MEDIUM if score < 0.3 else RevisionPriority.LOW,
                    description=description,
                    target_scope=scope,
                    specific_scenes=[],  # Would be populated in Phase 4.3
                    rationale=rationale,
                    suggested_fix=suggested_fix
                ))
        return recommendations

    def _derive_film_intelligence_context(
        self,
        film_id: str,
        scope: str,
        scope_id: Optional[str],
        film_structure: Optional[FilmStructure],
        film_memory: Optional["FilmLevelMemory"],
        creative_spine: Optional["CreativeSpine"],
        act_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build a read-only derived film-intelligence context for scoring."""
        result: Dict[str, Any] = {
            "available": False,
            "scope": scope,
            "sequence": None,
            "act": None,
            "film": None,
            "debt_payoff_arc_summary": {
                "setup_payoff_count": 0,
                "open_tension_count": 0,
                "motif_count": 0,
                "arc_count": 0,
            },
            "canonical_sources": {
                "structure": film_structure is not None,
                "memory": film_memory is not None,
                "spine": creative_spine is not None,
            },
            "notes": [],
        }
        try:
            if film_structure is None and film_memory is None and creative_spine is None:
                result["notes"].append("No canonical film intelligence sources available")
                return result

            film_summary = film_intelligence_service.analyze_film(
                film_id=film_id,
                film_structure=film_structure,
                film_memory=film_memory,
                creative_spine=creative_spine,
            ).model_dump()
            result["film"] = film_summary
            result["available"] = True

            if scope == "sequence" and scope_id:
                result["sequence"] = film_intelligence_service.analyze_sequence(
                    film_id=film_id,
                    sequence_id=scope_id,
                    film_structure=film_structure,
                    film_memory=film_memory,
                    creative_spine=creative_spine,
                ).model_dump()
            elif scope == "act" and act_number is not None:
                result["act"] = film_intelligence_service.analyze_act(
                    film_id=film_id,
                    act_number=act_number,
                    film_structure=film_structure,
                    film_memory=film_memory,
                    creative_spine=creative_spine,
                ).model_dump()

            active = result["sequence"] or result["act"] or result["film"] or {}
            result["debt_payoff_arc_summary"] = {
                "setup_payoff_count": len(active.get("setup_payoff_summaries", []) or []),
                "open_tension_count": len(active.get("tension_summaries", []) or []),
                "motif_count": len(active.get("motif_summaries", []) or []),
                "arc_count": len(active.get("arc_progression_summaries", []) or []),
            }
        except Exception:
            result["notes"].append("Film intelligence unavailable")
        return result

    def _apply_film_intelligence_evidence(
        self,
        dimension_scores: Dict[str, float],
        analyzer_context: Dict[str, Any],
    ) -> (Dict[str, float], Dict[str, Any]):
        """Apply tiny bounded score nudges from derived film intelligence."""
        film_intelligence = analyzer_context.get("film_intelligence") or {}
        provenance: Dict[str, Any] = {
            "applied": False,
            "available": bool(film_intelligence.get("available")),
            "affected_dimensions": [],
            "adjustments": {},
            "support": {},
            "signal_strength": "sparse",
            "total_delta": 0.0,
        }
        if not film_intelligence.get("available"):
            return dimension_scores, provenance

        film_summary = film_intelligence.get("film") or {}
        active_summary = (
            film_intelligence.get("sequence")
            or film_intelligence.get("act")
            or film_summary
            or {}
        )
        debt_summary = film_intelligence.get("debt_payoff_arc_summary") or {}
        canonical_sources = film_intelligence.get("canonical_sources") or {}

        if canonical_sources.get("structure") and canonical_sources.get("memory"):
            provenance["signal_strength"] = "grounded"

        adjustments: Dict[str, float] = {}

        film_progression = film_summary.get("progression_status")
        if film_progression == "grounded_progression":
            adjustments["thesis_alignment"] = 0.02

        arc_summaries = active_summary.get("arc_progression_summaries") or []
        if any(isinstance(arc, dict) and arc.get("progression_status") == "tracked_across_scope" for arc in arc_summaries):
            adjustments["character_progression"] = 0.02

        motif_summaries = active_summary.get("motif_summaries") or []
        if any(isinstance(motif, dict) and motif.get("status") in {"recurred_in_scope", "payoff_or_callback_present"} for motif in motif_summaries):
            adjustments["motif_continuity"] = 0.02
        elif debt_summary.get("motif_count", 0) > 0 and motif_summaries:
            adjustments["motif_continuity"] = -0.015

        tension_summaries = active_summary.get("tension_summaries") or []
        if any(isinstance(tension, dict) and tension.get("status") == "overdue" for tension in tension_summaries):
            adjustments["tension_resolution_rate"] = -0.025
            adjustments["continuity_debt_trajectory"] = -0.02
        elif any(isinstance(tension, dict) and tension.get("status") == "open_film_level" for tension in tension_summaries):
            adjustments["tension_resolution_rate"] = -0.015

        emotional_summary = film_summary.get("emotional_trajectory_summary") or {}
        if emotional_summary.get("point_count", 0) >= 3 and emotional_summary.get("coverage_status") == "tracked":
            adjustments["emotional_trajectory"] = 0.02

        if debt_summary.get("open_tension_count", 0) >= 2:
            existing = adjustments.get("continuity_debt_trajectory", 0.0)
            adjustments["continuity_debt_trajectory"] = existing - 0.01

        # Clamp per-dimension and total movement.
        bounded_adjustments: Dict[str, float] = {}
        running_total = 0.0
        for dimension, delta in adjustments.items():
            bounded_delta = max(
                -self._max_film_intelligence_dimension_delta,
                min(self._max_film_intelligence_dimension_delta, delta),
            )
            proposed_total = running_total + bounded_delta
            if abs(proposed_total) > self._max_film_intelligence_total_delta:
                remaining = self._max_film_intelligence_total_delta - abs(running_total)
                if remaining <= 0:
                    continue
                bounded_delta = remaining if bounded_delta > 0 else -remaining
                proposed_total = running_total + bounded_delta
            bounded_adjustments[dimension] = round(bounded_delta, 4)
            running_total = round(proposed_total, 4)

        updated_scores = dict(dimension_scores)
        for dimension, delta in bounded_adjustments.items():
            updated_scores[dimension] = max(0.0, min(1.0, round(updated_scores.get(dimension, 0.5) + delta, 4)))

        if bounded_adjustments:
            provenance["applied"] = True
            provenance["affected_dimensions"] = sorted(bounded_adjustments.keys())
            provenance["adjustments"] = bounded_adjustments
            provenance["total_delta"] = round(sum(bounded_adjustments.values()), 4)
            provenance["support"] = {
                "scope": film_intelligence.get("scope"),
                "canonical_sources": canonical_sources,
                "debt_payoff_arc_summary": debt_summary,
                "film_progression_status": film_progression,
            }

        return updated_scores, provenance

    def _enhance_recommendation_from_film_intelligence(
        self,
        dimension: str,
        base_description: str,
        base_rationale: str,
        film_intelligence_influence: Dict[str, Any],
    ) -> (str, str, Optional[str]):
        """Improve recommendation specificity using bounded film-intelligence evidence."""
        support = film_intelligence_influence.get("support") or {}
        debt_summary = support.get("debt_payoff_arc_summary") or {}

        if dimension == "motif_continuity" and debt_summary.get("motif_count", 0) > 0:
            return (
                "Motif continuity needs attention - established motifs need a clearer callback or payoff",
                f"{base_rationale}; derived film intelligence shows {debt_summary.get('motif_count', 0)} tracked motif(s) without strong callback evidence at this scope.",
                "Strengthen an established motif with a clearer callback or payoff beat.",
            )
        if dimension == "tension_resolution_rate" and debt_summary.get("open_tension_count", 0) > 0:
            return (
                "Tension resolution needs attention - unresolved tension appears to be stagnating",
                f"{base_rationale}; derived film intelligence still tracks {debt_summary.get('open_tension_count', 0)} open tension(s).",
                "Advance or meaningfully complicate an unresolved tension instead of leaving it static.",
            )
        if dimension == "character_progression" and debt_summary.get("arc_count", 0) > 0:
            return (
                "Character progression needs attention - arc movement appears stalled",
                f"{base_rationale}; derived arc summaries indicate character movement is not paying off strongly enough at this scope.",
                "Add a beat that changes how the character behaves, chooses, or reveals pressure.",
            )
        if dimension == "thesis_alignment":
            return (
                "Thesis alignment needs attention - the current material may be drifting from the film's governing progression",
                f"{base_rationale}; full-film progression context is stronger than the current scope's alignment signal.",
                "Re-anchor the scene or section to the governing thesis through action, conflict, or payoff.",
            )
        if dimension == "emotional_trajectory":
            return (
                "Emotional trajectory needs attention - the film-scale emotional build may be flattening here",
                f"{base_rationale}; derived film trajectory data suggests the current scope needs a clearer emotional rise or turn.",
                "Sharpen the emotional turn so this section changes the audience's pressure state.",
            )
        if dimension == "continuity_debt_trajectory":
            return (
                "Continuity debt is accumulating - setup/payoff or tension obligations are drifting forward unresolved",
                f"{base_rationale}; derived film intelligence indicates accumulating setup/payoff or tension debt.",
                "Pay off, restate, or deliberately deepen an outstanding setup before the debt compounds.",
            )
        return base_description, base_rationale, None
    
    def _dimension_to_category(self, dimension: str) -> RecommendationCategory:
        """Map dimension name to recommendation category."""
        mapping = {
            "thesis_alignment": RecommendationCategory.THESIS_DRIFT,
            "tone_coherence": RecommendationCategory.TONE_SHIFT,
            "character_progression": RecommendationCategory.CHARACTER_STAGNATION,
            "emotional_trajectory": RecommendationCategory.EMOTIONAL_FLAT_SPOT,
            "motif_continuity": RecommendationCategory.MOTIF_MISSING_CALLBACK,
            "tension_resolution_rate": RecommendationCategory.TENSION_UNDERPAY,
            "originality_score": RecommendationCategory.FORMULA_RISK,
            "continuity_debt_trajectory": RecommendationCategory.DEBT_ACCUMULATION,
        }
        return mapping.get(dimension, RecommendationCategory.THESIS_DRIFT)
    
    def _get_sequence_scenes(
        self,
        sequence_id: str,
        context: StoryScoringContext
    ) -> List[str]:
        """Get list of scene IDs in a sequence."""
        if not context.film_structure:
            return []
        sequence = context.film_structure.get_sequence(sequence_id)
        if sequence:
            return getattr(sequence, "scenes", []) or getattr(sequence, "scene_ids", [])
        return []
    
    def _get_act_sequences(
        self,
        act_number: int,
        context: StoryScoringContext
    ) -> List[Dict[str, Any]]:
        """Get list of sequences in an act."""
        if not context.film_structure:
            return []
        act = context.film_structure.get_act(act_number)
        if act:
            return [
                {
                    "sequence_id": seq.sequence_id,
                    "scenes": getattr(seq, "scenes", []) or getattr(seq, "scene_ids", []),
                }
                for seq in act.sequences
            ]
        return []
    
    def _get_act_scene_ids(
        self,
        act_number: int,
        context: StoryScoringContext
    ) -> List[str]:
        """Get all scene IDs in an act."""
        sequences = self._get_act_sequences(act_number, context)
        scene_ids = []
        for seq in sequences:
            scene_ids.extend(seq.get("scenes", []))
        return scene_ids
    
    def _get_all_scene_ids(
        self,
        context: StoryScoringContext
    ) -> List[str]:
        """Get all scene IDs in the film."""
        if not context.film_structure:
            return []
        return [f"scene_{i}" for i in range(1, context.film_structure.total_scenes + 1)]


# Global instance for convenience
story_scoring_service = StoryLevelScoringService()
