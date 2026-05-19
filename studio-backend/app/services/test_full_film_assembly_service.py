from __future__ import annotations

from app.services.full_film_assembly_service import full_film_assembly_service
from app.services.script_parser import ScriptParser


def test_full_film_assembly_timeline_supports_required_sections_and_exports():
    result = full_film_assembly_service.build_film_assembly_timeline(
        scenes=[
            {"scene_id": "scene_001"},
            {"scene_id": "scene_002"},
        ],
        scene_transitions=[
            {"scene_id": "scene_001", "transition": "fade", "duration": 2},
        ],
        ambient_audio_timeline={
            "tracks": [{"track_id": "amb_001", "scene_id": "scene_001", "layer": 1}],
        },
        audio_dialogue_timeline={
            "clips": [
                {
                    "line_id": "line_001",
                    "scene_id": "scene_001",
                    "start_seconds": 1.0,
                    "end_seconds": 2.4,
                    "text": "We have one shot.",
                }
            ]
        },
        stitched_export={"path": "output/renders/stitched_asm_002_balanced.mp4"},
    )

    timeline = result["film_assembly_timeline"]
    export_pipeline = result["film_export_pipeline"]
    runtime = result["film_runtime_metadata"]

    assert timeline["ordered_scenes"] == ["scene_001", "scene_002"]
    assert len(timeline["audio_tracks"]) == 2
    assert len(timeline["subtitles"]) == 1
    assert len(timeline["transitions"]) == 1
    assert len(timeline["title_cards"]) == 1
    assert len(timeline["credits"]) == 1

    assert export_pipeline["mp4_export"]["ready"] is True
    assert export_pipeline["archive_package"]["ready"] is True
    assert export_pipeline["preview_render"]["ready"] is True

    assert runtime["scene_count"] == 2
    assert runtime["ambient_track_count"] == 1
    assert runtime["dialogue_track_count"] == 1
    assert runtime["subtitle_count"] == 1


def test_script_breakdown_bundle_includes_film_assembly_pipeline_and_keeps_scene_exports():
    parser = ScriptParser()
    bundle = parser.build_script_breakdown_bundle(
        """
INT. STUDIO - NIGHT
A monitor flickers in silence.

EXT. ROOFTOP - DAWN
The skyline glows as the team exhales.
"""
    )

    assert isinstance(bundle.get("scene_assembly"), dict)
    assert isinstance(bundle.get("scene_assembly_v2"), dict)
    assert isinstance(bundle.get("stitched_export"), dict)

    assert isinstance(bundle.get("film_assembly_timeline"), dict)
    assert isinstance(bundle.get("film_export_pipeline"), dict)
    assert isinstance(bundle.get("film_runtime_metadata"), dict)
    assert "ordered_scenes" in bundle["film_assembly_timeline"]
    assert "mp4_export" in bundle["film_export_pipeline"]
    assert "scene_count" in bundle["film_runtime_metadata"]
