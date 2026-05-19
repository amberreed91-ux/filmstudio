from __future__ import annotations

from app.models.production_intelligence import ProviderRequestProvenance, SceneProductionPackage
from app.services.emotional_arc_service import emotional_arc_service
from app.services.provider_request_service import provider_request_service
from app.services.script_parser import ScriptParser


def test_emotional_arc_profile_contains_required_dimensions():
    scenes = [
        {"scene_id": "scene_001", "text": "quiet confession", "emotional_target": "vulnerable"},
        {"scene_id": "scene_002", "text": "rising threat", "emotional_target": "fear"},
    ]
    profiles = emotional_arc_service.build_emotional_arc_profiles(scenes)
    assert len(profiles) == 2
    first = profiles[0]
    assert hasattr(first, "emotional_intensity")
    assert hasattr(first, "tension")
    assert hasattr(first, "vulnerability")
    assert hasattr(first, "escalation")
    assert hasattr(first, "catharsis")


def test_emotional_arc_tracks_scene_movement_pacing_and_climax():
    scenes = [
        {"scene_id": "scene_001", "text": "quiet room tone", "emotional_target": "vulnerable"},
        {"scene_id": "scene_002", "text": "betrayal conflict danger", "emotional_target": "fear"},
        {"scene_id": "scene_003", "text": "release and accept", "emotional_target": "relief"},
    ]
    profiles = emotional_arc_service.build_emotional_arc_profiles(scenes)
    movement = emotional_arc_service.track_scene_to_scene_movement(profiles)
    pacing = emotional_arc_service.build_pacing_balance(profiles)
    climax = emotional_arc_service.build_climax_buildup(profiles)
    continuity = emotional_arc_service.emotional_continuity_score(profiles)
    assert len(movement) == 2
    assert pacing["balance"] in {"steady", "slow", "accelerated"}
    assert isinstance(climax["buildup_score"], float)
    assert continuity["status"] in {"stable", "mixed", "drifting"}


def test_provider_prompt_includes_emotional_arc_guidance_lines():
    payload = SceneProductionPackage(
        scene_id="scene_101",
        film_id="film_101",
        narrative_purpose="Escalate confrontation",
        emotional_target="rising dread",
        visual_target="two characters in narrow hallway",
        continuity_constraints=["Preserve screen direction"],
    ).model_dump()
    payload["emotional_continuity_score"] = {"score": 0.82, "status": "stable", "issues": []}
    payload["emotional_pacing_balance"] = {"balance": "steady", "avg_escalation": 0.61}
    payload["emotional_climax_buildup"] = {"buildup_score": 0.77, "peak_scene_id": "scene_103"}
    provenance = ProviderRequestProvenance(scene_id="scene_101", film_id="film_101")
    prompt_components, _ = provider_request_service._derive_prompt(payload, {}, provenance)
    assert any("Emotional continuity score:" in item for item in prompt_components)
    assert any("Climax buildup targeting scene:" in item for item in prompt_components)


def test_script_breakdown_bundle_includes_emotional_arc_outputs():
    parser = ScriptParser()
    bundle = parser.build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT
ELENA
I can't do this alone.
EXT. STREET - NIGHT
MARCUS
Then don't.
"""
    )
    assert isinstance(bundle.get("emotional_arc_profiles"), list)
    assert isinstance(bundle.get("emotional_arc_movement"), list)
    assert isinstance(bundle.get("emotional_pacing_balance"), dict)
    assert isinstance(bundle.get("emotional_climax_buildup"), dict)
    assert isinstance(bundle.get("emotional_continuity_score"), dict)
