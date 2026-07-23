"""Tests for audio-overrun handling in merge_audio_onto_video.

Reproduces the original bug: when dialogue audio is longer than the rendered
video clip (the normal case — e.g. 5.04s video with 10.22s dialogue), the old
``-shortest`` flag silently truncated the audio.

These tests confirm:
  - "error" mode fails loudly (no silent truncation, no output file)
  - "freeze_last_frame" mode preserves the full audio duration via tpad
  - bitrate is sample-rate-aware (not the old impossible 192k for mono 22050)
  - "trim_audio" is a clear not-implemented error
  - normal case (audio shorter than video) still works
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.audio_pipeline_service import AudioPipelineService, TrackStatus


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _ffmpeg_available(), reason="ffmpeg/ffprobe not available"
)


def _make_test_video(path: Path, duration: float = 3.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size=320x240:rate=24",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True, text=True, timeout=60,
        check=True,
    )


def _make_test_audio(
    path: Path, duration: float = 6.0, sample_rate: int = 22050, channels: int = 1
) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration}:sample_rate={sample_rate}",
            "-ac", str(channels),
            "-ar", str(sample_rate),
            str(path),
        ],
        capture_output=True, text=True, timeout=60,
        check=True,
    )


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, timeout=15,
    )
    payload = json.loads(proc.stdout)
    return float(payload["format"]["duration"])


def _probe_audio_stream(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=15,
    )
    payload = json.loads(proc.stdout)
    for s in payload.get("streams", []):
        if s["codec_type"] == "audio":
            return s
    return {}


@pytest.fixture
def service() -> AudioPipelineService:
    return AudioPipelineService()


@pytest.fixture
def overrun_media(tmp_path) -> tuple[Path, Path]:
    """Video 3s, audio 6s — audio is 2x longer (reproduces the bug scenario)."""
    video = tmp_path / "short_video.mp4"
    audio = tmp_path / "long_audio.wav"
    _make_test_video(video, duration=3.0)
    _make_test_audio(audio, duration=6.0, sample_rate=22050, channels=1)
    return video, audio


# ------------------------------------------------------------------
# 1. Error mode — must fail loudly, not silently truncate
# ------------------------------------------------------------------

async def test_error_mode_fails_loudly_on_audio_overrun(service, overrun_media):
    video, audio = overrun_media

    result = await service.merge_audio_onto_video(
        project_id="test_proj",
        scene_id="test_scene",
        video_path=video,
        audio_path=audio,
        replace_original=False,
        on_audio_overrun="error",
    )

    assert result["status"] == TrackStatus.FAILED, (
        f"Expected FAILED but got {result['status']}. Result: {result}"
    )
    assert "exceeds video duration" in result["error"], (
        f"Error should mention audio overrun. Got: {result.get('error')}"
    )
    assert result.get("video_duration") is not None, "Should report video duration"
    assert result.get("audio_duration") is not None, "Should report audio duration"
    assert result.get("overrun_seconds") is not None, "Should report overrun seconds"

    video_dur = result["video_duration"]
    audio_dur = result["audio_duration"]
    overrun = result["overrun_seconds"]

    assert abs(video_dur - 3.0) < 0.3, f"Video ~3s, got {video_dur}"
    assert abs(audio_dur - 6.0) < 0.3, f"Audio ~6s, got {audio_dur}"
    assert overrun > 2.5, f"Overrun ~3s, got {overrun}"

    # CRITICAL: no output file should have been created — merge was aborted
    expected_output = video.parent / f"{video.stem}_audio{video.suffix}"
    assert not expected_output.exists(), (
        "Output file must NOT exist when error mode aborts — "
        "this proves we are not silently truncating."
    )


# ------------------------------------------------------------------
# 2. Freeze-last-frame mode — audio must NOT be truncated
# ------------------------------------------------------------------

async def test_freeze_last_frame_preserves_full_audio(service, overrun_media):
    video, audio = overrun_media

    result = await service.merge_audio_onto_video(
        project_id="test_proj",
        scene_id="test_scene",
        video_path=video,
        audio_path=audio,
        replace_original=False,
        on_audio_overrun="freeze_last_frame",
    )

    assert result["status"] == TrackStatus.COMPLETE, (
        f"Expected COMPLETE but got {result['status']}. "
        f"Error: {result.get('error')}"
    )

    output_path = Path(result["file_path"])
    assert output_path.exists(), "Output file should exist"

    output_dur = _probe_duration(output_path)
    audio_dur = result["audio_duration"]

    # The output duration must be >= audio duration — dialogue fully preserved.
    # This is the core assertion that catches the original -shortest bug.
    assert output_dur >= audio_dur - 0.3, (
        f"Output duration ({output_dur:.2f}s) must be >= audio duration "
        f"({audio_dur:.2f}s) — audio was truncated! "
        f"This is the original -shortest bug."
    )

    # Verify the audio stream in the output is not truncated
    audio_stream = _probe_audio_stream(output_path)
    assert audio_stream, "Output must have an audio stream"
    output_audio_dur = float(audio_stream.get("duration", 0))
    assert output_audio_dur >= audio_dur - 0.3, (
        f"Output audio stream ({output_audio_dur:.2f}s) must be >= "
        f"source audio ({audio_dur:.2f}s) — dialogue truncated!"
    )

    # Verify result metadata
    assert result["audio_overrun"] is True
    assert result["audio_preserved"] is True


# ------------------------------------------------------------------
# 3. Bitrate fix — sample-rate-aware, not hardcoded 192k
# ------------------------------------------------------------------

async def test_bitrate_is_sample_rate_aware(service, overrun_media):
    """For 22050 Hz mono, AAC bitrate should be ~48k, not the old 192k."""
    video, audio = overrun_media

    result = await service.merge_audio_onto_video(
        project_id="test_proj",
        scene_id="test_scene",
        video_path=video,
        audio_path=audio,
        replace_original=False,
        on_audio_overrun="freeze_last_frame",
    )

    assert result["status"] == TrackStatus.COMPLETE

    output_path = Path(result["file_path"])
    audio_stream = _probe_audio_stream(output_path)

    bit_rate = int(audio_stream.get("bit_rate", 0))
    # 192k is impossible for mono 22050 — FFmpeg clamps to ~48-94k.
    # With our fix we request 48k, so actual should be <= 60k.
    assert bit_rate <= 70000, (
        f"AAC bitrate for 22050 Hz mono should be <= 70k, got {bit_rate}. "
        f"The old hardcoded 192k was silently clamped by FFmpeg — "
        f"this confirms the fix is sample-rate-aware."
    )
    assert bit_rate >= 35000, (
        f"AAC bitrate should be at least 35k for intelligible speech, got {bit_rate}."
    )


# ------------------------------------------------------------------
# 4. trim_audio — not yet implemented (clear error)
# ------------------------------------------------------------------

async def test_trim_audio_not_implemented(service, overrun_media):
    result = await service.merge_audio_onto_video(
        project_id="test_proj",
        scene_id="test_scene",
        video_path=overrun_media[0],
        audio_path=overrun_media[1],
        replace_original=False,
        on_audio_overrun="trim_audio",
    )

    assert result["status"] == TrackStatus.FAILED
    assert "not yet implemented" in result["error"], (
        f"Should say not implemented. Got: {result.get('error')}"
    )


# ------------------------------------------------------------------
# 5. Invalid mode — should raise ValueError
# ------------------------------------------------------------------

async def test_invalid_overrun_mode_raises(service, overrun_media):
    with pytest.raises(ValueError, match="on_audio_overrun"):
        await service.merge_audio_onto_video(
            project_id="test_proj",
            scene_id="test_scene",
            video_path=overrun_media[0],
            audio_path=overrun_media[1],
            on_audio_overrun="bogus_mode",
        )


# ------------------------------------------------------------------
# 6. Normal case — audio shorter than video still works
# ------------------------------------------------------------------

async def test_normal_case_audio_shorter_than_video(service, tmp_path):
    video = tmp_path / "long_video.mp4"
    audio = tmp_path / "short_audio.wav"
    _make_test_video(video, duration=10.0)
    _make_test_audio(audio, duration=3.0, sample_rate=22050, channels=1)

    result = await service.merge_audio_onto_video(
        project_id="test_proj",
        scene_id="test_scene",
        video_path=video,
        audio_path=audio,
        replace_original=False,
        on_audio_overrun="error",
    )

    assert result["status"] == TrackStatus.COMPLETE, (
        f"Normal case (audio < video) should succeed. "
        f"Got: {result.get('error')}"
    )
    assert result["audio_overrun"] is False
    assert result["audio_preserved"] is True
    assert result["output_duration"] >= result["video_duration"] - 0.3


# ------------------------------------------------------------------
# 7. Bitrate computation unit test (no ffmpeg needed)
# ------------------------------------------------------------------

def test_compute_aac_bitrate_mono_22050():
    """mono 22050 Hz → 48k (not 192k)."""
    assert AudioPipelineService._compute_aac_bitrate(22050, 1) == "48k"


def test_compute_aac_bitrate_mono_44100():
    """mono 44100 Hz → 96k."""
    assert AudioPipelineService._compute_aac_bitrate(44100, 1) == "96k"


def test_compute_aac_bitrate_stereo_44100():
    """stereo 44100 Hz → 192k (the old default, valid here)."""
    assert AudioPipelineService._compute_aac_bitrate(44100, 2) == "192k"
