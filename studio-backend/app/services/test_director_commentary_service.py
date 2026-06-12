from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.director_commentary_service import DirectorCommentaryService
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.semantic_memory_service import SemanticMemoryService
from app.services.shot_detection_service import ShotDetectionService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def test_generate_commentary_grounded_in_analysis(tmp_path: Path):
    storage = _make_storage(tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_text("video")

    va = VideoAssetService(storage)
    asset = va.register_local_file(project_id="project-1", local_path=str(clip), title="Clip")

    ks = KeyframeExtractionService(storage, va)
    ss = ShotDetectionService(storage, va, ks)
    sm = SemanticMemoryService(storage, va, ss)

    # Seed memory and one continuity-relevant shot-like context by storing memory.
    sm.ingest_asset_analysis(
        asset_id=asset.asset_id,
        dominant_mood="brooding",
        visual_style="arthouse",
        lighting_style="low-key",
        pacing_profile="measured",
        character_presence=["lead"],
        composition_patterns=["symmetry"],
        cinematic_notes="cool desaturated static framing",
    )

    service = DirectorCommentaryService(storage, va, ks, ss, sm)
    rows = service.generate_commentary(asset_id=asset.asset_id, overwrite=True)

    assert len(rows) >= 1
    first = rows[0]
    assert first.asset_id == asset.asset_id
    assert first.interpretation
    assert first.emotional_read
    assert first.visual_language_notes
    assert first.pacing_notes


def test_list_for_asset(tmp_path: Path):
    storage = _make_storage(tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_text("video")

    va = VideoAssetService(storage)
    asset = va.register_local_file(project_id="project-1", local_path=str(clip), title="Clip")
    service = DirectorCommentaryService(storage, va, None, None, None)
    service.generate_commentary(asset_id=asset.asset_id, overwrite=True)

    listed = service.list_for_asset(asset.asset_id)
    assert len(listed) >= 1


def test_generate_commentary_missing_asset_blocker(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = DirectorCommentaryService(storage, VideoAssetService(storage), None, None, None)
    try:
        service.generate_commentary(asset_id="asset-missing", overwrite=True)
        assert False, "Expected missing asset blocker"
    except ValueError as exc:
        assert "Video asset not found" in str(exc)
