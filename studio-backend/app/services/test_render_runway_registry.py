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


def test_adapter_registry_includes_runway() -> None:
    assert "runway" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["runway"] is RunwayAdapter
    assert "happyhorse" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["happyhorse"] is HappyHorseAdapter
    assert "happyhorse-r2v" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["happyhorse-r2v"] is HappyHorseR2VAdapter
    assert "wan" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["wan"] is WanTextToVideoAdapter


def test_render_service_provider_configs_include_runway() -> None:
    service = RenderService()
    providers = set(service._provider_configs.keys())
    assert "runway" in providers
    assert "happyhorse" in providers
    assert "happyhorse-r2v" in providers
    assert "wan" in providers
    assert "local" in providers
    assert "simulated" in providers


def test_default_provider_is_happyhorse(monkeypatch) -> None:
    monkeypatch.delenv("RENDER_VIDEO_PROVIDER", raising=False)
    service = RenderService()
    assert service.get_default_provider() == "happyhorse"


def test_default_provider_can_be_overridden_to_runway(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_VIDEO_PROVIDER", "runway")
    service = RenderService()
    assert service.get_default_provider() == "runway"


def test_create_job_accepts_runway_provider() -> None:
    service = RenderService()
    job = service.create_job(
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        prompt="smoke",
    )
    assert job.provider == "runway"


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


def test_smoke_test_path_inputs_can_create_runway_job() -> None:
    service = RenderService()

    # Mirrors the smoke script query parameters used by /api/f51/studio/render/jobs
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
    assert submitted.error_message == "Missing Runway API key"
    failure = submitted.metadata["provider_failure"]
    assert failure["category"] == "permanent"
    assert failure["error_type"] == "missing_api_key"
    assert failure["retryable"] is False
    retry_phase = next(
        row
        for row in submitted.metadata["zero_touch_pipeline"]["phases"]
        if row["phase"] == "retry"
    )
    assert retry_phase["status"] == "skipped"
    assert retry_phase["error_type"] == "missing_api_key"
