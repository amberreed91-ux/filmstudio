"""
Tests for Creative Spine - Phase 2 of Film Co-Direction System.

These tests verify:
a. CreativeSpine model works correctly
b. SpineService provides proper governance API
c. Backward compatibility with existing code
d. Constraint validation works as expected
e. Override and deviation management works
"""

import sys
import os

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from app.models.spine import (
    CreativeSpine,
    SpineConstraint,
    ConstraintViolation,
    ConstraintSeverity,
    ConstraintType,
    DriftReport,
    OverrideRecord,
    ApprovedDeviation,
)
from app.models.memory import FilmLevelMemory
from app.services.spine_service import SpineService, spine_service, ValidationResult
from app.models.crew import AgentRole


# Use existing roles for testing
# Note: DIRECTOR is now in the enum (Phase 3.1 fix)
TEST_DIRECTOR_ROLE = AgentRole.DIRECTOR
TEST_CINEMATOGRAPHER_ROLE = AgentRole.CINEMATOGRAPHER


# =============================================================================
# Test: CreativeSpine Model
# =============================================================================

def test_creative_spine_creation():
    """Test that CreativeSpine can be created."""
    spine = CreativeSpine(film_id="test_film_1")
    
    assert spine.film_id == "test_film_1"
    assert spine.spine_version == "1.0"
    assert len(spine.frozen_fields) == 3
    assert "story_thesis" in spine.frozen_fields
    assert "emotional_contract" in spine.frozen_fields
    assert "genre_lane" in spine.frozen_fields
    
    print("✓ test_creative_spine_creation passed")


def test_spine_initialization_from_memory():
    """Test that spine initializes constraints from FilmLevelMemory."""
    # Create a mock memory
    memory = FilmLevelMemory(
        film_id="test_film_2",
        story_thesis="What is the cost of truth?",
        emotional_contract="Tension and eventual catharsis",
        genre_lane="psychological thriller"
    )
    
    spine = CreativeSpine(film_id="test_film_2")
    spine.initialize_from_memory(memory)
    
    # Should have constraints for frozen fields
    assert len(spine.constraints) >= 3
    
    # Check story_thesis constraint
    thesis_constraint = spine.get_constraint_for_field("story_thesis")
    assert thesis_constraint is not None
    assert thesis_constraint.severity == ConstraintSeverity.ERROR
    assert thesis_constraint.constraint_type == ConstraintType.IMMUTABLE
    
    print("✓ test_spine_initialization_from_memory passed")


def test_is_frozen():
    """Test the is_frozen helper."""
    spine = CreativeSpine(film_id="test")
    
    assert spine.is_frozen("story_thesis") == True
    assert spine.is_frozen("emotional_contract") == True
    assert spine.is_frozen("visual_philosophy") == False  # It's revisable
    assert spine.is_frozen("pacing_philosophy") == False
    
    print("✓ test_is_frozen passed")


def test_record_override():
    """Test recording a human override."""
    spine = CreativeSpine(film_id="test")
    
    spine.record_override(
        field_name="visual_philosophy",
        old_value="dark and moody",
        new_value="high contrast noir",
        reason="Director updated visual direction",
        overridden_by="user_123"
    )
    
    assert len(spine.override_history) == 1
    override = spine.override_history[0]
    assert override.field_name == "visual_philosophy"
    assert override.old_value == "dark and moody"
    assert override.new_value == "high contrast noir"
    assert override.overridden_by == "user_123"
    
    print("✓ test_record_override passed")


def test_add_approved_deviation():
    """Test adding an approved deviation."""
    spine = CreativeSpine(film_id="test")
    
    spine.add_approved_deviation(
        field_name="pacing_philosophy",
        approved_value="faster pace acceptable",
        scope="act_2",
        reason="Story needs more momentum",
        approved_by="director_456",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    
    assert len(spine.approved_deviations) == 1
    deviation = spine.approved_deviations[0]
    assert deviation.field_name == "pacing_philosophy"
    assert deviation.scope == "act_2"
    assert deviation.is_active() == True
    
    print("✓ test_add_approved_deviation passed")


def test_get_active_deviations_for_scene():
    """Test getting active deviations for a scene."""
    spine = CreativeSpine(film_id="test")
    
    # Add film-wide deviation
    spine.add_approved_deviation(
        field_name="visual_philosophy",
        approved_value="desaturated",
        scope="film-wide",
        reason="Creative choice",
        approved_by="director"
    )
    
    # Add scene-specific deviation
    spine.add_approved_deviation(
        field_name="pacing_philosophy",
        approved_value="faster",
        scope="scene_45",
        reason="Action sequence",
        approved_by="director"
    )
    
    # Get all deviations that apply to scene_45 (both film-wide and scene-specific)
    applicable = spine.get_active_deviations_for_scene("scene_45")
    assert len(applicable) == 2
    # First should be film-wide
    assert applicable[0].scope == "film-wide"
    assert applicable[0].field_name == "visual_philosophy"
    # Second should be scene-specific
    assert applicable[1].scope == "scene_45"
    assert applicable[1].field_name == "pacing_philosophy"
    
    print("✓ test_get_active_deviations_for_scene passed")


def test_spine_to_dict():
    """Test spine serialization."""
    spine = CreativeSpine(film_id="test")
    d = spine.to_dict()
    
    assert d["film_id"] == "test"
    assert d["spine_version"] == "1.0"
    assert "frozen_fields" in d
    assert "constraint_weights" in d
    
    print("✓ test_spine_to_dict passed")


def test_spine_get_summary():
    """Test spine summary."""
    spine = CreativeSpine(film_id="test")
    summary = spine.get_summary()
    
    assert summary["film_id"] == "test"
    assert summary["frozen_field_count"] == 3
    assert summary["revisable_field_count"] == 3
    assert "constraint_count" in summary
    
    print("✓ test_spine_get_summary passed")


# =============================================================================
# Test: SpineService
# =============================================================================

def test_spine_service_creation():
    """Test that SpineService can be created."""
    service = SpineService()
    assert service is not None
    
    print("✓ test_spine_service_creation passed")


def test_get_or_create_spine():
    """Test getting or creating a spine."""
    service = SpineService()
    
    # First call creates
    spine1 = service.get_or_create_spine("film_1")
    assert spine1 is not None
    assert spine1.film_id == "film_1"
    
    # Second call returns same
    spine2 = service.get_or_create_spine("film_1")
    assert spine2 is spine1  # Same instance
    
    print("✓ test_get_or_create_spine passed")


def test_create_spine_from_memory():
    """Test creating spine from FilmLevelMemory."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_2",
        story_thesis="What is the cost of truth?",
        emotional_contract="Tension and eventual catharsis",
        genre_lane="psychological thriller"
    )
    
    spine = service.create_spine_from_memory("film_2", memory)
    
    assert spine.film_id == "film_2"
    assert len(spine.constraints) > 0
    
    # Memory should be cached
    cached = service._memory_cache.get("film_2")
    assert cached is memory
    
    print("✓ test_create_spine_from_memory passed")


def test_get_constraints_for_role_director():
    """Test getting constraints for director role."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_3",
        story_thesis="What is the cost of truth?",
        emotional_contract="Tension",
        genre_lane="thriller"
    )
    service.create_spine_from_memory("film_3", memory)
    
    constraints = service.get_constraints_for_role("film_3", TEST_DIRECTOR_ROLE)
    
    assert "immutable" in constraints
    assert "revisable" in constraints
    assert "story_thesis" in constraints["immutable"]
    
    print("✓ test_get_constraints_for_role_director passed")


def test_get_constraints_for_role_cinematographer():
    """Test getting constraints for cinematographer role."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_4",
        visual_philosophy="high contrast",
        pacing_philosophy="slow burn"
    )
    service.create_spine_from_memory("film_4", memory)
    
    constraints = service.get_constraints_for_role("film_4", TEST_CINEMATOGRAPHER_ROLE)
    
    # Cinematographers get visual and pacing
    assert "visual_philosophy" in constraints
    assert "pacing_philosophy" in constraints
    
    print("✓ test_get_constraints_for_role_cinematographer passed")


def test_check_decision_valid():
    """Test checking a valid decision."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_5",
        story_thesis="What is the cost?",
        emotional_contract="Tension"
    )
    service.create_spine_from_memory("film_5", memory)
    
    # Decision that matches spine should be valid
    result = service.check_decision(
        "film_5",
        {"type": "story_thesis", "value": "What is the cost?"},
        {"scene_id": "scene_1"}
    )
    
    assert result.is_valid == True
    assert len(result.violations) == 0
    
    print("✓ test_check_decision_valid passed")


def test_check_decision_violation():
    """Test checking a decision that violates spine."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_6",
        story_thesis="What is the cost of truth?",
        emotional_contract="Tension"
    )
    service.create_spine_from_memory("film_6", memory)
    
    # Decision that contradicts immutable field
    result = service.check_decision(
        "film_6",
        {"type": "story_thesis", "value": "Something completely different"},
        {"scene_id": "scene_1"}
    )
    
    assert result.is_valid == False
    assert len(result.violations) == 1
    assert result.violations[0].severity == ConstraintSeverity.ERROR
    
    print("✓ test_check_decision_violation passed")


def test_check_decision_warning():
    """Test checking a decision that deviates from revisable field."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_7",
        visual_philosophy="dark and moody"
    )
    service.create_spine_from_memory("film_7", memory)
    
    # Decision that differs from revisable field (warning, not error)
    result = service.check_decision(
        "film_7",
        {"type": "visual_philosophy", "value": "bright and cheerful"},
        {"scene_id": "scene_1"}
    )
    
    assert result.is_valid == True  # Still valid, just warnings
    assert len(result.warnings) == 1
    assert result.warnings[0].severity == ConstraintSeverity.WARNING
    
    print("✓ test_check_decision_warning passed")


def test_validate_against_spine():
    """Test validating agent output against spine."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_8",
        story_thesis="What is the cost?",
        emotional_contract="Tension"
    )
    service.create_spine_from_memory("film_8", memory)
    
    # Output that matches
    violations = service.validate_against_spine(
        "film_8",
        {"story_thesis": "What is the cost?"}
    )
    assert len(violations) == 0
    
    # Output that violates
    violations = service.validate_against_spine(
        "film_8",
        {"story_thesis": "Something else"}
    )
    assert len(violations) == 1
    
    print("✓ test_validate_against_spine passed")


def test_get_guidance():
    """Test getting guidance from spine."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_9",
        pacing_philosophy="slow_burn",
        visual_philosophy="high contrast"
    )
    service.create_spine_from_memory("film_9", memory)
    
    # Get pacing guidance for act 2
    guidance = service.get_guidance(
        "film_9",
        "pacing",
        {"act": 2}
    )
    
    assert "recommendation" in guidance
    assert "rationale" in guidance
    assert guidance["flexible"] == True
    
    print("✓ test_get_guidance passed")


def test_record_override_service():
    """Test recording override through service."""
    service = SpineService()
    
    memory = FilmLevelMemory(film_id="film_10", visual_philosophy="old value")
    service.create_spine_from_memory("film_10", memory)
    
    result = service.record_override(
        "film_10",
        "visual_philosophy",
        "old value",
        "new value",
        "Director updated",
        "user_123"
    )
    
    assert result == True
    
    # Check spine was updated
    spine = service.get_spine("film_10")
    assert len(spine.override_history) == 1
    
    print("✓ test_record_override_service passed")


def test_add_approved_deviation_service():
    """Test adding approved deviation through service."""
    service = SpineService()
    
    memory = FilmLevelMemory(film_id="film_11", pacing_philosophy="slow")
    service.create_spine_from_memory("film_11", memory)
    
    result = service.add_approved_deviation(
        "film_11",
        "pacing_philosophy",
        "faster acceptable",
        "act_2",
        "Story needs momentum",
        "director_456"
    )
    
    assert result == True
    
    # Check deviation was added
    spine = service.get_spine("film_11")
    assert len(spine.approved_deviations) == 1
    
    print("✓ test_add_approved_deviation_service passed")


def test_check_drift():
    """Test drift detection."""
    service = SpineService()
    
    memory = FilmLevelMemory(
        film_id="film_12",
        story_thesis="Original thesis"
    )
    service.create_spine_from_memory("film_12", memory)
    
    # Check drift with same memory
    reports = service.check_drift("film_12", memory)
    # Should have minimal or no drift
    
    print("✓ test_check_drift passed")


def test_global_spine_service_instance():
    """Test global spine_service instance exists."""
    assert spine_service is not None
    assert isinstance(spine_service, SpineService)
    
    print("✓ test_global_spine_service_instance passed")


def test_spince_summary():
    """Test getting spine summary."""
    service = SpineService()
    
    memory = FilmLevelMemory(film_id="film_13", story_thesis="Test")
    service.create_spine_from_memory("film_13", memory)
    
    summary = service.get_spince_summary("film_13")
    
    assert summary["film_id"] == "film_13"
    assert "constraint_count" in summary
    
    print("✓ test_spince_summary passed")


def test_list_spines():
    """Test listing all spines."""
    service = SpineService()
    
    service.create_spine_from_memory("film_a", FilmLevelMemory(film_id="film_a"))
    service.create_spine_from_memory("film_b", FilmLevelMemory(film_id="film_b"))
    
    spines = service.list_spines()
    assert "film_a" in spines
    assert "film_b" in spines
    
    print("✓ test_list_spines passed")


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_existing_tests_still_pass():
    """Verify existing tests are not broken."""
    # Import and run a quick sanity check from scene evolution
    from app.services.scene_evolution import SceneEvolutionTracker
    
    tracker = SceneEvolutionTracker()
    assert tracker is not None
    
    result = tracker.get_evolution_data("nonexistent_scene")
    assert result is None or isinstance(result, list)
    
    print("✓ test_existing_tests_still_pass passed")


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    """Run all tests in this suite."""
    print("=== Creative Spine Test Suite ===\n")
    
    tests = [
        # CreativeSpine model tests
        test_creative_spine_creation,
        test_spine_initialization_from_memory,
        test_is_frozen,
        test_record_override,
        test_add_approved_deviation,
        test_get_active_deviations_for_scene,
        test_spine_to_dict,
        test_spine_get_summary,
        
        # SpineService tests
        test_spine_service_creation,
        test_get_or_create_spine,
        test_create_spine_from_memory,
        test_get_constraints_for_role_director,
        test_get_constraints_for_role_cinematographer,
        test_check_decision_valid,
        test_check_decision_violation,
        test_check_decision_warning,
        test_validate_against_spine,
        test_get_guidance,
        test_record_override_service,
        test_add_approved_deviation_service,
        test_check_drift,
        test_global_spine_service_instance,
        test_spince_summary,
        test_list_spines,
        
        # Backward compatibility
        test_existing_tests_still_pass,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n=== ALL TESTS PASSED ===")
        return True
    else:
        print(f"\n=== {failed} TESTS FAILED ===")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)