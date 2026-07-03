import json
import logging
from typing import Any, Dict

from fastapi import HTTPException

from app.llm_client import call_llm
from app.models.script_intelligence import SoundAdvisory
from app.services.project_store import project_store

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an audio director for an A24-style short film. "
    "Given scene context, return a JSON audio brief with keys: "
    "mood (string), score_notes (one sentence of musical direction), "
    "ambient_notes (diegetic sound details), "
    "silence_flag (boolean, true only if silence serves the scene dramatically), "
    "tempo (slow/medium/fast), instrumentation (2-3 instruments max). "
    "No scores, no percentages, co-director voice only."
)


def _load_scene(project_id: str, scene_id: str) -> Dict[str, Any] | None:
    project = project_store.get_project(project_id)
    if not project or not isinstance(project, dict):
        return None
    for scene in (project.get("execution_summary") or {}).get("scenes") or []:
        if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
            return scene
    return None


def _derive_act_position(scene: Dict[str, Any], scenes: list) -> str:
    idx = next(
        (
            i
            for i, s in enumerate(scenes)
            if isinstance(s, dict) and s.get("scene_id") == scene.get("scene_id")
        ),
        -1,
    )
    total = len(scenes) if isinstance(scenes, list) else 0
    if idx >= 0 and total > 0:
        return f"act_{min(idx // max(1, total // 3) + 1, 3)}"
    return "unknown"


def _build_context(scene: Dict[str, Any], scenes: list) -> str:
    content = (
        scene.get("scene_text")
        or scene.get("content")
        or scene.get("description")
        or scene.get("heading")
        or ""
    )
    emotional_target = scene.get("emotional_target") or scene.get("emotional_tone") or "neutral"
    characters = scene.get("character_appearances") or scene.get("characters") or []
    act_position = _derive_act_position(scene, scenes)
    return (
        f"Scene content:\n{content}\n\n"
        f"Emotional target: {emotional_target}\n"
        f"Characters: {', '.join(str(c) for c in characters) if characters else 'none specified'}\n"
        f"Act position: {act_position}"
    )


async def generate_scene_audio_brief(
    project_id: str,
    scene_id: str,
    db,
) -> SoundAdvisory:
    scene = _load_scene(project_id, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found")

    scenes = (project_store.get_project(project_id) or {}).get("execution_summary", {}).get("scenes") or []
    context = _build_context(scene, scenes)

    try:
        raw = await call_llm(
            system_prompt=SYSTEM_PROMPT,
            message=context,
            max_tokens=512,
        )
    except Exception as exc:
        logger.error(
            "AUDIO_DIRECTOR_LLM_FAILED | project=%s scene=%s | %s",
            project_id,
            scene_id,
            exc,
        )
        raise HTTPException(status_code=500, detail=f"Audio director LLM failed: {exc}") from exc

    try:
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "AUDIO_DIRECTOR_PARSE_FAILED | project=%s scene=%s | raw=%s | %s",
            project_id,
            scene_id,
            raw,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to parse audio brief from LLM response") from exc

    # Filter to only fields that SoundAdvisory accepts
    advisory_data = {
        "mood": str(parsed.get("mood") or ""),
        "score_notes": str(parsed.get("score_notes") or ""),
        "ambient_notes": str(parsed.get("ambient_notes") or ""),
        "silence_flag": bool(parsed.get("silence_flag") or False),
    }

    return SoundAdvisory(**advisory_data)
