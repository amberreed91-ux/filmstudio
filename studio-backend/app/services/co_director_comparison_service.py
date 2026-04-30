"""
Co-Director Comparison Service - Phase 10.6

Bounded comparison between dominant critique and dominant proposal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.co_director import (
    CoDirectorComparison,
    CoDirectorComparisonCategory,
    CoDirectorComparisonReport,
    CoDirectorCritiqueCategory,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorProposalCategory,
    CoDirectorProposalReport,
    CoDirectorSession,
    SessionMode,
)


class CoDirectorComparisonService:
    """Produces at most one dominant comparison from critique/proposal artifacts."""

    def generate_comparison(
        self,
        session: CoDirectorSession,
        director_result: Optional[Dict[str, Any]],
        critique_report: Optional[CoDirectorCritiqueReport],
        proposal_report: Optional[CoDirectorProposalReport],
        scene_id: Optional[str] = None,
        film_id: Optional[str] = None,
    ) -> CoDirectorComparisonReport:
        sources_consulted = [CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]

        if session.current_mode == SessionMode.PASSIVE:
            return self._build_report(
                comparison=None,
                session=session,
                sources_consulted=sources_consulted,
                provenance={"reason": "passive_mode", "film_id": str(film_id) if film_id else None},
            )

        critique = critique_report.critique if critique_report else None
        proposal = proposal_report.proposal if proposal_report else None
        if critique is None or proposal is None:
            return self._build_report(
                comparison=None,
                session=session,
                sources_consulted=sources_consulted,
                provenance={"reason": "missing_critique_or_proposal", "film_id": str(film_id) if film_id else None},
            )

        if (
            critique.category == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION
            and proposal.category == CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY
        ):
            comparison = self._build_rejection_alignment(
                session=session,
                director_result=director_result or {},
                critique=critique,
                proposal=proposal,
                scene_id=scene_id,
            )
            return self._build_report(
                comparison=comparison,
                session=session,
                sources_consulted=sources_consulted,
                provenance={"reason": "rejection_recovery_alignment", "film_id": str(film_id) if film_id else None},
            )

        if (
            critique.category == CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW
            and proposal.category == CoDirectorProposalCategory.DIRECTOR_PILLAR_RECOVERY
        ):
            comparison = self._build_pillar_alignment(
                session=session,
                director_result=director_result or {},
                critique=critique,
                proposal=proposal,
                scene_id=scene_id,
            )
            return self._build_report(
                comparison=comparison,
                session=session,
                sources_consulted=sources_consulted,
                provenance={"reason": "pillar_recovery_alignment", "film_id": str(film_id) if film_id else None},
            )

        return self._build_report(
            comparison=None,
            session=session,
            sources_consulted=sources_consulted,
            provenance={"reason": "unsupported_alignment", "film_id": str(film_id) if film_id else None},
        )

    def _build_report(
        self,
        comparison: Optional[CoDirectorComparison],
        session: CoDirectorSession,
        sources_consulted: List[CoDirectorCritiqueSource],
        provenance: Dict[str, Any],
    ) -> CoDirectorComparisonReport:
        return CoDirectorComparisonReport(
            comparison=comparison,
            session_id=str(session.session_id),
            mode=session.current_mode,
            sources_consulted=sources_consulted,
            provenance=provenance,
        )

    def _build_rejection_alignment(
        self,
        session: CoDirectorSession,
        director_result: Dict[str, Any],
        critique: Any,
        proposal: Any,
        scene_id: Optional[str],
    ) -> CoDirectorComparison:
        grounded = list(critique.grounded_signals) + [f"proposal_category:{proposal.category.value}"]
        heuristic = list(proposal.heuristic_signals)
        score = self._coerce_float((director_result or {}).get("score"))
        if score is not None:
            grounded.append(f"current_score:{score:.3f}")
        return CoDirectorComparison(
            comparison_id=f"comparison_{uuid4().hex}",
            category=CoDirectorComparisonCategory.DIRECTOR_REJECTION_RECOVERY_ALIGNMENT,
            title="Rejection recovery proposal aligns with dominant director rejection",
            description="Current dominant proposal directly targets the rejection signals raised by director evaluation.",
            recommendation="Execute one bounded recovery pass focused on rejection signals, then re-evaluate before broader changes.",
            critique_id=critique.critique_id,
            proposal_id=proposal.proposal_id,
            grounded_signals=grounded,
            heuristic_signals=heuristic,
            source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
            overall_confidence=0.84,
            grounded_confidence=0.9,
            heuristic_confidence=0.33 if heuristic else 0.0,
            dominance_reason="rejection_signals_have_priority_over_other_revisions",
            provenance=["critique_report.critique", "proposal_report.proposal", "director_result.score"],
            canonical_sources={
                "critique_report.critique": False,
                "proposal_report.proposal": False,
                "director_result.score": True,
            },
            affected_scene_ids=self._scene_ids(session, critique.affected_scene_ids, scene_id),
            affected_elements=list(critique.affected_elements),
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

    def _build_pillar_alignment(
        self,
        session: CoDirectorSession,
        director_result: Dict[str, Any],
        critique: Any,
        proposal: Any,
        scene_id: Optional[str],
    ) -> CoDirectorComparison:
        grounded = list(critique.grounded_signals) + [f"proposal_category:{proposal.category.value}"]
        heuristic = list(proposal.heuristic_signals)
        pillars = director_result.get("pillars")
        if isinstance(pillars, dict):
            low_pillars = [name for name, value in pillars.items() if self._coerce_float(value) is not None and float(value) <= 0.45]
            if low_pillars:
                grounded.append(f"low_pillars:{','.join(low_pillars)}")
        return CoDirectorComparison(
            comparison_id=f"comparison_{uuid4().hex}",
            category=CoDirectorComparisonCategory.DIRECTOR_PILLAR_RECOVERY_ALIGNMENT,
            title="Pillar recovery proposal aligns with dominant low-pillar signals",
            description="Current dominant proposal addresses the weakest grounded director pillars with focused recovery scope.",
            recommendation="Prioritize the lowest grounded pillars first and validate uplift with one follow-up director pass.",
            critique_id=critique.critique_id,
            proposal_id=proposal.proposal_id,
            grounded_signals=grounded,
            heuristic_signals=heuristic,
            source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
            overall_confidence=0.78,
            grounded_confidence=0.84,
            heuristic_confidence=0.36 if heuristic else 0.0,
            dominance_reason="lowest_grounded_pillars_define_primary_revision_path",
            provenance=["critique_report.critique", "proposal_report.proposal", "director_result.pillars"],
            canonical_sources={
                "critique_report.critique": False,
                "proposal_report.proposal": False,
                "director_result.pillars": True,
            },
            affected_scene_ids=self._scene_ids(session, critique.affected_scene_ids, scene_id),
            affected_elements=list(critique.affected_elements),
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

    def _scene_ids(self, session: CoDirectorSession, critique_scene_ids: List[str], scene_id: Optional[str]) -> List[str]:
        if scene_id:
            return [str(scene_id)]
        if critique_scene_ids:
            return [str(item) for item in critique_scene_ids]
        if session.active_scene_id:
            return [str(session.active_scene_id)]
        return []

    def _coerce_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


# Singleton instance
co_director_comparison_service = CoDirectorComparisonService()
