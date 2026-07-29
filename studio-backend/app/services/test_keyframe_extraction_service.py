from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.data.storage import DatabaseStorage
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _create_sample_video(video_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=6:size=320x240:rate=24",
        str(video_path),
    ]
    subprocess.run(command, check=True)


def test_successful_extraction_from_generated_asset(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie_path = movie_dir / "demo.mp4"
    _create_sample_video(movie_path)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(
        project_id="project-1",
        source_url="/outputs/final_films/demo.mp4",
        title="Demo",
    )

    service = KeyframeExtractionService(storage, assets)
    service._outputs_root = outputs
    service._keyframes_root = outputs / "keyframes"

    keyframes = service.extract_keyframes_interval(asset_id=asset.asset_id, interval_seconds=2, max_frames=3)
    assert len(keyframes) == 3
    assert all(Path(k.frame_path).exists() for k in keyframes)
    assert keyframes[0].frame_url.startswith(f"/outputs/keyframes/{asset.asset_id}/")


def test_inaccessible_asset_returns_blocker(tmp_path: Path):
    storage = _make_storage(tmp_path)
    assets = VideoAssetService(storage)
    assets.register_external_url(project_id="project-1", source_url="https://example.com/video.mp4", title="Remote")
    asset = assets.list_assets_for_project("project-1")[0]

    service = KeyframeExtractionService(storage, assets)
    with pytest.raises(ValueError, match="not accessible"):
        service.extract_keyframes_interval(asset_id=asset.asset_id)


def test_missing_ffmpeg_returns_blocker(tmp_path: Path, monkeypatch):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie_path = movie_dir / "demo.mp4"
    _create_sample_video(movie_path)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(
        project_id="project-1",
        source_url="/outputs/final_films/demo.mp4",
        title="Demo",
    )

    service = KeyframeExtractionService(storage, assets)
    service._outputs_root = outputs
    monkeypatch.setattr("app.services.keyframe_extraction_service.shutil.which", lambda _: None)

    with pytest.raises(ValueError, match="FFmpeg"):
        service.extract_keyframes_interval(asset_id=asset.asset_id)


def test_existing_keyframes_returned_when_not_overwriting(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie_path = movie_dir / "demo.mp4"
    _create_sample_video(movie_path)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/demo.mp4", title="Demo")

    service = KeyframeExtractionService(storage, assets)
    service._outputs_root = outputs
    service._keyframes_root = outputs / "keyframes"

    first = service.extract_keyframes_interval(asset_id=asset.asset_id, interval_seconds=2, max_frames=2)
    second = service.extract_keyframes_interval(asset_id=asset.asset_id, interval_seconds=1, max_frames=5, overwrite=False)

    assert len(first) == 2
    assert [k.keyframe_id for k in second] == [k.keyframe_id for k in first]


def test_overwrite_regenerates_keyframes(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie_path = movie_dir / "demo.mp4"
    _create_sample_video(movie_path)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/demo.mp4", title="Demo")

    service = KeyframeExtractionService(storage, assets)
    service._outputs_root = outputs
    service._keyframes_root = outputs / "keyframes"

    first = service.extract_keyframes_interval(asset_id=asset.asset_id, interval_seconds=2, max_frames=2)
    second = service.extract_keyframes_interval(asset_id=asset.asset_id, interval_seconds=1, max_frames=4, overwrite=True)

    assert len(second) == 4
    assert first[0].keyframe_id != second[0].keyframe_id


def test_list_and_get_keyframe(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    movie_dir = outputs / "final_films"
    movie_dir.mkdir(parents=True, exist_ok=True)
    movie_path = movie_dir / "demo.mp4"
    _create_sample_video(movie_path)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/demo.mp4", title="Demo")

    service = KeyframeExtractionService(storage, assets)
    service._outputs_root = outputs
    service._keyframes_root = outputs / "keyframes"

    extracted = service.extract_keyframes_interval(asset_id=asset.asset_id, interval_seconds=2, max_frames=2)
    listed = service.list_keyframes_for_asset(asset.asset_id)
    fetched = service.get_keyframe(extracted[0].keyframe_id)

    assert len(listed) == 2
    assert fetched is not None
    assert fetched.keyframe_id == extracted[0].keyframe_id


def test_static_frame_url_is_correct(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = KeyframeExtractionService(storage, VideoAssetService(storage))
    assert service.build_frame_url(asset_id="asset-123", filename="frame_0001.jpg") == "/outputs/keyframes/asset-123/frame_0001.jpg"


def test_analyze_keyframe_variance_reports_stable_and_changed_frames(tmp_path: Path):
    black = tmp_path / "black.jpg"
    black_copy = tmp_path / "black-copy.jpg"
    white = tmp_path / "white.jpg"
    Image.new("RGB", (32, 32), "black").save(black)
    Image.new("RGB", (32, 32), "black").save(black_copy)
    Image.new("RGB", (32, 32), "white").save(white)

    result = asyncio.run(
        KeyframeExtractionService().analyze_keyframe_variance(
            frame_paths=[str(black), str(black_copy), str(white)],
            shot_id="shot-variance",
        )
    )

    assert result["frames_analyzed"] == 3
    assert result["frame_details"][0]["variance"] == 0
    assert result["frame_details"][1]["variance"] == 1
    assert result["avg_variance"] == 0.5
    assert result["stability_rating"] == "high_change"


def test_analyze_keyframe_variance_rejects_missing_frames(tmp_path: Path):
    with pytest.raises(ValueError, match="not accessible"):
        asyncio.run(
            KeyframeExtractionService().analyze_keyframe_variance(
                frame_paths=[str(tmp_path / "missing.jpg")],
                shot_id="shot-missing",
            )
        )
