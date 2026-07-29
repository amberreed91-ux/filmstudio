from __future__ import annotations

import asyncio

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
