from __future__ import annotations

from app.adapters import RunwayAdapter
from app.models import ProviderConfig


def _cfg() -> ProviderConfig:
    return ProviderConfig(
        provider_id="runway",
        name="Runway",
        enabled=True,
        is_simulated=False,
        api_key="rk_live",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "image_to_video"],
    )


def test_runway_model_defaults_to_gen45(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_model() == "gen4.5"


def test_runway_model_respects_env_override(monkeypatch):
    monkeypatch.setenv("RUNWAY_MODEL", "veo3")
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_model() == "veo3"
