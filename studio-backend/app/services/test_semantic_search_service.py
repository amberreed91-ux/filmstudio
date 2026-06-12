from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.semantic_memory_service import SemanticMemoryService
from app.services.semantic_search_service import SemanticSearchService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def test_search_similar_scenes_with_cosine(tmp_path: Path):
    storage = _make_storage(tmp_path)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_text("a")
    b.write_text("b")

    va = VideoAssetService(storage)
    asset_a = va.register_local_file(project_id="p1", local_path=str(a), title="A")
    asset_b = va.register_local_file(project_id="p1", local_path=str(b), title="B")

    sm = SemanticMemoryService(storage, va, None)
    mem_a = sm.ingest_asset_analysis(asset_id=asset_a.asset_id, dominant_mood="tense", visual_style="noir", lighting_style="low-key", pacing_profile="fast", cinematic_notes="rain neon")
    sm.ingest_asset_analysis(asset_id=asset_b.asset_id, dominant_mood="tense", visual_style="noir", lighting_style="low-key", pacing_profile="fast", cinematic_notes="rain neon")

    ss = SemanticSearchService(storage, sm)
    ss.register_frame_analysis(asset_id=asset_b.asset_id, caption="noir rain neon", mood_tags=["tense"], lighting_tags=["low-key"], camera_tags=["handheld"])

    result = ss.search_similar_scenes(memory_id=mem_a.memory_id, limit=10)
    assert len(result) >= 1
    assert result[0]["score"] >= 0


def test_search_by_mood_and_visual_style(tmp_path: Path):
    storage = _make_storage(tmp_path)
    v = tmp_path / "x.mp4"
    v.write_text("x")

    va = VideoAssetService(storage)
    asset = va.register_local_file(project_id="p1", local_path=str(v), title="X")
    sm = SemanticMemoryService(storage, va, None)
    sm.ingest_asset_analysis(asset_id=asset.asset_id, dominant_mood="melancholic", visual_style="arthouse", lighting_style="soft", pacing_profile="slow")

    ss = SemanticSearchService(storage, sm)
    mood = ss.search_by_mood("melanch")
    style = ss.search_by_visual_style("arthouse")

    assert len(mood) == 1
    assert len(style) == 1
