from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_video_asset_endpoints_register_and_list(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Video Asset Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    local_file = tmp_path / "ingest.mp4"
    local_file.write_text("video")

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "local_file",
            "local_path": str(local_file),
            "title": "Local Ingest Clip",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    listed = client.get(f"/api/f51/studio/projects/{project_id}/video-assets")
    assert listed.status_code == 200
    assets = listed.json()["assets"]
    assert any(row["asset_id"] == asset_id for row in assets)

    fetched = client.get(f"/api/f51/studio/video-assets/{asset_id}")
    assert fetched.status_code == 200
    assert fetched.json()["asset"]["title"] == "Local Ingest Clip"


def test_video_asset_endpoints_reject_missing_local_file():
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Video Asset Film 2"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    response = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "local_file",
            "local_path": "/tmp/definitely_missing_ingest.mp4",
            "title": "Missing Clip",
        },
    )
    assert response.status_code == 400
    assert "Local file not found" in response.json()["detail"]


def test_video_asset_status_update(tmp_path, monkeypatch):
    from app.services.video_asset_service import video_asset_service

    # Status updates should not depend on a developer's generated sample file.
    sample = tmp_path / "mock-video" / "sample.mp4"
    sample.parent.mkdir()
    sample.write_bytes(b"test generated asset")
    monkeypatch.setattr(video_asset_service, "_outputs_root", tmp_path)
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Video Asset Film 3"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "generated_output",
            "source_url": "/outputs/mock-video/sample.mp4",
            "title": "Generated Clip",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    updated = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/status",
        json={"status": "analysis_pending", "metadata_patch": {"stage": "queued"}},
    )
    assert updated.status_code == 200
    payload = updated.json()["asset"]
    assert payload["status"] == "analysis_pending"
    assert payload["metadata"]["stage"] == "queued"


def test_upload_video_asset_registers_row_and_metadata():
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Upload Asset Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    uploaded = client.post(
        "/api/f51/studio/video-assets/upload",
        data={
            "project_id": project_id,
            "title": "Uploaded Study Clip",
            "description": "Upload flow test",
            "tags": "study,noir",
            "notes": "reference footage",
            "metadata_json": "{\"user_note\":\"keep contrast\"}",
        },
        files={"file": ("study_clip.mp4", b"fake video bytes", "video/mp4")},
    )
    assert uploaded.status_code == 200
    asset = uploaded.json()["asset"]
    assert asset["source_type"] == "uploaded_file"
    assert asset["project_id"] == project_id
    assert asset["title"] == "Uploaded Study Clip"
    assert asset["metadata"]["original_filename"] == "study_clip.mp4"
    assert "study" in asset["metadata"]["tags"]


def test_list_all_uploaded_assets_and_attach_to_project():
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Attach Asset Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    uploaded = client.post(
        "/api/f51/studio/video-assets/upload",
        files={"file": ("floating_clip.mp4", b"fake bytes", "video/mp4")},
    )
    assert uploaded.status_code == 200
    asset_id = uploaded.json()["asset"]["asset_id"]
    assert uploaded.json()["asset"]["project_id"] == "unassigned"

    listed = client.get("/api/f51/studio/video-assets?source_type=uploaded_file")
    assert listed.status_code == 200
    assert any(row["asset_id"] == asset_id for row in listed.json()["assets"])

    attached = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/attach-project",
        json={"project_id": project_id},
    )
    assert attached.status_code == 200
    assert attached.json()["asset"]["project_id"] == project_id

    fetched = client.get(f"/api/f51/studio/video-assets/{asset_id}")
    assert fetched.status_code == 200
    assert fetched.json()["asset"]["project_id"] == project_id

    listed_for_project = client.get(f"/api/f51/studio/projects/{project_id}/video-assets")
    assert listed_for_project.status_code == 200
    assert any(row["asset_id"] == asset_id for row in listed_for_project.json()["assets"])


def test_upload_triggers_metadata_auto_match_and_confirm_flow():
    client = _client()
    imported = client.post(
        "/api/scene-intelligence/import",
        json={
            "scenes": [
                {
                    "scene_id": "scene_901",
                    "film_title": "Study Import",
                    "scene_name": "Office",
                    "intent": "Desk scene",
                    "emotional_beat_arc": ["calm"],
                    "camera_logic": ["static"],
                    "pacing_curve": ["steady"],
                    "director_notes": "Hold frame",
                    "expected_video_filename": "scene_901.mp4",
                }
            ]
        },
    )
    assert imported.status_code == 200

    uploaded = client.post(
        "/api/f51/studio/video-assets/upload",
        files={"file": ("scene_901.mp4", b"fake bytes", "video/mp4")},
    )
    assert uploaded.status_code == 200
    asset_id = uploaded.json()["asset"]["asset_id"]

    matches = client.get(f"/api/f51/studio/video-assets/{asset_id}/metadata-matches")
    assert matches.status_code == 200
    rows = matches.json()["matches"]
    assert len(rows) >= 1
    match_id = rows[0]["match_id"]

    confirmed = client.post(f"/api/f51/studio/video-assets/{asset_id}/metadata-matches/{match_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["match"]["match_status"] in {"confirmed", "auto_confirmed"}

    unmatched = client.get("/api/f51/studio/video-assets/unmatched")
    assert unmatched.status_code == 200


def test_generated_asset_route_rejects_path_escape(tmp_path, monkeypatch):
    from app.services.video_asset_service import video_asset_service

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (tmp_path / "private.txt").write_text("synthetic sentinel")
    monkeypatch.setattr(video_asset_service, "_outputs_root", outputs)
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Asset Boundary"})
    project_id = created.json()["project_id"]
    response = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "generated_output", "source_url": "/outputs/../private.txt", "title": "Invalid asset"},
    )
    assert response.status_code == 400
    assert "outputs directory" in response.json()["detail"]
    assert not client.get(f"/api/f51/studio/projects/{project_id}/video-assets").json()["assets"]
