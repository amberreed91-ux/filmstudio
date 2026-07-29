from __future__ import annotations

import asyncio
import certifi
import pytest

from app.adapters import RunwayAdapter, normalize_video_provider_response, ALLOWED_RUNWAY_MODELS
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.models.consistency import ConsistencyPayload, ReferenceAsset
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


def test_runway_can_be_selected_as_default_provider(monkeypatch):
    monkeypatch.setenv("RENDER_VIDEO_PROVIDER", "runway")
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
    assert job.status == "failed"
    assert job.error_message is not None
    assert "timed out" in job.error_message
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
    assert "Runway API unauthorized:" in (job.error_message or "")
    assert "invalid api key" in (job.error_message or "")
    error = job.output_payload.metadata["provider_response_normalized"]["metadata"]["error"]
    assert error["error_type"] == "invalid_api_key"
    assert error["status_code"] == 401


def test_runway_http_error_message_includes_provider_body(monkeypatch):
    adapter = RunwayAdapter(_cfg(api_key="rk_live"))

    async def _fake_request(method, path, payload=None, params=None):
        from app.adapters import RunwayAPIError
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        raise RunwayAPIError(
            status_code=400,
            endpoint=path,
            response_headers={"content-type": "application/json"},
            response_body="Validation of body failed: ratio must be one of 1280:768, 768:1280",
        )

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = asyncio.run(adapter.submit_job(_job()))
    assert job.status == "failed"
    assert "Runway API error 400:" in (job.error_message or "")
    assert "ratio must be one of" in (job.error_message or "")


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
    job.input_payload.parameters["ratio"] = "16:9"
    calls: list[tuple[str, str]] = []

    async def _fake_request(method, path, payload=None, params=None):
        calls.append((method, path))
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            assert path == "/v1/image_to_video"
            assert payload["promptImage"] == "https://example.com/image.jpg"
            assert payload["ratio"] == "1280:768"
            return {"id": "rw-123", "status": "queued"}
        return {"status": "completed", "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "complete"
    assert calls == [("GET", "/v1/organization"), ("POST", "/v1/image_to_video"), ("GET", "/v1/tasks/rw-123")]


def test_runway_text_request_keeps_text_to_video_ratio(monkeypatch):
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.parameters["ratio"] = "16:9"
    captured_payload: dict = {}

    async def _fake_request(method, path, payload=None, params=None):
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            assert path == "/v1/text_to_video"
            captured_payload.update(payload or {})
            return {"id": "rw-123", "status": "queued"}
        return {"status": "completed", "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "complete"
    assert captured_payload["ratio"] == "1280:720"


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


def test_runway_submit_job_with_consistency_payload_overrides_image_text(monkeypatch):
    """A job with a ConsistencyPayload gets promptImage from the highest-weight
    character_full ref (not referenceAssets[0]) and promptText is extended with
    fallback_text from remaining refs."""
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.referenceAssets = ["https://old-path/image.jpg"]
    job.input_payload.consistency_payload = ConsistencyPayload(
        project_id="proj-1",
        refs=[
            ReferenceAsset(ref_id="face", kind="character_face",
                           image_url="https://example.com/face.jpg",
                           project_id="proj-1"),
            ReferenceAsset(ref_id="full", kind="character_full",
                           image_url="https://example.com/full.jpg",
                           project_id="proj-1"),
            ReferenceAsset(ref_id="env", kind="environment",
                           image_url="https://example.com/env.jpg",
                           project_id="proj-1"),
        ],
        mode="identity_lock",
        weights={"full": 1.0, "face": 0.3, "env": 0.1},
        fallback_text={
            "face": "close-up facial reference",
            "env": "outdoor lighting, golden hour",
        },
    )
    calls: list[tuple[str, str, dict | None]] = []

    async def _fake_request(method, path, payload=None, params=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            assert path == "/v1/image_to_video", \
                f"expected image_to_video, got {path}"
            return {"id": "rw-cp-1", "status": "queued"}
        return {"status": "completed",
                "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "complete"

    post_entries = [
        (m, p, pl) for m, p, pl in calls
        if m == "POST"
    ]
    assert len(post_entries) == 1
    _method, _path, payload = post_entries[0]
    assert payload["promptImage"] == "https://example.com/full.jpg"
    assert "close-up facial reference" in payload["promptText"]
    assert "outdoor lighting, golden hour" in payload["promptText"]
    assert "must NOT appear" not in payload["promptText"]


def test_runway_submit_job_without_consistency_payload_unchanged(monkeypatch):
    """Zero regression: a job without consistency_payload behaves exactly
    as before — referenceAssets[0] → promptImage, prompt is untouched."""
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.referenceAssets = ["https://legacy/image.jpg"]
    calls: list[tuple[str, str, dict | None]] = []

    async def _fake_request(method, path, payload=None, params=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            assert path == "/v1/image_to_video"
            return {"id": "rw-legacy-1", "status": "queued"}
        return {"status": "completed",
                "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "complete"

    post_entries = [
        (m, p, pl) for m, p, pl in calls if m == "POST"
    ]
    assert len(post_entries) == 1
    _method, _path, payload = post_entries[0]
    assert payload["promptImage"] == "https://legacy/image.jpg"
    assert payload["promptText"] == "A cinematic dolly shot"


def test_runway_model_per_request_override_via_parameters(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.parameters["model"] = "gen6"
    assert adapter._runway_model(job) == "gen6"


def test_runway_model_accepts_supported_hosted_override(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.parameters["model"] = "gemini_omni_flash"
    assert adapter._runway_model(job) == "gemini_omni_flash"


def test_runway_classifies_credit_error_independent_of_status_code():
    assert (
        RunwayAdapter._classify_runway_error(
            400,
            '{"error":"You do not have enough credits to run this task."}',
        )
        == "missing_credits"
    )


def test_runway_classifies_unavailable_model_as_permanent():
    assert (
        RunwayAdapter._classify_runway_error(
            403,
            '{"error":"Model variant gen3a_turbo is not available"}',
        )
        == "unsupported_model"
    )


def test_runway_model_per_request_override_falls_back_to_env_when_no_parameter(monkeypatch):
    monkeypatch.setenv("RUNWAY_MODEL", "veo3")
    adapter = RunwayAdapter(_cfg())
    job = _job()
    assert "model" not in job.input_payload.parameters
    assert adapter._runway_model(job) == "veo3"


def test_runway_model_per_request_override_falls_back_to_default_when_no_parameter_no_env(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    job = _job()
    assert "model" not in job.input_payload.parameters
    assert adapter._runway_model(job) == "gen4.5"


def test_runway_model_without_job_arg_still_works(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    assert adapter._runway_model() == "gen4.5"


def test_runway_model_override_reaches_payload(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.parameters["model"] = "gen3"
    captured_payload: dict = {}

    async def _fake_request(method, path, payload=None, params=None):
        if method == "GET" and path == "/v1/organization":
            return {"id": "org_123"}
        if method == "POST":
            captured_payload.update(payload or {})
            return {"id": "rw-model-test", "status": "queued"}
        return {"status": "completed", "output": [{"url": "https://cdn.runway/video.mp4"}]}

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "complete"
    assert captured_payload["model"] == "gen3"


def test_runway_model_rejects_invalid_per_request_override(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.parameters["model"] = "bogus-model"
    with pytest.raises(ValueError) as exc_info:
        adapter._runway_model(job)
    message = str(exc_info.value)
    assert "bogus-model" in message
    for allowed in ALLOWED_RUNWAY_MODELS:
        assert allowed in message


def test_runway_model_invalid_override_fails_submit_without_provider_call(monkeypatch):
    monkeypatch.delenv("RUNWAY_MODEL", raising=False)
    adapter = RunwayAdapter(_cfg())
    job = _job()
    job.input_payload.parameters["model"] = "bogus-model"
    provider_was_called = {"hit": False}

    async def _fail_if_called(method, path, payload=None, params=None):
        provider_was_called["hit"] = True
        raise AssertionError("provider call must not happen for an invalid model override")

    monkeypatch.setattr(adapter, "_runway_request", _fail_if_called)
    monkeypatch.setattr(adapter, "_is_local_or_test_env", lambda: True)
    result = asyncio.run(adapter.submit_job(job))
    assert result.status == "failed"
    assert provider_was_called["hit"] is False
    assert "bogus-model" in (result.error_message or "")
    assert "Allowed models" in (result.error_message or "")
