from __future__ import annotations

import pytest

from app.adapters import WanTextToVideoAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel


def _adapter(*, api_key: str | None = "test-key") -> WanTextToVideoAdapter:
    return WanTextToVideoAdapter(
        ProviderConfig(
            provider_id="wan",
            name="Alibaba Wan",
            enabled=True,
            is_simulated=False,
            api_key=api_key,
            api_endpoint="https://dashscope.example.test/api/v1",
            requires=["api_key"],
            capabilities=["video_generation", "text_to_video", "multi_shot", "audio_generation"],
        )
    )


def _job(*, parameters: dict | None = None) -> RenderJobModel:
    return RenderJobModel(
        id="job-wan-1",
        project_id="project-wan",
        shot_id="scene_001_shot_001",
        provider="wan",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="A woman waits beneath a failing station light, restrained handheld camera.",
            parameters=parameters or {},
        ),
    )


def test_wan_normalizes_supported_duration_and_frame_size() -> None:
    assert WanTextToVideoAdapter._normalize_duration(3) == 5
    assert WanTextToVideoAdapter._normalize_duration(8) == 10
    assert WanTextToVideoAdapter._normalize_duration(14) == 15
    assert WanTextToVideoAdapter._wan_size("720P", "16:9") == "1280*720"
    assert WanTextToVideoAdapter._wan_size("1080P", "9:16") == "1080*1920"
    assert WanTextToVideoAdapter._wan_size("720P", "1:1") == "1280*720"


def test_wan_builds_documented_dashscope_payload() -> None:
    adapter = _adapter()

    payload = adapter._build_submit_payload(
        job=_job(),
        resolution="720P",
        duration=5,
        ratio="16:9",
        seed=42,
        params={"prompt_extend": True, "shot_type": "multi", "watermark": False},
    )

    assert payload == {
        "model": "wan2.6-t2v",
        "input": {
            "prompt": "A woman waits beneath a failing station light, restrained handheld camera."
        },
        "parameters": {
            "size": "1280*720",
            "duration": 5,
            "prompt_extend": True,
            "shot_type": "multi",
            "watermark": False,
            "seed": 42,
        },
    }


@pytest.mark.asyncio
async def test_wan_submits_polls_and_preserves_provider_audio(monkeypatch) -> None:
    adapter = _adapter()
    requests: list[tuple[str, str, dict | None]] = []

    async def fake_request(method: str, path: str, payload: dict | None = None) -> dict:
        requests.append((method, path, payload))
        if method == "POST":
            return {"output": {"task_id": "wan-task-1"}}
        return {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn.example.test/video.mp4?Expires=1&Signature=secret",
            }
        }

    async def fake_download(*, job: RenderJobModel, hosted_video_url: str) -> tuple[str, dict]:
        assert hosted_video_url.startswith("https://cdn.example.test/video.mp4")
        return (
            "/outputs/renders/project-wan/job-wan-1_wan.mp4",
            {"audio_stream_count": 1, "provider_audio_preserved": True},
        )

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)
    monkeypatch.setattr(adapter, "_download_and_strip_audio", fake_download)

    result = await adapter.submit_job(
        _job(parameters={"duration_seconds": 5, "resolution": "720P", "ratio": "16:9"})
    )

    assert result.status == "complete"
    assert result.provider_job_id == "wan-task-1"
    assert result.output_payload is not None
    assert result.output_payload.asset_url.endswith("job-wan-1_wan.mp4")
    normalized = result.output_payload.metadata["provider_response_normalized"]
    assert normalized["provider"] == "wan"
    assert normalized["metadata"]["model"] == "wan2.6-t2v"
    assert normalized["metadata"]["provider_mode"] == "hosted_api"
    assert normalized["metadata"]["media_download"]["provider_audio_preserved"] is True
    assert normalized["metadata"]["raw_response"]["output"]["video_url"] == (
        "<redacted temporary provider URL>"
    )
    assert requests[0][0:2] == (
        "POST",
        "/services/aigc/video-generation/video-synthesis",
    )
    assert requests[0][2]["parameters"]["size"] == "1280*720"


@pytest.mark.asyncio
async def test_wan_missing_key_fails_without_external_request(monkeypatch) -> None:
    adapter = _adapter(api_key=None)
    called = False

    async def unexpected_request(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider request should not run")

    monkeypatch.setattr(adapter, "_happyhorse_request", unexpected_request)

    result = await adapter.submit_job(_job())

    assert result.status == "failed"
    assert result.error_message == "Missing DashScope API key"
    assert called is False
    normalized = result.output_payload.metadata["provider_response_normalized"]
    assert normalized["metadata"]["error"]["error_type"] == "missing_api_key"


@pytest.mark.asyncio
async def test_wan_surfaces_nested_task_failure(monkeypatch) -> None:
    adapter = _adapter()

    async def fake_request(method: str, path: str, payload: dict | None = None) -> dict:
        if method == "POST":
            return {"output": {"task_id": "wan-task-failed"}}
        return {
            "output": {
                "task_status": "FAILED",
                "code": "QuotaExceeded",
                "message": "No remaining quota",
            }
        }

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)

    result = await adapter.submit_job(_job())

    assert result.status == "failed"
    assert result.error_message == "QuotaExceeded: No remaining quota"
    normalized = result.output_payload.metadata["provider_response_normalized"]
    assert normalized["metadata"]["error"]["error_type"] == "task_failed"
