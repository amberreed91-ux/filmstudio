"""Tests for the OpenRouter vision adherence scorer."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import app.config as app_config
from app.services.vision.openrouter_vision_service import OpenRouterVisionService
from app.services.vision.qwen_vision_service import QwenVisionService


def _settings(**overrides):
    base = {
        "openrouter_api_key": "test-key",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_missing_model_id_names_the_discovery_command(monkeypatch):
    """A missing model id must fail loudly rather than default to a guess.

    Two constants copied from prose in this project pointed at things that did
    not exist. The error text has to tell the caller where a real id comes from.
    """
    monkeypatch.setattr(app_config, "get_settings", lambda: _settings())
    with pytest.raises(RuntimeError) as exc:
        OpenRouterVisionService(model="")
    message = str(exc.value)
    assert "ADHERENCE_VISION_MODEL" in message
    assert "/models" in message


def test_missing_api_key_is_explicit(monkeypatch):
    monkeypatch.setattr(app_config, "get_settings", lambda: _settings(openrouter_api_key=""))
    with pytest.raises(RuntimeError) as exc:
        OpenRouterVisionService(model="vendor/some-model")
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_scoring_prompt_is_shared_with_the_qwen_path(monkeypatch):
    """Both providers must score with byte-identical prompt text.

    If the wording diverges, scores from the two providers stop being
    comparable — and a threshold calibrated under one wording silently stops
    meaning the same thing under the other.
    """
    monkeypatch.setattr(app_config, "get_settings", lambda: _settings())
    service = OpenRouterVisionService(model="vendor/some-model")
    kwargs = dict(
        expected_character="MAYA, grey work jacket",
        expected_action="sets the kettle down",
        expected_camera="slow push in",
        expected_lighting="single practical, warm",
        expected_environment="cramped kitchen at dusk",
    )
    assert service._build_scoring_prompt(**kwargs) == QwenVisionService._build_scoring_prompt(**kwargs)


@pytest.mark.asyncio
async def test_json_mode_rejection_falls_back_and_is_recorded(monkeypatch, tmp_path):
    """A model that refuses response_format still scores — visibly, not silently."""
    monkeypatch.setattr(app_config, "get_settings", lambda: _settings())
    service = OpenRouterVisionService(model="vendor/some-model")

    payload = {
        "dimensions": {
            name: {"score": 80, "evidence": "e", "expected": "x", "observed": "o"}
            for name in (
                "character_state",
                "action",
                "camera",
                "lighting",
                "environment_persistence",
            )
        },
        "temporal_drift": {"start_score": 80, "end_score": 78},
    }

    calls: list[bool] = []

    async def fake_create(**kwargs):
        used_json_mode = "response_format" in kwargs
        calls.append(used_json_mode)
        if used_json_mode:
            raise ValueError("response_format is not supported by this model")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )

    monkeypatch.setattr(service._client.chat.completions, "create", fake_create)

    frames = []
    for index in range(3):
        frame = tmp_path / f"frame_{index}.jpg"
        frame.write_bytes(b"\xff\xd8\xff\xdb not-a-real-jpeg")
        frames.append(str(frame))

    result = await service.score_adherence(
        frames=frames,
        expected_character="MAYA",
        expected_action="turns",
        expected_camera="static",
        expected_lighting="dim",
        expected_environment="kitchen",
    )

    assert calls == [True, False], "should try json mode first, then retry without it"
    assert service.json_mode_supported is False
    assert result["dimensions"]["action"]["score"] == 80.0
