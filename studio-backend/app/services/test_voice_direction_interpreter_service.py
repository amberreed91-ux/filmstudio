from __future__ import annotations

from app.services.script_parser import ScriptParser
from app.services.voice_direction_interpreter_service import voice_direction_interpreter_service


def test_voice_direction_interpreter_translates_cinematic_commands():
    result = voice_direction_interpreter_service.interpret_commands(
        [
            "make this lonelier",
            "increase tension",
            "slow the pacing",
            "more dreamlike",
            "make lighting harsher",
        ]
    )
    commands = result["voice_direction_commands"]
    guidance = result["voice_direction_guidance"]
    assert len(commands) == 5
    assert guidance["advisory_only"] is True
    assert guidance["requires_creator_approval"] is True
    assert any("tone" in row for row in guidance["emotional_changes"])
    assert any("pace" in row for row in guidance["pacing_changes"])
    assert any("lighting" in row or "style" in row for row in guidance["visual_style_updates"])


def test_script_breakdown_bundle_includes_voice_direction_fields():
    parser = ScriptParser()
    bundle = parser.build_script_breakdown_bundle(
        {
            "script_text": "INT. STUDIO - NIGHT\nNORA watches rain.",
            "voice_direction_commands": [
                "increase tension",
                "more dreamlike",
            ],
        }
    )
    assert isinstance(bundle.get("voice_direction_commands"), list)
    assert isinstance(bundle.get("voice_direction_guidance"), dict)
    assert bundle["voice_direction_guidance"].get("advisory_only") is True
    assert bundle["voice_direction_guidance"].get("requires_creator_approval") is True
    assert isinstance(bundle["voice_direction_guidance"].get("guidance_lines"), list)

