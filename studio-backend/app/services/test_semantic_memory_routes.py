from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_ingest_and_list_scene_memory_routes(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Memory Route Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    local_file = tmp_path / "route_memory.mp4"
    local_file.write_text("video")

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "local_file",
            "local_path": str(local_file),
            "title": "Memory Clip",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    ingested = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/scene-memory/ingest",
        json={
            "dominant_mood": "tense",
            "visual_style": "neo-noir",
            "lighting_style": "low-key",
            "pacing_profile": "slow-burn",
            "character_presence": ["lead"],
            "composition_patterns": ["symmetry"],
            "cinematic_notes": "Advisory memory note",
        },
    )
    assert ingested.status_code == 200
    memory_id = ingested.json()["memory"]["memory_id"]

    listed = client.get(f"/api/f51/studio/video-assets/{asset_id}/scene-memory")
    assert listed.status_code == 200
    assert any(row["memory_id"] == memory_id for row in listed.json()["memories"])

    searched = client.get("/api/f51/studio/scene-memory/search", params={"query": "advisory"})
    assert searched.status_code == 200
    assert len(searched.json()["memories"]) >= 1

    related = client.get(f"/api/f51/studio/scene-memory/{memory_id}/related")
    assert related.status_code == 200
    assert isinstance(related.json()["memories"], list)


def test_ingest_scene_memory_missing_asset_returns_400():
    client = _client()
    response = client.post(
        "/api/f51/studio/video-assets/asset-does-not-exist/scene-memory/ingest",
        json={},
    )
    assert response.status_code == 400
    assert "Video asset not found" in response.json()["detail"]
