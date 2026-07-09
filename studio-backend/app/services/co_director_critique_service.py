"""
Co-Director Critique Service - Phase 10.4.2

Director-signal-only critique generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.co_director import (
    CoDirectorCritique,
    CoDirectorCritiqueCategory,
    CoDirectorCritiquePriority,
    CoDirectorCritiqueReport,
    CoDirectorCritiqueSource,
    CoDirectorSession,
    SessionMode,
)


class CoDirectorCritiqueService:
    """
    Builds at most one dominant Co-Director critique from DirectorEvaluator output.
    """

    DIRECTOR_PILLAR_LOW_THRESHOLD = 0.45
    DIRECTOR_SCORE_LOW_THRESHOLD = 0.65

    def generate_critique(
        self,
        session: CoDirectorSession,
        director_result: Optional[Dict[str, Any]],
        scene_id: Optional[str] = None,
        film_id: Optional[str] = None,
        vision_awareness: Optional[Dict[str, Any]] = None,
    ) -> CoDirectorCritiqueReport:
        sources_consulted = [CoDirectorCritiqueSource.DIRECTOR_EVALUATOR]

        if session.current_mode == SessionMode.PASSIVE:
            return self._build_report(
                critique=None,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "director_evaluator",
                    "reason": "passive_mode",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        if not isinstance(director_result, dict):
            return self._build_report(
                critique=None,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "director_evaluator",
                    "reason": "invalid_director_result",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        rejection_reasons = self._as_str_list(director_result.get("rejection_reasons"))
        if rejection_reasons:
            critique = self._build_rejection_critique(
                session=session,
                director_result=director_result,
                rejection_reasons=rejection_reasons,
                scene_id=scene_id,
                vision_awareness=vision_awareness,
            )
            return self._build_report(
                critique=critique,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "director_evaluator",
                    "reason": "rejection_reasons",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        low_pillar_signals = self._extract_low_pillar_signals(director_result)
        if low_pillar_signals:
            critique = self._build_pillar_low_critique(
                session=session,
                director_result=director_result,
                low_pillar_signals=low_pillar_signals,
                scene_id=scene_id,
                vision_awareness=vision_awareness,
            )
            return self._build_report(
                critique=critique,
                session=session,
                sources_consulted=sources_consulted,
                provenance={
                    "source": "director_evaluator",
                    "reason": "low_pillar_signals",
                    "film_id": str(film_id) if film_id else None,
                },
            )

        return self._build_report(
            critique=None,
            session=session,
            sources_consulted=sources_consulted,
            provenance={
                "source": "director_evaluator",
                "reason": "no_actionable_director_signals",
                "film_id": str(film_id) if film_id else None,
            },
        )

    def _build_report(
        self,
        critique: Optional[CoDirectorCritique],
        session: CoDirectorSession,
        sources_consulted: List[CoDirectorCritiqueSource],
        provenance: Dict[str, Any],
    ) -> CoDirectorCritiqueReport:
        return CoDirectorCritiqueReport(
            critique=critique,
            session_id=str(session.session_id),
            mode=session.current_mode,
            sources_consulted=sources_consulted,
            provenance=provenance,
        )

    def _build_rejection_critique(
        self,
        session: CoDirectorSession,
        director_result: Dict[str, Any],
        rejection_reasons: List[str],
        scene_id: Optional[str],
        vision_awareness: Optional[Dict[str, Any]] = None,
    ) -> CoDirectorCritique:
        revision_notes = self._as_str_list(director_result.get("revision_notes"))
        grounded_signals = [f"rejection_reason:{reason}" for reason in rejection_reasons]
        if isinstance(vision_awareness, dict):
            grounded_signals.append(f"vision_memory_count:{int(vision_awareness.get('scene_memory_count', 0))}")
            grounded_signals.append(f"vision_continuity_issues:{int(vision_awareness.get('continuity_issue_count', 0))}")
        heuristic_signals = [f"revision_note:{note}" for note in revision_notes]
        affected_elements = self._extract_affected_elements(rejection_reasons, [])

        return CoDirectorCritique(
            critique_id=f"critique_{uuid4().hex}",
            category=CoDirectorCritiqueCategory.DIRECTOR_INSTANT_REJECTION,
            priority=CoDirectorCritiquePriority.CRITICAL,
            title="Director instant rejection blocks scene progression",
            description="Director evaluator triggered instant rejection signals requiring revision before progression.",
            recommendation="Resolve rejection reasons first, then re-run director evaluation before downstream critique passes.",
            grounded_signals=grounded_signals,
            heuristic_signals=heuristic_signals,
            source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
            overall_confidence=0.90 if len(grounded_signals) > 1 else 0.84,
            grounded_confidence=0.92,
            heuristic_confidence=0.35 if heuristic_signals else 0.0,
            provenance=["director_result.rejection_reasons", "director_result.revision_notes"],
            canonical_sources={"director_result.rejection_reasons": True},
            affected_scene_ids=self._resolve_affected_scene_ids(session, scene_id),
            affected_elements=affected_elements,
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

    def _build_pillar_low_critique(
        self,
        session: CoDirectorSession,
        director_result: Dict[str, Any],
        low_pillar_signals: List[str],
        scene_id: Optional[str],
        vision_awareness: Optional[Dict[str, Any]] = None,
    ) -> CoDirectorCritique:
        revision_notes = self._as_str_list(director_result.get("revision_notes"))
        grounded_signals = [f"low_pillar:{signal}" for signal in low_pillar_signals]
        if isinstance(vision_awareness, dict):
            grounded_signals.append(f"vision_memory_count:{int(vision_awareness.get('scene_memory_count', 0))}")
            grounded_signals.append(f"vision_continuity_issues:{int(vision_awareness.get('continuity_issue_count', 0))}")
        heuristic_signals = [f"revision_note:{note}" for note in revision_notes]
        affected_elements = self._extract_affected_elements([], low_pillar_signals)

        return CoDirectorCritique(
            critique_id=f"critique_{uuid4().hex}",
            category=CoDirectorCritiqueCategory.DIRECTOR_PILLAR_LOW,
            priority=CoDirectorCritiquePriority.HIGH,
            title="Director pillar signals indicate high revision severity",
            description="Director evaluation shows low pillar or coherence strength that indicates revision risk.",
            recommendation="Prioritize rewriting weak visual/coherence beats and retest for stable revise-or-approve outcomes.",
            grounded_signals=grounded_signals,
            heuristic_signals=heuristic_signals,
            source_systems=[CoDirectorCritiqueSource.DIRECTOR_EVALUATOR],
            overall_confidence=0.82 if len(grounded_signals) > 1 else 0.74,
            grounded_confidence=0.84,
            heuristic_confidence=0.40 if heuristic_signals else 0.0,
            provenance=["director_result.pillars", "director_result.score", "director_result.revision_notes"],
            canonical_sources={"director_result.pillars": True, "director_result.score": True},
            affected_scene_ids=self._resolve_affected_scene_ids(session, scene_id),
            affected_elements=affected_elements,
            session_id=str(session.session_id),
            mode=session.current_mode,
        )

    def _resolve_affected_scene_ids(self, session: CoDirectorSession, scene_id: Optional[str]) -> List[str]:
        if scene_id:
            return [str(scene_id)]
        if session.active_scene_id:
            return [str(session.active_scene_id)]
        return []

    def _extract_low_pillar_signals(self, director_result: Dict[str, Any]) -> List[str]:
        pillars = director_result.get("pillars")
        if not isinstance(pillars, dict):
            return []

        low_signals: List[str] = []
        for name, raw_value in pillars.items():
            value = self._coerce_float(raw_value)
            if value is None:
                continue
            if value <= self.DIRECTOR_PILLAR_LOW_THRESHOLD:
                low_signals.append(f"{name}={value:.3f}")

        if not low_signals:
            return []

        decision = director_result.get("decision")
        decision_str = str(decision).upper() if decision is not None else ""
        requires_revision = bool(director_result.get("requires_revision"))
        score = self._coerce_float(director_result.get("score"))
        if not (
            decision_str.endswith("REVISE")
            or decision_str.endswith("REJECT")
            or requires_revision
            or (score is not None and score < self.DIRECTOR_SCORE_LOW_THRESHOLD)
        ):
            return []

        return low_signals

    def _extract_affected_elements(self, rejection_reasons: List[str], low_pillar_signals: List[str]) -> List[str]:
        elements: List[str] = []
        for reason in rejection_reasons:
            if "dialogue" in reason:
                elements.append("dialogue")
            if "tone" in reason:
                elements.append("tone")
            if "visual" in reason:
                elements.append("visual")
            if "continuity" in reason:
                elements.append("continuity")

        for signal in low_pillar_signals:
            if "intent_alignment" in signal:
                elements.append("intent_alignment")
            if "emotional_consistency" in signal:
                elements.append("emotional_consistency")
            if "visual_coherence" in signal:
                elements.append("visual_coherence")
            if "continuity" in signal:
                elements.append("continuity")

        deduped = []
        for element in elements:
            if element not in deduped:
                deduped.append(element)
        return deduped

    def _coerce_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _as_str_list(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None and str(item).strip()]


# Singleton instance
co_director_critique_service = CoDirectorCritiqueService()
