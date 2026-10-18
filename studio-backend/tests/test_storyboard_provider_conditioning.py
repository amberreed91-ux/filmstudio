"""Request-boundary regressions; these do not claim generated visual quality."""
import pytest
from app.models import RenderJobInput, RenderJobModel
from app.services.prompt_budget_service import prompt_policy, cost
from app.services.render import _provider_model_for_job


def test_openrouter_video_specific_prompt_budget_is_retired():
    assert _provider_model_for_job("runway", {}) == "gen4.5"
    assert prompt_policy("runway", "gen4.5")[0] == 512
    assert prompt_policy("openrouter", "alibaba/happyhorse-1.1")[0] == 512
    assert cost("夜", "openrouter-video", "alibaba/happyhorse-1.1") == len("夜")


def test_historical_openrouter_job_record_still_parses():
    job = RenderJobModel(
        id="historical-openrouter-job",
        project_id="p",
        shot_id="s",
        provider="openrouter-video",
        status="complete",
        created_at="2026-09-05",
        updated_at="2026-09-05",
        input_payload=RenderJobInput(shot_id="s", prompt="Previously generated."),
    )
    assert job.provider == "openrouter-video"
    assert job.status == "complete"


def test_retired_openrouter_video_adapter_cannot_be_resolved():
    from app.adapters import ADAPTER_REGISTRY, get_adapter
    from app.models import ProviderConfig

    for provider in ("openrouter", "openrouter-video"):
        assert provider not in ADAPTER_REGISTRY
        with pytest.raises(ValueError, match="Unknown provider adapter"):
            get_adapter(provider, ProviderConfig(provider_id=provider, name="retired", enabled=True, is_simulated=False))


@pytest.mark.asyncio
async def test_legacy_adapter_instance_rejects_direct_submission():
    from app.adapters import OpenRouterVideoAdapter
    from app.models import ProviderConfig

    adapter = OpenRouterVideoAdapter(
        ProviderConfig(provider_id="openrouter-video", name="retired", enabled=True, is_simulated=False)
    )
    job = RenderJobModel(
        id="retired-direct-submit",
        project_id="p",
        shot_id="s",
        provider="openrouter-video",
        input_payload=RenderJobInput(shot_id="s", prompt="must not submit"),
    )
    with pytest.raises(ValueError, match="retired"):
        await adapter.submit_job(job)


def test_historical_model_identifier_uses_conservative_budget(monkeypatch):
    monkeypatch.delenv("OPENROUTER_VIDEO_MODEL", raising=False)
    assert _provider_model_for_job("openrouter-video", {}) == "openrouter-video"
    assert prompt_policy("openrouter-video", "alibaba/happyhorse-1.1")[0] == 512
    assert cost("夜", "openrouter", "alibaba/happyhorse-1.1") == len("夜")


def test_short_creator_prompt_survives_automatic_and_structured_planning(monkeypatch):
    from app.services import render
    from types import SimpleNamespace
    monkeypatch.setattr(render, "project_store", SimpleNamespace(get_project=lambda _: {"execution_summary": {"scenes": [{"scene_id": "scene_001", "text": "A wide view of the city."}]}}))
    service = render.RenderService()
    job = service.create_job(project_id="p", shot_id="scene_001_shot_001", provider="runway",
        prompt="Close on her closed left hand.", parameters={"preserve_shot_prompt": True, "structured_prompt": True, "shot_planning": {"blocking": "She opens her hand."}})
    assert "Close on her closed left hand." in job.input_payload.prompt
    assert "A wide view of the city" not in job.input_payload.prompt


def test_unsupported_provider_cannot_silently_ignore_the_board():
    from app.services.render import RenderService
    from app.services.stability import ValidationError
    with pytest.raises(ValidationError, match="first frame"):
        RenderService().create_job(project_id="p", shot_id="s", provider="wan", prompt="Keep the composition.", parameters={"storyboard_frame_url": "https://media.test/frame.png"})
