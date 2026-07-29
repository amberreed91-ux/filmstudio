from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import compose


def _client() -> TestClient:
    api = FastAPI()
    api.include_router(compose.router)
    return TestClient(api)


def _project_with_scene_assembly() -> dict:
    return {
        "project_id": "proj-compose",
        "execution_summary": {
            "scene_pipeline_assemblies": [
                {
                    "assembly_id": "proj-compose_scene_003",
                    "scene_id": "scene_003",
                    "status": "complete",
                    "output_url": "/outputs/scene_assemblies/proj-compose_scene_003_with_audio.mp4",
                    "duration_seconds": 5.5,
                    "clip_count": 2,
                    "shot_ids": ["shot_scene_003_001", "shot_scene_003_002"],
                    "updated_at": "2026-07-18T05:05:15+00:00",
                }
            ],
        },
    }


def test_get_composition_falls_back_to_scene_pipeline_assembly(monkeypatch):
    async def _missing_composition(project_id: str, scene_id: str):
        return None

    monkeypatch.setattr(compose, "get_scene_composition", _missing_composition)
    monkeypatch.setattr(
        "app.services.project_store.project_store.get_project",
        lambda project_id: _project_with_scene_assembly(),
    )

    response = _client().get("/api/f51/studio/projects/proj-compose/scenes/scene_003/composition")

    assert response.status_code == 200
    assert response.json() == {
        "id": "proj-compose_scene_003",
        "project_id": "proj-compose",
        "scene_id": "scene_003",
        "composed_url": "/outputs/scene_assemblies/proj-compose_scene_003_with_audio.mp4",
        "shot_count": 2,
        "duration_seconds": 5.5,
        "created_at": "2026-07-18T05:05:15+00:00",
        "updated_at": "2026-07-18T05:05:15+00:00",
    }


def test_get_composition_keeps_legacy_composition_precedence(monkeypatch):
    legacy = {
        "id": "legacy",
        "project_id": "proj-compose",
        "scene_id": "scene_003",
        "composed_url": "http://localhost:8010/static/composed/proj-compose/scene_003.mp4",
        "shot_count": 3,
        "duration_seconds": 7.0,
        "created_at": "2026-07-17T00:00:00",
        "updated_at": "2026-07-17T00:00:00",
    }

    async def _legacy_composition(project_id: str, scene_id: str):
        return legacy

    monkeypatch.setattr(compose, "get_scene_composition", _legacy_composition)
    monkeypatch.setattr(
        "app.services.project_store.project_store.get_project",
        lambda project_id: _project_with_scene_assembly(),
    )

    response = _client().get("/api/f51/studio/projects/proj-compose/scenes/scene_003/composition")

    assert response.status_code == 200
    assert response.json() == legacy


def test_get_composition_fallback_loads_project_from_sqlite_when_store_is_cold(monkeypatch):
    class FakeStorage:
        def get_project(self, project_id: str):
            return _project_with_scene_assembly()

    async def _missing_composition(project_id: str, scene_id: str):
        return None

    monkeypatch.setattr(compose, "get_scene_composition", _missing_composition)
    monkeypatch.setattr("app.services.project_store.project_store.get_project", lambda project_id: None)
    monkeypatch.setattr(compose.project_persistence_service, "_storage", FakeStorage())

    response = _client().get("/api/f51/studio/projects/proj-compose/scenes/scene_003/composition")

    assert response.status_code == 200
    assert response.json()["composed_url"] == "/outputs/scene_assemblies/proj-compose_scene_003_with_audio.mp4"
    assert response.json()["shot_count"] == 2
