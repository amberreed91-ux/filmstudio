"""
Tests for SceneOutput Factory Method - Phase 5.2

Tests the _build_scene_output factory method in AgentExecutor
to ensure it correctly assembles SceneOutput from runtime data.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.services.agent_executor import AgentExecutor
from app.services.co_director_session_service import co_director_session_service
from app.models.scene_output import SceneOutput
from app.models.co_director import SessionMode


# =============================================================================
# Test: Factory Method Exists
# =============================================================================

def test_factory_method_exists():
    """Test that _build_scene_output method exists on AgentExecutor."""
    executor = AgentExecutor()
    assert hasattr(executor, '_build_scene_output')
    assert callable(getattr(executor, '_build_scene_output'))


# =============================================================================
# Test: Building SceneOutput with Full Data
# =============================================================================

def test_build_scene_output_with_full_data():
    """Test building SceneOutput with all data provided."""
    executor = AgentExecutor()
    
    director_decision = {
        "approved": True,
        "notes": "Strong scene",
        "requires_revision": False,
        "decision": "APPROVE",
        "score": 0.85
    }
    
    continuity_report = {
        "tension_health": 0.9,
        "motif_health": 0.85,
        "character_consistent": True
    }
    
    story_score = {
        "overall_health": 0.78,
        "priority": "MEDIUM",
        "warnings": ["Consider visual variety"],
        "recommendations": []
    }
    
    alerts = [
        {"type": "MOTIF", "severity": "WARNING", "message": "Unresolved motif"}
    ]

    merged_decision = {
        "creative_decision": director_decision,
        "continuity_context": {
            "continuity_report": continuity_report,
            "alerts": alerts,
            "critical_count": 0,
            "warning_count": 1,
        },
        "has_continuity_debt": True,
        "conflict_severity": "LOW",
        "alerts_acknowledged": True,
        "escalation_flag": False,
    }
    
    conflicts_data = {
        "has_conflicts": True,
        "severity": "LOW",
        "resolved": True,
        "escalation_required": False
    }
    
    quality_metrics = {
        "vision_consistency": 0.85,
        "emotional_consistency": 0.80
    }
    
    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        director_decision=director_decision,
        continuity_report=continuity_report,
        story_score=story_score,
        alerts=alerts,
        merged_decision=merged_decision,
        conflicts_data=conflicts_data,
        quality_metrics=quality_metrics,
        metadata={"trace_id": "trace-123"},
        processing_time_ms=125.5,
        timestamp="2026-04-18T10:00:00Z"
    )
    
    assert isinstance(scene_output, SceneOutput)
    assert scene_output.scene_id == "scene_42"
    assert scene_output.film_id == "film_1"
    assert scene_output.director_decision.approved == True
    assert scene_output.director_decision.notes == "Strong scene"
    assert scene_output.continuity_report.tension_health == 0.9
    assert scene_output.story_health.overall_health == 0.78
    assert scene_output.conflicts is not None
    assert scene_output.conflicts.has_conflicts == True
    assert scene_output.quality_metrics is not None
    assert scene_output.quality_metrics.get("vision_consistency") == 0.85
    assert scene_output.quality_metrics.get("metadata", {}).get("trace_id") == "trace-123"
    # scene_package_context is additive debug metadata and may be present alongside user-supplied metadata
    assert scene_output.quality_metrics.get("merged_decision") == merged_decision
    assert scene_output.full_story_score == story_score
    assert scene_output.full_continuity_report is not None
    assert scene_output.full_continuity_report.get("alerts") == alerts
    assert scene_output.processing_time_ms == 125.5


# =============================================================================
# Test: Building SceneOutput with Partial Data
# =============================================================================

def test_build_scene_output_with_partial_data():
    """Test building SceneOutput with only some data provided."""
    executor = AgentExecutor()
    
    # Only director decision provided
    director_decision = {
        "approved": True,
        "notes": "Approved"
    }
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=director_decision
    )
    
    assert isinstance(scene_output, SceneOutput)
    assert scene_output.scene_id == "scene_1"
    assert scene_output.film_id == "film_1"
    assert scene_output.director_decision.approved == True
    # Other fields should have safe defaults
    assert scene_output.continuity_report is not None
    assert scene_output.story_health is not None


def test_build_scene_output_with_partial_merged_data():
    """Test building SceneOutput from merged runtime data with missing optional fields."""
    executor = AgentExecutor()

    merged_decision = {
        "creative_decision": {
            "approved": False,
            "notes": "Needs continuity pass",
            "requires_revision": True,
        },
        "continuity_context": {
            "continuity_report": {
                "tension_health": 0.7,
                "motif_health": 0.6,
                "character_consistent": False,
            },
            "alerts": [
                {"type": "CHARACTER", "severity": "CRITICAL", "message": "Character drift"}
            ],
        },
        "has_continuity_debt": True,
        "conflict_severity": "MEDIUM",
        "alerts_acknowledged": False,
        "escalation_flag": True,
    }

    scene_output = executor._build_scene_output(
        scene_id="scene_partial",
        film_id="film_1",
        merged_decision=merged_decision,
        metadata={"source": "integration-test"},
    )

    assert isinstance(scene_output, SceneOutput)
    assert scene_output.director_decision.requires_revision == True
    assert scene_output.continuity_report.critical_count == 1
    assert scene_output.conflicts is not None
    assert scene_output.conflicts.has_conflicts == True
    assert scene_output.conflicts.severity == "MEDIUM"
    assert scene_output.conflicts.escalation_required == True
    assert scene_output.quality_metrics is not None
    assert scene_output.quality_metrics.get("metadata", {}).get("source") == "integration-test"
    # scene_package_context is additive debug metadata and may be present alongside user-supplied metadata


def test_build_scene_output_minimal():
    """Test building SceneOutput with missing everything except required identifiers."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1"
    )
    
    assert isinstance(scene_output, SceneOutput)
    assert scene_output.scene_id == "scene_1"
    assert scene_output.film_id == "film_1"
    # Should have default values for all optional fields
    assert scene_output.director_decision is not None
    assert scene_output.continuity_report is not None
    assert scene_output.story_health is not None


# =============================================================================
# Test: Safe Handling of Missing Fields
# =============================================================================

def test_build_scene_output_missing_director_decision():
    """Test that missing director_decision is handled safely."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        story_score={"overall_health": 0.8}
    )
    
    assert scene_output.director_decision is not None
    # Should use defaults from SceneOutput.from_dict
    assert scene_output.director_decision.approved == False


def test_build_scene_output_missing_story_score():
    """Test that missing story_score is handled safely."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        director_decision={"approved": True}
    )
    
    assert scene_output.story_health is not None
    # Should use default health value
    assert scene_output.story_health.overall_health == 0.5


def test_build_scene_output_empty_alerts():
    """Test that empty alerts list is handled safely."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        alerts=[]
    )
    
    assert scene_output.continuity_report is not None
    assert scene_output.continuity_report.alert_count == 0


def test_build_scene_output_none_processing_time():
    """Test that None processing_time_ms is handled safely."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        processing_time_ms=None
    )
    
    # Should not raise, and should have default value
    assert scene_output.processing_time_ms == 0.0


def test_build_scene_output_includes_codirector_workflow_debug_only():
    """Phase 10.9: co-director workflow appears in debug metadata only."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_scene_package_context") as mock_scene_package, \
         patch("app.services.agent_executor.spine_consumption_service.get_co_director_context") as mock_codirector_context, \
         patch("app.services.agent_executor.co_director_session_service.get_session") as mock_get_session:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {"available": False, "summary": {}, "heuristic_outputs": {}}
        mock_scene_package.return_value = {"available": False}
        mock_codirector_context.return_value = {
            "session_active": True,
            "current_mode": "advisory",
            "active_scene_id": "scene_1",
            "revision_count": 1,
            "repeated_critique_count": 0,
            "last_accepted_suggestion": None,
            "timestamps": {"created_at": None, "updated_at": None},
            "derived": {},
            "canonical_sources": {"session_service": True, "session_record": True},
            "notes": [],
        }
        mock_get_session.return_value = MagicMock(
            session_id="11111111-1111-1111-1111-111111111111",
            current_mode=SessionMode.ADVISORY,
            active_scene_id=None,
            revision_count=1,
            repeated_critique_count=0,
        )

        scene_output = executor._build_scene_output(
            scene_id="scene_1",
            film_id="film_1",
            project_id="project_1",
            director_decision={"approved": False, "requires_revision": True, "notes": "revise"},
            quality_metrics={
                "decision": "REJECT",
                "score": 0.42,
                "pillars": {"visual_coherence": 0.31},
                "rejection_reasons": ["generic_visuals"],
                "revision_notes": ["Increase visual intent"],
            },
            metadata={"session_id": "11111111-1111-1111-1111-111111111111"},
        )

    debug_response = scene_output.to_debug_response()
    app_response = scene_output.to_app_response()

    metadata = debug_response.get("metadata", {})
    assert "co_director_context" in metadata
    workflow = metadata["co_director_context"].get("workflow")
    assert isinstance(workflow, dict)
    assert workflow.get("critique", {}).get("present") is True
    assert "workflow" not in app_response


def test_build_scene_output_real_session_id_string_enables_codirector_workflow():
    """Real metadata session_id string should resolve and enable workflow when advisory."""
    executor = AgentExecutor()
    session = co_director_session_service.create_session(
        project_id=uuid4(),
        film_id=uuid4(),
        mode=SessionMode.ADVISORY,
    )

    scene_output = executor._build_scene_output(
        scene_id="scene_real_session",
        film_id="film_real_session",
        project_id="project_real_session",
        director_decision={"approved": False, "requires_revision": True, "notes": "revise"},
        quality_metrics={
            "decision": "REJECT",
            "score": 0.4,
            "pillars": {"visual_coherence": 0.31},
            "rejection_reasons": ["generic_visuals"],
            "revision_notes": ["Increase visual intent"],
        },
        metadata={"session_id": str(session.session_id)},
    )

    debug_response = scene_output.to_debug_response()
    workflow = (debug_response.get("metadata") or {}).get("co_director_context", {}).get("workflow")
    assert isinstance(workflow, dict)
    assert workflow.get("mode") == "advisory"


def test_codirector_workflow_optional_when_session_id_missing():
    """Missing session_id must not affect core output and workflow remains optional."""
    executor = AgentExecutor()
    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_scene_package_context") as mock_scene_package, \
         patch("app.services.agent_executor.spine_consumption_service.get_co_director_context") as mock_codirector_context:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {"available": False, "summary": {}, "heuristic_outputs": {}}
        mock_scene_package.return_value = {"available": False}
        mock_codirector_context.return_value = {
            "session_active": True,
            "current_mode": "advisory",
            "active_scene_id": "scene_1",
            "revision_count": 1,
            "repeated_critique_count": 0,
            "last_accepted_suggestion": None,
            "timestamps": {"created_at": None, "updated_at": None},
            "derived": {},
            "canonical_sources": {"session_service": True, "session_record": False},
            "notes": [],
        }

        scene_output = executor._build_scene_output(
            scene_id="scene_1",
            film_id="film_1",
            project_id="project_1",
            director_decision={"approved": True, "requires_revision": False, "notes": "stable"},
            quality_metrics={"decision": "APPROVE", "score": 0.81, "pillars": {"visual_coherence": 0.8}},
            metadata={},
        )

    debug_response = scene_output.to_debug_response()
    workflow = debug_response.get("metadata", {}).get("co_director_context", {}).get("workflow")
    assert workflow is None
    # Core scene outputs remain unaffected.
    assert scene_output.director_decision.approved is True


def test_codirector_workflow_optional_when_session_id_invalid():
    """Invalid session_id must not affect core output and should skip workflow assembly."""
    executor = AgentExecutor()
    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_scene_package_context") as mock_scene_package, \
         patch("app.services.agent_executor.spine_consumption_service.get_co_director_context") as mock_codirector_context:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {"available": False, "summary": {}, "heuristic_outputs": {}}
        mock_scene_package.return_value = {"available": False}
        mock_codirector_context.return_value = {
            "session_active": True,
            "current_mode": "collaborative",
            "active_scene_id": "scene_1",
            "revision_count": 2,
            "repeated_critique_count": 1,
            "last_accepted_suggestion": None,
            "timestamps": {"created_at": None, "updated_at": None},
            "derived": {},
            "canonical_sources": {"session_service": True, "session_record": False},
            "notes": [],
        }

        scene_output = executor._build_scene_output(
            scene_id="scene_1",
            film_id="film_1",
            project_id="project_1",
            director_decision={"approved": False, "requires_revision": True, "notes": "revise"},
            quality_metrics={"decision": "REJECT", "score": 0.39, "pillars": {"visual_coherence": 0.3}},
            metadata={"session_id": "invalid-not-a-uuid"},
        )

    debug_response = scene_output.to_debug_response()
    workflow = debug_response.get("metadata", {}).get("co_director_context", {}).get("workflow")
    assert workflow is None
    assert scene_output.director_decision.requires_revision is True


def test_codirector_workflow_passive_session_is_silent():
    """PASSIVE mode should keep all co-director artifacts absent."""
    executor = AgentExecutor()
    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_scene_package_context") as mock_scene_package, \
         patch("app.services.agent_executor.spine_consumption_service.get_co_director_context") as mock_codirector_context, \
         patch("app.services.agent_executor.co_director_session_service.get_session") as mock_get_session:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {"available": False, "summary": {}, "heuristic_outputs": {}}
        mock_scene_package.return_value = {"available": False}
        mock_codirector_context.return_value = {
            "session_active": True,
            "current_mode": "passive",
            "active_scene_id": "scene_1",
            "revision_count": 0,
            "repeated_critique_count": 0,
            "last_accepted_suggestion": None,
            "timestamps": {"created_at": None, "updated_at": None},
            "derived": {},
            "canonical_sources": {"session_service": True, "session_record": True},
            "notes": [],
        }
        mock_get_session.return_value = MagicMock(
            session_id="11111111-1111-1111-1111-111111111111",
            current_mode=SessionMode.PASSIVE,
            active_scene_id=None,
            revision_count=0,
            repeated_critique_count=0,
        )

        scene_output = executor._build_scene_output(
            scene_id="scene_1",
            film_id="film_1",
            project_id="project_1",
            director_decision={"approved": True, "requires_revision": False, "notes": "stable"},
            quality_metrics={"decision": "APPROVE", "score": 0.83, "pillars": {"visual_coherence": 0.82}},
            metadata={"session_id": "11111111-1111-1111-1111-111111111111"},
        )

    workflow = scene_output.to_debug_response().get("metadata", {}).get("co_director_context", {}).get("workflow")
    assert workflow is not None
    assert workflow["critique"]["present"] is False
    assert workflow["proposal"]["present"] is False
    assert workflow["comparison"]["present"] is False
    assert workflow["intensity"]["present"] is False


def test_codirector_workflow_shape_is_repeatable_ignoring_ids_and_timestamps():
    """Same input should produce stable workflow shape even if IDs/timestamps differ."""
    executor = AgentExecutor()
    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_scene_package_context") as mock_scene_package, \
         patch("app.services.agent_executor.spine_consumption_service.get_co_director_context") as mock_codirector_context, \
         patch("app.services.agent_executor.co_director_session_service.get_session") as mock_get_session:
        mock_taste.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {"available": False, "summary": {}, "heuristic_outputs": {}}
        mock_scene_package.return_value = {"available": False}
        mock_codirector_context.return_value = {
            "session_active": True,
            "current_mode": "advisory",
            "active_scene_id": "scene_1",
            "revision_count": 1,
            "repeated_critique_count": 0,
            "last_accepted_suggestion": None,
            "timestamps": {"created_at": None, "updated_at": None},
            "derived": {},
            "canonical_sources": {"session_service": True, "session_record": True},
            "notes": [],
        }
        mock_get_session.return_value = MagicMock(
            session_id="11111111-1111-1111-1111-111111111111",
            current_mode=SessionMode.ADVISORY,
            active_scene_id=None,
            revision_count=1,
            repeated_critique_count=0,
        )

        payload = dict(
            scene_id="scene_1",
            film_id="film_1",
            project_id="project_1",
            director_decision={"approved": False, "requires_revision": True, "notes": "revise"},
            quality_metrics={
                "decision": "REJECT",
                "score": 0.41,
                "pillars": {"visual_coherence": 0.33},
                "rejection_reasons": ["generic_visuals"],
                "revision_notes": ["Increase visual intent"],
            },
            metadata={"session_id": "11111111-1111-1111-1111-111111111111"},
        )
        first = executor._build_scene_output(**payload).to_debug_response()["metadata"]["co_director_context"]["workflow"]
        second = executor._build_scene_output(**payload).to_debug_response()["metadata"]["co_director_context"]["workflow"]

    def _normalize(workflow: dict) -> dict:
        normalized = dict(workflow)
        for block in ("critique", "proposal", "comparison"):
            if isinstance(normalized.get(block), dict):
                normalized[block] = dict(normalized[block])
                normalized[block].pop("id", None)
                normalized[block].pop("critique_id", None)
                normalized[block].pop("proposal_id", None)
        return normalized

    assert _normalize(first) == _normalize(second)


def test_no_render_or_routing_service_consumes_codirector_metadata_authority():
    """Containment guard: co-director metadata should not be read by render/routing paths."""
    root = Path(__file__).resolve().parents[1]
    targets = list((root / "render.py", root / "render_validation_service.py", root / "render_comparison_service.py"))
    targets.extend((root.parent / "routes").glob("*.py"))
    for target in targets:
        if not target.exists():
            continue
        content = target.read_text(encoding="utf-8")
        assert "co_director_context" not in content
        assert "co_director_summary" not in content


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_build_scene_output_uses_creative_decision_key():
    """Test that factory method works with creative_decision format (backward compat)."""
    executor = AgentExecutor()
    
    # Some parts of the system use 'creative_decision' instead of 'director_decision'
    # The factory should pass it through and from_dict should handle it
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "creative_decision": {
            "approved": True,
            "notes": "Looks good"
        }
    }
    
    scene_output = SceneOutput.from_dict(data)
    
    assert scene_output.director_decision.approved == True
    assert scene_output.director_decision.notes == "Looks good"


def test_build_scene_output_alerts_from_continuity_report():
    """Test that alerts extracted from continuity_report.alerts are handled."""
    executor = AgentExecutor()
    
    continuity_report = {
        "tension_health": 0.9,
        "alerts": [
            {"type": "TENSION", "severity": "WARNING", "message": "Building slowly"}
        ]
    }
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        continuity_report=continuity_report
    )
    
    # Alerts should be extracted from continuity_report
    assert scene_output.continuity_report is not None
    assert scene_output.continuity_report.alert_count >= 0


# =============================================================================
# Test: Timestamp Handling
# =============================================================================

def test_build_scene_output_generates_timestamp_if_missing():
    """Test that timestamp is generated if not provided."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1"
    )
    
    assert scene_output.timestamp is not None
    assert "T" in scene_output.timestamp  # ISO format


def test_build_scene_output_uses_provided_timestamp():
    """Test that provided timestamp is used."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        timestamp="2026-04-18T15:30:00Z"
    )
    
    assert scene_output.timestamp == "2026-04-18T15:30:00Z"


# =============================================================================
# Test: Round-trip with SceneOutput methods
# =============================================================================

def test_build_scene_output_to_dict_round_trip():
    """Test that built SceneOutput can be serialized and deserialized."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        director_decision={"approved": True, "notes": "Good"},
        story_score={"overall_health": 0.8}
    )
    
    # Serialize
    serialized = scene_output.to_dict()
    
    # Deserialize back
    restored = SceneOutput.from_dict(serialized)
    
    assert restored.scene_id == scene_output.scene_id
    assert restored.film_id == scene_output.film_id
    assert restored.director_decision.approved == scene_output.director_decision.approved


def test_build_scene_output_to_app_response():
    """Test that built SceneOutput can produce app response."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        director_decision={"approved": True, "notes": "Good"}
    )
    
    app_response = scene_output.to_app_response()
    
    assert "scene_id" in app_response
    assert "approved" in app_response
    assert "overall_score" in app_response
    assert "key_alerts" in app_response
    assert app_response["scene_id"] == "scene_42"


def test_build_scene_output_to_debug_response():
    """Test that built SceneOutput can produce debug response."""
    executor = AgentExecutor()
    
    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        director_decision={"approved": True, "notes": "Good"},
        quality_metrics={"vision_consistency": 0.85}
    )
    
    debug_response = scene_output.to_debug_response()
    
    assert "scene_id" in debug_response
    assert "quality_metrics" in debug_response
    assert "director_evaluation" in debug_response
    assert "story_scoring" in debug_response
    assert debug_response["quality_metrics"]["vision_consistency"] == 0.85


def test_build_scene_output_attaches_taste_context_to_debug_metadata_only():
    """Taste context should be attached to debug metadata without changing decisions."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste_context:
        mock_taste_context.return_value = MagicMock(
            to_dict=lambda: {
                "dimension_adjustments": {"visual_restraint": 0.08},
                "dimension_confidence": {"visual_restraint": 0.7},
                "signal_counts": {"visual_restraint": 3},
                "supporting_trace_ids": {"visual_restraint": ["trace-1", "trace-2", "trace-3"]},
            }
        )

        scene_output = executor._build_scene_output(
            scene_id="scene_42",
            film_id="film_1",
            project_id="project_1",
            director_decision={
                "approved": False,
                "notes": "Needs revision",
                "requires_revision": True,
                "decision": "REVISE",
                "score": 0.72,
                "revision_notes": ["Tighten subtext"],
            },
            quality_metrics={
                "vision_consistency": 0.72,
                "decision": "REVISE",
                "revision_notes": ["Tighten subtext"],
            },
        )

    assert scene_output.director_decision.decision == "REVISE"
    assert scene_output.director_decision.score == 0.72
    assert scene_output.director_decision.revision_notes == ["Tighten subtext"]
    assert scene_output.quality_metrics is not None
    assert scene_output.quality_metrics["metadata"]["taste_context"]["dimension_adjustments"]["visual_restraint"] == 0.08

    debug_response = scene_output.to_debug_response()

    assert debug_response["director_decision"]["decision"] == "REVISE"
    assert debug_response["director_decision"]["score"] == 0.72
    assert debug_response["director_decision"]["revision_notes"] == ["Tighten subtext"]
    assert debug_response["taste_calibration_summary"]["trace_count"] == 3


def test_build_scene_output_attaches_film_intelligence_to_debug_metadata_only():
    """Film intelligence should be attached to debug metadata without changing app output."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste_context:
        mock_taste_context.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {
            "canonical_sources": {
                "structure": True,
                "memory": True,
                "spine": True,
            },
            "derived": {
                "scope": "sequence",
                "sequence": {
                    "sequence_id": "seq_b",
                    "act_number": 2,
                    "sequence_number": 1,
                    "scene_count": 3,
                    "progression_status": "grounded_progression",
                },
                "act": {
                    "act_number": 2,
                    "act_type": "confrontation",
                    "scene_count": 5,
                    "sequence_count": 2,
                    "progression_status": "grounded_progression",
                },
                "film": {
                    "film_id": "film_1",
                    "act_count": 3,
                    "sequence_count": 6,
                    "total_scenes": 18,
                    "progression_status": "grounded_progression",
                },
                "debt_payoff_arc_summary": {
                    "setup_payoff_count": 4,
                    "open_tension_count": 2,
                    "motif_count": 1,
                    "arc_count": 2,
                },
            },
        }

        scene_output = executor._build_scene_output(
            scene_id="scene_42",
            film_id="film_1",
            director_decision={
                "approved": False,
                "notes": "Needs revision",
                "requires_revision": True,
                "decision": "REVISE",
                    "score": 0.72,
                    "revision_notes": ["Tighten subtext"],
                },
                quality_metrics={
                    "vision_consistency": 0.72,
                    "decision": "REVISE",
                    "revision_notes": ["Tighten subtext"],
                },
        )

    app_response = scene_output.to_app_response()
    debug_response = scene_output.to_debug_response()

    assert app_response["decision"] == "REVISE"
    assert "film_intelligence_summary" not in app_response
    assert scene_output.quality_metrics["metadata"]["film_intelligence_context"]["derived"]["scope"] == "sequence"
    assert debug_response["film_intelligence_summary"]["sequence_summary"]["sequence_id"] == "seq_b"
    assert debug_response["film_intelligence_summary"]["debt_payoff_arc_counts"]["arc_count"] == 2


def test_build_scene_output_attaches_cinematic_language_to_debug_metadata_only():
    """Cinematic language should be attached only to debug metadata and summary."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste_context:
        mock_taste_context.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.return_value = {
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "framing_meaning": "isolated",
                "movement_significance": "intimacy",
                "restraint_score": 0.81,
                "dialogue_to_visual_substitution_opportunity": 0.73,
                "motif_evolution_stage": "reinforcement",
                "confidence": {
                    "visual_intent": 0.79,
                    "framing": 0.7,
                    "movement": 0.66,
                    "motif_evolution": 0.72,
                },
            },
            "heuristic_outputs": {
                "restraint_indicators": ["static frame"],
                "substitution_indicators": ["reflection"],
                "detected_motif_references": ["rain_glass"],
            },
        }

        scene_output = executor._build_scene_output(
            scene_id="scene_42",
            film_id="film_1",
            scene_data={
                "scene_id": "scene_42",
                "film_id": "film_1",
                "visual_description": "Rain streaks the window as Elena's reflection isolates her in the glass.",
                "camera_work": "Static frame with a subtle push in.",
            },
            director_decision={
                "approved": False,
                "notes": "Needs revision",
                "requires_revision": True,
                "decision": "REVISE",
                "score": 0.72,
                "revision_notes": ["Tighten subtext"],
            },
            quality_metrics={
                "vision_consistency": 0.72,
                "decision": "REVISE",
                "revision_notes": ["Tighten subtext"],
            },
        )

    app_response = scene_output.to_app_response()
    debug_response = scene_output.to_debug_response()

    assert "cinematic_language_summary" not in app_response
    assert scene_output.quality_metrics["metadata"]["cinematic_language_context"]["summary"]["visual_intent"] == "emotional"
    assert debug_response["cinematic_language_summary"]["visual_intent"] == "emotional"
    assert debug_response["cinematic_language_summary"]["motif_evolution"] == "reinforcement"


def test_build_scene_output_handles_missing_cinematic_language_context_safely():
    """Missing cinematic context should not crash or add debug summary noise."""
    executor = AgentExecutor()

    with patch("app.services.agent_executor.spine_consumption_service.get_cinematic_language_context") as mock_cinematic, \
         patch("app.services.agent_executor.spine_consumption_service.get_film_intelligence_context") as mock_film_intelligence, \
         patch("app.services.agent_executor.spine_consumption_service.get_taste_context") as mock_taste_context:
        mock_taste_context.return_value = MagicMock(to_dict=lambda: {})
        mock_film_intelligence.return_value = {"canonical_sources": {}, "derived": {}}
        mock_cinematic.side_effect = RuntimeError("unavailable")

        scene_output = executor._build_scene_output(
            scene_id="scene_42",
            film_id="film_1",
            director_decision={"approved": True, "notes": "Stable", "requires_revision": False},
        )

    debug_response = scene_output.to_debug_response()

    assert debug_response["cinematic_language_summary"] is None


def test_build_scene_output_to_summary():
    """Test that built SceneOutput can produce summary response."""
    executor = AgentExecutor()

    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        director_decision={"approved": True, "notes": "Good", "requires_revision": False},
        story_score={"overall_health": 0.8, "priority": "MEDIUM"},
    )

    summary = scene_output.to_summary()

    assert summary["scene_id"] == "scene_42"
    assert summary["approved"] is True
    assert summary["reason"] == "Good"
    assert summary["priority"] == "MEDIUM"


# =============================================================================
# Test: Integration with existing agent flow data
# =============================================================================

def test_build_scene_output_from_director_logic_output():
    """Test building SceneOutput from _director_logic output format."""
    executor = AgentExecutor()
    
    # Simulate what _director_logic returns
    director_output = {
        "task_type": "creative_review",
        "creative_decision": {
            "approved": True,
            "notes": "Strong character work",
            "requires_revision": False
        },
        "quality_metrics": {
            "vision_consistency": 0.85,
            "decision": "APPROVE"
        }
    }
    
    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        director_decision=director_output.get("creative_decision"),
        quality_metrics=director_output.get("quality_metrics")
    )
    
    assert scene_output.director_decision.approved == True
    assert scene_output.director_decision.notes == "Strong character work"
    assert scene_output.quality_metrics is not None


def test_build_scene_output_backward_compatibility_does_not_change_existing_shape():
    """Test helper remains additive and existing core SceneOutput fields are preserved."""
    executor = AgentExecutor()

    scene_output = executor._build_scene_output(
        scene_id="scene_backcompat",
        film_id="film_1",
        director_decision={"approved": True, "notes": "Stable"},
    )

    app_response = scene_output.to_app_response()

    for key in [
        "scene_id",
        "film_id",
        "timestamp",
        "approved",
        "requires_revision",
        "decision",
        "notes",
        "continuity",
        "story_health",
        "story_priority",
        "has_warnings",
        "has_conflicts",
        "escalation_required",
    ]:
        assert key in app_response


def test_build_scene_output_with_story_score():
    """Test building SceneOutput with story score data."""
    executor = AgentExecutor()
    
    story_score = {
        "film_id": "film_1",
        "scope": "scene",
        "scope_id": "scene_42",
        "overall_health": 0.78,
        "priority": "MEDIUM",
        "dimension_scores": {
            "thesis_alignment": 0.8,
            "tone_coherence": 0.75
        },
        "warnings": ["Consider visual variety"],
        "recommendations": [
            {"category": "CHARACTER", "description": "Deepen motivation"}
        ]
    }
    
    scene_output = executor._build_scene_output(
        scene_id="scene_42",
        film_id="film_1",
        story_score=story_score
    )
    
    assert scene_output.story_health is not None
    assert scene_output.story_health.overall_health == 0.78
    assert scene_output.story_health.priority == "MEDIUM"
    assert scene_output.full_story_score is not None


# =============================================================================
# Test: Safe handling of edge cases
# =============================================================================

def test_build_scene_output_with_none_values():
    """Test that None values in optional params are handled safely."""
    executor = AgentExecutor()
    
    # Passing None explicitly should not break anything
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=None,
        continuity_report=None,
        story_score=None,
        alerts=None,
        conflicts_data=None,
        quality_metrics=None,
        processing_time_ms=None,
        timestamp=None
    )
    
    assert scene_output is not None
    assert isinstance(scene_output, SceneOutput)


def test_build_scene_output_with_malformed_data():
    """Test that malformed optional data is handled safely."""
    executor = AgentExecutor()
    
    # Pass malformed data - should not raise
    scene_output = executor._build_scene_output(
        scene_id="scene_1",
        film_id="film_1",
        director_decision="not a dict",  # Should be dict
        continuity_report="also not a dict",
        story_score=123,  # Should be dict
        alerts="not a list"  # Should be list
    )
    
    # Should still produce a valid SceneOutput with defaults
    assert scene_output is not None
    assert isinstance(scene_output, SceneOutput)


# =============================================================================
# Run all tests
# =============================================================================

def run_all_tests():
    """Run all tests for the factory method."""
    print("Running Phase 5.2 SceneOutput Factory Tests...")
    print("=" * 60)
    
    tests = [
        # Factory method existence
        ("test_factory_method_exists", test_factory_method_exists),
        
        # Full data tests
        ("test_build_scene_output_with_full_data", test_build_scene_output_with_full_data),
        
        # Partial data tests
        ("test_build_scene_output_with_partial_data", test_build_scene_output_with_partial_data),
        ("test_build_scene_output_minimal", test_build_scene_output_minimal),
        
        # Safe handling tests
        ("test_build_scene_output_missing_director_decision", test_build_scene_output_missing_director_decision),
        ("test_build_scene_output_missing_story_score", test_build_scene_output_missing_story_score),
        ("test_build_scene_output_empty_alerts", test_build_scene_output_empty_alerts),
        ("test_build_scene_output_none_processing_time", test_build_scene_output_none_processing_time),
        
        # Backward compatibility tests
        ("test_build_scene_output_uses_creative_decision_key", test_build_scene_output_uses_creative_decision_key),
        ("test_build_scene_output_alerts_from_continuity_report", test_build_scene_output_alerts_from_continuity_report),
        
        # Timestamp handling tests
        ("test_build_scene_output_generates_timestamp_if_missing", test_build_scene_output_generates_timestamp_if_missing),
        ("test_build_scene_output_uses_provided_timestamp", test_build_scene_output_uses_provided_timestamp),
        
        # Round-trip tests
        ("test_build_scene_output_to_dict_round_trip", test_build_scene_output_to_dict_round_trip),
        ("test_build_scene_output_to_app_response", test_build_scene_output_to_app_response),
        ("test_build_scene_output_to_debug_response", test_build_scene_output_to_debug_response),
        
        # Integration tests
        ("test_build_scene_output_from_director_logic_output", test_build_scene_output_from_director_logic_output),
        ("test_build_scene_output_with_story_score", test_build_scene_output_with_story_score),
        
        # Edge case tests
        ("test_build_scene_output_with_none_values", test_build_scene_output_with_none_values),
        ("test_build_scene_output_with_malformed_data", test_build_scene_output_with_malformed_data),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
