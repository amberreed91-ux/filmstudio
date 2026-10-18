from __future__ import annotations

import pytest

from app.adapters import (
    ADAPTER_REGISTRY,
    HappyHorseAdapter,
    HappyHorseR2VAdapter,
    RunwayAdapter,
    WanTextToVideoAdapter,
)
from app.services.render import RenderService
from app.services.scene_production_pipeline_service import SceneProductionPipelineService


def test_adapter_registry_includes_direct_runway_compatibility_and_router() -> None:
    from app.adapters import RunwayRouterAdapter

    assert "runway" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["runway"] is RunwayAdapter
    assert "runway_router" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["runway_router"] is RunwayRouterAdapter
    assert "happyhorse" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["happyhorse"] is HappyHorseAdapter
    assert "happyhorse-r2v" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["happyhorse-r2v"] is HappyHorseR2VAdapter
    assert "wan" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["wan"] is WanTextToVideoAdapter
    assert "openrouter" not in ADAPTER_REGISTRY
    assert "openrouter-video" not in ADAPTER_REGISTRY


def test_render_service_provider_configs_include_runway() -> None:
    service = RenderService()
    providers = set(service._provider_configs.keys())
    assert "runway" in providers
    assert "happyhorse" in providers
    assert "happyhorse-r2v" in providers
    assert "wan" in providers
    assert "local" in providers
    assert "simulated" in providers
    assert "openrouter" not in providers
    assert "openrouter-video" not in providers


def test_default_provider_selection_is_preserved_for_operator_alias(monkeypatch) -> None:
    monkeypatch.delenv("RENDER_VIDEO_PROVIDER", raising=False)
    monkeypatch.setattr("app.services.render.get_settings", lambda: type("SettingsStub", (), {"render_video_provider": "runway"})())
    service = RenderService()
    assert service.get_default_provider() == "runway"


@pytest.mark.parametrize(
    ("selected", "expected"),
    [
        ("runway", "runway_router"),
        ("runway_router", "runway_router"),
        ("simulated", "simulated"),
        ("happyhorse", "happyhorse"),
    ],
)
def test_scene_generation_resolves_runway_to_router_without_changing_other_providers(selected, expected):
    pipeline = SceneProductionPipelineService()
    assert pipeline._resolve_generation_provider(selected) == expected


def test_scene_generation_default_runway_selection_resolves_to_router():
    from types import SimpleNamespace

    pipeline = SceneProductionPipelineService()
    pipeline.render_service = SimpleNamespace(get_default_provider=lambda: "runway")
    assert pipeline._resolve_generation_provider(None) == "runway_router"


@pytest.mark.asyncio
async def test_legacy_direct_runway_job_cannot_reach_an_adapter(monkeypatch) -> None:
    from app.models import RenderJobInput, RenderJobModel

    service = RenderService()
    job = RenderJobModel(
        id="legacy-direct-runway-job",
        project_id="synthetic-project",
        shot_id="scene_001_shot_001",
        provider="runway",
        input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="legacy"),
    )
    service._jobs[job.id] = job
    calls = []
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args: calls.append("adapter"))

    result = await service.submit_job(job.id)

    assert result.status == "failed"
    assert result.metadata["provider_boundary_failure"]["reason"] == "direct_runway_submission_disabled"
    assert calls == []


def test_retired_openrouter_default_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_VIDEO_PROVIDER", "openrouter")
    service = RenderService()
    with pytest.raises(ValueError, match="retired"):
        service.get_default_provider()


@pytest.mark.parametrize("provider", ["openrouter", "openrouter-video"])
def test_retired_openrouter_video_provider_cannot_be_created_or_configured(provider: str) -> None:
    service = RenderService()
    assert service.get_provider_config(provider) is None
    with pytest.raises(ValueError, match="retired"):
        service.create_job(project_id="proj-1", shot_id="shot-1", provider=provider, prompt="smoke")

    from app.models import ProviderConfig

    with pytest.raises(ValueError, match="retired"):
        service.set_provider_config(
            ProviderConfig(provider_id=provider, name="retired", enabled=True, is_simulated=False)
        )


def test_legacy_video_submit_stub_rejects_retired_openrouter():
    from app.services.providers.video_provider import submit_video_render

    result = submit_video_render(
        {"scene_id": "scene-1", "shot_id": "shot-1"},
        {
            "video_provider_enabled": True,
            "video_provider_name": "openrouter",
            "video_provider_api_key": "",
        },
    )
    assert result["status"] == "failed"
    assert result["meta"]["reason"] == "provider_retired"
    assert "retired" in result["error"]


def test_create_job_preserves_direct_runway_provider_for_compatibility() -> None:
    service = RenderService()
    job = service.create_job(
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        prompt="smoke",
    )
    assert job.provider == "runway"


def test_unsupported_default_provider_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_VIDEO_PROVIDER", "not-a-provider")
    with pytest.raises(ValueError, match="Unsupported RENDER_VIDEO_PROVIDER"):
        RenderService().get_default_provider()


def test_invalid_provider_still_returns_clear_error() -> None:
    service = RenderService()
    try:
        service.create_job(
            project_id="proj-1",
            shot_id="shot-1",
            provider="unknown-provider",
            prompt="bad",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        text = str(exc)
        assert "Unknown provider" in text
        assert "Available providers" in text


def test_smoke_test_path_inputs_can_create_runway_compatibility_job() -> None:
    service = RenderService()
    job = service.create_job(
        project_id="smoke-project",
        shot_id="smoke-shot",
        provider="runway",
        prompt="A lone woman walking through neon rain at night, cinematic, moody",
    )
    assert job.provider == "runway"
    assert job.status == "pending"


def test_clear_prompt_contradiction_returns_needs_review_job() -> None:
    service = RenderService()

    job = service.create_job(
        project_id="proj-contradiction",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt=(
            "A tight close-up of Maya, full body visible head-to-toe, "
            "standing in daylight at night."
        ),
        parameters={"skip_character_injection": True},
    )

    assert job.status == "needs_review"
    assert "contradictory" in (job.error_message or "")
    contradictions = job.metadata["prompt_contradictions"]
    codes = {row["code"] for row in contradictions}
    assert "framing_closeup_full_body" in codes
    assert "lighting_day_night" in codes
    phases = {
        row["phase"]: row
        for row in job.metadata["zero_touch_pipeline"]["phases"]
    }
    assert phases["prepare_provider_request"]["status"] == "needs_review"
    assert phases["render"]["status"] == "skipped"
    assert phases["retry"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_needs_review_job_is_not_submitted_to_provider(monkeypatch) -> None:
    service = RenderService()
    job = service.create_job(
        project_id="proj-contradiction",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="Static camera on an empty room with multiple visible characters in a rapid tracking shot.",
        parameters={"skip_character_injection": True},
    )

    called = False

    async def _unexpected_submit(_job):
        nonlocal called
        called = True
        return _job

    class _Adapter:
        submit_job = _unexpected_submit

    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _Adapter())
    submitted = await service.submit_job(job.id)

    assert submitted.status == "needs_review"
    assert called is False


def test_non_contradictory_prompt_remains_pending() -> None:
    service = RenderService()

    job = service.create_job(
        project_id="proj-safe",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="A close-up of Maya in nighttime practical light, static camera, tense but controlled.",
        parameters={"skip_character_injection": True},
    )

    assert job.status == "pending"
    assert not (job.metadata or {}).get("prompt_contradictions")


def test_invalid_runway_model_override_is_rejected_before_submission() -> None:
    service = RenderService()

    try:
        service.create_job(
            project_id="proj-1",
            shot_id="shot-1",
            provider="runway",
            prompt="A cinematic shot with enough detail for the provider request.",
            parameters={"model": "not-a-real-runway-model"},
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unsupported Runway model" in str(exc)


def test_invalid_happyhorse_model_override_is_rejected_before_submission() -> None:
    service = RenderService()

    try:
        service.create_job(
            project_id="proj-1",
            shot_id="shot-1",
            provider="happyhorse",
            prompt="A cinematic shot with enough detail for the provider request.",
            parameters={"model": "happyhorse-1.1-r2v"},
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "does not support this model override" in str(exc)


def test_invalid_wan_model_override_is_rejected_before_submission() -> None:
    service = RenderService()

    with pytest.raises(ValueError, match="Wan text-to-video"):
        service.create_job(
            project_id="proj-1",
            shot_id="shot-1",
            provider="wan",
            prompt="A cinematic shot with enough detail for the provider request.",
            parameters={"model": "wan-not-real"},
        )


@pytest.mark.asyncio
async def test_missing_runway_api_key_records_permanent_provider_failure(monkeypatch) -> None:
    monkeypatch.setattr("app.services.render.validate_generation_payload", lambda **_kwargs: None)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("RENDER_PROVIDER_TEST_MODE", raising=False)
    service = RenderService()

    job = service.create_job(
        project_id="proj-missing-key",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="Maya pauses in a quiet hallway, medium shot, practical light.",
    )
    submitted = await service.submit_job(job.id)

    assert submitted.status == "failed"
    assert submitted.metadata["provider_boundary_failure"]["reason"] == "direct_runway_submission_disabled"
    assert submitted.metadata["provider_boundary_failure"]["required_provider"] == "runway_router"
    assert "frozen contract" in submitted.error_message
