"""R4.3E: router submission reconciliation and ambiguity safety.

Safety invariant under test: an ambiguous router submission outcome must not
automatically trigger a new upstream submission. A retry (or recovery) may
resubmit only after reconciliation positively establishes that no live
upstream task exists for the recorded task id, or that the recorded failure
conclusively precedes any provider submission.

Provider interactions are faked at the transport double
(`_runway_router_request`); every test asserts submission-attempt counts.
No live provider is contacted.
"""
from __future__ import annotations

import asyncio
import copy

import pytest

from app.models import RenderJobInput, RenderJobModel
from app.services import render as render_module
from app.services.providers import runway_router_provider
from app.services.render import RenderService

TASK_ID = "task-ambiguous-1"
OUTPUT_URL = "https://cdn.test/reconciled.mp4"

GENERIC_REASON = "runway_router_provider_failed"
NO_ELIGIBLE_REASON = "no_eligible_model"
CONFIG_NOT_FOUND_REASON = "router_config_not_found"
MISSING_KEY_REASON = "missing_runway_api_key"
INCOMPATIBLE_REASON = "required_reference_incompatible"


def _router_job(
    job_id: str = "job-router-1",
    *,
    status: str = "failed",
    task_id: str | None = TASK_ID,
    reason: str = GENERIC_REASON,
    submission_attempted: bool = True,
    error_message: str = "Runway router submission failed",
) -> RenderJobModel:
    execution = {
        "routing_mode": "model_router",
        "router_config_id": "studio-production-router",
        "runway_task_id": task_id,
        "submission_attempted": submission_attempted,
    }
    normalized = {
        "provider": "runway_router",
        "task": "video_generation",
        "status": "failed",
        "output": {"video_url": None, "status": "failed"},
        "metadata": {
            "task_id": task_id,
            "render_job_id": job_id,
            "reason": reason,
            "error": error_message,
        },
    }
    return RenderJobModel(
        id=job_id,
        project_id="proj-r43e",
        shot_id="scene_001_shot_001",
        provider="runway_router",
        provider_job_id=task_id,
        status=status,
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001", prompt="A locked prompt.", referenceAssets=[], parameters={}
        ),
        output_payload={
            "asset_url": "",
            "thumbnail_url": "",
            "metadata": {"provider_response_normalized": normalized},
        },
        metadata={
            "router_execution": execution,
            # Durable storage requires complete frozen-contract metadata on
            # router rows; content shape is irrelevant to these tests.
            "creative_generation_contract": {"frozen": True},
            "creative_generation_manifest": {"manifest_fingerprint": "fp"},
            "creative_manifest_fingerprint": "fp",
            "creative_contract_digest": "digest",
            "creative_generation_identity": {"project_id": "proj-r43e"},
        },
        error_message=error_message,
        created_at="2026-10-15T00:00:00Z",
        updated_at="2026-10-15T00:00:00Z",
    )


class _Transport:
    """Scripted `_runway_router_request` double counting POSTs and GETs."""

    def __init__(self, *, get_responses=None, get_error=None):
        self.posts: list[dict] = []
        self.gets: list[str] = []
        self._get_responses = list(get_responses or [])
        self._get_error = get_error

    def __call__(self, url, *, method="GET", payload=None, api_key=None):
        if method == "POST":
            self.posts.append(copy.deepcopy(payload) if isinstance(payload, dict) else {})
            raise AssertionError("live POST must not occur in reconcile tests")
        self.gets.append(url)
        if self._get_error is not None:
            raise self._get_error
        if self._get_responses:
            return copy.deepcopy(self._get_responses.pop(0))
        return {"id": TASK_ID, "status": "RUNNING"}


@pytest.fixture()
def transport(monkeypatch):
    double = _Transport()
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setattr(runway_router_provider, "_runway_router_request", double)
    monkeypatch.setattr(runway_router_provider.time, "sleep", lambda *_: None)
    return double


@pytest.fixture()
def persistent_service(monkeypatch):
    """RenderService bound to isolated temp storage.

    Router jobs resolve through durable storage by design
    (`RenderService.get_job`); the service-level paths under test require a
    persisted row, so each hand-built job is saved, not just cached.
    """
    from app.data.storage import get_storage

    storage = get_storage()
    monkeypatch.setattr(render_module, "_storage", storage)
    return RenderService(), storage


def _store(service: RenderService, storage, job: RenderJobModel) -> RenderJobModel:
    storage.save_job(job)
    service._jobs[job.id] = job
    return job


def _succeeded_task(task_id: str = TASK_ID) -> dict:
    return {"id": task_id, "status": "SUCCEEDED", "output": [OUTPUT_URL]}


def _reconciliation(job: RenderJobModel) -> dict:
    return ((job.metadata or {}).get("router_reconciliation") or {})


class _FakeAdapter:
    """Adapter double recording submit attempts without provider contact."""

    def __init__(self):
        self.submits: list[str] = []

    async def submit_job(self, incoming, **kwargs):
        self.submits.append(incoming.id)
        return incoming


class _ExplodingAdapter:
    async def submit_job(self, incoming, **kwargs):  # pragma: no cover - tripwire
        raise AssertionError("no adapter submit expected past the gate in this test")


def _patch_adapter(monkeypatch, adapter):
    monkeypatch.setattr(
        "app.services.render.get_adapter", lambda _provider, _config: adapter
    )


async def _fetch_outputs(job):
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig

    config = ProviderConfig(
        provider_id="runway_router",
        name="Runway Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation"],
    )
    return await RunwayRouterAdapter(config).fetch_outputs(job)


# ── Reproduce G1: ambiguous outcome must not auto-resubmit ─────────────────

def test_g1_blind_retry_is_blocked_after_ambiguous_timeout(
    transport, persistent_service, monkeypatch
):
    """Core G1 repro: failed router job with a recorded task id and an
    inconclusive lookup must not produce a second submission on retry."""
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_error = RuntimeError("connection lost during lookup")
    adapter = _FakeAdapter()
    _patch_adapter(monkeypatch, adapter)

    with pytest.raises(ValueError, match="(?i)retry blocked"):
        asyncio.run(service.retry_job("job-router-1"))
    assert adapter.submits == []
    assert transport.posts == []
    evidence = _reconciliation(service._jobs["job-router-1"])
    assert evidence.get("retry_permitted") is False
    assert evidence.get("task_id") == TASK_ID


# ── Reconcile outcomes ─────────────────────────────────────────────────────

def test_reconcile_adopts_succeeded_upstream_task(transport, persistent_service):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    contract_before = copy.deepcopy(
        service._jobs["job-router-1"].metadata["creative_generation_contract"]
    )
    transport._get_responses.append(_succeeded_task())

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert reconciled.status == "complete"
    assert reconciled.output_payload.asset_url == OUTPUT_URL
    assert reconciled.provider_job_id == TASK_ID
    assert transport.posts == []
    assert len(transport.gets) == 1
    evidence = _reconciliation(reconciled)
    assert evidence.get("verdict") == "adopted_completed_task"
    assert evidence.get("retry_permitted") is False
    # Canonical request evidence untouched; provider not switched.
    assert reconciled.provider == "runway_router"
    assert reconciled.metadata["creative_generation_contract"] == contract_before
    assert list(reconciled.input_payload.referenceAssets or []) == []
    # Delivery gate shape holds for the adopted output.
    assets = asyncio.run(_fetch_outputs(reconciled))
    assert [a.url for a in assets] == [OUTPUT_URL]


def test_reconcile_preserves_upstream_active_task(transport, persistent_service):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.append({"id": TASK_ID, "status": "RUNNING"})

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert reconciled.status == "failed"
    assert reconciled.provider_job_id == TASK_ID
    assert transport.posts == []
    evidence = _reconciliation(reconciled)
    assert evidence.get("verdict") == "upstream_active"
    assert evidence.get("retry_permitted") is False


def test_reconcile_marks_upstream_terminal_failure(transport, persistent_service):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.append({"id": TASK_ID, "status": "FAILED", "failure": "boom"})

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert reconciled.status == "failed"
    assert transport.posts == []
    evidence = _reconciliation(reconciled)
    assert evidence.get("verdict") == "upstream_terminal_failure"
    assert evidence.get("retry_permitted") is True


def test_reconcile_without_task_id_is_safe_noop(transport, persistent_service):
    service, storage = persistent_service
    job = _router_job(task_id=None)
    job.provider_job_id = None
    _store(service, storage, job)

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert reconciled.status == "failed"
    assert transport.gets == [] and transport.posts == []
    assert _reconciliation(reconciled).get("verdict") == "skipped_no_task_id"


def test_reconcile_ignores_non_router_provider(transport, persistent_service):
    service, storage = persistent_service
    job = _router_job()
    job.provider = "simulated"
    _store(service, storage, job)

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert transport.gets == [] and transport.posts == []


def test_reconcile_ignores_contract_only_jobs(
    transport, persistent_service, monkeypatch
):
    # Contract-only jobs keep their own authority flow; persistence rejects
    # forged contract-only rows, so the classification itself is faked while
    # the guard branch under test is real.
    import app.services.scene002_contract_only as _contract_only

    service, storage = persistent_service
    _store(service, storage, _router_job())
    monkeypatch.setattr(_contract_only, "is_contract_only", lambda _job: True)

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert transport.gets == [] and transport.posts == []


def test_reconcile_inconclusive_on_lookup_404(transport, persistent_service):
    from app.services.providers.runway_router_provider import (
        RunwayRouterConfigNotFoundError,
    )

    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_error = RunwayRouterConfigNotFoundError("not found")

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    assert reconciled.status == "failed"
    assert transport.posts == []
    evidence = _reconciliation(reconciled)
    assert evidence.get("verdict") == "reconcile_inconclusive"
    assert evidence.get("retry_permitted") is False


def test_reconcile_unavailable_without_credentials(persistent_service, monkeypatch):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)

    reconciled = asyncio.run(service.reconcile_runway_router_task("job-router-1"))

    evidence = _reconciliation(reconciled)
    assert evidence.get("verdict") == "reconcile_unavailable"
    assert evidence.get("retry_permitted") is False


# ── Retry-gate behavior ────────────────────────────────────────────────────

def test_retry_adopts_completed_task_without_resubmission(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.append(_succeeded_task())
    adapter = _FakeAdapter()
    _patch_adapter(monkeypatch, adapter)

    result = asyncio.run(service.retry_job("job-router-1"))
    assert result.status == "complete"
    assert result.output_payload.asset_url == OUTPUT_URL
    assert adapter.submits == []
    assert transport.posts == []


def test_retry_blocked_while_upstream_active(transport, persistent_service, monkeypatch):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.append({"id": TASK_ID, "status": "RUNNING"})
    adapter = _FakeAdapter()
    _patch_adapter(monkeypatch, adapter)

    with pytest.raises(ValueError, match="(?i)upstream.*active|retry blocked"):
        asyncio.run(service.retry_job("job-router-1"))
    assert adapter.submits == []
    assert transport.posts == []


def test_retry_proceeds_after_confirmed_upstream_failure(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.append({"id": TASK_ID, "status": "CANCELLED"})
    _patch_adapter(monkeypatch, _ExplodingAdapter())
    # Gate permits resubmission (reconcile saw the dead task); the downstream
    # submit then fails closed on the hand-built job's stub contract proof
    # before any provider contact — the gate's permit is what is asserted.
    from app.services.generation_contract import GenerationContractError

    with pytest.raises(GenerationContractError):
        asyncio.run(service.retry_job("job-router-1"))
    assert transport.posts == []
    evidence = _reconciliation(service._jobs["job-router-1"])
    assert evidence.get("verdict") == "upstream_terminal_failure"
    assert evidence.get("retry_permitted") is True


def test_retry_proceeds_after_conclusive_pre_send_rejection(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    job = _router_job(
        task_id=None,
        reason=NO_ELIGIBLE_REASON,
        submission_attempted=False,
        error_message="no eligible model",
    )
    job.provider_job_id = None
    _store(service, storage, job)
    _patch_adapter(monkeypatch, _ExplodingAdapter())
    # No task id, conclusive pre-send rejection code: the gate permits without
    # any lookup, and the downstream submit fails closed on the stub proof.
    from app.services.generation_contract import GenerationContractError

    with pytest.raises(GenerationContractError):
        asyncio.run(service.retry_job("job-router-1"))
    assert transport.posts == [] and transport.gets == []


def test_retry_blocked_on_ambiguous_failure_without_task_id(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    job = _router_job(
        task_id=None,
        reason=GENERIC_REASON,
        submission_attempted=True,
        error_message="connection reset during POST",
    )
    job.provider_job_id = None
    _store(service, storage, job)
    adapter = _FakeAdapter()
    _patch_adapter(monkeypatch, adapter)

    with pytest.raises(ValueError, match="(?i)retry blocked"):
        asyncio.run(service.retry_job("job-router-1"))
    assert adapter.submits == []
    assert transport.posts == []


def test_concurrent_retries_cannot_duplicate_tasks(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.extend(
        [{"id": TASK_ID, "status": "RUNNING"}, {"id": TASK_ID, "status": "RUNNING"}]
    )
    adapter = _FakeAdapter()
    _patch_adapter(monkeypatch, adapter)

    async def _attempt():
        try:
            await service.retry_job("job-router-1")
            return "returned"
        except ValueError:
            return "blocked"

    outcomes = asyncio.run(_gather_two(_attempt))
    assert sorted(outcomes) == ["blocked", "blocked"]
    assert adapter.submits == []
    assert transport.posts == []


async def _gather_two(coro_factory):
    return await asyncio.gather(coro_factory(), coro_factory())


def test_restart_recovery_adopts_ambiguous_router_job(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    _store(service, storage, _router_job(status="rendering"))
    _store(service, storage, _router_job(job_id="job-router-orphan", status="failed"))
    transport._get_responses.extend([_succeeded_task(), _succeeded_task()])
    _patch_adapter(monkeypatch, _ExplodingAdapter())

    summary = asyncio.run(service.recover_jobs_after_restart())

    recovered = service._jobs["job-router-1"]
    assert recovered.status == "complete"
    assert recovered.output_payload.asset_url == OUTPUT_URL
    assert service._jobs["job-router-orphan"].status == "complete"
    assert transport.posts == []
    assert summary["orphan_reconciled_jobs"] >= 1


def test_continuity_retry_refused_while_upstream_ambiguous(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_responses.append({"id": TASK_ID, "status": "RUNNING"})
    _patch_adapter(monkeypatch, _ExplodingAdapter())

    result = asyncio.run(
        service.retry_with_continuity_context(
            "job-router-1", film_id="proj-r43e", scene_id="scene_001"
        )
    )
    assert "refused" in result["advisory"].lower()
    assert "job-router-1" in result["job"]["id"]
    assert transport.posts == []
    assert [jid for jid in service._jobs if jid != "job-router-1"] == []


def test_blocked_paths_preserve_contract_and_provider(
    transport, persistent_service, monkeypatch
):
    service, storage = persistent_service
    _store(service, storage, _router_job())
    transport._get_error = RuntimeError("lookup down")
    payload_before = copy.deepcopy(
        service._jobs["job-router-1"].input_payload.model_dump(mode="json")
    )
    contract_before = copy.deepcopy(
        service._jobs["job-router-1"].metadata["creative_generation_contract"]
    )
    _patch_adapter(monkeypatch, _ExplodingAdapter())
    with pytest.raises(ValueError, match="(?i)reconciliat|resolv"):
        asyncio.run(service.retry_job("job-router-1"))

    current = service._jobs["job-router-1"]
    assert current.provider == "runway_router"
    assert current.input_payload.model_dump(mode="json") == payload_before
    assert current.metadata["creative_generation_contract"] == contract_before
    assert list(current.input_payload.referenceAssets or []) == []
