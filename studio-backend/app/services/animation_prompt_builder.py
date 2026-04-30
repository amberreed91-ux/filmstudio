from __future__ import annotations

from typing import Any, Dict, List


class AnimationPromptBuilderService:
    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _string_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _join_or_fallback(self, values: List[str], fallback: str) -> str:
        cleaned = [value for value in values if value]
        return ", ".join(cleaned) if cleaned else fallback

    def build_payload(self, record: Dict[str, Any]) -> Dict[str, Any]:
        scene_id = self._string(record.get("scene_id"))
        film_title = self._string(record.get("film_title"))
        scene_name = self._string(record.get("scene_name"))
        intent = self._string(record.get("intent")) or "Carry the scene intention with readable cinematic motion."
        emotional_beat_arc = self._string_list(record.get("emotional_beat_arc"))
        camera_logic = self._string_list(record.get("camera_logic"))
        pacing_curve = self._string_list(record.get("pacing_curve"))
        director_notes = self._string(record.get("director_notes"))

        emotional_phrase = self._join_or_fallback(
            emotional_beat_arc,
            "steady emotional progression with clear visual escalation",
        )
        camera_phrase = self._join_or_fallback(
            camera_logic,
            "stable cinematic framing with motivated camera movement",
        )
        pacing_phrase = self._join_or_fallback(
            pacing_curve,
            "measured pacing with clean beat transitions",
        )
        notes_phrase = director_notes or "Preserve continuity, readable staging, and controlled screen direction."

        motion_prompt = (
            f"{intent} Translate the scene through {emotional_phrase}. "
            f"Use deliberate subject movement, environmental motion, and clear action continuity. "
            f"Director emphasis: {notes_phrase}"
        )
        camera_prompt = (
            f"Camera logic: {camera_phrase}. "
            "Maintain intentional framing, coherent screen direction, smooth lens behavior, and stable shot progression."
        )
        pacing_prompt = (
            f"Pacing curve: {pacing_phrase}. "
            "Shape motion rhythm with readable acceleration and deceleration, preserving emotional clarity from beat to beat."
        )
        negative_prompt = (
            "Avoid flicker, warped faces, unstable anatomy, random camera jumps, excessive motion, "
            "text artifacts, continuity errors, temporal jitter, duplicate limbs, and inconsistent lighting."
        )
        comfy_notes = (
            f"Default ComfyUI payload for {scene_name or scene_id or 'scene'} in {film_title or 'untitled film'}. "
            "Use as a deterministic starter prompt pack for animation workflow wiring."
        )

        return {
            "scene_id": scene_id,
            "film_title": film_title,
            "scene_name": scene_name,
            "animation_type": "image_to_video",
            "intent": intent,
            "motion_prompt": motion_prompt,
            "camera_prompt": camera_prompt,
            "pacing_prompt": pacing_prompt,
            "negative_prompt": negative_prompt,
            "duration_seconds": 5,
            "fps": 24,
            "comfy_notes": comfy_notes,
        }


animation_prompt_builder_service = AnimationPromptBuilderService()
