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
