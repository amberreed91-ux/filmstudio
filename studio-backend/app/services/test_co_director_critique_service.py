"""
Tests for Co-Director Critique Service - Phase 10.4.2

Director-signal-only bounded critique behavior.
"""

from uuid import uuid4

from app.models.co_director import (
    CoDirectorCritiqueCategory,
    CoDirectorCritiqueSource,
    CoDirectorSession,
    SessionMode,
)
from app.services.co_director_critique_service import CoDirectorCritiqueService
from app.services.director_evaluator import Decision, DirectorEvaluator


def _make_session(mode: SessionMode) -> CoDirectorSession:
    return CoDirectorSession(
        session_id=uuid4(),
        project_id=uuid4(),
        film_id=uuid4(),
        current_mode=mode,
    )


def test_passive_mode_returns_no_critique():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.PASSIVE)

    report = service.generate_critique(
        session=session,
        director_result={"rejection_reasons": ["tone_violation"]},
        scene_id="scene_1",
    )

    assert report.critique is None
    assert report.mode == SessionMode.PASSIVE
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.sources_consulted


def test_advisory_mode_rejection_reasons_returns_critical_critique():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)

    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REJECT,
            "rejection_reasons": ["over_explaining_dialogue", "tone_violation"],
            "revision_notes": ["Reduce explanatory dialogue density"],
        },
        scene_id="scene_9",
    )

    assert report.critique is not None
    assert report.critique.category == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION
    assert report.critique.priority.value == "critical"
    assert report.critique.mode == SessionMode.ADVISORY
    assert "rejection_reason:over_explaining_dialogue" in report.critique.grounded_signals
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.critique.source_systems
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.sources_consulted


def test_advisory_weak_result_returns_pillar_low_critique():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)

    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REVISE,
            "score": 0.58,
            "requires_revision": True,
            "pillars": {
                "intent_alignment": 0.41,
                "emotional_consistency": 0.63,
                "visual_coherence": 0.39,
                "continuity": 0.71,
            },
            "revision_notes": ["Add visual intent and sharpen continuity motivation"],
        },
        scene_id="scene_22",
    )

    assert report.critique is not None
    assert report.critique.category == CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW
    assert any("low_pillar:intent_alignment" in signal for signal in report.critique.grounded_signals)
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.sources_consulted


def test_empty_or_weak_director_result_returns_no_critique():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)

    empty_report = service.generate_critique(session=session, director_result={})
    assert empty_report.critique is None

    weak_report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.APPROVE,
            "score": 0.92,
            "requires_revision": False,
            "pillars": {
                "intent_alignment": 0.90,
                "emotional_consistency": 0.91,
                "visual_coherence": 0.86,
                "continuity": 0.88,
            },
        },
    )
    assert weak_report.critique is None


def test_only_one_dominant_critique_is_returned():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.COLLABORATIVE)

    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REJECT,
            "score": 0.42,
            "requires_revision": True,
            "rejection_reasons": ["generic_visuals"],
            "pillars": {
                "intent_alignment": 0.40,
                "emotional_consistency": 0.44,
                "visual_coherence": 0.36,
                "continuity": 0.49,
            },
        },
        scene_id="scene_31",
    )

    assert report.critique is not None
    assert report.critique.category == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION
    assert isinstance(report.critique.grounded_signals, list)


def test_report_includes_director_evaluator_source():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)

    report = service.generate_critique(
        session=session,
        director_result={"decision": Decision.REVISE, "pillars": {"intent_alignment": 0.40}, "score": 0.50},
    )

    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.sources_consulted


def test_existing_director_evaluator_service_behavior_unchanged():
    evaluator = DirectorEvaluator()
    result = evaluator.evaluate(scene_data={}, spine={"available": True})

    assert result["decision"] == Decision.REJECT
    assert "Missing scene data" in result["rejection_reasons"]


def test_conflicting_rejection_and_low_pillar_signals_prefers_rejection():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)
    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REJECT,
            "score": 0.2,
            "requires_revision": True,
            "rejection_reasons": ["tone_violation"],
            "pillars": {"visual_coherence": 0.11},
        },
        scene_id="scene_conflict",
    )
    assert report.critique is not None
    assert report.critique.category == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION


def test_malformed_pillars_and_unexpected_types_are_handled_safely():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)
    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REVISE,
            "score": "not-a-number",
            "requires_revision": "yes",
            "pillars": {"visual_coherence": "bad", "continuity": None},
            "rejection_reasons": None,
        },
    )
    assert report.critique is None


def test_missing_pillars_but_rejection_reasons_still_produces_rejection_critique():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)
    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REJECT,
            "rejection_reasons": ["generic_visuals"],
        },
    )
    assert report.critique is not None
    assert report.critique.category == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION


def test_vision_awareness_is_additive_and_advisory_in_critique():
    service = CoDirectorCritiqueService()
    session = _make_session(SessionMode.ADVISORY)
    report = service.generate_critique(
        session=session,
        director_result={
            "decision": Decision.REVISE,
            "score": 0.58,
            "requires_revision": True,
            "pillars": {"visual_coherence": 0.39},
        },
        vision_awareness={
            "advisory_only": True,
            "cannot_auto_regenerate": True,
            "cannot_override_user_intent": True,
            "scene_memory_count": 4,
            "continuity_issue_count": 2,
        },
    )
    assert report.critique is not None
    assert any(signal == "vision_memory_count:4" for signal in report.critique.grounded_signals)
    assert any(signal == "vision_continuity_issues:2" for signal in report.critique.grounded_signals)
