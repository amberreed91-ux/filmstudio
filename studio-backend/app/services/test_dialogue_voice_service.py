from __future__ import annotations

from app.services.dialogue_voice_service import dialogue_voice_service
from app.services.script_parser import ScriptParser


def test_dialogue_line_generation_includes_subtext_pacing_and_voice_consistency():
    scenes = [
        {
            "scene_id": "scene_001",
            "character_appearances": ["Elena", "Marcus"],
            "emotional_target": "guarded",
            "unresolved_tension": "hidden betrayal",
            "pacing": "slow",
        }
    ]
    profiles = [
        {
            "character_id": "elena",
            "name": "Elena",
            "voice_tone": "low hush",
            "speech_rhythm": "measured",
            "emotional_behavior": "suppresses panic",
        },
        {"character_id": "marcus", "name": "Marcus", "voice_tone": "dry restraint"},
    ]
    lines = dialogue_voice_service.build_dialogue_lines(scenes, profiles)
    assert len(lines) == 2
    assert lines[0].emotional_subtext
    assert lines[0].pacing_tag == "measured"
    assert lines[0].voice_style_hint == "low hush"
    assert "Behavior memory:" in lines[0].text


def test_voice_provider_abstraction_supports_elevenlabs_and_local_tts():
    eleven = dialogue_voice_service.build_voice_provider_plan("elevenlabs")
    local = dialogue_voice_service.build_voice_provider_plan("local_tts")
    assert eleven["capability"] == "ElevenLabs-ready"
    assert local["capability"] == "local TTS-ready"


def test_dialogue_timing_metadata_is_generated_deterministically():
    scenes = [{"scene_id": "scene_001", "character_appearances": ["Elena"], "emotional_target": "guarded"}]
    lines = dialogue_voice_service.build_dialogue_lines(scenes, [])
    timing = dialogue_voice_service.build_dialogue_timing_metadata(lines)
    assert len(timing) == 1
    assert timing[0]["start_seconds"] == 0.0
    assert timing[0]["end_seconds"] >= timing[0]["duration_seconds"]


def test_scene_assembly_integration_includes_dialogue_timeline_and_clip_count():
    parser = ScriptParser()
    scene_sequence = [{"scene_id": "scene_001", "shots": ["shot_001_a"]}]
    dialogue_timeline = {
        "voice_provider": "local_tts",
        "clips": [{"line_id": "scene_001_dlg_01", "scene_id": "scene_001"}],
        "total_clips": 1,
    }
    result = parser.build_scene_assembly(scene_sequence, {"render_id": "render_001"}, dialogue_timeline)
    assert result["scene_dialogue_timeline"]["voice_provider"] == "local_tts"
    assert result["dialogue_clip_count"] == 1


def test_script_breakdown_bundle_includes_dialogue_voice_layer_outputs():
    parser = ScriptParser()
    bundle = parser.build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT
ELENA
We cannot keep pretending.
MARCUS
Then stop pretending.
"""
    )
    assert isinstance(bundle.get("dialogue_lines"), list)
    assert isinstance(bundle.get("dialogue_timing_metadata"), list)
    assert isinstance(bundle.get("voice_provider_plan"), dict)
    assert isinstance(bundle.get("audio_dialogue_timeline"), dict)
