from __future__ import annotations

from typing import Any, Dict, List

from app.models.voice_direction_command import VoiceDirectionCommand


class VoiceDirectionInterpreterService:
    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _normalize(self, command: str) -> str:
        return self._string(command).lower()

    def interpret_command(self, command: Any) -> VoiceDirectionCommand:
        raw = self._string(command)
        normalized = self._normalize(raw)
        emotional_changes: Dict[str, str] = {}
        pacing_changes: Dict[str, str] = {}
        visual_style_updates: Dict[str, str] = {}

        if "lonelier" in normalized:
            emotional_changes["tone"] = "lonelier"
            emotional_changes["intensity"] = "subdued isolation"
        if "increase tension" in normalized or "more tension" in normalized:
            emotional_changes["tension"] = "increase"
            pacing_changes["rhythm"] = "tighter beats"
        if "slow the pacing" in normalized or "slower pacing" in normalized:
            pacing_changes["pace"] = "slow"
            pacing_changes["shot_duration"] = "longer holds"
        if "dreamlike" in normalized:
            visual_style_updates["style"] = "dreamlike"
            visual_style_updates["camera"] = "soft drift"
        if "lighting harsher" in normalized or "make lighting harsher" in normalized:
            visual_style_updates["lighting"] = "harsher contrast"
            visual_style_updates["contrast"] = "high"

        return VoiceDirectionCommand(
            raw_command=raw,
            normalized_command=normalized,
            emotional_changes=emotional_changes,
            pacing_changes=pacing_changes,
            visual_style_updates=visual_style_updates,
            advisory_only=True,
            requires_creator_approval=True,
        )

    def interpret_commands(self, commands: Any) -> Dict[str, Any]:
        rows = commands if isinstance(commands, list) else []
        interpreted: List[VoiceDirectionCommand] = []
        for row in rows:
            interpreted.append(self.interpret_command(row))

        emotional_changes: List[Dict[str, str]] = []
        pacing_changes: List[Dict[str, str]] = []
        visual_updates: List[Dict[str, str]] = []
        for cmd in interpreted:
            if cmd.emotional_changes:
                emotional_changes.append(cmd.emotional_changes)
            if cmd.pacing_changes:
                pacing_changes.append(cmd.pacing_changes)
            if cmd.visual_style_updates:
                visual_updates.append(cmd.visual_style_updates)

        guidance_lines: List[str] = []
        for cmd in interpreted:
            if cmd.emotional_changes:
                guidance_lines.append(f"Voice direction emotion: {cmd.emotional_changes}")
            if cmd.pacing_changes:
                guidance_lines.append(f"Voice direction pacing: {cmd.pacing_changes}")
            if cmd.visual_style_updates:
                guidance_lines.append(f"Voice direction visual: {cmd.visual_style_updates}")

        return {
            "voice_direction_commands": [cmd.model_dump() for cmd in interpreted],
            "voice_direction_guidance": {
                "advisory_only": True,
                "requires_creator_approval": True,
                "emotional_changes": emotional_changes,
                "pacing_changes": pacing_changes,
                "visual_style_updates": visual_updates,
                "guidance_lines": guidance_lines,
            },
        }


voice_direction_interpreter_service = VoiceDirectionInterpreterService()

