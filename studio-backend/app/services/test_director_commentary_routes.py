from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_director_commentary_routes(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Commentary Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    local_file = tmp_path / "commentary.mp4"
    local_file.write_text("video")

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "local_file", "local_path": str(local_file), "title": "Commentary Clip"},
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    generated = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/director-commentary/generate",
        json={"overwrite": True},
    )
    assert generated.status_code == 200
    assert isinstance(generated.json()["commentary"], list)

    listed = client.get(f"/api/f51/studio/video-assets/{asset_id}/director-commentary")
    assert listed.status_code == 200
    assert isinstance(listed.json()["commentary"], list)


def test_director_commentary_missing_asset_returns_400():
    client = _client()
    response = client.post(
        "/api/f51/studio/video-assets/asset-missing/director-commentary/generate",
        json={"overwrite": True},
    )
    assert response.status_code == 400
    assert "Video asset not found" in response.json()["detail"]
