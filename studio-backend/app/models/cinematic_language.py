"""
Cinematic Language Intelligence Models - Phase 8.1

Defines the data structures for cinematic language analysis.
These models are derived and advisory - they do NOT modify canonical state.

Usage:
    from app.models.cinematic_language import CinematicLanguageSignal, CinematicLanguageContext
    
    signal = CinematicLanguageSignal(
        scene_id="scene_1",
        film_id="film_123",
        ...
    )
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime


# =============================================================================
# Visual Intent Categories (heuristic output labels)
# =============================================================================

class VisualIntentCategory:
    """Categories for detected visual intent."""
    NARRATIVE = "narrative"      # Reveals/exposes story information
    EMOTIONAL = "emotional"      # Emphasizes/highlights emotional content
    THEMATIC = "thematic"        # Symbolizes/represents thematic content
    NONE_DETECTED = "none_detected"  # No clear visual intent detected


class FramingMeaning:
    """Framing semantics - what framing choices communicate."""
    DOMINANT = "dominant"        # Power/control position
    SUBMISSIVE = "submissive"    # Vulnerable/lower position
    ISOLATED = "isolated"        # Alone/separated
    CONNECTED = "connected"      # Together/relationship
    NEUTRAL = "neutral"          # No clear framing meaning


class MovementSignificance:
    """Camera movement significance."""
    STABILITY = "stability"      # Static/locked off - calm/resolved
    CHAOS = "chaos"              # Erratic/handheld - tension/disorder
    INTIMACY = "intimacy"        # Push in/dolly - intimacy/focus
    OBSERVATION = "observation"  # Slow pan/track - distance/clinical
    NONE = "none"                # No significant movement


class MotifEvolutionStage:
    """Stages of motif evolution in visuals."""
    INTRODUCTION = "introduction"    # First appearance of motif
    DEVELOPMENT = "development"      # Motif being developed/repeated
    REINFORCEMENT = "reinforcement"  # Motif reinforced/accumulating meaning
    PAYOFF = "payoff"                # Motif payoff/resolution
    NONE = "none"                    # No motif detected


# =============================================================================
# Analysis Method Labels
# =============================================================================

class AnalysisMethod:
    """Methods used for cinematic language analysis."""
    KEYWORD_MATCHING = "keyword_matching"
    PATTERN_ANYSIS = "pattern_analysis"
    COMBINED = "combined"
    PLACEHOLDER = "placeholder"  # Conservative fallback


# =============================================================================
# Core Signal Model
# =============================================================================

@dataclass
class CinematicLanguageSignal:
    """
    Advisory signal from Cinematic Language Intelligence.
    
    This is a READ-ONLY derived output. It does not modify any canonical state.
    All fields are labeled as grounded input observation or heuristic output.
    
    Heuristic outputs include confidence scores (0.0-1.0):
    - High confidence (0.8-1.0): Multiple strong markers found
    - Medium confidence (0.5-0.79): Some markers, interpretation plausible
    - Low confidence (0.0-0.49): Few/ambiguous markers, conservative
    
    Consumers should treat low-confidence signals as advisory only.
    """
    
    # === IDENTITY ===
    scene_id: str
    film_id: str
    
    # === GROUNDED INPUTS (what was observed from scene data) ===
    observed_visual_description: str = ""
    observed_camera_work: str = ""
    observed_lighting: str = ""
    observed_dialogue: str = ""
    observed_actions: str = ""
    
    # === HEURISTIC OUTPUTS (interpreted meaning) ===
    
    # Visual Intent
    visual_intent_category: str = VisualIntentCategory.NONE_DETECTED
    visual_intent_confidence: float = 0.5
    
    # Framing Semantics
    framing_meaning: str = FramingMeaning.NEUTRAL
    framing_confidence: float = 0.5
    
    # Camera Movement
    movement_significance: str = MovementSignificance.NONE
    movement_confidence: float = 0.5
    
    # Restraint
    restraint_score: float = 0.5  # 0.0 = over-directed, 1.0 = restrained
    restraint_indicators: List[str] = field(default_factory=list)
    
    # Dialogue Substitution
    dialogue_substitution_opportunity: float = 0.5  # 0.0 = not needed, 1.0 = strong opportunity
    substitution_indicators: List[str] = field(default_factory=list)
    
    # Motif Evolution
    motif_evolution_stage: str = MotifEvolutionStage.NONE
    motif_evolution_confidence: float = 0.5
    detected_motif_references: List[str] = field(default_factory=list)
    
    # === DEBUG METADATA ===
    analysis_method: str = AnalysisMethod.PLACEHOLDER
    timestamp: str = field(default="")
    
    def __post_init__(self):
        """Set default timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "observed_visual_description": self.observed_visual_description,
            "observed_camera_work": self.observed_camera_work,
            "observed_lighting": self.observed_lighting,
            "observed_dialogue": self.observed_dialogue,
            "observed_actions": self.observed_actions,
            "visual_intent_category": self.visual_intent_category,
            "visual_intent_confidence": self.visual_intent_confidence,
            "framing_meaning": self.framing_meaning,
            "framing_confidence": self.framing_confidence,
            "movement_significance": self.movement_significance,
            "movement_confidence": self.movement_confidence,
            "restraint_score": self.restraint_score,
            "restraint_indicators": self.restraint_indicators,
            "dialogue_substitution_opportunity": self.dialogue_substitution_opportunity,
            "substitution_indicators": self.substitution_indicators,
            "motif_evolution_stage": self.motif_evolution_stage,
            "motif_evolution_confidence": self.motif_evolution_confidence,
            "detected_motif_references": self.detected_motif_references,
            "analysis_method": self.analysis_method,
            "timestamp": self.timestamp,
        }
    
    def has_high_confidence_intent(self) -> bool:
        """Check if visual intent was detected with high confidence."""
        return (
            self.visual_intent_category != VisualIntentCategory.NONE_DETECTED
            and self.visual_intent_confidence >= 0.7
        )
    
    def is_restrained(self) -> bool:
        """Check if visual language appears restrained (score >= 0.6)."""
        return self.restraint_score >= 0.6
    
    def has_dialogue_substitution_opportunity(self) -> bool:
        """Check if there's a notable dialogue substitution opportunity (score >= 0.6)."""
        return self.dialogue_substitution_opportunity >= 0.6


# =============================================================================
# Context Model
# =============================================================================

@dataclass
class CinematicLanguageContext:
    """
    Context bundle for cinematic language analysis.
    
    This is a read-only pass-through that packages existing canonical data
    for the analyzer. No new truth is created here.
    
    All fields are optional to allow graceful degradation when
    full context is not available.
    """
    scene_data: Dict[str, Any] = field(default_factory=dict)
    film_memory: Optional[Any] = None  # FilmLevelMemory
    film_structure: Optional[Any] = None  # FilmStructure
    spine: Optional[Any] = None  # CreativeSpine
    
    def get_scene_id(self) -> str:
        """Extract scene_id from scene_data."""
        return self.scene_data.get("scene_id", "unknown")
    
    def get_film_id(self) -> str:
        """Extract film_id from scene_data or film_memory."""
        film_id = self.scene_data.get("film_id", "")
        if not film_id and self.film_memory:
            film_id = getattr(self.film_memory, "film_id", "")
        return film_id or "unknown"
    
    def get_visual_description(self) -> str:
        """Get visual_description from scene_data."""
        return str(self.scene_data.get("visual_description", ""))
    
    def get_camera_work(self) -> str:
        """Get camera_work from scene_data."""
        return str(self.scene_data.get("camera_work", ""))
    
    def get_lighting(self) -> str:
        """Get lighting from scene_data."""
        return str(self.scene_data.get("lighting", ""))
    
    def get_dialogue(self) -> str:
        """Get dialogue from scene_data."""
        return str(self.scene_data.get("dialogue", ""))
    
    def get_actions(self) -> str:
        """Get actions from scene_data."""
        return str(self.scene_data.get("actions", ""))
    
    def get_motifs(self) -> List[Any]:
        """Get motifs from film_memory if available."""
        if self.film_memory:
            return getattr(self.film_memory, "motifs", []) or []
        return []
    
    def get_film_themes(self) -> List[str]:
        """Get themes from film_memory or film_structure."""
        themes = []
        if self.film_memory:
            themes = getattr(self.film_memory, "themes", []) or []
        if not themes and self.film_structure:
            themes = getattr(self.film_structure, "themes", []) or []
        return themes
    
    def has_minimal_data(self) -> bool:
        """Check if minimal data is available for analysis."""
        visual_desc = self.get_visual_description()
        camera_work = self.get_camera_work()
        # At minimum, need some visual or camera data
        return bool(visual_desc or camera_work)