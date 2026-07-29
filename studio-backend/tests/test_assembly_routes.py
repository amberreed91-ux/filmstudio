from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import assembly


def _client() -> TestClient:
    api = FastAPI()
    api.include_router(assembly.router)
    return TestClient(api)


class FakeStorage:
    def __init__(self) -> None:
        self.film = None
        self.saved_film = None
        self.scene_compositions: list[dict] = []

    def get_project(self, project_id: str):
        return None

    def get_film(self, project_id: str):
        return self.film

    def list_scene_compositions_for_project(self, project_id: str):
        return list(self.scene_compositions)

    def save_film(self, **kwargs):
        self.saved_film = kwargs
        self.film = {
            "film_url": kwargs["film_url"],
            "scene_count": kwargs["scene_count"],
            "total_duration_seconds": kwargs["total_duration_seconds"],
            "has_audio": kwargs["has_audio"],
        }
        return self.film


def _project_with_scene_assembly(output_url: str) -> dict:
    return {
        "project_id": "proj-assembly",
        "execution_summary": {
            "scenes": [{"scene_id": "scene_003"}],
            "scene_pipeline_assemblies": [
                {
                    "scene_id": "scene_003",
                    "status": "complete",
                    "output_url": output_url,
                    "duration_seconds": 5.5,
                    "clip_count": 2,
                    "shot_ids": ["shot_scene_003_001", "shot_scene_003_002"],
                    "soundtrack_status": "manual_post_render",
                    "updated_at": "2026-07-18T05:05:15+00:00",
                }
            ],
        },
    }


def test_assembly_status_counts_scene_pipeline_assemblies(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(assembly.assembly_persistence_service, "_storage", storage)
    monkeypatch.setattr(
        "app.services.project_store.project_store.get_project",
        lambda project_id: _project_with_scene_assembly("/outputs/scene_assemblies/proj_scene_003.mp4"),
    )
    assembly._assembly_status.clear()

    response = _client().get("/api/f51/studio/projects/proj-assembly/assembly-status")

    assert response.status_code == 200
    assert response.json() == {
        "scenes_with_compositions": 1,
        "scenes_total": 1,
        "film_assembled": False,
        "film_url": None,
        "has_audio": False,
    }


def test_assemble_film_accepts_local_scene_pipeline_assembly(monkeypatch, tmp_path: Path):
    outputs_root = tmp_path / "outputs"
    scene_dir = outputs_root / "scene_assemblies"
    scene_dir.mkdir(parents=True)
    source_video = scene_dir / "proj_scene_003_with_audio.mp4"
    source_video.write_bytes(b"local-scene-video")
    storage = FakeStorage()
    monkeypatch.setattr(assembly, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(assembly, "FILMS_DIR", tmp_path / "static" / "films")
    monkeypatch.setattr(assembly.assembly_persistence_service, "_storage", storage)
    monkeypatch.setattr(
        "app.services.project_store.project_store.get_project",
        lambda project_id: _project_with_scene_assembly("/outputs/scene_assemblies/proj_scene_003_with_audio.mp4"),
    )
    monkeypatch.setattr(
        assembly.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    assembly._assembly_status.clear()

    response = _client().post("/api/f51/studio/projects/proj-assembly/assemble-film")

    assert response.status_code == 200
    assert response.json()["scene_count"] == 1
    assert response.json()["has_audio"] is True
    assert storage.saved_film["scene_count"] == 1
    assert storage.saved_film["total_duration_seconds"] == 5.5
    assert storage.saved_film["has_audio"] is True
