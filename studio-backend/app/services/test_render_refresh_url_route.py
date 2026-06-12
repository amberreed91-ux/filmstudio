from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.render as render_routes


class _DummyRenderService:
    async def refresh_output_url(self, job_id: str):
        if job_id == "missing":
            return None
        return "https://example.com/fresh.mp4"


def test_refresh_output_url_endpoint_success(monkeypatch):
    monkeypatch.setattr(render_routes, "render_service", _DummyRenderService())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")
    client = TestClient(api)

    response = client.post("/api/f51/studio/render/jobs/job-1/refresh-url")
    assert response.status_code == 200
    assert response.json() == {"output_url": "https://example.com/fresh.mp4"}


def test_refresh_output_url_endpoint_missing(monkeypatch):
    monkeypatch.setattr(render_routes, "render_service", _DummyRenderService())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")
    client = TestClient(api)

    response = client.post("/api/f51/studio/render/jobs/missing/refresh-url")
    assert response.status_code == 200
    assert response.json() == {"output_url": None}
