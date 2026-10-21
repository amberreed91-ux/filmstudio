"""Rationale derivation reads real scene importance; never silent filler.

Regression coverage for the Review Generation Plan bug where Scene 1 showed
only its slug line plus the retired template filler
("A beat that earns its place in the larger composition.") even though the
scene carries a real description. The description field was assigned but
never read, and scene_version ignored importance axes so the plan could
not regenerate when the scene changed.
"""
from __future__ import annotations

from app.services.generation_context_service import GenerationContextService
from app.services.shot_rationale_service import (
    GENERIC_FALLBACK_SENTENCE,
    SCENE_IMPORTANCE_NOT_SET,
    is_generic_fallback,
    shot_rationale_service,
    strip_generic_fallback,
)


def _scene_001_like() -> dict:
    return {
        "scene_id": "scene_001",
        "heading": "EXT. DOWNTOWN CHICAGO — GOLDEN HOUR",
        "location": "DOWNTOWN CHICAGO — GOLDEN HOUR",
        "time_of_day": "",
        "emotional_tone": "",
        "characters": "[]",
        "description": (
            "Chicago is alive. The L train moves through the skyline. "
            "People fill the streets.\nMaya walks through the city watching small moments."
        ),
        "text": "Chicago is alive. The L train moves through the skyline.",
    }


def test_described_scene_shows_real_importance_not_filler():
    result = shot_rationale_service.get_rationale(
        project_id="p", scene_id="scene_001", scene_data=_scene_001_like()
    )
    assert GENERIC_FALLBACK_SENTENCE not in result["rationale"]
    assert not is_generic_fallback(result["rationale"])
    assert "Chicago is alive." in result["rationale"]
    assert result["importance_state"] == "set"
    assert result["importance_source"] == "description"
    assert result["contains_generic_fallback"] is False


def test_genuinely_empty_scene_shows_explicit_not_set():
    result = shot_rationale_service.get_rationale(
        project_id="p",
        scene_id="scene_009",
        scene_data={"scene_id": "scene_009", "heading": "EXT. NOWHERE — NIGHT"},
    )
    assert GENERIC_FALLBACK_SENTENCE not in result["rationale"]
    assert SCENE_IMPORTANCE_NOT_SET in result["rationale"]
    assert result["importance_state"] == "not_set"
    assert result["importance_source"] == "none"


def test_stored_filler_is_detectable_and_strippable():
    stored = f"EXT. DOWNTOWN CHICAGO — GOLDEN HOUR. {GENERIC_FALLBACK_SENTENCE}"
    assert is_generic_fallback(stored) is True
    stripped = strip_generic_fallback(stored)
    assert GENERIC_FALLBACK_SENTENCE not in stripped
    assert not is_generic_fallback(stripped)
    assert "EXT. DOWNTOWN CHICAGO" in stripped
    assert is_generic_fallback("Chicago is alive.") is False


def test_degenerate_empty_cast_string_counts_as_absent():
    scene = _scene_001_like()
    scene["characters"] = "[]"
    result = shot_rationale_service.get_rationale(
        project_id="p", scene_id="scene_001", scene_data=scene
    )
    # Must take the description branch, never treat "[]" as a named character.
    assert "Chicago is alive." in result["rationale"]
    assert "[]" not in result["rationale"]


def test_scene_version_regenerates_when_importance_changes():
    service = GenerationContextService()
    base = _scene_001_like()
    edited = dict(base)
    edited["description"] = base["description"] + " Maya keeps walking."
    assert service.scene_version(base) != service.scene_version(edited)

    tone_edited = dict(base)
    tone_edited["emotional_tone"] = "grief"
    assert service.scene_version(base) != service.scene_version(tone_edited)

    chars_edited = dict(base)
    chars_edited["characters"] = ["MAYA"]
    assert service.scene_version(base) != service.scene_version(chars_edited)

    loc_edited = dict(base)
    loc_edited["location"] = "SOUTH SIDE — NIGHT"
    assert service.scene_version(base) != service.scene_version(loc_edited)


def test_scene_version_stable_for_identical_state():
    service = GenerationContextService()
    assert service.scene_version(_scene_001_like()) == service.scene_version(_scene_001_like())
    assert service.scene_version(None) == "absent"


def test_stale_scene_version_context_is_rejected_with_rebuild_blocker():
    service = GenerationContextService()
    base = _scene_001_like()
    context = service.create_generation_context(
        project_id="p",
        scene_id="scene_001",
        shot_id="scene_001_shot_001",
        scene=base,
        storyboard_context=None,
        reference_assets=[],
        prompt_source="BOARD",
    )
    edited = dict(base)
    edited["description"] = base["description"] + " Maya keeps walking."
    readiness = service.validate_generation_context(
        context=context,
        current_scene=edited,
        current_storyboard_context=None,
        current_reference_assets=[],
    )
    assert not readiness.ready
    assert any("scene version mismatch" in b.lower() for b in readiness.blockers)
    assert any("rebuild" in b.lower() for b in readiness.blockers)
