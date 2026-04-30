"""
Tests for StoryLevelScoringService - Phase 4.2

Tests the service shell with scaffolded dimension analyzers.
Full analyzer logic will be tested in Phase 4.3.

Run with: python -m pytest app/services/test_story_scoring_service.py -v
"""

import sys

from app.services.story_scoring_service import (
    StoryLevelScoringService,
    StoryScoringContext,
    BaseDimensionAnalyzer,
    ThesisAlignmentAnalyzer,
    ToneCoherenceAnalyzer,
    CharacterProgressionAnalyzer,
    EmotionalTrajectoryAnalyzer,
    MotifContinuityAnalyzer,
    TensionResolutionAnalyzer,
    OriginalityAnalyzer,
    ContinuityDebtTrajectoryAnalyzer,
    story_scoring_service,
)
from app.models.crew import (
    StoryScore,
    StoryRecommendation,
    RecommendationCategory,
    RevisionPriority,
    FilmStructure,
    Act,
    ActType,
    Sequence,
)
from app.models.memory import FilmLevelMemory, MotifRecord, UnresolvedTension, EmotionalTrajectoryPoint
from app.models.spine import CreativeSpine


# =============================================================================
# Test: Service Construction
# =============================================================================

def test_service_creation():
    """Test that StoryLevelScoringService can be instantiated."""
    service = StoryLevelScoringService()
    assert service is not None
    assert hasattr(service, '_analyzers')
    assert hasattr(service, '_default_weights')


def test_global_instance_exists():
    """Test that the global story_scoring_service instance exists."""
    assert story_scoring_service is not None
    assert isinstance(story_scoring_service, StoryLevelScoringService)


def test_all_eight_analyzers_registered():
    """Test that all 8 dimension analyzers are registered."""
    service = StoryLevelScoringService()
    expected_analyzers = [
        "thesis_alignment",
        "tone_coherence",
        "character_progression",
        "emotional_trajectory",
        "motif_continuity",
        "tension_resolution_rate",
        "originality_score",
        "continuity_debt_trajectory",
    ]
    for analyzer_name in expected_analyzers:
        assert analyzer_name in service._analyzers, f"Missing analyzer: {analyzer_name}"


def test_default_weights_sum_to_one():
    """Test that default weights sum to 1.0."""
    service = StoryLevelScoringService()
    total_weight = sum(service._default_weights.values())
    assert abs(total_weight - 1.0) < 0.001, f"Weights sum to {total_weight}, expected 1.0"


def test_analyzers_are_base_dimension_analyzer_instances():
    """Test that all registered analyzers inherit from BaseDimensionAnalyzer."""
    service = StoryLevelScoringService()
    for name, analyzer in service._analyzers.items():
        assert isinstance(analyzer, BaseDimensionAnalyzer), f"{name} is not a BaseDimensionAnalyzer"


# =============================================================================
# Test: Scoring Method Return Types
# =============================================================================

def test_score_scene_returns_story_score():
    """Test that score_scene returns a StoryScore."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test scene"},
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.film_id == "test_film"
    assert score.scope == "scene"
    assert score.scope_id == "scene_1"


def test_score_sequence_returns_story_score():
    """Test that score_sequence returns a StoryScore."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_sequence(
        film_id="test_film",
        sequence_id="sequence_1",
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.film_id == "test_film"
    assert score.scope == "sequence"
    assert score.scope_id == "sequence_1"


def test_score_act_returns_story_score():
    """Test that score_act returns a StoryScore."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_act(
        film_id="test_film",
        act_number=1,
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.film_id == "test_film"
    assert score.scope == "act"
    assert score.scope_id == "act_1"


def test_score_film_returns_story_score():
    """Test that score_film returns a StoryScore."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_film(
        film_id="test_film",
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.film_id == "test_film"
    assert score.scope == "film"
    assert score.scope_id is None


# =============================================================================
# Test: Safe Handling of Missing or Partial Inputs
# =============================================================================

def test_score_scene_with_minimal_context():
    """Test that score_scene works with minimal context (no film structure, no memory)."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    # Should not raise an exception
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.film_id == "test_film"


def test_score_scene_with_none_scene_data():
    """Test that score_scene handles None scene_data gracefully."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    # Should not raise an exception
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data=None,
        context=context
    )
    
    assert isinstance(score, StoryScore)


def test_score_sequence_with_no_film_structure():
    """Test that score_sequence handles missing film structure."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film", film_structure=None)
    
    score = service.score_sequence(
        film_id="test_film",
        sequence_id="sequence_1",
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.scene_count == 0  # No structure = no scenes


def test_score_act_with_no_film_structure():
    """Test that score_act handles missing film structure."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film", film_structure=None)
    
    score = service.score_act(
        film_id="test_film",
        act_number=1,
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.sequence_count == 0


def test_score_film_with_no_film_structure():
    """Test that score_film handles missing film structure."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film", film_structure=None)
    
    score = service.score_film(
        film_id="test_film",
        context=context
    )
    
    assert isinstance(score, StoryScore)
    assert score.scene_count == 0
    assert score.act_count == 0


def test_score_scene_with_all_optional_fields_none():
    """Test that score_scene handles all optional fields as None."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(
        film_id="test_film",
        film_structure=None,
        film_memory=None,
        act_memory=None,
        sequence_memory=None,
        creative_spine=None,
        continuity_tracker=None,
        spine_consumption=None,
        scene_id=None,
        scene_data=None,
        director_decision=None,
        scene_decisions=[]
    )
    
    # Should not raise an exception
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert isinstance(score, StoryScore)


# =============================================================================
# Test: Placeholder Analyzer Behavior (Phase 4.2)
# =============================================================================

def test_base_analyzer_returns_placeholder():
    """Test that BaseDimensionAnalyzer returns 0.5 placeholder."""
    analyzer = BaseDimensionAnalyzer()
    result = analyzer.analyze({})
    assert result == 0.5


def test_all_analyzers_return_placeholder_0_5():
    """Test that all dimension analyzers return 0.5 (placeholder)."""
    service = StoryLevelScoringService()
    context = {}
    
    for name, analyzer in service._analyzers.items():
        result = analyzer.analyze(context)
        assert result == 0.5, f"{name} returned {result}, expected 0.5"


def test_overall_health_with_all_placeholders():
    """Test that overall_health is 0.5 when all dimensions are 0.5."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    # All analyzers return 0.5, weighted average should be 0.5
    assert score.overall_health == 0.5


def test_revision_priority_with_all_placeholders():
    """Test revision priority with all 0.5 scores (should be MEDIUM)."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    # 0.5 is between 0.3 and 0.7, so priority should be MEDIUM
    assert score.revision_priority == RevisionPriority.MEDIUM


def test_no_warnings_with_placeholder_scores():
    """Test that there are no warnings when all scores are 0.5 (threshold is < 0.5)."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    # 0.5 is not < 0.5, so no warnings
    assert len(score.warnings) == 0


def test_no_recommendations_with_placeholder_scores():
    """Test that there are no recommendations when all scores are 0.5 (threshold is < 0.5)."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    # 0.5 is not < 0.5, so no recommendations
    assert len(score.recommendations) == 0


# =============================================================================
# Test: Dimension Score Structure
# =============================================================================

def test_all_dimension_scores_present():
    """Test that all 8 dimension scores are present in StoryScore."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    expected_dimensions = [
        "thesis_alignment",
        "tone_coherence",
        "character_progression",
        "emotional_trajectory",
        "motif_continuity",
        "tension_resolution_rate",
        "originality_score",
        "continuity_debt_trajectory",
    ]
    
    for dim in expected_dimensions:
        assert hasattr(score, dim), f"Missing dimension: {dim}"
        assert isinstance(getattr(score, dim), float), f"{dim} is not a float"


def test_dimension_weights_preserved():
    """Test that dimension weights are preserved in the score."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.dimension_weights is not None
    assert isinstance(score.dimension_weights, dict)
    assert len(score.dimension_weights) == 8


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_story_scoring_context_has_required_fields():
    """Test that StoryScoringContext has all required fields with defaults."""
    context = StoryScoringContext(film_id="test_film")
    
    assert context.film_id == "test_film"
    assert context.film_structure is None
    assert context.film_memory is None
    assert context.scene_decisions == []


def test_story_scoring_context_scene_decisions_default():
    """Test that scene_decisions defaults to empty list."""
    context = StoryScoringContext(film_id="test_film")
    assert context.scene_decisions == []
    assert isinstance(context.scene_decisions, list)


def test_story_score_has_required_fields():
    """Test that StoryScore has all required fields."""
    score = StoryScore(film_id="test_film", scope="scene")
    
    assert score.film_id == "test_film"
    assert score.scope == "scene"
    assert score.scope_id is None


def test_story_recommendation_creation():
    """Test that StoryRecommendation can be created."""
    recommendation = StoryRecommendation(
        category=RecommendationCategory.THESIS_DRIFT,
        priority=RevisionPriority.MEDIUM,
        description="Test recommendation",
        target_scope="scene",
        specific_scenes=["scene_1"],
        rationale="Test rationale"
    )
    
    assert recommendation.category == RecommendationCategory.THESIS_DRIFT
    assert recommendation.priority == RevisionPriority.MEDIUM


def test_revision_priority_enum_values():
    """Test RevisionPriority enum has expected values."""
    assert RevisionPriority.LOW.value == "low"
    assert RevisionPriority.MEDIUM.value == "medium"
    assert RevisionPriority.HIGH.value == "high"
    assert RevisionPriority.CRITICAL.value == "critical"


def test_recommendation_category_enum_values():
    """Test RecommendationCategory enum has expected values."""
    assert RecommendationCategory.THESIS_DRIFT.value == "thesis_drift"
    assert RecommendationCategory.TONE_SHIFT.value == "tone_shift"
    assert RecommendationCategory.CHARACTER_STAGNATION.value == "character_stagnation"
    assert RecommendationCategory.EMOTIONAL_FLAT_SPOT.value == "emotional_flat_spot"
    assert RecommendationCategory.MOTIF_MISSING_CALLBACK.value == "motif_missing_callback"
    assert RecommendationCategory.TENSION_UNDERPAY.value == "tension_underpay"
    assert RecommendationCategory.FORMULA_RISK.value == "formula_risk"
    assert RecommendationCategory.DEBT_ACCUMULATION.value == "debt_accumulation"


# =============================================================================
# Test: Timestamp and Metadata
# =============================================================================

def test_score_has_timestamp():
    """Test that StoryScore has a timestamp."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.timestamp is not None
    assert isinstance(score.timestamp, str)


def test_score_based_on_scenes_list():
    """Test that based_on_scenes is populated correctly."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.based_on_scenes is not None
    assert isinstance(score.based_on_scenes, list)
    assert "scene_1" in score.based_on_scenes


# =============================================================================
# Test: Exception Safety
# =============================================================================

def test_analyzer_exception_caught_safely():
    """Test that analyzer exceptions are caught and don't break scoring."""
    
    class FailingAnalyzer(BaseDimensionAnalyzer):
        def analyze(self, context):
            raise ValueError("Intentional test failure")
    
    service = StoryLevelScoringService()
    service._analyzers["thesis_alignment"] = FailingAnalyzer()
    
    context = StoryScoringContext(film_id="test_film")
    
    # Should not raise - exception should be caught
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    # The failing analyzer should have returned 0.5 as fallback
    assert score.thesis_alignment == 0.5


# =============================================================================
# Test: Scope-Specific Behavior
# =============================================================================

def test_scene_score_scope_fields():
    """Test that scene scoring populates scope-specific fields correctly."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_5",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.scope == "scene"
    assert score.scope_id == "scene_5"
    assert score.based_on_scenes == ["scene_5"]


def test_sequence_score_scope_fields():
    """Test that sequence scoring populates scope-specific fields correctly."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_sequence(
        film_id="test_film",
        sequence_id="seq_2",
        context=context
    )
    
    assert score.scope == "sequence"
    assert score.scope_id == "seq_2"


def test_act_score_scope_fields():
    """Test that act scoring populates scope-specific fields correctly."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_act(
        film_id="test_film",
        act_number=2,
        context=context
    )
    
    assert score.scope == "act"
    assert score.scope_id == "act_2"


def test_film_score_scope_fields():
    """Test that film scoring populates scope-specific fields correctly."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_film(
        film_id="test_film",
        context=context
    )
    
    assert score.scope == "film"
    assert score.scope_id is None


# =============================================================================
# Test: Priority Determination Thresholds
# =============================================================================

def test_priority_critical_for_very_low_scores():
    """Test that CRITICAL priority is assigned when min score < 0.3."""
    service = StoryLevelScoringService()
    
    # Override one analyzer to return very low score
    class VeryLowAnalyzer(BaseDimensionAnalyzer):
        def analyze(self, context):
            return 0.2
    
    service._analyzers["thesis_alignment"] = VeryLowAnalyzer()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.revision_priority == RevisionPriority.CRITICAL


def test_priority_high_for_low_scores():
    """Test that HIGH priority is assigned when min score is between 0.3 and 0.5."""
    service = StoryLevelScoringService()
    
    # Override one analyzer to return low score
    class LowAnalyzer(BaseDimensionAnalyzer):
        def analyze(self, context):
            return 0.4
    
    service._analyzers["thesis_alignment"] = LowAnalyzer()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.revision_priority == RevisionPriority.HIGH


def test_priority_medium_for_moderate_scores():
    """Test that MEDIUM priority is assigned when min score is between 0.5 and 0.7."""
    service = StoryLevelScoringService()
    
    # All return 0.5 (default)
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.revision_priority == RevisionPriority.MEDIUM


def test_priority_low_for_good_scores():
    """Test that LOW priority is assigned when all scores >= 0.7."""
    service = StoryLevelScoringService()
    
    # Override all analyzers to return high scores
    class HighAnalyzer(BaseDimensionAnalyzer):
        def analyze(self, context):
            return 0.8
    
    for key in service._analyzers:
        service._analyzers[key] = HighAnalyzer()
    
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert score.revision_priority == RevisionPriority.LOW


# =============================================================================
# Test: Warning Generation
# =============================================================================

def test_warnings_generated_for_low_scores():
    """Test that warnings are generated for scores below 0.5."""
    service = StoryLevelScoringService()
    
    # Override one analyzer to return low score
    class LowAnalyzer(BaseDimensionAnalyzer):
        def analyze(self, context):
            return 0.3
    
    service._analyzers["thesis_alignment"] = LowAnalyzer()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert len(score.warnings) > 0
    assert any("thesis alignment" in w.lower() for w in score.warnings)


def test_recommendations_generated_for_low_scores():
    """Test that recommendations are generated for scores below 0.5."""
    service = StoryLevelScoringService()
    
    # Override one analyzer to return low score
    class LowAnalyzer(BaseDimensionAnalyzer):
        def analyze(self, context):
            return 0.3
    
    service._analyzers["thesis_alignment"] = LowAnalyzer()
    context = StoryScoringContext(film_id="test_film")
    
    score = service.score_scene(
        film_id="test_film",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context
    )
    
    assert len(score.recommendations) > 0
    assert any(r.category == RecommendationCategory.THESIS_DRIFT for r in score.recommendations)


# =============================================================================
# Test: to_dict Methods
# =============================================================================

def test_story_score_to_dict():
    """Test that StoryScore.to_dict() works."""
    score = StoryScore(film_id="test_film", scope="scene")
    result = score.to_dict()
    
    assert isinstance(result, dict)
    assert result["film_id"] == "test_film"
    assert result["scope"] == "scene"


def test_story_recommendation_to_dict():
    """Test that StoryRecommendation.to_dict() works."""
    recommendation = StoryRecommendation(
        category=RecommendationCategory.THESIS_DRIFT,
        priority=RevisionPriority.MEDIUM,
        description="Test",
        target_scope="scene",
        specific_scenes=["scene_1"],
        rationale="Test rationale"
    )
    result = recommendation.to_dict()
    
    assert isinstance(result, dict)
    assert result["category"] == "thesis_drift"
    assert result["priority"] == "medium"


# =============================================================================
# Run All Tests
# =============================================================================


# =============================================================================
# Phase 4.3: Tests for Real Analyzer Logic
# =============================================================================

def test_thesis_alignment_with_themes():
    """Test ThesisAlignmentAnalyzer with theme data."""
    from app.services.story_scoring_service import ThesisAlignmentAnalyzer
    
    analyzer = ThesisAlignmentAnalyzer()
    
    # Scene with theme mentions
    context_with_themes = {
        "film_memory": None,
        "film_structure": type('obj', (object,), {"themes": ["love", "sacrifice", "redemption"]})(),
        "scene_data": {"content": "A story about love and sacrifice"},
        "scope": "scene"
    }
    score = analyzer.analyze(context_with_themes)
    assert score > 0.5, f"Expected > 0.5 with theme mentions, got {score}"
    
    # Scene without theme mentions
    context_without_themes = {
        "film_memory": None,
        "film_structure": type('obj', (object,), {"themes": ["love", "sacrifice"]})(),
        "scene_data": {"content": "A story about random things"},
        "scope": "scene"
    }
    score = analyzer.analyze(context_without_themes)
    assert score == 0.5, f"Expected 0.5 without theme mentions, got {score}"


def test_tone_coherence_with_shifts():
    """Test ToneCoherenceAnalyzer with tone shift data."""
    from app.services.story_scoring_service import ToneCoherenceAnalyzer
    
    analyzer = ToneCoherenceAnalyzer()
    
    # Film with few tone shifts (good)
    context_few_shifts = {
        "film_structure": type('obj', (object,), {
            "tone_shifts": [{"scene_index": 5, "from_tone": "dark", "to_tone": "light"}]
        })(),
        "scope": "film"
    }
    score = analyzer.analyze(context_few_shifts)
    assert score >= 0.7, f"Expected >= 0.7 with few shifts, got {score}"
    
    # Film with many tone shifts (potentially unstable)
    context_many_shifts = {
        "film_structure": type('obj', (object,), {
            "tone_shifts": [{"scene_index": i, "from_tone": "a", "to_tone": "b"} for i in range(15)]
        })(),
        "scope": "film"
    }
    score = analyzer.analyze(context_many_shifts)
    assert score <= 0.5, f"Expected <= 0.5 with many shifts, got {score}"


def test_character_progression_with_data():
    """Test CharacterProgressionAnalyzer with character data."""
    from app.services.story_scoring_service import CharacterProgressionAnalyzer
    
    analyzer = CharacterProgressionAnalyzer()
    
    # Film with good character distribution
    context_good = {
        "film_structure": type('obj', (object,), {
            "character_scenes": {"char1": ["s1", "s2", "s3", "s4", "s5"], "char2": ["s2", "s3", "s4", "s5", "s6"]},
            "total_scenes": 10
        })(),
        "scope": "film",
        "scene_decisions": []
    }
    score = analyzer.analyze(context_good)
    assert score >= 0.6, f"Expected >= 0.6 with good character distribution, got {score}"
    
    # Film with poor character distribution
    context_poor = {
        "film_structure": type('obj', (object,), {
            "character_scenes": {"char1": ["s1"], "char2": ["s2"]},
            "total_scenes": 20
        })(),
        "scope": "film",
        "scene_decisions": []
    }
    score = analyzer.analyze(context_poor)
    assert score < 0.6, f"Expected < 0.6 with poor distribution, got {score}"


def test_emotional_trajectory_with_data():
    """Test EmotionalTrajectoryAnalyzer with trajectory data."""
    from app.services.story_scoring_service import EmotionalTrajectoryAnalyzer
    
    analyzer = EmotionalTrajectoryAnalyzer()
    
    # Film with 3-act structure
    context_structured = {
        "film_structure": type('obj', (object,), {"acts": [1, 2, 3]})(),
        "scope": "film"
    }
    score = analyzer.analyze(context_structured)
    assert score >= 0.7, f"Expected >= 0.7 with 3-act structure, got {score}"
    
    # No data
    context_empty = {
        "film_structure": None,
        "scope": "film"
    }
    score = analyzer.analyze(context_empty)
    assert score == 0.5, f"Expected 0.5 with no data, got {score}"


def test_motif_continuity_with_data():
    """Test MotifContinuityAnalyzer with motif data."""
    from app.services.story_scoring_service import MotifContinuityAnalyzer
    
    analyzer = MotifContinuityAnalyzer()
    
    # Scene referencing motifs
    context_with_ref = {
        "film_memory": type('obj', (object,), {"motifs": [{"name": "red"}, {"name": "door"}]})(),
        "scene_data": {"content": "The red door creaked open"},
        "scope": "scene"
    }
    score = analyzer.analyze(context_with_ref)
    assert score > 0.5, f"Expected > 0.5 with motif reference, got {score}"
    
    # No motifs defined
    context_no_motifs = {
        "film_memory": type('obj', (object,), {"motifs": []})(),
        "scope": "film"
    }
    score = analyzer.analyze(context_no_motifs)
    assert score == 0.5, f"Expected 0.5 with no motifs, got {score}"


def test_tension_resolution_with_data():
    """Test TensionResolutionAnalyzer with tension data."""
    from app.services.story_scoring_service import TensionResolutionAnalyzer
    
    analyzer = TensionResolutionAnalyzer()
    
    # Film with no tensions (resolved)
    context_resolved = {
        "film_memory": type('obj', (object,), {"unresolved_tensions": []})(),
        "scope": "film"
    }
    score = analyzer.analyze(context_resolved)
    assert score >= 0.7, f"Expected >= 0.7 with no tensions, got {score}"
    
    # Film with many high-urgency tensions
    context_high_urgency = {
        "film_memory": type('obj', (object,), {
            "unresolved_tensions": [
                type('obj', (object,), {"urgency_level": 8}),
                type('obj', (object,), {"urgency_level": 9}),
                type('obj', (object,), {"urgency_level": 7})
            ]
        })(),
        "scope": "film"
    }
    score = analyzer.analyze(context_high_urgency)
    assert score <= 0.5, f"Expected <= 0.5 with high urgency tensions, got {score}"


def test_originality_with_cliches():
    """Test OriginalityAnalyzer with cliché detection."""
    from app.services.story_scoring_service import OriginalityAnalyzer
    
    analyzer = OriginalityAnalyzer()
    
    # Scene with clichés
    context_with_cliches = {
        "film_memory": type('obj', (object,), {"restraint_rules": []})(),
        "scene_data": {"content": "Suddenly a deus ex machina appeared and it was all a dream"},
        "scope": "scene"
    }
    score = analyzer.analyze(context_with_cliches)
    assert score <= 0.5, f"Expected <= 0.5 with clichés, got {score}"
    
    # Original scene
    context_original = {
        "film_memory": type('obj', (object,), {"restraint_rules": []})(),
        "scene_data": {"content": "The character made a surprising choice that subverted expectations"},
        "scope": "scene"
    }
    score = analyzer.analyze(context_original)
    assert score >= 0.6, f"Expected >= 0.6 for original content, got {score}"


def test_continuity_debt_trajectory_with_data():
    """Test ContinuityDebtTrajectoryAnalyzer with tracker data."""
    from app.services.story_scoring_service import ContinuityDebtTrajectoryAnalyzer
    from app.services.conflicts import FilmContinuityTracker
    
    analyzer = ContinuityDebtTrajectoryAnalyzer()
    tracker = FilmContinuityTracker()
    
    # Record some scenes with low debt
    tracker.record_scene_decision("film1", "scene1", {"continuity_context": {"alerts": []}})
    tracker.record_scene_decision("film1", "scene2", {"continuity_context": {"alerts": []}})
    
    # Low debt trajectory
    context_low_debt = {
        "continuity_tracker": tracker,
        "film_id": "film1",
        "scope": "film"
    }
    score = analyzer.analyze(context_low_debt)
    assert score >= 0.7, f"Expected >= 0.7 with low debt, got {score}"
    
    # No tracker
    context_no_tracker = {
        "continuity_tracker": None,
        "film_id": "film1",
        "scope": "film"
    }
    score = analyzer.analyze(context_no_tracker)
    assert score == 0.5, f"Expected 0.5 with no tracker, got {score}"


def test_all_analyzers_handle_missing_context():
    """Test that all analyzers gracefully handle missing context data."""
    from app.services.story_scoring_service import (
        ThesisAlignmentAnalyzer, ToneCoherenceAnalyzer, CharacterProgressionAnalyzer,
        EmotionalTrajectoryAnalyzer, MotifContinuityAnalyzer, TensionResolutionAnalyzer,
        OriginalityAnalyzer, ContinuityDebtTrajectoryAnalyzer
    )
    
    analyzers = [
        ThesisAlignmentAnalyzer(),
        ToneCoherenceAnalyzer(),
        CharacterProgressionAnalyzer(),
        EmotionalTrajectoryAnalyzer(),
        MotifContinuityAnalyzer(),
        TensionResolutionAnalyzer(),
        OriginalityAnalyzer(),
        ContinuityDebtTrajectoryAnalyzer()
    ]
    
    empty_context = {}
    
    for analyzer in analyzers:
        try:
            score = analyzer.analyze(empty_context)
            assert 0.0 <= score <= 1.0, f"{analyzer.__class__.__name__} returned invalid score {score}"
        except Exception as e:
            assert False, f"{analyzer.__class__.__name__} raised exception: {e}"


def test_analyzers_deterministic():
    """Test that analyzers return consistent results for same input."""
    from app.services.story_scoring_service import ThesisAlignmentAnalyzer
    
    analyzer = ThesisAlignmentAnalyzer()
    context = {
        "film_memory": type('obj', (object,), {"story_thesis": "Test thesis", "themes": ["theme1"]})(),
        "film_structure": None,
        "scene_data": {"content": "A scene about theme1"},
        "scope": "scene"
    }
    
    # Run same analysis multiple times
    scores = [analyzer.analyze(context) for _ in range(5)]
    assert all(s == scores[0] for s in scores), f"Analyzer returned inconsistent results: {scores}"


def _build_film_intelligence_structure() -> FilmStructure:
    act_1_seq = Sequence(
        sequence_id="seq_1",
        act_number=1,
        sequence_number=1,
        start_scene_index=1,
        end_scene_index=3,
        scenes=["scene_1", "scene_2", "scene_3"],
        sequence_goal="Establish the fracture",
        mini_thesis="Avoidance holds until pressure rises",
    )
    act_2_seq = Sequence(
        sequence_id="seq_2",
        act_number=2,
        sequence_number=1,
        start_scene_index=4,
        end_scene_index=6,
        scenes=["scene_4", "scene_5", "scene_6"],
        sequence_goal="Complicate the unresolved tension",
        mini_thesis="The family can no longer hide from the conflict",
    )
    act_3_seq = Sequence(
        sequence_id="seq_3",
        act_number=3,
        sequence_number=1,
        start_scene_index=7,
        end_scene_index=8,
        scenes=["scene_7", "scene_8"],
        sequence_goal="Deliver earned catharsis",
        mini_thesis="Truth arrives after resistance breaks",
    )
    return FilmStructure(
        film_id="film_intel_story",
        total_scenes=8,
        acts=[
            Act(
                act_number=1,
                act_type=ActType.SETUP,
                start_scene_index=1,
                end_scene_index=3,
                sequences=[act_1_seq],
                thematic_focus="Avoidance",
                emotional_contract="tension",
            ),
            Act(
                act_number=2,
                act_type=ActType.CONFRONTATION,
                start_scene_index=4,
                end_scene_index=6,
                sequences=[act_2_seq],
                thematic_focus="Pressure",
                emotional_contract="tension",
            ),
            Act(
                act_number=3,
                act_type=ActType.RESOLUTION,
                start_scene_index=7,
                end_scene_index=8,
                sequences=[act_3_seq],
                thematic_focus="Catharsis",
                emotional_contract="release",
            ),
        ],
        all_sequences=[act_1_seq, act_2_seq, act_3_seq],
        themes=["grief", "honesty"],
        character_scenes={
            "Elena": ["scene_1", "scene_4", "scene_8"],
            "Marcus": ["scene_2", "scene_5", "scene_8"],
        },
    )


def _build_film_intelligence_memory() -> FilmLevelMemory:
    return FilmLevelMemory(
        film_id="film_intel_story",
        story_thesis="Grief forces the family to abandon performance and face the truth.",
        emotional_contract="tension",
        genre_lane="family drama",
        visual_philosophy="intimate realism",
        pacing_philosophy="measured pressure",
        themes=["grief", "honesty"],
        motifs=[
            MotifRecord(
                motif_id="rain_glass",
                name="rain on glass",
                motif_type="visual",
                first_appearance_scene="scene_2",
                associated_theme="suppressed grief",
                accumulated_meaning="Distortion stands in for avoidance.",
                recurrences=[{"scene_id": "scene_7", "description": "Returns during confession"}],
            )
        ],
        unresolved_tensions=[
            UnresolvedTension(
                tension_id="burial_argument",
                tension_type="relationship",
                introduced_scene="scene_3",
                description="The siblings disagree over the father's burial.",
                parties_involved=["Elena", "Marcus"],
                urgency_level=0.8,
                expected_resolution_act=2,
            )
        ],
        emotional_trajectory=[
            EmotionalTrajectoryPoint(scene_index=2, scene_id="scene_2", emotional_state="unease", intensity=0.4),
            EmotionalTrajectoryPoint(scene_index=5, scene_id="scene_5", emotional_state="pressure", intensity=0.7),
            EmotionalTrajectoryPoint(scene_index=8, scene_id="scene_8", emotional_state="catharsis", intensity=0.9),
        ],
    )


def test_story_scoring_unchanged_when_no_film_intelligence_available():
    """No film intelligence should leave story scoring at its baseline behavior."""
    service = StoryLevelScoringService()
    context = StoryScoringContext(film_id="film_no_intel")

    score = service.score_scene(
        film_id="film_no_intel",
        scene_id="scene_1",
        scene_data={"content": "test"},
        context=context,
    )

    assert score.overall_health == 0.5
    assert score.debug_metadata["film_intelligence_influence"]["applied"] is False
    assert score.debug_metadata["film_intelligence_influence"]["available"] is False


def test_film_intelligence_can_improve_grounding_for_dimensions():
    """Available film intelligence should nudge supported dimensions upward slightly."""
    service = StoryLevelScoringService()
    structure = _build_film_intelligence_structure()
    memory = _build_film_intelligence_memory()
    spine = CreativeSpine(film_id="film_intel_story")
    spine.initialize_from_memory(memory)
    context = StoryScoringContext(
        film_id="film_intel_story",
        film_structure=structure,
        film_memory=memory,
        creative_spine=spine,
    )

    baseline_context = {
        "film_structure": structure,
        "film_memory": memory,
        "scope": "film",
    }
    baseline_emotional = service._analyzers["emotional_trajectory"].analyze(baseline_context)

    score = service.score_film(
        film_id="film_intel_story",
        context=context,
    )

    assert score.emotional_trajectory > baseline_emotional
    assert score.debug_metadata["film_intelligence_influence"]["applied"] is True
    assert "emotional_trajectory" in score.debug_metadata["film_intelligence_influence"]["affected_dimensions"]


def test_recommendation_specificity_improves_with_film_intelligence():
    """Film intelligence support should make low-score recommendations more specific."""
    service = StoryLevelScoringService()
    recommendations = service._generate_recommendations(
        dimension_scores={
            "motif_continuity": 0.4,
            "tension_resolution_rate": 0.4,
        },
        scope="film",
        scope_id="film_intel_story",
        film_intelligence_influence={
            "support": {
                "debt_payoff_arc_summary": {
                    "setup_payoff_count": 3,
                    "open_tension_count": 2,
                    "motif_count": 1,
                    "arc_count": 2,
                }
            }
        },
    )

    descriptions = [rec.description.lower() for rec in recommendations]
    suggested_fixes = [rec.suggested_fix or "" for rec in recommendations]
    assert any("motif" in description and "callback" in description for description in descriptions)
    assert any("tension" in description and "stagnating" in description for description in descriptions)
    assert any("clearer callback" in fix.lower() for fix in suggested_fixes)


def test_film_intelligence_influence_remains_bounded():
    """Film intelligence influence must stay within explicit caps."""
    service = StoryLevelScoringService()
    structure = _build_film_intelligence_structure()
    memory = _build_film_intelligence_memory()
    spine = CreativeSpine(film_id="film_intel_story")
    spine.initialize_from_memory(memory)
    context = StoryScoringContext(
        film_id="film_intel_story",
        film_structure=structure,
        film_memory=memory,
        creative_spine=spine,
    )

    score = service.score_film(
        film_id="film_intel_story",
        context=context,
    )

    influence = score.debug_metadata["film_intelligence_influence"]
    assert abs(influence["total_delta"]) <= service._max_film_intelligence_total_delta
    assert all(
        abs(delta) <= service._max_film_intelligence_dimension_delta
        for delta in influence["adjustments"].values()
    )


# Add new tests to run_all_tests function
def run_all_tests_with_phase_43():
    """Run all tests including Phase 4.3 analyzer logic tests."""
    import sys
    
    # Original tests
    original_tests = [
        test_service_creation,
        test_global_instance_exists,
        test_all_eight_analyzers_registered,
        test_default_weights_sum_to_one,
        test_analyzers_are_base_dimension_analyzer_instances,
        test_score_scene_returns_story_score,
        test_score_sequence_returns_story_score,
        test_score_act_returns_story_score,
        test_score_film_returns_story_score,
        test_score_scene_with_minimal_context,
        test_score_scene_with_none_scene_data,
        test_score_sequence_with_no_film_structure,
        test_score_act_with_no_film_structure,
        test_score_film_with_no_film_structure,
        test_score_scene_with_all_optional_fields_none,
        test_base_analyzer_returns_placeholder,
        test_all_analyzers_return_placeholder_0_5,
        test_overall_health_with_all_placeholders,
        test_revision_priority_with_all_placeholders,
        test_no_warnings_with_placeholder_scores,
        test_no_recommendations_with_placeholder_scores,
        test_all_dimension_scores_present,
        test_dimension_weights_preserved,
        test_story_scoring_context_has_required_fields,
        test_story_scoring_context_scene_decisions_default,
        test_story_score_has_required_fields,
        test_story_recommendation_creation,
        test_revision_priority_enum_values,
        test_recommendation_category_enum_values,
        test_score_has_timestamp,
        test_score_based_on_scenes_list,
        test_analyzer_exception_caught_safely,
        test_scene_score_scope_fields,
        test_sequence_score_scope_fields,
        test_act_score_scope_fields,
        test_film_score_scope_fields,
        test_priority_critical_for_very_low_scores,
        test_priority_high_for_low_scores,
        test_priority_medium_for_moderate_scores,
        test_priority_low_for_good_scores,
        test_warnings_generated_for_low_scores,
        test_recommendations_generated_for_low_scores,
        test_story_score_to_dict,
        test_story_recommendation_to_dict,
    ]
    
    # Phase 4.3 tests
    phase_43_tests = [
        test_thesis_alignment_with_themes,
        test_tone_coherence_with_shifts,
        test_character_progression_with_data,
        test_emotional_trajectory_with_data,
        test_motif_continuity_with_data,
        test_tension_resolution_with_data,
        test_originality_with_cliches,
        test_continuity_debt_trajectory_with_data,
        test_all_analyzers_handle_missing_context,
        test_analyzers_deterministic,
    ]
    
    all_tests = original_tests + phase_43_tests
    passed = 0
    failed = 0
    
    for test in all_tests:
        try:
            test()
            passed += 1
            print(f"✓ {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__}: {e}")
    
    print(f"\n{passed}/{len(all_tests)} tests passed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests_with_phase_43()
    sys.exit(0 if success else 1)
