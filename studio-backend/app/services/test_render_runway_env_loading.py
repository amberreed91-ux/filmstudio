from __future__ import annotations

from app.services.render import RenderService
from app.services.providers.config import get_provider_config


def test_render_service_reads_runwayml_api_secret_first(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "key_secret_1234")
    monkeypatch.setenv("RUNWAY_API_KEY", "key_test_1234")
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)

    service = RenderService()
    runway = service.get_provider_config("runway")

    assert runway is not None
    assert runway.api_key == "key_secret_1234"


def test_render_service_falls_back_to_runway_api_key(monkeypatch) -> None:
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.setenv("RUNWAY_API_KEY", "key_test_1234")
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)

    service = RenderService()
    runway = service.get_provider_config("runway")

    assert runway is not None
    assert runway.api_key == "key_test_1234"


def test_render_service_missing_runway_api_key_results_in_none(monkeypatch) -> None:
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)

    service = RenderService()
    runway = service.get_provider_config("runway")

    assert runway is not None
    assert runway.api_key is None


def test_provider_config_prefers_runwayml_api_secret(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "key_secret_6789")
    monkeypatch.setenv("RUNWAY_API_KEY", "key_fallback_1234")
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)

    config = get_provider_config()
    assert config["video_provider_api_key"] == "key_secret_6789"


def test_provider_config_falls_back_to_runway_api_key(monkeypatch) -> None:
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.setenv("RUNWAY_API_KEY", "key_fallback_1234")
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)

    config = get_provider_config()
    assert config["video_provider_api_key"] == "key_fallback_1234"
