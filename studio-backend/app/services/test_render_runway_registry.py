from __future__ import annotations

from app.adapters import ADAPTER_REGISTRY, RunwayAdapter
from app.services.render import RenderService


def test_adapter_registry_includes_runway() -> None:
    assert "runway" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["runway"] is RunwayAdapter


def test_render_service_provider_configs_include_runway() -> None:
    service = RenderService()
    providers = set(service._provider_configs.keys())
    assert "runway" in providers
    assert "local" in providers
    assert "simulated" in providers


def test_create_job_accepts_runway_provider() -> None:
    service = RenderService()
    job = service.create_job(
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        prompt="smoke",
    )
    # Runway is always overridden to local/simulated for this build
    assert job.provider == "local"


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
    # Runway is always overridden to local/simulated for this build
    assert job.provider == "local"
    assert job.status == "pending"
