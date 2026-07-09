from __future__ import annotations

from app.services.ambient_audio_service import ambient_audio_service
from app.services.script_parser import ScriptParser


def test_ambient_audio_track_generation_supports_required_types_and_layers():
    scene_sequence = [
        {"scene_id": "scene_001", "shots": ["shot_001_a"]},
        {"scene_id": "scene_002", "shots": ["shot_002_a"]},
        {"scene_id": "scene_003", "shots": ["shot_003_a"]},
    ]
    tracks = ambient_audio_service.build_layered_ambient_tracks(scene_sequence, 18.0)
    assert len(tracks) >= 6
    ambience_types = {track.ambience_type for track in tracks}
    assert ambience_types.issubset(ambient_audio_service.SUPPORTED_TYPES)
    assert any(track.layer == 1 for track in tracks)
    assert any(track.layer == 2 for track in tracks)


def test_ambient_timeline_sync_supports_layered_audio_and_dialogue_ducking():
    scene_sequence = [{"scene_id": "scene_001", "shots": ["shot_001_a"]}]
    tracks = ambient_audio_service.build_layered_ambient_tracks(scene_sequence, 6.0)
    dialogue_timeline = {
        "clips": [{"line_id": "l1", "start_seconds": 1.0, "end_seconds": 2.0}],
        "total_clips": 1,
    }
    timeline = ambient_audio_service.build_ambient_timeline_sync(tracks, dialogue_timeline)
    assert timeline["layered"] is True
    assert timeline["track_count"] == len(timeline["tracks"])
    assert timeline["duck_windows"][0]["duck_to"] == 0.72


def test_scene_assembly_and_final_audio_render_plan_integration():
    parser = ScriptParser()
    scene_sequence = [{"scene_id": "scene_001", "shots": ["shot_001_a", "shot_001_b"]}]
    ambient_timeline = {
        "tracks": [{"track_id": "scene_001_amb_01", "scene_id": "scene_001", "layer": 1}],
        "duck_windows": [],
        "layered": True,
        "track_count": 1,
    }
    result = parser.build_scene_assembly(
        scene_sequence,
        {"render_id": "render_001"},
        {"clips": [], "total_clips": 0},
        ambient_timeline,
    )
    assert result["scene_ambient_timeline"]["layered"] is True
    assert result["ambient_track_count"] == 1

    final_mix = ambient_audio_service.build_final_film_audio_render_plan(
        {"path": "output/renders/stitched_asm_002_balanced.mp4"},
        ambient_timeline,
    )["final_audio_mix"]
    assert final_mix["target_format"] == "mp4"
    assert final_mix["layered_audio"] is True


def test_script_breakdown_bundle_includes_ambient_audio_outputs():
    parser = ScriptParser()
    bundle = parser.build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT
Rain taps the window.
EXT. STREET - NIGHT
Cars hiss past in wet traffic.
"""
    )
    assert isinstance(bundle.get("ambient_audio_tracks"), list)
    assert isinstance(bundle.get("ambient_audio_timeline"), dict)
    assert isinstance(bundle.get("final_film_audio_render_plan"), dict)
