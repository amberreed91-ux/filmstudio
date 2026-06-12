from __future__ import annotations

import asyncio
import certifi

from app.adapters import RunwayAdapter, normalize_video_provider_response
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services.render import RenderService


def _job() -> RenderJobModel:
    return RenderJobModel(
        id="job-1",
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="shot-1",
            prompt="A cinematic dolly shot",
            referenceAssets=[],
            parameters={},
        ),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _cfg(api_key: str | None = "rk_live", api_endpoint: str | None = "https://api.runwayml.com") -> ProviderConfig:
    return ProviderConfig(
        provider_id="runway",
        name="Runway",
        enabled=True,
        is_simulated=False,
        api_key=api_key,
        api_endpoint=api_endpoint,
        requires=["api_key"],
        capabilities=["video_generation", "image_to_video"],
    )


def test_runway_is_default_provider_when_enabled():
    service = RenderService()
    assert service.get_default_provider() == "runway"


def test_runway_model_defaults_to_gen45(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_model() == "gen4.5"


def test_runway_model_respects_env_override(monkeypatch):
    monkeypatch.setenv("RUNWAY_MODEL", "veo3")
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_model() == "veo3"


def test_normalize_video_provider_response_shape():
    normalized = normalize_video_provider_response(
        {"status": "completed", "video_url": "https://cdn/runway.mp4", "metadata": {"seed": 7}},
        provider="runway",
    )
    assert set(normalized.keys()) == {
        "provider",
        "task",
        "status",
        "message",
        "video_url",
        "preview_url",
        "metadata",
    }
    assert normalized["provider"] == "runway"
    assert normalized["task"] == "video_generation"
    assert normalized["status"] == "completed"
    assert normalized["video_url"] == "https://cdn/runway.mp4"


def test_runway_missing_api_key_fails_gracefully():
    adapter = RunwayAdapter(_cfg(api_key=None))
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    assert job.error_message == "Missing Runway API key"


def test_runway_make_request_sends_bearer_and_version_headers(monkeypatch):
    adapter = RunwayAdapter(_cfg(api_key="rk_live_1234"))
    captured: dict = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        async def json(self):
            return {"ok": True}

    class _FakeContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeSession:
        def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers or {}
            return _FakeContext()

    async def _fake_get_session():
        return _FakeSession()

    monkeypatch.setattr(adapter, "_get_session", _fake_get_session)
    asyncio.run(
        adapter._make_request(
            "POST",
            "/v1/text_to_video",
            headers=adapter._runway_headers(),
            json={"prompt": "hello"},
        )
    )

    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer rk_live_1234"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Runway-Version"] == "2024-11-06"


def test_runway_successful_mocked_response(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    calls: list[tuple[str, str]] = []

    async def _fake_request(method, path, payload=None, params=None):
        calls.append((method, path))
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            assert path == "/v1/text_to_video"
            assert payload["model"] == adapter._runway_model()
            assert payload["promptText"] == "A cinematic dolly shot"
            assert payload["ratio"] == "1280:720"
            assert "promptImage" not in payload
            return {"id": "rw-123", "status": "queued"}
        return {"status": "completed", "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert calls == [("GET", "/v1/organization"), ("POST", "/v1/text_to_video"), ("GET", "/v1/tasks/rw-123")]
    assert job.status == "complete"
    assert job.provider_job_id == "rw-123"
    assert job.output_payload is not None
    assert job.output_payload.asset_url == "https://cdn.runway/video.mp4"
    normalized = job.output_payload.metadata["provider_response_normalized"]
    assert normalized["provider"] == "runway"
    assert normalized["status"] == "completed"
    assert normalized["metadata"]["provider_mode"] == "hosted_api"


def test_runway_failed_task_returns_structured_error(monkeypatch):
    adapter = RunwayAdapter(_cfg())

    async def _fake_request(method, path, payload=None, params=None):
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            return {"id": "rw-123", "status": "queued"}
        return {"status": "failed", "message": "safety filter"}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    assert "safety filter" in (job.error_message or "")
    error = job.output_payload.metadata["provider_response_normalized"]["metadata"]["error"]
    assert error["error_type"] == "task_failed"
    assert "safety filter" in error["message"]


def test_runway_timeout_is_failed(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    monkeypatch.setenv("RUNWAY_TIMEOUT_SECONDS", "1")

    poll_calls = {"count": 0}
    async def _fake_request(method, path, payload=None, params=None):
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            return {"id": "rw-123", "status": "queued"}
        poll_calls["count"] += 1
        return {"status": "processing"}

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "rendering"
    assert job.error_message is None
    assert job.provider_job_id == "rw-123"
    assert poll_calls["count"] > 0
    timeout_meta = job.output_payload.metadata["provider_response_normalized"]["metadata"]["timeout"]
    assert timeout_meta["error_type"] == "timeout"


def test_runway_timeout_default_is_300_seconds(monkeypatch):
    monkeypatch.delenv("RUNWAY_TIMEOUT_SECONDS", raising=False)
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_timeout_seconds() == 300


def test_runway_timeout_env_override_is_honored(monkeypatch):
    monkeypatch.setenv("RUNWAY_TIMEOUT_SECONDS", "180")
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_timeout_seconds() == 180


def test_runway_missing_video_url_is_failed(monkeypatch):
    adapter = RunwayAdapter(_cfg())

    async def _fake_request(method, path, payload=None, params=None):
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            return {"id": "rw-123", "status": "queued"}
        return {"status": "completed", "output": []}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    assert "without video_url" in (job.error_message or "")
    error = job.output_payload.metadata["provider_response_normalized"]["metadata"]["error"]
    assert error["error_type"] == "missing_video_url"


def test_runway_unauthorized_api_key(monkeypatch):
    adapter = RunwayAdapter(_cfg(api_key="rk_bad"))

    async def _fake_request(method, path, payload=None, params=None):
        from app.adapters import RunwayAPIError
        raise RunwayAPIError(
            status_code=401,
            endpoint=path,
            response_headers={"content-type": "application/json"},
            response_body='{"error":{"code":"UNAUTHORIZED","message":"invalid api key"}}',
        )

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    assert job.error_message == "Runway API unauthorized"
    error = job.output_payload.metadata["provider_response_normalized"]["metadata"]["error"]
    assert error["error_type"] == "invalid_api_key"
    assert error["status_code"] == 401


def test_runway_error_classification_variants() -> None:
    adapter = RunwayAdapter(_cfg())
    assert adapter._classify_runway_error(401, "key revoked") == "revoked_key"
    assert adapter._classify_runway_error(401, "billing credit required") == "missing_credits"
    assert adapter._classify_runway_error(401, "organization not found") == "missing_org_access"
    assert adapter._classify_runway_error(400, "invalid model") == "unsupported_model"
    assert adapter._classify_runway_error(400, "Validation of body failed") == "invalid_payload"


def test_runway_image_request_uses_image_to_video_and_includes_prompt_image(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.referenceAssets = ["https://example.com/image.jpg"]
    calls: list[tuple[str, str]] = []

    async def _fake_request(method, path, payload=None, params=None):
        calls.append((method, path))
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            assert path == "/v1/image_to_video"
            assert payload["promptImage"] == "https://example.com/image.jpg"
            return {"id": "rw-123", "status": "queued"}
        return {"status": "completed", "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "complete"
    assert calls == [("GET", "/v1/organization"), ("POST", "/v1/image_to_video"), ("GET", "/v1/tasks/rw-123")]


def test_runway_long_running_task_completes_without_early_failure(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    poll_count = {"n": 0}

    async def _fake_request(method, path, payload=None, params=None):
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            return {"id": "rw-123"}
        poll_count["n"] += 1
        if poll_count["n"] < 3:
            return {"status": "RUNNING"}
        return {"status": "SUCCEEDED", "output": ["https://cdn.runway/video.mp4"]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert poll_count["n"] >= 3
    assert job.status == "complete"
    assert job.output_payload.asset_url == "https://cdn.runway/video.mp4"


def test_get_job_status_extracts_completed_output(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.provider_job_id = "rw-123"
    job.status = "rendering"

    async def _fake_request(method, path, payload=None, params=None):
        return {"status": "SUCCEEDED", "output": ["https://cdn.runway/video.mp4"]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    updated = asyncio.run(adapter.get_job_status(job))
    assert updated.status == "complete"
    assert updated.output_payload is not None
    assert updated.output_payload.asset_url == "https://cdn.runway/video.mp4"


def test_runway_ssl_verify_defaults_to_secure(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    monkeypatch.delenv("RUNWAY_ALLOW_INSECURE_SSL", raising=False)
    monkeypatch.delenv("RUNWAY_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    ssl_option = adapter._resolve_ssl_option()
    assert ssl_option is not False


def test_runway_ssl_uses_custom_ca_bundle(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    monkeypatch.setenv("RUNWAY_CA_BUNDLE", certifi.where())
    ssl_option = adapter._resolve_ssl_option()
    assert ssl_option is not False


def test_insecure_ssl_override_rejected_outside_local_test(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RUNWAY_ALLOW_INSECURE_SSL", "true")
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    assert "only allowed when APP_ENV is local or test" in (job.error_message or "")


def test_ssl_failure_classified_as_ssl_verification_error(monkeypatch):
    adapter = RunwayAdapter(_cfg(api_key="rk_live"))
    monkeypatch.setenv("APP_ENV", "local")

    async def _fake_runway_request(_method, _path, payload=None, params=None):
        raise OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    monkeypatch.setattr(adapter, "_runway_request", _fake_runway_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    error = job.output_payload.metadata["provider_response_normalized"]["metadata"]["error"]
    assert error["error_type"] == "ssl_verification_error"


def test_render_provider_test_mode_mock_success_returns_output_url(monkeypatch):
    adapter = RunwayAdapter(_cfg(api_key="rk_live"))
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("RENDER_PROVIDER_TEST_MODE", "mock_success")
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "complete"
    assert isinstance(job.provider_job_id, str) and job.provider_job_id.startswith("mock-task-")
    assert job.output_payload is not None
    assert str(job.output_payload.asset_url) == "/outputs/mock-video/sample.mp4"


def test_render_provider_test_mode_mock_success_rejected_in_production(monkeypatch):
    adapter = RunwayAdapter(_cfg(api_key="rk_live"))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RENDER_PROVIDER_TEST_MODE", "mock_success")
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    error = job.output_payload.metadata["provider_response_normalized"]["metadata"]["error"]
    assert error["error_type"] == "test_mode_not_allowed"
