"""
Tests for Co-Director Collaboration Service - Phase 10.8
"""

from uuid import uuid4

from app.models.co_director import (
    CoDirectorComparison,
    CoDirectorComparisonCategory,
    CoDirectorComparisonReport,
    CoDirectorCritique,
    CoDirectorCritiqueCategory,
    CoDirectorCritiquePriority,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorIntensityLevel,
    CoDirectorIntensityProfile,
    CoDirectorIntensityReport,
    CoDirectorProposal,
    CoDirectorProposalCategory,
    CoDirectorProposalReport,
    CoDirectorSession,
    SessionMode,
)
from app.services.co_director_collaboration_service import CoDirectorCollaborationService


def _session(mode: SessionMode) -> CoDirectorSession:
    return CoDirectorSession(session_id=uuid4(), project_id=uuid4(), film_id=uuid4(), current_mode=mode)


def _reports(mode: SessionMode):
    critique = CoDirectorCritique(
        critique_id="c1",
        category=CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION,
        priority=CoDirectorCritiquePriority.CRITICAL,
        title="Critique",
        description="Desc",
        recommendation="Fix rejection reasons",
        grounded_signals=["g"],
        heuristic_signals=["h"],
        source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
        overall_confidence=0.9,
        grounded_confidence=0.92,
        heuristic_confidence=0.3,
        provenance=["p"],
        canonical_sources={"a": True},
        affected_scene_ids=["scene_1"],
        affected_elements=["dialogue"],
        mode=mode,
    )
    proposal = CoDirectorProposal(
        proposal_id="p1",
        category=CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY,
        priority=CoDirectorCritiquePriority.CRITICAL,
        title="Proposal",
        description="Desc",
        recommendation="Perform one bounded rewrite",
        critique_id="c1",
        grounded_signals=["g"],
        heuristic_signals=["h"],
        source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
        overall_confidence=0.86,
        grounded_confidence=0.9,
        heuristic_confidence=0.32,
        provenance=["p"],
        canonical_sources={"a": True},
        affected_scene_ids=["scene_1"],
        affected_elements=["dialogue"],
        mode=mode,
    )
    comparison = CoDirectorComparison(
        comparison_id="cmp1",
        category=CoDirectorComparisonCategory.DIRECTOR_REJECTION_RECOVERY_ALIGNMENT,
        title="Comparison",
        description="Desc",
        recommendation="Re-evaluate after rewrite",
        critique_id="c1",
        proposal_id="p1",
        grounded_signals=["g"],
        heuristic_signals=["h"],
        source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
        overall_confidence=0.84,
        grounded_confidence=0.9,
        heuristic_confidence=0.33,
        dominance_reason="rejection_signals_have_priority_over_other_revisions",
        provenance=["p"],
        canonical_sources={"a": True},
        affected_scene_ids=["scene_1"],
        affected_elements=["dialogue"],
        mode=mode,
    )
    intensity = CoDirectorIntensityProfile(
        level=CoDirectorIntensityLevel.FOCUSED,
        rationale="Revision churn requires focused guidance.",
        critique_repetition_risk="moderate",
        escalation_required=False,
        recommended_mode=mode,
        grounded_signals=["revision_count:3"],
        heuristic_signals=["sustained_revision_cycle"],
        overall_confidence=0.79,
        grounded_confidence=0.88,
        heuristic_confidence=0.34,
        mode=mode,
    )
    return (
        CoDirectorCritiqueReport(critique=critique, mode=mode, sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]),
        CoDirectorProposalReport(proposal=proposal, mode=mode, sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]),
        CoDirectorComparisonReport(comparison=comparison, mode=mode, sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]),
        CoDirectorIntensityReport(intensity_profile=intensity, mode=mode, sources_consulted=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]),
    )


def test_passive_mode_is_silent():
    service = CoDirectorCollaborationService()
    report = service.build_collaboration_report(_session(SessionMode.PASSIVE), None, None, None, None)
    assert report.critique is None
    assert report.proposal is None
    assert report.comparison is None
    assert report.intensity_profile is None


def test_collaboration_report_assembles_dominant_focus_and_notes():
    service = CoDirectorCollaborationService()
    session = _session(SessionMode.COLLABORATIVE)
    critique_report, proposal_report, comparison_report, intensity_report = _reports(SessionMode.COLLABORATIVE)
    report = service.build_collaboration_report(
        session=session,
        critique_report=critique_report,
        proposal_report=proposal_report,
        comparison_report=comparison_report,
        intensity_report=intensity_report,
    )
    assert report.dominant_focus == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION.value
    assert len(report.advisory_notes) >= 1
    assert CoDirectorCritiqueSource.DIRECTOR_EVALUATOR in report.sources_consulted
