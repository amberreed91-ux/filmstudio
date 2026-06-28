from __future__ import annotations

import json
import logging
from typing import Any

from app.llm_client import call_llm
from app.services.project_store import project_store
from app.services.study_context import fetch_active_memories, fetch_scene_content

logger = logging.getLogger("emotion-analysis")


class EmotionAnalysisService:

    async def analyze_scene(
        self,
        project_id: str,
        scene_id: str,
        scene_index: int,
        total_scenes: int,
    ) -> dict[str, Any]:
        project = project_store.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") or []
        scene = next((s for s in scenes if str(s.get("scene_id")) == scene_id), None)
        if not scene:
            raise ValueError(f"Scene {scene_id} not found in project {project_id}")

        scene_heading = scene.get("heading") or scene.get("scene_name") or ""
        full_text = fetch_scene_content(project_id, scene_id)

        memories = fetch_active_memories(project_id)
        tone_rules = memories.get("tone", [])
        tone_context = "; ".join(tone_rules) if tone_rules else "No specific tone rules established"

        system_prompt = "You are a film analytics AI. Return ONLY valid JSON, no other text."

        user_prompt = (
            f"Analyze this scene from THE LAST TIDE and rate the likely emotional "
            f"response for each audience type on a 0-100 scale.\n\n"
            f"Scene: {scene_heading}\n"
            f"Content: {full_text}\n"
            f"Position: Scene {scene_index} of {total_scenes}\n"
            f"Tone context: {tone_context}\n\n"
            f"Return exactly this JSON:\n"
            f"{{\n"
            f"  'general': {{'engagement': N, 'tension': N, 'emotional_impact': N}},\n"
            f"  'cinephile': {{'engagement': N, 'tension': N, 'emotional_impact': N}},\n"
            f"  'genre_fan': {{'engagement': N, 'tension': N, 'emotional_impact': N}}\n"
            f"}}"
        )

        raw = await call_llm(system_prompt, user_prompt, max_tokens=512)

        return self._parse(raw, scene_id)

    def _parse(self, raw: str, scene_id: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip().replace("'", '"')

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Groq response: %s", raw[:300])
            return self._fallback(scene_id)

        def _clamp(val: Any, default: int = 50) -> int:
            try:
                return max(0, min(100, int(val)))
            except (ValueError, TypeError):
                return default

        def _safe_group(key: str) -> dict[str, int]:
            group = data.get(key, {})
            return {
                "engagement": _clamp(group.get("engagement")),
                "tension": _clamp(group.get("tension")),
                "emotional_impact": _clamp(group.get("emotional_impact")),
            }

        return {
            "scene_id": scene_id,
            "general": _safe_group("general"),
            "cinephile": _safe_group("cinephile"),
            "genre_fan": _safe_group("genre_fan"),
        }

    def _fallback(self, scene_id: str) -> dict[str, Any]:
        return {
            "scene_id": scene_id,
            "general": {"engagement": 50, "tension": 40, "emotional_impact": 45},
            "cinephile": {"engagement": 55, "tension": 45, "emotional_impact": 50},
            "genre_fan": {"engagement": 60, "tension": 50, "emotional_impact": 55},
        }


emotion_analysis_service = EmotionAnalysisService()
