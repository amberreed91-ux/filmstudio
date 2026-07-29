from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import get_storage
from app.routes.studio_brain import router
from app.services.studio_brain_executive_service import studio_brain_executive_service


def test_studio_brain_routes_create_plan_and_conflicts(tmp_path):
    storage = get_storage("sqlite", storage_path=str(tmp_path))
    studio_brain_executive_service._storage = storage
    studio_brain_executive_service._knowledge_service = None

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    create = client.post(
        "/api/f51/studio/projects/proj-001/brain/sessions",
        json={"purpose": "production_planning", "scope": {"phase": "production"}, "created_by": "owner"},
    )
    assert create.status_code == 200
    session_id = create.json()["session"]["session_id"]

    plan = client.post(f"/api/f51/studio/projects/proj-001/brain/sessions/{session_id}/plan")
    assert plan.status_code == 200
    body = plan.json()
    assert body["plan"]["steps"]
    assert body["legacy_orchestration_bundle"]["deterministic_audit"]["advisory_only"] is True

    conflicts = client.post(f"/api/f51/studio/projects/proj-001/brain/sessions/{session_id}/conflicts/detect")
    assert conflicts.status_code == 200
    assert conflicts.json()["conflicts"]
