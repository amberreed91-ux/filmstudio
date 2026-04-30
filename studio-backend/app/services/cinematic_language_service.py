"""
Cinematic Language Intelligence Service - Phase 8.2

Analyzes visual storytelling as meaning, not just style.
This is a READ-ONLY derived service. It reads existing canonical data
and produces interpretive signals. It does NOT:
- Modify FilmLevelMemory or FilmStructure
- Change scoring thresholds in DirectorEvaluator
- Introduce new canonical truth
- Override or bypass existing evaluators

Phase 8.2: Implements conservative signal extraction using keyword matching.
All analysis is grounded in explicit textual cues from scene data.

Usage:
    from app.services.cinematic_language_service import CinematicLanguageAnalyzer
    from app.models.cinematic_language import CinematicLanguageContext
    
    analyzer = CinematicLanguageAnalyzer()
    context = CinematicLanguageContext(
        scene_data=scene_data,
        film_memory=film_memory,
        film_structure=film_structure,
        spine=spine
    )
    signal = analyzer.analyze_scene(context)
"""

from typing import Dict, List, Optional, Any, Tuple
import logging

from app.models.cinematic_language import (
    CinematicLanguageSignal,
    CinematicLanguageContext,
    VisualIntentCategory,
    FramingMeaning,
    MovementSignificance,
    MotifEvolutionStage,
    AnalysisMethod,
)

logger = logging.getLogger("studio-cinematic-language")


class CinematicLanguageAnalyzer:
    """
    Analyzes visual storytelling as meaning, not just style.
    
    Phase 8.2: Implements conservative signal extraction using keyword matching.
    All analysis is grounded in explicit textual cues from scene data.
    
    This is a READ-ONLY derived service. All outputs are advisory only.
    """
    
    # =============================================================================
    # Keyword Dictionaries for Visual Intent Detection
    # =============================================================================
    
    VISUAL_INTENT_MARKERS = {
        VisualIntentCategory.NARRATIVE: [
            "reveals", "exposes", "uncovers", "shows us", "we see",
            "exposes", "discloses", "exhibits", "displays",
            "exposing", "revealing", "showing"
        ],
        VisualIntentCategory.EMOTIONAL: [
            "emphasizes", "highlights", "focuses on", "dwells on",
            "intimate", "emotional", "poignant", "heartfelt",
            "emphasizing", "highlighting", "focusing"
        ],
        VisualIntentCategory.THEMATIC: [
            "symbolizes", "represents", "embodies", "mirrors",
            "parallel", "contrast", "echoes", "reflects",
            "symbolizing", "representing", "embodying"
        ],
    }
    
    # =============================================================================
    # Keyword Dictionaries for Framing Semantics
    # =============================================================================
    
    FRAMING_MARKERS = {
        FramingMeaning.DOMINANT: [
            "above", "overlooking", "looking down", "higher angle",
            "dominates", "towers", "looms", "dominant frame",
            "from above", "bird's eye", "overhead"
        ],
        FramingMeaning.SUBMISSIVE: [
            "below", "looking up", "lower angle", "beneath",
            "vulnerable", "small", "diminished", "low angle",
            "from below", "worm's eye"
        ],
        FramingMeaning.ISOLATED: [
            "alone", "separated", "apart", "distant", "alone in frame",
            "isolated", "solitary", "secluded", "apart from others",
            "in the corner", "on the edge", "abandoned"
        ],
        FramingMeaning.CONNECTED: [
            "together", "facing each other", "alongside", "paired",
            "connected", "united", "side by side", "embracing",
            "kneeling together", "holding hands", "shoulder to shoulder"
        ],
    }
    
    # =============================================================================
    # Keyword Dictionaries for Camera Movement Significance
    # =============================================================================
    
    MOVEMENT_MARKERS = {
        MovementSignificance.STABILITY: [
            "static", "locked off", "still", "stationary",
            "no movement", "fixed frame", "locked", "hold",
            "one shot", "single take", "long take"
        ],
        MovementSignificance.CHAOS: [
            "shaky", "handheld", "erratic", "rapid pans",
            "chaotic", "frantic", "disorienting", "unsteady",
            "handheld camera", "shaking", "jerky"
        ],
        MovementSignificance.INTIMACY: [
            "dolly in", "tracking toward", "push in", "close",
            "crane down", "rising to", "approaching",
            "dolly", "tracking", "moving closer"
        ],
        MovementSignificance.OBSERVATION: [
            "slow pan", "slow track", "establishing", "wide",
            "pulling back", "dolly out", "tracking away",
            "wide shot", "establishing shot", "master shot"
        ],
    }
    
    # =============================================================================
    # Keyword Dictionaries for Restraint Scoring
    # =============================================================================
    
    RESTRAINT_POSITIVE_MARKERS = [
        "single shot", "one take", "static frame", "held",
        "without cutting", "long take", "minimal", "restrained",
        "simple frame", "unadorned", "quiet", "stillness",
        "patient", "disciplined", "no movement"
    ]
    
    RESTRAINT_NEGATIVE_MARKERS = [
        "constant", "every angle", "coverage", "shot reverse shot",
        "multiple angles", "rapid cutting", "excessive",
        "fragmented", "hyperactive", "busy", "overcut",
        "cut to", "cut back", "back and forth"
    ]
    
    # =============================================================================
    # Keyword Dictionaries for Dialogue Substitution Opportunity
    # =============================================================================
    
    SUBSTITUTION_POSITIVE_MARKERS = [
        "silence", "wordless", "no dialogue", "without words",
        "visual storytelling", "actions speak", "show don't tell",
        "meaningful action", "expressive movement", "gesture",
        "visual reveal", "visual punchline", "visual payoff"
    ]
    
    SUBSTITUTION_NEGATIVE_MARKERS = [
        "explains", "tells us", "informs us", "says aloud",
        "narrates", "voiceover", "voice over", "explaining",
        "on the nose", "states", "declares"
    ]
    
    def __init__(self):
        """Initialize the Cinematic Language Analyzer."""
        pass
    
    def analyze_scene(self, context: CinematicLanguageContext) -> CinematicLanguageSignal:
        """
        Perform cinematic language analysis on scene data.
        
        Phase 8.2: Implements conservative signal extraction using keyword matching.
        All analysis is grounded in explicit textual cues from scene data.
        
        Args:
            context: CinematicLanguageContext with scene_data and optional 
                    film_memory, film_structure, spine
            
        Returns:
            CinematicLanguageSignal with heuristic outputs
        """
        scene_id = context.get_scene_id()
        film_id = context.get_film_id()
        
        # Extract grounded inputs from context
        visual_description = context.get_visual_description()
        camera_work = context.get_camera_work()
        lighting = context.get_lighting()
        dialogue = context.get_dialogue()
        actions = context.get_actions()
        
        # Phase 8.2: Real keyword matching analysis
        
        # Detect visual intent
        visual_intent_category, visual_intent_confidence = self._detect_visual_intent(
            visual_description, camera_work
        )
        
        # Detect framing meaning
        framing_meaning, framing_confidence = self._detect_framing_meaning(
            visual_description, camera_work
        )
        
        # Detect movement significance
        movement_significance, movement_confidence = self._detect_movement_significance(
            camera_work
        )
        
        # Score restraint
        restraint_score, restraint_indicators = self._score_restraint(
            visual_description, camera_work
        )
        
        # Detect dialogue substitution opportunity
        dialogue_substitution_opportunity, substitution_indicators = self._detect_dialogue_substitution_opportunity(
            dialogue, visual_description, actions
        )
        
        # Track motif evolution
        motif_evolution_stage, motif_evolution_confidence, detected_motif_references = self._track_motif_evolution(
            visual_description, context.get_motifs()
        )
        
        return CinematicLanguageSignal(
            scene_id=scene_id,
            film_id=film_id,
            observed_visual_description=visual_description,
            observed_camera_work=camera_work,
            observed_lighting=lighting,
            observed_dialogue=dialogue,
            observed_actions=actions,
            visual_intent_category=visual_intent_category,
            visual_intent_confidence=visual_intent_confidence,
            framing_meaning=framing_meaning,
            framing_confidence=framing_confidence,
            movement_significance=movement_significance,
            movement_confidence=movement_confidence,
            restraint_score=restraint_score,
            restraint_indicators=restraint_indicators,
            dialogue_substitution_opportunity=dialogue_substitution_opportunity,
            substitution_indicators=substitution_indicators,
            motif_evolution_stage=motif_evolution_stage,
            motif_evolution_confidence=motif_evolution_confidence,
            detected_motif_references=detected_motif_references,
            analysis_method=AnalysisMethod.KEYWORD_MATCHING,
        )
    
    def _detect_visual_intent(
        self, 
        visual_description: str, 
        camera_work: str
    ) -> Tuple[str, float]:
        """
        Detect visual intent category from visual_description and camera_work.
        
        Uses explicit keyword matching on textual cues.
        Returns conservative fallback if no clear markers found.
        
        Returns:
            Tuple of (category, confidence)
        """
        if not visual_description and not camera_work:
            return (VisualIntentCategory.NONE_DETECTED, 0.5)
        
        combined_text = f"{visual_description} {camera_work}".lower()
        
        # Count matches for each category
        category_scores: Dict[str, float] = {}
        category_matches: Dict[str, List[str]] = {}
        
        for category, markers in self.VISUAL_INTENT_MARKERS.items():
            matches = [m for m in markers if m in combined_text]
            if matches:
                # Confidence based on number of matches (capped at 0.85)
                confidence = min(0.5 + (len(matches) * 0.15), 0.85)
                category_scores[category] = confidence
                category_matches[category] = matches
        
        if not category_scores:
            return (VisualIntentCategory.NONE_DETECTED, 0.5)
        
        # Return highest scoring category
        best_category = max(category_scores, key=category_scores.get)
        best_confidence = category_scores[best_category]
        
        return (best_category, best_confidence)
    
    def _detect_framing_meaning(
        self, 
        visual_description: str, 
        camera_work: str
    ) -> Tuple[str, float]:
        """
        Detect framing semantics (power, isolation, relationship).
        
        Uses explicit keyword matching on textual cues.
        Returns conservative fallback if no clear markers found.
        
        Returns:
            Tuple of (meaning, confidence)
        """
        if not visual_description and not camera_work:
            return (FramingMeaning.NEUTRAL, 0.5)
        
        combined_text = f"{visual_description} {camera_work}".lower()
        
        # Count matches for each meaning
        meaning_scores: Dict[str, float] = {}
        meaning_matches: Dict[str, List[str]] = {}
        
        for meaning, markers in self.FRAMING_MARKERS.items():
            matches = [m for m in markers if m in combined_text]
            if matches:
                # Confidence based on number of matches (capped at 0.8)
                confidence = min(0.5 + (len(matches) * 0.1), 0.8)
                meaning_scores[meaning] = confidence
                meaning_matches[meaning] = matches
        
        if not meaning_scores:
            return (FramingMeaning.NEUTRAL, 0.5)
        
        # Return highest scoring meaning
        best_meaning = max(meaning_scores, key=meaning_scores.get)
        best_confidence = meaning_scores[best_meaning]
        
        return (best_meaning, best_confidence)
    
    def _detect_movement_significance(
        self, 
        camera_work: str
    ) -> Tuple[str, float]:
        """
        Detect camera movement vs. stillness meaning.
        
        Uses explicit keyword matching on textual cues.
        Returns conservative fallback if no clear markers found.
        
        Returns:
            Tuple of (significance, confidence)
        """
        if not camera_work:
            return (MovementSignificance.NONE, 0.5)
        
        camera_work_lower = camera_work.lower()
        
        # Count matches for each significance
        significance_scores: Dict[str, float] = {}
        
        for significance, markers in self.MOVEMENT_MARKERS.items():
            matches = [m for m in markers if m in camera_work_lower]
            if matches:
                # Confidence based on number of matches (capped at 0.8)
                confidence = min(0.5 + (len(matches) * 0.1), 0.8)
                significance_scores[significance] = confidence
        
        if not significance_scores:
            return (MovementSignificance.NONE, 0.5)
        
        # Return highest scoring significance
        best_significance = max(significance_scores, key=significance_scores.get)
        best_confidence = significance_scores[best_significance]
        
        return (best_significance, best_confidence)
    
    def _score_restraint(
        self, 
        visual_description: str, 
        camera_work: str
    ) -> Tuple[float, List[str]]:
        """
        Score visual restraint vs. over-direction.
        
        Uses marker counting: positive markers increase score,
        negative markers decrease score. Returns 0.5 if no markers found.
        
        Returns:
            Tuple of (score 0.0-1.0, list of indicators found)
        """
        if not visual_description and not camera_work:
            return (0.5, [])
        
        combined_text = f"{visual_description} {camera_work}".lower()
        
        positive_matches = [m for m in self.RESTRAINT_POSITIVE_MARKERS if m in combined_text]
        negative_matches = [m for m in self.RESTRAINT_NEGATIVE_MARKERS if m in combined_text]
        
        all_indicators = positive_matches + negative_matches
        
        if not all_indicators:
            return (0.5, [])
        
        # Score calculation: start at 0.5, add 0.1 per positive, subtract 0.1 per negative
        # Clamp to 0.0-1.0
        score = 0.5 + (len(positive_matches) * 0.1) - (len(negative_matches) * 0.1)
        score = max(0.0, min(1.0, score))
        
        return (round(score, 2), all_indicators)
    
    def _detect_dialogue_substitution_opportunity(
        self, 
        dialogue: str, 
        visual_description: str, 
        actions: str
    ) -> Tuple[float, List[str]]:
        """
        Detect if visual storytelling could replace dialogue.
        
        Uses explicit keyword matching and ratio analysis.
        High dialogue + rich visual description = potential substitution opportunity.
        
        Returns:
            Tuple of (opportunity score 0.0-1.0, list of indicators found)
        """
        if not dialogue and not visual_description:
            return (0.5, [])
        
        combined_text = f"{visual_description} {actions}".lower()
        dialogue_lower = dialogue.lower()
        
        positive_matches = [m for m in self.SUBSTITUTION_POSITIVE_MARKERS if m in combined_text]
        negative_matches = [m for m in self.SUBSTITUTION_NEGATIVE_MARKERS if m in dialogue_lower]
        
        all_indicators = positive_matches + negative_matches
        
        # Base score calculation
        if not all_indicators:
            # No explicit markers - use ratio heuristic
            # High dialogue length relative to visual description suggests substitution opportunity
            dialogue_len = len(dialogue)
            visual_len = len(visual_description)
            
            if dialogue_len > 200 and visual_len < 50:
                # Heavy dialogue, minimal visual description
                return (0.6, ["dialogue_heavy_visual_light"])
            elif dialogue_len > 400 and visual_len < 100:
                # Very heavy dialogue, very minimal visuals
                return (0.7, ["very_dialogue_heavy"])
            else:
                return (0.5, [])
        
        # Score based on explicit markers
        # Positive matches (visual storytelling markers) increase opportunity
        # Negative matches (exposition markers) decrease opportunity
        score = 0.5 + (len(positive_matches) * 0.15) - (len(negative_matches) * 0.15)
        score = max(0.0, min(1.0, score))
        
        return (round(score, 2), all_indicators)
    
    def _track_motif_evolution(
        self, 
        visual_description: str, 
        motifs: List[Any]
    ) -> Tuple[str, float, List[str]]:
        """
        Track how visual motifs evolve across the film.
        
        Cross-references visual_description with film_memory.motifs.
        Returns conservative fallback if no motifs available or no matches.
        
        Returns:
            Tuple of (stage, confidence, list of detected motif_ids)
        """
        if not motifs:
            return (MotifEvolutionStage.NONE, 0.5, [])
        
        if not visual_description:
            return (MotifEvolutionStage.NONE, 0.5, [])
        
        visual_lower = visual_description.lower()
        detected_motif_ids: List[str] = []
        
        for motif in motifs:
            # Get motif name and check for matches in visual description
            motif_name = getattr(motif, "name", "") or ""
            motif_id = getattr(motif, "motif_id", "") or ""
            
            if motif_name and motif_name.lower() in visual_lower:
                detected_motif_ids.append(motif_id)
        
        if not detected_motif_ids:
            return (MotifEvolutionStage.NONE, 0.5, [])
        
        # For now, if we detect a motif reference, mark as development stage
        # Later phases could track recurrence count to determine evolution stage
        # Conservative: return development with medium confidence
        return (MotifEvolutionStage.DEVELOPMENT, 0.6, detected_motif_ids)


# =============================================================================
# Module-level singleton for convenience
# =============================================================================

# Lazy-initialized singleton instance
_cinematic_language_analyzer: Optional[CinematicLanguageAnalyzer] = None


def get_cinematic_language_analyzer() -> CinematicLanguageAnalyzer:
    """
    Get the singleton CinematicLanguageAnalyzer instance.
    
    Returns:
        CinematicLanguageAnalyzer instance
    """
    global _cinematic_language_analyzer
    if _cinematic_language_analyzer is None:
        _cinematic_language_analyzer = CinematicLanguageAnalyzer()
    return _cinematic_language_analyzer


def analyze_scene(
    scene_data: Dict[str, Any],
    film_memory: Optional[Any] = None,
    film_structure: Optional[Any] = None,
    spine: Optional[Any] = None,
) -> CinematicLanguageSignal:
    """
    Convenience function to analyze a scene.
    
    Creates context from provided data and runs analysis.
    
    Args:
        scene_data: Scene data dict with visual_description, camera_work, etc.
        film_memory: Optional FilmLevelMemory instance
        film_structure: Optional FilmStructure instance
        spine: Optional CreativeSpine instance
        
    Returns:
        CinematicLanguageSignal with analysis results
    """
    context = CinematicLanguageContext(
        scene_data=scene_data,
        film_memory=film_memory,
        film_structure=film_structure,
        spine=spine,
    )
    analyzer = get_cinematic_language_analyzer()
    return analyzer.analyze_scene(context)