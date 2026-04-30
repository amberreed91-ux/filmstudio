"""
Tests for Cinematic Language Intelligence - Phase 8.2

Tests Phase 8.2 signal extraction:
- Real keyword matching analysis
- Conservative confidence scoring
- Sparse scenes return conservative defaults
- Strong visual intent scenes get different output than generic scenes
- Motif-aware scenes surface motif-related signals
- Backward compatibility preserved

Does NOT test (Phase 8.3+):
- Integration with DirectorEvaluator
- Scoring influence
- Runtime wiring
"""

import pytest
from typing import Dict, Any, Optional
from unittest.mock import Mock, MagicMock

from app.models.cinematic_language import (
    CinematicLanguageSignal,
    CinematicLanguageContext,
    VisualIntentCategory,
    FramingMeaning,
    MovementSignificance,
    MotifEvolutionStage,
    AnalysisMethod,
)
from app.services.cinematic_language_service import (
    CinematicLanguageAnalyzer,
    get_cinematic_language_analyzer,
    analyze_scene,
)


# =============================================================================
# Test: CinematicLanguageSignal Model Construction (Backward Compatibility)
# =============================================================================

class TestCinematicLanguageSignal:
    """Tests for CinematicLanguageSignal model - backward compatibility."""
    
    def test_signal_creation_with_required_fields(self):
        """Test signal can be created with only required fields."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
        )
        
        assert signal.scene_id == "scene_1"
        assert signal.film_id == "film_123"
        assert signal.timestamp  # Should be auto-generated
    
    def test_signal_creation_with_all_fields(self):
        """Test signal can be created with all fields specified."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            observed_visual_description="A wide shot of the city",
            observed_camera_work="Static frame",
            observed_lighting="Golden hour",
            observed_dialogue="Hello there",
            observed_actions="Character walks forward",
            visual_intent_category=VisualIntentCategory.NARRATIVE,
            visual_intent_confidence=0.8,
            framing_meaning=FramingMeaning.DOMINANT,
            framing_confidence=0.7,
            movement_significance=MovementSignificance.STABILITY,
            movement_confidence=0.6,
            restraint_score=0.75,
            restraint_indicators=["static frame", "minimal"],
            dialogue_substitution_opportunity=0.4,
            substitution_indicators=["visual description rich"],
            motif_evolution_stage=MotifEvolutionStage.DEVELOPMENT,
            motif_evolution_confidence=0.5,
            detected_motif_references=["motif_1", "motif_2"],
            analysis_method=AnalysisMethod.KEYWORD_MATCHING,
        )
        
        assert signal.scene_id == "scene_1"
        assert signal.film_id == "film_123"
        assert signal.visual_intent_category == VisualIntentCategory.NARRATIVE
        assert signal.visual_intent_confidence == 0.8
        assert signal.framing_meaning == FramingMeaning.DOMINANT
        assert signal.restraint_score == 0.75
        assert len(signal.restraint_indicators) == 2
        assert len(signal.detected_motif_references) == 2
    
    def test_signal_to_dict(self):
        """Test signal can be converted to dictionary."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            visual_intent_category=VisualIntentCategory.EMOTIONAL,
            visual_intent_confidence=0.75,
        )
        
        result = signal.to_dict()
        
        assert isinstance(result, dict)
        assert result["scene_id"] == "scene_1"
        assert result["film_id"] == "film_123"
        assert result["visual_intent_category"] == VisualIntentCategory.EMOTIONAL
        assert result["visual_intent_confidence"] == 0.75
    
    def test_signal_has_high_confidence_intent_true(self):
        """Test has_high_confidence_intent returns True when conditions met."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            visual_intent_category=VisualIntentCategory.NARRATIVE,
            visual_intent_confidence=0.8,
        )
        
        assert signal.has_high_confidence_intent() is True
    
    def test_signal_has_high_confidence_intent_false_low_confidence(self):
        """Test has_high_confidence_intent returns False with low confidence."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            visual_intent_category=VisualIntentCategory.NARRATIVE,
            visual_intent_confidence=0.5,
        )
        
        assert signal.has_high_confidence_intent() is False
    
    def test_signal_has_high_confidence_intent_false_none_detected(self):
        """Test has_high_confidence_intent returns False when none_detected."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            visual_intent_category=VisualIntentCategory.NONE_DETECTED,
            visual_intent_confidence=0.9,
        )
        
        assert signal.has_high_confidence_intent() is False
    
    def test_signal_is_restrained_true(self):
        """Test is_restrained returns True when score >= 0.6."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            restraint_score=0.7,
        )
        
        assert signal.is_restrained() is True
    
    def test_signal_is_restrained_false(self):
        """Test is_restrained returns False when score < 0.6."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            restraint_score=0.4,
        )
        
        assert signal.is_restrained() is False
    
    def test_signal_has_dialogue_substitution_opportunity_true(self):
        """Test has_dialogue_substitution_opportunity returns True when score >= 0.6."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            dialogue_substitution_opportunity=0.75,
        )
        
        assert signal.has_dialogue_substitution_opportunity() is True
    
    def test_signal_has_dialogue_substitution_opportunity_false(self):
        """Test has_dialogue_substitution_opportunity returns False when score < 0.6."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            dialogue_substitution_opportunity=0.3,
        )
        
        assert signal.has_dialogue_substitution_opportunity() is False


# =============================================================================
# Test: CinematicLanguageContext Model
# =============================================================================

class TestCinematicLanguageContext:
    """Tests for CinematicLanguageContext model."""
    
    def test_context_creation_empty(self):
        """Test context can be created with no arguments."""
        context = CinematicLanguageContext()
        
        assert context.scene_data == {}
        assert context.film_memory is None
        assert context.film_structure is None
        assert context.spine is None
    
    def test_context_creation_with_scene_data(self):
        """Test context can be created with scene_data."""
        scene_data = {
            "scene_id": "scene_1",
            "film_id": "film_123",
            "visual_description": "A dark forest",
            "camera_work": "Tracking shot",
        }
        context = CinematicLanguageContext(scene_data=scene_data)
        
        assert context.get_scene_id() == "scene_1"
        assert context.get_film_id() == "film_123"
        assert context.get_visual_description() == "A dark forest"
        assert context.get_camera_work() == "Tracking shot"
    
    def test_context_get_visual_description_empty(self):
        """Test get_visual_description returns empty string when not set."""
        context = CinematicLanguageContext()
        
        assert context.get_visual_description() == ""
    
    def test_context_get_camera_work_empty(self):
        """Test get_camera_work returns empty string when not set."""
        context = CinematicLanguageContext()
        
        assert context.get_camera_work() == ""
    
    def test_context_get_lighting_empty(self):
        """Test get_lighting returns empty string when not set."""
        context = CinematicLanguageContext()
        
        assert context.get_lighting() == ""
    
    def test_context_get_dialogue_empty(self):
        """Test get_dialogue returns empty string when not set."""
        context = CinematicLanguageContext()
        
        assert context.get_dialogue() == ""
    
    def test_context_get_actions_empty(self):
        """Test get_actions returns empty string when not set."""
        context = CinematicLanguageContext()
        
        assert context.get_actions() == ""
    
    def test_context_get_motifs_empty_list(self):
        """Test get_motifs returns empty list when no film_memory."""
        context = CinematicLanguageContext()
        
        assert context.get_motifs() == []
    
    def test_context_get_film_themes_empty_list(self):
        """Test get_film_themes returns empty list when no memory."""
        context = CinematicLanguageContext()
        
        assert context.get_film_themes() == []
    
    def test_context_has_minimal_data_false_empty(self):
        """Test has_minimal_data returns False when no data."""
        context = CinematicLanguageContext()
        
        assert context.has_minimal_data() is False
    
    def test_context_has_minimal_data_true_with_visual_description(self):
        """Test has_minimal_data returns True with visual_description."""
        context = CinematicLanguageContext(
            scene_data={"visual_description": "A dark forest"}
        )
        
        assert context.has_minimal_data() is True
    
    def test_context_has_minimal_data_true_with_camera_work(self):
        """Test has_minimal_data returns True with camera_work."""
        context = CinematicLanguageContext(
            scene_data={"camera_work": "Tracking shot"}
        )
        
        assert context.has_minimal_data() is True


# =============================================================================
# Test: CinematicLanguageAnalyzer Construction
# =============================================================================

class TestCinematicLanguageAnalyzer:
    """Tests for CinematicLanguageAnalyzer service."""
    
    def test_analyzer_instantiation(self):
        """Test analyzer can be instantiated."""
        analyzer = CinematicLanguageAnalyzer()
        
        assert analyzer is not None
    
    def test_get_cinematic_language_analyzer_singleton(self):
        """Test get_cinematic_language_analyzer returns singleton."""
        analyzer1 = get_cinematic_language_analyzer()
        analyzer2 = get_cinematic_language_analyzer()
        
        assert analyzer1 is analyzer2


# =============================================================================
# Test: Sparse Input Handling (Conservative Defaults)
# =============================================================================

class TestSparseInputHandling:
    """Tests for safe handling of sparse/minimal input."""
    
    def test_analyze_empty_scene_data(self):
        """Test analyze handles empty scene_data gracefully."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(scene_data={})
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.scene_id == "unknown"
        assert signal.film_id == "unknown"
        assert signal.observed_visual_description == ""
        assert signal.observed_camera_work == ""
        # Conservative defaults for sparse input
        assert signal.visual_intent_category == VisualIntentCategory.NONE_DETECTED
        assert signal.visual_intent_confidence == 0.5
        assert signal.framing_meaning == FramingMeaning.NEUTRAL
        assert signal.framing_confidence == 0.5
        assert signal.movement_significance == MovementSignificance.NONE
        assert signal.movement_confidence == 0.5
        assert signal.restraint_score == 0.5
        assert signal.restraint_indicators == []
    
    def test_analyze_minimal_scene_data(self):
        """Test analyze handles minimal scene_data (only scene_id)."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={"scene_id": "scene_1"}
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.scene_id == "scene_1"
        assert signal.film_id == "unknown"
        # Conservative defaults
        assert signal.visual_intent_category == VisualIntentCategory.NONE_DETECTED
        assert signal.visual_intent_confidence == 0.5
    
    def test_analyze_partial_scene_data(self):
        """Test analyze handles partial scene_data gracefully."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "film_id": "film_123",
                "visual_description": "A wide shot",
                # No camera_work, lighting, dialogue, actions
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.scene_id == "scene_1"
        assert signal.film_id == "film_123"
        assert signal.observed_visual_description == "A wide shot"
        assert signal.observed_camera_work == ""
        assert signal.observed_dialogue == ""
    
    def test_analyze_with_no_optional_context(self):
        """Test analyze handles missing optional context (film_memory, etc)."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={"scene_id": "scene_1", "visual_description": "Test"}
        )
        # film_memory, film_structure, spine all None
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.scene_id == "scene_1"
        assert signal.motif_evolution_stage == MotifEvolutionStage.NONE
        assert signal.detected_motif_references == []


# =============================================================================
# Test: Visual Intent Detection (Explicit Cues)
# =============================================================================

class TestVisualIntentDetection:
    """Tests for visual intent detection from explicit visual language cues."""
    
    def test_detects_narrative_intent(self):
        """Test detects narrative intent from explicit cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The camera reveals the hidden letter behind the book",
                "camera_work": "Slow push in to expose the secret"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.visual_intent_category == VisualIntentCategory.NARRATIVE
        assert signal.visual_intent_confidence > 0.5
        assert signal.analysis_method == AnalysisMethod.KEYWORD_MATCHING
    
    def test_detects_emotional_intent(self):
        """Test detects emotional intent from explicit cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The camera emphasizes her face, highlighting the emotional weight",
                "camera_work": "Slow dolly in, dwelling on the moment"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.visual_intent_category == VisualIntentCategory.EMOTIONAL
        assert signal.visual_intent_confidence > 0.5
    
    def test_detects_thematic_intent(self):
        """Test detects thematic intent from explicit cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The broken mirror symbolizes his fractured identity",
                "camera_work": "The composition mirrors the previous scene"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.visual_intent_category == VisualIntentCategory.THEMATIC
        assert signal.visual_intent_confidence > 0.5
    
    def test_no_intent_detected_for_generic_scene(self):
        """Test generic scene returns none_detected."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A room with a table and chairs",
                "camera_work": "Medium shot"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.visual_intent_category == VisualIntentCategory.NONE_DETECTED
        assert signal.visual_intent_confidence == 0.5
    
    def test_stronger_intent_higher_confidence(self):
        """Test stronger visual intent scenes get higher confidence."""
        analyzer = CinematicLanguageAnalyzer()
        
        # Weak intent
        context_weak = CinematicLanguageContext(
            scene_data={"scene_id": "scene_1", "visual_description": "reveals something"}
        )
        signal_weak = analyzer.analyze_scene(context_weak)
        
        # Strong intent (multiple markers)
        context_strong = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_2",
                "visual_description": "The camera reveals, exposes, and shows us the hidden evidence",
                "camera_work": "The framing exposes the truth"
            }
        )
        signal_strong = analyzer.analyze_scene(context_strong)
        
        assert signal_strong.visual_intent_confidence > signal_weak.visual_intent_confidence


# =============================================================================
# Test: Framing Semantics Detection
# =============================================================================

class TestFramingSemantics:
    """Tests for framing semantics detection."""
    
    def test_detects_dominant_framing(self):
        """Test detects dominant framing from power/control cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The camera looks down at the small figure from above",
                "camera_work": "High angle shot"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.framing_meaning == FramingMeaning.DOMINANT
        assert signal.framing_confidence > 0.5
    
    def test_detects_submissive_framing(self):
        """Test detects submissive framing from vulnerability cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "Looking up at the towering figure from below",
                "camera_work": "Low angle, the subject appears small and vulnerable"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.framing_meaning == FramingMeaning.SUBMISSIVE
        assert signal.framing_confidence > 0.5
    
    def test_detects_isolated_framing(self):
        """Test detects isolated framing from separation cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The character stands alone in the corner of the frame, separated from others",
                "camera_work": "Solitary figure, apart from the group"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.framing_meaning == FramingMeaning.ISOLATED
        assert signal.framing_confidence > 0.5
    
    def test_detects_connected_framing(self):
        """Test detects connected framing from relationship cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The couple stands together, shoulder to shoulder, facing each other",
                "camera_work": "Side by side, embracing"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.framing_meaning == FramingMeaning.CONNECTED
        assert signal.framing_confidence > 0.5
    
    def test_neutral_framing_for_generic_scene(self):
        """Test generic scene returns neutral framing."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A person walking down a street",
                "camera_work": "Medium shot"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.framing_meaning == FramingMeaning.NEUTRAL
        assert signal.framing_confidence == 0.5


# =============================================================================
# Test: Camera Movement Significance
# =============================================================================

class TestCameraMovementSignificance:
    """Tests for camera movement significance detection."""
    
    def test_detects_stability_significance(self):
        """Test detects stability from static/locked cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "camera_work": "Static frame, locked off, no movement"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.movement_significance == MovementSignificance.STABILITY
        assert signal.movement_confidence > 0.5
    
    def test_detects_chaos_significance(self):
        """Test detects chaos from erratic/handheld cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "camera_work": "Shaky handheld, erratic rapid pans, chaotic movement"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.movement_significance == MovementSignificance.CHAOS
        assert signal.movement_confidence > 0.5
    
    def test_detects_intimacy_significance(self):
        """Test detects intimacy from push-in/dolly cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "camera_work": "Slow dolly in, tracking toward the subject, push in"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.movement_significance == MovementSignificance.INTIMACY
        assert signal.movement_confidence > 0.5
    
    def test_detects_observation_significance(self):
        """Test detects observation from slow pan/wide cues."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "camera_work": "Slow pan across the landscape, establishing wide shot"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.movement_significance == MovementSignificance.OBSERVATION
        assert signal.movement_confidence > 0.5
    
    def test_no_movement_for_empty_camera_work(self):
        """Test empty camera work returns none."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A scene",
                # No camera_work
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.movement_significance == MovementSignificance.NONE
        assert signal.movement_confidence == 0.5


# =============================================================================
# Test: Restraint Scoring
# =============================================================================

class TestRestraintScoring:
    """Tests for restraint vs over-direction scoring."""
    
    def test_restrained_scene_high_score(self):
        """Test restrained scene gets high restraint score."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A single static frame, held for the full scene",
                "camera_work": "One take, no cutting, minimal"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.restraint_score > 0.5
        assert len(signal.restraint_indicators) > 0
    
    def test_over_directed_scene_low_score(self):
        """Test over-directed scene gets low restraint score."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "Constant coverage, multiple angles, rapid cutting",
                "camera_work": "Shot reverse shot, back and forth, fragmented"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.restraint_score < 0.5
        assert len(signal.restraint_indicators) > 0
    
    def test_generic_scene_neutral_score(self):
        """Test generic scene with no markers gets neutral score."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A room with furniture",
                "camera_work": "Standard shot"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.restraint_score == 0.5
        assert signal.restraint_indicators == []


# =============================================================================
# Test: Dialogue Substitution Opportunity
# =============================================================================

class TestDialogueSubstitutionOpportunity:
    """Tests for dialogue-to-visual substitution opportunity detection."""
    
    def test_wordless_scene_high_opportunity(self):
        """Test wordless scene with visual richness gets high opportunity."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "dialogue": "",
                "visual_description": "Wordless action, expressive movement, visual storytelling",
                "actions": "The character silently acts out the meaning"
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.dialogue_substitution_opportunity > 0.5
        assert len(signal.substitution_indicators) > 0
    
    def test_heavy_dialogue_low_opportunity(self):
        """Test heavy dialogue scene gets lower opportunity."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                # Use exact substring matches for negative markers
                "dialogue": "I explain everything. The narrator tells us the story.",
                "visual_description": "Two people talking",
                "actions": ""
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        # Should detect negative markers (explains, tells us)
        assert signal.dialogue_substitution_opportunity < 0.5
        assert len(signal.substitution_indicators) > 0
    
    def test_dialogue_heavy_visual_light_opportunity(self):
        """Test heavy dialogue with light visuals gets substitution opportunity."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                # Very long dialogue
                "dialogue": " " * 300,
                # Minimal visual description
                "visual_description": "Talk scene",
            }
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.dialogue_substitution_opportunity >= 0.6
        assert "dialogue_heavy_visual_light" in signal.substitution_indicators


# =============================================================================
# Test: Motif Evolution Tracking
# =============================================================================

class TestMotifEvolutionTracking:
    """Tests for motif evolution tracking."""
    
    def test_detects_motif_reference(self):
        """Test detects motif reference when visual description matches motif."""
        # Create mock motif
        mock_motif = Mock()
        mock_motif.motif_id = "red_door_1"
        mock_motif.name = "red door"
        
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "The red door creaks open slowly"
            },
            film_memory=Mock(motifs=[mock_motif])
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert "red_door_1" in signal.detected_motif_references
        assert signal.motif_evolution_stage == MotifEvolutionStage.DEVELOPMENT
        assert signal.motif_evolution_confidence > 0.5
    
    def test_no_motif_tracking_without_film_memory(self):
        """Test no motif tracking when film_memory not available."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A red door appears"
            }
            # No film_memory
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.motif_evolution_stage == MotifEvolutionStage.NONE
        assert signal.detected_motif_references == []
    
    def test_no_motif_tracking_when_no_match(self):
        """Test no motif tracking when visual description doesn't match motifs."""
        mock_motif = Mock()
        mock_motif.motif_id = "blue_window_1"
        mock_motif.name = "blue window"
        
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={
                "scene_id": "scene_1",
                "visual_description": "A red door appears"
            },
            film_memory=Mock(motifs=[mock_motif])
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.motif_evolution_stage == MotifEvolutionStage.NONE
        assert signal.detected_motif_references == []


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Tests for backward compatibility."""
    
    def test_analyze_scene_convenience_function(self):
        """Test analyze_scene convenience function works."""
        scene_data = {
            "scene_id": "scene_1",
            "film_id": "film_123",
            "visual_description": "A dark forest",
            "camera_work": "Tracking shot",
        }
        
        signal = analyze_scene(scene_data)
        
        assert signal.scene_id == "scene_1"
        assert signal.film_id == "film_123"
        assert signal.observed_visual_description == "A dark forest"
    
    def test_analyze_scene_with_optional_context(self):
        """Test analyze_scene convenience function with optional context."""
        scene_data = {
            "scene_id": "scene_1",
            "film_id": "film_123",
        }
        
        # Pass None for optional context - should not raise
        signal = analyze_scene(
            scene_data,
            film_memory=None,
            film_structure=None,
            spine=None,
        )
        
        assert signal.scene_id == "scene_1"
        assert signal.film_id == "film_123"
    
    def test_analysis_method_is_keyword_matching(self):
        """Test that Phase 8.2 uses keyword matching analysis method."""
        analyzer = CinematicLanguageAnalyzer()
        context = CinematicLanguageContext(
            scene_data={"scene_id": "scene_1", "visual_description": "Test"}
        )
        
        signal = analyzer.analyze_scene(context)
        
        assert signal.analysis_method == AnalysisMethod.KEYWORD_MATCHING


# =============================================================================
# Test: Signal Structure Validation
# =============================================================================

class TestSignalStructureValidation:
    """Tests for signal structure validation."""
    
    def test_signal_has_all_required_fields(self):
        """Test signal has all required fields."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
        )
        
        # Check all fields are present
        assert hasattr(signal, "scene_id")
        assert hasattr(signal, "film_id")
        assert hasattr(signal, "observed_visual_description")
        assert hasattr(signal, "observed_camera_work")
        assert hasattr(signal, "observed_lighting")
        assert hasattr(signal, "observed_dialogue")
        assert hasattr(signal, "observed_actions")
        assert hasattr(signal, "visual_intent_category")
        assert hasattr(signal, "visual_intent_confidence")
        assert hasattr(signal, "framing_meaning")
        assert hasattr(signal, "framing_confidence")
        assert hasattr(signal, "movement_significance")
        assert hasattr(signal, "movement_confidence")
        assert hasattr(signal, "restraint_score")
        assert hasattr(signal, "restraint_indicators")
        assert hasattr(signal, "dialogue_substitution_opportunity")
        assert hasattr(signal, "substitution_indicators")
        assert hasattr(signal, "motif_evolution_stage")
        assert hasattr(signal, "motif_evolution_confidence")
        assert hasattr(signal, "detected_motif_references")
        assert hasattr(signal, "analysis_method")
        assert hasattr(signal, "timestamp")
    
    def test_signal_confidence_values_bounded(self):
        """Test confidence values are in valid range."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            visual_intent_confidence=0.8,
            framing_confidence=0.7,
            movement_confidence=0.6,
            restraint_score=0.75,
            dialogue_substitution_opportunity=0.4,
            motif_evolution_confidence=0.5,
        )
        
        # All confidence/score values should be 0.0-1.0
        assert 0.0 <= signal.visual_intent_confidence <= 1.0
        assert 0.0 <= signal.framing_confidence <= 1.0
        assert 0.0 <= signal.movement_confidence <= 1.0
        assert 0.0 <= signal.restraint_score <= 1.0
        assert 0.0 <= signal.dialogue_substitution_opportunity <= 1.0
        assert 0.0 <= signal.motif_evolution_confidence <= 1.0
    
    def test_signal_indicator_fields_are_lists(self):
        """Test indicator fields are lists."""
        signal = CinematicLanguageSignal(
            scene_id="scene_1",
            film_id="film_123",
            restraint_indicators=["static frame", "minimal"],
            substitution_indicators=["rich visual description"],
            detected_motif_references=["motif_1"],
        )
        
        assert isinstance(signal.restraint_indicators, list)
        assert isinstance(signal.substitution_indicators, list)
        assert isinstance(signal.detected_motif_references, list)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])