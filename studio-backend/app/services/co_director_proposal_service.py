"""
Co-Director Proposal Service - Phase 10.5

Bounded, advisory-only proposal generation from critique reports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.co_director import (
    CoDirectorCritiqueCategory,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorProposal,
    CoDirectorProposalCategory,
    CoDirectorProposalReport,
    CoDirectorSession,
    SessionMode,
)


class CoDirectorProposalService:
    """
    Builds at most one dominant proposal from an existing critique report.
    """

    def generate_proposal(
        self,
        session: CoDirectorSession,
        critique_report: Optional[CoDirectorCritiqueReport],
        scene_id: Optional[str] = None,
        film_id: Optional[str] = None,
    ) -> CoDirectorProposalReport:
        sources_consulted = [CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]

        if session.current_mode == SessionMode.PASSIVE:
            return self._build_report(
                proposal=None,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "co_director_critique_report",
                    "reason": "passive_mode",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        critique = critique_report.critique if critique_report else None
        if critique is None:
            return self._build_report(
                proposal=None,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "co_director_critique_report",
                    "reason": "no_dominant_critique",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        if critique.category == CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION:
            proposal = self._build_rejection_recovery_proposal(
                session=session,
                critique_report=critique_report,
                scene_id=scene_id,
            )
            return self._build_report(
                proposal=proposal,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "co_director_critique_report",
                    "reason": "director_instant_rejection",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        if critique.category == CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW:
            proposal = self._build_pillar_recovery_proposal(
                session=session,
                critique_report=critique_report,
                scene_id=scene_id,
            )
            return self._build_report(
                proposal=proposal,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "co_director_critique_report",
                    "reason": "director_pillar_low",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        return self._build_report(
            proposal=None,
            session=session,
            sources_consulted=sources_consulted,
            provenance={
                "source": "co_director_critique_report",
                "reason": "unsupported_critique_category_for_phase_10_5",
                "film_id": str(film_id) if film_id else None,
            },
        )

    def _build_report(
        self,
        proposal: Optional[CoDirectorProposal],
        session: CoDirectorSession,
        sources_consulted: List[CoDirectorCritiqueSource],
        provenance: Dict[str, Any],
    ) -> CoDirectorProposalReport:
        return CoDirectorProposalReport(
            proposal=proposal,
            session_id=str(session.session_id),
            mode=session.current_mode,
            sources_consulted=sources_consulted,
            provenance=provenance,
        )

    def _build_rejection_recovery_proposal(
        self,
        session: CoDirectorSession,
        critique_report: CoDirectorCritiqueReport,
        scene_id: Optional[str],
    ) -> CoDirectorProposal:
        critique = critique_report.critique
        assert critique is not None

        return CoDirectorProposal(
            proposal_id=f"proposal_{uuid4().hex}",
            category=CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY,
            priority=critique.priority,
            title="Recover from director rejection before further iteration",
            description="Address the dominant rejection signals in a single bounded rewrite pass.",
            recommendation="Resolve grounded rejection reasons first, then re-run director evaluation and stop if rejection persists.",
            critique_id=critique.critique_id,
            grounded_signals=list(critique.grounded_signals),
            heuristic_signals=list(critique.heuristic_signals),
            source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
            overall_confidence=0.86,
            grounded_confidence=0.90,
            heuristic_confidence=0.32 if critique.heuristic_signals else 0.0,
            provenance=["critique_report.critique", "critique.grounded_signals", "critique.heuristic_signals"],
            canonical_sources={"critique_report.critique": False},
            affected_scene_ids=self._resolve_affected_scene_ids(session, critique.affected_scene_ids, scene_id),
            affected_elements=list(critique.affected_elements),
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

    def _build_pillar_recovery_proposal(
        self,
        session: CoDirectorSession,
        critique_report: CoDirectorCritiqueReport,
        scene_id: Optional[str],
    ) -> CoDirectorProposal:
        critique = critique_report.critique
        assert critique is not None

        return CoDirectorProposal(
            proposal_id=f"proposal_{uuid4().hex}",
            category=CoDirectorProposalCategory.DIRECTOR_PILLAR_RECOVERY,
            priority=critique.priority,
            title="Recover weak director pillars with one targeted revision pass",
            description="Improve the lowest grounded director pillars before any broader experimentation.",
            recommendation="Prioritize the weakest grounded pillar signals and re-evaluate once to confirm severity reduction.",
            critique_id=critique.critique_id,
            grounded_signals=list(critique.grounded_signals),
            heuristic_signals=list(critique.heuristic_signals),
            source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
            overall_confidence=0.78,
            grounded_confidence=0.84,
            heuristic_confidence=0.36 if critique.heuristic_signals else 0.0,
            provenance=["critique_report.critique", "critique.grounded_signals", "critique.heuristic_signals"],
            canonical_sources={"critique_report.critique": False},
            affected_scene_ids=self._resolve_affected_scene_ids(session, critique.affected_scene_ids, scene_id),
            affected_elements=list(critique.affected_elements),
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

    def _resolve_affected_scene_ids(
        self,
        session: CoDirectorSession,
        critique_scene_ids: List[str],
        scene_id: Optional[str],
    ) -> List[str]:
        if scene_id:
            return [str(scene_id)]
        if critique_scene_ids:
            return [str(value) for value in critique_scene_ids]
        if session.active_scene_id:
            return [str(session.active_scene_id)]
        return []


# Singleton instance
co_director_proposal_service = CoDirectorProposalService()
