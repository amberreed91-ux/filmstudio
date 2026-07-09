from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.models import RenderJobModel, RenderJobOutput
from app.services.render import RenderService, set_storage
from app.services.render_job_backfill import hydrate_render_service_from_storage


class _StorageStub:
    def __init__(self, jobs: Optional[list[RenderJobModel]] = None):
        self._jobs: dict[str, RenderJobModel] = {job.id: job for job in (jobs or [])}
        self._projects: dict[str, dict] = {}

    def save_job(self, job: RenderJobModel):
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)

    def list_jobs(self, project_id: Optional[str] = None, status: Optional[str] = None, limit: int = 10000):
        rows = list(self._jobs.values())
        if project_id:
            rows = [row for row in rows if row.project_id == project_id]
        if status:
            rows = [row for row in rows if row.status == status]
        return rows[:limit]

    def save_project(self, project):
        project_id = getattr(project, "project_id", None) or str((project or {}).get("project_id", ""))
        if project_id:
            self._projects[project_id] = {"project_id": project_id}
        return project


class _AdapterComplete:
    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        if job.status == "pending":
            job.status = "rendering"
            job.provider_job_id = job.provider_job_id or f"task-{job.id}"
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        job.status = "complete"
        job.progress = 100
        job.output_payload = RenderJobOutput(asset_url="https://example.com/out.mp4")
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        return True

    async def fetch_outputs(self, job: RenderJobModel):
        return []


def test_restart_recovery_completes_rendering_job(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()

    now = datetime.now().isoformat()
    job = RenderJobModel(
        id="job-restart-1",
        project_id="p1",
        shot_id="shot_1",
        provider="runway",
        provider_job_id="task-123",
        status="rendering",
        progress=45,
        created_at=now,
        updated_at=now,
    )
    service._jobs[job.id] = job
    storage.save_job(job)

    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterComplete())

    result = asyncio.run(service.recover_jobs_after_restart())
    recovered = service.get_job(job.id)

    assert result["recovered_jobs"] == 1
    assert recovered is not None
    assert recovered.status == "complete"
    assert recovered.recovery_status in {"recovered_terminal", "orphan_reconciled"}
    assert recovered.output_payload is not None


def test_stale_task_recovery_without_provider_task_id():
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()

    stale_time = (datetime.now() - timedelta(minutes=30)).isoformat()
    job = RenderJobModel(
        id="job-stale-1",
        project_id="p1",
        shot_id="shot_2",
        provider="simulated",
        status="rendering",
        progress=10,
        created_at=stale_time,
        updated_at=stale_time,
    )
    service._jobs[job.id] = job

    result = asyncio.run(service.recover_jobs_after_restart())
    recovered = service.get_job(job.id)

    assert result["stale_recovered_jobs"] == 1
    assert recovered is not None
    assert recovered.status == "failed"
    assert recovered.recovery_status == "stale_recovered"
    assert "Stale job" in (recovered.error_message or "")


def test_duplicate_submission_prevention(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterComplete())

    job = service.create_job(project_id="p1", shot_id="shot_3", provider="simulated", prompt="test")
    first = asyncio.run(service.submit_job(job.id))
    second = asyncio.run(service.submit_job(job.id))

    assert first.status == "rendering"
    assert second.status == "rendering"
    assert second.provider_job_id == first.provider_job_id


def test_persistence_restoration_hydrates_jobs():
    now = datetime.now().isoformat()
    existing = RenderJobModel(
        id="job-persist-1",
        project_id="p2",
        shot_id="shot_4",
        provider="simulated",
        status="complete",
        progress=100,
        recovery_status="recovered_terminal",
        last_polled_at=now,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    storage = _StorageStub([existing])
    service = RenderService()

    loaded = hydrate_render_service_from_storage(service, storage)
    restored = service.get_job(existing.id)

    assert loaded == 1
    assert restored is not None
    assert restored.recovery_status == "recovered_terminal"
    assert restored.last_polled_at == now
