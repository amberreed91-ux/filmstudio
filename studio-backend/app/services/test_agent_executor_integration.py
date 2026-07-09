"""
Tests for Agent Executor Integration - Phase 3.4.4

These tests verify:
a. MEMORY_ARCHIVIST role dispatch reaches _memory_archivist_logic
b. Continuity reports are returned correctly
c. Missing data is handled safely
d. Existing agent behavior is not broken
"""

import sys
import os

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from unittest.mock import patch, MagicMock
from unittest.mock import MagicMock, AsyncMock

from app.models.crew import AgentRole, CrewTask, TaskType, TaskInput
from app.services.agent_executor import AgentExecutor
from app.services.memory_archivist import memory_archivist_evaluator, ContinuityHealthReport, SceneContinuityReport
from app.services.spine_consumption_service import SpineConsumptionService
from app.models.memory import FilmLevelMemory
from app.models.crew import FilmStructure

# =============================================================================
# Test: MEMORY_ARCHIVIST Role Dispatch
# =============================================================================

def test_memory_archivist_role_exists():
    """Test that MEMORY_ARCHIVIST role exists in AgentRole enum."""
    assert hasattr(AgentRole, 'MEMORY_ARCHIVIST')
    assert AgentRole.MEMORY_ARCHIVIST.value == "memory_archivist"
    print("✓ test_memory_archivist_role_exists passed")

def test_executor_has_memory_archivist_logic():
    """Test that AgentExecutor has _memory_archivist_logic method."""
    executor = AgentExecutor()
    assert hasattr(executor, '_memory_archivist_logic')
    assert callable(getattr(executor, '_memory_archivist_logic'))
    print("✓ test_executor_has_memory_archivist_logic passed")

def test_memory_archivist_imported_in_executor():
    """Test that memory_archivist_evaluator is imported in agent_executor."""
    from app.services import agent_executor
    assert hasattr(agent_executor, 'memory_archivist_evaluator')
    assert agent_executor.memory_archivist_evaluator is not None
    print("✓ test_memory_archivist_imported_in_executor passed")

# =============================================================================
# Test: Memory Archivist Logic - Scene Level
# =============================================================================

def test_memory_archivist_scene_evaluation():
    """Test scene-level continuity evaluation through executor."""
    executor = AgentExecutor()
    
    # Create a mock task for MEMORY_ARCHIVIST
    task = CrewTask(
        task_id="test_task_1",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_45",
            "film_id": "test_film",
            "scene_data": {"scene_id": "scene_45", "film_id": "test_film"},
            "evaluation_mode": "scene"
        })
    )
    
    # Run the logic synchronously for testing
    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )
    
    assert result["task_type"] == "continuity_analysis"
    assert "continuity_report" in result
    assert result["continuity_report"]["report_type"] == "scene"
    assert result["continuity_report"]["scene_id"] == "scene_45"
    print("✓ test_memory_archivist_scene_evaluation passed")

def test_memory_archivist_film_evaluation():
    """Test film-level continuity evaluation through executor."""
    executor = AgentExecutor()
    
    # Create a mock task for MEMORY_ARCHIVIST with film-level evaluation
    task = CrewTask(
        task_id="test_task_2",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "film_id": "test_film",
            "evaluation_mode": "film"
        })
    )
    
    # Run the logic synchronously for testing
    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )
    
    assert result["task_type"] == "continuity_analysis"
    assert "continuity_report" in result
    assert result["continuity_report"]["report_type"] == "film"
    assert result["continuity_report"]["film_id"] == "test_film"
    print("✓ test_memory_archivist_film_evaluation passed")

# =============================================================================
# Test: Missing Data Handling
# =============================================================================

def test_memory_archivist_handles_missing_film_data():
    """Test that Memory Archivist handles missing film data gracefully."""
    executor = AgentExecutor()
    
    # Task with non-existent film
    task = CrewTask(
        task_id="test_task_3",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_1",
            "film_id": "nonexistent_film",
            "evaluation_mode": "scene"
        })
    )
    
    # Run the logic - should not raise, should handle gracefully
    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )
    
    # Should still return a result structure, just with limited data
    assert result["task_type"] == "continuity_analysis"
    assert "continuity_report" in result


def test_memory_archivist_attaches_film_intelligence_debug_metadata():
    """Executor should preserve film-intelligence continuity provenance in debug-oriented payloads."""
    executor = AgentExecutor()
    task = CrewTask(
        task_id="test_task_film_intel",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_45",
            "film_id": "test_film",
            "scene_data": {"scene_id": "scene_45", "film_id": "test_film"},
            "evaluation_mode": "scene"
        })
    )

    with patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence:
        mock_film_intelligence.return_value = {
            "canonical_sources": {"structure": True, "memory": True, "spine": False},
            "derived": {
                "scope": "sequence",
                "sequence": {"sequence_id": "seq_1"},
                "film": {"progression_status": "grounded_progression"},
                "debt_payoff_arc_summary": {
                    "setup_payoff_count": 2,
                    "open_tension_count": 2,
                    "motif_count": 1,
                    "arc_count": 0,
                },
            },
        }

        result = asyncio.run(
            executor._memory_archivist_logic(task)
        )

    assert result["task_type"] == "continuity_analysis"
    assert "debug_metadata" in result["continuity_report"]
    influence = result["continuity_report"]["debug_metadata"]["film_intelligence_influence"]
    assert influence["available"] is True
    assert "affected_areas" in influence
    # alerts may be empty or contain info messages about missing data
    print("✓ test_memory_archivist_handles_missing_film_data passed")

def test_memory_archivist_handles_missing_scene_data():
    """Test that Memory Archivist handles missing scene data gracefully."""
    executor = AgentExecutor()
    
    # Task with no scene_data
    task = CrewTask(
        task_id="test_task_4",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "film_id": "test_film",
            "evaluation_mode": "scene"
            # No scene_id or scene_data provided
        })
    )
    
    # Run the logic - should not raise
    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )
    
    assert result["task_type"] == "continuity_analysis"
    print("✓ test_memory_archivist_handles_missing_scene_data passed")


def test_memory_archivist_handles_none_scene_data():
    """Test that Memory Archivist handles scene_data=None safely."""
    executor = AgentExecutor()

    task = CrewTask(
        task_id="test_task_none_scene_data",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_bad_1",
            "film_id": "film_missing_everything",
            "scene_data": None,
            "evaluation_mode": "scene"
        })
    )

    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )

    assert result["task_type"] == "continuity_analysis"
    assert "continuity_report" in result
    assert result["continuity_report"]["report_type"] == "scene"
    assert result["continuity_report"]["scene_id"] == "scene_bad_1"
    print("✓ test_memory_archivist_handles_none_scene_data passed")


def test_memory_archivist_handles_wrong_type_scene_data():
    """Test that Memory Archivist handles non-dict scene_data safely."""
    executor = AgentExecutor()

    task = CrewTask(
        task_id="test_task_wrong_type_scene_data",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_bad_type_1",
            "film_id": "film_missing_everything",
            "scene_data": "not-a-dict",
            "evaluation_mode": "scene"
        })
    )

    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )

    assert result["task_type"] == "continuity_analysis"
    assert "continuity_report" in result
    assert result["continuity_report"]["report_type"] == "scene"
    assert result["continuity_report"]["scene_id"] == "scene_bad_type_1"
    print("✓ test_memory_archivist_handles_wrong_type_scene_data passed")


def test_memory_archivist_valid_scene_data_still_works():
    """Test that existing valid dict scene_data path still works."""
    executor = AgentExecutor()

    task = CrewTask(
        task_id="test_task_valid_scene_data",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_valid_1",
            "film_id": "test_film",
            "scene_data": {"existing_key": "existing_value"},
            "evaluation_mode": "scene"
        })
    )

    result = asyncio.run(
        executor._memory_archivist_logic(task)
    )

    assert result["task_type"] == "continuity_analysis"
    assert "continuity_report" in result
    assert result["continuity_report"]["report_type"] == "scene"
    assert result["continuity_report"]["scene_id"] == "scene_valid_1"
    print("✓ test_memory_archivist_valid_scene_data_still_works passed")

# =============================================================================
# Test: Dispatch Integration
# =============================================================================

def test_dispatch_routes_to_memory_archivist():
    """Test that _run_agent_logic routes MEMORY_ARCHIVIST to _memory_archivist_logic."""
    executor = AgentExecutor()
    
    # Create a mock task for MEMORY_ARCHIVIST
    task = CrewTask(
        task_id="test_task_5",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_10",
            "film_id": "test_film",
            "evaluation_mode": "scene"
        })
    )
    
    # Run the dispatch
    result = asyncio.run(
        executor._run_agent_logic(task)
    )
    
    # Should have executed memory archivist logic
    assert result["agent_role"] == "memory_archivist"
    assert result["task_type"] == "continuity_analysis"
    print("✓ test_dispatch_routes_to_memory_archivist passed")

# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_existing_roles_still_work():
    """Test that existing roles still dispatch correctly."""
    executor = AgentExecutor()
    
    # Test DIRECTOR dispatch
    director_task = CrewTask(
        task_id="test_director",
        project_id="test_project",
        agent_role=AgentRole.DIRECTOR,
        task_type=TaskType.REVIEW,
        input=TaskInput(data={
            "scene_id": "scene_1",
            "film_id": "test_film",
            "scene_data": {}
        })
    )
    
    result = asyncio.run(
        executor._run_agent_logic(director_task)
    )
    
    assert result["agent_role"] == "director"
    assert "creative_decision" in result
    print("✓ test_existing_roles_still_work passed")


def test_director_logic_includes_bounded_taste_influence_provenance():
    """Director logic should expose bounded taste influence when context exists."""
    executor = AgentExecutor()

    task = CrewTask(
        task_id="test_director_taste",
        project_id="test_project",
        agent_role=AgentRole.DIRECTOR,
        task_type=TaskType.REVIEW,
        input=TaskInput(data={
            "scene_id": "scene_1",
            "film_id": "test_film",
            "scene_data": {
                "scene_id": "scene_1",
                "dialogue": "I keep pretending I can hold this together.",
                "actions": "Marcus stays quiet.",
                "intent": "reveals the siblings avoiding direct grief",
                "emotional_tone": "tension",
                "tone": "dramatic",
                "visual_description": "Rain streaks the window as her reflection blurs.",
                "camera_work": "static frame with a subtle reframing that isolates Elena without cutting",
                "character_appearances": ["Elena", "Marcus"],
            }
        })
    )

    with patch("app.services.agent_executor.spine_consumption_service.get_context_for_role") as mock_context, \
         patch("app.services.agent_executor.spine_consumption_service.get_structure_context") as mock_structure, \
         patch("app.services.agent_executor.spine_consumption_service.get_memory_context") as mock_memory, \
         patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste:
        mock_context.return_value = {
            "available": True,
            "story_thesis": "grief forces a fractured family to face each other honestly",
            "emotional_contract": "tension",
            "tone": "dramatic",
            "visual_style": "intimate realism with emotionally motivated framing",
            "constraints": {
                "prefer_subtext_over_exposition": True,
                "reject_obvious_dialogue": True,
                "enforce_tone_consistency": True,
                "require_visual_intent": True,
            },
        }
        mock_structure.return_value = {"available": True, "current_act": {"act_type": "CONFRONTATION"}}
        mock_memory.return_value = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}
        mock_taste.return_value = MagicMock(
            to_dict=lambda: {
                "dimension_adjustments": {"subtext_level": 0.08},
                "dimension_confidence": {"subtext_level": 0.7},
                "signal_counts": {"subtext_level": 3},
            }
        )

        result = asyncio.run(
            executor._director_logic(task)
        )

    assert "taste_influence" in result["quality_metrics"]
    assert abs(result["quality_metrics"]["taste_influence"]["total_score_delta"]) <= 0.05
    print("✓ test_director_logic_includes_bounded_taste_influence_provenance passed")


def test_director_logic_includes_bounded_cinematic_influence_provenance():
    """Director logic should expose bounded cinematic influence when present."""
    executor = AgentExecutor()

    task = CrewTask(
        task_id="test_director_cinematic",
        project_id="test_project",
        agent_role=AgentRole.DIRECTOR,
        task_type=TaskType.REVIEW,
        input=TaskInput(data={
            "scene_id": "scene_1",
            "film_id": "test_film",
            "scene_data": {
                "scene_id": "scene_1",
                "dialogue": "I keep pretending I can hold this together.",
                "actions": "Marcus stays quiet.",
                "intent": "reveals the siblings avoiding direct grief",
                "emotional_tone": "tension",
                "tone": "dramatic",
                "visual_description": "Rain streaks the window as her reflection blurs.",
                "camera_work": "static frame with a subtle reframing that isolates Elena without cutting",
                "character_appearances": ["Elena", "Marcus"],
            }
        })
    )

    with patch("app.services.agent_executor.spine_consumption_service.get_context_for_role") as mock_context, \
         patch("app.services.agent_executor.spine_consumption_service.get_structure_context") as mock_structure, \
         patch("app.services.agent_executor.spine_consumption_service.get_memory_context") as mock_memory, \
         patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic:
        mock_context.return_value = {
            "available": True,
            "story_thesis": "grief forces a fractured family to face each other honestly",
            "emotional_contract": "tension",
            "tone": "dramatic",
            "visual_style": "intimate realism with emotionally motivated framing",
            "constraints": {
                "prefer_subtext_over_exposition": True,
                "reject_obvious_dialogue": True,
                "enforce_tone_consistency": True,
                "require_visual_intent": True,
            },
        }
        mock_structure.return_value = {"available": True, "current_act": {"act_type": "CONFRONTATION"}}
        mock_memory.return_value = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_cinematic.return_value = {
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "restraint_score": 0.84,
                "dialogue_to_visual_substitution_opportunity": 0.86,
                "confidence": {"visual_intent": 0.81},
            },
            "heuristic_outputs": {
                "visual_intent_confidence": 0.81,
                "substitution_indicators": ["reflection"],
            },
        }

        result = asyncio.run(
            executor._director_logic(task)
        )

    assert "cinematic_influence" in result["quality_metrics"]
    assert abs(result["quality_metrics"]["cinematic_influence"]["total_score_delta"]) <= 0.05
    assert "affected_signals" in result["quality_metrics"]["cinematic_influence"]
    assert "generated_notes" in result["quality_metrics"]["cinematic_influence"]


def test_build_scene_output_preserves_cinematic_language_debug_visibility_only():
    """Executor should preserve cinematic language metadata only in debug-oriented output."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "framing_meaning": "isolated",
                "movement_significance": "intimacy",
                "restraint_score": 0.8,
                "dialogue_to_visual_substitution_opportunity": 0.71,
                "motif_evolution_stage": "development",
                "confidence": {
                    "visual_intent": 0.77,
                    "framing": 0.66,
                    "movement": 0.64,
                    "motif_evolution": 0.69,
                },
            },
            "heuristic_outputs": {
                "restraint_indicators": ["static frame"],
                "substitution_indicators": ["reflection"],
                "detected_motif_references": ["rain_glass"],
            },
        }

        scene_output = executor._build_scene_output(
            scene_id="scene_1",
            film_id="test_film",
            scene_data={
                "scene_id": "scene_1",
                "film_id": "test_film",
                "visual_description": "Rain on glass fractures Elena's reflection.",
                "camera_work": "Static frame with a subtle reframing.",
            },
            director_decision={"approved": True, "notes": "Stable", "requires_revision": False},
        )

    app_response = scene_output.to_app_response()
    debug_response = scene_output.to_debug_response()

    assert "cinematic_language_summary" not in app_response
    assert debug_response["cinematic_language_summary"]["visual_intent"] == "emotional"
    assert scene_output.quality_metrics["metadata"]["cinematic_language_context"]["summary"]["motif_evolution_stage"] == "development"


def test_build_scene_output_handles_sparse_cinematic_language_context_without_crashing():
    """Sparse cinematic context should remain non-blocking and debug-safe."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {"available": False, "summary": {}, "heuristic_outputs": {}}

        scene_output = executor._build_scene_output(
            scene_id="scene_1",
            film_id="test_film",
            director_decision={"approved": True, "notes": "Stable", "requires_revision": False},
        )

    assert scene_output is not None
    assert scene_output.to_debug_response()["cinematic_language_summary"] is None
    assert scene_output.to_app_response()["approved"] is True

def test_existing_agent_executor_still_works():
    """Test that existing AgentExecutor can be instantiated and used."""
    executor = AgentExecutor()
    assert executor is not None
    assert executor.state is not None
    print("✓ test_existing_agent_executor_still_works passed")

def test_memory_archivist_does_not_override_director():
    """Test that Memory Archivist does not have blocking/override behavior."""
    executor = AgentExecutor()
    
    # Memory Archivist should return analysis, not decisions
    task = CrewTask(
        task_id="test_task_6",
        project_id="test_project",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        task_type=TaskType.VALIDATION,
        input=TaskInput(data={
            "scene_id": "scene_1",
            "film_id": "test_film",
            "evaluation_mode": "scene"
        })
    )
    
    result = asyncio.run(
        executor._run_agent_logic(task)
    )
    
    # Memory Archivist returns continuity_report, not creative_decision
    assert "continuity_report" in result
    assert "creative_decision" not in result
    # It should not have 'approved' or 'requires_revision' like Director
    assert "approved" not in result.get("creative_decision", {})
    print("✓ test_memory_archivist_does_not_override_director passed")

# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    print("=== Agent Executor Integration Test Suite (Phase 3.4.4) ===")
    tests = [
        # MEMORY_ARCHIVIST role exists
        test_memory_archivist_role_exists,
        test_executor_has_memory_archivist_logic,
        test_memory_archivist_imported_in_executor,
        
        # Scene and film evaluation
        test_memory_archivist_scene_evaluation,
        test_memory_archivist_film_evaluation,
        
        # Missing data handling
        test_memory_archivist_handles_missing_film_data,
        test_memory_archivist_handles_missing_scene_data,
        test_memory_archivist_handles_none_scene_data,
        test_memory_archivist_handles_wrong_type_scene_data,
        test_memory_archivist_valid_scene_data_still_works,
        
        # Dispatch integration
        test_dispatch_routes_to_memory_archivist,
        
        # Backward compatibility
        test_existing_roles_still_work,
        test_existing_agent_executor_still_works,
        test_memory_archivist_does_not_override_director,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"=== Test Results ===")
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
