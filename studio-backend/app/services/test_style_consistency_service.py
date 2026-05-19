from __future__ import annotations

from app.models.production_intelligence import ProviderRequestProvenance, SceneProductionPackage
from app.services.provider_request_service import provider_request_service
from app.services.script_parser import ScriptParser
from app.services.style_consistency_service import style_consistency_service


def test_build_film_visual_style_profile_supports_required_styles():
    required = ["noir", "A24 atmospheric", "dreamlike", "sci-fi", "horror", "realism"]
    for style in required:
        profile = style_consistency_service.build_film_visual_style_profile(style)
        assert profile.style_id.startswith("style_")
        assert profile.style_name
        assert profile.color_palette
        assert profile.lighting_language
        assert profile.lens_style
        assert profile.camera_movement_style
        assert profile.framing_patterns
        assert profile.texture_keywords


def test_inject_style_guidance_appends_style_lock_context():
    profile = style_consistency_service.build_film_visual_style_profile("noir")
    context = style_consistency_service.build_style_reference_context(profile)
    shaped = style_consistency_service.inject_style_guidance("rain-soaked alley", context)
    assert "rain-soaked alley" in shaped
    assert "Film visual style lock:" in shaped
    assert "style: noir" in shaped


def test_provider_request_includes_style_guidance_and_notes():
    payload = SceneProductionPackage(
        scene_id="scene_101",
        film_id="film_101",
        narrative_purpose="Reveal hidden surveillance",
        emotional_target="uneasy dread",
        visual_target="detective silhouette by wet asphalt",
        continuity_constraints=["Preserve screen direction"],
    ).model_dump()
    payload["film_visual_style_profile"] = style_consistency_service.build_film_visual_style_profile(
        "sci-fi"
    ).model_dump()

    provenance = ProviderRequestProvenance(scene_id="scene_101", film_id="film_101")
    prompt_components, _ = provider_request_service._derive_prompt(payload, {}, provenance)
    execution_notes, _ = provider_request_service._derive_execution_notes(payload, provenance)

    assert any("Film visual style lock:" in component for component in prompt_components)
    assert any("style continuity" in note.lower() for note in execution_notes)


def test_visual_continuity_scoring_and_prompt_envelope_integration():
    scenes = [
        {
            "scene_id": "scene_001",
            "text": "Night exterior with high contrast light and heavy grain framing.",
        }
    ]
    profile = style_consistency_service.build_film_visual_style_profile("noir")
    context = style_consistency_service.build_style_reference_context(profile)
    score = style_consistency_service.score_visual_continuity(scenes, context)
    assert isinstance(score.get("score"), float)
    assert score.get("status") in {"locked", "mostly_locked", "drifting"}

    parser = ScriptParser()
    envelope = parser.build_prompt_envelope(
        scenes,
        {"prompt_influence_enabled": True},
        ["cinematic contrast"],
        ["wide establishing shot"],
    )["prompt_envelope"]
    assert any("Film visual style lock:" in token for token in envelope["visual_tokens"])
