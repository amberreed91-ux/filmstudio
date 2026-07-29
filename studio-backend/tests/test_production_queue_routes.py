from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes import production_queue as production_queue_routes
from app.services.production_queue_service import ProductionQueueService


class _FakeRenderJob:
    def __init__(self, project_id: str, shot_id: str, provider: str | None, prompt: str, parameters: dict):
        self.id = f"job_{shot_id}"
        self.project_id = project_id
        self.shot_id = shot_id
        self.provider = provider or "simulated"
        self.status = "pending"
        self.error_message = None
        self.input_payload = type("FakeInput", (), {"prompt": prompt, "parameters": parameters})()


class _FakeRenderService:
    def create_job(self, project_id, shot_id, provider=None, prompt="", reference_assets=None, parameters=None):
        return _FakeRenderJob(project_id, shot_id, provider, prompt, parameters or {})

    def get_job(self, _job_id):
        return None


def _client(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(storage=storage, worker_owner_id="route-test")
    monkeypatch.setattr(production_queue_routes, "production_queue_service", service)
    app = FastAPI()
    app.include_router(production_queue_routes.router)
    return TestClient(app)


def test_create_list_summary_and_events(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    create_response = client.post(
        "/api/f51/studio/production-queue/items",
        json={
            "project_id": "project_route",
            "work_type": "custom_workflow",
            "canonical_type": "custom_workflow",
            "canonical_id": "wf_route",
            "idempotency_key": "wf_route",
            "priority": 75,
        },
    )

    assert create_response.status_code == 200
    item = create_response.json()
    assert item["status"] == "queued"

    list_response = client.get("/api/f51/studio/production-queue/projects/project_route/items")
    assert list_response.status_code == 200
    assert list_response.json()["total_visible"] == 1

    summary_response = client.get("/api/f51/studio/production-queue/projects/project_route/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["counts_by_status"]["queued"] == 1

    events_response = client.get(f"/api/f51/studio/production-queue/items/{item['queue_item_id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[0]["event_type"] == "queued"


def test_retry_rejects_active_item(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/f51/studio/production-queue/items",
        json={
            "project_id": "project_route",
            "work_type": "custom_workflow",
            "canonical_type": "custom_workflow",
            "canonical_id": "wf_route",
            "idempotency_key": "wf_route",
        },
    ).json()

    response = client.post(f"/api/f51/studio/production-queue/items/{created['queue_item_id']}/retry", json={})

    assert response.status_code == 409


def test_cancel_and_diagnostics_routes_expose_queue_health(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/f51/studio/production-queue/items",
        json={
            "project_id": "project_route",
            "work_type": "custom_workflow",
            "canonical_type": "custom_workflow",
            "canonical_id": "wf_route",
            "idempotency_key": "wf_route",
            "provider": "simulated",
        },
    ).json()

    cancel_response = client.post(
        f"/api/f51/studio/production-queue/items/{created['queue_item_id']}/cancel",
        json={"reason": "No longer needed."},
    )
    diagnostics_response = client.get("/api/f51/studio/production-queue/diagnostics?project_id=project_route")

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert diagnostics_response.status_code == 200
    data = diagnostics_response.json()
    assert data["project_id"] == "project_route"
    assert data["worker"]["owner_id"] == "route-test"
    assert data["summary"]["counts_by_status"]["cancelled"] == 1


def test_scene_queue_route_expands_scene_work(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path))
    service = ProductionQueueService(
        storage=storage,
        render_svc=_FakeRenderService(),
        worker_owner_id="route-test",
    )
    monkeypatch.setattr(production_queue_routes, "production_queue_service", service)

    from app.services import project_store as project_store_module

    monkeypatch.setattr(
        project_store_module.project_store,
        "get_project",
        lambda _project_id: {
            "project_id": "project_route",
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "description": "A quiet threshold before the choice.",
                        "shots": [
                            {"shot_id": "scene_001_shot_001", "description": "A hand hovers near the handle."},
                            {"shot_id": "scene_001_shot_002", "description": "A face decides not to speak."},
                        ],
                    }
                ]
            },
        },
    )
    app = FastAPI()
    app.include_router(production_queue_routes.router)

    response = TestClient(app).post(
        "/api/f51/studio/production-queue/projects/project_route/scenes/scene_001/queue",
        json={"provider": "simulated", "priority": 70},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["render_items"]) == 2
    assert len(data["audio_items"]) == 2
    assert data["stitch_item"]["work_type"] == "scene_stitch"
