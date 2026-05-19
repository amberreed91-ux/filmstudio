from __future__ import annotations

from typing import Any, Dict, List

from app.models.ambient_audio_track import AmbientAudioTrack


class AmbientAudioService:
    SUPPORTED_TYPES = {
        "rain",
        "traffic",
        "crowd_tone",
        "room_tone",
        "wind",
        "cinematic_drones",
    }

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _float(self, value: Any, fallback: float = 0.5) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        return fallback

    def build_layered_ambient_tracks(
        self,
        scene_sequence: Any,
        base_runtime_seconds: float = 0.0,
    ) -> List[AmbientAudioTrack]:
        sequence = scene_sequence if isinstance(scene_sequence, list) else []
        runtime = max(1.0, base_runtime_seconds if isinstance(base_runtime_seconds, (int, float)) else 12.0)
        scene_window = runtime / max(1, len(sequence))
        tracks: List[AmbientAudioTrack] = []
        cursor = 0.0
        for scene_idx, scene_entry in enumerate(sequence, start=1):
            if not isinstance(scene_entry, dict):
                continue
            scene_id = self._string(scene_entry.get("scene_id")) or f"scene_{scene_idx:03d}"
            primary_type = (
                "rain" if scene_idx % 3 == 1 else ("traffic" if scene_idx % 3 == 2 else "room_tone")
            )
            secondary_type = "cinematic_drones" if scene_idx % 2 == 0 else "wind"
            layer_defs = [
                (1, primary_type, 0.55),
                (2, secondary_type, 0.38),
            ]
            for layer, ambience_type, intensity in layer_defs:
                if ambience_type not in self.SUPPORTED_TYPES:
                    continue
                tracks.append(
                    AmbientAudioTrack(
                        track_id=f"{scene_id}_amb_{layer:02d}",
                        scene_id=scene_id,
                        layer=layer,
                        ambience_type=ambience_type,
                        intensity=intensity,
                        start_seconds=round(cursor, 2),
                        end_seconds=round(cursor + scene_window, 2),
                        provider_hint="local",
                    )
                )
            cursor += scene_window
        return tracks

    def build_ambient_timeline_sync(
        self,
        ambient_tracks: Any,
        dialogue_timeline: Any = None,
    ) -> Dict[str, Any]:
        tracks = ambient_tracks if isinstance(ambient_tracks, list) else []
        dialogue = dialogue_timeline if isinstance(dialogue_timeline, dict) else {}
        clips = dialogue.get("clips") if isinstance(dialogue.get("clips"), list) else []
        duck_windows: List[Dict[str, float]] = []
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            start = self._float(clip.get("start_seconds"), 0.0)
            end = self._float(clip.get("end_seconds"), 0.0)
            if end > start:
                duck_windows.append({"start_seconds": start, "end_seconds": end, "duck_to": 0.72})

        timeline = []
        for track in tracks:
            payload = track.model_dump() if isinstance(track, AmbientAudioTrack) else (track if isinstance(track, dict) else None)
            if not isinstance(payload, dict):
                continue
            timeline.append(
                {
                    "track_id": self._string(payload.get("track_id")),
                    "scene_id": self._string(payload.get("scene_id")),
                    "layer": int(payload.get("layer", 1)),
                    "ambience_type": self._string(payload.get("ambience_type")),
                    "start_seconds": self._float(payload.get("start_seconds"), 0.0),
                    "end_seconds": self._float(payload.get("end_seconds"), 0.0),
                    "intensity": self._float(payload.get("intensity"), 0.5),
                }
            )

        return {
            "tracks": timeline,
            "duck_windows": duck_windows,
            "layered": True,
            "track_count": len(timeline),
        }

    def build_final_film_audio_render_plan(
        self,
        stitched_export: Any,
        ambient_timeline: Any,
    ) -> Dict[str, Any]:
        stitched = stitched_export if isinstance(stitched_export, dict) else {}
        ambient = ambient_timeline if isinstance(ambient_timeline, dict) else {}
        return {
            "final_audio_mix": {
                "target_format": "mp4",
                "video_path": self._string(stitched.get("path")),
                "ambient_track_count": int(ambient.get("track_count", 0)),
                "layered_audio": ambient.get("layered") is True,
                "mix_ready": bool(self._string(stitched.get("path"))),
            }
        }


ambient_audio_service = AmbientAudioService()
