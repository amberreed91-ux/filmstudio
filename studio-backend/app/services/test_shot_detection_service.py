from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.shot_detection_service import ShotDetectionService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _create_shot_video(video_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    # 3 distinct color shots with fade transitions to exercise transition tagging.
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1.2",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.2",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1.2",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.2",
        "-f", "lavfi", "-i", "color=c=green:s=320x240:d=1.2",
        "-filter_complex", "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0,format=yuv420p[v]",
        "-map", "[v]",
        str(video_path),
    ]
    subprocess.run(command, check=True)


def test_detect_shots_and_list(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie = movie_dir / "shots.mp4"
    _create_shot_video(movie)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    keyframes = KeyframeExtractionService(storage, assets)
    keyframes._outputs_root = outputs
    keyframes._keyframes_root = outputs / "keyframes"

    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/shots.mp4", title="Shots")
    service = ShotDetectionService(storage, assets, keyframes)
    service._outputs_root = outputs

    shots = service.detect_shots(asset_id=asset.asset_id, threshold=0.2)
    listed = service.list_shots(asset.asset_id)

    assert len(shots) >= 2
    assert len(listed) == len(shots)
    assert listed[0].start_time == 0.0
    assert all(s.end_time > s.start_time for s in listed)


def test_generate_representative_frames(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie = movie_dir / "shots2.mp4"
    _create_shot_video(movie)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    keyframes = KeyframeExtractionService(storage, assets)
    keyframes._outputs_root = outputs
    keyframes._keyframes_root = outputs / "keyframes"

    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/shots2.mp4", title="Shots2")
    service = ShotDetectionService(storage, assets, keyframes)
    service._outputs_root = outputs

    frames = service.generate_representative_frames(asset_id=asset.asset_id, max_frames=5)
    assert len(frames) > 0
    assert all(f.extraction_reason == "representative" for f in frames)


def test_missing_ffmpeg_blocker(tmp_path: Path, monkeypatch):
    storage = _make_storage(tmp_path)
    assets = VideoAssetService(storage)
    service = ShotDetectionService(storage, assets, None)

    monkeypatch.setattr("app.services.shot_detection_service.shutil.which", lambda _: None)
    with pytest.raises(ValueError, match="FFmpeg/FFprobe"):
        service.detect_shots(asset_id="asset-missing")
