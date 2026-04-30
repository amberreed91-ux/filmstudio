"""
Tests for Director-Memory Archivist Conflict Resolution - Phase 3.5

Tests cover:
1. merge_director_memory_archivist() function
2. get_alert_severity_level() function
3. should_escalate_decision() function
4. FilmContinuityTracker class
5. DirectorContinuityDecision model
"""

import sys
import os

# Add the backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.director_memory_resolver import (
    merge_director_memory_archivist,
    get_alert_severity_level,
    should_escalate_decision,
    create_director_continuity_decision,
    get_resolution_summary,
    AlertSeverity,
    ConflictSeverity
)
from app.services.conflicts import FilmContinuityTracker, film_continuity_tracker
from app.models.crew import DirectorContinuityDecision


def test_merge_no_alerts():
    """Test merge when there are no alerts."""
    director_output = {
        "decision": "APPROVE",
        "score": 0.85,
        "revision_notes": ["Good scene"]
    }
    memory_archivist_output = {
        "health_scores": {"overall": 0.9, "tension": 0.8},
        "alerts": [],
        "continuity_report": {}
    }
    
    result = merge_director_memory_archivist(
        director_output, memory_archivist_output, "scene_1", "film_1"
    )
    
    assert result["decision"] == "APPROVE"
    assert result["score"] == 0.85
    assert result["has_continuity_debt"] == False
    assert result["has_critical_alerts"] == False
    assert result["alerts_acknowledged"] == True
    assert result["escalation_flag"] == False
    assert result["continuity_context"]["critical_count"] == 0
    assert result["continuity_context"]["warning_count"] == 0
    print("✓ test_merge_no_alerts passed")


def test_merge_with_warning_alerts():
    """Test merge when there are WARNING alerts."""
    director_output = {
        "decision": "APPROVE",
        "score": 0.85,
        "revision_notes": ["Good scene"]
    }
    memory_archivist_output = {
        "health_scores": {"overall": 0.7, "tension": 0.6},
        "alerts": [
            {
                "type": "TENSION_OVERDUE",
                "severity": "WARNING",
                "description": "Tension 'betrayal_setup' is overdue"
            }
        ],
        "continuity_report": {}
    }
    
    result = merge_director_memory_archivist(
        director_output, memory_archivist_output, "scene_1", "film_1"
    )
    
    assert result["decision"] == "APPROVE"
    assert result["has_continuity_debt"] == True
    assert result["has_critical_alerts"] == False
    assert result["alerts_acknowledged"] == True
    assert result["escalation_flag"] == False
    assert result["continuity_context"]["critical_count"] == 0
    assert result["continuity_context"]["warning_count"] == 1
    print("✓ test_merge_with_warning_alerts passed")


def test_merge_with_critical_alerts():
    """Test merge when there are CRITICAL alerts."""
    director_output = {
        "decision": "APPROVE",
        "score": 0.85,
        "revision_notes": ["Good scene"]
    }
    memory_archivist_output = {
        "health_scores": {"overall": 0.5, "tension": 0.3},
        "alerts": [
            {
                "type": "PAYOFF_MISSING",
                "severity": "CRITICAL",
                "description": "Tension 'main_tension' has no resolution"
            }
        ],
        "continuity_report": {}
    }
    
    result = merge_director_memory_archivist(
        director_output, memory_archivist_output, "scene_1", "film_1"
    )
    
    assert result["decision"] == "APPROVE" # Director decision preserved
    assert result["has_continuity_debt"] == False  # No warnings, only CRITICAL
    assert result["has_critical_alerts"] == True
    assert result["alerts_acknowledged"] == False  # CRITICAL requires ack
    assert result["escalation_flag"] == False  # Only 1 CRITICAL, not >= 2
    assert result["continuity_context"]["critical_count"] == 1
    # CRITICAL alert should be added to revision notes
    assert any("Continuity Critical:" in note for note in result["revision_notes"])
    print("✓ test_merge_with_critical_alerts passed")


def test_merge_with_multiple_critical_alerts():
    """Test merge when there are 2+ CRITICAL alerts - should set escalation flag."""
    director_output = {
        "decision": "APPROVE",
        "score": 0.85,
        "revision_notes": ["Good scene"]
    }
    memory_archivist_output = {
        "health_scores": {"overall": 0.3, "tension": 0.2},
        "alerts": [
            {
                "type": "PAYOFF_MISSING",
                "severity": "CRITICAL",
                "description": "Tension 'main_tension' has no resolution"
            },
            {
                "type": "MOTIF_MISSED",
                "severity": "CRITICAL",
                "description": "Motif 'red_apple' callback not found"
            }
        ],
        "continuity_report": {}
    }
    
    result = merge_director_memory_archivist(
        director_output, memory_archivist_output, "scene_1", "film_1"
    )
    
    assert result["decision"] == "APPROVE"
    assert result["has_critical_alerts"] == True
    assert result["alerts_acknowledged"] == False
    assert result["escalation_flag"] == True  # 2 CRITICALs = escalation
    assert result["continuity_context"]["critical_count"] == 2
    print("✓ test_merge_with_multiple_critical_alerts passed")


def test_get_alert_severity_level_no_alerts():
    """Test severity level with no alerts."""
    assert get_alert_severity_level([]) == ConflictSeverity.LOW
    print("✓ test_get_alert_severity_level_no_alerts passed")


def test_get_alert_severity_level_warning():
    """Test severity level with warnings."""
    alerts = [{"severity": "WARNING"}]
    assert get_alert_severity_level(alerts) == ConflictSeverity.LOW
    
    alerts = [{"severity": "WARNING"}, {"severity": "WARNING"}, {"severity": "WARNING"}]
    assert get_alert_severity_level(alerts) == ConflictSeverity.MEDIUM
    print("✓ test_get_alert_severity_level_warning passed")


def test_get_alert_severity_level_critical():
    """Test severity level with critical alerts."""
    alerts = [{"severity": "CRITICAL"}]
    assert get_alert_severity_level(alerts) == ConflictSeverity.MEDIUM
    
    alerts = [{"severity": "CRITICAL"}, {"severity": "CRITICAL"}, {"severity": "CRITICAL"}]
    assert get_alert_severity_level(alerts) == ConflictSeverity.HIGH
    print("✓ test_get_alert_severity_level_critical passed")


def test_should_escalate_decision():
    """Test escalation determination."""
    # No escalation needed
    assert should_escalate_decision({"escalation_flag": False}) == False
    
    # Explicit escalation flag
    assert should_escalate_decision({"escalation_flag": True}) == True
    
    # High severity
    assert should_escalate_decision({
        "escalation_flag": False,
        "conflict_severity": ConflictSeverity.HIGH
    }) == True
    
    # Blocking severity
    assert should_escalate_decision({
        "escalation_flag": False,
        "conflict_severity": ConflictSeverity.BLOCKING
    }) == True
    print("✓ test_should_escalate_decision passed")


def test_create_director_continuity_decision():
    """Test creating DirectorContinuityDecision model."""
    merged = {
        "decision": "APPROVE",
        "score": 0.85,
        "revision_notes": ["Good scene"],
        "continuity_context": {
            "health_scores": {"overall": 0.8},
            "alerts": [{"type": "INFO", "severity": "info"}],
            "continuity_report": {"film_id": "film_1"},
            "critical_count": 0,
            "warning_count": 0
        },
        "has_continuity_debt": False,
        "conflict_severity": "low",
        "alerts_acknowledged": True,
        "escalation_flag": False,
        "scene_id": "scene_1",
        "film_id": "film_1",
        "timestamp": "2024-01-01T00:00:00"
    }
    
    decision = create_director_continuity_decision(merged)
    
    assert isinstance(decision, DirectorContinuityDecision)
    assert decision.decision == "APPROVE"
    assert decision.score == 0.85
    assert decision.critical_alert_count == 0
    assert decision.warning_alert_count == 0
    assert decision.scene_id == "scene_1"
    assert decision.film_id == "film_1"
    print("✓ test_create_director_continuity_decision passed")


def test_get_resolution_summary():
    """Test getting resolution summary."""
    merged = {
        "decision": "APPROVE",
        "score": 0.85,
        "continuity_context": {
            "critical_count": 1,
            "warning_count": 2,
            "health_scores": {"overall": 0.7}
        },
        "alerts_acknowledged": False,
        "escalation_flag": True
    }
    
    summary = get_resolution_summary(merged)
    
    assert summary["decision"] == "APPROVE"
    assert summary["score"] == 0.85
    assert summary["has_continuity_issues"] == True
    assert summary["critical_alerts"] == 1
    assert summary["warning_alerts"] == 2
    assert summary["requires_acknowledgment"] == True
    assert summary["escalation_flag"] == True
    print("✓ test_get_resolution_summary passed")


def test_film_continuity_tracker_record():
    """Test FilmContinuityTracker recording scene decisions."""
    tracker = FilmContinuityTracker()
    
    decision = {
        "decision": "APPROVE",
        "continuity_context": {
            "alerts": [
                {"type": "TENSION_OVERDUE", "severity": "WARNING"}
            ]
        }
    }
    
    tracker.record_scene_decision("film_1", "scene_1", decision)
    
    # Check scene decision was recorded
    recorded = tracker.get_scene_decision("film_1", "scene_1")
    assert recorded["decision"] == "APPROVE"
    print("✓ test_film_continuity_tracker_record passed")


def test_film_continuity_tracker_debt():
    """Test FilmContinuityTracker debt tracking."""
    tracker = FilmContinuityTracker()
    
    # Record multiple scenes with alerts
    tracker.record_scene_decision("film_1", "scene_1", {
        "decision": "APPROVE",
        "continuity_context": {
            "alerts": [
                {"type": "TENSION_OVERDUE", "severity": "WARNING"}
            ]
        }
    })
    
    tracker.record_scene_decision("film_1", "scene_2", {
        "decision": "APPROVE",
        "continuity_context": {
            "alerts": [
                {"type": "MOTIF_MISSED", "severity": "CRITICAL"}
            ]
        }
    })
    
    debt = tracker.get_film_continuity_debt("film_1")
    
    assert debt["total_alerts"] == 2
    assert debt["critical_count"] == 1
    assert debt["warning_count"] == 1
    assert debt["scene_count"] == 2
    print("✓ test_film_continuity_tracker_debt passed")


def test_film_continuity_tracker_health_score():
    """Test FilmContinuityTracker health score calculation."""
    tracker = FilmContinuityTracker()
    
    # Record a scene with no issues
    tracker.record_scene_decision("film_1", "scene_1", {
        "decision": "APPROVE",
        "continuity_context": {"alerts": []}
    })
    
    health = tracker.get_film_health_score("film_1")
    assert health == 1.0  # Perfect health with no alerts
    
    # Add a scene with CRITICAL alert
    tracker.record_scene_decision("film_1", "scene_2", {
        "decision": "APPROVE",
        "continuity_context": {
            "alerts": [{"type": "CRITICAL", "severity": "CRITICAL"}]
        }
    })
    
    health = tracker.get_film_health_score("film_1")
    assert health < 1.0  # Health reduced by CRITICAL alert
    print("✓ test_film_continuity_tracker_health_score passed")


def test_film_continuity_tracker_clear():
    """Test FilmContinuityTracker clear function."""
    tracker = FilmContinuityTracker()
    
    tracker.record_scene_decision("film_1", "scene_1", {
        "decision": "APPROVE",
        "continuity_context": {"alerts": []}
    })
    
    assert tracker.get_scene_decision("film_1", "scene_1") is not None
    
    tracker.clear_film("film_1")
    
    assert tracker.get_scene_decision("film_1", "scene_1") is None
    assert tracker.get_film_continuity_debt("film_1")["total_alerts"] == 0
    print("✓ test_film_continuity_tracker_clear passed")


def test_film_continuity_tracker_summary():
    """Test FilmContinuityTracker summary function."""
    tracker = FilmContinuityTracker()
    
    tracker.record_scene_decision("film_1", "scene_1", {
        "decision": "APPROVE",
        "continuity_context": {
            "alerts": [
                {"type": "TENSION_OVERDUE", "severity": "WARNING"}
            ]
        }
    })
    
    summary = tracker.get_film_summary("film_1")
    
    assert summary["film_id"] == "film_1"
    assert "health_score" in summary
    assert summary["scene_count"] == 1
    assert summary["total_alerts"] == 1
    assert summary["warning_count"] == 1
    print("✓ test_film_continuity_tracker_summary passed")


def test_global_film_continuity_tracker_exists():
    """Test that global film_continuity_tracker instance exists."""
    assert film_continuity_tracker is not None
    assert isinstance(film_continuity_tracker, FilmContinuityTracker)
    print("✓ test_global_film_continuity_tracker_exists passed")


def test_director_continuity_decision_to_dict():
    """Test DirectorContinuityDecision.to_dict() method."""
    decision = DirectorContinuityDecision(
        decision="APPROVE",
        score=0.85,
        revision_notes=["Good scene"],
        alerts=[{"type": "INFO", "severity": "info"}],
        critical_alert_count=0,
        warning_alert_count=0,
        scene_id="scene_1",
        film_id="film_1",
        timestamp="2024-01-01T00:00:00"
    )
    
    d = decision.to_dict()
    
    assert d["decision"] == "APPROVE"
    assert d["score"] == 0.85
    assert d["scene_id"] == "scene_1"
    assert d["film_id"] == "film_1"
    print("✓ test_director_continuity_decision_to_dict passed")


def run_all_tests():
    """Run all tests."""
    print("\n=== Director-Memory Archivist Conflict Resolution Tests ===\n")
    
    tests = [
        test_merge_no_alerts,
        test_merge_with_warning_alerts,
        test_merge_with_critical_alerts,
        test_merge_with_multiple_critical_alerts,
        test_get_alert_severity_level_no_alerts,
        test_get_alert_severity_level_warning,
        test_get_alert_severity_level_critical,
        test_should_escalate_decision,
        test_create_director_continuity_decision,
        test_get_resolution_summary,
        test_film_continuity_tracker_record,
        test_film_continuity_tracker_debt,
        test_film_continuity_tracker_health_score,
        test_film_continuity_tracker_clear,
        test_film_continuity_tracker_summary,
        test_global_film_continuity_tracker_exists,
        test_director_continuity_decision_to_dict,
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
    
    print(f"\n=== Results: {passed} passed, {failed} failed ===\n")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)