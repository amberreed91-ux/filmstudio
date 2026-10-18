from __future__ import annotations

import asyncio

import pytest

from app.data.storage import DatabaseStorage
from app.models.production_queue import (
    ProductionQueueDependencyCreate,
    ProductionQueueDependencyType,
    ProductionQueueItem,
    ProductionQueueItemCreate,
    ProductionQueueStatus,
    ProductionQueueWorkType,
)
from app.services.production_queue_service import ProductionQueueService


def _lease_item(storage, service, item, *, lease_seconds=60):
    from datetime import datetime, timedelta

    now = datetime.now()
    claimed = storage.acquire_queue_lease_for_item(
        queue_item_id=item.queue_item_id,
        owner_id=service.worker_owner_id,
        now=now.isoformat(),
        lease_expires_at=(now + timedelta(seconds=lease_seconds)).isoformat(),
    )
    assert claimed is not None
    return claimed


class _FakeRenderJob:
    project_id = "project_q"
    shot_id = "shot_001"
    provider = "simulated"
    id = "job_001"
    status = "pending"
    error_message = None

    class _Input:
        prompt = "A precise cinematic shot."
        parameters = {"scene_id": "scene_001"}

    input_payload = _Input()


class _FakeRenderService:
    def __init__(self):
        self.job = _FakeRenderJob()
        self.created = []

    def get_job(self, job_id):
        return self.job if job_id == self.job.id else None

    def create_job(self, project_id, shot_id, provider=None, prompt="", reference_assets=None, parameters=None):
        job = type("FakeCreatedRenderJob", (), {})()
        job.id = f"job_{shot_id}"
        job.project_id = project_id
        job.shot_id = shot_id
        job.provider = provider or "simulated"
        job.status = "pending"
        job.error_message = None
        job.input_payload = type("FakeInput", (), {"prompt": prompt, "parameters": parameters or {}})()
        self.created.append(job)
        return job


def test_queue_dispatch_of_disabled_provider_fails_closed(tmp_path, monkeypatch):
    from app.models import RenderJobModel, StudioProject
    from app.services import render as render_module

    storage = DatabaseStorage(str(tmp_path))
    storage.save_project(StudioProject(project_id="project_q", title="Queue test"))
    service = render_module.RenderService()
    job = RenderJobModel(
        id="disabled-queue-job",
        project_id="project_q",
        shot_id="scene_001_shot_001",
        provider="runway",
    )
    storage.save_job(job)
    service._jobs[job.id] = job
    service._provider_configs["runway"].enabled = False
    monkeypatch.setattr(render_module, "_storage", storage)
    queue_service = ProductionQueueService(storage=storage, render_svc=service, worker_owner_id="test-disabled")
    item = queue_service.enqueue_existing_render_job(job_id=job.id)
    item = _lease_item(storage, queue_service, item)
    result = asyncio.run(queue_service.execute_leased_item(item))

    assert result["status"] == "failed"
    assert service.get_job(job.id).provider == "runway"
    assert service.get_job(job.id).status == "failed"
    with storage._get_connection() as conn:
        attempt = conn.execute(
            "SELECT status, error_message FROM production_queue_attempts WHERE queue_item_id = ?",
            (item.queue_item_id,),
        ).fetchone()
    assert attempt["status"] == "failed"
    assert "disabled" in attempt["error_message"]


def test_queue_item_creation_is_idempotent(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")

    payload = ProductionQueueItemCreate(
        project_id="project_q",
        work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
        canonical_type="custom_workflow",
        canonical_id="workflow_1",
        idempotency_key="workflow_1",
        priority=80,
    )

    first = service.enqueue_item(payload)
    second = service.enqueue_item(payload)

    assert second.queue_item_id == first.queue_item_id
    summary = service.summarize("project_q")
    assert summary.counts_by_status == {"queued": 1}


def test_existing_render_job_can_be_attached_to_queue(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(
        storage=storage,
        render_svc=_FakeRenderService(),
        worker_owner_id="test-owner",
    )

    item = service.enqueue_existing_render_job(job_id="job_001", priority=70)

    assert item.work_type == "render_job"
    assert item.canonical_type == "render_job"
    assert item.canonical_id == "job_001"
    assert item.provider == "simulated"
    assert item.priority == 70


def test_provider_capacity_defers_ready_item(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    monkeypatch.setattr(service, "_provider_limit", lambda provider: 0)
    service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="workflow_1",
            provider="runway",
            idempotency_key="workflow_1",
        )
    )

    result = asyncio.run(service.run_once())

    assert result["status"] == "idle"
    item = service.list_items(project_id="project_q").items[0]
    assert item.status == "waiting_provider"
    assert item.reason == "Provider capacity is full."


def test_queue_summary_reports_configured_provider_limit(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    monkeypatch.setattr(service, "_provider_limits", lambda: {"runway": 3})
    service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="workflow_1",
            provider="runway",
            idempotency_key="workflow_1",
        )
    )

    summary = service.summarize("project_q")

    pressure = summary.provider_pressure[0]
    assert pressure.provider == "runway"
    assert pressure.limit == 3
    assert pressure.status == "available"


def test_large_queue_fixture_pages_without_dropping_same_timestamp_rows(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    created_at = "2026-07-27T00:00:00"
    total_items = 1200
    for index in range(total_items):
        storage.create_queue_item(
            ProductionQueueItem(
                queue_item_id=f"pqi_{index:04d}",
                project_id="feature_project",
                scene_id=f"scene_{index // 10:03d}",
                shot_id=f"shot_{index:04d}",
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id=f"job_{index:04d}",
                provider="runway" if index % 2 else "simulated",
                status=ProductionQueueStatus.QUEUED,
                priority=index % 100,
                idempotency_key=f"feature_project:{index:04d}",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    first_page = service.list_items(project_id="feature_project", limit=200)
    second_page = service.list_items(project_id="feature_project", cursor=first_page.next_cursor, limit=200)
    summary = service.summarize("feature_project")

    assert first_page.total_visible == 200
    assert second_page.total_visible == 200
    assert first_page.has_more is True
    assert second_page.has_more is True
    assert set(item.queue_item_id for item in first_page.items).isdisjoint(
        item.queue_item_id for item in second_page.items
    )
    assert summary.counts_by_status == {"queued": total_items}


def test_scene_generation_expands_to_render_audio_and_stitch_items(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    fake_render = _FakeRenderService()
    service = ProductionQueueService(storage=storage, render_svc=fake_render, worker_owner_id="test-owner")
    project = {
        "project_id": "project_q",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "description": "A quiet hallway before the confrontation.",
                    "shots": [
                        {"shot_id": "scene_001_shot_001", "description": "The door handle turns."},
                        {"shot_id": "scene_001_shot_002", "description": "A face catches the light."},
                    ],
                }
            ]
        },
    }

    result = service.enqueue_scene_generation(
        project_id="project_q",
        scene_id="scene_001",
        project=project,
        provider="simulated",
        priority=60,
    )

    assert len(result["render_items"]) == 2
    assert len(result["audio_items"]) == 2
    assert result["stitch_item"].work_type == "scene_stitch"
    stitch_deps = storage.list_queue_dependencies(result["stitch_item"].queue_item_id)
    assert len(stitch_deps) == 2
    assert {dep.depends_on_id for dep in stitch_deps} == {
        item.queue_item_id for item in result["audio_items"]
    }


def test_queue_retry_classification_dead_letters_permanent_render_failure(tmp_path):
    from types import SimpleNamespace

    from app.services.stability import ProviderError

    storage = DatabaseStorage(str(tmp_path))
    render_job = SimpleNamespace(
        id="job-permanent-failure",
        status="pending",
        metadata={
            "provider_failure": {
                "error_type": "invalid_api_key",
                "retryable": False,
            }
        },
    )

    class _FailingRenderService:
        def get_job(self, _job_id):
            return render_job

        async def submit_job(self, _job_id):
            raise ProviderError("Invalid API key", stage="provider_submission")

    service = ProductionQueueService(
        storage=storage,
        render_svc=_FailingRenderService(),
        worker_owner_id="test-permanent-failure",
    )
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.RENDER_JOB,
            canonical_type="render_job",
            canonical_id=render_job.id,
            provider="runway_router",
            idempotency_key="permanent-render-failure",
        )
    )
    item = _lease_item(storage, service, item)

    result = asyncio.run(service.execute_leased_item(item))

    assert result["status"] == "failed"
    assert service.get_item(item.queue_item_id).status == ProductionQueueStatus.DEAD_LETTERED
    assert service.get_item(item.queue_item_id).failure["retryable"] is False


def test_queue_retry_classification_keeps_transient_render_failure_retryable(tmp_path):
    from types import SimpleNamespace

    from app.services.stability import ProviderError

    storage = DatabaseStorage(str(tmp_path))
    render_job = SimpleNamespace(
        id="job-transient-failure",
        status="pending",
        metadata={
            "provider_failure": {
                "error_type": "rate_limit",
                "retryable": True,
            }
        },
    )

    class _FailingRenderService:
        def get_job(self, _job_id):
            return render_job

        async def submit_job(self, _job_id):
            raise ProviderError("Provider rate limit reached", stage="provider_submission")

    service = ProductionQueueService(
        storage=storage,
        render_svc=_FailingRenderService(),
        worker_owner_id="test-transient-failure",
    )
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.RENDER_JOB,
            canonical_type="render_job",
            canonical_id=render_job.id,
            provider="runway_router",
            idempotency_key="transient-render-failure",
        )
    )
    item = _lease_item(storage, service, item)

    result = asyncio.run(service.execute_leased_item(item))

    assert result["status"] == "failed"
    updated = service.get_item(item.queue_item_id)
    assert updated.status == ProductionQueueStatus.FAILED
    assert updated.failure["category"] == "rate_limit"
    assert updated.failure["retryable"] is True


def test_queue_worker_completes_inspection_only_work_and_records_events(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="workflow_1",
            idempotency_key="workflow_1",
        )
    )

    result = asyncio.run(service.run_once())

    assert result["status"] == "executed"
    updated = service.get_item(item.queue_item_id)
    assert updated is not None
    assert updated.status == "complete"
    events = service.list_events(item.queue_item_id)
    assert {event.event_type for event in events} >= {"queued", "lease_acquired", "dispatch_completed"}


def test_queue_dependency_blocks_until_required_item_completes(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    parent = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="parent",
            idempotency_key="parent",
        )
    )
    child = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="child",
            idempotency_key="child",
            priority=90,
            dependencies=[
                ProductionQueueDependencyCreate(
                    depends_on_type=ProductionQueueDependencyType.QUEUE_ITEM,
                    depends_on_id=parent.queue_item_id,
                    required_status="complete",
                )
            ],
        )
    )

    result = asyncio.run(service.run_once())

    assert result["status"] in {"idle", "executed"}
    blocked = service.get_item(child.queue_item_id)
    assert blocked is not None
    assert blocked.status in {"waiting_dependency", "queued"}

    asyncio.run(service.run_once())
    service.refresh_waiting_dependencies()
    asyncio.run(service.run_once())

    assert service.get_item(parent.queue_item_id).status == "complete"
    assert service.get_item(child.queue_item_id).status == "complete"


def test_expired_lease_returns_item_to_queue(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="workflow_1",
            idempotency_key="workflow_1",
        )
    )
    leased = storage.acquire_queue_lease(
        owner_id="other-owner",
        now="2026-01-01T00:00:00",
        lease_expires_at="2026-01-01T00:00:01",
    )
    assert leased is not None

    recovered = storage.expire_stale_queue_leases("2026-01-01T00:00:02")

    assert recovered == 1
    updated = service.get_item(item.queue_item_id)
    assert updated is not None
    assert updated.status == "queued"


def test_lease_renewal_requires_current_owner_live_lease_and_future_expiry(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="lease-owner")
    now = "2026-01-01T00:00:00"
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="workflow_lease_renewal",
            idempotency_key="lease-renewal",
        )
    )
    now = __import__("datetime").datetime.now()
    lease_expiry = (now + __import__("datetime").timedelta(seconds=1)).isoformat()
    leased = storage.acquire_queue_lease_for_item(
        queue_item_id=item.queue_item_id,
        owner_id="lease-owner",
        now=now.isoformat(),
        lease_expires_at=lease_expiry,
    )
    assert leased is not None
    generation = leased.lease_generation

    extension = (now + __import__("datetime").timedelta(seconds=5)).isoformat()
    assert storage.renew_queue_lease(item.queue_item_id, "lease-owner", generation, extension) is True
    assert storage.renew_queue_lease(item.queue_item_id, "lease-owner", generation, lease_expiry) is True
    assert service.get_item(item.queue_item_id).lease_expires_at == extension
    assert storage.renew_queue_lease(item.queue_item_id, "other-owner", generation, (now + __import__("datetime").timedelta(seconds=10)).isoformat()) is False
    assert storage.renew_queue_lease(item.queue_item_id, "lease-owner", generation, "2000-01-01T00:00:00") is False
    assert storage.renew_queue_lease(item.queue_item_id, "lease-owner", generation + 1, (now + __import__("datetime").timedelta(seconds=10)).isoformat()) is False

    recovered = storage.expire_stale_queue_leases("2100-01-01T00:00:00")
    assert recovered == 1
    assert storage.renew_queue_lease(item.queue_item_id, "lease-owner", generation, "2101-01-01T00:00:00") is False


def test_heartbeat_renews_live_lease_and_rejects_terminal_or_superseded_lease(tmp_path):
    from datetime import datetime, timedelta

    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="heartbeat-owner")
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="heartbeat-item",
            idempotency_key="heartbeat-item",
        )
    )
    item = _lease_item(storage, service, item, lease_seconds=30)
    original_expiry = item.lease_expires_at

    assert storage.renew_queue_lease(
        item.queue_item_id,
        service.worker_owner_id,
        item.lease_generation,
        (datetime.now() + timedelta(seconds=120)).isoformat(),
    ) is True
    renewed = service.get_item(item.queue_item_id)
    assert renewed.lease_expires_at > original_expiry
    assert renewed.status == ProductionQueueStatus.RUNNING
    stale_worker = ProductionQueueService(storage=storage, worker_owner_id="superseded-worker")
    storage.expire_stale_queue_leases("9999-01-01T00:00:00")
    recovered = service.get_item(item.queue_item_id)
    assert recovered.status == ProductionQueueStatus.QUEUED
    replacement = _lease_item(storage, stale_worker, recovered)
    assert replacement.lease_generation == item.lease_generation + 1
    assert storage.renew_queue_lease(
        item.queue_item_id,
        service.worker_owner_id,
        item.lease_generation,
        (datetime.now() + timedelta(seconds=60)).isoformat(),
    ) is False


def test_long_execution_heartbeat_extends_lease_without_shortening_it(tmp_path):
    async def exercise():
        storage = DatabaseStorage(str(tmp_path))
        service = ProductionQueueService(storage=storage, worker_owner_id="heartbeat-worker")
        service.heartbeat_interval_seconds = 0.02
        from types import SimpleNamespace

        job = SimpleNamespace(id="heartbeat-render", status="pending", metadata={}, error_message=None)

        class _SlowRenderService:
            def get_job(self, _job_id):
                return job

            async def submit_job(self, _job_id):
                await asyncio.sleep(0.15)
                return SimpleNamespace(id=job.id, status="complete", metadata={}, error_message=None)

        service.set_render_service(_SlowRenderService())
        item = service.enqueue_item(
            ProductionQueueItemCreate(
                project_id="project_q",
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id=job.id,
                idempotency_key="slow-workflow",
            )
        )
        item = _lease_item(storage, service, item, lease_seconds=2)
        service.lease_seconds = 3
        initial_expiry = service.get_item(item.queue_item_id).lease_expires_at
        task = asyncio.create_task(service.execute_leased_item(item))
        await asyncio.sleep(0.07)
        renewed_expiry = service.get_item(item.queue_item_id).lease_expires_at
        assert renewed_expiry > initial_expiry
        result = await task
        assert result["status"] == "complete"
        assert service.get_item(item.queue_item_id).status == ProductionQueueStatus.COMPLETE

    asyncio.run(exercise())


def test_heartbeat_loss_during_execution_blocks_result_after_recovery_and_reclaim(tmp_path):
    async def exercise():
        from types import SimpleNamespace

        storage = DatabaseStorage(str(tmp_path))
        entered = asyncio.Event()
        release = asyncio.Event()

        class _SlowRenderService:
            def get_job(self, _job_id):
                return SimpleNamespace(id="heartbeat-loss-job", status="pending", metadata={}, error_message=None)

            async def submit_job(self, _job_id):
                entered.set()
                await release.wait()
                return SimpleNamespace(id="heartbeat-loss-job", status="complete", metadata={}, error_message=None)

        first = ProductionQueueService(storage=storage, render_svc=_SlowRenderService(), worker_owner_id="heartbeat-lost")
        first.heartbeat_interval_seconds = 0.01
        item = first.enqueue_item(
            ProductionQueueItemCreate(
                project_id="project_q",
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id="heartbeat-loss-job",
                idempotency_key="heartbeat-loss-job",
            )
        )
        item = _lease_item(storage, first, item)
        execution = asyncio.create_task(first.execute_leased_item(item))
        await entered.wait()

        assert storage.expire_stale_queue_leases("9999-01-01T00:00:00") == 1
        await asyncio.sleep(0.03)
        assert (item.queue_item_id, item.lease_generation) in first._heartbeat_lost_items
        replacement_worker = ProductionQueueService(storage=storage, worker_owner_id="heartbeat-replacement")
        replacement = _lease_item(storage, replacement_worker, first.get_item(item.queue_item_id))

        release.set()
        result = await execution
        assert result["status"] == "lease_lost"
        current = storage.get_queue_item(item.queue_item_id)
        assert current.lease_owner == replacement_worker.worker_owner_id
        assert current.lease_generation == replacement.lease_generation

    asyncio.run(exercise())


def test_cancellation_during_execution_fences_stale_completion(tmp_path):
    async def exercise():
        from types import SimpleNamespace

        storage = DatabaseStorage(str(tmp_path))
        entered = asyncio.Event()
        release = asyncio.Event()

        class _SlowRenderService:
            def get_job(self, _job_id):
                return SimpleNamespace(id="cancel-race-job", status="pending", metadata={}, error_message=None)

            async def submit_job(self, _job_id):
                entered.set()
                await release.wait()
                return SimpleNamespace(id="cancel-race-job", status="complete", metadata={}, error_message=None)

        worker = ProductionQueueService(
            storage=storage,
            render_svc=_SlowRenderService(),
            worker_owner_id="cancel-race-worker",
        )
        worker.heartbeat_interval_seconds = 60
        item = worker.enqueue_item(
            ProductionQueueItemCreate(
                project_id="project_q",
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id="cancel-race-job",
                idempotency_key="cancel-race-job",
            )
        )
        item = _lease_item(storage, worker, item)
        execution = asyncio.create_task(worker.execute_leased_item(item))
        await entered.wait()

        cancelled = worker.cancel_item(item.queue_item_id, "Creator cancelled this render")
        assert cancelled.status == ProductionQueueStatus.CANCELLED
        release.set()
        result = await execution

        assert result["status"] == "cancelled"
        persisted = storage.get_queue_item(item.queue_item_id)
        assert persisted.status == ProductionQueueStatus.CANCELLED
        assert storage.list_queue_attempts(item.queue_item_id)[0].status == "cancelled"

    asyncio.run(exercise())


def test_expired_lease_during_execution_blocks_stale_completion_and_recovery_allows_reclaim(tmp_path):
    async def exercise():
        from types import SimpleNamespace

        storage = DatabaseStorage(str(tmp_path))
        entered = asyncio.Event()
        release = asyncio.Event()

        class _SlowRenderService:
            def get_job(self, _job_id):
                return SimpleNamespace(id="slow-job", status="pending", metadata={}, error_message=None)

            async def submit_job(self, _job_id):
                entered.set()
                await release.wait()
                return SimpleNamespace(id="slow-job", status="rendering", metadata={}, error_message=None)

        first_worker = ProductionQueueService(
            storage=storage, render_svc=_SlowRenderService(), worker_owner_id="first-worker"
        )
        second_worker = ProductionQueueService(storage=storage, worker_owner_id="replacement-worker")
        first_worker.heartbeat_interval_seconds = 60
        item = first_worker.enqueue_item(
            ProductionQueueItemCreate(
                project_id="project_q",
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id="slow-job",
                idempotency_key="stale-completion",
            )
        )
        item = _lease_item(storage, first_worker, item)
        first_attempt = asyncio.create_task(first_worker.execute_leased_item(item))
        await entered.wait()

        storage.expire_stale_queue_leases("9999-01-01T00:00:00")
        expired_attempt = storage.list_queue_attempts(item.queue_item_id)[0]
        assert expired_attempt.status == "lease_lost"
        reclaimed = _lease_item(storage, second_worker, first_worker.get_item(item.queue_item_id))
        newer_result = reclaimed.model_copy(update={"status": ProductionQueueStatus.RUNNING, "reason": "new owner result"})
        newer_result.lease_owner = None
        newer_result.lease_acquired_at = None
        newer_result.lease_expires_at = None
        assert storage.finalize_queue_lease(newer_result, second_worker.worker_owner_id, reclaimed.lease_generation)

        release.set()
        result = await first_attempt
        assert result["status"] == "lease_lost"
        current = first_worker.get_item(item.queue_item_id)
        assert current.status == ProductionQueueStatus.RUNNING
        assert current.reason == "new owner result"
        assert current.lease_generation == reclaimed.lease_generation

    asyncio.run(exercise())


def test_stale_worker_lost_before_router_http_does_not_submit(monkeypatch):
    async def exercise():
        import threading
        from types import SimpleNamespace

        from app.services import render as render_module
        from app.services.providers import runway_router_provider

        storage = SimpleNamespace(queue_lease_is_current=lambda *_args: False)
        service = ProductionQueueService(storage=storage, worker_owner_id="stale-router-worker")
        entered = threading.Event()
        release = threading.Event()
        provider_calls = []
        original_assert = render_module.assert_queue_execution_lease_current

        def block_at_http_boundary():
            entered.set()
            assert release.wait(timeout=2)
            original_assert()

        def capture_urlopen(*args, **kwargs):
            provider_calls.append((args, kwargs))
            raise AssertionError("stale worker must not initiate the HTTP request")

        monkeypatch.setattr(render_module, "assert_queue_execution_lease_current", block_at_http_boundary)
        monkeypatch.setattr(runway_router_provider, "urlopen", capture_urlopen)
        fence_token = render_module._queue_execution_fence.set({
            "queue_item_id": "queue-1",
            "lease_owner": service.worker_owner_id,
            "lease_generation": 1,
        })
        try:
            task = asyncio.create_task(asyncio.to_thread(
                runway_router_provider._runway_router_request,
                "https://runway.invalid/v1/generate/video",
                method="POST",
                payload={"input": {}},
                api_key="test-key",
            ))
            assert await asyncio.to_thread(entered.wait, 2)
            release.set()
            with pytest.raises(render_module.QueueExecutionLeaseLost):
                await task
        finally:
            release.set()
            render_module._queue_execution_fence.reset(fence_token)
        assert provider_calls == []

    asyncio.run(exercise())


def test_stale_worker_cannot_overwrite_render_job_after_lease_replacement(tmp_path, monkeypatch):
    async def exercise():
        from types import SimpleNamespace

        from app.services import render as render_module
        from app.models import RenderJobModel, StudioProject

        storage = DatabaseStorage(str(tmp_path))
        storage.save_project(StudioProject(project_id="project_q", title="Queue fencing"))
        render_module.set_storage(storage)
        render_service = render_module.RenderService()
        job = RenderJobModel(id="fenced-render", project_id="project_q", shot_id="shot-1", provider="simulated")
        storage.save_job(job)
        render_service._jobs[job.id] = job
        entered = asyncio.Event()
        release = asyncio.Event()
        original_submit = render_service.submit_job

        async def blocked_submit(job_id):
            entered.set()
            await release.wait()
            return await original_submit(job_id)

        render_service.submit_job = blocked_submit
        first_worker = ProductionQueueService(storage=storage, render_svc=render_service, worker_owner_id="render-worker-a")
        second_worker = ProductionQueueService(storage=storage, worker_owner_id="render-worker-b")
        first_worker.heartbeat_interval_seconds = 60
        item = first_worker.enqueue_existing_render_job(job_id=job.id)
        item = _lease_item(storage, first_worker, item)
        first_attempt = asyncio.create_task(first_worker.execute_leased_item(item))
        await entered.wait()

        storage.expire_stale_queue_leases("9999-01-01T00:00:00")
        replacement = _lease_item(storage, second_worker, first_worker.get_item(item.queue_item_id))
        release.set()
        result = await first_attempt

        assert result["status"] == "lease_lost"
        persisted_job = storage.get_job(job.id)
        assert persisted_job.status == "pending"
        assert storage.get_queue_item(item.queue_item_id).lease_owner == second_worker.worker_owner_id
        assert storage.get_queue_item(item.queue_item_id).lease_generation == replacement.lease_generation
        assert render_service.get_job(job.id).status == "pending"
        attempts = storage.list_queue_attempts(item.queue_item_id)
        assert attempts[0].status == "lease_lost"
        assert attempts[0].lease_generation == item.lease_generation

    asyncio.run(exercise())


def test_competing_workers_acquire_only_one_current_fencing_generation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="enqueue-owner")
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="competing-item",
            idempotency_key="competing-item",
        )
    )

    def claim(owner):
        now = __import__("datetime").datetime.now()
        return storage.acquire_queue_lease_for_item(
            queue_item_id=item.queue_item_id,
            owner_id=owner,
            now=now.isoformat(),
            lease_expires_at=(now + __import__("datetime").timedelta(seconds=30)).isoformat(),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("worker-a", "worker-b")))

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].lease_generation == 1
    assert storage.queue_lease_is_current(item.queue_item_id, winners[0].lease_owner, winners[0].lease_generation)


def test_final_attempt_result_cannot_be_overwritten_after_lease_replacement(tmp_path):
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="attempt-worker")
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="attempt-fence",
            idempotency_key="attempt-fence",
        )
    )
    leased = _lease_item(storage, service, item)
    attempt = SimpleNamespace(
        attempt_id="stale-attempt",
        queue_item_id=item.queue_item_id,
        attempt_number=leased.attempt_count,
        lease_owner=service.worker_owner_id,
        status="complete",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        duration_ms=1,
        error_type=None,
        error_message=None,
        result={"status": "complete"},
        metadata={},
    )
    assert storage.record_queue_attempt_fenced(attempt, leased.lease_generation)
    storage.expire_stale_queue_leases("9999-01-01T00:00:00")
    replacement_worker = ProductionQueueService(storage=storage, worker_owner_id="attempt-replacement")
    replacement = _lease_item(storage, replacement_worker, service.get_item(item.queue_item_id))
    newer_attempt = attempt.__class__(**{**attempt.__dict__, "attempt_id": "newer-attempt", "lease_owner": replacement_worker.worker_owner_id, "status": "running"})
    assert storage.record_queue_attempt_fenced(newer_attempt, replacement.lease_generation)

    attempt.status = "lease_lost"
    attempt.result = {"status": "lease_lost"}
    assert storage.record_queue_attempt_fenced(attempt, leased.lease_generation, final=True) is False
    attempts = storage.list_queue_attempts(item.queue_item_id)
    assert len(attempts) == 2
    assert attempts[1].status == "running"
    assert attempts[1].lease_generation == replacement.lease_generation


def test_stale_renewal_cannot_extend_terminal_lease(tmp_path):
    from datetime import datetime, timedelta

    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="terminal-owner")
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="terminal-item",
            idempotency_key="terminal-item",
        )
    )
    item = _lease_item(storage, service, item)
    completed = item.model_copy(deep=True)
    completed.status = ProductionQueueStatus.COMPLETE
    completed.reason = "finished"
    completed.result = {"ok": True}
    completed.completed_at = datetime.now().isoformat()
    completed.updated_at = completed.completed_at
    completed.lease_owner = None
    completed.lease_acquired_at = None
    completed.lease_expires_at = None
    assert storage.finalize_queue_lease(completed, service.worker_owner_id, item.lease_generation)
    assert storage.renew_queue_lease(
        item.queue_item_id,
        service.worker_owner_id,
        item.lease_generation,
        (datetime.now() + timedelta(seconds=60)).isoformat(),
    ) is False


def test_queue_cancelled_render_job_is_not_requeued_as_provider_failure(tmp_path):
    from types import SimpleNamespace

    storage = DatabaseStorage(str(tmp_path))
    render_job = SimpleNamespace(
        id="job-cancelled",
        status="cancelled",
        error_message="Cancelled by creator",
        metadata={},
    )
    service = ProductionQueueService(
        storage=storage,
        render_svc=SimpleNamespace(get_job=lambda _job_id: render_job),
        worker_owner_id="cancelled-render",
    )
    item = service.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_q",
            work_type=ProductionQueueWorkType.RENDER_JOB,
            canonical_type="render_job",
            canonical_id=render_job.id,
            idempotency_key="cancelled-render",
        )
    )

    item = _lease_item(storage, service, item)
    result = asyncio.run(service.execute_leased_item(item))

    assert result["status"] == "cancelled"
    assert service.get_item(item.queue_item_id).status == ProductionQueueStatus.CANCELLED


def test_background_worker_start_is_idempotent_and_stops_cleanly(tmp_path):
    async def exercise_worker():
        storage = DatabaseStorage(str(tmp_path))
        service = ProductionQueueService(storage=storage, worker_owner_id="test-owner")

        first = service.start_background_worker()
        second = service.start_background_worker()
        assert second is first
        assert not first.done()

        await service.stop_background_worker()

        assert service.worker_status().running is False
        assert first.done()

    asyncio.run(exercise_worker())
