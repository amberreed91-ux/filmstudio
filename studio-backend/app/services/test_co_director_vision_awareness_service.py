from types import SimpleNamespace

from app.services.co_director_vision_awareness_service import CoDirectorVisionAwarenessService


def test_build_awareness_context_is_advisory_and_bounded(monkeypatch):
    service = CoDirectorVisionAwarenessService()

    assets = [SimpleNamespace(asset_id="asset-1")]
    memories = [
        SimpleNamespace(
            asset_id="asset-1",
            visual_style="noir",
            lighting_style="low-key",
            pacing_profile="slow-burn",
            composition_patterns=["wide", "static"],
        )
    ]
    issues = [
        SimpleNamespace(category="lighting", metadata={"scene_id": "scene_1"}),
        SimpleNamespace(category="framing", metadata={"scene_id": "scene_1"}),
    ]

    monkeypatch.setattr(
        "app.services.co_director_vision_awareness_service.video_asset_service.list_assets_for_project",
        lambda _project_id: assets,
    )
    monkeypatch.setattr(
        "app.services.co_director_vision_awareness_service.semantic_memory_service.list_memories_for_asset",
        lambda _asset_id: memories,
    )
    monkeypatch.setattr(
        "app.services.co_director_vision_awareness_service.continuity_intelligence_service.list_project_issues",
        lambda _project_id: issues,
    )

    result = service.build_awareness_context(project_id="project_1", scene_id="scene_1")
    assert result["advisory_only"] is True
    assert result["cannot_auto_regenerate"] is True
    assert result["cannot_override_user_intent"] is True
    assert len(result["visual_consistency_suggestions"]) > 0
    assert len(result["pacing_suggestions"]) > 0
    assert len(result["composition_observations"]) > 0


def test_build_awareness_context_handles_missing_project_safely():
    service = CoDirectorVisionAwarenessService()
    result = service.build_awareness_context(project_id=None)
    assert result["advisory_only"] is True
    assert result["cannot_auto_regenerate"] is True
    assert result["cannot_override_user_intent"] is True
