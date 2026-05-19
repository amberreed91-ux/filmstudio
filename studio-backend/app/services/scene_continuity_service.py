from __future__ import annotations

from typing import Any, Dict, List


class SceneContinuityService:
    """
    Additive continuity engine for adjacent scene tracking and transition context.
    """

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _norm(self, value: Any) -> str:
        return self._string(value).lower()

    def _scene_state(self, scene: Any) -> Dict[str, str]:
        if not isinstance(scene, dict):
            return {
                "scene_id": "",
                "emotional_state": "",
                "lighting_continuity": "",
                "wardrobe_continuity": "",
                "environment_continuity": "",
                "pacing_continuity": "",
                "unresolved_tension": "",
                "facial_identity": "",
                "silhouette": "",
                "movement_style": "",
                "speech_rhythm": "",
            }
        return {
            "scene_id": self._string(scene.get("scene_id")),
            "emotional_state": self._string(
                scene.get("emotional_target")
                or scene.get("dominant_emotion")
                or scene.get("emotion")
            ),
            "lighting_continuity": self._string(
                scene.get("lighting_language")
                or scene.get("lighting")
                or scene.get("lighting_style")
            ),
            "wardrobe_continuity": self._string(
                scene.get("wardrobe_continuity")
                or scene.get("wardrobe")
                or scene.get("character_costume")
            ),
            "environment_continuity": self._string(
                scene.get("environment_continuity")
                or scene.get("location")
                or scene.get("setting")
            ),
            "pacing_continuity": self._string(
                scene.get("pacing_continuity")
                or scene.get("pacing")
                or scene.get("scene_rhythm")
            ),
            "unresolved_tension": self._string(
                scene.get("unresolved_tension")
                or scene.get("tension")
                or scene.get("open_thread")
            ),
            "facial_identity": self._string(scene.get("facial_identity")),
            "silhouette": self._string(scene.get("silhouette")),
            "movement_style": self._string(scene.get("movement_style")),
            "speech_rhythm": self._string(scene.get("speech_rhythm")),
        }

    def track_scene_continuity(self, scenes: Any) -> Dict[str, Any]:
        scenes_list = scenes if isinstance(scenes, list) else []
        scene_states = [self._scene_state(scene) for scene in scenes_list if isinstance(scene, dict)]
        transitions: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for index in range(1, len(scene_states)):
            prev_state = scene_states[index - 1]
            next_state = scene_states[index]
            transition = self.generate_transition_context(prev_state, next_state)
            transitions.append(transition)

            mismatches = self._collect_mismatches(prev_state, next_state)
            for mismatch in mismatches:
                warnings.append(
                    f"{prev_state.get('scene_id') or 'scene_prev'} -> "
                    f"{next_state.get('scene_id') or 'scene_next'}: {mismatch}"
                )

        return {
            "scene_states": scene_states,
            "transitions": transitions,
            "warnings": warnings,
            "status": "ok" if not warnings else "warning",
        }

    def _collect_mismatches(self, prev_state: Dict[str, str], next_state: Dict[str, str]) -> List[str]:
        checks = [
            ("emotional_state", "emotional continuity drift"),
            ("lighting_continuity", "lighting continuity mismatch"),
            ("wardrobe_continuity", "wardrobe continuity mismatch"),
            ("environment_continuity", "environment continuity mismatch"),
            ("pacing_continuity", "pacing continuity mismatch"),
            ("facial_identity", "facial identity drift"),
            ("silhouette", "silhouette drift"),
            ("movement_style", "movement style drift"),
            ("speech_rhythm", "speech rhythm drift"),
        ]
        mismatches: List[str] = []
        for key, label in checks:
            prev_value = self._norm(prev_state.get(key))
            next_value = self._norm(next_state.get(key))
            if prev_value and next_value and prev_value != next_value:
                mismatches.append(label)
        return mismatches

    def generate_transition_context(
        self,
        previous_scene_state: Any,
        next_scene_state: Any,
    ) -> Dict[str, str]:
        prev_state = previous_scene_state if isinstance(previous_scene_state, dict) else {}
        next_state = next_scene_state if isinstance(next_scene_state, dict) else {}
        entering = self._string(next_state.get("emotional_state"))
        exiting = self._string(prev_state.get("emotional_state"))
        unresolved = self._string(prev_state.get("unresolved_tension")) or self._string(
            next_state.get("unresolved_tension")
        )
        return {
            "entering_emotion": entering,
            "exiting_emotion": exiting,
            "unresolved_tension": unresolved,
        }

    def build_prompt_continuity_lines(self, transition_context: Any, warnings: Any) -> List[str]:
        context = transition_context if isinstance(transition_context, dict) else {}
        lines: List[str] = []
        entering = self._string(context.get("entering_emotion"))
        exiting = self._string(context.get("exiting_emotion"))
        unresolved = self._string(context.get("unresolved_tension"))
        if exiting or entering:
            lines.append(f"Transition emotion: exit={exiting or 'neutral'} -> enter={entering or 'neutral'}")
        if unresolved:
            lines.append(f"Carry unresolved tension: {unresolved}")
        warning_list = warnings if isinstance(warnings, list) else []
        if warning_list:
            lines.append(f"Continuity warning: {warning_list[0]}")
        return lines


scene_continuity_service = SceneContinuityService()
