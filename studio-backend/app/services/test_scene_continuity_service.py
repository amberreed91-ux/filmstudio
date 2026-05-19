from __future__ import annotations

from app.models.production_intelligence import ProviderRequestProvenance, SceneProductionPackage
from app.services.provider_request_service import provider_request_service
from app.services.scene_continuity_service import scene_continuity_service
from app.services.script_parser import ScriptParser


def test_track_scene_continuity_tracks_required_dimensions_and_warnings():
    scenes = [
        {
            "scene_id": "scene_001",
            "emotional_target": "guarded",
            "lighting": "low key",
            "wardrobe": "green coat",
            "location": "apartment hallway",
            "pacing": "slow",
            "unresolved_tension": "hidden betrayal",
        },
        {
            "scene_id": "scene_002",
            "emotional_target": "angry",
            "lighting": "high key",
            "wardrobe": "black coat",
            "location": "street exterior",
            "pacing": "fast",
        },
    ]
    continuity = scene_continuity_service.track_scene_continuity(scenes)
    assert continuity["status"] == "warning"
    assert len(continuity["scene_states"]) == 2
    first = continuity["scene_states"][0]
    assert set(first.keys()) == {
        "scene_id",
        "emotional_state",
        "lighting_continuity",
        "wardrobe_continuity",
        "environment_continuity",
        "pacing_continuity",
        "unresolved_tension",
        "facial_identity",
        "silhouette",
        "movement_style",
        "speech_rhythm",
    }
    assert continuity["warnings"]


def test_generate_transition_context_contains_entering_exiting_and_unresolved_tension():
    transition = scene_continuity_service.generate_transition_context(
        {"emotional_state": "guarded", "unresolved_tension": "hidden betrayal"},
        {"emotional_state": "angry"},
    )
    assert transition == {
        "entering_emotion": "angry",
        "exiting_emotion": "guarded",
        "unresolved_tension": "hidden betrayal",
    }


def test_provider_request_includes_scene_continuity_prompt_guidance():
    payload = SceneProductionPackage(
        scene_id="scene_101",
        film_id="film_101",
        narrative_purpose="Escalate argument",
        emotional_target="rising anger",
        visual_target="Two siblings in corridor",
        continuity_constraints=["Preserve screen direction"],
    ).model_dump()
    payload["director_continuity_context"] = {
        "transition_context": {
            "entering_emotion": "angry",
            "exiting_emotion": "guarded",
            "unresolved_tension": "hidden betrayal",
        }
    }
    payload["continuity_warnings"] = ["scene_001 -> scene_002: pacing continuity mismatch"]

    provenance = ProviderRequestProvenance(scene_id="scene_101", film_id="film_101")
    prompt_components, _ = provider_request_service._derive_prompt(payload, {}, provenance)
    execution_notes, _ = provider_request_service._derive_execution_notes(payload, provenance)
    assert any("Transition emotion:" in component for component in prompt_components)
    assert any("Carry unresolved tension:" in component for component in prompt_components)
    assert any("Continuity warning:" in note for note in execution_notes)


def test_prompt_envelope_includes_transition_continuity_lines():
    parser = ScriptParser()
    scenes = [
        {"scene_id": "scene_001", "text": "INT. HALLWAY - NIGHT", "emotional_target": "guarded", "pacing": "slow"},
        {"scene_id": "scene_002", "text": "EXT. STREET - NIGHT", "emotional_target": "angry", "pacing": "fast"},
    ]
    envelope = parser.build_prompt_envelope(
        scenes,
        {"prompt_influence_enabled": True},
        ["cinematic contrast"],
        ["wide establishing shot"],
    )["prompt_envelope"]
    assert any("Transition emotion:" in token for token in envelope["shot_tokens"])
