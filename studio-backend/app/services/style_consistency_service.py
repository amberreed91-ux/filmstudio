from __future__ import annotations

from typing import Any, Dict, List

from app.models.film_visual_style_profile import FilmVisualStyleProfile


class StyleConsistencyService:
    """
    Additive-only style locking helper for prompt shaping and continuity scoring.
    """

    _STYLE_PRESETS: Dict[str, Dict[str, List[str]]] = {
        "noir": {
            "color_palette": ["black", "silver", "desaturated blue"],
            "lighting_language": ["high contrast", "low key", "hard shadows"],
            "lens_style": ["35mm spherical", "subtle halation"],
            "camera_movement_style": ["restrained dolly", "measured push-in"],
            "framing_patterns": ["negative space", "silhouette framing"],
            "texture_keywords": ["film grain", "rain haze", "smoke density"],
        },
        "a24_atmospheric": {
            "color_palette": ["earth tones", "faded amber", "muted teal"],
            "lighting_language": ["natural motivated light", "window falloff"],
            "lens_style": ["vintage anamorphic", "gentle bloom"],
            "camera_movement_style": ["patient handheld", "slow drift"],
            "framing_patterns": ["off-center portraiture", "lingering medium wide"],
            "texture_keywords": ["organic grain", "soft diffusion", "air particulate"],
        },
        "dreamlike": {
            "color_palette": ["lavender haze", "pearl cyan", "rose mist"],
            "lighting_language": ["ethereal glow", "diffused highlights"],
            "lens_style": ["soft focus", "prism flare"],
            "camera_movement_style": ["floating glide", "weightless crane"],
            "framing_patterns": ["symmetrical tableaux", "foreground veils"],
            "texture_keywords": ["mist", "bokeh bloom", "velvet blacks"],
        },
        "sci_fi": {
            "color_palette": ["neon cyan", "deep navy", "magenta accents"],
            "lighting_language": ["practical neon", "specular rim light"],
            "lens_style": ["clean anamorphic", "wide-angle precision"],
            "camera_movement_style": ["controlled tracking", "stabilized arcs"],
            "framing_patterns": ["architectural depth", "scale contrast"],
            "texture_keywords": ["holographic haze", "metallic sheen", "digital grain"],
        },
        "horror": {
            "color_palette": ["sickly green", "blood red accents", "cold blue"],
            "lighting_language": ["chiaroscuro", "flicker practicals", "deep shadow pockets"],
            "lens_style": ["wide unease", "distorted close focus"],
            "camera_movement_style": ["slow creeping push", "sudden whip restraint"],
            "framing_patterns": ["blocked exits", "occluded foreground"],
            "texture_keywords": ["grit", "damp surfaces", "uneven exposure"],
        },
        "realism": {
            "color_palette": ["neutral skin tones", "subtle warm-cool balance"],
            "lighting_language": ["motivated practicals", "natural contrast"],
            "lens_style": ["clean spherical", "documentary close focus"],
            "camera_movement_style": ["grounded handheld", "observational pans"],
            "framing_patterns": ["eye-level intimacy", "functional coverage"],
            "texture_keywords": ["fine grain", "true-to-life detail", "natural depth"],
        },
    }

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _string_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _normalize_style_name(self, style_name: Any) -> str:
        raw = self._string(style_name).lower()
        if not raw:
            return "realism"
        normalized = raw.replace("-", "_").replace(" ", "_")
        alias_map = {"a24": "a24_atmospheric", "a24atmospheric": "a24_atmospheric", "scifi": "sci_fi"}
        return alias_map.get(normalized, normalized)

    def build_film_visual_style_profile(self, style_name: Any) -> FilmVisualStyleProfile:
        normalized = self._normalize_style_name(style_name)
        preset = self._STYLE_PRESETS.get(normalized, self._STYLE_PRESETS["realism"])
        return FilmVisualStyleProfile(
            style_id=f"style_{normalized}",
            style_name=normalized,
            color_palette=list(preset.get("color_palette", [])),
            lighting_language=list(preset.get("lighting_language", [])),
            lens_style=list(preset.get("lens_style", [])),
            camera_movement_style=list(preset.get("camera_movement_style", [])),
            framing_patterns=list(preset.get("framing_patterns", [])),
            texture_keywords=list(preset.get("texture_keywords", [])),
        )

    def build_style_reference_context(self, style_profile: Any) -> Dict[str, Any]:
        profile: FilmVisualStyleProfile
        if isinstance(style_profile, FilmVisualStyleProfile):
            profile = style_profile
        elif isinstance(style_profile, dict):
            try:
                profile = FilmVisualStyleProfile(**style_profile)
            except Exception:
                profile = self.build_film_visual_style_profile("realism")
        else:
            profile = self.build_film_visual_style_profile("realism")

        reference_lines = [
            f"style: {profile.style_name}",
            f"palette: {', '.join(profile.color_palette[:3])}",
            f"lighting: {', '.join(profile.lighting_language[:2])}",
            f"lens: {', '.join(profile.lens_style[:2])}",
            f"movement: {', '.join(profile.camera_movement_style[:2])}",
            f"framing: {', '.join(profile.framing_patterns[:2])}",
            f"texture: {', '.join(profile.texture_keywords[:3])}",
        ]
        return {"style_profile": profile.model_dump(), "reference_lines": reference_lines}

    def inject_style_guidance(self, prompt: str, style_context: Dict[str, Any]) -> str:
        base = prompt.strip() if isinstance(prompt, str) else ""
        if not isinstance(style_context, dict):
            return base
        lines = style_context.get("reference_lines")
        if not isinstance(lines, list):
            return base
        clean = [str(line).strip() for line in lines if str(line).strip()]
        if not clean:
            return base
        addon = "Film visual style lock: " + " | ".join(clean)
        if not base:
            return addon
        return f"{base}. {addon}"

    def maintain_scene_style_consistency(self, style_context: Dict[str, Any]) -> List[str]:
        if not isinstance(style_context, dict):
            return []
        profile = style_context.get("style_profile")
        if not isinstance(profile, dict):
            return []
        return [
            "Maintain visual style continuity across scene transitions.",
            "Preserve wardrobe-adjacent color harmony with locked palette.",
            "Keep lighting language and lens treatment consistent with style profile.",
            "Keep camera movement and framing patterns aligned with established style.",
            "Preserve texture language and atmospheric detail continuity.",
        ]

    def score_visual_continuity(self, scenes: Any, style_context: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(style_context, dict):
            return {"score": 0.0, "status": "unavailable", "signals_present": 0, "signals_expected": 0}
        lines = style_context.get("reference_lines")
        if not isinstance(lines, list) or not lines:
            return {"score": 0.0, "status": "unavailable", "signals_present": 0, "signals_expected": 0}

        style_text = " ".join(str(line).lower() for line in lines)
        scenes_list = scenes if isinstance(scenes, list) else []
        scene_text = " ".join(
            str(scene.get("text", "")).lower()
            for scene in scenes_list
            if isinstance(scene, dict)
        )
        signals_expected = 6
        signal_words = [
            ("palette", ["color", "palette", "tone"]),
            ("lighting", ["light", "shadow", "lit"]),
            ("lens", ["lens", "focus", "anamorphic", "spherical"]),
            ("movement", ["dolly", "handheld", "tracking", "crane", "movement"]),
            ("framing", ["frame", "framing", "composition", "negative space"]),
            ("texture", ["grain", "mist", "haze", "texture"]),
        ]
        signals_present = 0
        for _, words in signal_words:
            if any(word in scene_text for word in words) or any(word in style_text for word in words):
                signals_present += 1

        score = round(signals_present / signals_expected, 3)
        status = "locked" if score >= 0.8 else ("mostly_locked" if score >= 0.5 else "drifting")
        return {
            "score": score,
            "status": status,
            "signals_present": signals_present,
            "signals_expected": signals_expected,
        }


style_consistency_service = StyleConsistencyService()
