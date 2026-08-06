from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.previs_service import PrevisService
from app.services.project_store import ProjectStore
from app.services.stability import ProviderError, StateError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService


class FakeRenderer:
    def __init__(self, *, submit_error: bool = False) -> None:
        self.submit_error = submit_error
        self.jobs: dict[str, SimpleNamespace] = {}
        self.created = 0
        self.polls = 0

    def create_job(self, **kwargs):
        self.created += 1
        job_id = f"previs-job-{self.created}"
        provider = kwargs.pop("provider", "simulated")
        job = SimpleNamespace(
            id=job_id,
            status="pending",
            provider=provider,
            output_payload=None,
            error_message=None,
            **kwargs,
        )
        self.jobs[job_id] = job
        return job

    async def submit_job(self, job_id: str):
        if self.submit_error:
            raise RuntimeError("provider unavailable")
        return self.jobs[job_id]

    async def get_job_status(self, job_id: str):
        self.polls += 1
        return self.jobs[job_id]

    async def cancel_job(self, job_id: str) -> bool:
        self.jobs[job_id].status = "cancelled"
        return True


def _storage(tmp_path: Path, project_id: str = "project_previs") -> DatabaseStorage:
    storage = DatabaseStorage(str(tmp_path / "previs-db"))
    storage.save_project(
        StudioProject(
            project_id=project_id,
            title="Checkpoint 4 Previs",
            execution_summary={
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "heading": "INT. EDIT BAY - NIGHT",
                        "description": "Maya holds the cut one breath longer.",
                        "location": "Edit bay",
                        "time_of_day": "night",
                        "emotional_tone": "contained dread",
                        "characters": ["MAYA"],
                    }
                ]
            },
        )
    )
    return storage


def _approved_storyboard(tmp_path: Path, storage: DatabaseStorage) -> dict:
    state = ProjectStore(str(tmp_path / "storyboard-state.json"))
    state.save_project(
        {
            "project_id": "project_previs",
            "title": "Checkpoint 4 Previs",
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "description": "Maya holds the cut one breath longer.",
                        "location": "Edit bay",
                        "characters": ["MAYA"],
                    }
                ]
            },
        }
    )
    service = StoryboardBlueprintService(storage)
    service.project_store = state
    detail = service.get_or_create_blueprint(
        project_id="project_previs",
        scene_id="scene_001",
        shot_count=1,
    )
    return service.approve_version(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )


@pytest.mark.asyncio
async def test_generation_uses_canonical_scene_and_is_idempotent_across_restart(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)

    first = await service.generate_scene("project_previs", "scene_001")
    duplicate = await service.generate_scene("project_previs", "scene_001")
    restarted = await PrevisService(storage, renderer).generate_scene("project_previs", "scene_001")

    assert first["job_id"] == duplicate["job_id"] == restarted["job_id"]
    assert duplicate["duplicate"] is True
    assert renderer.created == 1
    with pytest.raises(StateError):
        await service.generate_scene("project_previs", "scene_missing")
    with pytest.raises(StateError):
        await service.generate_scene("wrong_project", "scene_001")


@pytest.mark.asyncio
async def test_submission_failure_is_persisted_and_propagated(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer(submit_error=True)
    service = PrevisService(storage, renderer)

    with pytest.raises(ProviderError) as raised:
        await service.generate_scene("project_previs", "scene_001")

    record = storage.get_previs_image_by_job("previs-job-1")
    assert raised.value.error_type == "provider_error"
    assert record is not None
    assert record["status"] == "failed"
    assert record["failure_reason"] == "Provider submission failed"


@pytest.mark.asyncio
async def test_polling_demotes_complete_without_asset_and_stops_at_terminal_state(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)
    created = await service.generate_scene("project_previs", "scene_001")
    renderer.jobs[created["job_id"]].status = "complete"

    first = await service.list_scene_images(
        "project_previs", "scene_001", use_video_url_fallback=True
    )
    second = await service.list_scene_images(
        "project_previs", "scene_001", use_video_url_fallback=True
    )

    assert first[0]["status"] == "failed"
    assert "without an output" in first[0]["failure_reason"]
    assert second[0]["status"] == "failed"
    assert renderer.polls == 1


@pytest.mark.asyncio
async def test_approved_previs_requires_explicit_revision_and_preserves_history(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)
    created = await service.generate_scene("project_previs", "scene_001")
    storage.update_previs_image_status(created["job_id"], "complete", image_path="https://media.test/previs.mp4")
    approved = service.approve_image("project_previs", created["previs_image_id"], "amber")

    with pytest.raises(StateError):
        await service.generate_scene("project_previs", "scene_001")

    revision = await service.generate_scene(
        "project_previs",
        "scene_001",
        allow_approved_revision=True,
    )
    original = service.get_image("project_previs", approved["id"])
    assert revision["job_id"] != approved["job_id"]
    assert original["approved"] is True
    assert original["approved_by"] == "amber"


@pytest.mark.asyncio
async def test_cancel_and_retry_create_a_traceable_new_attempt(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)
    created = await service.generate_scene("project_previs", "scene_001")

    cancelled = await service.cancel_image("project_previs", created["previs_image_id"])
    retried = await service.retry_image("project_previs", cancelled["id"])
    retry_record = service.get_image("project_previs", retried["previs_image_id"])

    assert cancelled["status"] == "cancelled"
    assert retry_record["attempt_number"] == 2
    assert retry_record["source_previs_image_id"] == cancelled["id"]
    assert retry_record["job_id"] != cancelled["job_id"]


@pytest.mark.asyncio
async def test_storyboard_provenance_and_package_survive_reload(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    approved_storyboard = _approved_storyboard(tmp_path, storage)
    shot = approved_storyboard["shots"][0]
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)

    generated = await service.generate_scene(
        "project_previs",
        "scene_001",
        storyboard_shot_id=shot.storyboard_shot_id,
    )
    storage.update_previs_image_status(
        generated["job_id"], "complete", image_path="https://media.test/approved-previs.mp4"
    )
    service.approve_image("project_previs", generated["previs_image_id"])
    package = service.create_production_package("project_previs", "scene_001")

    reloaded = PrevisService(storage, renderer)
    persisted_image = reloaded.get_image("project_previs", generated["previs_image_id"])
    persisted_package = storage.get_previs_production_package(package["package_id"])
    assert persisted_image["blueprint_id"] == shot.blueprint_id
    assert persisted_image["blueprint_version_id"] == shot.version_id
    assert persisted_image["storyboard_shot_id"] == shot.storyboard_shot_id
    assert persisted_package is not None
    assert persisted_package["blueprint_version_id"] == shot.version_id
    assert persisted_package["payload"]["shots"][0]["previs_image_id"] == persisted_image["id"]


def test_previs_route_contract_passes_storyboard_provenance(monkeypatch) -> None:
    from app.routes import previs_routes

    class RouteService:
        async def generate_scene(self, project_id, scene_id, shot_number, take_number, **kwargs):
            assert (project_id, scene_id, shot_number, take_number) == (
                "project_previs", "scene_001", 2, 3
            )
            assert kwargs == {
                "storyboard_shot_id": "storyboard-shot-1",
                "allow_approved_revision": True,
            }
            return {
                "job_id": "job-route",
                "status": "pending",
                "scene_id": scene_id,
                "previs_image_id": "previs-route",
                "storyboard_shot_id": "storyboard-shot-1",
            }

    monkeypatch.setattr(previs_routes, "previs_service", RouteService())
    app = FastAPI()
    app.include_router(previs_routes.router)
    client = TestClient(app)
    response = client.post(
        "/projects/project_previs/previs/generate-scene/scene_001",
        params={
            "shot_number": 2,
            "take_number": 3,
            "storyboard_shot_id": "storyboard-shot-1",
            "allow_approved_revision": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["previs_image_id"] == "previs-route"


def test_previs_route_maps_provider_failure_without_leaking_raw_error(monkeypatch) -> None:
    from app.routes import previs_routes

    class FailingRouteService:
        async def generate_scene(self, *args, **kwargs):
            raise ProviderError(
                "Previs provider submission failed",
                stage="previs_submit",
                metadata={"cause": "TimeoutError"},
            )

    monkeypatch.setattr(previs_routes, "previs_service", FailingRouteService())
    app = FastAPI()
    app.include_router(previs_routes.router)
    response = TestClient(app).post(
        "/projects/project_previs/previs/generate-scene/scene_001"
    )
    assert response.status_code == 502
    assert response.json()["detail"]["error_type"] == "provider_error"
    assert "Traceback" not in response.text
