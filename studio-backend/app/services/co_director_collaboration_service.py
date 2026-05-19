"""
Co-Director Collaboration Service - Phase 10.8

Bounded orchestration of critique/proposal/comparison/intensity outputs.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.models.co_director import (
    CoDirectorProposalCategory,
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
        vision_awareness: Optional[Dict[str, object]] = None,
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
        if isinstance(vision_awareness, dict):
            advisory_notes.extend((vision_awareness.get("visual_consistency_suggestions") or [])[:1])
            advisory_notes.extend((vision_awareness.get("pacing_suggestions") or [])[:1])
            advisory_notes.extend((vision_awareness.get("composition_observations") or [])[:1])
        advisory_notes = advisory_notes[:3]
        creative_disagreements: List[str] = []
        alternate_scene_suggestions: List[str] = []
        visual_experiments: List[str] = []
        thematic_proposals: List[str] = []

        if critique:
            creative_disagreements.append(
                f"{critique.title}: {critique.recommendation} (advisory only)"
            )
        if proposal:
            if proposal.category == CoDirectorProposalCategory.ALTERNATE_SCENE_SUGGESTION:
                alternate_scene_suggestions.append(proposal.recommendation)
            elif proposal.category == CoDirectorProposalCategory.VISUAL_EXPERIMENTATION:
                visual_experiments.append(proposal.recommendation)
            elif proposal.category == CoDirectorProposalCategory.THEMATIC_PROPOSAL:
                thematic_proposals.append(proposal.recommendation)
            elif proposal.category in {
                CoDirectorProposalCategory.DIRECTOR_REJECTION_RECOVERY,
                CoDirectorProposalCategory.DIRECTOR_PILLAR_RECOVERY,
                CoDirectorProposalCategory.CREATIVE_DISAGREEMENT,
            }:
                creative_disagreements.append(proposal.recommendation)
        if isinstance(vision_awareness, dict):
            visual_experiments.extend((vision_awareness.get("visual_consistency_suggestions") or [])[:2])
            alternate_scene_suggestions.extend((vision_awareness.get("pacing_suggestions") or [])[:2])
            thematic_proposals.extend((vision_awareness.get("composition_observations") or [])[:2])

        return CoDirectorCollaborationReport(
            session_id=str(session.session_id),
            mode=session.current_mode,
            critique=critique,
            proposal=proposal,
            comparison=comparison,
            intensity_profile=intensity_profile,
            dominant_focus=dominant_focus,
            advisory_notes=advisory_notes,
            creative_disagreements=creative_disagreements[:2],
            alternate_scene_suggestions=alternate_scene_suggestions[:2],
            visual_experiments=visual_experiments[:2],
            thematic_proposals=thematic_proposals[:2],
            advisory_only=True,
            sources_consulted=sources_consulted,
            provenance={
                "reason": "bounded_orchestration",
                "film_id": str(film_id) if film_id else None,
                "vision_awareness": {
                    "advisory_only": bool((vision_awareness or {}).get("advisory_only", True)),
                    "cannot_auto_regenerate": bool((vision_awareness or {}).get("cannot_auto_regenerate", True)),
                    "cannot_override_user_intent": bool((vision_awareness or {}).get("cannot_override_user_intent", True)),
                } if isinstance(vision_awareness, dict) else None,
            },
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
