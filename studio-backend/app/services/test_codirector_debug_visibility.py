"""
Tests for Phase 10.3: debug-only co-director visibility.

These tests verify that co-director session context appears only in
debug-oriented output, without affecting app-facing responses.
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.models.scene_output import SceneOutput, DirectorDecisionSummary, ContinuityReportSummary, StoryHealthSummary
from app.models.co_director import SessionMode, CoDirectorSession
from app.services.spine_consumption_service import SpineConsumptionService


class TestCoDirectorDebugVisibility:
    """Tests for co-director debug visibility in SceneOutput."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a minimal SceneOutput for testing
        self.scene_output = SceneOutput(
            scene_id="scene_42",
            film_id="film_123",
            director_decision=DirectorDecisionSummary(
                approved=True,
                notes="Test scene approved",
                decision="APPROVE",
                score=0.85
            ),
            continuity_report=ContinuityReportSummary(
                has_alerts=False,
                alert_count=0
            ),
            story_health=StoryHealthSummary(
                overall_health=0.8,
                priority="MEDIUM"
            ),
            timestamp=datetime.now(timezone.utc).isoformat() + "Z"
        )

    # =====================================================================
    # Debug Response Tests
    # =====================================================================

    def test_co_director_summary_not_in_debug_when_no_context(self):
        """co_director_summary is None when no co-director context is present."""
        # No co_director_context in quality_metrics
        debug_response = self.scene_output.to_debug_response()
        
        assert "co_director_summary" in debug_response
        assert debug_response["co_director_summary"] is None

    def test_co_director_summary_in_debug_when_context_present(self):
        """co_director_summary appears in debug response when context exists."""
        # Create co-director context
        codirector_context = {
            "session_active": True,
            "current_mode": "advisory",
            "active_scene_id": "scene_42",
            "revision_count": 5,
            "repeated_critique_count": 2,
            "last_accepted_suggestion": "camera_angle",
            "derived": {
                "engagement_level": "advisory",
                "collaboration_depth": "moderate",
                "suggestion_acceptance_rate": "high",
                "critique_repetition_risk": "low"
            },
            "timestamps": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "canonical_sources": {
                "session_service": True,
                "session_record": True
            },
            "notes": []
        }

        # Attach co-director context to quality_metrics metadata
        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        assert "co_director_summary" in debug_response
        assert debug_response["co_director_summary"] is not None
        
        summary = debug_response["co_director_summary"]
        assert summary["session_active"] is True
        assert summary["current_mode"] == "advisory"
        assert summary["revision_count"] == 5
        assert summary["repeated_critique_count"] == 2
        assert summary["last_accepted_suggestion"] == "camera_angle"

    def test_co_director_summary_contains_derived_metrics(self):
        """co_director_summary includes derived metrics when present."""
        codirector_context = {
            "session_active": True,
            "current_mode": "collaborative",
            "active_scene_id": "scene_100",
            "revision_count": 15,
            "derived": {
                "engagement_level": "highly_engaged",
                "collaboration_depth": "deep",
                "suggestion_acceptance_rate": "high",
                "critique_repetition_risk": "moderate"
            }
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        summary = debug_response["co_director_summary"]
        assert "derived" in summary
        assert summary["derived"]["engagement_level"] == "highly_engaged"
        assert summary["derived"]["collaboration_depth"] == "deep"

    def test_co_director_summary_includes_timestamps(self):
        """co_director_summary includes session timestamps when present."""
        created_at = datetime.now(timezone.utc).isoformat()
        updated_at = datetime.now(timezone.utc).isoformat()
        
        codirector_context = {
            "session_active": True,
            "current_mode": "passive",
            "timestamps": {
                "created_at": created_at,
                "updated_at": updated_at
            }
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        summary = debug_response["co_director_summary"]
        assert "session_timestamps" in summary
        assert summary["session_timestamps"]["created_at"] == created_at
        assert summary["session_timestamps"]["updated_at"] == updated_at

    def test_co_director_summary_absent_when_session_inactive(self):
        """co_director_summary is None when session is not active."""
        codirector_context = {
            "session_active": False,
            "current_mode": None,
            "revision_count": 0
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        # Should be None since session is not active
        assert debug_response["co_director_summary"] is None

    # =====================================================================
    # App Response Tests - MUST NOT CHANGE
    # =====================================================================

    def test_app_response_unchanged_by_codirector(self):
        """App response does not include co-director data."""
        codirector_context = {
            "session_active": True,
            "current_mode": "collaborative",
            "revision_count": 20
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        app_response = self.scene_output.to_app_response()
        
        # App response should NOT have co_director_summary
        assert "co_director_summary" not in app_response
        assert "co_director_context" not in app_response
        assert "co_director" not in app_response

    def test_app_response_still_has_core_fields(self):
        """App response still contains all core fields after co-director visibility."""
        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": {
                    "session_active": True,
                    "current_mode": "advisory"
                }
            }
        }

        app_response = self.scene_output.to_app_response()
        
        # Core fields should still be present
        assert "scene_id" in app_response
        assert "film_id" in app_response
        assert "approved" in app_response
        assert "decision" in app_response
        assert "continuity" in app_response
        assert "story_health" in app_response

    # =====================================================================
    # Summary Response Tests - MUST NOT CHANGE
    # =====================================================================

    def test_summary_response_unchanged_by_codirector(self):
        """Summary response does not include co-director data."""
        codirector_context = {
            "session_active": True,
            "current_mode": "collaborative"
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        summary_response = self.scene_output.to_summary()
        
        # Summary should NOT have co_director data
        assert "co_director_summary" not in summary_response
        assert "co_director_context" not in summary_response

    def test_summary_still_has_core_fields(self):
        """Summary still contains core fields after co-director visibility."""
        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": {
                    "session_active": True,
                    "current_mode": "advisory"
                }
            }
        }

        summary_response = self.scene_output.to_summary()
        
        # Core summary fields should still be present
        assert "scene_id" in summary_response
        assert "film_id" in summary_response
        assert "decision" in summary_response
        assert "approved" in summary_response
        assert "priority" in summary_response

    # =====================================================================
    # Debug Response Structure Tests
    # =====================================================================

    def test_debug_response_still_has_all_existing_fields(self):
        """Debug response still contains all existing summary fields."""
        # Ensure all existing summary methods are present
        assert hasattr(SceneOutput, '_build_taste_calibration_summary')
        assert hasattr(SceneOutput, '_build_film_intelligence_summary')
        assert hasattr(SceneOutput, '_build_cinematic_language_summary')
        assert hasattr(SceneOutput, '_build_scene_package_summary')
        assert hasattr(SceneOutput, '_build_codirector_summary')

        debug_response = self.scene_output.to_debug_response()
        
        # All existing fields should still be present
        assert "taste_calibration_summary" in debug_response
        assert "film_intelligence_summary" in debug_response
        assert "cinematic_language_summary" in debug_response
        assert "scene_package_summary" in debug_response

    def test_debug_response_contains_full_context_when_present(self):
        """Debug response contains full co_director_context in metadata."""
        full_context = {
            "session_active": True,
            "current_mode": "advisory",
            "active_scene_id": "scene_42",
            "revision_count": 10,
            "derived": {
                "engagement_level": "advisory"
            },
            "canonical_sources": {
                "session_service": True,
                "session_record": True
            }
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": full_context
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        # Full context should be in metadata for debugging
        assert "metadata" in debug_response
        assert "co_director_context" in debug_response["metadata"]
        assert debug_response["metadata"]["co_director_context"] == full_context

    # =====================================================================
    # Safe Handling Tests
    # =====================================================================

    def test_handles_missing_metadata_gracefully(self):
        """Handles missing metadata gracefully."""
        self.scene_output.quality_metrics = None

        debug_response = self.scene_output.to_debug_response()
        
        assert "co_director_summary" in debug_response
        assert debug_response["co_director_summary"] is None

    def test_handles_non_dict_metadata_gracefully(self):
        """Handles non-dict metadata gracefully."""
        self.scene_output.quality_metrics = "not a dict"

        debug_response = self.scene_output.to_debug_response()
        
        assert "co_director_summary" in debug_response
        assert debug_response["co_director_summary"] is None

    def test_handles_non_dict_context_gracefully(self):
        """Handles non-dict co_director_context gracefully."""
        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": "not a dict"
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        assert "co_director_summary" in debug_response
        assert debug_response["co_director_summary"] is None

    def test_handles_incomplete_context_gracefully(self):
        """Handles incomplete co-director context gracefully."""
        # Missing some fields
        codirector_context = {
            "session_active": True
            # Missing current_mode, revision_count, etc.
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        debug_response = self.scene_output.to_debug_response()
        
        # Should still work, using defaults
        assert "co_director_summary" in debug_response
        summary = debug_response["co_director_summary"]
        assert summary["session_active"] is True

    # =====================================================================
    # Backward Compatibility Tests
    # =====================================================================

    def test_backward_compatible_with_existing_outputs(self):
        """Output remains backward compatible with existing structure."""
        # Create output without any co-director context
        self.scene_output.quality_metrics = None

        debug_response = self.scene_output.to_debug_response()
        
        # Should have same structure as before Phase 10.3
        assert "scene_id" in debug_response
        assert "film_id" in debug_response
        assert "director_decision" in debug_response
        assert "continuity_report" in debug_response
        assert "story_health" in debug_response
        assert "quality_metrics" in debug_response
        # New field present but None
        assert "co_director_summary" in debug_response

    def test_to_dict_includes_co_director_summary(self):
        """to_dict() includes co_director_summary (same as to_debug_response)."""
        codirector_context = {
            "session_active": True,
            "current_mode": "collaborative",
            "revision_count": 5
        }

        self.scene_output.quality_metrics = {
            "metadata": {
                "co_director_context": codirector_context
            }
        }

        output_dict = self.scene_output.to_dict()
        
        assert "co_director_summary" in output_dict
        assert output_dict["co_director_summary"] is not None


class TestBuildCoDirectorSummary:
    """Tests for _build_codirector_summary static method."""

    def test_build_summary_from_valid_context(self):
        """Builds summary correctly from valid context."""
        metadata = {
            "co_director_context": {
                "session_active": True,
                "current_mode": "advisory",
                "active_scene_id": "scene_42",
                "revision_count": 5,
                "repeated_critique_count": 2,
                "last_accepted_suggestion": "lighting",
                "derived": {
                    "engagement_level": "advisory",
                    "collaboration_depth": "surface"
                },
                "timestamps": {
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-02T00:00:00Z"
                },
                "canonical_sources": {
                    "session_service": True,
                    "session_record": True
                }
            }
        }

        summary = SceneOutput._build_codirector_summary(metadata)
        
        assert summary is not None
        assert summary["session_active"] is True
        assert summary["current_mode"] == "advisory"
        assert summary["active_scene_id"] == "scene_42"
        assert summary["revision_count"] == 5
        assert summary["derived"]["engagement_level"] == "advisory"

    def test_returns_none_when_no_metadata(self):
        """Returns None when metadata is None."""
        summary = SceneOutput._build_codirector_summary(None)
        assert summary is None

    def test_returns_none_when_metadata_not_dict(self):
        """Returns None when metadata is not a dict."""
        summary = SceneOutput._build_codirector_summary("not a dict")
        assert summary is None

    def test_returns_none_when_no_codirector_context(self):
        """Returns None when no co_director_context in metadata."""
        summary = SceneOutput._build_codirector_summary({})
        assert summary is None

    def test_returns_none_when_context_not_dict(self):
        """Returns None when co_director_context is not a dict."""
        metadata = {
            "co_director_context": "not a dict"
        }
        summary = SceneOutput._build_codirector_summary(metadata)
        assert summary is None

    def test_returns_none_when_session_inactive(self):
        """Returns None when session is not active."""
        metadata = {
            "co_director_context": {
                "session_active": False
            }
        }
        summary = SceneOutput._build_codirector_summary(metadata)
        assert summary is None

    def test_handles_missing_optional_fields(self):
        """Handles missing optional fields gracefully."""
        metadata = {
            "co_director_context": {
                "session_active": True
                # Missing all optional fields
            }
        }

        summary = SceneOutput._build_codirector_summary(metadata)
        
        assert summary is not None
        assert summary["session_active"] is True
        # Optional fields should have defaults
        assert summary.get("current_mode") is None
        assert summary.get("revision_count") == 0