from __future__ import annotations

from app.models.production_intelligence import SceneProductionPackage
from app.services.character_consistency_service import character_consistency_service
from app.models.production_intelligence import ProviderRequestProvenance
from app.services.provider_request_service import provider_request_service
from app.services.script_parser import ScriptParser


def test_build_character_profiles_from_scenes_creates_profiles():
    scenes = [
        {"scene_id": "scene_001", "character_appearances": ["Elena", "Marcus"]},
        {"scene_id": "scene_002", "character_appearances": ["Elena"]},
    ]
    profiles = character_consistency_service.build_character_profiles_from_scenes(scenes)
    ids = sorted(profile.character_id for profile in profiles)
    assert ids == ["elena", "marcus"]


def test_inject_character_visual_traits_appends_context():
    context = {
        "characters": [{"character_id": "elena", "name": "Elena"}],
        "reference_lines": ["Elena | appearance: short dark hair | wardrobe: green coat"],
    }
    shaped = character_consistency_service.inject_character_visual_traits("moody wide shot", context)
    assert "moody wide shot" in shaped
    assert "Character continuity:" in shaped
    assert "Elena" in shaped


def test_provider_request_includes_character_consistency_notes_and_prompt():
    payload = SceneProductionPackage(
        scene_id="scene_001",
        film_id="film_001",
        narrative_purpose="Reveal tension between siblings",
        emotional_target="controlled dread",
        visual_target="Two characters in mirrored framing",
        continuity_constraints=["Preserve screen direction"],
    ).model_dump()
    payload["character_profiles"] = [
        {
            "character_id": "elena",
            "name": "Elena",
            "appearance_traits": ["short dark hair"],
            "wardrobe": ["green coat"],
            "visual_references": ["scene_001_ref"],
            "voice_tone": "restrained",
            "emotional_baseline": "guarded",
        }
    ]
    payload["character_appearances"] = ["Elena"]
    provenance = ProviderRequestProvenance(scene_id="scene_001", film_id="film_001")
    prompt_components, _ = provider_request_service._derive_prompt(payload, {}, provenance)
    execution_notes, _ = provider_request_service._derive_execution_notes(payload, provenance)
    assert any("Character continuity" in component for component in prompt_components)
    assert any("wardrobe continuity" in note.lower() for note in execution_notes)


def test_script_parser_prompt_envelope_adds_character_consistency_tokens():
    parser = ScriptParser()
    scenes = [
        {
            "scene_id": "scene_001",
            "text": "INT. ROOM - NIGHT",
            "character_appearances": ["Elena"],
        }
    ]
    envelope = parser.build_prompt_envelope(
        scenes,
        {"prompt_influence_enabled": True},
        ["cinematic contrast"],
        ["wide establishing shot"],
    )["prompt_envelope"]
    assert any("Character continuity" in token for token in envelope["visual_tokens"])
    assert any("consistent character appearance" in token.lower() for token in envelope["shot_tokens"])
