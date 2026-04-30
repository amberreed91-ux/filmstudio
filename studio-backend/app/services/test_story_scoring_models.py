"""
Tests for Phase 4 Story-Level Scoring Models

Tests:
- Model construction
- Enum values
- Serialization (to_dict)
- Backward compatibility
"""

import sys
sys.path.insert(0, '.')

from app.models.crew import (
    StoryScore,
    StoryRecommendation,
    RecommendationCategory,
    RevisionPriority
)


def test_revision_priority_enum_values():
    """Test RevisionPriority enum has expected values."""
    assert RevisionPriority.LOW.value == "low"
    assert RevisionPriority.MEDIUM.value == "medium"
    assert RevisionPriority.HIGH.value == "high"
    assert RevisionPriority.CRITICAL.value == "critical"
    print("✓ test_revision_priority_enum_values passed")


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
    print("✓ test_recommendation_category_enum_values passed")


def test_story_recommendation_construction():
    """Test StoryRecommendation can be constructed with all fields."""
    rec = StoryRecommendation(
        category=RecommendationCategory.THESIS_DRIFT,
        priority=RevisionPriority.HIGH,
        description="Scene 5 does not support the film's thesis about redemption",
        target_scope="scene",
        specific_scenes=["scene_5"],
        rationale="The thesis established in Act 1 is about redemption, but scene 5 shows character making no choice",
        suggested_fix="Add a moment where the character chooses to forgive"
    )
    
    assert rec.category == RecommendationCategory.THESIS_DRIFT
    assert rec.priority == RevisionPriority.HIGH
    assert rec.description == "Scene 5 does not support the film's thesis about redemption"
    assert rec.target_scope == "scene"
    assert rec.specific_scenes == ["scene_5"]
    assert rec.rationale == "The thesis established in Act 1 is about redemption, but scene 5 shows character making no choice"
    assert rec.suggested_fix == "Add a moment where the character chooses to forgive"
    print("✓ test_story_recommendation_construction passed")


def test_story_recommendation_optional_fields():
    """Test StoryRecommendation optional fields work correctly."""
    rec = StoryRecommendation(
        category=RecommendationCategory.TONE_SHIFT,
        priority=RevisionPriority.MEDIUM,
        description="Tone shifts from serious to comedic unexpectedly",
        target_scope="sequence",
        specific_scenes=["scene_8", "scene_9"],
        rationale="Sequence 2 starts serious but shifts to comedy by scene 8"
    )
    
    assert rec.category == RecommendationCategory.TONE_SHIFT
    assert rec.suggested_fix is None  # Optional field
    print("✓ test_story_recommendation_optional_fields passed")


def test_story_recommendation_to_dict():
    """Test StoryRecommendation serialization to dict."""
    rec = StoryRecommendation(
        category=RecommendationCategory.CHARACTER_STAGNATION,
        priority=RevisionPriority.LOW,
        description="Character arc not progressing",
        target_scope="act",
        specific_scenes=["scene_10", "scene_11", "scene_12"],
        rationale="Character has been in same emotional state for 3 scenes"
    )
    
    d = rec.to_dict()
    
    assert d["category"] == "character_stagnation"
    assert d["priority"] == "low"
    assert d["description"] == "Character arc not progressing"
    assert d["target_scope"] == "act"
    assert d["specific_scenes"] == ["scene_10", "scene_11", "scene_12"]
    assert d["rationale"] == "Character has been in same emotional state for 3 scenes"
    assert d["suggested_fix"] is None
    print("✓ test_story_recommendation_to_dict passed")


def test_story_score_construction():
    """Test StoryScore can be constructed with all fields."""
    score = StoryScore(
        film_id="film_1",
        scope="scene",
        scope_id="scene_5",
        thesis_alignment=0.85,
        tone_coherence=0.90,
        character_progression=0.75,
        emotional_trajectory=0.80,
        motif_continuity=0.95,
        tension_resolution_rate=0.70,
        originality_score=0.88,
        continuity_debt_trajectory=0.60,
        overall_health=0.80,
        dimension_weights={"thesis_alignment": 0.2, "tone_coherence": 0.1},
        scene_count=1,
        act_count=1,
        sequence_count=1,
        warnings=["Minor tone drift in middle section"],
        recommendations=[],
        revision_priority=RevisionPriority.MEDIUM,
        timestamp="2026-04-18T00:00:00",
        based_on_scenes=["scene_5"]
    )
    
    assert score.film_id == "film_1"
    assert score.scope == "scene"
    assert score.scope_id == "scene_5"
    assert score.thesis_alignment == 0.85
    assert score.tone_coherence == 0.90
    assert score.character_progression == 0.75
    assert score.emotional_trajectory == 0.80
    assert score.motif_continuity == 0.95
    assert score.tension_resolution_rate == 0.70
    assert score.originality_score == 0.88
    assert score.continuity_debt_trajectory == 0.60
    assert score.overall_health == 0.80
    assert score.dimension_weights == {"thesis_alignment": 0.2, "tone_coherence": 0.1}
    assert score.scene_count == 1
    assert score.act_count == 1
    assert score.sequence_count == 1
    assert score.warnings == ["Minor tone drift in middle section"]
    assert score.recommendations == []
    assert score.revision_priority == RevisionPriority.MEDIUM
    assert score.timestamp == "2026-04-18T00:00:00"
    assert score.based_on_scenes == ["scene_5"]
    print("✓ test_story_score_construction passed")


def test_story_score_defaults():
    """Test StoryScore default values."""
    score = StoryScore(film_id="film_1", scope="scene")
    
    assert score.film_id == "film_1"
    assert score.scope == "scene"
    assert score.scope_id is None
    assert score.thesis_alignment == 0.0
    assert score.tone_coherence == 0.0
    assert score.character_progression == 0.0
    assert score.emotional_trajectory == 0.0
    assert score.motif_continuity == 0.0
    assert score.tension_resolution_rate == 0.0
    assert score.originality_score == 0.0
    assert score.continuity_debt_trajectory == 0.0
    assert score.overall_health == 0.0
    assert score.dimension_weights == {}
    assert score.scene_count == 0
    assert score.act_count == 0
    assert score.sequence_count == 0
    assert score.warnings == []
    assert score.recommendations == []
    assert score.revision_priority == RevisionPriority.LOW
    assert score.timestamp == ""
    assert score.based_on_scenes == []
    print("✓ test_story_score_defaults passed")


def test_story_score_to_dict():
    """Test StoryScore serialization to dict."""
    rec = StoryRecommendation(
        category=RecommendationCategory.DEBT_ACCUMULATION,
        priority=RevisionPriority.HIGH,
        description="Continuity debt increasing faster than resolved",
        target_scope="film",
        specific_scenes=["scene_3", "scene_7", "scene_12"],
        rationale="3 new critical alerts in last 5 scenes but 0 resolved"
    )
    
    score = StoryScore(
        film_id="film_1",
        scope="film",
        thesis_alignment=0.75,
        tone_coherence=0.82,
        character_progression=0.68,
        emotional_trajectory=0.71,
        motif_continuity=0.90,
        tension_resolution_rate=0.55,
        originality_score=0.78,
        continuity_debt_trajectory=0.40,
        overall_health=0.70,
        scene_count=15,
        act_count=3,
        sequence_count=5,
        warnings=["Continuity debt increasing"],
        recommendations=[rec],
        revision_priority=RevisionPriority.HIGH,
        timestamp="2026-04-18T00:00:00",
        based_on_scenes=[f"scene_{i}" for i in range(1, 16)]
    )
    
    d = score.to_dict()
    
    assert d["film_id"] == "film_1"
    assert d["scope"] == "film"
    assert d["scope_id"] is None
    assert d["thesis_alignment"] == 0.75
    assert d["tone_coherence"] == 0.82
    assert d["character_progression"] == 0.68
    assert d["emotional_trajectory"] == 0.71
    assert d["motif_continuity"] == 0.90
    assert d["tension_resolution_rate"] == 0.55
    assert d["originality_score"] == 0.78
    assert d["continuity_debt_trajectory"] == 0.40
    assert d["overall_health"] == 0.70
    assert d["scene_count"] == 15
    assert d["act_count"] == 3
    assert d["sequence_count"] == 5
    assert d["warnings"] == ["Continuity debt increasing"]
    assert len(d["recommendations"]) == 1
    assert d["recommendations"][0]["category"] == "debt_accumulation"
    assert d["revision_priority"] == "high"
    assert d["timestamp"] == "2026-04-18T00:00:00"
    assert len(d["based_on_scenes"]) == 15
    print("✓ test_story_score_to_dict passed")


def test_story_score_with_recommendations():
    """Test StoryScore with multiple recommendations."""
    rec1 = StoryRecommendation(
        category=RecommendationCategory.THESIS_DRIFT,
        priority=RevisionPriority.HIGH,
        description="Act 2 thesis support weak",
        target_scope="act",
        specific_scenes=["scene_20", "scene_21"],
        rationale="Thesis about power corrupting not supported"
    )
    
    rec2 = StoryRecommendation(
        category=RecommendationCategory.MOTIF_MISSING_CALLBACK,
        priority=RevisionPriority.MEDIUM,
        description="Red motif callback missing",
        target_scope="sequence",
        specific_scenes=["scene_22"],
        rationale="Red motif established in scene 3 but no callback by scene 22"
    )
    
    score = StoryScore(
        film_id="film_1",
        scope="act",
        scope_id="act_2",
        thesis_alignment=0.55,
        overall_health=0.65,
        recommendations=[rec1, rec2],
        revision_priority=RevisionPriority.HIGH
    )
    
    assert len(score.recommendations) == 2
    assert score.recommendations[0].category == RecommendationCategory.THESIS_DRIFT
    assert score.recommendations[1].category == RecommendationCategory.MOTIF_MISSING_CALLBACK
    print("✓ test_story_score_with_recommendations passed")


def test_backward_compatibility_existing_models():
    """Test that existing models in crew.py still work."""
    from app.models.crew import (
        FilmStructure,
        Act,
        Sequence,
        Beat,
        BeatType,
        DirectorContinuityDecision
    )
    
    # Test FilmStructure still works
    film = FilmStructure(
        film_id="test_film",
        title="Test Film",
        total_scenes=30
    )
    assert film.film_id == "test_film"
    assert film.title == "Test Film"
    assert film.total_scenes == 30
    
    # Test to_dict still works
    d = film.to_dict()
    assert d["film_id"] == "test_film"
    
    print("✓ test_backward_compatibility_existing_models passed")


def run_all_tests():
    print("=== Phase 4 Story-Level Scoring Models Tests ===")
    
    # Enum tests
    test_revision_priority_enum_values()
    test_recommendation_category_enum_values()
    
    # StoryRecommendation tests
    test_story_recommendation_construction()
    test_story_recommendation_optional_fields()
    test_story_recommendation_to_dict()
    
    # StoryScore tests
    test_story_score_construction()
    test_story_score_defaults()
    test_story_score_to_dict()
    test_story_score_with_recommendations()
    
    # Backward compatibility
    test_backward_compatibility_existing_models()
    
    print("\n=== Results: All tests passed ===")


if __name__ == "__main__":
    run_all_tests()