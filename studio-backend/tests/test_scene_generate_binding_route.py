"""Route carrier for Desk-confirmed reference binding digests (Phase C4).

The generate route accepts an optional shot-ID → digest map and passes it
to the scene pipeline untouched. The server re-verifies every digest
against current canonical state inside generate_scene; the route itself
never interprets client data as authorization.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.projects import router


def _client() -> TestClient:
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


def _fake_generate(monkeypatch, captured: dict):
    async def _generate(**kwargs):
        captured.update(kwargs)
        return {
            "status": "complete",
            "project_id": kwargs["project_id"],
            "scene_id": kwargs["scene_id"],
            "shots": [],
        }

    monkeypatch.setattr(
        "app.routes.projects._load_project_from_store",
        lambda project_id: {"project_id": project_id, "execution_summary": {}},
    )
    monkeypatch.setattr(
        "app.routes.projects._sync_project_to_canonical_store",
        lambda project: None,
    )
    monkeypatch.setattr(
        "app.routes.projects.scene_production_pipeline_service.generate_scene",
        _generate,
    )


def test_generate_route_carries_confirmed_binding_digests(monkeypatch):
    captured: dict = {}
    _fake_generate(monkeypatch, captured)
    digests = {"scene_001_shot_001": "a" * 64}

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/pipeline/generate",
        json={"expected_reference_binding_digests": digests},
    )

    assert response.status_code == 200
    assert captured["expected_reference_binding_digests"] == digests


def test_generate_route_defaults_to_no_confirmed_digests(monkeypatch):
    captured: dict = {}
    _fake_generate(monkeypatch, captured)

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/pipeline/generate",
        json={},
    )

    assert response.status_code == 200
    assert captured["expected_reference_binding_digests"] is None


def test_generate_route_requires_persisted_confirmation_at_submission(monkeypatch):
    """R4.2: the submission entrypoint always enforces durable confirmations.

    The route passes require_persisted_confirmation=True so reference-bound
    shots without a revalidated server-side record fail closed with zero
    jobs, even when per-submit digests are supplied.
    """
    captured: dict = {}
    _fake_generate(monkeypatch, captured)
    digests = {"scene_001_shot_001": "a" * 64}

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/pipeline/generate",
        json={"expected_reference_binding_digests": digests},
    )

    assert response.status_code == 200
    assert captured["require_persisted_confirmation"] is True
