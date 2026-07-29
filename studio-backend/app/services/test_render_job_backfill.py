from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.project_store import ProjectStore
from app.services.render import RenderService, set_storage
from app.services.render_job_backfill import (
    backfill_render_jobs_from_project_state,
    hydrate_render_service_from_storage,
)


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_project_store(tmp_path: Path) -> ProjectStore:
    store = ProjectStore(str(tmp_path / "project_state_store.json"))
    store.save_project(
        {
            "project_id": "project-1",
            "title": "Backfill Project",
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "multi_shot_execution_ledger": [
                            {
                                "shot_id": "scene_001_shot_001",
                                "shot_render_job_id": "job-20260509155819-scene_001_shot_001",
                                "provider_job_id": "provider-1",
                                "status": "completed",
                                "output_url": "/media/comfyui/historical.mp4",
                                "metadata": {"source": "project_state"},
                                "prompt": "historical prompt",
                            }
                        ],
                    }
                ]
            },
        }
    )
    return store


def test_manual_flow_persists_render_jobs(tmp_path: Path):
    storage = _make_storage(tmp_path)
    set_storage(storage)
    service = RenderService()

    job = service.create_job(project_id="project-1", shot_id="shot-1", prompt="manual")

    persisted = storage.get_job(job.id)
    assert persisted is not None
    assert persisted.id == job.id


def test_startup_hydration_restores_jobs(tmp_path: Path):
    storage = _make_storage(tmp_path)
    job = RenderJobModel(
        id="job-hydrate-1",
        project_id="project-1",
        shot_id="shot-1",
        provider="simulated",
        status="complete",
        input_payload=RenderJobInput(shot_id="shot-1", prompt="test"),
        output_payload=RenderJobOutput(asset_url="/media/comfyui/out.mp4"),
    )
    storage.save_job(job)
    service = RenderService()

    loaded_count = hydrate_render_service_from_storage(service, storage)

    assert loaded_count == 1
    assert service.get_job("job-hydrate-1") is not None


def test_startup_hydration_uses_bounded_default_limit(tmp_path: Path):
    class _Storage:
        limit = None

        def list_jobs(self, limit=0):
            self.limit = limit
            return []

    storage = _Storage()
    service = RenderService()

    loaded_count = hydrate_render_service_from_storage(service, storage)

    assert loaded_count == 0
    assert storage.limit == 1000


def test_backfill_persists_project_state_jobs(tmp_path: Path):
    storage = _make_storage(tmp_path)
    store = _make_project_store(tmp_path)
    service = RenderService()

    result = backfill_render_jobs_from_project_state(storage, service, store)

    assert result["created_count"] == 1
    persisted = storage.get_job("job-20260509155819-scene_001_shot_001")
    assert persisted is not None
    assert persisted.provider_job_id == "provider-1"
    assert persisted.status == "complete"
    assert persisted.output_payload is not None
    assert persisted.output_payload.asset_url == "/media/comfyui/historical.mp4"
    assert service.get_job("job-20260509155819-scene_001_shot_001") is not None


def test_backfill_avoids_duplicates(tmp_path: Path):
    storage = _make_storage(tmp_path)
    store = _make_project_store(tmp_path)

    first = backfill_render_jobs_from_project_state(storage, None, store)
    second = backfill_render_jobs_from_project_state(storage, None, store)

    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["skipped_count"] == 1
    assert len(storage.list_jobs(limit=10)) == 1


def test_reconcile_status_works_after_backfill(tmp_path: Path):
    storage = _make_storage(tmp_path)
    store = _make_project_store(tmp_path)
    service = RenderService()

    backfill_render_jobs_from_project_state(storage, service, store)

    job = service.get_job("job-20260509155819-scene_001_shot_001")
    assert job is not None
    assert job.output_payload is not None
    assert job.output_payload.asset_url == "/media/comfyui/historical.mp4"
