from __future__ import annotations

from fastapi.testclient import TestClient

import app.routes.canonical_workflow as workflow_routes
from app.services.stability import StateError
from main import app


def _effective_routes():
    for route in app.router.routes:
        effective_candidates = getattr(route, "effective_candidates", None)
        if callable(effective_candidates):
            yield from effective_candidates()
        else:
            yield route


class RouteWorkflowService:
    def __init__(self) -> None:
        self.run = {
            "run_id": "workflow-route-001",
            "project_id": "project-route",
            "script_id": "script-route",
            "scene_id": "scene-route",
            "blueprint_id": "blueprint-route",
            "blueprint_version_id": "version-route",
            "status": "blueprint_approved",
            "context_hash": "a" * 64,
            "data": {"identifiers": {}, "artifacts": {}, "approvals": {}, "failures": []},
            "created_at": "2026-08-06T12:00:00+00:00",
            "updated_at": "2026-08-06T12:00:00+00:00",
        }

    def begin(self, **kwargs):
        if kwargs["script_id"] != "script-route":
            raise StateError("Script does not own the requested scene", stage="workflow_ownership")
        return self.run

    def get(self, run_id: str):
        if run_id != self.run["run_id"]:
            raise StateError("Canonical workflow run not found", stage="workflow_load")
        return self.run

    def transitions(self, run_id: str):
        self.get(run_id)
        return []


def test_canonical_workflow_routes_are_mounted_once_and_reachable(monkeypatch) -> None:
    fake = RouteWorkflowService()
    monkeypatch.setattr(workflow_routes, "canonical_production_workflow_service", fake)
    path = "/api/f51/studio/projects/{project_id}/scenes/{scene_id}/production-thread"
    matching = [
        route for route in _effective_routes()
        if getattr(route, "path", None) == path and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matching) == 1
    assert path in app.openapi()["paths"]

    client = TestClient(app)
    created = client.post(
        "/api/f51/studio/projects/project-route/scenes/scene-route/production-thread",
        json={
            "script_id": "script-route",
            "sequence_id": "sequence-route",
            "beat_ids": ["beat-route"],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["run"]["run_id"] == "workflow-route-001"

    loaded = client.get("/api/f51/studio/production-threads/workflow-route-001")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["run"]["status"] == "blueprint_approved"


def test_canonical_workflow_route_formats_ownership_errors(monkeypatch) -> None:
    fake = RouteWorkflowService()
    monkeypatch.setattr(workflow_routes, "canonical_production_workflow_service", fake)
    response = TestClient(app).post(
        "/api/f51/studio/projects/project-route/scenes/scene-route/production-thread",
        json={"script_id": "script-other"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error_type"] == "state_error"
    assert response.json()["detail"]["stage"] == "workflow_ownership"
