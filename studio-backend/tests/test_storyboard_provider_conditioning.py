"""Request-boundary regressions; these do not claim generated visual quality."""
import pytest
from app.adapters import OpenRouterVideoAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services.prompt_budget_service import prompt_policy, cost
from app.services.render import _provider_model_for_job


def job_with_board():
    return RenderJobModel(id="j", project_id="p", shot_id="s", provider="openrouter-video", status="pending",
        created_at="2026-09-05", updated_at="2026-09-05", input_payload=RenderJobInput(
            shot_id="s", prompt="Her hand stays closed.",
            referenceAssets=["https://media.test/board.png", "https://media.test/prop.png"],
            parameters={"storyboard_frame_url": "https://media.test/board.png"}))


def adapter():
    return OpenRouterVideoAdapter(ProviderConfig(provider_id="openrouter-video", name="OpenRouter", enabled=True, is_simulated=False))


def test_board_is_a_first_frame_and_other_assets_remain_references():
    job = job_with_board()
    body = adapter()._build_openrouter_body(job, resolution="720p", duration=8, ratio="16:9", seed=0)
    assert body["frame_images"] == [{"type": "image_url", "image_url": {"url": "https://media.test/board.png"}, "frame_type": "first_frame"}]
    assert body["input_references"] == [{"type": "image_url", "image_url": {"url": "https://media.test/prop.png"}}]
    assert body["seed"] == 0


def test_provider_alias_uses_the_same_budget_and_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_VIDEO_MODEL", raising=False)
    assert _provider_model_for_job("openrouter-video", {}) == "alibaba/happyhorse-1.1"
    assert prompt_policy("openrouter-video", "alibaba/happyhorse-1.1") == prompt_policy("openrouter", "alibaba/happyhorse-1.1")
    assert cost("夜", "openrouter-video", "alibaba/happyhorse-1.1") == 2


def test_identity_reference_does_not_replace_the_board():
    job = job_with_board()
    job.input_payload.consistency_payload = ConsistencyPayload(project_id="p", mode="identity_lock", refs=[ReferenceAsset(ref_id="character", project_id="p", kind="character_full", image_url="https://media.test/character.png")])
    body = adapter()._build_openrouter_body(job, resolution="720p", duration=8, ratio="16:9", seed=None)
    assert body["frame_images"][0]["image_url"]["url"].endswith("board.png")
    assert body["input_references"][-1]["image_url"]["url"].endswith("character.png")


def test_local_board_is_encoded_and_missing_board_does_not_degrade(tmp_path, monkeypatch):
    from app.adapters import HappyHorseR2VAdapter
    monkeypatch.setattr(HappyHorseR2VAdapter, "_previs_assets_root", staticmethod(lambda: tmp_path))
    (tmp_path / "frame.png").write_bytes(b"image-fixture")
    job = job_with_board()
    job.input_payload.parameters["storyboard_frame_url"] = "/previs-assets/frame.png"
    body = adapter()._build_openrouter_body(job, resolution="720p", duration=8, ratio="16:9", seed=None)
    assert body["frame_images"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    (tmp_path / "frame.png").unlink()
    with pytest.raises(ValueError, match="not found"):
        adapter()._build_openrouter_body(job, resolution="720p", duration=8, ratio="16:9", seed=None)


def test_short_creator_prompt_survives_automatic_and_structured_planning(monkeypatch):
    from app.services import render
    from types import SimpleNamespace
    monkeypatch.setattr(render, "project_store", SimpleNamespace(get_project=lambda _: {"execution_summary": {"scenes": [{"scene_id": "scene_001", "text": "A wide view of the city."}]}}))
    service = render.RenderService()
    job = service.create_job(project_id="p", shot_id="scene_001_shot_001", provider="openrouter-video",
        prompt="Close on her closed left hand.", parameters={"preserve_shot_prompt": True, "structured_prompt": True, "shot_planning": {"blocking": "She opens her hand."}})
    assert "Close on her closed left hand." in job.input_payload.prompt
    assert "A wide view of the city" not in job.input_payload.prompt


def test_unsupported_provider_cannot_silently_ignore_the_board():
    from app.services.render import RenderService
    from app.services.stability import ValidationError
    with pytest.raises(ValidationError, match="first frame"):
        RenderService().create_job(project_id="p", shot_id="s", provider="wan", prompt="Keep the composition.", parameters={"storyboard_frame_url": "https://media.test/frame.png"})


@pytest.mark.parametrize("parameters, message", [({"duration": 20}, "duration"), ({"resolution": "480p"}, "resolution"), ({"ratio": "9:16"}, "ratio")])
def test_requested_settings_cannot_be_silently_normalized(parameters, message):
    job = job_with_board()
    job.input_payload.parameters.update(parameters)
    with pytest.raises(ValueError, match=message):
        adapter()._build_openrouter_body(job, resolution="720p", duration=15, ratio="16:9", seed=0)
