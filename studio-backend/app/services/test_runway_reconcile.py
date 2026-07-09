from __future__ import annotations

import asyncio

from app.adapters import get_adapter
from app.models import RenderJobInput, RenderJobModel
from app.services.render import RenderService


def _failed_runway_job(job_id: str = "job-1", task_id: str | None = "task-1") -> RenderJobModel:
    metadata = {
        "provider_response_normalized": {
            "provider": "runway",
            "task": "video_generation",
            "status": "failed",
            "output": {"video_url": None, "status": "failed"},
            "metadata": {"task_id": task_id},
        }
    }
    return RenderJobModel(
        id=job_id,
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        provider_job_id=task_id,
        status="failed",
        input_payload=RenderJobInput(shot_id="shot-1", prompt="x", referenceAssets=[], parameters={}),
        output_payload={"asset_url": "", "thumbnail_url": "", "metadata": metadata},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _running_runway_job(job_id: str = "job-running", task_id: str | None = "task-running") -> RenderJobModel:
    return RenderJobModel(
        id=job_id,
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        provider_job_id=task_id,
        status="rendering",
        input_payload=RenderJobInput(shot_id="shot-1", prompt="x", referenceAssets=[], parameters={}),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _pending_runway_job(job_id: str = "job-pending", task_id: str | None = "task-pending") -> RenderJobModel:
    return RenderJobModel(
        id=job_id,
        project_id="proj-1",
        shot_id="shot-1",
        provider="runway",
        provider_job_id=task_id,
        status="pending",
        input_payload=RenderJobInput(shot_id="shot-1", prompt="x", referenceAssets=[], parameters={}),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def test_failed_historical_job_reconciles_successfully(monkeypatch):
    service = RenderService()
    job = _failed_runway_job(task_id="task-123")
    service._jobs[job.id] = job

    class _Adapter:
        async def get_job_status(self, incoming):
            incoming.status = "complete"
            incoming.output_payload.asset_url = "https://cdn.runway/video.mp4"
            incoming.output_payload.thumbnail_url = "https://cdn.runway/preview.jpg"
            incoming.output_payload.metadata = {
                "provider_response_normalized": {
                    "provider": "runway",
                    "task": "video_generation",
                    "status": "completed",
                    "output": {"video_url": "https://cdn.runway/video.mp4", "status": "completed"},
                    "metadata": {"task_id": "task-123", "provider_mode": "hosted_api"},
                }
            }
            return incoming

    monkeypatch.setattr("app.services.render.get_adapter", lambda _provider, _config: _Adapter())

    reconciled = asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert reconciled.status == "complete"
    normalized = reconciled.output_payload.metadata["provider_response_normalized"]
    assert normalized["output"]["video_url"] == "https://cdn.runway/video.mp4"
    assert normalized["metadata"]["provider_status"] == "completed"


def test_missing_task_id_handled_safely():
    service = RenderService()
    job = _failed_runway_job(task_id=None)
    service._jobs[job.id] = job

    reconciled = asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert reconciled.status == "failed"


def test_failed_runway_task_remains_failed(monkeypatch):
    service = RenderService()
    job = _failed_runway_job(task_id="task-999")
    service._jobs[job.id] = job

    class _Adapter:
        async def get_job_status(self, incoming):
            incoming.status = "failed"
            incoming.error_message = "still failed"
            return incoming

    monkeypatch.setattr("app.services.render.get_adapter", lambda _provider, _config: _Adapter())

    reconciled = asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert reconciled.status == "failed"
    assert reconciled.error_message == "still failed"


def test_reconcile_running_job_preserves_running_state(monkeypatch):
    """Polling or reconcile on a running job does NOT change its state to complete."""
    service = RenderService()
    job = _running_runway_job(task_id="task-running")
    service._jobs[job.id] = job

    class _Adapter:
        async def get_job_status(self, incoming):
            # Simulate Runway still running
            incoming.status = "rendering"
            return incoming

    monkeypatch.setattr("app.services.render.get_adapter", lambda _provider, _config: _Adapter())

    reconciled = asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert reconciled.status == "rendering"
    assert reconciled.provider_job_id == "task-running"


def test_reconcile_pending_job_preserves_pending_state(monkeypatch):
    """Reconcile on a pending job keeps it pending."""
    service = RenderService()
    job = _pending_runway_job(task_id="task-pending")
    service._jobs[job.id] = job

    class _Adapter:
        async def get_job_status(self, incoming):
            incoming.status = "pending"
            return incoming

    monkeypatch.setattr("app.services.render.get_adapter", lambda _provider, _config: _Adapter())

    reconciled = asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert reconciled.status == "pending"
    assert reconciled.provider_job_id == "task-pending"


def test_reconcile_succeeded_task_attaches_output_url(monkeypatch):
    """Reconcile hits Runway API, finds completed task, attaches output_url."""
    service = RenderService()
    job = _running_runway_job(task_id="task-long-running")
    service._jobs[job.id] = job

    class _Adapter:
        async def get_job_status(self, incoming):
            # Upstream Runway task finished — ensure output_payload exists
            if incoming.output_payload is None:
                from app.models import RenderJobOutput
                incoming.output_payload = RenderJobOutput(asset_url="", thumbnail_url="", metadata={})
            incoming.status = "complete"
            incoming.output_payload.asset_url = "https://cdn.runway.com/finished.mp4"
            incoming.output_payload.thumbnail_url = "https://cdn.runway.com/thumb.jpg"
            incoming.output_payload.metadata = {
                "provider_response_normalized": {
                    "provider": "runway",
                    "task": "video_generation",
                    "status": "completed",
                    "output": {"video_url": "https://cdn.runway.com/finished.mp4", "status": "completed"},
                    "metadata": {"task_id": "task-long-running"},
                }
            }
            return incoming

    monkeypatch.setattr("app.services.render.get_adapter", lambda _provider, _config: _Adapter())

    reconciled = asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert reconciled.status == "complete"
    assert "finished.mp4" in reconciled.output_payload.asset_url
    normalized = reconciled.output_payload.metadata["provider_response_normalized"]
    assert normalized["metadata"]["provider_status"] == "completed"


def test_reconcile_does_not_resubmit_job(monkeypatch):
    """Reconciling a job must NEVER call submit_job — only get_job_status."""
    service = RenderService()
    job = _running_runway_job(task_id="task-no-resubmit")
    service._jobs[job.id] = job
    submit_called = False

    class _Adapter:
        async def get_job_status(self, incoming):
            incoming.status = "rendering"
            return incoming

        async def submit_job(self, _job):
            nonlocal submit_called
            submit_called = True
            return _job

    monkeypatch.setattr("app.services.render.get_adapter", lambda _provider, _config: _Adapter())

    asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert not submit_called, "reconcile must NOT call submit_job"


def test_reconcile_non_runway_job_returns_unchanged(monkeypatch):
    """Reconcile on a simulated provider job returns it unchanged."""
    service = RenderService()
    job = RenderJobModel(
        id="job-sim",
        project_id="proj-1",
        shot_id="shot-1",
        provider="simulated",
        status="rendering",
        input_payload=RenderJobInput(shot_id="shot-1", prompt="x", referenceAssets=[], parameters={}),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    service._jobs[job.id] = job

    asyncio.run(service.reconcile_completed_runway_task(job.id))
    assert service.get_job(job.id).status == "rendering"
