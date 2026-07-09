from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_seed_demo_project_route_returns_urls():
    client = TestClient(app)
    response = client.post("/api/f51/studio/dev/seed-demo-project", json={"project_id": "demo_studio_cinematic_001"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "demo_studio_cinematic_001"
    assert payload["study_room_url"].endswith("project_id=demo_studio_cinematic_001")
    assert payload["previs_url"].endswith("project_id=demo_studio_cinematic_001")
    assert payload["production_url"].endswith("project_id=demo_studio_cinematic_001")
    assert payload["screening_url"].endswith("project_id=demo_studio_cinematic_001")
    assert payload["crew_ops_url"].endswith("project_id=demo_studio_cinematic_001")


def test_seeded_demo_render_jobs_are_visible_in_render_jobs_list():
    client = TestClient(app)
    client.post("/api/f51/studio/dev/seed-demo-project", json={"project_id": "demo_studio_cinematic_001"})

    response = client.get("/api/f51/studio/render/jobs", params={"project_id": "demo_studio_cinematic_001"})
    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list)
    assert len(rows) >= 2

    completed = [row for row in rows if row.get("status") == "complete"]
    assert len(completed) >= 2

    for row in completed[:2]:
        assert row.get("output_url")
        assert row.get("preview_url")
