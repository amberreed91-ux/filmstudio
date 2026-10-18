from __future__ import annotations

import pytest
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

    def list_for_project(self, project_id: str, *, scene_id: str = ""):
        if project_id != self.run["project_id"]:
            raise StateError("Project not found", stage="workflow_ownership")
        if scene_id and scene_id != self.run["scene_id"]:
            return []
        return [self.run]

    def scene_context(self, project_id: str, scene_id: str):
        return {"script_id": "script-route", "sequence_id": "sequence-route", "beat_ids": ["beat-route"]}

    def current_blueprint_version_id(self, project_id: str, scene_id: str):
        if project_id != self.run["project_id"] or scene_id != self.run["scene_id"]:
            return ""
        return self.run["blueprint_version_id"]


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

    listed = client.get(
        "/api/f51/studio/projects/project-route/production-threads",
        params={"scene_id": "scene-route"},
    )
    assert listed.status_code == 200, listed.text
    assert [row["run_id"] for row in listed.json()["runs"]] == ["workflow-route-001"]
    assert listed.json()["current_blueprint_version_id"] == "version-route"
    assert listed.json()["scene_context"] == fake.scene_context("project-route", "scene-route")


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


@pytest.mark.parametrize("suffix,method", [("renders", "render_production_package"), ("revision/render", "render_revision")])
@pytest.mark.parametrize("provider", [None, "runway", "simulated"])
def test_provider_selection_reaches_service(monkeypatch, suffix, method, provider):
    fake = RouteWorkflowService()
    calls = []
    async def operation(run_id, **kwargs):
        calls.append((run_id, kwargs))
        return fake.run
    setattr(fake, method, operation)
    monkeypatch.setattr(workflow_routes, "canonical_production_workflow_service", fake)
    body = {} if provider is None else {"provider": provider}
    response = TestClient(app).post(f"/api/f51/studio/production-threads/workflow-route-001/{suffix}", json=body)
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert calls[0][1]["provider"] == provider


@pytest.mark.parametrize("provider", [None, "simulated"])
def test_previs_provider_selection_reaches_service(monkeypatch, provider):
    # Checkpoint 5 previs is simulated-only: omission and "simulated" reach
    # the service; production render / revision keep full provider behavior.
    fake = RouteWorkflowService()
    calls = []
    async def operation(run_id, **kwargs):
        calls.append((run_id, kwargs))
        return fake.run
    setattr(fake, "generate_previs", operation)
    monkeypatch.setattr(workflow_routes, "canonical_production_workflow_service", fake)
    body = {} if provider is None else {"provider": provider}
    response = TestClient(app).post("/api/f51/studio/production-threads/workflow-route-001/previs/generate", json=body)
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert calls[0][1]["provider"] == provider


@pytest.mark.parametrize("provider", ["runway", "runway_router", "runway_direct"])
def test_previs_non_simulated_provider_rejected_before_workflow_action(monkeypatch, provider):
    # Fail-closed at the route: no service call, 4xx surface.
    fake = RouteWorkflowService()
    calls = []
    async def operation(run_id, **kwargs):
        calls.append((run_id, kwargs))
        return fake.run
    setattr(fake, "generate_previs", operation)
    monkeypatch.setattr(workflow_routes, "canonical_production_workflow_service", fake)
    response = TestClient(app).post(
        "/api/f51/studio/production-threads/workflow-route-001/previs/generate",
        json={"provider": provider},
    )
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize("provider", ["", "   ", "runway video"])
def test_invalid_provider_rejected_before_workflow_action(provider):
    response = TestClient(app).post("/api/f51/studio/production-threads/workflow-route-001/renders", json={"provider": provider})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "suffix,method",
    [
        ("previs/generate", "generate_previs"),
        ("renders", "render_production_package"),
        ("revision/render", "render_revision"),
    ],
)
@pytest.mark.parametrize("provider", ["openrouter", "openrouter-video"])
def test_retired_video_provider_rejected_by_workflow_route_before_action(monkeypatch, suffix, method, provider):
    fake = RouteWorkflowService()
    calls = []

    async def operation(run_id, **kwargs):
        calls.append((run_id, kwargs))
        return fake.run

    setattr(fake, method, operation)
    monkeypatch.setattr(workflow_routes, "canonical_production_workflow_service", fake)
    response = TestClient(app).post(
        f"/api/f51/studio/production-threads/workflow-route-001/{suffix}",
        json={"provider": provider},
    )
    assert response.status_code == 422
    assert calls == []
