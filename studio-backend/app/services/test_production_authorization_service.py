from __future__ import annotations

import copy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig, RenderJobModel
from app.services.generation_contract import FrozenGenerationContract
from app.services.production_authorization_service import authorize_runway_submission
from app.services.production_queue_service import ProductionQueueService
from app.services.generation_cost_gate import generation_cost_gate
from app.services.shot_manifest import recompute_manifest_fingerprint

_generator_path = Path(__file__).resolve().parents[2] / "tests" / "test_generation_contract_remediation.py"
_generator_spec = importlib.util.spec_from_file_location("generation_contract_test_fixtures", _generator_path)
if _generator_spec is None or _generator_spec.loader is None:
    raise RuntimeError("Unable to load the frozen-contract test fixture")
_generator_module = importlib.util.module_from_spec(_generator_spec)
_generator_spec.loader.exec_module(_generator_module)
_job_with_frozen_contract = _generator_module._job_with_frozen_contract


OWNER_ID = "owner-1"
PROJECT_ID = "project-contract-test"
SCENE_ID = "scene_001"
VERSION_ID = "test-board-v1"
SHOT_ID = "scene_001_shot_001"
STORYBOARD_SHOT_ID = "board-shot-1"
BLUEPRINT_ID = "blueprint-1"


def _authorized_job(*, actor_id: str = OWNER_ID) -> RenderJobModel:
    job = _job_with_frozen_contract()
    contract = FrozenGenerationContract.from_record(job.metadata["creative_generation_contract"])
    manifest = job.metadata["creative_generation_manifest"]
    manifest["shots"][0]["storyboard_shot_id"] = STORYBOARD_SHOT_ID
    fingerprint = recompute_manifest_fingerprint(manifest)
    manifest["manifest_fingerprint"] = fingerprint
    contract = replace(contract, manifest_fingerprint=fingerprint)
    job.metadata.update(
        production_request_actor_id=actor_id,
        creative_generation_contract=contract.to_record(),
        creative_generation_manifest=manifest,
        creative_manifest_fingerprint=fingerprint,
        creative_contract_digest=contract.creative_digest(),
    )
    job.metadata["creative_generation_identity"]["job_id"] = job.id
    job.input_payload.parameters["storyboard"] = {
        "storyboard_shot_id": STORYBOARD_SHOT_ID,
        "version_id": VERSION_ID,
    }
    return job


def _save_sqlite_owner_approved_storyboard(storage) -> None:
    from app.models import StudioProject
    from app.models.storyboard_blueprint import (
        StoryboardBlueprint,
        StoryboardBlueprintStatus,
        StoryboardBlueprintVersion,
        StoryboardShot,
        StoryboardShotStatus,
    )

    storage.save_project(StudioProject(project_id=PROJECT_ID, title="Authorization proof"))
    storage.access_save_user({"username": OWNER_ID, "user_id": OWNER_ID}, create=True)
    storage.access_claim_project(PROJECT_ID, OWNER_ID)
    storage.save_storyboard_blueprint(StoryboardBlueprint(
        blueprint_id=BLUEPRINT_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        current_version_id=VERSION_ID,
        approved_version_id=VERSION_ID,
        status=StoryboardBlueprintStatus.APPROVED,
    ))
    storage.save_storyboard_blueprint_version(StoryboardBlueprintVersion(
        version_id=VERSION_ID,
        blueprint_id=BLUEPRINT_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        status=StoryboardBlueprintStatus.APPROVED,
        approved_at="2026-10-10T12:00:00Z",
        approved_by=OWNER_ID,
        metadata={"production_approval": {"actor_id": OWNER_ID, "actor_authenticated": True}},
    ))
    storage.save_storyboard_shot(StoryboardShot(
        storyboard_shot_id=STORYBOARD_SHOT_ID,
        blueprint_id=BLUEPRINT_ID,
        version_id=VERSION_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        shot_id=SHOT_ID,
        shot_number=1,
        status=StoryboardShotStatus.APPROVED,
    ))


def _create_job_with_render_service(storage, *, actor_id: str | None = OWNER_ID) -> RenderJobModel:
    from app.access_context import access_user_id
    from app.services.render import RenderService

    source_job = _authorized_job()
    contract_record = source_job.metadata["creative_generation_contract"]
    contract = FrozenGenerationContract.from_record(contract_record)
    # Pipeline-realistic scope: setting rows carry their owning project_id
    # (R4.5 session A, owner-authorized fixture shape).
    binding = [
        {
            "ref_id": ref["ref_id"], "uri": ref["uri"], "target_type": ref["target_type"],
            "target_id": ref["target_id"], "role": ref["studio_role"], "category": ref["category"],
            "canonical": ref["canonical"], "approval_state": ref["approval_state"],
            "source_kind": ref["source_kind"], "kind": ref["kind"],
            "studio_role": ref["studio_role"], "source": ref["source"],
            **({"project_id": PROJECT_ID} if ref["target_type"] == "setting" else {}),
        }
        for ref in contract_record["payload"]["references"]
    ]
    storyboard_parameters = dict(source_job.input_payload.parameters)
    storyboard_parameters["storyboard"] = {
        "storyboard_shot_id": STORYBOARD_SHOT_ID,
        "version_id": VERSION_ID,
    }
    manifest = source_job.metadata["creative_generation_manifest"]
    manifest["storyboard"] = {"storyboard_version": VERSION_ID}
    manifest["shots"][0]["storyboard_shot_id"] = STORYBOARD_SHOT_ID
    manifest["manifest_fingerprint"] = ""
    fingerprint = recompute_manifest_fingerprint(manifest)
    manifest["manifest_fingerprint"] = fingerprint
    contract = replace(contract, manifest_fingerprint=fingerprint)
    contract_record = contract.to_record()
    source_job.metadata.update(
        creative_generation_contract=contract_record,
        creative_generation_manifest=manifest,
        creative_manifest_fingerprint=fingerprint,
        creative_contract_digest=contract.creative_digest(),
    )

    actor_token = access_user_id.set(actor_id)
    try:
        return RenderService().create_job(
            project_id=source_job.project_id,
            shot_id=source_job.shot_id,
            provider="runway_router",
            prompt=contract.prompt,
            parameters=storyboard_parameters,
            reference_assets=source_job.input_payload.referenceAssets,
            generation_contract=contract_record,
            creative_manifest_fingerprint=fingerprint,
            creative_manifest=source_job.metadata["creative_generation_manifest"],
            dialogue_handoff=contract.payload()["dialogue_handoff"],
            frozen_reference_binding=binding,
            prepared_generation_contract=contract_record,
        )
    finally:
        access_user_id.reset(actor_token)


def _authority_storage(job: RenderJobModel, *, owner_id: str = OWNER_ID, current_version: str = VERSION_ID):
    blueprint = SimpleNamespace(
        blueprint_id=BLUEPRINT_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        current_version_id=current_version,
        approved_version_id=VERSION_ID,
        status="approved",
    )
    version = SimpleNamespace(
        version_id=VERSION_ID,
        blueprint_id=BLUEPRINT_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        status="approved",
        approved_at="2026-10-10T12:00:00Z",
        approved_by=OWNER_ID,
        metadata={
            "production_approval": {
                "actor_id": OWNER_ID,
                "actor_authenticated": True,
            }
        },
    )
    shot = SimpleNamespace(
        storyboard_shot_id=STORYBOARD_SHOT_ID,
        blueprint_id=BLUEPRINT_ID,
        version_id=VERSION_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        shot_id=SHOT_ID,
        status="approved",
    )
    durable_job = job.model_copy(deep=True)
    if not isinstance(durable_job.metadata, dict):
        durable_job.metadata = {}
    durable_job.metadata.pop("production_authorization", None)
    queue_items = {}
    queue_attempts = {}

    def create_queue_item(item):
        queue_items[item.queue_item_id] = item.model_copy(deep=True)
        return item

    def get_queue_item(queue_item_id):
        item = queue_items.get(queue_item_id)
        return item.model_copy(deep=True) if item is not None else None

    def acquire_queue_lease_for_item(queue_item_id, owner_id, now, lease_expires_at):
        item = queue_items.get(queue_item_id)
        if item is None or item.status.value not in {"queued", "waiting_provider"}:
            return None
        item.status = "leased"
        item.lease_owner = owner_id
        item.lease_acquired_at = now
        item.lease_expires_at = lease_expires_at
        item.lease_generation += 1
        item.attempt_count += 1
        return item.model_copy(deep=True)

    def queue_lease_is_current(queue_item_id, owner_id, generation):
        item = queue_items.get(queue_item_id)
        return bool(
            item
            and item.lease_owner == owner_id
            and item.lease_generation == generation
            and (item.status.value if hasattr(item.status, "value") else item.status) in {"leased", "running"}
        )

    def renew_queue_lease(queue_item_id, owner_id, generation, lease_expires_at):
        if not queue_lease_is_current(queue_item_id, owner_id, generation):
            return False
        queue_items[queue_item_id].status = "running"
        queue_items[queue_item_id].lease_expires_at = lease_expires_at
        return True

    def finalize_queue_lease(item, lease_owner, lease_generation, attempt=None):
        current = queue_items.get(item.queue_item_id)
        if not current or not queue_lease_is_current(item.queue_item_id, lease_owner, lease_generation):
            return False
        item.status = item.status.value if hasattr(item.status, "value") else item.status
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        queue_items[item.queue_item_id] = item
        return True

    def record_queue_attempt_fenced(attempt, lease_generation, *, final=False):
        current = queue_items.get(attempt.queue_item_id)
        if current is None or current.lease_generation != lease_generation:
            return False
        if final:
            attempt.status = attempt.status.value if hasattr(attempt.status, "value") else attempt.status
        current_status = current.status.value if hasattr(current.status, "value") else current.status
        if final:
            previous = queue_attempts.get(attempt.attempt_id)
            if previous is None or previous.status != "running" or current_status not in {
                "leased", "running", "complete", "failed", "cancelled", "dead_lettered"
            }:
                return False
            if current.lease_owner is not None and current.lease_owner != attempt.lease_owner:
                return False
        elif not queue_lease_is_current(attempt.queue_item_id, attempt.lease_owner, lease_generation):
            return False
        queue_attempts[attempt.attempt_id] = attempt.model_copy(deep=True)
        return True

    def update_queue_item(item, **kwargs):
        if kwargs.get("expected_lease") is not None:
            owner, generation = kwargs["expected_lease"]
            if not queue_lease_is_current(item.queue_item_id, owner, generation):
                return None
            item.lease_owner = None
            item.lease_acquired_at = None
            item.lease_expires_at = None
        queue_items[item.queue_item_id] = item
        return item

    return SimpleNamespace(
        get_job=lambda job_id: durable_job.model_copy(deep=True) if job_id == job.id else None,
        access_project_owner=lambda project_id: owner_id if project_id == PROJECT_ID else None,
        get_project=lambda project_id: {} if project_id == PROJECT_ID else None,
        get_storyboard_blueprint=lambda project_id, scene_id: blueprint,
        get_storyboard_blueprint_version=lambda version_id: version if version_id == VERSION_ID else None,
        get_storyboard_shot=lambda shot_id: shot if shot_id == STORYBOARD_SHOT_ID else None,
        find_queue_item_by_idempotency_key=lambda project_id, idempotency_key: None,
        create_queue_item=create_queue_item,
        get_queue_item=get_queue_item,
        acquire_queue_lease_for_item=acquire_queue_lease_for_item,
        queue_lease_is_current=queue_lease_is_current,
        renew_queue_lease=renew_queue_lease,
        finalize_queue_lease=finalize_queue_lease,
        record_queue_attempt_fenced=record_queue_attempt_fenced,
        save_queue_event=lambda event: event,
        update_queue_item=update_queue_item,
    )


def test_owner_approved_frozen_job_is_authorized():
    job = _authorized_job()

    decision = authorize_runway_submission(job, storage=_authority_storage(job))

    assert decision.allowed is True
    assert decision.reason == "owner_approved_frozen_request"
    assert decision.actor_id == OWNER_ID


@pytest.mark.parametrize(
    ("actor_id", "owner_id", "current_version", "expected_reason"),
    [
        ("intruder", OWNER_ID, VERSION_ID, "project_owner_mismatch"),
        (OWNER_ID, "new-owner", VERSION_ID, "project_owner_mismatch"),
        (OWNER_ID, OWNER_ID, "newer-board", "storyboard_approval_stale"),
    ],
)
def test_non_owner_or_stale_approval_is_denied(actor_id, owner_id, current_version, expected_reason):
    job = _authorized_job(actor_id=actor_id)

    decision = authorize_runway_submission(
        job,
        storage=_authority_storage(job, owner_id=owner_id, current_version=current_version),
    )

    assert decision.allowed is False
    assert decision.reason == expected_reason


def test_render_service_creation_persists_only_current_owner_approved_router_jobs(tmp_path, monkeypatch):
    from app.data.storage import DatabaseStorage
    from app.services import render as render_module

    storage = DatabaseStorage(str(tmp_path / "render-creation-owner"))
    _save_sqlite_owner_approved_storyboard(storage)
    monkeypatch.setattr(render_module, "_storage", storage)

    created = _create_job_with_render_service(storage)

    persisted = storage.get_job(created.id)
    assert persisted is not None
    assert persisted.provider == "runway_router"
    assert persisted.metadata["production_request_actor_id"] == OWNER_ID
    assert persisted.metadata["production_authorization"] == {
        "allowed": True,
        "reason": "owner_approved_frozen_request",
        "project_id": PROJECT_ID,
        "job_id": created.id,
        "actor_id": OWNER_ID,
        "stage": "job_creation",
    }


@pytest.mark.parametrize("actor_id", [None, "intruder"])
def test_render_service_creation_denies_missing_or_non_owner_actor_before_persistence(tmp_path, monkeypatch, actor_id):
    from app.data.storage import DatabaseStorage
    from app.services import render as render_module

    storage = DatabaseStorage(str(tmp_path / f"render-creation-denied-{actor_id}"))
    _save_sqlite_owner_approved_storyboard(storage)
    monkeypatch.setattr(render_module, "_storage", storage)

    with pytest.raises(ValueError, match="authenticated project owner|current project owner"):
        _create_job_with_render_service(storage, actor_id=actor_id)

    assert storage.list_jobs(project_id=PROJECT_ID) == []


def test_render_service_creation_denies_stale_approval_before_persistence(tmp_path, monkeypatch):
    from app.data.storage import DatabaseStorage
    from app.services import render as render_module

    storage = DatabaseStorage(str(tmp_path / "render-creation-stale"))
    _save_sqlite_owner_approved_storyboard(storage)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    blueprint.approved_version_id = "replaced-version"
    storage.save_storyboard_blueprint(blueprint)
    monkeypatch.setattr(render_module, "_storage", storage)

    with pytest.raises(ValueError, match="storyboard_approval_stale"):
        _create_job_with_render_service(storage)

    assert storage.list_jobs(project_id=PROJECT_ID) == []


def test_live_sqlite_storage_accepts_only_authenticated_current_owner_approval(tmp_path):
    from app.data.storage import DatabaseStorage
    from app.models import StudioProject
    from app.models.storyboard_blueprint import (
        StoryboardBlueprint,
        StoryboardBlueprintStatus,
        StoryboardBlueprintVersion,
        StoryboardShot,
        StoryboardShotStatus,
    )

    storage = DatabaseStorage(str(tmp_path / "owner-authorization"))
    storage.save_project(StudioProject(project_id=PROJECT_ID, title="Authorization proof"))
    storage.access_save_user({"username": OWNER_ID, "user_id": OWNER_ID}, create=True)
    storage.access_claim_project(PROJECT_ID, OWNER_ID)

    source_job = _authorized_job()
    manifest = source_job.metadata["creative_generation_manifest"]
    contract = FrozenGenerationContract.from_record(source_job.metadata["creative_generation_contract"])
    storage.save_job(source_job)
    blueprint = StoryboardBlueprint(
        blueprint_id=BLUEPRINT_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        current_version_id=VERSION_ID,
        approved_version_id=VERSION_ID,
        status=StoryboardBlueprintStatus.APPROVED,
    )
    version = StoryboardBlueprintVersion(
        version_id=VERSION_ID,
        blueprint_id=BLUEPRINT_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        status=StoryboardBlueprintStatus.APPROVED,
        approved_at="2026-10-10T12:00:00Z",
        approved_by=OWNER_ID,
        metadata={"production_approval": {"actor_id": OWNER_ID, "actor_authenticated": True}},
    )
    shot = StoryboardShot(
        storyboard_shot_id=STORYBOARD_SHOT_ID,
        blueprint_id=BLUEPRINT_ID,
        version_id=VERSION_ID,
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        shot_id=SHOT_ID,
        shot_number=1,
        status=StoryboardShotStatus.APPROVED,
    )
    storage.save_storyboard_blueprint(blueprint)
    storage.save_storyboard_blueprint_version(version)
    storage.save_storyboard_shot(shot)

    persisted_job = storage.get_job(source_job.id)
    assert persisted_job is not None
    assert authorize_runway_submission(persisted_job, storage=storage).allowed is True

    wrong_actor_job = persisted_job.model_copy(deep=True)
    wrong_actor_job.metadata["production_request_actor_id"] = "not-owner"
    assert authorize_runway_submission(wrong_actor_job, storage=storage).reason == "durable_render_job_identity_mismatch"

    version.metadata["production_approval"]["actor_authenticated"] = False
    storage.save_storyboard_blueprint_version(version)
    assert authorize_runway_submission(persisted_job, storage=storage).reason == "storyboard_owner_approval_missing"
    assert contract.manifest_fingerprint == manifest["manifest_fingerprint"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tamper", "expected_reason"),
    [
        ("prompt", "last-mile provider boundary"),
        ("manifest", "frozen_generation_contract_integrity_failed"),
        ("storyboard", "frozen_storyboard_shot_identity_mismatch"),
        ("owner", "project_owner_mismatch"),
    ],
)
async def test_router_boundary_revalidates_authority_after_estimate_before_live_submit(
    monkeypatch, tamper, expected_reason,
):
    job = _authorized_job()
    storage = _authority_storage(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    from app.services.providers import runway_router_provider

    provider_calls = []
    def fake_authorized_submit(*args, **kwargs):
        if kwargs.get("dry_run"):
            provider_calls.append("estimate")
            durable = storage.get_job(job.id)
            if tamper == "prompt":
                durable.input_payload.prompt = "altered after estimate"
            elif tamper == "manifest":
                durable.metadata["creative_generation_manifest"]["shots"][0]["shot_prompt"] = "altered after estimate"
            elif tamper == "storyboard":
                durable.input_payload.parameters["storyboard"]["version_id"] = "stale-version"
            else:
                storage.access_project_owner = lambda _project_id: "new-owner"
            if tamper != "owner":
                storage.get_job = lambda job_id: durable.model_copy(deep=True) if job_id == job.id else None
            return {"status": "dry_run", "url": None, "file_path": None,
                    "meta": {"estimated_cost_credits": 1}}
        provider_calls.append("live")
        return {"status": "success", "url": "https://cdn.test/output.mp4",
                "file_path": None, "meta": {"runway_task_id": "task-1"}}
    monkeypatch.setattr(runway_router_provider, "submit_runway_router_video_render", fake_authorized_submit)
    monkeypatch.setattr(generation_cost_gate, "enforce_shot_limit", lambda *args, **kwargs: {})
    monkeypatch.setattr("app.services.render._storage", storage)
    monkeypatch.setattr(generation_cost_gate, "_renderer", SimpleNamespace(
        list_jobs=lambda **_kwargs: [],
    ))
    monkeypatch.setattr("app.services.providers.runway_router_provider.get_runway_router_api_key", lambda: "test-key")

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    result = await adapter.submit_job(job)

    assert result.status == "failed"
    if provider_calls == ["estimate"]:
        assert expected_reason in result.error_message
    else:
        assert result.metadata["production_authorization"]["reason"] == expected_reason
    assert "live" not in provider_calls


@pytest.mark.asyncio
async def test_router_boundary_denies_before_submission_when_owner_approval_is_invalid(monkeypatch):
    job = _authorized_job(actor_id="intruder")
    storage = _authority_storage(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    provider_calls = []

    async def record_provider_submission(_job):
        provider_calls.append("submit")
        return _job

    monkeypatch.setattr(adapter, "_submit_job_after_authorization", record_provider_submission)

    result = await adapter.submit_job(job)

    assert result.status == "failed"
    assert result.metadata["production_authorization"] == {
        "allowed": False,
        "reason": "project_owner_mismatch",
        "project_id": PROJECT_ID,
        "job_id": "job-contract-test",
    }
    assert provider_calls == []


@pytest.mark.asyncio
async def test_router_boundary_submits_only_after_durable_owner_approval(monkeypatch):
    job = _authorized_job()
    storage = _authority_storage(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    provider_calls = []

    async def record_provider_submission(current_job, *, authority_storage=None):
        provider_calls.append(current_job.id)
        current_job.status = "rendering"
        return current_job

    async def authorized_provider_submission(current_job, *, authority_storage=None):
        assert authority_storage is storage
        return await record_provider_submission(current_job, authority_storage=authority_storage)

    monkeypatch.setattr(adapter, "_submit_job_after_authorization", authorized_provider_submission)

    result = await adapter.submit_job(job)

    assert result.status == "rendering"
    assert result.metadata["production_authorization"]["allowed"] is True
    assert result.metadata["production_authorization"]["actor_id"] == OWNER_ID
    assert provider_calls == ["job-contract-test"]


@pytest.mark.asyncio
async def test_queue_dispatch_keeps_owner_authorization_on_canonical_submission(monkeypatch):
    job = _authorized_job(actor_id="intruder")
    storage = _authority_storage(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    submitted = []

    async def submit_authorized(current_job, *, authority_storage=None):
        submitted.append(current_job.id)
        current_job.status = "rendering"
        return current_job

    monkeypatch.setattr(adapter, "_submit_job_after_authorization", submit_authorized)
    fake_render = SimpleNamespace(
        get_job=lambda job_id: job if job_id == job.id else None,
        submit_job=lambda job_id: adapter.submit_job(job),
    )
    queue = ProductionQueueService(storage=storage, render_svc=fake_render, worker_owner_id="authorization-test-worker")
    item = queue.enqueue_item(__import__("app.models.production_queue", fromlist=["ProductionQueueItemCreate", "ProductionQueueWorkType"]).ProductionQueueItemCreate(
        project_id=PROJECT_ID,
        work_type=__import__("app.models.production_queue", fromlist=["ProductionQueueWorkType"]).ProductionQueueWorkType.RENDER_JOB,
        canonical_type="render_job",
        canonical_id=job.id,
        provider="runway_router",
        shot_id=job.shot_id,
    ))

    from datetime import datetime, timedelta

    item = storage.acquire_queue_lease_for_item(
        item.queue_item_id,
        queue.worker_owner_id,
        datetime.now().isoformat(),
        (datetime.now() + timedelta(seconds=300)).isoformat(),
    )
    result = await queue.execute_leased_item(item)

    assert result["status"] == "failed"
    assert submitted == []


@pytest.mark.asyncio
async def test_direct_execution_boundary_call_without_authority_fails_closed(monkeypatch):
    """Calling _submit_job_after_authorization directly cannot bypass auth."""
    from app.services.providers import runway_router_provider

    job = _authorized_job()
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: None)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    provider_calls = []

    def capture(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("unauthorized direct execution must fail before Router HTTP")

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)

    result = await adapter._submit_job_after_authorization(job)

    assert result.status == "failed"
    assert result.metadata["production_authorization"] == {
        "allowed": False,
        "reason": "durable_production_storage_required",
        "project_id": PROJECT_ID,
        "job_id": job.id,
    }
    assert provider_calls == []


@pytest.mark.asyncio
async def test_direct_execution_boundary_call_with_revoked_owner_fails_closed(monkeypatch):
    from app.services.providers import runway_router_provider

    job = _authorized_job()
    storage = _authority_storage(job)
    storage.access_project_owner = lambda _project_id: "new-owner"
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    provider_calls = []

    def capture(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("revoked owner must fail before Router HTTP")

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)

    result = await adapter._submit_job_after_authorization(job)

    assert result.status == "failed"
    assert result.metadata["production_authorization"] == {
        "allowed": False,
        "reason": "project_owner_mismatch",
        "project_id": PROJECT_ID,
        "job_id": job.id,
    }
    assert provider_calls == []


@pytest.mark.asyncio
async def test_retry_path_enforces_stale_approval_before_provider_contact(monkeypatch, tmp_path):
    """RenderService.retry_job funnels through the same execution boundary."""
    from app.data.storage import DatabaseStorage
    from app.services import render as render_module
    from app.services.providers import runway_router_provider

    storage = DatabaseStorage(str(tmp_path / "render-retry-authority"))
    _save_sqlite_owner_approved_storyboard(storage)
    monkeypatch.setattr(render_module, "_storage", storage)
    monkeypatch.setattr(
        "app.services.recovery_lineage_guard.verify_render_lineage", lambda _path: {"ok": True}
    )
    # Reference-shape validation is covered elsewhere; this test isolates the
    # owner-authority gate on the retry path (same stub pattern as the
    # queued-state persistence regression).
    monkeypatch.setattr(render_module, "validate_generation_payload", lambda **_kwargs: {})
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    created = _create_job_with_render_service(storage)
    # Align the frozen binding exactly as the canonical pipeline stores it:
    # the manifest row and the job metadata carry the same binding rows, so
    # the resubmission integrity check passes and the test reaches the
    # owner-authority gate it is actually exercising.
    job = storage.get_job(created.id)
    binding = [
        {key: row.get(key) for key in (
            "ref_id", "project_id", "uri", "target_type", "target_id", "role", "category",
            "canonical", "approval_state", "source_kind", "kind",
        ) if key in row}
        for row in job.metadata["frozen_reference_binding"]
    ]
    manifest = job.metadata["creative_generation_manifest"]
    from app.services.reference_validation import reference_binding_digest

    manifest["shots"][0]["reference_binding"] = copy.deepcopy(binding)
    job.metadata["frozen_reference_binding"] = copy.deepcopy(binding)
    job.metadata["frozen_reference_binding_sha256"] = reference_binding_digest(binding)
    for _ in range(3):
        manifest["manifest_fingerprint"] = ""
        fingerprint = recompute_manifest_fingerprint(manifest)
        manifest["manifest_fingerprint"] = fingerprint
        contract = replace(
            FrozenGenerationContract.from_record(job.metadata["creative_generation_contract"]),
            manifest_fingerprint=fingerprint,
        )
        manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
        job.metadata.update(
            creative_generation_contract=contract.to_record(),
            creative_generation_manifest=manifest,
            creative_manifest_fingerprint=fingerprint,
            creative_contract_digest=contract.creative_digest(),
        )
    storage.save_job(job)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    blueprint.approved_version_id = "replaced-version"
    storage.save_storyboard_blueprint(blueprint)
    provider_calls = []

    def capture(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("stale approval must fail before Router HTTP")

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)
    service = render_module.RenderService()
    failed = storage.get_job(created.id)
    failed.status = "failed"
    storage.save_job(failed)
    service._jobs[created.id] = failed

    result = await service.retry_job(created.id)

    assert result.status == "failed"
    assert result.metadata["production_authorization"]["reason"] == "storyboard_approval_stale"
    assert provider_calls == []


@pytest.mark.asyncio
async def test_queue_redispatch_with_revoked_approval_makes_zero_provider_calls(monkeypatch):
    from app.services.providers import runway_router_provider

    job = _authorized_job(actor_id="intruder")
    storage = _authority_storage(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    adapter = RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Model Router", enabled=True)
    )
    provider_calls = []

    def capture(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("revoked approval must fail before Router HTTP")

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)
    fake_render = SimpleNamespace(
        get_job=lambda job_id: job if job_id == job.id else None,
        submit_job=lambda job_id: adapter.submit_job(job),
    )
    queue = ProductionQueueService(storage=storage, render_svc=fake_render, worker_owner_id="authorization-test-worker")
    item = queue.enqueue_item(__import__("app.models.production_queue", fromlist=["ProductionQueueItemCreate", "ProductionQueueWorkType"]).ProductionQueueItemCreate(
        project_id=PROJECT_ID,
        work_type=__import__("app.models.production_queue", fromlist=["ProductionQueueWorkType"]).ProductionQueueWorkType.RENDER_JOB,
        canonical_type="render_job",
        canonical_id=job.id,
        provider="runway_router",
        shot_id=job.shot_id,
    ))

    from datetime import datetime, timedelta

    item = storage.acquire_queue_lease_for_item(
        item.queue_item_id,
        queue.worker_owner_id,
        datetime.now().isoformat(),
        (datetime.now() + timedelta(seconds=300)).isoformat(),
    )
    result = await queue.execute_leased_item(item)

    assert result["status"] == "failed"
    assert provider_calls == []
