from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.semantic_memory_service import SemanticMemoryService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def test_ingest_asset_analysis(tmp_path: Path):
    storage = _make_storage(tmp_path)
    outputs = tmp_path / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    local_video = tmp_path / "clip.mp4"
    local_video.write_text("video")

    assets = VideoAssetService(storage)
    asset = assets.register_local_file(project_id="project-1", local_path=str(local_video), title="Clip")

    service = SemanticMemoryService(storage, assets, None)
    memory = service.ingest_asset_analysis(
        asset_id=asset.asset_id,
        dominant_mood="tense",
        visual_style="neo-noir",
        lighting_style="low-key",
        pacing_profile="staccato",
        character_presence=["lead", "shadow figure"],
        composition_patterns=["symmetry"],
        cinematic_notes="Strong suspense profile",
    )

    assert memory.memory_id.startswith("memory-")
    assert memory.asset_id == asset.asset_id
    assert memory.embeddings is not None


def test_search_and_related_memories(tmp_path: Path):
    storage = _make_storage(tmp_path)
    video_a = tmp_path / "a.mp4"
    video_b = tmp_path / "b.mp4"
    video_a.write_text("a")
    video_b.write_text("b")

    assets = VideoAssetService(storage)
    asset_a = assets.register_local_file(project_id="project-1", local_path=str(video_a), title="A")
    asset_b = assets.register_local_file(project_id="project-1", local_path=str(video_b), title="B")

    service = SemanticMemoryService(storage, assets, None)
    mem_a = service.ingest_asset_analysis(
        asset_id=asset_a.asset_id,
        dominant_mood="melancholic",
        visual_style="arthouse",
        lighting_style="soft",
        pacing_profile="slow",
        cinematic_notes="quiet corridor and reflective silence",
    )
    service.ingest_asset_analysis(
        asset_id=asset_b.asset_id,
        dominant_mood="melancholic",
        visual_style="arthouse",
        lighting_style="soft",
        pacing_profile="slow",
        cinematic_notes="reflective silence and soft movement",
    )

    matches = service.search_memories("reflective silence")
    assert len(matches) >= 1

    related = service.retrieve_related_memories(mem_a.memory_id)
    assert len(related) >= 1


def test_ingest_missing_asset_blocker(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = SemanticMemoryService(storage, VideoAssetService(storage), None)

    try:
        service.ingest_asset_analysis(asset_id="asset-missing")
        assert False, "Expected missing asset blocker"
    except ValueError as exc:
        assert "Video asset not found" in str(exc)
