from __future__ import annotations

from typing import Any, Dict, List

from app.models.film_assembly_timeline import FilmAssemblyTimeline


class FullFilmAssemblyService:
    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def build_film_assembly_timeline(
        self,
        scenes: Any,
        scene_transitions: Any,
        ambient_audio_timeline: Any,
        audio_dialogue_timeline: Any,
        stitched_export: Any,
    ) -> Dict[str, Any]:
        scene_list = scenes if isinstance(scenes, list) else []
        ordered_scenes = [
            self._string(scene.get("scene_id"))
            for scene in scene_list
            if isinstance(scene, dict) and self._string(scene.get("scene_id"))
        ]
        transitions = scene_transitions if isinstance(scene_transitions, list) else []
        ambient_tracks = (
            ambient_audio_timeline.get("tracks")
            if isinstance(ambient_audio_timeline, dict) and isinstance(ambient_audio_timeline.get("tracks"), list)
            else []
        )
        dialogue_clips = (
            audio_dialogue_timeline.get("clips")
            if isinstance(audio_dialogue_timeline, dict) and isinstance(audio_dialogue_timeline.get("clips"), list)
            else []
        )
        subtitles: List[Dict[str, str | float]] = []
        for clip in dialogue_clips:
            if not isinstance(clip, dict):
                continue
            text = self._string(clip.get("text"))
            if not text:
                continue
            subtitles.append(
                {
                    "scene_id": self._string(clip.get("scene_id")),
                    "start_seconds": float(clip.get("start_seconds", 0.0)),
                    "end_seconds": float(clip.get("end_seconds", 0.0)),
                    "text": text,
                }
            )

        title_cards = [{"label": "Main Title", "start_seconds": 0.0, "end_seconds": 2.5}]
        credits = [{"label": "End Credits", "start_seconds": max(0.0, len(ordered_scenes) * 3.0), "end_seconds": max(1.0, len(ordered_scenes) * 3.0 + 6.0)}]

        timeline = FilmAssemblyTimeline(
            timeline_id=f"film_timeline_{len(ordered_scenes):03d}",
            ordered_scenes=ordered_scenes,
            audio_tracks=[*ambient_tracks, *dialogue_clips],
            subtitles=subtitles,
            transitions=[row for row in transitions if isinstance(row, dict)],
            title_cards=title_cards,
            credits=credits,
        )

        stitched = stitched_export if isinstance(stitched_export, dict) else {}
        mp4_path = self._string(stitched.get("path")) or f"output/renders/full_film_{timeline.timeline_id}.mp4"
        export_pipeline = {
            "mp4_export": {"path": mp4_path, "ready": bool(ordered_scenes)},
            "archive_package": {"path": f"output/archives/{timeline.timeline_id}.zip", "ready": bool(ordered_scenes)},
            "preview_render": {"path": f"output/previews/{timeline.timeline_id}_preview.mp4", "ready": bool(ordered_scenes)},
        }
        runtime_metadata = {
            "scene_count": len(ordered_scenes),
            "ambient_track_count": len(ambient_tracks),
            "dialogue_track_count": len(dialogue_clips),
            "subtitle_count": len(subtitles),
            "transition_count": len(timeline.transitions),
            "title_card_count": len(title_cards),
            "credits_count": len(credits),
        }
        return {
            "film_assembly_timeline": timeline.model_dump(),
            "film_export_pipeline": export_pipeline,
            "film_runtime_metadata": runtime_metadata,
        }


full_film_assembly_service = FullFilmAssemblyService()
