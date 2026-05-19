from __future__ import annotations

from typing import Any, Dict, List

from app.models.character_profile import CharacterProfile


class CharacterIdentityMemoryService:
    def _as_profiles(self, profiles: Any) -> List[CharacterProfile]:
        out: List[CharacterProfile] = []
        if not isinstance(profiles, list):
            return out
        for row in profiles:
            if isinstance(row, CharacterProfile):
                out.append(row)
            elif isinstance(row, dict):
                try:
                    out.append(CharacterProfile(**row))
                except Exception:
                    continue
        return out

    def persist_reference_images(self, character_profiles: Any) -> Dict[str, List[str]]:
        refs: Dict[str, List[str]] = {}
        for profile in self._as_profiles(character_profiles):
            if profile.visual_references:
                refs[profile.character_id] = list(profile.visual_references)
        return refs

    def build_provider_identity_context(self, character_profiles: Any, scene_data: Any) -> Dict[str, Any]:
        profiles = self._as_profiles(character_profiles)
        scene = scene_data if isinstance(scene_data, dict) else {}
        scene_names = {
            str(name).strip().lower()
            for name in (scene.get("character_appearances") or scene.get("characters") or [])
            if str(name).strip()
        } if isinstance(scene.get("character_appearances") or scene.get("characters"), list) else set()
        lines: List[str] = []
        for profile in profiles:
            if scene_names and profile.name.lower() not in scene_names and profile.character_id.lower() not in scene_names:
                continue
            parts = [profile.name]
            if profile.facial_identity:
                parts.append(f"facial identity: {profile.facial_identity}")
            if profile.silhouette:
                parts.append(f"silhouette: {profile.silhouette}")
            if profile.movement_style:
                parts.append(f"movement: {profile.movement_style}")
            if profile.wardrobe:
                parts.append(f"wardrobe: {', '.join(profile.wardrobe[:2])}")
            lines.append(" | ".join(parts))
        return {
            "advisory_only": True,
            "identity_lines": lines,
            "reference_images": self.persist_reference_images(profiles),
        }

    def build_emotional_memory_continuity(self, character_profiles: Any, scene_data: Any) -> List[str]:
        profiles = self._as_profiles(character_profiles)
        scene = scene_data if isinstance(scene_data, dict) else {}
        scene_emotion = str(scene.get("emotional_target") or "").strip().lower()
        notes: List[str] = []
        for profile in profiles:
            baseline = profile.emotional_baseline.strip().lower()
            behavior = profile.emotional_behavior.strip().lower()
            if baseline:
                notes.append(f"{profile.name}: emotional baseline {baseline}.")
            if behavior:
                notes.append(f"{profile.name}: behavior pattern {behavior}.")
            if scene_emotion and baseline and scene_emotion != baseline:
                notes.append(f"{profile.name}: carry continuity from {baseline} into {scene_emotion}.")
        return notes

    def detect_identity_drift_warnings(self, character_profiles: Any, scene_data: Any) -> List[str]:
        profiles = self._as_profiles(character_profiles)
        scene = scene_data if isinstance(scene_data, dict) else {}
        drift: List[str] = []
        scene_tone = str(scene.get("emotional_target") or "").strip().lower()
        for profile in profiles:
            if not profile.name:
                continue
            if not profile.facial_identity:
                drift.append(f"{profile.name}: facial identity not set; drift risk across shots.")
            if not profile.silhouette:
                drift.append(f"{profile.name}: silhouette not set; framing drift risk.")
            if not profile.movement_style:
                drift.append(f"{profile.name}: movement style not set; motion drift risk.")
            if scene_tone and profile.emotional_baseline and scene_tone != profile.emotional_baseline.strip().lower():
                drift.append(
                    f"{profile.name}: emotional drift warning ({profile.emotional_baseline} -> {scene_tone})."
                )
        return drift


character_identity_memory_service = CharacterIdentityMemoryService()

