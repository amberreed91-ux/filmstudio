"""Router cancel: POST /v1/tasks/{id}/cancel + one follow-up GET must confirm.

Stubbed transport only: every provider interaction is faked at
``_runway_router_request``. No provider calls, no network, no spend.
"""
from __future__ import annotations

import asyncio
import copy

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.models.production_queue import ProductionQueueItemCreate, ProductionQueueWorkType
from app.services import render as render_module
from app.services.production_queue_service import ProductionQueueService
from app.services.providers import runway_router_provider
from app.services.providers.runway_router_provider import (
    RunwayRouterConfigNotFoundError,
    cancel_runway_router_task,
)
from app.services.render import RenderService

TASK_ID = "task-cancel-1"
OTHER_TASK = "task-cancel-other"


def _job(job_id="job-cancel-1", *, task_id=TASK_ID, project_id="proj-cancel-a", status="rendering"):
    return RenderJobModel(
        id=job_id,
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="runway_router",
        provider_job_id=task_id,
        status=status,
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001", prompt="A quiet hallway.", referenceAssets=[], parameters={}
        ),
        metadata={},
        created_at="2026-10-15T00:00:00Z",
        updated_at="2026-10-15T00:00:00Z",
    )


def _cfg():
    return ProviderConfig(
        provider_id="runway_router",
        name="Runway Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation"],
    )


class _Transport:
    """Scripted `_runway_router_request` double: POST then GET, no network."""

    def __init__(self, *, post_resp=None, post_error=None, get_resp=None, get_error=None):
        self.calls = []
        self._post_resp = copy.deepcopy(post_resp) if post_resp is not None else {}
        self._post_error = post_error
        self._get_resp = copy.deepcopy(get_resp) if get_resp is not None else {}
        self._get_error = get_error

    def __call__(self, url, *, method="GET", payload=None, api_key=None):
        self.calls.append((method, url))
        assert api_key == "test-key", "stubbed transport must see the test credential"
        if method == "POST":
            assert url.endswith(f"/v1/tasks/{TASK_ID}/cancel") or TASK_ID in url, f"unexpected POST {url}"
            if self._post_error is not None:
                raise self._post_error
            return copy.deepcopy(self._post_resp)
        assert method == "GET", f"only POST + one GET allowed, saw {method}"
        if self._get_error is not None:
            raise self._get_error
        return copy.deepcopy(self._get_resp)


def _patch(monkeypatch, transport):
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setattr(runway_router_provider, "_runway_router_request", transport)


def _posts_gets(transport):
    posts = [c for c in transport.calls if c[0] == "POST"]
    gets = [c for c in transport.calls if c[0] == "GET"]
    return posts, gets


# 1 — POST identifies same task + GET CANCELLED => True.
def test_cancel_verified_same_id_and_get_cancelled(monkeypatch):
    t = _Transport(post_resp={"id": TASK_ID, "status": "CANCELLED"}, get_resp={"id": TASK_ID, "status": "CANCELLED"})
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is True and out["outcome"] == "cancelled"
    posts, gets = _posts_gets(t)
    assert len(posts) == 1 and len(gets) == 1


# 2 — POST reports CANCELLED without id + GET CANCELLED => True.
def test_cancel_post_reports_cancelled_without_id_still_verified(monkeypatch):
    t = _Transport(post_resp={"status": "CANCELLED"}, get_resp={"id": TASK_ID, "status": "CANCELLED"})
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is True
    posts, gets = _posts_gets(t)
    assert len(posts) == 1 and len(gets) == 1


# 3 — POST accepted but GET still RUNNING => False + unconfirmed.
def test_cancel_post_accepted_get_running_is_unconfirmed(monkeypatch):
    t = _Transport(post_resp={"id": TASK_ID}, get_resp={"id": TASK_ID, "status": "RUNNING"})
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is False
    assert out["outcome"] == "cancel_requested_unconfirmed"
    assert out["upstream_status"] == "RUNNING"


# 4 — POST accepted but GET still PENDING => False + unconfirmed.
def test_cancel_post_accepted_get_pending_is_unconfirmed(monkeypatch):
    t = _Transport(post_resp={"id": TASK_ID}, get_resp={"id": TASK_ID, "status": "PENDING"})
    _patch(monkeypatch, t)
    adapter = RunwayRouterAdapter(_cfg())
    job = _job()
    assert asyncio.run(adapter.cancel_job(job)) is False
    assert ((job.metadata or {}).get("router_execution") or {}).get("cancel_requested_unconfirmed") is True
    posts, gets = _posts_gets(t)
    assert len(posts) == 1 and len(gets) == 1


# 5 — no provider_job_id => False with zero transport.
def test_cancel_without_task_id_makes_no_transport(monkeypatch):
    t = _Transport()
    _patch(monkeypatch, t)
    adapter = RunwayRouterAdapter(_cfg())
    assert asyncio.run(adapter.cancel_job(_job(task_id=""))) is False
    assert t.calls == []


# 6 — POST 404 reclassified as unknown_task, not confirmed.
def test_cancel_post_404_reclassified_unknown_task(monkeypatch):
    t = _Transport(post_error=RunwayRouterConfigNotFoundError("not found"))
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is False and out["outcome"] == "unknown_task"
    posts, gets = _posts_gets(t)
    assert len(posts) == 1 and len(gets) == 0


# 7 — POST 400 is unverified, never confirmed.
def test_cancel_post_400_is_unverified(monkeypatch):
    t = _Transport(post_error=RuntimeError("Runway router request failed with HTTP 400 (Bad Request)"))
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is False and out["outcome"] == "unverified"


# 8 — POST 405 is unverified, never confirmed.
def test_cancel_post_405_is_unverified(monkeypatch):
    t = _Transport(post_error=RuntimeError("Runway router request failed with HTTP 405 (Method Not Allowed)"))
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is False and out["outcome"] == "unverified"


# 9 — GET identity mismatch => False, unverified.
def test_cancel_get_mismatched_id_is_unverified(monkeypatch):
    t = _Transport(post_resp={"id": TASK_ID}, get_resp={"id": OTHER_TASK, "status": "CANCELLED"})
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is False and out["outcome"] == "unverified"


# 10 — GET transport failure after POST => False, unverified.
def test_cancel_get_failure_is_unverified(monkeypatch):
    t = _Transport(
        post_resp={"id": TASK_ID},
        get_error=RuntimeError("Runway router request failed: ConnectionError"),
    )
    _patch(monkeypatch, t)
    out = cancel_runway_router_task(TASK_ID)
    assert out["cancelled"] is False and out["outcome"] == "unverified"


# 11 (amendment 2) — queue cancel_item stays local-only but warns upstream may run.
def test_queue_cancel_item_includes_upstream_warning(tmp_path):
    from app.data.storage import DatabaseStorage

    storage = DatabaseStorage(str(tmp_path / "q.db"))
    svc = ProductionQueueService(storage=storage)
    item = svc.enqueue_item(
        ProductionQueueItemCreate(
            project_id="proj-cancel-a",
            work_type=ProductionQueueWorkType.RENDER_JOB,
            canonical_type="render_job",
            canonical_id="job-cancel-1",
            idempotency_key="cancel-warn-1",
        )
    )
    cancelled = svc.cancel_item(item.queue_item_id, "Creator cancelled")
    assert cancelled.status.value == "cancelled"
    warning = (cancelled.result or {}).get("upstream_cancel_warning", "")
    assert "local-only" in str(warning) and "may still be running" in str(warning)


# 12 (amendment 2+service) — only RenderService marks cancelled, only on True; unconfirmed preserves.
def test_render_service_marks_cancelled_only_on_true(monkeypatch):
    service = RenderService()
    service._provider_configs["runway_router"] = _cfg()
    monkeypatch.setattr(runway_router_provider, "_runway_router_request", _Transport(
        post_resp={"id": TASK_ID}, get_resp={"id": TASK_ID, "status": "RUNNING"}
    ))
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    job = _job()
    service._jobs[job.id] = job
    assert asyncio.run(service.cancel_job(job.id)) is False
    assert service._jobs[job.id].status == "rendering"
    assert ((service._jobs[job.id].metadata or {}).get("router_execution") or {}).get(
        "cancel_requested_unconfirmed"
    ) is True


def test_render_service_marks_cancelled_on_verified_true(monkeypatch):
    service = RenderService()
    service._provider_configs["runway_router"] = _cfg()
    t = _Transport(post_resp={"id": TASK_ID}, get_resp={"id": TASK_ID, "status": "CANCELLED"})
    monkeypatch.setattr(runway_router_provider, "_runway_router_request", t)
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    job = _job(job_id="job-cancel-2")
    service._jobs[job.id] = job
    assert asyncio.run(service.cancel_job(job.id)) is True
    assert service._jobs[job.id].status == "cancelled"
    posts, gets = _posts_gets(t)
    assert len(posts) == 1 and len(gets) == 1


# 13 — second project isolation: exact task ids do not cross projects.
def test_cancel_second_project_isolated(monkeypatch):
    service = RenderService()
    service._provider_configs["runway_router"] = _cfg()
    seen_urls: list = []

    def _double(url, *, method="GET", payload=None, api_key=None):
        seen_urls.append((method, url))
        if method == "POST":
            assert TASK_ID in url
            return {"id": TASK_ID}
        return {"id": TASK_ID, "status": "CANCELLED"}

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", _double)
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    job_a = _job(job_id="job-a", project_id="proj-cancel-a")
    job_b = _job(job_id="job-b", project_id="proj-cancel-b", task_id=OTHER_TASK)
    service._jobs[job_a.id] = job_a
    service._jobs[job_b.id] = job_b
    assert asyncio.run(service.cancel_job(job_a.id)) is True
    assert service._jobs["job-a"].status == "cancelled"
    assert service._jobs["job-b"].status == "rendering"
    assert all(TASK_ID in url for _, url in seen_urls)
    assert not any(OTHER_TASK in url for _, url in seen_urls)
