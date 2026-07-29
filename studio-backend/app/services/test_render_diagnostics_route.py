from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.render as render_routes
from app.services import render as render_module


class _DummyStorage:
    def __init__(self):
        self.db_path = "/tmp/studio-test.db"

    def list_jobs(self, limit: int = 1):
        return []


class _DummyRenderService:
    def __init__(self):
        self._jobs = {"job-1": {"id": "job-1"}}

    def list_jobs(self, project_id=None):
        return []

    def list_providers(self):
        class _Provider:
            provider_id = "simulated"
            name = "Simulated"
            status = "available"
            is_simulated = True
            active_jobs = 0
            queued_jobs = 0

        return [_Provider()]


def test_render_diagnostics_endpoint(monkeypatch):
    monkeypatch.setattr(render_routes, "render_service", _DummyRenderService())
    monkeypatch.setattr(render_module, "_storage", _DummyStorage())

    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")
    client = TestClient(api)
    res = client.get("/api/f51/studio/render/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert "provider_status" in data
    assert "render_queue" in data
    assert "hydration_state" in data
    assert "persistence_health" in data
    assert "environment" in data
    assert data["persistence_health"]["status"] == "ok"
