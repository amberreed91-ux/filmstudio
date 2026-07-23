from __future__ import annotations

import shutil
import subprocess

import pytest

from app.adapters import HappyHorseAdapter
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
