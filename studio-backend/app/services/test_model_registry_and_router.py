"""Regression tests: centralized model registry + bounded model routing.

Covers the workstream's required proofs:
- Auto model selection respects model capabilities (no unsupported pick).
- User-selected models are never silently replaced.
- Unsupported reference configurations are blocked.
- Unsupported duration/resolution requirements are blocked.
- Selection reasons are filmmaker-readable; no invented scores.
- Router output is a recommendation record only (no canonical mutation).
"""
from __future__ import annotations

import pytest

from app.services.model_registry import (
    AVAILABILITY_DISABLED,
    ModelRegistry,
    model_registry,
)
from app.services.model_router import (
    SELECTION_MODE_AUTO,
    SELECTION_MODE_USER,
    ModelRouter,
)


def _req(**overrides):
    base = {
        "generation_mode": "text_to_video",
        "reference_count": 0,
        "duration_seconds": 5,
    }
    base.update(overrides)
    return base


# ── Registry integrity ───────────────────────────────────────────────────────


def test_registry_only_contains_models_verified_against_runway_docs():
    models = model_registry.list_models()
    ids = {m.model_id for m in models}
    # The retired hardcoded allowlist accepted these; the verified registry must not.
    assert "gen6" not in ids
    assert "gen3" not in ids
    assert "gen4.5" in ids


def test_registry_allowed_model_ids_excludes_retired_models():
    allowed = model_registry.allowed_model_ids("runway")
    assert "gen6" not in allowed
    assert "gen3" not in allowed
    assert "gen4.5" in allowed


def test_registry_adapters_validation_rejects_nonexistent_model():
    from app.services.render import _validate_model_override

    with pytest.raises(ValueError) as exc:
        _validate_model_override("runway", {"model": "gen6"})
    assert "gen6" in str(exc.value)


def test_registry_accepts_newly_supported_runway_models():
    # gen4_turbo exists in the current Runway Dev API (image-only).
    from app.services.render import _validate_model_override

    _validate_model_override("runway", {"model": "gen4_turbo"})


def test_registry_set_availability_disables_without_deleting():
    registry = ModelRegistry()
    registry.set_availability("gen4.5", AVAILABILITY_DISABLED)
    model = registry.get_model("gen4.5")
    assert model is not None
    assert model.availability_status == AVAILABILITY_DISABLED
    assert "gen4.5" not in registry.allowed_model_ids("runway")


def test_unknown_model_lookup_fails_closed():
    with pytest.raises(ValueError):
        model_registry.require_model("definitely-not-a-model")


# ── Router: auto selection respects capabilities ─────────────────────────────


def test_auto_select_respects_generation_mode():
    # gen4_turbo is image-only: a text-to-video shot must never pick it.
    selection = ModelRouter().select_model(provider="runway", requirements=_req(generation_mode="text_to_video"))
    assert selection.model_id != "gen4_turbo"
    assert selection.selection_mode == SELECTION_MODE_AUTO


def test_auto_select_favors_models_with_reference_budget_for_multi_reference_shots():
    selection = ModelRouter().select_model(
        provider="runway",
        requirements=_req(reference_count=6, reference_types=["character_image", "setting_image"]),
    )
    model = model_registry.get_model(selection.model_id)
    assert model is not None
    assert model.maximum_reference_count >= 6
    assert "references" in selection.selection_reason.lower()


def test_auto_select_single_reference_shots_toward_low_cost():
    selection = ModelRouter().select_model(provider="runway", requirements=_req(reference_count=0))
    assert selection.estimated_cost_credits > 0


def test_audio_requirement_surfaces_warning_for_non_audio_models():
    # audio=True is a soft preference (Studio has its own audio pipeline);
    # the router warns rather than fabricating a constraint.
    selection = ModelRouter().select_model(provider="runway", requirements=_req(audio=True, prefer_audio=True))
    chosen = model_registry.get_model(selection.model_id)
    if not chosen.audio_support:
        assert any("audio" in w.lower() for w in selection.warnings)


def test_auto_selection_reason_is_filmmaker_readable_without_scores():
    selection = ModelRouter().select_model(
        provider="runway",
        requirements=_req(reference_count=4, reference_types=["character_image", "setting_image"]),
    )
    reason = selection.selection_reason
    assert reason
    assert "%" not in reason
    assert "/10" not in reason
    assert "score" not in reason.lower()


def test_estimated_cost_matches_published_per_second_rate():
    selection = ModelRouter().select_model(provider="runway", requirements=_req(duration_seconds=10))
    model = model_registry.get_model(selection.model_id)
    assert selection.estimated_cost_credits == model.credits_per_second * 10


# ── Router: user selection is authoritative ──────────────────────────────────


def test_user_selected_model_is_returned_unchanged():
    selection = ModelRouter().select_model(
        provider="runway", requirements=_req(), user_model_id="gen4.5"
    )
    assert selection.model_id == "gen4.5"
    assert selection.selection_mode == SELECTION_MODE_USER
    assert "will not replace" in selection.selection_reason


def test_user_selected_incompatible_model_is_blocked_not_swapped():
    # h3_max cannot render 30s: a user selecting it for a 30s shot is blocked
    # with the capability conflict named — never silently downgraded.
    with pytest.raises(ValueError) as exc:
        ModelRouter().select_model(
            provider="runway", requirements=_req(duration_seconds=30), user_model_id="h3_max"
        )
    message = str(exc.value)
    assert "h3_max" in message
    assert "cannot satisfy" in message


def test_user_selected_unknown_model_is_rejected():
    with pytest.raises(ValueError):
        ModelRouter().select_model(provider="runway", requirements=_req(), user_model_id="gen6")


# ── Reference / duration / resolution capability gates ───────────────────────


def test_unsupported_reference_count_blocks_every_candidate():
    with pytest.raises(ValueError) as exc:
        # Every Runway-registered model has a bounded reference budget; 50
        # exceeds all of them.
        ModelRouter().select_model(provider="runway", requirements=_req(reference_count=50))
    assert "No runway model satisfies" in str(exc.value)


def test_last_frame_requirement_blocks_models_without_keyframe_support():
    blockers, _ = model_registry.check_requirements(
        model_registry.require_model("gen4.5"), _req(last_frame=True)
    )
    assert any("last-frame" in blocker for blocker in blockers)


def test_unsupported_duration_blocks_known_models():
    blockers, _ = model_registry.check_requirements(
        model_registry.require_model("gen4.5"), _req(duration_seconds=30)
    )
    assert any("cannot render 30s" in blocker for blocker in blockers)


def test_unsupported_resolution_blocks_known_models():
    blockers, _ = model_registry.check_requirements(
        model_registry.require_model("gemini_omni_flash"), _req(resolution="1080p")
    )
    assert any("1080p" in blocker for blocker in blockers)


# ── Router never mutates canonical truth ─────────────────────────────────────


def test_router_output_is_a_recommendation_record_only():
    selection = ModelRouter().select_model(provider="runway", requirements=_req())
    payload = selection.to_dict()
    assert set(payload) == {
        "model_id", "provider", "selection_mode", "selection_reason",
        "estimated_cost_credits", "warnings",
    }


def test_registry_reports_models_for_unknown_provider_as_empty():
    assert model_registry.models_for_provider("kling") == []


# ── Creator-selected capability enforcement at the service boundary ──────────
#
# A concrete creator model that cannot satisfy the shot's requirements must
# fail closed at job creation (before persistence) and at submission (against
# the persisted payload, catching post-creation mutation) — never silently
# downgraded. Compatible selections record requested/validated/effective
# identity on the job.


def test_creator_selected_incompatible_model_blocked_at_creation():
    from app.services.render import RenderService

    service = RenderService()
    with pytest.raises(ValueError, match="cannot satisfy"):
        service.create_job(
            project_id="proj-model-cap",
            shot_id="scene_001_shot_001",
            provider="runway",
            prompt="Maya pauses in a quiet hallway long enough to need thirty seconds of screen time.",
            parameters={"model": "h3_max", "duration": 30},
        )


def test_creator_selected_compatible_model_records_identity():
    from app.services.render import RenderService

    service = RenderService()
    job = service.create_job(
        project_id="proj-model-cap-compatible",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="Maya pauses in a quiet hallway, medium shot, practical light.",
        parameters={"model": "gen4.5", "duration": 5},
    )
    identity = job.metadata.get("creator_model_identity")
    assert identity is not None
    assert identity["requested"] == "gen4.5"
    assert identity["validated"] == "USER_SELECTED"
    assert identity["effective"] == "gen4.5"


def test_creator_selected_capability_rechecked_at_submission():
    import asyncio

    from app.services.render import RenderService

    service = RenderService()
    job = service.create_job(
        project_id="proj-model-cap-recheck",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="Maya pauses in a quiet hallway, medium shot, practical light.",
        parameters={"model": "gen4.5", "duration": 5},
    )
    # Mutate the persisted payload after creation: the submit-time recheck
    # must fail closed against the persisted values, not the creation-time ones.
    job.input_payload.parameters["duration"] = 30
    job.input_payload.parameters["model"] = "h3_max"
    with pytest.raises(ValueError, match="cannot satisfy"):
        asyncio.run(service.submit_job(job.id))
    assert job.status == "failed"
    assert "cannot satisfy" in (job.error_message or "")


def test_router_adapter_fails_success_without_task_output_association(monkeypatch):
    import asyncio

    from app.adapters import RunwayRouterAdapter
    from app.services.providers import runway_router_provider
    import importlib.util
    from pathlib import Path

    fixture_path = Path(__file__).resolve().parents[2] / "tests" / "test_generation_contract_remediation.py"
    spec = importlib.util.spec_from_file_location("router_output_identity_fixtures", fixture_path)
    assert spec is not None and spec.loader is not None
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)

    job = fixtures._job_with_frozen_contract()
    storage = fixtures._bind_router_execution_authority(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    monkeypatch.setattr(
        runway_router_provider,
        "submit_runway_router_video_render",
        lambda *_args, **_kwargs: {
            "status": "success",
            "url": "https://cdn.test/output.mp4",
            "meta": {
                "runway_task_id": "submitted-task",
                "output_identity": {
                    "provider_task_id": "different-task",
                    "output_url": "https://cdn.test/output.mp4",
                    "association_source": "runway_router_polled_task",
                },
            },
        },
    )

    result = asyncio.run(RunwayRouterAdapter(fixtures._provider_config())._submit_job_after_authorization(job))

    assert result.status == "failed"
    assert result.output_payload.metadata["provider_response_normalized"]["metadata"]["reason"] == "provider_output_identity_mismatch"
    assert result.provider_job_id == "submitted-task"
    assert result.metadata["router_execution"]["provider_output_identity"]["provider_task_id"] == "different-task"
    assert result.metadata["router_execution"]["provider_output_identity"]["output_url"] == "https://cdn.test/output.mp4"
    assert result.output_payload.asset_url == ""
    assert asyncio.run(RunwayRouterAdapter(fixtures._provider_config()).fetch_outputs(result)) == []


def test_router_path_still_rejects_concrete_creator_model():
    from app.services.render import _validate_model_override

    with pytest.raises(ValueError, match="Model Router selects the eligible model"):
        _validate_model_override("runway_router", {"model": "gen4.5"})
