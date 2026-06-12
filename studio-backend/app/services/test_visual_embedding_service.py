from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services.video_asset_service import VideoAssetService
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.visual_embedding_service import VisualEmbeddingService
from app.services.visual_embedding_adapter import MockLocalVisualEmbeddingAdapter, UnavailableVisualEmbeddingAdapter


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _create_sample_video(video_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=24", str(video_path)],
        check=True,
    )


def _setup(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    (outputs / "final_films").mkdir(parents=True, exist_ok=True)
    movie = outputs / "final_films" / "demo.mp4"
    _create_sample_video(movie)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/demo.mp4", title="Demo")

    keyframes = KeyframeExtractionService(storage, assets)
    keyframes._outputs_root = outputs
    keyframes._keyframes_root = outputs / "keyframes"
    extracted = keyframes.extract_keyframes_for_asset(asset_id=asset.asset_id, interval_seconds=2, max_frames=3, overwrite=True)
    return storage, asset, keyframes, extracted


def test_embedding_persistence_and_dimension(tmp_path: Path):
    storage, asset, keyframes, extracted = _setup(tmp_path)
    service = VisualEmbeddingService(storage=storage, keyframe_service=keyframes, video_asset_service=None, embedding_adapter=MockLocalVisualEmbeddingAdapter())
    row = service.create_embedding_for_keyframe(extracted[0].keyframe_id)
    assert row.status == "complete"
    assert row.vector_dimension > 0
    assert len(row.embedding_vector) == row.vector_dimension

    fetched = service.get_embedding(row.embedding_id)
    assert fetched is not None
    assert fetched.embedding_id == row.embedding_id


def test_unavailable_provider_path(tmp_path: Path):
    storage, asset, keyframes, extracted = _setup(tmp_path)
    service = VisualEmbeddingService(storage=storage, keyframe_service=keyframes, video_asset_service=None, embedding_adapter=UnavailableVisualEmbeddingAdapter())
    row = service.create_embedding_for_keyframe(extracted[0].keyframe_id)
    assert row.status == "unavailable"
    assert row.vector_dimension == 0


def test_cosine_similarity_and_project_filtering(tmp_path: Path):
    storage, asset, keyframes, extracted = _setup(tmp_path)
    service = VisualEmbeddingService(storage=storage, keyframe_service=keyframes, video_asset_service=None, embedding_adapter=MockLocalVisualEmbeddingAdapter())
    service.create_embeddings_for_asset(asset.asset_id)

    sims = service.find_similar_keyframes(keyframe_id=extracted[0].keyframe_id, top_k=3, project_id=asset.project_id)
    assert len(sims) >= 1
    assert all(item["project_id"] == asset.project_id for item in sims)

    assert service.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert service.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
