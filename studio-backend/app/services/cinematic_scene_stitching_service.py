from __future__ import annotations

from typing import Any, Dict, List

from app.models.scene_assembly import SceneAssembly


class CinematicSceneStitchingService:
    """
    Additive stitching planner for coherent scene-level clip assembly.
    """

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _extract_ordered_shots(self, scene_sequence: Any) -> List[str]:
        if not isinstance(scene_sequence, list):
            return []
        ordered: List[str] = []
        for scene_entry in scene_sequence:
            if not isinstance(scene_entry, dict):
                continue
            shots = scene_entry.get("shots")
            if not isinstance(shots, list):
                continue
            for shot in shots:
                clean = self._string(shot)
                if clean:
                    ordered.append(clean)
        return ordered

    def _select_transition(self, index: int, total: int, pacing_profile: str) -> str:
        if index >= total - 1:
            return "end"
        if pacing_profile == "fast":
            return "cut"
        if pacing_profile == "slow":
            return "fade"
        return "fade" if index % 2 else "cut"

    def _transition_timing(self, transition: str, pacing_profile: str) -> float:
        if transition == "end":
            return 0.0
        if transition == "cut":
            return 0.12 if pacing_profile == "fast" else 0.18
        return 0.8 if pacing_profile == "slow" else 0.55

    def build_scene_assembly_v2(
        self,
        scene_sequence: Any,
        render_output: Any,
        pacing_profile: str = "balanced",
    ) -> Dict[str, Any]:
        ordered_shots = self._extract_ordered_shots(scene_sequence)
        shot_count = len(ordered_shots)
        clean_pacing = pacing_profile if pacing_profile in {"slow", "balanced", "fast"} else "balanced"
        transition_map: Dict[str, Dict[str, str | float]] = {}

        for idx, shot_id in enumerate(ordered_shots):
            transition = self._select_transition(idx, shot_count, clean_pacing)
            transition_map[shot_id] = {
                "transition": transition,
                "timing_seconds": self._transition_timing(transition, clean_pacing),
            }

        runtime_seconds = round((shot_count * 3.0) + sum(
            float(meta.get("timing_seconds", 0.0))
            for meta in transition_map.values()
            if isinstance(meta, dict)
        ), 2)
        assembly_id = f"asm_{shot_count:03d}_{clean_pacing}"

        scene_assembly = SceneAssembly(
            assembly_id=assembly_id,
            ordered_shots=ordered_shots,
            runtime=runtime_seconds,
            transition_map=transition_map,
        )

        # Preserve original clips and expose stitched export path metadata.
        source_clips = [f"{shot_id}.mp4" for shot_id in ordered_shots]
        stitched_mp4_path = f"output/renders/stitched_{assembly_id}.mp4"
        export_ready = bool(ordered_shots) and render_output is not None

        return {
            "scene_assembly_v2": scene_assembly.model_dump(),
            "stitching_plan": {
                "shot_ordering": ordered_shots,
                "transition_timing": transition_map,
                "fade_cut_selection": {
                    shot_id: transition_map[shot_id]["transition"] for shot_id in ordered_shots
                },
                "pacing_aware_assembly": clean_pacing,
            },
            "stitched_export": {
                "format": "mp4",
                "path": stitched_mp4_path,
                "export_ready": export_ready,
                "source_clips_preserved": True,
                "source_clips": source_clips,
            },
        }


cinematic_scene_stitching_service = CinematicSceneStitchingService()
