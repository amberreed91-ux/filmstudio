"""
Tests for SceneOutput Model - Phase 5.1

This module tests the unified output model for scene-level runtime results.
"""

import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, 'studio-backend')

from app.models.scene_output import (
    DirectorDecisionSummary,
    ContinuityReportSummary,
    StoryHealthSummary,
    ConflictSummary,
    SceneOutput,
)
from app.services.director_evaluator import Decision


# =============================================================================
# Helper Functions
# =============================================================================

def create_minimal_scene_output() -> SceneOutput:
    """Create a minimal SceneOutput for testing."""
    return SceneOutput(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(approved=True),
        continuity_report=ContinuityReportSummary(),
        story_health=StoryHealthSummary(),
    )


def create_full_scene_output() -> SceneOutput:
    """Create a SceneOutput with all fields populated."""
    return SceneOutput(
        scene_id="scene_42",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(
            approved=True,
            notes="Strong scene with good character development",
            requires_revision=False,
            decision="APPROVE",
            score=0.85,
            revision_notes=["Consider tightening the dialogue in beat 2"]
        ),
        continuity_report=ContinuityReportSummary(
            has_alerts=True,
            alert_count=2,
            critical_count=0,
            warning_count=2,
            tension_health=0.9,
            motif_health=0.85,
            character_consistent=True
        ),
        story_health=StoryHealthSummary(
            overall_health=0.78,
            priority="MEDIUM",
            has_warnings=True,
            warning_count=1,
            recommendation_count=2
        ),
        conflicts=ConflictSummary(
            has_conflicts=True,
            severity="LOW",
            resolved=True,
            escalation_required=False
        ),
        timestamp="2026-04-18T10:00:00Z",
        quality_metrics={
            "vision_consistency": 0.85,
            "emotional_consistency": 0.80,
            "continuity_score": 0.90
        },
        processing_time_ms=125.5,
        full_story_score={
            "film_id": "film_1",
            "scope": "scene",
            "scope_id": "scene_42",
            "overall_health": 0.78,
            "dimension_scores": {
                "thesis_alignment": 0.8,
                "tone_coherence": 0.75,
                "character_progression": 0.85,
                "emotional_trajectory": 0.70,
                "motif_continuity": 0.80,
                "tension_resolution_rate": 0.75,
                "originality_score": 0.72,
                "continuity_debt_trajectory": 0.85
            },
            "warnings": ["Consider adding more visual variety"],
            "recommendations": [
                {"category": "CHARACTER", "priority": "MEDIUM", "description": "Deepen character motivation"}
            ]
        },
        full_continuity_report={
            "tension_health": 0.9,
            "motif_health": 0.85,
            "alerts": [
                {"type": "MOTIF", "severity": "WARNING", "message": "Unresolved motif callback"},
                {"type": "TENSION", "severity": "WARNING", "message": "Tension building slowly"}
            ]
        },
        revision_priority="MEDIUM"
    )


# =============================================================================
# Test: Model Construction
# =============================================================================

def test_director_decision_summary_construction():
    """Test DirectorDecisionSummary construction with various parameters."""
    # Minimal
    dd = DirectorDecisionSummary(approved=True)
    assert dd.approved is True
    assert dd.notes == ""
    assert dd.requires_revision is False
    assert dd.decision == "REJECT"
    assert dd.score == 0.0
    assert dd.revision_notes == []

    # Full
    dd = DirectorDecisionSummary(
        approved=False,
        notes="Needs work",
        requires_revision=True,
        decision="REVISE",
        score=0.45,
        revision_notes=["Fix pacing", "Add visual interest"]
    )
    assert dd.approved is False
    assert dd.notes == "Needs work"
    assert dd.requires_revision is True
    assert dd.decision == "REVISE"
    assert dd.score == 0.45
    assert len(dd.revision_notes) == 2


def test_continuity_report_summary_construction():
    """Test ContinuityReportSummary construction."""
    # Default
    cr = ContinuityReportSummary()
    assert cr.has_alerts is False
    assert cr.alert_count == 0
    assert cr.critical_count == 0
    assert cr.warning_count == 0
    assert cr.tension_health == 1.0
    assert cr.motif_health == 1.0
    assert cr.character_consistent is True

    # With alerts
    cr = ContinuityReportSummary(
        has_alerts=True,
        alert_count=3,
        critical_count=1,
        warning_count=2,
        tension_health=0.7,
        motif_health=0.65,
        character_consistent=False
    )
    assert cr.has_alerts is True
    assert cr.alert_count == 3
    assert cr.critical_count == 1
    assert cr.warning_count == 2
    assert cr.tension_health == 0.7
    assert cr.motif_health == 0.65
    assert cr.character_consistent is False


def test_story_health_summary_construction():
    """Test StoryHealthSummary construction."""
    # Default
    sh = StoryHealthSummary()
    assert sh.overall_health == 0.5
    assert sh.priority == "LOW"
    assert sh.has_warnings is False
    assert sh.warning_count == 0
    assert sh.recommendation_count == 0

    # With data
    sh = StoryHealthSummary(
        overall_health=0.65,
        priority="HIGH",
        has_warnings=True,
        warning_count=3,
        recommendation_count=5
    )
    assert sh.overall_health == 0.65
    assert sh.priority == "HIGH"
    assert sh.has_warnings is True
    assert sh.warning_count == 3
    assert sh.recommendation_count == 5


def test_conflict_summary_construction():
    """Test ConflictSummary construction."""
    # Default
    c = ConflictSummary()
    assert c.has_conflicts is False
    assert c.severity is None
    assert c.resolved is True
    assert c.escalation_required is False

    # With conflicts
    c = ConflictSummary(
        has_conflicts=True,
        severity="HIGH",
        resolved=False,
        escalation_required=True
    )
    assert c.has_conflicts is True
    assert c.severity == "HIGH"
    assert c.resolved is False
    assert c.escalation_required is True


def test_scene_output_minimal_construction():
    """Test SceneOutput construction with minimal required fields."""
    output = create_minimal_scene_output()
    
    assert output.scene_id == "scene_1"
    assert output.film_id == "film_1"
    assert output.director_decision.approved is True
    assert output.continuity_report.has_alerts is False
    assert output.story_health.overall_health == 0.5
    assert output.conflicts is None
    assert output.quality_metrics is None
    assert output.processing_time_ms == 0.0
    assert output.full_story_score is None
    assert output.full_continuity_report is None


def test_scene_output_full_construction():
    """Test SceneOutput construction with all fields."""
    output = create_full_scene_output()
    
    assert output.scene_id == "scene_42"
    assert output.film_id == "film_1"
    assert output.director_decision.approved is True
    assert output.director_decision.score == 0.85
    assert output.continuity_report.alert_count == 2
    assert output.story_health.priority == "MEDIUM"
    assert output.conflicts is not None
    assert output.conflicts.severity == "LOW"
    assert output.quality_metrics is not None
    assert output.processing_time_ms == 125.5
    assert output.full_story_score is not None
    assert output.full_continuity_report is not None


def test_scene_output_timestamp_auto_generation():
    """Test that timestamp is auto-generated if not provided."""
    output = SceneOutput(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(approved=True),
        continuity_report=ContinuityReportSummary(),
        story_health=StoryHealthSummary(),
    )
    
    assert output.timestamp != ""
    assert output.timestamp.endswith("Z")
    # Should be valid ISO format
    datetime.fromisoformat(output.timestamp.replace("Z", "+00:00"))


def test_scene_output_timestamp_preserved():
    """Test that provided timestamp is preserved."""
    custom_timestamp = "2026-01-15T09:30:00Z"
    output = SceneOutput(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(approved=True),
        continuity_report=ContinuityReportSummary(),
        story_health=StoryHealthSummary(),
        timestamp=custom_timestamp
    )
    
    assert output.timestamp == custom_timestamp


# =============================================================================
# Test: Optional Field Handling
# =============================================================================

def test_optional_conflicts_none():
    """Test SceneOutput with conflicts=None."""
    output = create_minimal_scene_output()
    assert output.conflicts is None


def test_optional_conflicts_populated():
    """Test SceneOutput with conflicts populated."""
    output = create_full_scene_output()
    assert output.conflicts is not None
    assert output.conflicts.has_conflicts is True


def test_optional_quality_metrics_none():
    """Test SceneOutput with quality_metrics=None."""
    output = create_minimal_scene_output()
    assert output.quality_metrics is None


def test_optional_quality_metrics_populated():
    """Test SceneOutput with quality_metrics populated."""
    output = create_full_scene_output()
    assert output.quality_metrics is not None
    assert "vision_consistency" in output.quality_metrics


def test_optional_full_story_score_none():
    """Test SceneOutput with full_story_score=None."""
    output = create_minimal_scene_output()
    assert output.full_story_score is None


def test_optional_full_story_score_populated():
    """Test SceneOutput with full_story_score populated."""
    output = create_full_scene_output()
    assert output.full_story_score is not None
    assert "dimension_scores" in output.full_story_score


def test_optional_full_continuity_report_none():
    """Test SceneOutput with full_continuity_report=None."""
    output = create_minimal_scene_output()
    assert output.full_continuity_report is None


def test_optional_full_continuity_report_populated():
    """Test SceneOutput with full_continuity_report populated."""
    output = create_full_scene_output()
    assert output.full_continuity_report is not None
    assert "alerts" in output.full_continuity_report


# =============================================================================
# Test: Helper Methods (to_dict)
# =============================================================================

def test_director_decision_summary_to_dict():
    """Test DirectorDecisionSummary.to_dict()."""
    dd = DirectorDecisionSummary(
        approved=True,
        notes="Good work",
        requires_revision=False,
        decision="APPROVE",
        score=0.9,
        revision_notes=["Minor note"]
    )
    
    result = dd.to_dict()
    assert result["approved"] is True
    assert result["notes"] == "Good work"
    assert result["requires_revision"] is False
    assert result["decision"] == "APPROVE"
    assert result["score"] == 0.9
    assert result["revision_notes"] == ["Minor note"]


def test_continuity_report_summary_to_dict():
    """Test ContinuityReportSummary.to_dict()."""
    cr = ContinuityReportSummary(
        has_alerts=True,
        alert_count=2,
        critical_count=1,
        warning_count=1,
        tension_health=0.8,
        motif_health=0.75,
        character_consistent=True
    )
    
    result = cr.to_dict()
    assert result["has_alerts"] is True
    assert result["alert_count"] == 2
    assert result["critical_count"] == 1
    assert result["warning_count"] == 1
    assert result["tension_health"] == 0.8
    assert result["motif_health"] == 0.75
    assert result["character_consistent"] is True


def test_story_health_summary_to_dict():
    """Test StoryHealthSummary.to_dict()."""
    sh = StoryHealthSummary(
        overall_health=0.72,
        priority="MEDIUM",
        has_warnings=True,
        warning_count=2,
        recommendation_count=3
    )
    
    result = sh.to_dict()
    assert result["overall_health"] == 0.72
    assert result["priority"] == "MEDIUM"
    assert result["has_warnings"] is True
    assert result["warning_count"] == 2
    assert result["recommendation_count"] == 3


def test_conflict_summary_to_dict():
    """Test ConflictSummary.to_dict()."""
    c = ConflictSummary(
        has_conflicts=True,
        severity="HIGH",
        resolved=False,
        escalation_required=True
    )
    
    result = c.to_dict()
    assert result["has_conflicts"] is True
    assert result["severity"] == "HIGH"
    assert result["resolved"] is False
    assert result["escalation_required"] is True


# =============================================================================
# Test: App Response Conversion
# =============================================================================

def test_to_app_response_minimal():
    """Test to_app_response with minimal SceneOutput."""
    output = create_minimal_scene_output()
    response = output.to_app_response()
    
    # Should have identity fields
    assert "scene_id" in response
    assert "film_id" in response
    assert "timestamp" in response
    
    # Should have core decision fields
    assert "approved" in response
    assert "requires_revision" in response
    assert "decision" in response
    assert "notes" in response
    assert "overall_score" in response
    
    # Should have continuity summary
    assert "continuity" in response
    assert isinstance(response["continuity"], dict)
    
    # Should have story health fields
    assert "story_health" in response
    assert "overall_health" in response
    assert "story_priority" in response
    assert "priority" in response
    assert "has_warnings" in response
    assert "key_alerts" in response
    assert "key_issues" in response
    assert "revision_notes" in response
    assert "recommendations" in response
    
    # Should have conflict summary
    assert "has_conflicts" in response
    assert "escalation_required" in response
    
    # Should NOT have internal fields
    assert "quality_metrics" not in response
    assert "processing_time_ms" not in response
    assert "full_story_score" not in response


def test_to_app_response_full():
    """Test to_app_response with full SceneOutput."""
    output = create_full_scene_output()
    response = output.to_app_response()
    
    # Should have all app-facing fields
    assert response["scene_id"] == "scene_42"
    assert response["film_id"] == "film_1"
    assert response["approved"] is True
    assert response["decision"] == "APPROVE"
    assert response["overall_score"] == 0.85
    assert response["story_health"] == 0.78
    assert response["overall_health"] == 0.78
    assert response["story_priority"] == "MEDIUM"
    assert response["priority"] == "MEDIUM"
    assert response["has_conflicts"] is True
    assert response["escalation_required"] is False
    assert len(response["key_alerts"]) == 2
    assert len(response["key_issues"]) == 2
    assert response["revision_notes"] == ["Consider tightening the dialogue in beat 2"]
    assert response["recommendations"] == [
        {"category": "CHARACTER", "priority": "MEDIUM", "description": "Deepen character motivation"}
    ]
    
    # Continuity should be a dict
    assert isinstance(response["continuity"], dict)
    assert response["continuity"]["has_alerts"] is True
    assert response["continuity"]["alert_count"] == 2


def test_to_app_response_normalizes_decision_enum():
    """Test that to_app_response converts enum decisions to strings."""
    output = create_minimal_scene_output()
    output.director_decision.decision = Decision.REJECT

    response = output.to_app_response()

    assert response["decision"] == "REJECT"
    assert isinstance(response["decision"], str)


def test_to_app_response_excludes_internal_fields():
    """Test that to_app_response excludes internal/debug fields."""
    output = create_full_scene_output()
    response = output.to_app_response()
    
    # Internal fields should not be present
    assert "quality_metrics" not in response
    assert "processing_time_ms" not in response
    assert "full_story_score" not in response
    assert "full_continuity_report" not in response
    assert "revision_priority" not in response
    assert "quality_metrics" not in response
    assert "metadata" not in response


# =============================================================================
# Test: Debug Response Conversion
# =============================================================================

def test_to_debug_response_minimal():
    """Test to_debug_response with minimal SceneOutput."""
    output = create_minimal_scene_output()
    response = output.to_debug_response()
    
    # Should have all fields including internal
    assert "scene_id" in response
    assert "film_id" in response
    assert "timestamp" in response
    assert "director_decision" in response
    assert "continuity_report" in response
    assert "story_health" in response
    assert "conflicts" in response
    assert "quality_metrics" in response
    assert "processing_time_ms" in response
    assert "full_story_score" in response
    assert "full_continuity_report" in response
    assert "alerts" in response
    assert "metadata" in response
    assert "director_evaluation" in response
    assert "continuity_analysis" in response
    assert "conflict_resolution" in response
    assert "story_scoring" in response


def test_to_debug_response_full():
    """Test to_debug_response with full SceneOutput."""
    output = create_full_scene_output()
    response = output.to_debug_response()
    
    # Should have all fields
    assert response["scene_id"] == "scene_42"
    assert response["film_id"] == "film_1"
    assert response["director_decision"]["approved"] is True
    assert response["continuity_report"]["alert_count"] == 2
    assert response["story_health"]["overall_health"] == 0.78
    assert response["conflicts"]["severity"] == "LOW"
    assert response["quality_metrics"]["vision_consistency"] == 0.85
    assert response["processing_time_ms"] == 125.5
    assert response["full_story_score"]["overall_health"] == 0.78
    assert response["full_continuity_report"]["tension_health"] == 0.9
    assert len(response["alerts"]) == 2
    assert response["director_evaluation"]["decision"] == "APPROVE"
    assert response["continuity_analysis"]["full_report"]["tension_health"] == 0.9
    assert response["conflict_resolution"]["summary"]["severity"] == "LOW"
    assert response["story_scoring"]["breakdown"]["overall_health"] == 0.78


def test_to_debug_response_includes_taste_calibration_summary():
    """Taste calibration should be visible only in debug output."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "taste_context": {
            "dimension_adjustments": {
                "visual_restraint": 0.08,
                "subtext_level": 0.05,
            },
            "dimension_confidence": {
                "visual_restraint": 0.7,
                "subtext_level": 0.5,
            },
            "signal_counts": {
                "visual_restraint": 3,
                "subtext_level": 2,
            },
        }
    }

    response = output.to_debug_response()

    assert response["taste_calibration_summary"]["dimensions"] == [
        "subtext_level",
        "visual_restraint",
    ]
    assert response["taste_calibration_summary"]["values"]["visual_restraint"] == 0.08
    assert response["taste_calibration_summary"]["confidence"]["subtext_level"] == 0.5
    assert response["taste_calibration_summary"]["trace_count"] == 5


def test_to_debug_response_includes_film_intelligence_summary():
    """Film intelligence should be visible only in debug output."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "film_intelligence_context": {
            "canonical_sources": {
                "structure": True,
                "memory": True,
                "spine": False,
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
    }

    response = output.to_debug_response()

    assert response["film_intelligence_summary"]["scope"] == "sequence"
    assert response["film_intelligence_summary"]["canonical_sources"]["structure"] is True
    assert response["film_intelligence_summary"]["sequence_summary"]["sequence_id"] == "seq_b"
    assert response["film_intelligence_summary"]["act_summary"]["act_number"] == 2
    assert response["film_intelligence_summary"]["film_summary"]["total_scenes"] == 18
    assert response["film_intelligence_summary"]["debt_payoff_arc_counts"]["open_tension_count"] == 2


def test_to_debug_response_includes_cinematic_language_summary():
    """Cinematic language should appear only in the debug response when meaningful."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "cinematic_language_context": {
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "framing_meaning": "isolated",
                "movement_significance": "intimacy",
                "restraint_score": 0.82,
                "dialogue_to_visual_substitution_opportunity": 0.74,
                "motif_evolution_stage": "reinforcement",
                "confidence": {
                    "visual_intent": 0.8,
                    "framing": 0.7,
                    "movement": 0.65,
                    "motif_evolution": 0.75,
                },
            },
        }
    }

    response = output.to_debug_response()

    assert response["cinematic_language_summary"]["visual_intent"] == "emotional"
    assert response["cinematic_language_summary"]["framing_meaning"] == "isolated"
    assert response["cinematic_language_summary"]["movement_significance"] == "intimacy"
    assert response["cinematic_language_summary"]["restraint_score"] == 0.82
    assert response["cinematic_language_summary"]["dialogue_substitution"] == 0.74
    assert response["cinematic_language_summary"]["motif_evolution"] == "reinforcement"
    assert response["cinematic_language_summary"]["available"] is True


def test_to_debug_response_handles_sparse_cinematic_language_metadata_safely():
    """Sparse cinematic metadata should not crash or force a summary."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "cinematic_language_context": {
            "available": False,
            "summary": {},
        }
    }

    response = output.to_debug_response()

    assert response["cinematic_language_summary"] is None


def test_to_debug_response_preserves_continuity_film_intelligence_provenance():
    """Continuity debug payload should preserve Archivist film-intelligence provenance."""
    output = create_full_scene_output()
    output.full_continuity_report = {
        "tension_health": 0.8,
        "motif_health": 0.7,
        "alerts": [],
        "debug_metadata": {
            "film_intelligence_influence": {
                "applied": True,
                "available": True,
                "affected_areas": ["tension_stagnation", "setup_payoff_weakness"],
                "signal_strength": "grounded",
            }
        },
    }

    response = output.to_debug_response()

    assert response["continuity_analysis"]["full_report"]["debug_metadata"]["film_intelligence_influence"]["applied"] is True
    assert "tension_stagnation" in response["continuity_analysis"]["full_report"]["debug_metadata"]["film_intelligence_influence"]["affected_areas"]


def test_film_intelligence_debug_visibility_does_not_change_app_response():
    """Film intelligence debug metadata must not alter app-facing output."""
    output = create_full_scene_output()
    original_app_response = output.to_app_response()
    output.quality_metrics["metadata"] = {
        "film_intelligence_context": {
            "canonical_sources": {"structure": True, "memory": True, "spine": True},
            "derived": {
                "scope": "film",
                "film": {
                    "film_id": "film_1",
                    "act_count": 3,
                    "sequence_count": 6,
                    "total_scenes": 18,
                    "progression_status": "grounded_progression",
                },
                "debt_payoff_arc_summary": {
                    "setup_payoff_count": 2,
                    "open_tension_count": 1,
                    "motif_count": 1,
                    "arc_count": 2,
                },
            },
        }
    }

    updated_app_response = output.to_app_response()

    assert updated_app_response == original_app_response
    assert "film_intelligence_summary" not in updated_app_response


def test_cinematic_language_debug_visibility_does_not_change_app_or_summary_response():
    """Cinematic language debug metadata must not alter app or summary views."""
    output = create_full_scene_output()
    original_app_response = output.to_app_response()
    original_summary_response = output.to_summary()
    output.quality_metrics["metadata"] = {
        "cinematic_language_context": {
            "available": True,
            "summary": {
                "visual_intent": "narrative",
                "framing_meaning": "connected",
                "movement_significance": "observation",
                "restraint_score": 0.68,
                "dialogue_to_visual_substitution_opportunity": 0.59,
                "motif_evolution_stage": "development",
                "confidence": {
                    "visual_intent": 0.75,
                    "framing": 0.62,
                    "movement": 0.66,
                    "motif_evolution": 0.61,
                },
            },
        }
    }

    updated_app_response = output.to_app_response()
    updated_summary_response = output.to_summary()
    debug_response = output.to_debug_response()

    assert updated_app_response == original_app_response
    assert updated_summary_response == original_summary_response
    assert "cinematic_language_summary" not in updated_app_response
    assert "cinematic_language_summary" not in updated_summary_response
    assert debug_response["cinematic_language_summary"]["visual_intent"] == "narrative"


def test_to_debug_response_normalizes_decision_enum():
    """Test that to_debug_response converts enum decisions to strings."""
    output = create_full_scene_output()
    output.director_decision.decision = Decision.REJECT
    output.quality_metrics["decision"] = Decision.REJECT

    response = output.to_debug_response()

    assert response["director_decision"]["decision"] == "REJECT"
    assert response["director_evaluation"]["decision"] == "REJECT"
    assert response["quality_metrics"]["decision"] == "REJECT"
    assert isinstance(response["director_decision"]["decision"], str)
    assert isinstance(response["quality_metrics"]["decision"], str)


def test_to_debug_response_normalizes_nested_merged_decision_enum():
    """Test that nested merged decision quality-metric enums are normalized."""
    output = create_full_scene_output()
    output.quality_metrics["merged_decision"] = {
        "quality_metrics": {
            "decision": Decision.REVISE,
            "vision_consistency": 0.79,
        },
        "creative_decision": {
            "approved": False,
            "requires_revision": True,
        },
    }

    response = output.to_debug_response()

    assert response["quality_metrics"]["merged_decision"]["quality_metrics"]["decision"] == "REVISE"
    assert response["conflict_resolution"]["merged_decision"]["quality_metrics"]["decision"] == "REVISE"
    assert isinstance(
        response["quality_metrics"]["merged_decision"]["quality_metrics"]["decision"],
        str,
    )


def test_to_debug_response_preserves_plain_string_nested_merged_decision():
    """Test that nested merged decision string values are preserved."""
    output = create_full_scene_output()
    output.quality_metrics["merged_decision"] = {
        "quality_metrics": {
            "decision": "REVISE",
            "vision_consistency": 0.79,
        }
    }

    response = output.to_debug_response()

    assert response["quality_metrics"]["merged_decision"]["quality_metrics"]["decision"] == "REVISE"
    assert response["conflict_resolution"]["merged_decision"]["quality_metrics"]["decision"] == "REVISE"


def test_to_debug_response_includes_internal_fields():
    """Test that to_debug_response includes internal/debug fields."""
    output = create_full_scene_output()
    response = output.to_debug_response()
    
    # Internal fields should be present
    assert "quality_metrics" in response
    assert "processing_time_ms" in response
    assert "full_story_score" in response
    assert "full_continuity_report" in response
    assert "revision_priority" in response
    assert "alerts" in response
    assert "director_evaluation" in response
    assert "continuity_analysis" in response
    assert "conflict_resolution" in response
    assert "story_scoring" in response


def test_taste_debug_visibility_does_not_change_core_decision_fields():
    """Taste debug metadata must not alter decision, score, or revision notes."""
    output = create_full_scene_output()
    original_decision = output.director_decision.decision
    original_score = output.director_decision.score
    original_revision_notes = list(output.director_decision.revision_notes)

    output.quality_metrics["metadata"] = {
        "taste_context": {
            "dimension_adjustments": {"visual_restraint": 0.08},
            "dimension_confidence": {"visual_restraint": 0.7},
            "signal_counts": {"visual_restraint": 3},
        }
    }

    debug_response = output.to_debug_response()

    assert debug_response["director_decision"]["decision"] == original_decision
    assert debug_response["director_decision"]["score"] == original_score
    assert debug_response["director_decision"]["revision_notes"] == original_revision_notes


def test_to_debug_response_handles_sparse_film_intelligence_metadata_safely():
    """Sparse film-intelligence debug metadata should not break debug serialization."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "film_intelligence_context": {
            "canonical_sources": {
                "structure": False,
                "memory": False,
                "spine": False,
            },
            "derived": {
                "scope": "film",
            },
        }
    }

    response = output.to_debug_response()

    assert response["film_intelligence_summary"] is None


def test_to_debug_response_includes_taste_influence_provenance():
    """Debug response should expose applied taste influence separately from taste context."""
    output = create_full_scene_output()
    output.quality_metrics["taste_influence"] = {
        "applied": True,
        "affected_dimensions": ["subtext_level"],
        "total_score_delta": -0.012,
        "adjustments": {"subtext_level": -0.012},
        "confidence": {"subtext_level": 0.7},
        "signal_counts": {"subtext_level": 3},
    }

    response = output.to_debug_response()

    assert response["taste_influence"]["applied"] is True
    assert response["taste_influence"]["affected_dimensions"] == ["subtext_level"]
    assert response["taste_influence"]["total_score_delta"] == -0.012


def test_to_debug_response_includes_cinematic_influence_provenance():
    """Debug response should expose cinematic influence separately from context metadata."""
    output = create_full_scene_output()
    output.quality_metrics["cinematic_influence"] = {
        "applied": True,
        "affected_signals": ["restrained_visual_intent_support", "dialogue_to_visual_substitution_note"],
        "total_score_delta": 0.015,
        "adjustments": {"restrained_visual_intent_support": 0.015},
        "confidence": {
            "restrained_visual_intent_support": 0.79,
            "dialogue_to_visual_substitution_note": 0.86,
        },
        "generated_notes": ["Let the frame carry more of the meaning before the dialogue states it"],
    }

    response = output.to_debug_response()

    assert response["cinematic_influence"]["applied"] is True
    assert "restrained_visual_intent_support" in response["cinematic_influence"]["affected_signals"]
    assert response["cinematic_influence"]["total_score_delta"] == 0.015
    assert any("frame carry more of the meaning" in note.lower() for note in response["cinematic_influence"]["generated_notes"])


# =============================================================================
# Test: Summary Conversion
# =============================================================================

def test_to_summary_minimal():
    """Test to_summary with minimal SceneOutput."""
    output = create_minimal_scene_output()
    response = output.to_summary()

    assert response["scene_id"] == "scene_1"
    assert response["film_id"] == "film_1"
    assert response["decision"] == "REJECT"
    assert response["approved"] is True
    assert "reason" in response
    assert response["priority"] == "LOW"
    assert response["overall_health"] == 0.5


def test_to_summary_full():
    """Test to_summary with full SceneOutput."""
    output = create_full_scene_output()
    response = output.to_summary()

    assert response["scene_id"] == "scene_42"
    assert response["decision"] == "APPROVE"
    assert response["approved"] is True
    assert response["reason"] == "Strong scene with good character development"
    assert response["priority"] == "MEDIUM"
    assert response["overall_health"] == 0.78


def test_to_summary_normalizes_decision_enum():
    """Test that to_summary converts enum decisions to strings."""
    output = create_minimal_scene_output()
    output.director_decision.decision = Decision.REJECT

    response = output.to_summary()

    assert response["decision"] == "REJECT"
    assert isinstance(response["decision"], str)


def test_plain_string_decision_values_still_work():
    """Test that existing string decisions are preserved."""
    output = create_full_scene_output()

    app_response = output.to_app_response()
    debug_response = output.to_debug_response()
    summary_response = output.to_summary()

    assert app_response["decision"] == "APPROVE"
    assert debug_response["director_decision"]["decision"] == "APPROVE"
    assert summary_response["decision"] == "APPROVE"


# =============================================================================
# Test: to_dict (Default Serialization)
# =============================================================================

def test_to_dict_equals_debug_response():
    """Test that to_dict() returns same as to_debug_response()."""
    output = create_full_scene_output()
    
    assert output.to_dict() == output.to_debug_response()


def test_to_dict_minimal():
    """Test to_dict with minimal SceneOutput."""
    output = create_minimal_scene_output()
    result = output.to_dict()
    
    assert "scene_id" in result
    assert "film_id" in result
    assert result["full_story_score"] is None
    assert result["quality_metrics"] is None


# =============================================================================
# Test: from_dict (Deserialization)
# =============================================================================

def test_from_dict_minimal():
    """Test from_dict with minimal data."""
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "creative_decision": {"approved": True}
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.scene_id == "scene_1"
    assert output.film_id == "film_1"
    assert output.director_decision.approved is True
    assert output.continuity_report.has_alerts is False
    assert output.story_health.overall_health == 0.5


def test_from_dict_with_story_score():
    """Test from_dict with story_score data."""
    data = {
        "scene_id": "scene_5",
        "film_id": "film_1",
        "creative_decision": {"approved": False, "notes": "Needs revision"},
        "story_score": {
            "overall_health": 0.65,
            "warnings": ["Warning 1"],
            "recommendations": [{"category": "TEST", "priority": "HIGH", "description": "Rec"}],
            "priority": "MEDIUM"
        }
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.scene_id == "scene_5"
    assert output.director_decision.approved is False
    assert output.director_decision.notes == "Needs revision"
    assert output.story_health.overall_health == 0.65
    assert output.story_health.priority == "MEDIUM"
    assert output.story_health.has_warnings is True
    assert output.story_health.warning_count == 1
    assert output.story_health.recommendation_count == 1


def test_from_dict_with_continuity_alerts():
    """Test from_dict with continuity alerts."""
    data = {
        "scene_id": "scene_3",
        "film_id": "film_1",
        "creative_decision": {"approved": True},
        "alerts": [
            {"severity": "CRITICAL", "type": "TENSION"},
            {"severity": "WARNING", "type": "MOTIF"},
            {"severity": "WARNING", "type": "CHARACTER"}
        ]
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.continuity_report.has_alerts is True
    assert output.continuity_report.alert_count == 3
    assert output.continuity_report.critical_count == 1
    assert output.continuity_report.warning_count == 2


def test_from_dict_with_conflicts():
    """Test from_dict with conflict data."""
    data = {
        "scene_id": "scene_7",
        "film_id": "film_1",
        "creative_decision": {"approved": True},
        "has_conflicts": True,
        "conflict_severity": "HIGH",
        "escalation_flag": True
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.conflicts is not None
    assert output.conflicts.has_conflicts is True
    assert output.conflicts.severity == "HIGH"
    assert output.conflicts.escalation_required is True


def test_from_dict_with_full_data():
    """Test from_dict with complete data."""
    data = {
        "scene_id": "scene_10",
        "film_id": "film_1",
        "creative_decision": {
            "approved": True,
            "notes": "Excellent work",
            "requires_revision": False
        },
        "quality_metrics": {
            "decision": "APPROVE",
            "vision_consistency": 0.92,
            "revision_notes": ["Note 1"]
        },
        "story_score": {
            "overall_health": 0.88,
            "warnings": [],
            "recommendations": [],
            "priority": "LOW"
        },
        "alerts": [],
        "timestamp": "2026-04-18T12:00:00Z",
        "processing_time_ms": 85.3
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.scene_id == "scene_10"
    assert output.film_id == "film_1"
    assert output.director_decision.approved is True
    assert output.director_decision.notes == "Excellent work"
    assert output.director_decision.decision == "APPROVE"
    assert output.director_decision.score == 0.92
    assert output.story_health.overall_health == 0.88
    assert output.timestamp == "2026-04-18T12:00:00Z"
    assert output.processing_time_ms == 85.3


def test_from_dict_missing_fields():
    """Test from_dict with missing fields uses defaults."""
    data = {
        "scene_id": "scene_1"
        # Missing film_id, creative_decision, etc.
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.scene_id == "scene_1"
    assert output.film_id == ""  # Default empty string
    assert output.director_decision.approved is False  # Default
    assert output.story_health.overall_health == 0.5  # Default


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_backward_compat_director_approved_field():
    """Test that 'approved' field from director output is preserved."""
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "creative_decision": {"approved": True}
    }
    
    output = SceneOutput.from_dict(data)
    response = output.to_app_response()
    
    assert response["approved"] is True


def test_backward_compat_director_notes_field():
    """Test that 'notes' field from director output is preserved."""
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "creative_decision": {"approved": True, "notes": "Good dialogue"}
    }
    
    output = SceneOutput.from_dict(data)
    response = output.to_app_response()
    
    assert response["notes"] == "Good dialogue"


def test_backward_compat_story_score_dict():
    """Test that story_score dict is preserved in full_story_score."""
    story_score = {
        "overall_health": 0.75,
        "dimension_scores": {"thesis_alignment": 0.8},
        "warnings": [],
        "recommendations": []
    }
    
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "story_score": story_score
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.full_story_score is not None
    assert output.full_story_score["overall_health"] == 0.75
    assert "dimension_scores" in output.full_story_score


def test_backward_compat_alerts_list():
    """Test that alerts list is preserved in full_continuity_report."""
    alerts = [
        {"severity": "WARNING", "type": "MOTIF", "message": "Unresolved"}
    ]
    
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "alerts": alerts
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.full_continuity_report is not None
    assert "alerts" in output.full_continuity_report
    assert len(output.full_continuity_report["alerts"]) == 1


def test_backward_compat_quality_metrics():
    """Test that quality_metrics is preserved."""
    metrics = {
        "vision_consistency": 0.85,
        "emotional_consistency": 0.80
    }
    
    data = {
        "scene_id": "scene_1",
        "film_id": "film_1",
        "quality_metrics": metrics
    }
    
    output = SceneOutput.from_dict(data)
    
    assert output.quality_metrics is not None
    assert output.quality_metrics["vision_consistency"] == 0.85


# =============================================================================
# Test: Round-trip Serialization
# =============================================================================

def test_round_trip_full():
    """Test that to_dict -> from_dict produces equivalent object."""
    original = create_full_scene_output()
    
    # Serialize then deserialize
    serialized = original.to_dict()
    restored = SceneOutput.from_dict(serialized)
    
    # Core fields should match
    assert restored.scene_id == original.scene_id
    assert restored.film_id == original.film_id
    assert restored.director_decision.approved == original.director_decision.approved
    assert restored.director_decision.notes == original.director_decision.notes
    assert restored.continuity_report.alert_count == original.continuity_report.alert_count
    assert restored.story_health.overall_health == original.story_health.overall_health
    assert restored.conflicts is not None and original.conflicts is not None
    assert restored.conflicts.severity == original.conflicts.severity


def test_round_trip_minimal():
    """Test that to_dict -> from_dict works for minimal object."""
    original = create_minimal_scene_output()
    
    serialized = original.to_dict()
    restored = SceneOutput.from_dict(serialized)
    
    assert restored.scene_id == original.scene_id
    assert restored.film_id == original.film_id
    assert restored.director_decision.approved == original.director_decision.approved


# =============================================================================
# Test: Edge Cases
# =============================================================================

def test_edge_case_empty_revision_notes():
    """Test with empty revision_notes list."""
    output = SceneOutput(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(
            approved=True,
            revision_notes=[]
        ),
        continuity_report=ContinuityReportSummary(),
        story_health=StoryHealthSummary()
    )
    
    assert output.director_decision.revision_notes == []


def test_edge_case_zero_processing_time():
    """Test with zero processing_time_ms."""
    output = SceneOutput(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(approved=True),
        continuity_report=ContinuityReportSummary(),
        story_health=StoryHealthSummary(),
        processing_time_ms=0.0
    )
    
    assert output.processing_time_ms == 0.0


def test_edge_case_boundary_health_values():
    """Test with boundary health values (0.0 and 1.0)."""
    output = SceneOutput(
        scene_id="scene_1",
        film_id="film_1",
        director_decision=DirectorDecisionSummary(approved=True),
        continuity_report=ContinuityReportSummary(
            tension_health=0.0,
            motif_health=1.0
        ),
        story_health=StoryHealthSummary(
            overall_health=0.0
        )
    )
    
    assert output.continuity_report.tension_health == 0.0
    assert output.continuity_report.motif_health == 1.0
    assert output.story_health.overall_health == 0.0


def test_edge_case_all_priorities():
    """Test with all priority values."""
    for priority in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        output = SceneOutput(
            scene_id="scene_1",
            film_id="film_1",
            director_decision=DirectorDecisionSummary(approved=True),
            continuity_report=ContinuityReportSummary(),
            story_health=StoryHealthSummary(priority=priority)
        )
        assert output.story_health.priority == priority


def test_edge_case_all_decisions():
    """Test with all decision values."""
    for decision in ["APPROVE", "REVISE", "REJECT"]:
        output = SceneOutput(
            scene_id="scene_1",
            film_id="film_1",
            director_decision=DirectorDecisionSummary(
                approved=(decision == "APPROVE"),
                decision=decision
            ),
            continuity_report=ContinuityReportSummary(),
            story_health=StoryHealthSummary()
        )
        assert output.director_decision.decision == decision


# =============================================================================
# Phase 9.3 Tests: Scene Package Debug Visibility
# =============================================================================

def _make_scene_package_context(
    narrative_purpose: str = "Introduce the protagonist's flaw",
    emotional_target: str = "tension",
    visual_target: str = "rain on glass fractures reflection",
    motif_obligations: Optional[List[str]] = None,
    continuity_constraints: Optional[List[str]] = None,
    restraint_rules: Optional[List[str]] = None,
    has_film_intel: bool = True,
    has_cinematic_lang: bool = True,
    has_taste: bool = False,
    available: bool = True,
) -> Dict[str, Any]:
    """Helper: build a realistic scene_package_context payload."""
    if motif_obligations is None:
        motif_obligations = ["Reinforce motif: glass_breaking"]
    if continuity_constraints is None:
        continuity_constraints = ["Maintain character continuity for: Elena, Marcus"]
    if restraint_rules is None:
        restraint_rules = ["Prefer subtext over exposition"]

    return {
        "film_id": "film_1",
        "scene_id": "scene_42",
        "timestamp": "2026-04-18T10:00:00Z",
        "available": available,
        "canonical": {
            "scene_id": "scene_42",
            "film_id": "film_1",
            "narrative_purpose": narrative_purpose,
            "emotional_target": emotional_target,
            "visual_target": visual_target,
            "motif_obligations": motif_obligations,
            "continuity_constraints": continuity_constraints,
            "restraint_rules": restraint_rules,
            "forbidden_moves": [],
            "provider_neutral_execution_brief": f"Narrative purpose: {narrative_purpose}",
        },
        "derived": {
            "film_intelligence": {"scope": "sequence", "sequence_summary": {"sequence_id": "seq_b"}}
            if has_film_intel
            else {},
            "cinematic_language": {"visual_intent": "emotional", "restraint_score": 0.82}
            if has_cinematic_lang
            else {},
            "taste_guidance": {"dimension_adjustments": {"subtext_level": 0.08}}
            if has_taste
            else {},
            "_note": "Derived guidance is advisory only, never canonical",
        },
        "provenance": {
            "canonical_sources": {"structure_available": True, "memory_available": True, "spine_available": False},
            "derived_sources": {
                "film_intelligence": has_film_intel,
                "cinematic_language": has_cinematic_lang,
                "taste_context": has_taste,
            },
            "grounded_fields": ["narrative_purpose", "emotional_target", "visual_target"],
            "derived_fields": ["derived_guidance.film_intelligence", "derived_guidance.cinematic_language"],
            "advisory_fields": ["derived_guidance.taste_guidance"],
            "notes": [],
        },
        "summary": {
            "narrative_purpose": narrative_purpose,
            "emotional_target": emotional_target,
            "visual_target": visual_target,
            "motif_obligations": motif_obligations[:3],
            "continuity_constraints": continuity_constraints[:3],
            "restraint_rules": restraint_rules[:3],
            "_note": "Summary shows up to 3 items per list field",
        },
        "notes": [],
    }


def test_scene_package_summary_appears_in_debug_response():
    """Scene package summary must appear in debug response when data exists."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context()
    }

    response = output.to_debug_response()

    assert "scene_package_summary" in response
    assert response["scene_package_summary"]["available"] is True
    assert response["scene_package_summary"]["narrative_purpose"] == "Introduce the protagonist's flaw"
    assert response["scene_package_summary"]["emotional_target"] == "tension"
    assert response["scene_package_summary"]["visual_target"] == "rain on glass fractures reflection"
    assert response["scene_package_summary"]["motif_obligation_count"] == 1
    assert response["scene_package_summary"]["continuity_constraint_count"] == 1
    assert response["scene_package_summary"]["restraint_rule_count"] == 1


def test_scene_package_summary_dervied_guidance_flags():
    """Derived guidance presence flags must be correctly set."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context(
            has_film_intel=True,
            has_cinematic_lang=True,
            has_taste=True,
        )
    }

    response = output.to_debug_response()

    summary = response["scene_package_summary"]
    assert summary["has_film_intelligence_guidance"] is True
    assert summary["has_cinematic_language_guidance"] is True
    assert summary["has_taste_guidance"] is True
    assert summary["has_any_derived_guidance"] is True


def test_scene_package_summary_dervied_guidance_flags_none_when_empty():
    """Derived guidance flags must be False when no derived guidance present."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context(
            has_film_intel=False,
            has_cinematic_lang=False,
            has_taste=False,
        )
    }

    response = output.to_debug_response()

    summary = response["scene_package_summary"]
    assert summary["has_film_intelligence_guidance"] is False
    assert summary["has_cinematic_language_guidance"] is False
    assert summary["has_taste_guidance"] is False
    assert summary["has_any_derived_guidance"] is False


def test_scene_package_summary_provenance_compact():
    """Provenance must be included as a compact sub-dict when present."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context()
    }

    response = output.to_debug_response()

    provenance = response["scene_package_summary"]["provenance"]
    assert "canonical_sources" in provenance
    assert "derived_sources" in provenance
    assert provenance["grounded_field_count"] == 3
    assert provenance["derived_field_count"] == 2


def test_scene_package_summary_sample_lists():
    """Motif/continuity/restraint sample lists must appear when present."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context()
    }

    response = output.to_debug_response()

    summary = response["scene_package_summary"]
    assert summary["motif_obligations_sample"] == ["Reinforce motif: glass_breaking"]
    assert summary["continuity_constraints_sample"] == ["Maintain character continuity for: Elena, Marcus"]
    assert summary["restraint_rules_sample"] == ["Prefer subtext over exposition"]


def test_scene_package_summary_sparse_context_handled_safely():
    """Sparse scene package context must not crash and must return None."""
    output = create_full_scene_output()

    # available=False
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context(available=False)
    }
    response = output.to_debug_response()
    assert response["scene_package_summary"] is None


def test_scene_package_summary_missing_metadata_handled_safely():
    """Missing metadata must not crash and must return None."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {}

    response = output.to_debug_response()
    assert response["scene_package_summary"] is None


def test_scene_package_summary_no_quality_metrics_handled_safely():
    """Missing quality_metrics must not crash and must return None."""
    output = create_full_scene_output()
    output.quality_metrics = None

    response = output.to_debug_response()
    assert response["scene_package_summary"] is None


def test_scene_package_debug_does_not_change_app_response():
    """Scene package debug metadata must not alter app-facing output."""
    output = create_full_scene_output()
    original_app = output.to_app_response()
    original_summary = output.to_summary()

    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context()
    }

    updated_app = output.to_app_response()
    updated_summary = output.to_summary()

    assert updated_app == original_app
    assert updated_summary == original_summary
    assert "scene_package_summary" not in updated_app
    assert "scene_package_summary" not in updated_summary


def test_scene_package_debug_does_not_change_summary_response():
    """Scene package debug metadata must not alter the to_summary() response."""
    output = create_full_scene_output()
    original = output.to_summary()

    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context()
    }

    updated = output.to_summary()
    assert updated == original


def test_scene_package_debug_existing_debug_fields_still_work():
    """Existing debug fields must still work correctly alongside scene_package_summary."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "taste_context": {
            "dimension_adjustments": {"visual_restraint": 0.08},
            "dimension_confidence": {"visual_restraint": 0.7},
            "signal_counts": {"visual_restraint": 3},
        },
        "cinematic_language_context": {
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "framing_meaning": "isolated",
                "movement_significance": "intimacy",
                "restraint_score": 0.82,
                "dialogue_to_visual_substitution_opportunity": 0.74,
                "motif_evolution_stage": "reinforcement",
                "confidence": {"visual_intent": 0.8, "framing": 0.7},
            },
        },
        "film_intelligence_context": {
            "canonical_sources": {"structure": True, "memory": True, "spine": False},
            "derived": {
                "scope": "sequence",
                "sequence": {"sequence_id": "seq_b", "act_number": 2},
                "debt_payoff_arc_summary": {"setup_payoff_count": 2, "open_tension_count": 1},
            },
        },
        "scene_package_context": _make_scene_package_context(),
    }

    response = output.to_debug_response()

    # All existing summaries must still be present
    assert response["taste_calibration_summary"] is not None
    assert response["taste_calibration_summary"]["dimensions"] == ["visual_restraint"]
    assert response["cinematic_language_summary"] is not None
    assert response["cinematic_language_summary"]["visual_intent"] == "emotional"
    assert response["film_intelligence_summary"] is not None
    assert response["film_intelligence_summary"]["sequence_summary"]["sequence_id"] == "seq_b"
    # New scene_package_summary
    assert response["scene_package_summary"] is not None
    assert response["scene_package_summary"]["narrative_purpose"] == "Introduce the protagonist's flaw"


def test_scene_package_backward_compatibility_no_metadata():
    """SceneOutput without metadata must still produce valid debug response."""
    output = create_full_scene_output()
    output.quality_metrics = None

    response = output.to_debug_response()
    assert "scene_package_summary" in response
    assert response["scene_package_summary"] is None
    assert response["taste_calibration_summary"] is None
    assert response["cinematic_language_summary"] is None
    assert response["film_intelligence_summary"] is None


def test_scene_package_backward_compatibility_minimal_output():
    """Minimal SceneOutput (no quality_metrics at all) must not crash."""
    output = create_minimal_scene_output()
    # minimal output has quality_metrics=None

    # should not raise
    debug_response = output.to_debug_response()
    app_response = output.to_app_response()
    summary_response = output.to_summary()

    assert "scene_package_summary" in debug_response
    assert debug_response["scene_package_summary"] is None
    assert app_response["approved"] is True
    assert summary_response["scene_id"] == "scene_1"


def test_scene_package_summary_traceability_ids():
    """Scene and film IDs from package context must appear for traceability."""
    output = create_full_scene_output()
    output.quality_metrics["metadata"] = {
        "scene_package_context": _make_scene_package_context()
    }

    response = output.to_debug_response()

    assert response["scene_package_summary"]["scene_id"] == "scene_42"
    assert response["scene_package_summary"]["film_id"] == "film_1"


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    """Run all tests and report results."""
    tests = [
        # Model Construction
        test_director_decision_summary_construction,
        test_continuity_report_summary_construction,
        test_story_health_summary_construction,
        test_conflict_summary_construction,
        test_scene_output_minimal_construction,
        test_scene_output_full_construction,
        test_scene_output_timestamp_auto_generation,
        test_scene_output_timestamp_preserved,

        # Optional Field Handling
        test_optional_conflicts_none,
        test_optional_conflicts_populated,
        test_optional_quality_metrics_none,
        test_optional_quality_metrics_populated,
        test_optional_full_story_score_none,
        test_optional_full_story_score_populated,
        test_optional_full_continuity_report_none,
        test_optional_full_continuity_report_populated,

        # Helper Methods
        test_director_decision_summary_to_dict,
        test_continuity_report_summary_to_dict,
        test_story_health_summary_to_dict,
        test_conflict_summary_to_dict,

        # App Response Conversion
        test_to_app_response_minimal,
        test_to_app_response_full,
        test_to_app_response_excludes_internal_fields,

        # Debug Response Conversion
        test_to_debug_response_minimal,
        test_to_debug_response_full,
        test_to_debug_response_includes_internal_fields,

        # to_dict
        test_to_dict_equals_debug_response,
        test_to_dict_minimal,

        # from_dict
        test_from_dict_minimal,
        test_from_dict_with_story_score,
        test_from_dict_with_continuity_alerts,
        test_from_dict_with_conflicts,
        test_from_dict_with_full_data,
        test_from_dict_missing_fields,

        # Backward Compatibility
        test_backward_compat_director_approved_field,
        test_backward_compat_director_notes_field,
        test_backward_compat_story_score_dict,
        test_backward_compat_alerts_list,
        test_backward_compat_quality_metrics,

        # Round-trip
        test_round_trip_full,
        test_round_trip_minimal,

        # Edge Cases
        test_edge_case_empty_revision_notes,
        test_edge_case_zero_processing_time,
        test_edge_case_boundary_health_values,
        test_edge_case_all_priorities,
        test_edge_case_all_decisions,

        # Phase 9.3: Scene Package Debug Visibility
        test_scene_package_summary_appears_in_debug_response,
        test_scene_package_summary_dervied_guidance_flags,
        test_scene_package_summary_dervied_guidance_flags_none_when_empty,
        test_scene_package_summary_provenance_compact,
        test_scene_package_summary_sample_lists,
        test_scene_package_summary_sparse_context_handled_safely,
        test_scene_package_summary_missing_metadata_handled_safely,
        test_scene_package_summary_no_quality_metrics_handled_safely,
        test_scene_package_debug_does_not_change_app_response,
        test_scene_package_debug_does_not_change_summary_response,
        test_scene_package_debug_existing_debug_fields_still_work,
        test_scene_package_backward_compatibility_no_metadata,
        test_scene_package_backward_compatibility_minimal_output,
        test_scene_package_summary_traceability_ids,
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for test in tests:
        try:
            test()
            passed += 1
            print(f"✓ {test.__name__}")
        except AssertionError as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"✗ {test.__name__}: {e}")
        except Exception as e:
            failed += 1
            errors.append((test.__name__, f"ERROR: {e}"))
            print(f"✗ {test.__name__}: ERROR: {e}")
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    
    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
