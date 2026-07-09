"""Route-level tests for the recommended-duration endpoint.

The route is thin (validate -> call service -> format response), so these
verify wiring + HTTP formatting, not the estimation math (covered by the
service tests).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.render as render_routes
import app.services.shot_duration_estimator_service as estimator_module


class _StubService:
    def __init__(self, payload, raise_value_error=False):
        self._payload = payload
        self._raise = raise_value_error
        self.calls = []

    def estimate_for_shot(self, project_id, shot_id, pacing=None):
        self.calls.append((project_id, shot_id, pacing))
        if self._raise:
            raise ValueError(f"Project not found: {project_id}")
        return self._payload


def _client():
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")
    return TestClient(api)


def test_recommended_duration_endpoint_returns_service_payload(monkeypatch):
    payload = {
        "project_id": "p1",
        "shot_id": "scene_001_shot_001",
        "scene_id": "scene_001",
        "found": True,
        "advisory_only": True,
        "dialogue_excerpt": "Hello there.",
        "dialogue_line_count": 1,
        "dialogue_word_count": 2,
        "speech_seconds": 1.0,
        "estimated_seconds": 2.5,
        "recommended_seconds": 5.0,
        "current_default_seconds": 5.0,
        "min_viable_seconds": 5.0,
        "max_viable_seconds": 10.0,
        "pacing": "balanced",
        "speech_wpm": 150,
        "exceeds_provider_max": False,
    }
    stub = _StubService(payload)
    monkeypatch.setattr(estimator_module, "shot_duration_estimator_service", stub)

    res = _client().get(
        "/api/f51/studio/render/projects/p1/shots/scene_001_shot_001/recommended-duration"
    )
    assert res.status_code == 200
    assert res.json() == payload
    assert stub.calls == [("p1", "scene_001_shot_001", None)]


def test_recommended_duration_endpoint_passes_pacing_query(monkeypatch):
    stub = _StubService({"found": True, "recommended_seconds": 5.0})
    monkeypatch.setattr(estimator_module, "shot_duration_estimator_service", stub)

    _client().get(
        "/api/f51/studio/render/projects/p1/shots/s1/recommended-duration?pacing=fast"
    )
    assert stub.calls[0][2] == "fast"


def test_recommended_duration_endpoint_404_when_project_missing(monkeypatch):
    stub = _StubService({}, raise_value_error=True)
    monkeypatch.setattr(estimator_module, "shot_duration_estimator_service", stub)

    res = _client().get(
        "/api/f51/studio/render/projects/missing/shots/s1/recommended-duration"
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
