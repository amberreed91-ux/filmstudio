from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.render as render_routes


class _DummyRenderService:
    async def reconcile_completed_runway_task(self, job_id: str):
        if job_id == "missing":
            raise ValueError("Job missing not found")
        return {"id": job_id, "status": "complete"}


def test_reconcile_endpoint_success(monkeypatch):
    monkeypatch.setattr(render_routes, "render_service", _DummyRenderService())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")
    client = TestClient(api)
    res = client.post("/api/f51/studio/render/jobs/job-1/reconcile")
    assert res.status_code == 200
    assert res.json()["id"] == "job-1"
    assert res.json()["status"] == "complete"


def test_reconcile_endpoint_not_found(monkeypatch):
    monkeypatch.setattr(render_routes, "render_service", _DummyRenderService())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")
    client = TestClient(api)
    res = client.post("/api/f51/studio/render/jobs/missing/reconcile")
    assert res.status_code == 404
