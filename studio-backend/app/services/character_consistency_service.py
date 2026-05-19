from __future__ import annotations

from typing import Any, Dict, List

from app.models.character_profile import CharacterProfile


class CharacterConsistencyService:
    """
    Additive-only helper for character continuity context and prompt shaping.
    """

    def _string_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def build_character_profiles_from_scenes(self, scenes: Any) -> List[CharacterProfile]:
        if not isinstance(scenes, list):
            return []

        seen: Dict[str, CharacterProfile] = {}
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            scene_characters = scene.get("character_appearances")
            if not isinstance(scene_characters, list):
                scene_characters = scene.get("characters")
            if not isinstance(scene_characters, list):
                continue
            for char_name in scene_characters:
                name = self._string(char_name)
                if not name:
                    continue
                character_id = name.lower().replace(" ", "_")
                if character_id in seen:
                    continue
                seen[character_id] = CharacterProfile(
                    character_id=character_id,
                    name=name,
                    appearance_traits=[],
                    wardrobe=[],
                    visual_references=[],
                    voice_tone="",
                    emotional_baseline="",
                    facial_identity="",
                    silhouette="",
                    movement_style="",
                    emotional_behavior="",
                    speech_rhythm="",
                )
        return list(seen.values())

    def build_character_reference_context(self, character_profiles: Any, scene_data: Any) -> Dict[str, Any]:
        profiles: List[CharacterProfile] = []
        if isinstance(character_profiles, list):
            for entry in character_profiles:
                if isinstance(entry, CharacterProfile):
                    profiles.append(entry)
                elif isinstance(entry, dict):
                    try:
                        profiles.append(CharacterProfile(**entry))
                    except Exception:
                        continue

        scene_characters: List[str] = []
        if isinstance(scene_data, dict):
            scene_characters = self._string_list(scene_data.get("character_appearances") or scene_data.get("characters"))

        if not scene_characters:
            return {"characters": [], "reference_lines": []}

        normalized_scene_names = {name.lower() for name in scene_characters}
        matched = [
            profile for profile in profiles
            if profile.name.lower() in normalized_scene_names or profile.character_id.lower() in normalized_scene_names
        ]

        lines: List[str] = []
        for profile in matched:
            parts: List[str] = [profile.name]
            if profile.appearance_traits:
                parts.append(f"appearance: {', '.join(profile.appearance_traits[:3])}")
            if profile.wardrobe:
                parts.append(f"wardrobe: {', '.join(profile.wardrobe[:2])}")
            if profile.emotional_baseline:
                parts.append(f"emotional baseline: {profile.emotional_baseline}")
            lines.append(" | ".join(parts))

        return {
            "characters": [profile.model_dump() for profile in matched],
            "reference_lines": lines,
        }

    def inject_character_visual_traits(self, prompt: str, character_context: Dict[str, Any]) -> str:
        base = prompt.strip() if isinstance(prompt, str) else ""
        if not isinstance(character_context, dict):
            return base
        references = character_context.get("reference_lines")
        if not isinstance(references, list) or not references:
            return base
        addon = "Character continuity: " + " || ".join(str(line).strip() for line in references if str(line).strip())
        if not addon.strip():
            return base
        if not base:
            return addon
        return f"{base}. {addon}"

    def maintain_scene_consistency(self, scene_data: Any, character_context: Dict[str, Any]) -> List[str]:
        if not isinstance(character_context, dict):
            return []
        characters = character_context.get("characters")
        if not isinstance(characters, list) or not characters:
            return []

        notes = [
            "Maintain consistent character appearance across shots.",
            "Maintain wardrobe continuity for recurring characters.",
            "Maintain emotional continuity for recurring characters.",
        ]
        if isinstance(scene_data, dict):
            tone = self._string(scene_data.get("emotional_target") or scene_data.get("tone"))
            if tone:
                notes.append(f"Keep character emotional baseline aligned with scene tone: {tone}.")
        return notes


character_consistency_service = CharacterConsistencyService()
