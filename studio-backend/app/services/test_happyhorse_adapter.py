from __future__ import annotations

import base64
import shutil
import subprocess

import pytest

from app.adapters import HappyHorseAdapter, HappyHorseR2VAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.models.consistency import ConsistencyPayload, ReferenceAsset


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg and ffprobe are required for audio-strip verification",
)
def test_happyhorse_strip_audio_removes_audio_stream(tmp_path) -> None:
    raw = tmp_path / "raw_with_audio.mp4"
    stripped = tmp_path / "stripped.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(raw),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    before = HappyHorseAdapter._ffprobe_streams_sync(raw)
    assert any(stream.get("codec_type") == "audio" for stream in before)

    HappyHorseAdapter._strip_audio_sync(raw, stripped)
    after = HappyHorseAdapter._ffprobe_streams_sync(stripped)

    assert any(stream.get("codec_type") == "video" for stream in after)
    assert not any(stream.get("codec_type") == "audio" for stream in after)


def test_happyhorse_normalizes_documented_parameter_ranges() -> None:
    assert HappyHorseAdapter._normalize_resolution("480P") == "720P"
    assert HappyHorseAdapter._normalize_resolution("1080p") == "1080P"
    assert HappyHorseAdapter._normalize_duration(1) == 3
    assert HappyHorseAdapter._normalize_duration(20) == 15
    assert HappyHorseAdapter._normalize_ratio("21:9") == "21:9"


def test_happyhorse_redacts_temporary_signed_urls_from_metadata() -> None:
    signed_url = (
        "https://dashscope.example.test/video.mp4?"
        "Expires=1784917270&OSSAccessKeyId=test&Signature=secret"
    )

    redacted = HappyHorseAdapter._redact_temporary_provider_urls(
        {
            "output": {
                "video_url": signed_url,
                "thumbnail_url": "https://cdn.example.test/thumbnail.jpg",
            },
            "nested": [{"url": signed_url}],
        }
    )

    assert redacted["output"]["video_url"] == "<redacted temporary provider URL>"
    assert redacted["nested"][0]["url"] == "<redacted temporary provider URL>"
    assert redacted["output"]["thumbnail_url"] == "https://cdn.example.test/thumbnail.jpg"


@pytest.mark.asyncio
async def test_happyhorse_merges_consistency_payload_into_prompt(monkeypatch):
    captured_payloads = []
    adapter = HappyHorseAdapter(
        ProviderConfig(
            provider_id="happyhorse",
            name="HappyHorse",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation"],
        )
    )
    job = RenderJobModel(
        id="job-happyhorse-consistency",
        project_id="project_1",
        shot_id="scene_001_shot_001",
        provider="happyhorse",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="Maya and Dre hold a tense two-shot.",
            parameters={"duration": 3, "ratio": "16:9"},
            consistency_payload=ConsistencyPayload(
                project_id="project_1",
                refs=[
                    ReferenceAsset(
                        ref_id="style-ref",
                        kind="style",
                        image_url="https://example.test/style.png",
                        project_id="project_1",
                    )
                ],
                weights={"style-ref": 0.15},
                mode="identity_lock",
                fallback_text={
                    "style-ref": "preserve project visual style reference"
                },
            ),
        ),
    )

    async def fake_request(method, path, payload=None):
        if method == "POST":
            captured_payloads.append(payload)
            return {"output": {"task_id": "task-1"}}
        return {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn.example.test/video.mp4",
            }
        }

    async def fake_strip_audio(*, job, hosted_video_url):
        return "/outputs/renders/project_1/stripped.mp4", {"stripped": True}

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)
    monkeypatch.setattr(adapter, "_download_and_strip_audio", fake_strip_audio)

    result = await adapter.submit_job(job)

    assert result.status == "complete"
    outgoing_prompt = captured_payloads[0]["input"]["prompt"]
    assert "Maya and Dre hold a tense two-shot." in outgoing_prompt
    assert "preserve project visual style reference" in outgoing_prompt


@pytest.mark.asyncio
async def test_happyhorse_t2v_character_reference_degrades_to_text_only(monkeypatch):
    captured_payloads = []
    adapter = HappyHorseAdapter(
        ProviderConfig(
            provider_id="happyhorse",
            name="HappyHorse",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation", "text_to_video"],
        )
    )
    job = RenderJobModel(
        id="job-happyhorse-t2v-character-fallback",
        project_id="project_1",
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Maya crosses the hallway.",
            parameters={"duration": 3, "ratio": "16:9"},
            consistency_payload=ConsistencyPayload(
                project_id="project_1",
                refs=[
                    ReferenceAsset(
                        ref_id="charlock:maya",
                        kind="character_full",
                        image_url="https://cdn.example.test/maya-reference.jpg",
                        project_id="project_1",
                    )
                ],
                weights={"charlock:maya": 1.0},
                mode="identity_lock",
                fallback_text={
                    "charlock:maya": "Use locked reference for Maya; preserve visual identity."
                },
            ),
        ),
    )

    async def fake_request(method, path, payload=None):
        if method == "POST":
            captured_payloads.append(payload)
            return {"output": {"task_id": "task-t2v"}}
        return {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn.example.test/video.mp4",
            }
        }

    async def fake_strip_audio(*, job, hosted_video_url):
        return "/outputs/renders/project_1/t2v-stripped.mp4", {"stripped": True}

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)
    monkeypatch.setattr(adapter, "_download_and_strip_audio", fake_strip_audio)

    result = await adapter.submit_job(job)

    assert result.status == "complete"
    payload = captured_payloads[0]
    assert payload["model"] == "happyhorse-1.1-t2v"
    assert "media" not in payload["input"]
    assert "Use locked reference for Maya" in payload["input"]["prompt"]
    assert result.metadata["character_reference_degraded_to_text"] is True
    assert result.metadata["provider_payload_metadata"]["references_injected"] is False
    assert result.metadata["provider_payload_metadata"]["references_degraded_to_prompt"] is True


@pytest.mark.asyncio
async def test_happyhorse_r2v_payload_uses_media_and_image_prompt_references(monkeypatch):
    captured_payloads = []
    adapter = HappyHorseR2VAdapter(
        ProviderConfig(
            provider_id="happyhorse-r2v",
            name="HappyHorse Reference-to-Video",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation", "reference_to_video", "image_conditioning"],
        )
    )
    job = RenderJobModel(
        id="job-happyhorse-r2v",
        project_id="project_1",
        shot_id="scene_001_shot_002",
        provider="happyhorse-r2v",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Maya crosses the hallway.",
            parameters={"duration": 3, "ratio": "16:9", "resolution": "720P"},
            consistency_payload=ConsistencyPayload(
                project_id="project_1",
                refs=[
                    ReferenceAsset(
                        ref_id="charlock:maya",
                        kind="character_full",
                        image_url="https://cdn.example.test/maya-reference.jpg",
                        source_shot_id="scene_001_shot_001",
                        project_id="project_1",
                    )
                ],
                weights={"charlock:maya": 1.0},
                mode="identity_lock",
                fallback_text={
                    "charlock:maya": "Use locked reference for Maya; preserve face and wardrobe."
                },
            ),
        ),
    )

    async def fake_request(method, path, payload=None):
        if method == "POST":
            captured_payloads.append(payload)
            return {"output": {"task_id": "task-r2v"}}
        return {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn.example.test/video.mp4",
            }
        }

    async def fake_strip_audio(*, job, hosted_video_url):
        return "/outputs/renders/project_1/r2v-stripped.mp4", {"stripped": True}

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)
    monkeypatch.setattr(adapter, "_download_and_strip_audio", fake_strip_audio)

    result = await adapter.submit_job(job)

    assert result.status == "complete"
    payload = captured_payloads[0]
    assert payload["model"] == "happyhorse-1.1-r2v"
    assert payload["input"]["media"] == [
        {"type": "reference_image", "url": "https://cdn.example.test/maya-reference.jpg"}
    ]
    assert "[Image 1]" in payload["input"]["prompt"]
    assert "Maya" in payload["input"]["prompt"]
    assert result.metadata["provider_payload_metadata"]["references_injected"] is True
    assert result.metadata["provider_payload_metadata"]["reference_count"] == 1


@pytest.mark.asyncio
async def test_happyhorse_r2v_embeds_local_previs_reference(monkeypatch, tmp_path):
    reference_bytes = b"local-previs-image"
    reference_path = tmp_path / "project_1" / "maya-reference.png"
    reference_path.parent.mkdir()
    reference_path.write_bytes(reference_bytes)
    monkeypatch.setattr(
        HappyHorseR2VAdapter,
        "_previs_assets_root",
        staticmethod(lambda: tmp_path),
    )

    captured_payloads = []
    adapter = HappyHorseR2VAdapter(
        ProviderConfig(
            provider_id="happyhorse-r2v",
            name="HappyHorse Reference-to-Video",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation", "reference_to_video"],
        )
    )
    job = RenderJobModel(
        id="job-happyhorse-local-reference",
        project_id="project_1",
        shot_id="scene_001_shot_002",
        provider="happyhorse-r2v",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Maya crosses the hallway.",
            parameters={"duration": 3, "ratio": "16:9"},
            consistency_payload=ConsistencyPayload(
                project_id="project_1",
                refs=[
                    ReferenceAsset(
                        ref_id="charlock:maya",
                        kind="character_full",
                        image_url="/previs-assets/project_1/maya-reference.png",
                        project_id="project_1",
                    )
                ],
                weights={"charlock:maya": 1.0},
                mode="identity_lock",
                fallback_text={"charlock:maya": "Preserve Maya's identity."},
            ),
        ),
    )

    async def fake_request(method, path, payload=None):
        if method == "POST":
            captured_payloads.append(payload)
            return {"output": {"task_id": "task-local-reference"}}
        return {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn.example.test/video.mp4",
            }
        }

    async def fake_strip_audio(*, job, hosted_video_url):
        return "/outputs/renders/project_1/r2v-stripped.mp4", {"stripped": True}

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)
    monkeypatch.setattr(adapter, "_download_and_strip_audio", fake_strip_audio)

    result = await adapter.submit_job(job)

    assert result.status == "complete"
    data_url = captured_payloads[0]["input"]["media"][0]["url"]
    assert data_url.startswith("data:image/png;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == reference_bytes


@pytest.mark.asyncio
async def test_happyhorse_r2v_embeds_completed_reference_frame(monkeypatch, tmp_path):
    reference_bytes = b"completed-reference-frame"
    outputs_root = tmp_path / "outputs"
    reference_path = outputs_root / "references" / "project_1" / "maya-reference.jpg"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(reference_bytes)
    monkeypatch.setattr(
        HappyHorseR2VAdapter,
        "_previs_assets_root",
        staticmethod(lambda: tmp_path / "previs"),
    )
    monkeypatch.setattr(
        HappyHorseR2VAdapter,
        "_outputs_root",
        staticmethod(lambda: outputs_root),
    )

    data_url = HappyHorseR2VAdapter._provider_reference_url(
        "/outputs/references/project_1/maya-reference.jpg"
    )

    assert data_url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == reference_bytes


def test_happyhorse_r2v_deduplicates_shared_reference_images():
    adapter = HappyHorseR2VAdapter(
        ProviderConfig(
            provider_id="happyhorse-r2v",
            name="HappyHorse Reference-to-Video",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation", "reference_to_video"],
        )
    )
    shared_url = "https://cdn.example.test/shared-storyboard.png"
    job = RenderJobModel(
        id="job-happyhorse-shared-reference",
        project_id="project_1",
        shot_id="scene_001_shot_002",
        provider="happyhorse-r2v",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Maya speaks with Mom.",
            consistency_payload=ConsistencyPayload(
                project_id="project_1",
                refs=[
                    ReferenceAsset(
                        ref_id="charlock:maya",
                        kind="character_full",
                        image_url=shared_url,
                        project_id="project_1",
                    ),
                    ReferenceAsset(
                        ref_id="charlock:mom",
                        kind="character_full",
                        image_url=shared_url,
                        project_id="project_1",
                    ),
                ],
                weights={"charlock:maya": 1.0, "charlock:mom": 1.0},
                mode="identity_lock",
                fallback_text={
                    "charlock:maya": "Preserve Maya's identity.",
                    "charlock:mom": "Preserve Mom's identity.",
                },
            ),
        ),
    )

    payload = adapter._build_submit_payload(
        job=job,
        resolution="720P",
        duration=5,
        ratio="16:9",
        seed=None,
        params={},
    )

    assert payload["input"]["media"] == [
        {"type": "reference_image", "url": shared_url}
    ]
    assert "Preserve Maya's identity." in payload["input"]["prompt"]
    assert "Preserve Mom's identity." in payload["input"]["prompt"]


@pytest.mark.asyncio
async def test_happyhorse_surfaces_nested_task_failure_message(monkeypatch):
    adapter = HappyHorseAdapter(
        ProviderConfig(
            provider_id="happyhorse",
            name="HappyHorse",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation"],
        )
    )
    job = RenderJobModel(
        id="job-happyhorse-provider-failure",
        project_id="project_1",
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Maya crosses the hallway.",
            parameters={"duration": 3},
        ),
    )

    async def fake_request(method, path, payload=None):
        if method == "POST":
            return {"output": {"task_id": "task-provider-failure"}}
        return {
            "output": {
                "task_status": "FAILED",
                "code": "InvalidParameter",
                "message": "Failed to download the reference image",
            }
        }

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)

    result = await adapter.submit_job(job)

    assert result.status == "failed"
    assert result.error_message == "InvalidParameter: Failed to download the reference image"


@pytest.mark.asyncio
async def test_happyhorse_accepts_duration_seconds_alias(monkeypatch):
    captured_payloads = []
    adapter = HappyHorseAdapter(
        ProviderConfig(
            provider_id="happyhorse",
            name="HappyHorse",
            enabled=True,
            is_simulated=False,
            api_key="test-key",
            api_endpoint="https://dashscope.example.test",
            requires=["api_key"],
            capabilities=["video_generation", "text_to_video"],
        )
    )
    job = RenderJobModel(
        id="job-happyhorse-duration-alias",
        project_id="project_1",
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Maya crosses the hallway.",
            parameters={"duration_seconds": 8, "ratio": "16:9", "resolution": "1080p"},
        ),
    )

    async def fake_request(method, path, payload=None):
        if method == "POST":
            captured_payloads.append(payload)
            return {"output": {"task_id": "task-duration"}}
        return {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn.example.test/video.mp4",
            }
        }

    async def fake_strip_audio(*, job, hosted_video_url):
        return "/outputs/renders/project_1/duration-stripped.mp4", {"stripped": True}

    monkeypatch.setattr(adapter, "_happyhorse_request", fake_request)
    monkeypatch.setattr(adapter, "_download_and_strip_audio", fake_strip_audio)

    result = await adapter.submit_job(job)

    assert result.status == "complete"
    assert captured_payloads[0]["parameters"]["duration"] == 8
    assert captured_payloads[0]["parameters"]["resolution"] == "1080P"
