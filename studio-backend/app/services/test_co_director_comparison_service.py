"""
Tests for Co-Director Comparison Service - Phase 10.6
"""

from uuid import uuid4

from app.models.co_director import (
    CoDirectorComparisonCategory,
    CoDirectorCritique,
    CoDirectorCritiqueCategory,
    CoDirectorCritiquePriority,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorProposal,
    CoDirectorProposalCategory,
    CoDirectorProposalReport,
    CoDirectorSession,
    SessionMode,
)
from app.services.co_director_comparison_service import CoDirectorComparisonService


def _session(mode: SessionMode) -> CoDirectorSession:
    return CoDirectorSession(session_id=uuid4(), project_id=uuid4(), film_id=uuid4(), current_mode=mode)


def _critique(category: CoDirectorCritiqueCategory) -> CoDirectorCritique:
    return CoDirectorCritique(
        critique_id=f"critique_{uuid4().hex}",
        category=category,
        priority=CoDirectorCritiquePriority.HIGH,
        title="Critique",
        description="Description",
        recommendation="Recommendation",
        grounded_signals=["g1"],
        heuristic_signals=["h1"],
        source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
        overall_confidence=0.8,
        grounded_confidence=0.85,
        heuristic_confidence=0.3,
        provenance=["p1"],
        canonical_sources={"c1": True},
        affected_scene_ids=["scene_1"],
        affected_elements=["dialogue"],
        mode=SessionMode.ADVISORY,
    )


def _proposal(category: CoDirectorProposalCategory, critique_id: str) -> CoDirectorProposal:
    return CoDirectorProposal(
        proposal_id=f"proposal_{uuid4().hex}",
        category=category,
        priority=CoDirectorCritiquePriority.HIGH,
        title="Proposal",
        description="Description",
        recommendation="Recommendation",
        critique_id=critique_id,
        grounded_signals=["g1"],
        heuristic_signals=["h1"],
        source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
        overall_confidence=0.78,
        grounded_confidence=0.82,
        heuristic_confidence=0.31,
        provenance=["p2"],
        canonical_sources={"c2": True},
        affected_scene_ids=["scene_1"],
        affected_elements=["dialogue"],
        mode=SessionMode.ADVISORY,
    )


def test_passive_mode_returns_no_comparison():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.PASSIVE)
    report = service.generate_comparison(session, {}, None, None)
    assert report.comparison is None


def test_rejection_alignment_generates_comparison():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.ADVISORY)
    critique = _critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    proposal = _proposal(CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY, critique.critique_id)
    comparison_report = service.generate_comparison(
        session=session,
        director_result={"score": 0.45},
        critique_report=CoDirectorCritiqueReport(critique=critique, mode=SessionMode.ADVISORY),
        proposal_report=CoDirectorProposalReport(proposal=proposal, mode=SessionMode.ADVISORY),
    )
    assert comparison_report.comparison is not None
    assert comparison_report.comparison.category == CoDirectorComparisonCategory.DIRECTOR_REJECTION_RECOVERY_ALIGNMENT


def test_pillar_alignment_generates_comparison():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.COLLABORATIVE)
    critique = _critique(CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW)
    proposal = _proposal(CoDirectorProposalCategory.DIRECTOR_PILLAR_RECOVERY, critique.critique_id)
    comparison_report = service.generate_comparison(
        session=session,
        director_result={"pillars": {"visual_coherence": 0.31, "continuity": 0.7}},
        critique_report=CoDirectorCritiqueReport(critique=critique, mode=SessionMode.COLLABORATIVE),
        proposal_report=CoDirectorProposalReport(proposal=proposal, mode=SessionMode.COLLABORATIVE),
    )
    assert comparison_report.comparison is not None
    assert comparison_report.comparison.category == CoDirectorComparisonCategory.DIRECTOR_PILLAR_RECOVERY_ALIGNMENT


def test_missing_inputs_returns_none():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.ADVISORY)
    comparison_report = service.generate_comparison(session, {}, CoDirectorCritiqueReport(), CoDirectorProposalReport())
    assert comparison_report.comparison is None


def test_conflicting_rejection_and_low_pillars_prefers_rejection_path():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.ADVISORY)
    critique = _critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    proposal = _proposal(CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY, critique.critique_id)
    comparison_report = service.generate_comparison(
        session=session,
        director_result={"score": 0.22, "pillars": {"visual_coherence": 0.1}},
        critique_report=CoDirectorCritiqueReport(critique=critique, mode=SessionMode.ADVISORY),
        proposal_report=CoDirectorProposalReport(proposal=proposal, mode=SessionMode.ADVISORY),
    )
    assert comparison_report.comparison is not None
    assert comparison_report.comparison.category == CoDirectorComparisonCategory.DIRECTOR_REJECTION_RECOVERY_ALIGNMENT


def test_grounded_signals_capture_director_score_not_heuristic():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.ADVISORY)
    critique = _critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    proposal = _proposal(CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY, critique.critique_id)
    comparison_report = service.generate_comparison(
        session=session,
        director_result={"score": 0.45},
        critique_report=CoDirectorCritiqueReport(critique=critique, mode=SessionMode.ADVISORY),
        proposal_report=CoDirectorProposalReport(proposal=proposal, mode=SessionMode.ADVISORY),
    )
    assert comparison_report.comparison is not None
    assert any(signal.startswith("current_score:") for signal in comparison_report.comparison.grounded_signals)
    assert not any(signal.startswith("current_score:") for signal in comparison_report.comparison.heuristic_signals)


def test_grounded_signals_capture_low_pillars_not_heuristic():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.COLLABORATIVE)
    critique = _critique(CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW)
    proposal = _proposal(CoDirectorProposalCategory.DIRECTOR_PILLAR_RECOVERY, critique.critique_id)
    comparison_report = service.generate_comparison(
        session=session,
        director_result={"pillars": {"visual_coherence": 0.31, "continuity": 0.7}},
        critique_report=CoDirectorCritiqueReport(critique=critique, mode=SessionMode.COLLABORATIVE),
        proposal_report=CoDirectorProposalReport(proposal=proposal, mode=SessionMode.COLLABORATIVE),
    )
    assert comparison_report.comparison is not None
    assert any(signal.startswith("low_pillars:") for signal in comparison_report.comparison.grounded_signals)
    assert not any(signal.startswith("low_pillars:") for signal in comparison_report.comparison.heuristic_signals)


def test_comparison_does_not_label_derived_artifacts_as_canonical_truth():
    service = CoDirectorComparisonService()
    session = _session(SessionMode.ADVISORY)
    critique = _critique(CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION)
    proposal = _proposal(CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY, critique.critique_id)
    comparison_report = service.generate_comparison(
        session=session,
        director_result={"score": 0.42},
        critique_report=CoDirectorCritiqueReport(critique=critique, mode=SessionMode.ADVISORY),
        proposal_report=CoDirectorProposalReport(proposal=proposal, mode=SessionMode.ADVISORY),
    )
    assert comparison_report.comparison is not None
    assert comparison_report.comparison.canonical_sources.get("critique_report.critique", False) is False
    assert comparison_report.comparison.canonical_sources.get("proposal_report.proposal", False) is False
