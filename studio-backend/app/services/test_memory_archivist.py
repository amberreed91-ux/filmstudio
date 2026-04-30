"""
Tests for Memory Archivist - Phase 3.4

Tests verify:
1. Detects unresolved tensions
2. Detects missing motif callbacks
3. Detects inconsistent character states
4. Handles empty or partial memory safely
5. Does not break existing suites
"""

import sys
import os

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.memory_archivist import (
    MemoryArchivistEvaluator,
    memory_archivist_evaluator,
    AlertType,
    AlertSeverity,
    ContinuityAlert,
    TensionHealth,
    MotifCallbackStatus,
    CharacterConsistencyIssue,
)


# =============================================================================
# Test: Tension Health Detection
# =============================================================================

def test_detects_unresolved_tensions():
    """Test that overdue tensions are detected."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        "unresolved_tensions": [
            {
                "tension_id": "tension_1",
                "description": "The missing inheritance",
                "introduced_scene": "scene_5",
                "expected_resolution_act": 2,
            },
            {
                "tension_id": "tension_2",
                "description": "The secret affair",
                "introduced_scene": "scene_10",
                "expected_resolution_act": 3,
            },
        ],
    }

    structure = {
        "available": True,
        "current_act": {"act_number": 3},
    }

    result = evaluator.evaluate_film_continuity("test_film", {}, structure, memory)

    # tension_1 should be overdue (expected act 2, now in act 3)
    tension_1 = next((t for t in result.tension_statuses if t.tension_id == "tension_1"), None)
    assert tension_1 is not None
    assert tension_1.is_overdue == True

    # tension_2 should not be overdue yet (expected act 3, now in act 3)
    tension_2 = next((t for t in result.tension_statuses if t.tension_id == "tension_2"), None)
    assert tension_2 is not None
    assert tension_2.is_overdue == False

    print("✓ test_detects_unresolved_tensions passed")


def test_tension_health_score():
    """Test tension health score calculation."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        "unresolved_tensions": [
            {
                "tension_id": "t1",
                "description": "Tension 1",
                "introduced_scene": "scene_1",
                "expected_resolution_act": 2,
            },
        ],
    }

    structure = {
        "available": True,
        "current_act": {"act_number": 3},
    }

    result = evaluator.evaluate_film_continuity("test_film", {}, structure, memory)

    # With one overdue tension, health should be low
    assert result.tension_health < 1.0
    print("✓ test_tension_health_score passed")


# =============================================================================
# Test: Motif Callback Detection
# =============================================================================

def test_detects_missing_motif_callbacks():
    """Test that missing motif callbacks are detected."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        "motifs": [
            {
                "motif_id": "red_dress",
                "name": "Red Dress",
                "motif_type": "visual",
                "firstAppearance": "scene_3",
            },
        ],
    }

    # In act 2, the motif should have been called back
    structure = {
        "available": True,
        "current_act": {"act_number": 2},
    }

    result = evaluator.evaluate_film_continuity("test_film", {}, structure, memory)

    # The motif should be marked as overdue (no callback yet in act 2)
    motif_status = next((m for m in result.motif_statuses if m.motif_id == "red_dress"), None)
    assert motif_status is not None
    assert motif_status.is_overdue == True

    print("✓ test_detects_missing_motif_callbacks passed")


def test_motif_callback_fulfilled():
    """Test that fulfilled motif callbacks are tracked."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        "motifs": [
            {
                "motif_id": "red_dress",
                "name": "Red Dress",
                "motif_type": "visual",
                "firstAppearance": "scene_3",
                "callbackScene": "scene_15",  # Callback happened
            },
        ],
    }

    structure = {
        "available": True,
        "current_act": {"act_number": 3},
    }

    result = evaluator.evaluate_film_continuity("test_film", {}, structure, memory)

    motif_status = next((m for m in result.motif_statuses if m.motif_id == "red_dress"), None)
    assert motif_status is not None
    assert motif_status.is_fulfilled == True
    assert motif_status.is_overdue == False

    print("✓ test_motif_callback_fulfilled passed")


# =============================================================================
# Test: Character State Consistency
# =============================================================================

def test_detects_inconsistent_character_states():
    """Test that inconsistent character states are detected."""
    evaluator = MemoryArchivistEvaluator()

    # Scene 1: Character is calm
    scene1_data = {
        "scene_id": "scene_5",
        "character_appearances": ["alice"],
        "alice_emotional_state": "calm",
    }
    evaluator.evaluate_scene_continuity("scene_5", scene1_data, {}, {}, {})

    # Scene 2: Character is angry (no justification)
    scene2_data = {
        "scene_id": "scene_6",
        "character_appearances": ["alice"],
        "alice_emotional_state": "angry",
        "actions": ["Alice walks into the room"],  # No justification for anger
    }
    result = evaluator.evaluate_scene_continuity("scene_6", scene2_data, {}, {}, {})

    # Should detect inconsistency
    assert len(result.inconsistent_states) > 0
    issue = result.inconsistent_states[0]
    assert issue.character_id == "alice"
    assert "calm" in issue.previous_state.lower()
    assert "angry" in issue.current_state.lower()

    print("✓ test_detects_inconsistent_character_states passed")


def test_justified_emotional_transition():
    """Test that justified emotional transitions are not flagged."""
    evaluator = MemoryArchivistEvaluator()

    # Scene 1: Character is calm
    scene1_data = {
        "scene_id": "scene_10",
        "character_appearances": ["bob"],
        "bob_emotional_state": "calm",
    }
    evaluator.evaluate_scene_continuity("scene_10", scene1_data, {}, {}, {})

    # Scene 2: Character is angry (justified by being attacked)
    scene2_data = {
        "scene_id": "scene_11",
        "character_appearances": ["bob"],
        "bob_emotional_state": "angry",
        "actions": ["Bob was attacked by a stranger", "Bob defended himself"],
    }
    result = evaluator.evaluate_scene_continuity("scene_11", scene2_data, {}, {}, {})

    # Should NOT detect inconsistency (transition is justified)
    assert len(result.inconsistent_states) == 0

    print("✓ test_justified_emotional_transition passed")


# =============================================================================
# Test: Empty/Partial Memory Handling
# =============================================================================

def test_handles_empty_memory():
    """Test that empty memory is handled safely."""
    evaluator = MemoryArchivistEvaluator()

    result = evaluator.evaluate_film_continuity("test_film", {}, {}, {})

    # Should return a valid report, not crash
    assert result is not None
    assert result.film_id == "test_film"
    assert result.overall_health == 1.0  # Default when no data

    print("✓ test_handles_empty_memory passed")


def test_handles_no_unresolved_tensions():
    """Test that missing tensions list is handled."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        # No unresolved_tensions key
    }

    result = evaluator.evaluate_film_continuity("test_film", {}, {}, memory)

    assert result.tension_health == 1.0
    assert len(result.tension_statuses) == 0

    print("✓ test_handles_no_unresolved_tensions passed")


def test_handles_no_motifs():
    """Test that missing motifs list is handled."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        # No motifs key
    }

    result = evaluator.evaluate_film_continuity("test_film", {}, {}, memory)

    assert result.motif_health == 1.0
    assert len(result.motif_statuses) == 0

    print("✓ test_handles_no_motifs passed")


def test_handles_unavailable_spine():
    """Test that unavailable spine is handled safely."""
    evaluator = MemoryArchivistEvaluator()

    result = evaluator.evaluate_film_continuity("test_film", spine=None, structure={}, memory={})

    # Should return valid report, not crash
    assert result is not None
    assert result.film_id == "test_film"

    print("✓ test_handles_unavailable_spine passed")


# =============================================================================
# Test: Scene Continuity Report
# =============================================================================

def test_scene_continuity_report_structure():
    """Test that scene continuity report has correct structure."""
    evaluator = MemoryArchivistEvaluator()

    scene_data = {
        "scene_id": "scene_20",
        "film_id": "test_film",
        "character_appearances": ["alice", "bob"],
        "dialogue": "Hello, how are you?",
        "visual_description": "A cozy living room",
    }

    result = evaluator.evaluate_scene_continuity("scene_20", scene_data, {}, {}, {})

    assert result.scene_id == "scene_20"
    assert result.film_id == "test_film"
    assert isinstance(result.issues, list)
    assert isinstance(result.warnings, list)
    assert isinstance(result.alerts, list)
    assert isinstance(result.character_states, dict)

    print("✓ test_scene_continuity_report_structure passed")


def test_scene_continuity_passes_with_good_data():
    """Test that scene passes with good continuity data."""
    evaluator = MemoryArchivistEvaluator()

    scene_data = {
        "scene_id": "scene_25",
        "film_id": "test_film",
        "character_appearances": ["alice"],
        "alice_emotional_state": "happy",
        "dialogue": "What a lovely day!",
        "visual_description": "Sunlight streaming through windows",
    }

    result = evaluator.evaluate_scene_continuity("scene_25", scene_data, {}, {}, {})

    # Should pass with no issues
    assert result.passed == True
    assert len(result.issues) == 0
    assert len(result.warnings) == 0
    assert len(result.alerts) == 0

    print("✓ test_scene_continuity_passes_with_good_data passed")


def test_detects_scene_level_continuity_betrayal():
    """Test that obvious continuity betrayal produces at least one warning alert."""
    evaluator = MemoryArchivistEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "film_id": "test_film",
        "dialogue": "Marcus laughs as he hands Elena a coffee. Guess we figured that out pretty quickly, huh?",
        "actions": "They sit comfortably, joking easily like nothing has been building between them.",
        "intent": "They behave as if the earlier conflict never mattered.",
        "emotional_tone": "light",
        "tone": "casual",
        "visual_description": "Rain hits the window but neither character reacts to it.",
        "camera_work": "simple two-shot",
        "lighting": "neutral indoor lighting",
        "character_appearances": ["Elena", "Marcus"],
    }

    memory = {
        "available": True,
        "emotional_contract": "tension",
        "unresolved_tensions": [
            {
                "tension_id": "burial_argument",
                "description": "Elena and Marcus disagree about their father's burial.",
                "introduced_scene": "scene_3",
                "expected_resolution_act": 2,
            }
        ],
        "motifs": [
            {
                "motif_id": "rain_glass",
                "name": "rain on window glass",
                "motif_type": "visual",
            }
        ],
    }

    result = evaluator.evaluate_scene_continuity("scene_14", scene_data, {}, {}, memory)

    assert len(result.warnings) >= 1
    assert len(result.alerts) >= 1
    alert_types = {alert.alert_type for alert in result.alerts}
    assert AlertType.PAYOFF_MISSING in alert_types or AlertType.EMOTIONAL_CONTRACT_VIOLATION in alert_types

    print("✓ test_detects_scene_level_continuity_betrayal passed")


def test_sparse_context_scene_does_not_trigger_betrayal_false_positive():
    """Test that sparse scenes without continuity context do not get betrayal warnings."""
    evaluator = MemoryArchivistEvaluator()

    scene_data = {
        "scene_id": "scene_31",
        "film_id": "test_film",
        "dialogue": "They share a quiet look.",
        "actions": "A pause hangs between them.",
        "visual_description": "Rain taps the window.",
        "character_appearances": ["alice", "bob"],
    }

    result = evaluator.evaluate_scene_continuity("scene_31", scene_data, {}, {}, {})

    assert len(result.warnings) == 0
    assert len(result.alerts) == 0

    print("✓ test_sparse_context_scene_does_not_trigger_betrayal_false_positive passed")


def test_film_intelligence_absent_keeps_archivist_behavior_unchanged():
    """Missing film intelligence should not add continuity influence or extra alerts."""
    evaluator = MemoryArchivistEvaluator()
    scene_data = {
        "scene_id": "scene_40",
        "film_id": "test_film",
        "dialogue": "They sit in silence.",
        "visual_description": "A quiet room.",
        "character_appearances": ["alice"],
    }

    result = evaluator.evaluate_scene_continuity("scene_40", scene_data, {}, {}, {}, None)

    assert result.passed is True
    assert len(result.alerts) == 0
    assert result.debug_metadata["film_intelligence_influence"]["applied"] is False
    assert result.debug_metadata["film_intelligence_influence"]["available"] is False

    print("✓ test_film_intelligence_absent_keeps_archivist_behavior_unchanged passed")


def test_film_intelligence_improves_warning_specificity_for_stalled_tension():
    """Film intelligence should sharpen scene warnings for stagnating tensions."""
    evaluator = MemoryArchivistEvaluator()
    scene_data = {
        "scene_id": "scene_14",
        "film_id": "test_film",
        "dialogue": "They avoid saying what matters.",
        "actions": "They circle the table without confronting the issue.",
        "visual_description": "Rain taps the window.",
        "character_appearances": ["Elena", "Marcus"],
    }
    memory = {
        "available": True,
        "unresolved_tensions": [
            {
                "tension_id": "burial_argument",
                "description": "Elena and Marcus disagree about the burial.",
                "introduced_scene": "scene_3",
                "expected_resolution_act": 2,
            }
        ],
    }
    film_intelligence = {
        "canonical_sources": {"structure": True, "memory": True, "spine": True},
        "derived": {
            "scope": "sequence",
            "sequence": {
                "sequence_id": "seq_b",
                "arc_progression_summaries": [],
                "motif_summaries": [],
            },
            "act": {
                "act_number": 2,
                "progression_status": "grounded_progression",
                "arc_progression_summaries": [],
                "motif_summaries": [],
            },
            "film": {
                "progression_status": "grounded_progression",
            },
            "debt_payoff_arc_summary": {
                "setup_payoff_count": 2,
                "open_tension_count": 3,
                "motif_count": 0,
                "arc_count": 0,
            },
        },
    }

    result = evaluator.evaluate_scene_continuity(
        "scene_14",
        scene_data,
        {},
        {},
        memory,
        film_intelligence,
    )

    assert any("stagnating" in alert.description.lower() for alert in result.alerts)
    assert any("film-scale continuity" in warning.lower() for warning in result.warnings)
    assert result.debug_metadata["film_intelligence_influence"]["applied"] is True
    assert "tension_stagnation" in result.debug_metadata["film_intelligence_influence"]["affected_areas"]

    print("✓ test_film_intelligence_improves_warning_specificity_for_stalled_tension passed")


def test_film_intelligence_surfaces_setup_payoff_weakness_non_blocking():
    """Film intelligence can surface setup/payoff weakness without blocking the scene result."""
    evaluator = MemoryArchivistEvaluator()
    scene_data = {
        "scene_id": "scene_50",
        "film_id": "test_film",
        "dialogue": "They move on too quickly.",
        "visual_description": "A hallway with the family portrait.",
        "character_appearances": ["Elena"],
    }
    film_intelligence = {
        "canonical_sources": {"structure": True, "memory": True, "spine": False},
        "derived": {
            "scope": "act",
            "act": {
                "act_number": 3,
                "progression_status": "grounded_progression",
                "arc_progression_summaries": [],
                "motif_summaries": [],
            },
            "film": {
                "progression_status": "grounded_progression",
            },
            "debt_payoff_arc_summary": {
                "setup_payoff_count": 3,
                "open_tension_count": 0,
                "motif_count": 1,
                "arc_count": 0,
            },
        },
    }

    result = evaluator.evaluate_scene_continuity(
        "scene_50",
        scene_data,
        {},
        {},
        {"available": True},
        film_intelligence,
    )

    assert result is not None
    assert isinstance(result.warnings, list)
    assert result.debug_metadata["film_intelligence_influence"]["applied"] is True
    assert "setup_payoff_weakness" in result.debug_metadata["film_intelligence_influence"]["affected_areas"]

    print("✓ test_film_intelligence_surfaces_setup_payoff_weakness_non_blocking passed")


# =============================================================================
# Test: Missing Payoffs Detection
# =============================================================================

def test_detects_missing_payoffs_in_act3():
    """Test that missing payoffs are detected in act 3."""
    evaluator = MemoryArchivistEvaluator()

    memory = {
        "available": True,
        "act1_setups": ["the mysterious letter", "the hidden key"],
        "resolutions": [],  # No resolutions yet
    }

    structure = {
        "available": True,
        "current_act": {"act_number": 3},
    }

    result = evaluator.evaluate_scene_continuity(
        "scene_50",
        {"scene_id": "scene_50"},
        {},
        structure,
        memory
    )

    # Should detect missing payoffs
    assert len(result.missing_payoffs) > 0

    print("✓ test_detects_missing_payoffs_in_act3 passed")


# =============================================================================
# Test: Global Instance
# =============================================================================

def test_global_instance_exists():
    """Test that global memory_archivist_evaluator instance exists."""
    assert memory_archivist_evaluator is not None
    assert isinstance(memory_archivist_evaluator, MemoryArchivistEvaluator)
    print("✓ test_global_instance_exists passed")


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_existing_director_evaluator_still_works():
    """Test that director_evaluator can still be imported."""
    from app.services.director_evaluator import DirectorEvaluator
    evaluator = DirectorEvaluator()
    assert evaluator is not None
    print("✓ test_existing_director_evaluator_still_works passed")


def test_existing_spine_consumption_service_still_works():
    """Test that spine_consumption_service still works."""
    from app.services.spine_consumption_service import SpineConsumptionService
    service = SpineConsumptionService()
    assert service is not None
    print("✓ test_existing_spine_consumption_service_still_works passed")


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    """Run all memory archivist tests."""
    print("=== Memory Archivist Test Suite ===")

    tests = [
        # Tension detection
        test_detects_unresolved_tensions,
        test_tension_health_score,
        # Motif detection
        test_detects_missing_motif_callbacks,
        test_motif_callback_fulfilled,
        # Character consistency
        test_detects_inconsistent_character_states,
        test_justified_emotional_transition,
        # Empty/partial handling
        test_handles_empty_memory,
        test_handles_no_unresolved_tensions,
        test_handles_no_motifs,
        test_handles_unavailable_spine,
        # Scene continuity
        test_scene_continuity_report_structure,
        test_scene_continuity_passes_with_good_data,
        # Missing payoffs
        test_detects_missing_payoffs_in_act3,
        # Global instance
        test_global_instance_exists,
        # Backward compatibility
        test_existing_director_evaluator_still_works,
        test_existing_spine_consumption_service_still_works,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print("=== ALL TESTS PASSED ===")
    else:
        print("=== SOME TESTS FAILED ===")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
