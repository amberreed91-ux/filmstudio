from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Awaitable, Callable, Optional

from app.services.project_store import project_store
from app.services.study_context import build_study_context_block, fetch_active_memories
from app.services.stability import ValidationError, ProviderError


logger = logging.getLogger("previs-generation-settings-service")

# Callable returning (completion_text, provider_used) — matches the
# get_llm_completion_with_fallback helper shape so this service is testable
# with an AsyncMock returning a tuple.
FallbackLLM = Callable[..., Awaitable[tuple[str, str]]]


VALID_RESOLUTIONS = ("480p", "720p", "1080p")
VALID_MODELS = ("Wan 2.2", "LTX-Video", "Auto (Best Available)")


@dataclass(frozen=True)
class GenerationSettingsRecommendation:
    duration_seconds: int
    fps: int
    resolution: str
    model: Optional[str]


@dataclass(frozen=True)
class ProviderDurationConstraint:
    provider: str
    supports_custom_duration: bool
    valid_durations_seconds: tuple[int, ...]
    nearest_valid_duration_seconds: int
    advisory: str


@dataclass(frozen=True)
class GenerationSettingsResult:
    scene_id: str
    shot_number: int
    recommended: GenerationSettingsRecommendation
    duration_constraint: ProviderDurationConstraint
    reasoning: str
    study_memories_used: int


def _find_scene(project_id: str, scene_id: str) -> dict | None:
    project = project_store.get_project(project_id)
    if not project:
        return None
    summary = project.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    for s in scenes:
        if isinstance(s, dict) and s.get("scene_id") == scene_id:
            return s
    scenes_list = project.get("scenes") or []
    for s in scenes_list:
        if isinstance(s, dict) and s.get("scene_id") == scene_id:
            return s
    return None


def _scene_order_index(project_id: str, scene_id: str) -> int | None:
    project = project_store.get_project(project_id)
    if not project:
        return None
    summary = project.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    for idx, s in enumerate(scenes):
        if isinstance(s, dict) and s.get("scene_id") == scene_id:
            return idx
    return None


def _dialogue_density(scene_text: str) -> str:
    """Coarse dialogue-density read: count ALL-CAPS character cue lines."""
    if not scene_text:
        return "none"
    lines = [ln.strip() for ln in scene_text.splitlines() if ln.strip()]
    cue_lines = sum(
        1 for ln in lines if re.match(r"^[A-Z][A-Z\s.\-']{2,40}$", ln) and not ln.startswith("(")
    )
    if cue_lines == 0:
        return "none"
    if cue_lines <= 3:
        return "light"
    if cue_lines <= 8:
        return "moderate"
    return "dense"


async def _pacing_label_for_scene(project_id: str, scene_id: str) -> Optional[str]:
    """Reuse PacingInsight from script_intelligence if computable for this scene.

    PacingInsight is per-act, so derive the scene's act from its order index
    and return that act's pacing label. Returns None when there is insufficient
    data (e.g. <2 scenes) so the route proceeds without pacing.
    """
    try:
        from app.services.script_intelligence_service import script_intelligence_service

        analysis = await script_intelligence_service.analyze_scene_breakdown(project_id)
    except Exception as exc:
        logger.debug("Pacing insight unavailable for %s: %s", scene_id, exc)
        return None

    order_index = _scene_order_index(project_id, scene_id)
    if order_index is None:
        return None
    total = analysis.total_scenes or 0
    if total < 2:
        return None
    act1_end = max(1, total // 4)
    act2_end = total - max(1, total // 4)
    if order_index < act1_end:
        act_num = 1
    elif order_index < act2_end:
        act_num = 2
    else:
        act_num = 3
    for insight in analysis.pacing_insights:
        if insight.act_number == act_num:
            return insight.pacing_label
    return None


class PrevisGenerationSettingsService:
    """Recommend per-shot generation settings (duration/fps/resolution/model).

    Reasons over shot type, scene pacing (reusing PacingInsight when already
    computable), dialogue density, and whether the shot is an establishing
    shot. Routes the LLM call through the provider-fallback helper so a
    blocked/slow Qwen call falls back to OpenRouter instead of hanging.
    """

    async def build_prompt(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_number: int,
        shot_type: str,
    ) -> tuple[str, str, int]:
        scene = _find_scene(project_id, scene_id)
        if scene is None:
            raise ValidationError(
                f"Scene {scene_id} not found",
                stage="previs_generation_settings",
                metadata={"project_id": project_id, "scene_id": scene_id},
            )

        scene_text = scene.get("text") or scene.get("description") or ""
        establishing = shot_number == 1 or (shot_type or "").lower() == "wide"
        dialogue_density = _dialogue_density(scene_text)
        pacing_label = await _pacing_label_for_scene(project_id, scene_id)

        context_block = build_study_context_block(project_id, scene_id)
        memories = fetch_active_memories(project_id)
        mem_count = memories.get("raw_count", 0)

        signals = [
            f"Shot type: {shot_type or 'unspecified'}",
            f"Shot number: {shot_number}",
            f"Establishing shot: {'yes' if establishing else 'no'}",
            f"Dialogue density: {dialogue_density}",
        ]
        if pacing_label:
            signals.append(f"Scene pacing: {pacing_label}")

        system_prompt = (
            "You are a previs supervisor recommending generation settings for a "
            "single shot. Speak in co-director voice — specific and actionable, "
            "no scores or percentages, no generic praise.\n\n"
            f"{context_block or 'No additional project context is available.'}\n\n"
            "Output contract:\n"
            "- Output ONLY a JSON object with keys:\n"
            "  duration_seconds (integer 4-20), fps (integer 8/12/16/24),\n"
            "  resolution (one of 480p/720p/1080p), model (one of "
            "'Wan 2.2'/'LTX-Video'/'Auto (Best Available)' or null),\n"
            "  reasoning (one sentence, co-director voice, no scores/percentages)\n"
            "- Wide/establishing shots favor longer durations and 720p+.\n"
            "- Close/intimate shots favor shorter durations and lower fps for texture.\n"
            "- Dialogue-dense shots favor 24fps; atmospheric shots may use lower fps.\n"
            "- Output ONLY valid JSON, no other text."
        )
        user_message = (
            "Recommend generation settings for this shot.\n\n"
            + "\n".join(signals)
            + "\n\nScene content:\n"
            + (scene_text[:1200] if scene_text else "(no scene text available)")
        )
        return system_prompt, user_message, mem_count

    async def recommend(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_number: int,
        shot_type: str,
        llm_with_fallback: FallbackLLM,
    ) -> GenerationSettingsResult:
        system_prompt, user_message, mem_count = await self.build_prompt(
            project_id=project_id,
            scene_id=scene_id,
            shot_number=shot_number,
            shot_type=shot_type,
        )
        started = perf_counter()
        try:
            reply, provider = await llm_with_fallback(
                system_prompt, user_message, max_tokens=512
            )
            recommendation, reasoning = self._parse(reply)
            duration_constraint = self.provider_duration_constraint(
                recommendation.model,
                recommendation.duration_seconds,
            )
            logger.info(
                "project_id=%s job_id=- provider=%s stage=previs_generation_settings "
                "duration_ms=%d memories_supplied=%d",
                project_id,
                provider,
                int((perf_counter() - started) * 1000),
                mem_count,
            )
            return GenerationSettingsResult(
                scene_id=scene_id,
                shot_number=shot_number,
                recommended=recommendation,
                duration_constraint=duration_constraint,
                reasoning=reasoning,
                study_memories_used=mem_count,
            )
        except (ValidationError, ProviderError):
            raise
        except Exception as exc:
            raise ProviderError(
                "Generation settings recommendation failed",
                stage="previs_generation_settings",
                metadata={
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "cause": type(exc).__name__,
                },
            ) from exc

    @staticmethod
    def _parse(reply: str) -> tuple[GenerationSettingsRecommendation, str]:
        text = (reply or "").strip()
        # Tolerate a fenced ```json block.
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        payload = fence.group(1) if fence else text
        try:
            data = json.loads(payload)
        except Exception:
            data = {}
        duration = int(data.get("duration_seconds", 8))
        fps = int(data.get("fps", 16))
        resolution = str(data.get("resolution") or "720p").strip().lower()
        model = data.get("model")
        reasoning = str(data.get("reasoning") or "").strip()

        duration = max(4, min(20, duration))
        if fps not in (8, 12, 16, 24):
            fps = 16
        if resolution not in VALID_RESOLUTIONS:
            resolution = "720p"
        if isinstance(model, str) and model.strip():
            model = model.strip()
            if model not in VALID_MODELS:
                model = None
        else:
            model = None
        if not reasoning:
            reasoning = (
                "Settings reflect the shot's framing and the scene's rhythm — "
                "adjust if the beat asks for more or less room."
            )
        return (
            GenerationSettingsRecommendation(
                duration_seconds=duration,
                fps=fps,
                resolution=resolution,
                model=model,
            ),
            reasoning,
        )

    @staticmethod
    def provider_duration_constraint(
        model: Optional[str],
        requested_seconds: int,
    ) -> ProviderDurationConstraint:
        provider = model or "Auto (Best Available)"
        valid = (4, 8, 12, 16, 20)
        nearest = min(valid, key=lambda value: abs(value - requested_seconds))
        return ProviderDurationConstraint(
            provider=provider,
            supports_custom_duration=True,
            valid_durations_seconds=valid,
            nearest_valid_duration_seconds=nearest,
            advisory=(
                "This provider accepts the available duration steps. Treat the "
                "suggestion as a starting rhythm and adjust it before rendering."
            ),
        )


previs_generation_settings_service = PrevisGenerationSettingsService()
