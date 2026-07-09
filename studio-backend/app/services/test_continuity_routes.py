from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_project_continuity_routes(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Continuity Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    local_a = tmp_path / "cont_a.mp4"
    local_b = tmp_path / "cont_b.mp4"
    local_a.write_text("a")
    local_b.write_text("b")

    asset_a = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "local_file", "local_path": str(local_a), "title": "A"},
    )
    assert asset_a.status_code == 200
    aid_a = asset_a.json()["asset"]["asset_id"]

    asset_b = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "local_file", "local_path": str(local_b), "title": "B"},
    )
    assert asset_b.status_code == 200
    aid_b = asset_b.json()["asset"]["asset_id"]

    r1 = client.post(
        f"/api/f51/studio/video-assets/{aid_a}/scene-memory/ingest",
        json={"dominant_mood": "quiet", "lighting_style": "low-key", "visual_style": "warm", "pacing_profile": "slow", "character_presence": ["lead"], "composition_patterns": ["symmetry"], "cinematic_notes": "warm saturated"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/f51/studio/video-assets/{aid_b}/scene-memory/ingest",
        json={"dominant_mood": "tense", "lighting_style": "high-key", "visual_style": "cool", "pacing_profile": "fast", "character_presence": ["lead", "support"], "composition_patterns": ["handheld"], "cinematic_notes": "cool desaturated"},
    )
    assert r2.status_code == 200

    analyzed = client.post(
        f"/api/f51/studio/projects/{project_id}/continuity/analyze",
        json={"overwrite": True},
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["advisory_only"] is True
    assert analyzed.json()["auto_regeneration_triggered"] is False

    listed = client.get(f"/api/f51/studio/projects/{project_id}/continuity/issues")
    assert listed.status_code == 200
    assert listed.json()["advisory_only"] is True
    assert isinstance(listed.json()["issues"], list)


def test_project_continuity_missing_project():
    client = _client()
    response = client.post("/api/f51/studio/projects/project-missing/continuity/analyze", json={"overwrite": True})
    assert response.status_code == 404
