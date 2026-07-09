from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services.video_asset_service import VideoAssetService
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.frame_analysis_service import FrameAnalysisService
from app.services.vision_model_adapter import MockLocalVisionModelAdapter, UnavailableVisionModelAdapter


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _create_sample_video(video_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=24",
            str(video_path),
        ],
        check=True,
    )


def _build_services(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    (outputs / "final_films").mkdir(parents=True, exist_ok=True)
    movie_path = outputs / "final_films" / "demo.mp4"
    _create_sample_video(movie_path)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(
        project_id="project-1",
        source_url="/outputs/final_films/demo.mp4",
        title="Demo",
    )

    keyframes = KeyframeExtractionService(storage, assets)
    keyframes._outputs_root = outputs
    keyframes._keyframes_root = outputs / "keyframes"
    extracted = keyframes.extract_keyframes_for_asset(asset_id=asset.asset_id, interval_seconds=2, max_frames=3, overwrite=True)

    return storage, asset, keyframes, extracted


def test_mock_analysis_creates_persisted_frame_analysis(tmp_path: Path):
    storage, asset, keyframes, extracted = _build_services(tmp_path)
    service = FrameAnalysisService(
        storage=storage,
        keyframe_service=keyframes,
        video_asset_service=VideoAssetService(storage),
        vision_adapter=MockLocalVisionModelAdapter(),
    )

    row = service.analyze_keyframe(extracted[0].keyframe_id)
    assert row.analysis_id.startswith("analysis-")
    assert row.asset_id == asset.asset_id
    assert row.project_id == asset.project_id
    assert row.status == "complete"
    assert row.caption

    fetched = service.get_analysis(row.analysis_id)
    assert fetched is not None
    assert fetched.analysis_id == row.analysis_id


def test_unavailable_provider_returns_honest_unavailable(tmp_path: Path):
    storage, asset, keyframes, extracted = _build_services(tmp_path)
    service = FrameAnalysisService(
        storage=storage,
        keyframe_service=keyframes,
        video_asset_service=VideoAssetService(storage),
        vision_adapter=UnavailableVisionModelAdapter(),
    )

    row = service.analyze_keyframe(extracted[0].keyframe_id)
    assert row.status == "unavailable"
    assert row.provider == "unavailable"
    assert row.metadata.get("message") == "vision analysis not configured"


def test_list_analyses_by_asset_and_project(tmp_path: Path):
    storage, asset, keyframes, extracted = _build_services(tmp_path)
    service = FrameAnalysisService(
        storage=storage,
        keyframe_service=keyframes,
        video_asset_service=VideoAssetService(storage),
        vision_adapter=MockLocalVisionModelAdapter(),
    )

    for frame in extracted[:2]:
        service.analyze_keyframe(frame.keyframe_id)

    by_asset = service.list_analyses_for_asset(asset.asset_id)
    by_project = service.list_analyses_for_project(asset.project_id)

    assert len(by_asset) >= 2
    assert len(by_project) >= 2
    assert all(row.asset_id == asset.asset_id for row in by_asset)
    assert all(row.project_id == asset.project_id for row in by_project)
