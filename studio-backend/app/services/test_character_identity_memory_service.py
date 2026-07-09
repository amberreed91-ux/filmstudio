from __future__ import annotations

from app.services.character_identity_memory_service import character_identity_memory_service
from app.services.script_parser import ScriptParser


def test_character_identity_memory_service_builds_provider_context_and_drift_warnings():
    profiles = [
        {
            "character_id": "elena",
            "name": "Elena",
            "visual_references": ["ref/elena-face-01.png"],
            "facial_identity": "oval face, scar left brow",
            "silhouette": "narrow shoulders, long coat",
            "movement_style": "measured stillness",
            "emotional_baseline": "guarded",
            "emotional_behavior": "suppresses panic",
            "speech_rhythm": "measured",
        }
    ]
    scene = {"scene_id": "scene_001", "character_appearances": ["Elena"], "emotional_target": "angry"}
    provider_context = character_identity_memory_service.build_provider_identity_context(profiles, scene)
    memory_notes = character_identity_memory_service.build_emotional_memory_continuity(profiles, scene)
    drift = character_identity_memory_service.detect_identity_drift_warnings(profiles, scene)

    assert provider_context["advisory_only"] is True
    assert provider_context["identity_lines"]
    assert provider_context["reference_images"]["elena"] == ["ref/elena-face-01.png"]
    assert any("carry continuity" in note.lower() for note in memory_notes)
    assert any("emotional drift warning" in row.lower() for row in drift)


def test_script_breakdown_bundle_includes_identity_memory_fields_and_warnings():
    bundle = ScriptParser().build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT
ELENA stares into a mirror.
MARCUS
We have to move now.
"""
    )
    assert isinstance(bundle.get("character_identity_memory"), dict)
    assert isinstance(bundle.get("provider_identity_context"), dict)
    assert isinstance(bundle.get("emotional_identity_continuity"), list)
    assert isinstance(bundle.get("identity_drift_warnings"), list)
    assert isinstance(bundle.get("continuity_warnings"), list)

