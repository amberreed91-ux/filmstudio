from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ShotRationaleService:
    """Builds a one-sentence 'Why this shot matters' rationale from existing signals.

    Uses scene data, continuity context, scene intelligence, and render job
    status — no new API calls or LLM invocations needed.
    """

    def __init__(self, storage=None):
        self._storage = storage

    def get_rationale(
        self,
        project_id: str,
        scene_id: str,
        scene_data: Dict[str, Any],
        continuity_context: Optional[Dict[str, Any]] = None,
        scene_intent: Optional[Dict[str, Any]] = None,
        scene_position: Optional[int] = None,
        total_scenes: Optional[int] = None,
    ) -> Dict[str, Any]:
        sentence = self._build_sentence(
            scene_data=scene_data,
            continuity_context=continuity_context,
            scene_intent=scene_intent,
            scene_position=scene_position,
            total_scenes=total_scenes,
        )
        return {
            "rationale": sentence,
            "scene_context": {
                "scene_id": scene_id,
                "characters": scene_data.get("characters", []),
                "location": scene_data.get("location", ""),
                "emotional_tone": scene_data.get("emotional_tone", ""),
                "scene_heading": scene_data.get("heading", ""),
            },
            "emotional_context": {
                "emotional_register": (continuity_context or {}).get("emotional_register", ""),
                "tonal_direction": (continuity_context or {}).get("tonal_direction", ""),
                "active_motifs": (continuity_context or {}).get("active_motifs", []),
            },
        }

    def _build_sentence(
        self,
        scene_data: Dict[str, Any],
        continuity_context: Optional[Dict[str, Any]] = None,
        scene_intent: Optional[Dict[str, Any]] = None,
        scene_position: Optional[int] = None,
        total_scenes: Optional[int] = None,
    ) -> str:
        scene_id = str(scene_data.get("scene_id") or "").strip()
        emotional_tone = str(scene_data.get("emotional_tone") or "").strip().lower()
        location = str(scene_data.get("location") or "").strip()
        characters = scene_data.get("characters", [])
        if isinstance(characters, str):
            characters = [c.strip() for c in characters.split(",") if c.strip()]
        heading = str(scene_data.get("heading") or "").strip()
        description = str(scene_data.get("description") or scene_data.get("text") or "").strip()
        scene_name = str(scene_data.get("scene_name") or "").strip()

        emotional_register = ""
        active_motifs: List[str] = []
        tonal_direction = ""
        if continuity_context:
            emotional_register = str(continuity_context.get("emotional_register") or "").strip()
            active_motifs = continuity_context.get("active_motifs", []) or []
            tonal_direction = str(continuity_context.get("tonal_direction") or "").strip()

        intent = ""
        if scene_intent:
            intent = str(scene_intent.get("intent") or "").strip()

        scene_label = scene_name or heading or f"Scene {scene_id}"

        if intent and characters:
            return (
                f"{intent} "
                f"A {emotional_tone or 'charged'} scene with {self._format_characters(characters)} at {location or 'this space'}, "
                f"grounded in {emotional_register or emotional_tone or 'its emotional core'}."
            )

        if characters and location and emotional_tone:
            verb = "take" if len(characters) != 1 else "takes"
            base = f"A {emotional_tone} scene at {location} where {self._format_characters(characters)} {verb} the frame"
            if emotional_register:
                base += f", carrying the {emotional_register} of the journey so far"
            if active_motifs:
                base += f" and weaving in the {active_motifs[0]} motif"
            base += "."
            return base

        if emotional_register or tonal_direction:
            base = f"This {scene_label} reads in {emotional_register or emotional_tone or 'a measured'} register"
            if tonal_direction:
                base += f", with the arc {tonal_direction}"
            if active_motifs:
                base += f" as the {active_motifs[0]} motif lingers"
            base += "."
            return base

        return f"{scene_label}. A beat that earns its place in the larger composition."

    def _format_characters(self, characters: List[str]) -> str:
        if not characters:
            return "the characters"
        if len(characters) == 1:
            return characters[0]
        if len(characters) == 2:
            return f"{characters[0]} and {characters[1]}"
        return f"{', '.join(characters[:-1])}, and {characters[-1]}"


shot_rationale_service = ShotRationaleService()
