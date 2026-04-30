from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

def _client_with_store() -> TestClient:
    return TestClient(app)


def test_create_and_list_project():
    client = _client_with_store()

    created = client.post("/api/f51/studio/projects", json={"title": "Persistence Test"})
    assert created.status_code == 200
    payload = created.json()
    assert payload["project_id"]
    assert payload["title"] == "Persistence Test"

    listed = client.get("/api/f51/studio/projects")
    assert listed.status_code == 200
    body = listed.json()
    assert isinstance(body.get("projects"), list)
    assert any(row.get("project_id") == payload["project_id"] for row in body["projects"])


def test_generate_scenes_and_load_project():
    client = _client_with_store()
    created = client.post("/api/f51/studio/projects", json={"title": "Film"}).json()
    project_id = created["project_id"]

    script = """
INT. KITCHEN - NIGHT
Mara watches Eli draw.

INT. HALLWAY - NIGHT
A scratching sound comes from inside the wall.
"""
    generated = client.post(
        f"/api/f51/studio/projects/{project_id}/generate-scenes",
        json={"script_text": script},
    )
    assert generated.status_code == 200
    updated = generated.json()
    scenes = updated.get("execution_summary", {}).get("scenes", [])
    assert isinstance(scenes, list)
    assert len(scenes) >= 2

    fetched = client.get(f"/api/f51/studio/projects/{project_id}")
    assert fetched.status_code == 200
    loaded = fetched.json()
    assert loaded["project_id"] == project_id
    assert loaded.get("script_text", "").strip().startswith("INT. KITCHEN")


def test_update_scene_review_and_film_cut():
    client = _client_with_store()
    created = client.post("/api/f51/studio/projects", json={"title": "Film"}).json()
    project_id = created["project_id"]

    scene_review = client.put(
        f"/api/f51/studio/projects/{project_id}/scene-review",
        json={
            "approved_scenes": ["scene_001"],
            "reviewed_scenes": ["scene_001", "scene_002"],
            "scene_review_status": {"scene_001": "approved", "scene_002": "needs_work"},
        },
    )
    assert scene_review.status_code == 200
    review_payload = scene_review.json()
    assert review_payload["approved_scenes"] == ["scene_001"]

    cut_update = client.put(
        f"/api/f51/studio/projects/{project_id}/film-cut",
        json={
            "film_cut": {
                "cut_id": "default",
                "scene_order": ["scene_001", "scene_002"],
                "included_scenes": ["scene_001"],
                "excluded_scenes": ["scene_002"],
                "created_at": "2026-01-01T00:00:00Z",
            }
        },
    )
    assert cut_update.status_code == 200
    cut_payload = cut_update.json()
    assert cut_payload["film_cut"]["included_scenes"] == ["scene_001"]


def test_missing_project_safe_response():
    client = _client_with_store()
    missing = client.put(
        "/api/f51/studio/projects/does-not-exist/scene-review",
        json={"approved_scenes": [], "reviewed_scenes": [], "scene_review_status": {}},
    )
    assert missing.status_code == 404


def test_empty_script_safe():
    client = _client_with_store()
    created = client.post("/api/f51/studio/projects", json={"title": "Film"}).json()
    project_id = created["project_id"]

    generated = client.post(
        f"/api/f51/studio/projects/{project_id}/generate-scenes",
        json={"script_text": ""},
    )
    assert generated.status_code == 200
    payload = generated.json()
    assert "execution_summary" in payload
    assert isinstance(payload.get("execution_summary"), dict)
