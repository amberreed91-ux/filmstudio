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
    service.run_continuity_review(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
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


@pytest.mark.asyncio
async def test_render_uses_creator_settings_and_retry_preserves_them(tmp_path):
    from app.models.previs_render import PrevisRenderSettings

    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    renderer._provider_configs = {"openrouter-video": {}}
    service = PrevisService(storage, renderer)
    settings = PrevisRenderSettings(prompt="Close on Maya's left hand. She keeps the key.", duration_seconds=8, resolution="1080p", seed=0)
    result = await service.generate_scene("project_previs", "scene_001", provider="openrouter-video", render_settings=settings)
    job = renderer.jobs[result["job_id"]]
    assert job.prompt == settings.prompt
    assert job.parameters["duration"] == 8
    assert job.parameters["resolution"] == "1080p"
    assert job.parameters["seed"] == 0
    storage.update_previs_image_status(job.id, "failed")
    retry = await service.retry_image("project_previs", result["previs_image_id"])
    retried = renderer.jobs[retry["job_id"]]
    assert (retried.prompt, retried.parameters, retried.provider) == (job.prompt, job.parameters, job.provider)


@pytest.mark.asyncio
async def test_approved_board_frame_and_timing_reach_previs_and_direct_render(tmp_path):
    storage = _storage(tmp_path)
    detail = _approved_storyboard(tmp_path, storage)
    shot = detail["shots"][0]
    shot.storyboard_image_url = "https://media.test/approved-closeup.png"
    shot.render_contract.duration_seconds = 8
    shot.render_contract.aspect_ratio = "9:16"
    storage.save_storyboard_shot(shot)
    renderer = FakeRenderer()
    result = await PrevisService(storage, renderer).generate_scene("project_previs", "scene_001", storyboard_shot_id=shot.storyboard_shot_id)
    direct = StoryboardBlueprintService(storage).render_storyboard_shot(blueprint_id=shot.blueprint_id, storyboard_shot_id=shot.storyboard_shot_id, render_service=renderer)
    for job in [renderer.jobs[result["job_id"]], direct]:
        assert job.parameters["duration"] == 8
        assert job.parameters["ratio"] == "9:16"
        assert job.parameters["storyboard_frame_url"] == shot.storyboard_image_url
        assert shot.storyboard_image_url in job.reference_assets


@pytest.mark.asyncio
async def test_previs_rejects_stale_approved_version(tmp_path):
    storage = _storage(tmp_path)
    detail = _approved_storyboard(tmp_path, storage)
    blueprint = detail["blueprint"]
    blueprint.current_version_id = "new-draft-version"
    storage.save_storyboard_blueprint(blueprint)
    renderer = FakeRenderer()
    with pytest.raises(StateError):
        await PrevisService(storage, renderer).generate_scene("project_previs", "scene_001", storyboard_shot_id=detail["shots"][0].storyboard_shot_id)
    assert renderer.created == 0


@pytest.mark.asyncio
async def test_prompt_review_is_terminal_in_previs(tmp_path):
    class ReviewRenderer(FakeRenderer):
        async def submit_job(self, job_id):
            self.jobs[job_id].status = "needs_review"
            self.jobs[job_id].error_message = "Required shot facts exceed the model budget"
            return self.jobs[job_id]

    storage = _storage(tmp_path)
    renderer = ReviewRenderer()
    service = PrevisService(storage, renderer)
    result = await service.generate_scene("project_previs", "scene_001")
    assert result["status"] == "needs_review"
    images = await service.list_scene_images("project_previs", "scene_001", use_video_url_fallback=True)
    assert images[0]["status"] == "needs_review"
    assert renderer.polls == 0


def test_previs_route_validates_and_passes_render_settings(monkeypatch):
    from app.routes import previs_routes

    calls = []
    class RouteService:
        async def generate_scene(self, *args, **kwargs):
            calls.append(kwargs)
            return {"job_id": "j", "status": "pending", "scene_id": "s"}
    monkeypatch.setattr(previs_routes, "previs_service", RouteService())
    app = FastAPI()
    app.include_router(previs_routes.router)
    client = TestClient(app)
    path = "/projects/p/previs/generate-scene/s"
    assert client.post(path, json={"prompt": "Her hand stays closed.", "duration_seconds": 8, "seed": 0}).status_code == 200
    assert calls[0]["render_settings"].duration_seconds == 8
    assert calls[0]["render_settings"].seed == 0
    assert client.post(path, json={"duration_seconds": -1}).status_code == 422
    assert client.post(path, json={"prompt": "   "}).status_code == 422
    assert len(calls) == 1


def test_scene_pipeline_uses_the_same_approved_frame_and_contract(tmp_path, monkeypatch):
    from app.services import storyboard_blueprint_service as storyboard_module
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService
    storage = _storage(tmp_path)
    detail = _approved_storyboard(tmp_path, storage)
    shot = detail["shots"][0]
    shot.storyboard_image_url = "https://media.test/frame.png"
    shot.render_contract.duration_seconds = 9
    storage.save_storyboard_shot(shot)
    monkeypatch.setattr(storyboard_module, "storyboard_blueprint_service", StoryboardBlueprintService(storage))
    project = {"project_id": "project_previs"}
    scene = {"scene_id": "scene_001", "text": "Maya keeps the key."}
    pipeline = SceneProductionPipelineService()
    result = pipeline._resolve_ordered_shots(project, scene)
    assert result[0]["parameters"]["duration"] == 9
    assert result[0]["parameters"]["storyboard_frame_url"] == shot.storyboard_image_url
    assert pipeline._scene_text(scene) == "Maya keeps the key."
    blueprint = detail["blueprint"]
    blueprint.current_version_id = "draft"
    storage.save_storyboard_blueprint(blueprint)
    with pytest.raises(StateError):
        pipeline._resolve_ordered_shots(project, scene)


@pytest.mark.asyncio
async def test_previs_cannot_bypass_storyboard_approval_by_omitting_shot_id(tmp_path):
    storage = _storage(tmp_path)
    detail = _approved_storyboard(tmp_path, storage)
    blueprint = detail["blueprint"]
    blueprint.approved_version_id = None
    storage.save_storyboard_blueprint(blueprint)
    renderer = FakeRenderer()
    with pytest.raises(StateError):
        await PrevisService(storage, renderer).generate_scene("project_previs", "scene_001")
    assert renderer.created == 0


@pytest.mark.asyncio
async def test_explicit_shot_directions_survive_previs_request(tmp_path):
    from app.models.previs_render import PrevisRenderSettings
    renderer = FakeRenderer()
    settings = PrevisRenderSettings(prompt="Maya holds the key.", shot_planning={"blocking": "Her left hand stays closed.", "camera": "Locked close-up."})
    result = await PrevisService(_storage(tmp_path), renderer).generate_scene("project_previs", "scene_001", render_settings=settings)
    job = renderer.jobs[result["job_id"]]
    assert "Her left hand stays closed." in job.prompt
    assert "Locked close-up." in job.prompt
    assert job.parameters["preserve_shot_prompt"]


def test_storyboard_contract_keeps_tail_lighting_before_provider_budget(tmp_path):
    from app.models.storyboard_blueprint import StoryboardShotVisualPlan
    service = StoryboardBlueprintService(_storage(tmp_path))
    prompt = service._build_provider_neutral_prompt("project_previs", {"text": "Maya holds the key. " * 60}, "scene_001_shot_001", 1, 1,
        StoryboardShotVisualPlan(framing="Close-up", environment="Edit bay", lighting="Only red emergency light illuminates her hand."), "The held key carries her refusal.")
    assert len(prompt) > 512
    assert "Only red emergency light illuminates her hand." in prompt
    # Contract assembly normalizes punctuation between components.
    assert prompt.endswith("The held key carries her refusal")


def test_project_save_preserves_approved_storyboard_and_shots(tmp_path):
    storage = _storage(tmp_path)
    detail = _approved_storyboard(tmp_path, storage)
    project = storage.get_project("project_previs")
    project.title = "Updated without losing the approved storyboard"
    storage.save_project(project)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    assert blueprint is not None
    assert blueprint.approved_version_id == detail["version"].version_id
    assert storage.get_storyboard_shot(detail["shots"][0].storyboard_shot_id) is not None


@pytest.mark.asyncio
async def test_production_package_freezes_approved_take_settings(tmp_path):
    from app.models.previs_render import PrevisRenderSettings
    storage = _storage(tmp_path)
    detail = _approved_storyboard(tmp_path, storage)
    shot = detail["shots"][0]
    shot.storyboard_image_url = "https://media.test/approved-frame.png"
    storage.save_storyboard_shot(shot)
    service = PrevisService(storage, FakeRenderer())
    result = await service.generate_scene("project_previs", "scene_001", storyboard_shot_id=shot.storyboard_shot_id,
        render_settings=PrevisRenderSettings(prompt="Her left hand remains closed.", duration_seconds=8, seed=42, resolution="1080p"))
    storage.update_previs_image_status(result["job_id"], "complete", image_path="https://media.test/approved-take.mp4")
    service.approve_image("project_previs", result["previs_image_id"])
    package = service.create_production_package("project_previs", "scene_001")
    row = package["payload"]["shots"][0]
    assert row["prompt"] == "Her left hand remains closed."
    assert row["parameters"]["duration"] == 8
    assert row["parameters"]["seed"] == 42
    assert row["parameters"]["resolution"] == "1080p"
    assert row["parameters"]["storyboard_frame_url"] == shot.storyboard_image_url
    assert row["image_path"] not in row["reference_assets"]
