"""Regression tests: generation context, readiness gate, fresh render.

Covers the workstream's required proofs:
- New render does not inherit old camera instructions / storyboard
  interpretation / prompts / references / model selection.
- Changing scene, shot, storyboard, or references invalidates stale
  generation state.
- Fresh Render creates a new generation context.
- Historical prompts/renders cannot silently become current inputs.
- Generation readiness blocks stale data; camera AI suggestions are never
  silently approved.
- Cost limits prevent unauthorized generation.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.generation_context_service import (
    CAMERA_SOURCE_AI_SUGGESTED,
    CAMERA_SOURCE_APPROVED,
    CAMERA_SOURCE_UNSPECIFIED,
    CAMERA_SOURCE_USER_SPECIFIED,
    GenerationContext,
    GenerationContextService,
)
from app.services.model_registry import model_registry
from app.services.model_router import SELECTION_MODE_USER


def _scene(text: str = "INT. DINER - NIGHT") -> dict:
    return {"scene_id": "scn_1", "heading": "INT. DINER - NIGHT", "text": text, "updated_at": "t1"}


def _build_context(service: GenerationContextService, *, scene=None, storyboard=None, refs=None) -> GenerationContext:
    return service.create_generation_context(
        project_id="proj_1",
        scene_id="scn_1",
        shot_id="scn_1_shot_001_take_1",
        scene=scene if scene is not None else _scene(),
        storyboard_context=storyboard,
        reference_assets=refs or [],
        prompt_source="BOARD",
    )


# ── Context fingerprinting ───────────────────────────────────────────────────


def test_scene_change_invalidates_stale_generation_state():
    service = GenerationContextService()
    context = _build_context(service, scene=_scene("original text"))
    readiness = service.validate_generation_context(
        context=context,
        current_scene=_scene("edited text"),
        current_storyboard_context=None,
        current_reference_assets=[],
    )
    assert not readiness.ready
    assert any("scene changed" in blocker.lower() for blocker in readiness.blockers)


def test_storyboard_change_invalidates_stale_generation_state():
    service = GenerationContextService()
    context = _build_context(service, storyboard={"version": "sbv_1"})
    readiness = service.validate_generation_context(
        context=context,
        current_scene=_scene(),
        current_storyboard_context={"version": "sbv_2"},
        current_reference_assets=[],
    )
    assert not readiness.ready
    assert any("storyboard changed" in blocker.lower() for blocker in readiness.blockers)


def test_reference_change_invalidates_stale_generation_state():
    service = GenerationContextService()
    context = _build_context(service, refs=["https://cdn/ref-a.png"])
    readiness = service.validate_generation_context(
        context=context,
        current_scene=_scene(),
        current_storyboard_context=None,
        current_reference_assets=["https://cdn/ref-b.png"],
    )
    assert not readiness.ready
    assert any("references changed" in blocker.lower() for blocker in readiness.blockers)


def test_scene_mismatch_is_blocked():
    service = GenerationContextService()
    context = _build_context(service)
    readiness = service.validate_generation_context(
        context=context,
        current_scene=_scene(),
        current_storyboard_context=None,
        current_reference_assets=[],
        expected_scene_id="scn_9",
    )
    assert not readiness.ready
    assert any("Scene mismatch" in blocker for blocker in readiness.blockers)


def test_shot_mismatch_is_blocked():
    service = GenerationContextService()
    context = _build_context(service)
    readiness = service.validate_generation_context(
        context=context,
        current_scene=_scene(),
        current_storyboard_context=None,
        current_reference_assets=[],
        expected_shot_id="another_shot",
    )
    assert not readiness.ready
    assert any("Shot mismatch" in blocker for blocker in readiness.blockers)


def test_matching_state_is_ready():
    service = GenerationContextService()
    scene = _scene()
    refs = ["https://cdn/ref-a.png"]
    context = _build_context(service, scene=scene, refs=refs)
    readiness = service.validate_generation_context(
        context=context,
        current_scene=scene,
        current_storyboard_context=None,
        current_reference_assets=refs,
    )
    assert readiness.ready
    assert readiness.blockers == []


def test_fresh_render_creates_a_new_generation_context_each_time():
    service = GenerationContextService()
    scene = _scene()
    one = _build_context(service, scene=scene)
    two = _build_context(service, scene=scene)
    assert one.generation_context_id != two.generation_context_id
    assert one.created_at  # always stamped


# ── Camera provenance integrity ──────────────────────────────────────────────


def test_camera_unspecified_is_explicit_not_invented():
    service = GenerationContextService()
    instructions = service.derive_camera_instructions(creator_planning=None)
    by_dimension = {c.dimension: c for c in instructions}
    assert by_dimension["lens"].instruction_source == CAMERA_SOURCE_UNSPECIFIED
    assert by_dimension["lens"].value == ""  # no invented lens
    assert by_dimension["movement"].instruction_source == CAMERA_SOURCE_UNSPECIFIED


def test_camera_user_specified_values_are_stamped():
    service = GenerationContextService()
    instructions = service.derive_camera_instructions(
        creator_planning={"framing": "medium close-up", "camera": "slow push in"}
    )
    by_dimension = {c.dimension: c for c in instructions}
    assert by_dimension["framing"].instruction_source == CAMERA_SOURCE_USER_SPECIFIED
    assert by_dimension["camera"].value == "slow push in"


def test_storyboard_camera_plan_is_approved_not_ai():
    """Creator camera plans are APPROVED; template board values are not."""
    class _Plan:
        camera_movement = "static"
        framing = "wide"
        lens_language = ""
        composition = ""
        blocking = ""

    class _Shot:
        visual_plan = _Plan()
        version_id = "sbv_7"
        render_contract = SimpleNamespace(structured_parameters={"camera_plan": {"camera": "static", "framing": "wide"}})
        metadata: dict = {}

    service = GenerationContextService()
    instructions = service.derive_camera_instructions(storyboard_shot=_Shot())
    by_dimension = {c.dimension: c for c in instructions}
    assert by_dimension["camera"].instruction_source == CAMERA_SOURCE_APPROVED
    assert by_dimension["camera"].source_version == "sbv_7"


def test_storyboard_template_camera_without_creator_plan_is_not_approved():
    """A heuristic board visual plan carries NO creator plan provenance, so its
    values are never stamped APPROVED (P0-2: approval of the board is not
    approval of heuristic camera data)."""
    class _Plan:
        camera_movement = "static"
        framing = "wide"
        lens_language = ""
        composition = ""
        blocking = ""

    class _Shot:
        visual_plan = _Plan()
        version_id = "sbv_7"
        render_contract = SimpleNamespace(structured_parameters={})
        metadata: dict = {}

    service = GenerationContextService()
    instructions = service.derive_camera_instructions(storyboard_shot=_Shot())
    by_dimension = {c.dimension: c for c in instructions}
    assert "camera" not in by_dimension  # held out of renderable camera entirely
    assert by_dimension["framing"].instruction_source == CAMERA_SOURCE_UNSPECIFIED


def test_unapproved_ai_camera_suggestions_block_the_render():
    from app.services.generation_context_service import CameraInstruction

    service = GenerationContextService()
    context = _build_context(service)
    # Simulate a context carrying an unapproved AI suggestion (as a stale or
    # injected value would appear).
    context.camera_instructions.append(
        CameraInstruction(
            dimension="movement", value="crane up", instruction_source=CAMERA_SOURCE_AI_SUGGESTED
        )
    )
    readiness = service.validate_generation_context(
        context=context,
        current_scene=_scene(),
        current_storyboard_context=None,
        current_reference_assets=[],
    )
    assert not readiness.ready
    assert any("unapproved AI suggestion" in blocker for blocker in readiness.blockers)


def test_camera_version_changes_when_instructions_change():
    service = GenerationContextService()
    a = service.derive_camera_instructions(creator_planning={"framing": "wide"})
    b = service.derive_camera_instructions(creator_planning={"framing": "close-up"})
    assert service.camera_version(a) != service.camera_version(b)


# ── Fresh render vs historical reuse ─────────────────────────────────────────


def test_historical_context_cannot_pass_against_current_state():
    """A context minted from an OLD snapshot must not validate as current."""
    service = GenerationContextService()
    historical_context = _build_context(service, scene=_scene("old scene text"), refs=["old_ref.png"])
    readiness = service.validate_generation_context(
        context=historical_context,
        current_scene=_scene("new scene text"),
        current_storyboard_context=None,
        current_reference_assets=["new_ref.png"],
    )
    assert not readiness.ready
    assert len(readiness.blockers) >= 2  # scene + reference both stale


def test_context_to_dict_carries_the_workstream_metadata_contract():
    service = GenerationContextService()
    context = _build_context(service, storyboard={"version": "sbv_3"})
    payload = context.to_dict()
    for key in (
        "generation_context_id", "project_id", "scene_id", "shot_id",
        "scene_version", "shot_version", "storyboard_version",
        "reference_version", "camera_version", "context_fingerprint",
        "camera_instructions", "prompt_source", "created_at",
    ):
        assert key in payload


# ── Cost protection ──────────────────────────────────────────────────────────


def test_cost_limit_blocks_generation_above_configured_maximum(monkeypatch):
    from app.services.previs_service import PrevisService

    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "50")
    service = PrevisService(storage=None, renderer=None)
    # veo3.1 bills 40 credits/second → 10s = 400 credits.
    with pytest.raises(Exception) as exc:
        service._enforce_cost_limit("proj", "runway", {"duration": 10}, "veo3.1")
    assert "per-generation limit" in str(exc.value)


def test_cost_limit_allows_generation_below_maximum(monkeypatch):
    from app.services.previs_service import PrevisService

    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "500")
    service = PrevisService(storage=None, renderer=None)
    service._enforce_cost_limit("proj", "runway", {"duration": 10}, "gen4.5")  # 120 < 500: no raise


def test_cost_limit_disabled_by_default():
    from app.services.previs_service import PrevisService

    service = PrevisService(storage=None, renderer=None)
    # No limits configured → no raise even for an expensive combination.
    service._enforce_cost_limit("proj", "runway", {"duration": 30}, "seedance2_5")


def test_user_selected_model_metadata_persists_selection_mode():
    from app.services.model_router import model_router

    selection = model_router.select_model(provider="runway", requirements={}, user_model_id="gen4.5")
    assert selection.to_dict()["selection_mode"] == SELECTION_MODE_USER
