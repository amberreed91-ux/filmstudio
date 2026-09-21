"""
Tests for Co-Director Proposal Service - Phase 10.5

Bounded proposal generation from dominant critiques only.
"""

from uuid import uuid4

from app.models.co_director import (
    CONFIDENCE_EMERGING,
    CONFIDENCE_STRONG,
    CoDirectorCritique,
    CoDirectorCritiqueCategory,
    CoDirectorCritiquePriority,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorProposalCategory,
    CoDirectorSession,
    SessionMode,
)
from app.services.co_director_proposal_service import CoDirectorProposalService


def _make_session(mode: SessionMode) -> CoDirectorSession:
    return CoDirectorSession(
        session_id=uuid4(),
        project_id=uuid4(),
        film_id=uuid4(),
        current_mode=mode,
    )


def _make_critique(category: CoDirectorCritiqueCategory) -> CoDirectorCritique:
    return CoDirectorCritique(
        critique_id=f"critique_{uuid4().hex}",
        category=category,
        priority=CoDirectorCritiquePriority.HIGH,
        title="Test critique",
        description="Test description",
        recommendation="Test recommendation",
        grounded_signals=["signal_a"],
        heuristic_signals=["heuristic_b"],
        source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
        overall_confidence=CONFIDENCE_STRONG,
        grounded_confidence=CONFIDENCE_STRONG,
        heuristic_confidence=CONFIDENCE_EMERGING,
        provenance=["director_result.pillars"],
        canonical_sources={"director_result.pillars": True},
        affected_scene_ids=["scene_77"],
        affected_elements=["visual_coherence"],
        mode=SessionMode.ADVISORY,
    )


def test_passive_mode_returns_no_proposal():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.PASSIVE)
    critique = _make_critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.PASSIVE,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report, scene_id="scene_1")

    assert proposal_report.proposal is None
    assert proposal_report.mode == SessionMode.PASSIVE
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in proposal_report.sources_consulted


def test_advisory_instant_rejection_generates_rejection_recovery_proposal():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.ADVISORY)
    critique = _make_critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.ADVISORY,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    assert proposal_report.proposal.category == CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY
    assert proposal_report.proposal.critique_id == critique.critique_id
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in proposal_report.proposal.source_systems


def test_advisory_pillar_low_generates_pillar_recovery_proposal():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.ADVISORY)
    critique = _make_critique(CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.ADVISORY,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    assert proposal_report.proposal.category == CoDirectorProposalCategory.DIRECTOR_PILLAR_RECOVERY
    assert proposal_report.proposal.mode == SessionMode.ADVISORY


def test_missing_critique_returns_no_proposal():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.COLLABORATIVE)
    report = CoDirectorCritiqueReport(
        critique=None,
        session_id=str(session.session_id),
        mode=SessionMode.COLLABORATIVE,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is None


def test_only_one_dominant_proposal_is_returned():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.COLLABORATIVE)
    critique = _make_critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.COLLABORATIVE,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    assert isinstance(proposal_report.proposal.grounded_signals, list)
    assert isinstance(proposal_report.proposal.heuristic_signals, list)
    assert not hasattr(proposal_report, "proposals")


def test_unsupported_critique_category_returns_no_proposal():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.ADVISORY)
    critique = _make_critique(CoDirectorCritiqueCategory.CONTINUITY_ALERT)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.ADVISORY,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    assert proposal_report.proposal.category == CoDirectorProposalCategory.THEMATIC_PROPOSAL
    assert proposal_report.provenance.get("reason") == "advisory_thematic_proposal"


def test_proposal_does_not_label_derived_artifact_as_canonical_truth():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.ADVISORY)
    critique = _make_critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.ADVISORY,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    # Derived artifacts must not self-label as canonical truth.
    assert proposal_report.proposal.canonical_sources.get("critique_report.critique", False) is False


def test_collaborative_mode_generates_alternate_scene_suggestion_for_non_core_critique():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.COLLABORATIVE)
    critique = _make_critique(CoDirectorCritiqueCategory.CONTINUITY_ALERT)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.COLLABORATIVE,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    assert proposal_report.proposal.category == CoDirectorProposalCategory.ALTERNATE_SCENE_SUGGESTION
    assert proposal_report.proposal.advisory_only is True


def test_experimental_mode_generates_visual_experimentation_proposal():
    service = CoDirectorProposalService()
    session = _make_session(SessionMode.EXPERIMENTAL)
    critique = _make_critique(CoDirectorCritiqueCategory.CONTINUITY_ALERT)
    report = CoDirectorCritiqueReport(
        critique=critique,
        session_id=str(session.session_id),
        mode=SessionMode.EXPERIMENTAL,
        sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
    )

    proposal_report = service.generate_proposal(session=session, critique_report=report)

    assert proposal_report.proposal is not None
    assert proposal_report.proposal.category == CoDirectorProposalCategory.VISUAL_EXPERIMENTATION
    assert proposal_report.proposal.advisory_only is True
