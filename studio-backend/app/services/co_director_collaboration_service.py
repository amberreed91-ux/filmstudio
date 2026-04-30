"""
Co-Director Collaboration Service - Phase 10.8

Bounded orchestration of critique/proposal/comparison/intensity outputs.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.models.co_director import (
    CoDirectorCollaborationReport,
    CoDirectorComparisonReport,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorIntensityReport,
    CoDirectorProposalReport,
    CoDirectorSession,
    SessionMode,
)


class CoDirectorCollaborationService:
    """Builds one bounded collaboration report for advisory/collaborative modes."""

    def build_collaboration_report(
        self,
        session: CoDirectorSession,
        critique_report: Optional[CoDirectorCritiqueReport],
        proposal_report: Optional[CoDirectorProposalReport],
        comparison_report: Optional[CoDirectorComparisonReport],
        intensity_report: Optional[CoDirectorIntensityReport],
        film_id: Optional[str] = None,
    ) -> CoDirectorCollaborationReport:
        sources_consulted = self._collect_sources(
            critique_report=critique_report,
            proposal_report=proposal_report,
            comparison_report=comparison_report,
            intensity_report=intensity_report,
        )

        if session.current_mode == SessionMode.PASSIVE:
            return CoDirectorCollaborationReport(
                session_id=str(session.session_id),
                mode=session.current_mode,
                sources_consulted=sources_consulted,
                provenance={"reason": "passive_mode", "film_id": str(film_id) if film_id else None},
            )

        critique = critique_report.critique if critique_report else None
        proposal = proposal_report.proposal if proposal_report else None
        comparison = comparison_report.comparison if comparison_report else None
        intensity_profile = intensity_report.intensity_profile if intensity_report else None

        dominant_focus = None
        if critique:
            dominant_focus = critique.category.value
        elif proposal:
            dominant_focus = proposal.category.value
        elif comparison:
            dominant_focus = comparison.category.value

        advisory_notes: List[str] = []
        if critique:
            advisory_notes.append(critique.recommendation)
        if proposal:
            advisory_notes.append(proposal.recommendation)
        if comparison:
            advisory_notes.append(comparison.recommendation)
        if intensity_profile:
            advisory_notes.append(intensity_profile.rationale)
        advisory_notes = advisory_notes[:3]

        return CoDirectorCollaborationReport(
            session_id=str(session.session_id),
            mode=session.current_mode,
            critique=critique,
            proposal=proposal,
            comparison=comparison,
            intensity_profile=intensity_profile,
            dominant_focus=dominant_focus,
            advisory_notes=advisory_notes,
            sources_consulted=sources_consulted,
            provenance={"reason": "bounded_orchestration", "film_id": str(film_id) if film_id else None},
        )

    def _collect_sources(
        self,
        critique_report: Optional[CoDirectorCritiqueReport],
        proposal_report: Optional[CoDirectorProposalReport],
        comparison_report: Optional[CoDirectorComparisonReport],
        intensity_report: Optional[CoDirectorIntensityReport],
    ) -> List[CoDirectorCritiqueSource]:
        combined: List[CoDirectorCritiqueSource] = []
        reports = [critique_report, proposal_report, comparison_report, intensity_report]
        for report in reports:
            if report is None:
                continue
            for source in getattr(report, "sources_consulted", []) or []:
                if source not in combined:
                    combined.append(source)
        if CoDirectorCritiqueSource.DIRECTOR_EVALUATOR not in combined:
            combined.append(CoDirectorCritiqueSource.DIRECTOR_EVALUATOR)
        return combined


# Singleton instance
co_director_collaboration_service = CoDirectorCollaborationService()
