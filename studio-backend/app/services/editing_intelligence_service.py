from __future__ import annotations

from typing import Any, Dict, List

from app.models.editing_suggestion import EditingSuggestion


class EditingIntelligenceService:
    def build_editing_intelligence(
        self,
        screening_playlist: Any,
        scene_transitions: Any,
        emotional_continuity: Any,
        sequence_flow: Any,
    ) -> Dict[str, Any]:
        playlist = screening_playlist if isinstance(screening_playlist, list) else []
        transitions = scene_transitions if isinstance(scene_transitions, list) else []
        continuity = emotional_continuity if isinstance(emotional_continuity, dict) else {}
        flow = sequence_flow if isinstance(sequence_flow, dict) else {}
        suggestions: List[EditingSuggestion] = []

        if len(playlist) >= 3:
            first = playlist[0] if isinstance(playlist[0], dict) else {}
            last = playlist[-1] if isinstance(playlist[-1], dict) else {}
            suggestions.append(
                EditingSuggestion(
                    suggestion_type="scene_order",
                    priority="low",
                    title="Validate opening-to-ending scene order",
                    recommendation="Test swapping scene 2 and 3 for a stronger reveal cadence.",
                    rationale="Current order may resolve tension too early.",
                    target_scene_id=str(first.get("scene_id", "")),
                )
            )
            suggestions.append(
                EditingSuggestion(
                    suggestion_type="emotional_timing",
                    priority="medium",
                    title="Protect emotional landing beat",
                    recommendation="Add a short hold before the final cut so the emotional landing has room to breathe.",
                    rationale="Ending beats benefit from slight breath before resolution.",
                    target_scene_id=str(last.get("scene_id", "")),
                )
            )

        repeated_holds = 0
        previous_transition = ""
        for row in transitions:
            if not isinstance(row, dict):
                continue
            current = str(row.get("transition", "")).strip().lower()
            if previous_transition == "hold" and current == "hold":
                repeated_holds += 1
            previous_transition = current
        if repeated_holds > 0:
            suggestions.append(
                EditingSuggestion(
                    suggestion_type="transition_improvements",
                    priority="medium",
                    title="Reduce repeated hold transitions",
                    recommendation="Replace at least one hold with a cut or fade to restore momentum.",
                    rationale="Back-to-back holds can flatten cinematic movement.",
                )
            )

        if isinstance(flow.get("issues"), list) and flow.get("issues"):
            suggestions.append(
                EditingSuggestion(
                    suggestion_type="pacing_trims",
                    priority="high",
                    title="Trim pacing drag in transition moments",
                    recommendation="Tighten the weakest transition section without cutting away the reaction beat that carries emotion forward.",
                    rationale=str(flow["issues"][0]),
                )
            )

        continuity_score = float(continuity.get("score", 1.0)) if isinstance(continuity.get("score"), (int, float)) else 1.0
        if continuity_score < 0.75:
            suggestions.append(
                EditingSuggestion(
                    suggestion_type="shot_duration",
                    priority="medium",
                    title="Rebalance shot duration variance",
                    recommendation="Shorten abrupt high-intensity shots and extend connective reaction shots.",
                    rationale="Large emotional jumps suggest timing mismatch between shots.",
                )
            )

        if not suggestions:
            suggestions.append(
                EditingSuggestion(
                    suggestion_type="pacing_trims",
                    priority="low",
                    title="Cut is stable",
                    recommendation="No critical edit is needed; optionally tighten one mid-sequence beat if the room feels the momentum soften.",
                    rationale="Signals indicate stable continuity and flow.",
                )
            )

        payload = [item.model_dump() for item in suggestions]
        return {
            "editing_intelligence": {
                "advisory_only": True,
                "suggestions": payload,
                "suggestion_count": len(payload),
            },
            "editing_suggestions": payload,
        }


editing_intelligence_service = EditingIntelligenceService()
