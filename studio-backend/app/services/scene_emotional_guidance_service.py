"""Scene Emotional Guidance Service.

Produces advisory, scene-level emotional guidance from signals that are
already loaded elsewhere in the studio — no provider calls, no LLM.

Complements ``ShotRationaleService`` (which answers "why this shot matters")
by naming the emotional work a scene is doing and, only when a concrete
signal is present, one actionable risk.

Co-director voice rules (AGENTS.md):
  - no scores, ratings, or percentages
  - no empty praise
  - at most one risk note at a time
  - silence when the available signals are too thin to say anything concrete
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.director_memory_service import director_memory_service
from app.services.shot_rationale_service import shot_rationale_service
from app.services.stability import elapsed_ms, log_stage_event, start_timer

logger = logging.getLogger("scene-emotional-guidance")

_FLAT_FLOW_PATTERNS = {"flat", "broken"}
_FLOW_SCORE_FLOOR = 0.64


class SceneEmotionalGuidanceService:
    """Builds advisory emotional guidance for a single scene."""

    def __init__(self, rationale_service=None, memory_service=None) -> None:
        self._rationale_service = rationale_service or shot_rationale_service
        self._memory_service = memory_service or director_memory_service

    def build_guidance(
        self,
        *,
        project_id: str,
        scene_id: str,
        scene_data: dict[str, Any] | None = None,
        continuity_context: dict[str, Any] | None = None,
        scene_intent: dict[str, Any] | None = None,
        scene_position: int | None = None,
        total_scenes: int | None = None,
        memory_callbacks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        timer = start_timer()
        scene_data = scene_data if isinstance(scene_data, dict) else {}
        continuity_context = continuity_context if isinstance(continuity_context, dict) else {}

        rationale = ""
        try:
            rationale = str(
                self._rationale_service.get_rationale(
                    project_id=project_id,
                    scene_id=scene_id,
                    scene_data=scene_data,
                    continuity_context=continuity_context,
                    scene_intent=scene_intent,
                    scene_position=scene_position,
                    total_scenes=total_scenes,
                ).get("rationale")
                or ""
            ).strip()
        except Exception as exc:  # noqa: BLE001 — advisory only, never block the caller
            logger.warning("rationale composition failed for %s: %s", scene_id, exc)

        callbacks = self._collect_callbacks(project_id, scene_data, scene_position, memory_callbacks)

        emotional_work = self._build_emotional_work(scene_data, continuity_context)
        risk, guidance = self._build_risk_and_guidance(scene_data, callbacks)

        result = {
            "scene_id": scene_id,
            "project_id": project_id,
            "rationale": rationale,
            "emotional_work": emotional_work,
            "guidance": guidance,
            "risk": risk,
            "callbacks": callbacks,
            "advisory_only": True,
            "auto_regeneration_triggered": False,
        }

        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=None,
            stage="scene_emotional_guidance",
            duration_ms=elapsed_ms(timer),
            extra={"scene_id": scene_id, "has_guidance": bool(guidance)},
        )
        return result

    # ------------------------------------------------------------------ #
    # Internal builders
    # ------------------------------------------------------------------ #

    def _collect_callbacks(
        self,
        project_id: str,
        scene_data: dict[str, Any],
        scene_position: int | None,
        provided: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if provided is not None:
            return [c for c in provided if isinstance(c, dict)]
        if not project_id:
            return []
        try:
            scan = self._memory_service.scan_scene(
                project_id,
                scene_data,
                scene_index=(scene_position - 1) if isinstance(scene_position, int) else None,
            )
        except Exception as exc:  # noqa: BLE001 — memory is advisory; degrade to silence
            logger.warning("memory scan failed for %s: %s", scene_data.get("scene_id"), exc)
            return []
        callbacks = scan.get("callbacks") if isinstance(scan, dict) else []
        return [c for c in callbacks if isinstance(c, dict)] if isinstance(callbacks, list) else []

    def _build_emotional_work(
        self,
        scene_data: dict[str, Any],
        continuity_context: dict[str, Any],
    ) -> str:
        tone = str(scene_data.get("emotional_tone") or "").strip().lower()
        register = str(continuity_context.get("emotional_register") or "").strip().lower()
        direction = str(continuity_context.get("tonal_direction") or "").strip().lower()

        descriptor = register or tone
        if not descriptor and not direction:
            return ""

        sentence = f"The scene holds the film in a {descriptor or 'measured'} register"
        if direction:
            sentence += f" as the arc moves {direction}"
        sentence += "."
        return sentence

    def _build_risk_and_guidance(
        self,
        scene_data: dict[str, Any],
        callbacks: list[dict[str, Any]],
    ) -> tuple[str, str]:
        flow = scene_data.get("scene_emotional_flow")
        flow = flow if isinstance(flow, dict) else {}
        flow_pattern = str(flow.get("pattern") or scene_data.get("flow_pattern") or "").strip().lower()
        flow_score = flow.get("flow_score")
        flow_score = float(flow_score) if isinstance(flow_score, (int, float)) else None

        if flow_pattern in _FLAT_FLOW_PATTERNS or (flow_score is not None and flow_score < _FLOW_SCORE_FLOOR):
            return (
                "The emotional turn here isn't landing cleanly — the beat flattens before it releases.",
                "Hold the central tension one beat longer so the release carries weight.",
            )

        report = scene_data.get("scene_continuity_report")
        report = report if isinstance(report, dict) else {}
        issues = report.get("issues") if isinstance(report.get("issues"), list) else []
        issues = [str(i).strip() for i in issues if str(i).strip()]
        if issues:
            return (
                f"Continuity meaning breaks here: {issues[0]}",
                "Re-anchor this beat to what the audience already knows before moving on.",
            )

        for callback in callbacks:
            if callback.get("kind") == "characters":
                message = str(callback.get("message") or "").strip()
                if message:
                    return (
                        message,
                        "Make the shift deliberate on screen — give it a visual or blocking cue.",
                    )

        return "", ""


scene_emotional_guidance_service = SceneEmotionalGuidanceService()
