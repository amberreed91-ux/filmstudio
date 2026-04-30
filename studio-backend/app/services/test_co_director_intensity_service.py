"""
Tests for Co-Director Intensity Service - Phase 10.7
"""

from uuid import uuid4

from app.models.co_director import (
    CoDirectorCritiqueSource,
    CoDirectorIntensityLevel,
    CoDirectorSession,
    SessionMode,
)
from app.services.co_director_intensity_service import CoDirectorIntensityService


def _session(mode: SessionMode, revisions: int = 0, repeated: int = 0) -> CoDirectorSession:
    return CoDirectorSession(
        session_id=uuid4(),
        project_id=uuid4(),
        film_id=uuid4(),
        current_mode=mode,
        revision_count=revisions,
        repeated_critique_count=repeated,
    )


def test_passive_mode_returns_no_intensity_profile():
    service = CoDirectorIntensityService()
    report = service.generate_intensity(_session(SessionMode.PASSIVE))
    assert report.intensity_profile is None
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.sources_consulted


def test_advisory_low_churn_is_light():
    service = CoDirectorIntensityService()
    report = service.generate_intensity(_session(SessionMode.ADVISORY, revisions=1, repeated=0))
    assert report.intensity_profile is not None
    assert report.intensity_profile.level == CoDirectorIntensityLevel.LIGHT


def test_advisory_churn_is_focused():
    service = CoDirectorIntensityService()
    report = service.generate_intensity(_session(SessionMode.ADVISORY, revisions=4, repeated=1))
    assert report.intensity_profile is not None
    assert report.intensity_profile.level == CoDirectorIntensityLevel.FOCUSED


def test_collaborative_high_churn_is_deep():
    service = CoDirectorIntensityService()
    report = service.generate_intensity(_session(SessionMode.COLLABORATIVE, revisions=9, repeated=3))
    assert report.intensity_profile is not None
    assert report.intensity_profile.level == CoDirectorIntensityLevel.DEEP
    assert report.intensity_profile.escalation_required is True
