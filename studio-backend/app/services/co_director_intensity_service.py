"""
Co-Director Intensity Service - Phase 10.7

Session-aware, bounded intensity adaptation for advisory guidance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.co_director import (
    CONFIDENCE_CONSISTENT,
    CONFIDENCE_EMERGING,
    CONFIDENCE_STRONG,
    CoDirectorComparisonReport,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorIntensityLevel,
    CoDirectorIntensityProfile,
    CoDirectorIntensityReport,
    CoDirectorProposalReport,
    CoDirectorSession,
    SessionMode,
)


class CoDirectorIntensityService:
    """Derives bounded intensity profile from session state and dominant artifacts."""

    def generate_intensity(
        self,
        session: CoDirectorSession,
        critique_report: Optional[CoDirectorCritiqueReport] = None,
        proposal_report: Optional[CoDirectorProposalReport] = None,
        comparison_report: Optional[CoDirectorComparisonReport] = None,
        film_id: Optional[str] = None,
    ) -> CoDirectorIntensityReport:
        sources_consulted = [CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]

        if session.current_mode == SessionMode.PASSIVE:
            return CoDirectorIntensityReport(
                intensity_profile=None,
                session_id=str(session.session_id),
                mode=session.current_mode,
                sources_consulted=sources_consulted,
                provenance={"reason": "passive_mode", "film_id": str(film_id) if film_id else None},
            )

        grounded_signals = [
            f"revision_count:{session.revision_count}",
            f"repeated_critique_count:{session.repeated_critique_count}",
        ]
        if critique_report and critique_report.critique:
            grounded_signals.append(f"critique_category:{critique_report.critique.category.value}")
        if proposal_report and proposal_report.proposal:
            grounded_signals.append(f"proposal_category:{proposal_report.proposal.category.value}")
        if comparison_report and comparison_report.comparison:
            grounded_signals.append(f"comparison_category:{comparison_report.comparison.category.value}")

        heuristic_signals: List[str] = []
        if session.revision_count >= 3:
            heuristic_signals.append("sustained_revision_cycle")
        if session.repeated_critique_count >= 2:
            heuristic_signals.append("repetition_risk_elevated")

        level, rationale, escalation_required = self._resolve_intensity(session)

        profile = CoDirectorIntensityProfile(
            level=level,
            rationale=rationale,
            critique_repetition_risk=self._repetition_risk(session.repeated_critique_count),
            escalation_required=escalation_required,
            recommended_mode=session.current_mode,
            grounded_signals=grounded_signals,
            heuristic_signals=heuristic_signals,
            overall_confidence=CONFIDENCE_CONSISTENT,
            grounded_confidence=CONFIDENCE_STRONG,
            heuristic_confidence=CONFIDENCE_EMERGING,
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

        return CoDirectorIntensityReport(
            intensity_profile=profile,
            session_id=str(session.session_id),
            mode=session.current_mode,
            sources_consulted=sources_consulted,
            provenance={"reason": "session_state_intensity_resolution", "film_id": str(film_id) if film_id else None},
        )

    def _resolve_intensity(self, session: CoDirectorSession) -> tuple[CoDirectorIntensityLevel, str, bool]:
        repeated = session.repeated_critique_count
        revisions = session.revision_count

        if session.current_mode == SessionMode.COLLABORATIVE:
            if repeated >= 3 or revisions >= 8:
                return (
                    CoDirectorIntensityLevel.DEEP,
                    "Collaborative mode with high repetition/revision load requires deep guidance.",
                    True,
                )
            if repeated >= 1 or revisions >= 3:
                return (
                    CoDirectorIntensityLevel.FOCUSED,
                    "Collaborative mode with active revision cycles benefits from focused guidance.",
                    False,
                )
            return (
                CoDirectorIntensityLevel.LIGHT,
                "Collaborative mode with low churn remains in light guidance.",
                False,
            )

        # Advisory mode
        if repeated >= 3 or revisions >= 8:
            return (
                CoDirectorIntensityLevel.FOCUSED,
                "Advisory mode capped at focused intensity despite high churn.",
                True,
            )
        if repeated >= 1 or revisions >= 3:
            return (
                CoDirectorIntensityLevel.FOCUSED,
                "Advisory mode with revision churn requires focused guidance.",
                False,
            )
        return (
            CoDirectorIntensityLevel.LIGHT,
            "Advisory mode with low churn remains light.",
            False,
        )

    def _repetition_risk(self, repeated_critique_count: int) -> str:
        if repeated_critique_count <= 0:
            return "low"
        if repeated_critique_count < 3:
            return "moderate"
        return "high"


# Singleton instance
co_director_intensity_service = CoDirectorIntensityService()
