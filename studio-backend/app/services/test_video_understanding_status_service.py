from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from app.data.storage import DatabaseStorage
from app.models import VideoKeyframe
from app.services.semantic_memory_service import SemanticMemoryService
from app.services.semantic_search_service import SemanticSearchService
from app.services.video_asset_service import VideoAssetService
from app.services.video_understanding_status_service import VideoUnderstandingStatusService
from app.services.keyframe_extraction_service import KeyframeExtractionService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def test_incomplete_asset_keeps_understanding_disabled(tmp_path: Path):
    storage = _make_storage(tmp_path)
    local_video = tmp_path / "clip.mp4"
    local_video.write_text("video")
    assets = VideoAssetService(storage)
    keyframes = KeyframeExtractionService(storage=storage, video_asset_service=assets)
    memory = SemanticMemoryService(storage, assets, None)
    search = SemanticSearchService(storage=storage, semantic_memory_service=memory)
    service = VideoUnderstandingStatusService(video_assets=assets, keyframes=keyframes, semantic_memory=memory, semantic_search=search)

    asset = assets.register_local_file(project_id="project-vu", local_path=str(local_video), title="Clip")
    status = service.get_asset_status(asset.asset_id)
    assert status.keyframes_complete is False
    assert status.analysis_complete is False
    assert status.memory_complete is False
    assert status.understanding_enabled is False


def test_complete_asset_enables_true_understanding(tmp_path: Path):
    storage = _make_storage(tmp_path)
    local_video = tmp_path / "clip2.mp4"
    local_video.write_text("video")
    assets = VideoAssetService(storage)
    keyframes = KeyframeExtractionService(storage=storage, video_asset_service=assets)
    memory = SemanticMemoryService(storage, assets, None)
    search = SemanticSearchService(storage=storage, semantic_memory_service=memory)
    service = VideoUnderstandingStatusService(video_assets=assets, keyframes=keyframes, semantic_memory=memory, semantic_search=search)

    asset = assets.register_local_file(project_id="project-vu", local_path=str(local_video), title="Clip2")
    frame = storage.save_video_keyframe(
        VideoKeyframe(
            keyframe_id="kf-test-1",
            asset_id=asset.asset_id,
            project_id=asset.project_id,
            timestamp_seconds=0.0,
            frame_path="/tmp/fake.jpg",
            frame_url=None,
            frame_index=0,
            extraction_reason="interval",
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={},
        )
    )
    search.register_frame_analysis(
        asset_id=asset.asset_id,
        keyframe_id=frame.keyframe_id,
        caption="A dim corridor",
        mood_tags=["tense"],
        lighting_tags=["low-key"],
        camera_tags=["static"],
        metadata={"source": "test"},
    )
    memory.ingest_asset_analysis(
        asset_id=asset.asset_id,
        dominant_mood="tense",
        visual_style="noir",
        lighting_style="low-key",
        pacing_profile="slow",
        composition_patterns=["symmetry"],
        cinematic_notes="test memory",
    )

    status = service.get_asset_status(asset.asset_id)
    assert status.keyframes_complete is True
    assert status.analysis_complete is True
    assert status.memory_complete is True
    assert status.understanding_enabled is True
