from __future__ import annotations

from app.services.cinematic_scene_stitching_service import cinematic_scene_stitching_service
from app.services.script_parser import ScriptParser


def test_stitching_service_builds_scene_assembly_v2_with_order_runtime_and_transition_map():
    scene_sequence = [
        {"scene_id": "scene_001", "shots": ["shot_001_a", "shot_001_b"]},
        {"scene_id": "scene_002", "shots": ["shot_002_a"]},
    ]
    result = cinematic_scene_stitching_service.build_scene_assembly_v2(
        scene_sequence,
        {"render_id": "render_001"},
        pacing_profile="fast",
    )

    assembly = result["scene_assembly_v2"]
    assert assembly["assembly_id"] == "asm_003_fast"
    assert assembly["ordered_shots"] == ["shot_001_a", "shot_001_b", "shot_002_a"]
    assert isinstance(assembly["runtime"], float)
    assert set(assembly["transition_map"].keys()) == {"shot_001_a", "shot_001_b", "shot_002_a"}


def test_stitching_plan_supports_ordering_transition_and_fade_cut_selection():
    scene_sequence = [
        {"scene_id": "scene_001", "shots": ["shot_001_a", "shot_001_b", "shot_001_c"]},
    ]
    result = cinematic_scene_stitching_service.build_scene_assembly_v2(
        scene_sequence,
        {"render_id": "render_001"},
        pacing_profile="balanced",
    )
    plan = result["stitching_plan"]
    assert plan["shot_ordering"] == ["shot_001_a", "shot_001_b", "shot_001_c"]
    assert plan["pacing_aware_assembly"] == "balanced"
    assert plan["fade_cut_selection"]["shot_001_a"] in {"fade", "cut", "end"}
    assert "shot_001_b" in plan["transition_timing"]


def test_stitched_export_is_mp4_and_preserves_original_clips():
    scene_sequence = [
        {"scene_id": "scene_001", "shots": ["shot_001_a", "shot_001_b"]},
    ]
    result = cinematic_scene_stitching_service.build_scene_assembly_v2(
        scene_sequence,
        {"render_id": "render_001"},
    )
    export = result["stitched_export"]
    assert export["format"] == "mp4"
    assert export["path"].endswith(".mp4")
    assert export["source_clips_preserved"] is True
    assert export["source_clips"] == ["shot_001_a.mp4", "shot_001_b.mp4"]


def test_script_parser_scene_assembly_keeps_v1_and_exposes_v2_stitching_fields():
    parser = ScriptParser()
    scene_sequence = [
        {"scene_id": "scene_001", "shots": ["shot_001_a", "shot_001_b"]},
        {"scene_id": "scene_002", "shots": ["shot_002_a"]},
    ]
    result = parser.build_scene_assembly(scene_sequence, {"render_id": "render_001"})
    assert result["scene_assembly"] == {
        "scene_count": 2,
        "assembled": True,
        "shots_available": 3,
    }
    assert result["scene_assembly_v2"]["ordered_shots"] == ["shot_001_a", "shot_001_b", "shot_002_a"]
    assert result["stitched_export"]["format"] == "mp4"
