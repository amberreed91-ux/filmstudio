from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services.video_asset_service import VideoAssetService
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.frame_analysis_service import FrameAnalysisService
from app.services.visual_embedding_service import VisualEmbeddingService
from app.services.vision_model_adapter import MockLocalVisionModelAdapter
from app.services.visual_embedding_adapter import MockLocalVisualEmbeddingAdapter
from app.services.cinematic_memory_service import CinematicMemoryService
from app.services.semantic_retrieval_service import SemanticRetrievalService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_video(path: Path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=24", str(path)], check=True)


def _setup(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    (outputs / "final_films").mkdir(parents=True, exist_ok=True)
    movie = outputs / "final_films" / "demo.mp4"
    _make_video(movie)

    assets = VideoAssetService(storage)
    assets._outputs_root = outputs
    asset = assets.register_generated_output(project_id="project-1", source_url="/outputs/final_films/demo.mp4", title="Demo")

    keyframes = KeyframeExtractionService(storage, assets)
    keyframes._outputs_root = outputs
    keyframes._keyframes_root = outputs / "keyframes"
    frames = keyframes.extract_keyframes_for_asset(asset_id=asset.asset_id, interval_seconds=2, max_frames=3, overwrite=True)

    frame_analysis = FrameAnalysisService(storage=storage, keyframe_service=keyframes, video_asset_service=assets, vision_adapter=MockLocalVisionModelAdapter())
    for frame in frames:
        frame_analysis.analyze_keyframe(frame.keyframe_id)

    embeddings = VisualEmbeddingService(storage=storage, keyframe_service=keyframes, video_asset_service=assets, embedding_adapter=MockLocalVisualEmbeddingAdapter())
    embeddings.create_embeddings_for_asset(asset.asset_id)

    memory = CinematicMemoryService(
        storage=storage,
        frame_analysis_service=frame_analysis,
        visual_embedding_service=embeddings,
        keyframe_service=keyframes,
        video_asset_service=assets,
    )
    retrieval = SemanticRetrievalService(
        storage=storage,
        cinematic_memory_service=memory,
        visual_embedding_service=embeddings,
        keyframe_service=keyframes,
    )
    return storage, asset, frames, memory, retrieval


def test_memory_persistence_and_search(tmp_path: Path):
    storage, asset, frames, memory, retrieval = _setup(tmp_path)
    rows = memory.build_memory_for_asset(asset.asset_id)
    assert len(rows) >= 1
    listed = memory.list_memory_for_project(asset.project_id)
    assert len(listed) >= 1
    results = retrieval.search_memory(project_id=asset.project_id, query="soft natural lighting", top_k=5)
    assert len(results) >= 1
    assert "why_match" in results[0]


def test_related_frame_retrieval_no_cross_project_leakage(tmp_path: Path):
    storage, asset_a, frames_a, memory, retrieval = _setup(tmp_path)
    memory.build_memory_for_asset(asset_a.asset_id)

    # Create separate project asset
    outputs = tmp_path / "outputs"
    movie2 = outputs / "final_films" / "demo2.mp4"
    _make_video(movie2)
    assets2 = VideoAssetService(storage)
    assets2._outputs_root = outputs
    asset_b = assets2.register_generated_output(project_id="project-2", source_url="/outputs/final_films/demo2.mp4", title="Demo2")
    keyframes2 = KeyframeExtractionService(storage, assets2)
    keyframes2._outputs_root = outputs
    keyframes2._keyframes_root = outputs / "keyframes"
    frames_b = keyframes2.extract_keyframes_for_asset(asset_id=asset_b.asset_id, interval_seconds=2, max_frames=2, overwrite=True)

    frame_analysis2 = FrameAnalysisService(storage=storage, keyframe_service=keyframes2, video_asset_service=assets2, vision_adapter=MockLocalVisionModelAdapter())
    for frame in frames_b:
        frame_analysis2.analyze_keyframe(frame.keyframe_id)
    embeddings2 = VisualEmbeddingService(storage=storage, keyframe_service=keyframes2, video_asset_service=assets2, embedding_adapter=MockLocalVisualEmbeddingAdapter())
    embeddings2.create_embeddings_for_asset(asset_b.asset_id)
    memory2 = CinematicMemoryService(storage=storage, frame_analysis_service=frame_analysis2, visual_embedding_service=embeddings2, keyframe_service=keyframes2, video_asset_service=assets2)
    memory2.build_memory_for_asset(asset_b.asset_id)

    related = retrieval.visual_to_memory_retrieval(keyframe_id=frames_a[0].keyframe_id, top_k=10, project_id=asset_a.project_id)
    assert all((row.get("memory") and row["memory"].project_id == asset_a.project_id) for row in related)
