"""Guard: direct save_job writers cannot authorize production state (R4.3I / D1).

Owner decision D1 (Oct 15, 2026): the five direct ``save_job`` writers
outside the render-service create path are non-authorization writers;
no change. This file pins that decision with synthetic data only
(tmp SQLite, no provider calls, no network):

- the storage choke point (``DatabaseStorage.save_job``) fails closed for
  contract-less ``runway_router`` rows, so no writer can persist
  unauthorized router state even if it tried;
- ``submitted`` is a runtime-only alias that persists as ``pending``;
- the one writer that can create rows (project-state backfill) records a
  contract-less router row as an error instead of creating it;
- the queue cancel-sync writer only moves existing pending/rendering jobs
  to ``cancelled`` and never touches provider;
- the maintenance recovery writer only recovers simulated/local output
  placeholders or demotes to ``failed``, never authoring router state.
"""

from __future__ import annotations

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobModel, StudioProject


def _storage(tmp_path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "guard-storage"))


def _job(job_id: str, *, provider: str = "simulated", status: str = "pending") -> RenderJobModel:
    return RenderJobModel(
        id=job_id,
        project_id="guard-project",
        shot_id="scene_001_shot_001",
        provider=provider,
        status=status,
    )


# ── Storage choke point: contract-less router rows fail closed ──────────────


def test_save_job_rejects_contractless_router_insert(tmp_path):
    storage = _storage(tmp_path)
    with pytest.raises(RuntimeError, match="frozen contract"):
        storage.save_job(_job("job-router-guard-1", provider="runway_router"))
    assert storage.get_job("job-router-guard-1") is None


def test_save_job_rejects_router_provider_flip_on_update(tmp_path):
    storage = _storage(tmp_path)
    storage.save_job(_job("job-flip-guard-1", provider="simulated", status="pending"))
    flipped = _job("job-flip-guard-1", provider="runway_router", status="pending")
    with pytest.raises(RuntimeError, match="frozen contract"):
        storage.save_job(flipped)
    persisted = storage.get_job("job-flip-guard-1")
    assert persisted is not None
    assert persisted.provider == "simulated"


def test_save_job_normalizes_submitted_to_pending(tmp_path):
    # "submitted" is a runtime-only alias: it persists as "pending" and is
    # never stored verbatim, so no writer can leave a "submitted" row behind.
    storage = _storage(tmp_path)
    job = _job("job-submitted-guard-1", status="submitted")
    storage.save_job(job)
    assert job.status == "submitted"
    with storage._get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM render_jobs WHERE id = ?", (job.id,)
        ).fetchone()
    assert row["status"] == "pending"


# ── Backfill (the one writer that can create rows) fails closed ─────────────


def test_backfill_cannot_create_contractless_router_row(tmp_path):
    from app.services.project_store import ProjectStore
    from app.services.render_job_backfill import backfill_render_jobs_from_project_state

    storage = _storage(tmp_path)
    store = ProjectStore(str(tmp_path / "guard_project_state.json"))
    store.save_project(
        {
            "project_id": "guard-project",
            "title": "Guard Project",
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "multi_shot_execution_ledger": [
                            {
                                "shot_id": "scene_001_shot_001",
                                "shot_render_job_id": "job-router-backfill-guard",
                                "provider": "runway_router",
                                "provider_job_id": "synthetic-task-1",
                                "status": "completed",
                                "output_url": "https://example.invalid/synthetic.mp4",
                                "prompt": "synthetic guard prompt",
                            }
                        ],
                    }
                ]
            },
        }
    )

    result = backfill_render_jobs_from_project_state(storage, None, store)

    assert result["created_count"] == 0
    assert storage.get_job("job-router-backfill-guard") is None
    assert any(
        "job-router-backfill-guard" in error and "frozen contract" in error
        for error in result["errors"]
    )


# ── Queue cancel sync only cancels existing pending/rendering jobs ───────────


class _GuardRenderService:
    def __init__(self, jobs):
        self._jobs = {job.id: job for job in jobs}

    def get_job(self, job_id):
        return self._jobs.get(job_id)


def test_queue_cancel_sync_never_authorizes_provider_or_success(tmp_path):
    from app.services.production_queue_service import ProductionQueueService

    storage = _storage(tmp_path)
    storage.save_project(StudioProject(project_id="guard-project", title="Guard Project"))
    rendering = _job("job-cancel-guard-1", provider="simulated", status="rendering")
    complete = _job("job-cancel-guard-2", provider="simulated", status="complete")
    storage.save_job(rendering)
    storage.save_job(complete)

    service = ProductionQueueService(
        storage=storage,
        render_svc=_GuardRenderService([rendering, complete]),
        worker_owner_id="guard-test",
    )
    rendering_item = service.enqueue_existing_render_job(job_id=rendering.id)
    complete_item = service.enqueue_existing_render_job(job_id=complete.id)

    service.cancel_item(rendering_item.queue_item_id, reason="guard probe")
    service.cancel_item(complete_item.queue_item_id, reason="guard probe")

    assert storage.get_job(rendering.id).status == "cancelled"
    assert storage.get_job(rendering.id).provider == "simulated"
    assert storage.get_job(complete.id).status == "complete"
    assert storage.get_job(complete.id).provider == "simulated"
    assert len(storage.list_jobs()) == 2


# ── Maintenance recovery never authors router or success state ───────────────


def test_recover_output_urls_never_authors_router_or_success(tmp_path, monkeypatch):
    import app.services.render as render_module
    from app.services.render_maintenance_service import RenderMaintenanceService

    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    storage.save_job(_job("job-recover-guard-1", provider="simulated", status="complete"))
    storage.save_job(_job("job-demote-guard-1", provider="runway", status="complete"))

    result = RenderMaintenanceService().recover_output_urls()

    assert result == {"recovered": 1, "demoted": 1, "skipped": 0, "total_checked": 2}
    recovered = storage.get_job("job-recover-guard-1")
    assert recovered.provider == "simulated"
    assert recovered.status == "complete"
    assert recovered.output_payload is not None
    assert recovered.output_payload.asset_url
    demoted = storage.get_job("job-demote-guard-1")
    assert demoted.provider == "runway"
    assert demoted.status == "failed"
    for job in storage.list_jobs():
        assert job.provider != "runway_router"
        assert job.status != "submitted"
