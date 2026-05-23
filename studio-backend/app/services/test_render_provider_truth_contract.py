from app.services.render import RenderService


def _runway(statuses):
    for row in statuses:
        if row.provider_id == "runway":
            return row
    raise AssertionError("runway provider not found")


def test_provider_status_reports_missing_api_key_without_runway_key(monkeypatch):
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("RENDER_PROVIDER_TEST_MODE", raising=False)

    service = RenderService()
    runway = _runway(service.list_providers())

    assert runway.provider_key == "runway"
    assert runway.enabled is True
    assert runway.ready_for_hosted_generation is False
    assert runway.provider_mode == "unavailable"
    assert "api_key" in runway.missing_requirements
    assert runway.is_mock is False


def test_provider_status_exposes_mock_success_mode(monkeypatch):
    monkeypatch.setenv("RENDER_PROVIDER_TEST_MODE", "mock_success")
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)

    service = RenderService()
    runway = _runway(service.list_providers())

    assert runway.provider_mode == "mock_success"
    assert runway.ready_for_hosted_generation is False
    assert runway.is_mock is True
    assert "Mock Success Mode" in runway.display_label


def test_provider_status_reports_hosted_mode_when_key_present(monkeypatch):
    monkeypatch.setenv("RUNWAY_API_KEY", "rk_live_1234")
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)
    monkeypatch.setenv("RENDER_PROVIDER_TEST_MODE", "false")

    service = RenderService()
    runway = _runway(service.list_providers())

    assert runway.provider_mode == "hosted_api"
    assert runway.ready_for_hosted_generation is True
    assert runway.is_mock is False
    assert runway.missing_requirements == []
