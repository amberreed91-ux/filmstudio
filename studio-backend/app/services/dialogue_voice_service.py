from __future__ import annotations

from typing import Any, Dict, List

from app.models.dialogue_line import DialogueLine


class DialogueVoiceService:
    """
    Additive dialogue + voice planning layer for cinematic scene pipelines.
    """

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _string_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _derive_pacing_tag(self, scene: Dict[str, Any]) -> str:
        pacing = self._string(scene.get("pacing") or scene.get("pacing_continuity")).lower()
        if pacing in {"slow", "fast", "balanced"}:
            return pacing
        return "balanced"

    def _derive_emotional_subtext(self, scene: Dict[str, Any]) -> str:
        emotion = self._string(scene.get("emotional_target") or scene.get("dominant_emotion") or scene.get("emotion"))
        unresolved = self._string(scene.get("unresolved_tension") or scene.get("tension"))
        if emotion and unresolved:
            return f"{emotion} undercurrent with unresolved tension: {unresolved}"
        if emotion:
            return f"{emotion} undercurrent"
        return "restrained subtext"

    def build_dialogue_lines(
        self,
        scenes: Any,
        character_profiles: Any = None,
    ) -> List[DialogueLine]:
        scene_list = scenes if isinstance(scenes, list) else []
        voice_lookup: Dict[str, str] = {}
        rhythm_lookup: Dict[str, str] = {}
        behavior_lookup: Dict[str, str] = {}
        if isinstance(character_profiles, list):
            for profile in character_profiles:
                if not isinstance(profile, dict):
                    continue
                cid = self._string(profile.get("character_id"))
                voice = self._string(profile.get("voice_tone")) or self._string(profile.get("name"))
                rhythm = self._string(profile.get("speech_rhythm"))
                behavior = self._string(profile.get("emotional_behavior"))
                if cid:
                    voice_lookup[cid] = voice
                    if rhythm:
                        rhythm_lookup[cid] = rhythm
                    if behavior:
                        behavior_lookup[cid] = behavior

        lines: List[DialogueLine] = []
        for scene in scene_list:
            if not isinstance(scene, dict):
                continue
            scene_id = self._string(scene.get("scene_id"))
            if not scene_id:
                continue
            characters = self._string_list(scene.get("character_appearances") or scene.get("characters"))
            if not characters:
                characters = ["Narrator"]
            pacing_tag = self._derive_pacing_tag(scene)
            subtext = self._derive_emotional_subtext(scene)
            for idx, char_name in enumerate(characters[:2]):
                character_id = char_name.lower().replace(" ", "_")
                hint = voice_lookup.get(character_id) or f"{char_name} cinematic voice"
                rhythm = rhythm_lookup.get(character_id, "")
                behavior = behavior_lookup.get(character_id, "")
                line_text = f"{char_name} carries the beat with {subtext}."
                if behavior:
                    line_text = f"{line_text} Behavior memory: {behavior}."
                lines.append(
                    DialogueLine(
                        line_id=f"{scene_id}_dlg_{idx + 1:02d}",
                        scene_id=scene_id,
                        character_id=character_id,
                        character_name=char_name,
                        text=line_text,
                        emotional_subtext=subtext,
                        pacing_tag=(rhythm.lower() if rhythm else pacing_tag),
                        voice_style_hint=hint,
                    )
                )
        return lines

    def build_voice_provider_plan(self, provider: str = "local_tts") -> Dict[str, Any]:
        normalized = self._string(provider).lower() or "local_tts"
        if normalized in {"elevenlabs", "eleven_labs"}:
            return {
                "provider": "elevenlabs",
                "status": "ready",
                "capability": "ElevenLabs-ready",
                "requires_network": True,
            }
        return {
            "provider": "local_tts",
            "status": "ready",
            "capability": "local TTS-ready",
            "requires_network": False,
        }

    def build_dialogue_timing_metadata(self, dialogue_lines: Any) -> List[Dict[str, Any]]:
        lines = dialogue_lines if isinstance(dialogue_lines, list) else []
        timeline: List[Dict[str, Any]] = []
        cursor = 0.0
        for row in lines:
            if isinstance(row, DialogueLine):
                payload = row.model_dump()
            elif isinstance(row, dict):
                payload = row
            else:
                continue
            text = self._string(payload.get("text"))
            line_id = self._string(payload.get("line_id"))
            scene_id = self._string(payload.get("scene_id"))
            pacing = self._string(payload.get("pacing_tag")).lower() or "balanced"
            wpm = 180 if pacing == "fast" else (120 if pacing == "slow" else 150)
            word_count = max(1, len(text.split()))
            duration = round((word_count / wpm) * 60.0 + 0.2, 2)
            start = round(cursor, 2)
            end = round(cursor + duration, 2)
            timeline.append(
                {
                    "line_id": line_id,
                    "scene_id": scene_id,
                    "start_seconds": start,
                    "end_seconds": end,
                    "duration_seconds": duration,
                }
            )
            cursor = end
        return timeline

    def build_audio_timeline(
        self,
        dialogue_lines: Any,
        timing_metadata: Any,
        voice_provider_plan: Any,
    ) -> Dict[str, Any]:
        timing = timing_metadata if isinstance(timing_metadata, list) else []
        lines = dialogue_lines if isinstance(dialogue_lines, list) else []
        provider = voice_provider_plan if isinstance(voice_provider_plan, dict) else {}
        clips: List[Dict[str, Any]] = []
        timing_by_id: Dict[str, Dict[str, Any]] = {}
        for row in timing:
            if isinstance(row, dict):
                lid = self._string(row.get("line_id"))
                if lid:
                    timing_by_id[lid] = row
        for line in lines:
            payload = line.model_dump() if isinstance(line, DialogueLine) else (line if isinstance(line, dict) else None)
            if not isinstance(payload, dict):
                continue
            line_id = self._string(payload.get("line_id"))
            timing_row = timing_by_id.get(line_id, {})
            clips.append(
                {
                    "line_id": line_id,
                    "scene_id": self._string(payload.get("scene_id")),
                    "character_id": self._string(payload.get("character_id")),
                    "text": self._string(payload.get("text")),
                    "voice_provider": provider.get("provider", "local_tts"),
                    "start_seconds": timing_row.get("start_seconds", 0.0),
                    "end_seconds": timing_row.get("end_seconds", 0.0),
                }
            )
        return {
            "voice_provider": provider.get("provider", "local_tts"),
            "clips": clips,
            "total_clips": len(clips),
        }


dialogue_voice_service = DialogueVoiceService()
