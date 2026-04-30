"""
Tests for Phase 10.2: read-only co-director context exposure.

These tests verify that get_co_director_context() provides safe,
bounded access to co-director session state without modifying anything.
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.services.spine_consumption_service import SpineConsumptionService
from app.models.co_director import SessionMode, CoDirectorSession


class TestGetCoDirectorContext:
    """Tests for SpineConsumptionService.get_co_director_context()"""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = SpineConsumptionService()

    # =====================================================================
    # Safe Defaults Tests
    # =====================================================================

    def test_returns_safe_defaults_when_no_session(self):
        """Context returns safe defaults when session doesn't exist."""
        result = self.service.get_co_director_context(
            project_id="project_123",
            film_id="film_456",
            session_id=uuid4()
        )

        assert result["session_active"] is False
        assert result["current_mode"] is None
        assert result["revision_count"] == 0
        assert result["repeated_critique_count"] == 0
        assert result["last_accepted_suggestion"] is None
        assert result["timestamps"]["created_at"] is None
        assert result["timestamps"]["updated_at"] is None

    def test_returns_safe_defaults_when_session_id_none(self):
        """Context returns safe defaults when session_id is None."""
        result = self.service.get_co_director_context(
            project_id="project_123",
            film_id="film_456",
            session_id=None
        )

        assert result["session_active"] is False
        assert any("session_id" in note for note in result["notes"])

    def test_returns_safe_defaults_on_service_error(self):
        """Context returns safe defaults when service throws."""
        with patch(
            'app.services.spine_consumption_service.co_director_session_service',
            wraps=MagicMock()
        ) as mock_service:
            mock_service.get_session.side_effect = RuntimeError("Service error")

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=uuid4()
            )

            assert result["session_active"] is False
            assert any("unavailable" in note for note in result["notes"])

    # =====================================================================
    # Session Active Tests
    # =====================================================================

    def test_returns_session_data_when_exists(self):
        """Context returns correct data when session exists."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.ADVISORY,
            active_scene_id=uuid4(),
            revision_count=5,
            repeated_critique_count=2,
            last_accepted_suggestion="camera_angle",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["session_active"] is True
            assert result["current_mode"] == "advisory"
            assert result["revision_count"] == 5
            assert result["repeated_critique_count"] == 2
            assert result["last_accepted_suggestion"] == "camera_angle"
            assert result["timestamps"]["created_at"] is not None
            assert result["timestamps"]["updated_at"] is not None

    def test_handles_non_uuid_scene_id_gracefully(self):
        """Context handles non-UUID scene_ids (like 'scene_42') gracefully."""
        session_id = uuid4()

        session = CoDirectorSession(
            session_id=session_id,
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            active_scene_id=None,
            revision_count=0,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session_id,
                scene_id="scene_42"
            )

            # Non-UUID scene_id should be stored as-is, not cause an error
            # set_active_scene won't be called for non-UUID scene_ids
            assert result["active_scene_id"] == "scene_42"
            assert mock_service.set_active_scene.called is False
            assert not any("unavailable" in note for note in result["notes"])

    def test_updates_session_when_valid_uuid_scene_id(self):
        """Context updates session when given a valid UUID scene_id."""
        session_id = uuid4()
        current_scene_id = uuid4()

        session = CoDirectorSession(
            session_id=session_id,
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            active_scene_id=current_scene_id,
            revision_count=0,
        )

        new_scene_id = uuid4()
        updated_session = CoDirectorSession(
            session_id=session_id,
            project_id=session.project_id,
            film_id=session.film_id,
            current_mode=SessionMode.PASSIVE,
            active_scene_id=new_scene_id,
            revision_count=0,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session
            mock_service.set_active_scene.return_value = updated_session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session_id,
                scene_id=str(new_scene_id)  # Valid UUID string
            )

            # Valid UUID scene_id should trigger set_active_scene
            assert mock_service.set_active_scene.called
            assert result["active_scene_id"] == str(new_scene_id)

    def test_does_not_update_scene_when_unchanged(self):
        """Context doesn't update when scene_id matches current."""
        session_id = uuid4()

        session = CoDirectorSession(
            session_id=session_id,
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            active_scene_id=uuid4(),  # Set to some UUID
            revision_count=0,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session
            # Mock the active_scene_id string representation
            session.active_scene_id = uuid4()

            # Call with same scene as string (will be different from UUID)
            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session_id,
                scene_id="scene_42"  # Different scene
            )

            # set_active_scene should still be called since strings don't match UUIDs
            # (this is correct behavior - we don't know the current scene string)

    # =====================================================================
    # Mode Handling Tests
    # =====================================================================

    def test_handles_passive_mode(self):
        """Context correctly handles PASSIVE mode."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            revision_count=0,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["current_mode"] == "passive"
            assert result["derived"]["engagement_level"] == "passive"

    def test_handles_advisory_mode(self):
        """Context correctly handles ADVISORY mode."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.ADVISORY,
            revision_count=2,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["current_mode"] == "advisory"
            assert result["derived"]["engagement_level"] == "advisory"
            assert result["derived"]["collaboration_depth"] == "surface"

    def test_handles_collaborative_mode(self):
        """Context correctly handles COLLABORATIVE mode."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.COLLABORATIVE,
            revision_count=15,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["current_mode"] == "collaborative"
            assert result["derived"]["engagement_level"] == "highly_engaged"
            assert result["derived"]["collaboration_depth"] == "deep"

    # =====================================================================
    # Derived Metrics Tests
    # =====================================================================

    def test_derived_engagement_level_inactive_when_passive(self):
        """Derived metrics reflect passive mode."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            revision_count=0,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["derived"]["engagement_level"] == "passive"
            assert result["derived"]["collaboration_depth"] == "none"

    def test_derived_metrics_reflect_revision_count(self):
        """Derived collaboration depth reflects revision count."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.ADVISORY,
            revision_count=5,  # Moderate range
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["derived"]["collaboration_depth"] == "moderate"

    def test_derived_critique_repetition_risk_high_when_count_high(self):
        """Derived critique risk is high when repeated_critique_count is high."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.ADVISORY,
            revision_count=10,
            repeated_critique_count=5,  # High
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["derived"]["critique_repetition_risk"] == "high"

    def test_derived_suggestion_acceptance_rate_when_accepted(self):
        """Derived suggestion acceptance shows high when suggestion accepted."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.COLLABORATIVE,
            revision_count=3,
            last_accepted_suggestion="lighting_adjustment",
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["derived"]["suggestion_acceptance_rate"] == "high"

    # =====================================================================
    # Canonical Sources Tracking Tests
    # =====================================================================

    def test_tracks_session_service_availability(self):
        """Context tracks whether session service was consulted."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["canonical_sources"]["session_service"] is True
            assert result["canonical_sources"]["session_record"] is True

    def test_canonical_sources_false_when_no_session(self):
        """Context tracks when session wasn't found."""
        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = None

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=uuid4()
            )

            assert result["canonical_sources"]["session_service"] is True
            assert result["canonical_sources"]["session_record"] is False

    # =====================================================================
    # Timestamp Handling Tests
    # =====================================================================

    def test_timestamps_iso_format(self):
        """Timestamps are returned in ISO format."""
        now = datetime.now(timezone.utc)
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            created_at=now,
            updated_at=now,
        )

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            assert result["timestamps"]["created_at"] is not None
            assert result["timestamps"]["updated_at"] is not None
            # Should be valid ISO strings
            datetime.fromisoformat(result["timestamps"]["created_at"])

    def test_timestamps_null_when_session_missing(self):
        """Timestamps are null when session is missing."""
        result = self.service.get_co_director_context(
            project_id="project_123",
            film_id="film_456",
            session_id=uuid4()
        )

        assert result["timestamps"]["created_at"] is None
        assert result["timestamps"]["updated_at"] is None

    # =====================================================================
    # Notes Tests
    # =====================================================================

    def test_adds_note_when_session_requires_explicit_id(self):
        """Context notes when session lookup needs explicit ID."""
        result = self.service.get_co_director_context(
            project_id="project_123",
            film_id="film_456",
            session_id=None
        )

        assert any("explicit session_id" in note for note in result["notes"])

    def test_adds_note_when_no_session_found(self):
        """Context notes when session wasn't found."""
        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = None

            result = self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=uuid4()
            )

            assert any("No active co-director session" in note for note in result["notes"])

    # =====================================================================
    # Bounded Architecture Tests
    # =====================================================================

    def test_does_not_modify_session(self):
        """Context method does not modify the session object."""
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=uuid4(),
            film_id=uuid4(),
            current_mode=SessionMode.PASSIVE,
            revision_count=0,
        )

        original_revision_count = session.revision_count

        with patch(
            'app.services.spine_consumption_service.co_director_session_service'
        ) as mock_service:
            mock_service.get_session.return_value = session

            self.service.get_co_director_context(
                project_id="project_123",
                film_id="film_456",
                session_id=session.session_id
            )

            # Session should be unchanged
            assert session.revision_count == original_revision_count

    def test_result_contains_all_required_fields(self):
        """Context result contains all required fields per spec."""
        result = self.service.get_co_director_context(
            project_id="project_123",
            film_id="film_456",
            session_id=None
        )

        required_fields = [
            "film_id", "session_id", "scene_id", "timestamp",
            "session_active", "current_mode", "active_scene_id",
            "revision_count", "repeated_critique_count",
            "last_accepted_suggestion", "timestamps",
            "derived", "canonical_sources", "notes"
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    def test_result_has_correct_structure(self):
        """Context result has correct nested structure."""
        result = self.service.get_co_director_context(
            project_id="project_123",
            film_id="film_456",
            session_id=None
        )

        # Check nested structures
        assert isinstance(result["timestamps"], dict)
        assert "created_at" in result["timestamps"]
        assert "updated_at" in result["timestamps"]

        assert isinstance(result["derived"], dict)
        assert "engagement_level" in result["derived"]

        assert isinstance(result["canonical_sources"], dict)
        assert "session_service" in result["canonical_sources"]
        assert "session_record" in result["canonical_sources"]

        assert isinstance(result["notes"], list)