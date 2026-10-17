"""R4.5 session B1 — freeze-integrity tests (F7, F9, F8).

Proves, from evidence, that a freshly created pipeline Router job carries
inputs matching its frozen inputs, takes no mutation after authorization,
and records its selection metadata as digest-linked evidence instead of
dropping it — while every tamper control still catches mutation.

Guardrails: synthetic fixtures only (phase6 tmp fixture + the R45 harness),
sockets blocked by the r43k plugin, provider tripwires on every refusal
(zero transport calls asserted), Runway the only provider, no live calls,
no schema change, no stored-contract migration. Checkpoint G is untouched.
Scene 002 paths are not exercised here (separate suites own them).
"""
from __future__ import annotations

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from test_multishot_integrity_phase6_e2e import (  # real production pipeline fixture
    PROJECT_ID,
    SCENE_ID,
    SHOT_IDS,
    FakeAudioService,
    FakeStitchingService,
    _prepare_approved_successor,
    phase6,  # noqa: F401 — re-exported so pytest resolves it as a fixture
)
from test_r45_shared_router_gates import (
    R45_PROJECT,
    R45_SCENE,
    R45_SHOT,
    _r45_build,
    _r45_create,
)

PROBE_ROUTER_CONFIG_ID = "r45b1-router"
PROBE_OWNER = "r45b1-owner"

F7_COMPARED_KEYS = ("scene_coverage", "scene_coverage_shot", "dialogue_handoff")


def _tripwire_transport(calls: list):
    def _capture(url, *, method="GET", payload=None, api_key=None):
        calls.append({"url": url, "method": method, "payload": copy.deepcopy(payload)})
        raise AssertionError("tamper refusal must not touch the provider transport")

    return _capture


def _router_adapter_with_tripwire(monkeypatch: pytest.MonkeyPatch, calls: list):
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.services.providers import runway_router_provider

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", _tripwire_transport(calls))
    config = ProviderConfig(
        provider_id="runway_router",
        name="Runway Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
    )
    return RunwayRouterAdapter(config)


def _reason(job) -> str:
    return str(((job.metadata or {}).get("router_execution") or {}).get("reason") or "")


# ── F7: store more ────────────────────────────────────────────────────────────


def test_f7_creation_persists_adapter_compared_keys(tmp_path, monkeypatch):
    """create_job persists the adapter-compared keys from the frozen contract."""
    from app.services.generation_contract import FrozenGenerationContract

    artifact = _r45_build()
    job, storage = _r45_create(artifact, tmp_path, monkeypatch)
    payload = FrozenGenerationContract.from_record(
        job.metadata["creative_generation_contract"]
    ).payload()
    params = job.input_payload.parameters or {}
    for key in F7_COMPARED_KEYS:
        assert key in params, f"freshly created Router job must carry {key}"
        assert params[key] == payload[key]
    # The durable row carries the same snapshot (authorization compares it).
    durable = storage.get_job(job.id)
    assert (durable.input_payload.parameters or {}) == params


def test_f7_non_router_jobs_unchanged(tmp_path, monkeypatch):
    """Non-router jobs gain no frozen-contract keys at creation."""
    from app.services import render as render_module
    from app.services.render import RenderService

    monkeypatch.setattr(render_module, "_storage", None)
    service = RenderService()
    job = service.create_job(
        project_id="proj-nr",
        shot_id="shot-nr-001",
        provider="simulated",
        prompt="A quiet room.",
        parameters={"seed": 5, "custom": "x"},
    )
    # The non-router enrichment pipeline (prompt budget, intent fidelity,
    # ...) still applies, but none of the frozen-contract keys may appear.
    for key in F7_COMPARED_KEYS:
        assert key not in (job.input_payload.parameters or {})


# ── F9: seed before freeze ────────────────────────────────────────────────────


def _b1_pipeline(phase6_fixture):
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )

    return SceneProductionPipelineService(
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        backend_root=phase6_fixture["backend_root"],
    )


def test_f9_router_seed_decided_before_freeze(phase6, monkeypatch):
    """A pipeline Router batch carries a decided seed end-to-end before any durable write."""
    from app.services.generation_contract import FrozenGenerationContract

    _prepare_approved_successor(phase6)
    pipeline = _b1_pipeline(phase6)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID,
        project=phase6["project"], provider="runway_router",
    )
    assert batch.get("ready") is True
    for entry in batch["entries"]:
        assert entry.get("seed") is not None, "seed must be decided before the freeze"
        frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        assert frozen.seed == entry["seed"]
        assert frozen.payload()["seed"] == entry["seed"]
    manifest_rows = {row["shot_id"]: row for row in batch["manifest"]["shots"]}
    for entry in batch["entries"]:
        assert manifest_rows[entry["shot_id"]]["seed"] == entry["seed"]
    # A second prepare reuses the stored seed instead of inventing a new one.
    again = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID,
        project=phase6["project"], provider="runway_router",
    )
    for first, second in zip(batch["entries"], again["entries"]):
        assert second["seed"] == first["seed"]


def test_f9_non_router_prepare_invents_no_seed(phase6, monkeypatch):
    """Non-router batches keep the pre-existing seed behavior (none decided here)."""
    _prepare_approved_successor(phase6)
    pipeline = _b1_pipeline(phase6)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID,
        project=phase6["project"], provider="simulated",
    )
    for entry in batch["entries"]:
        assert entry.get("seed") is None


def test_f9_seed_helper_reuses_stored_seed():
    """Unit-pin: a stored shot seed is reused verbatim."""
    from unittest.mock import Mock

    from app.services.scene_production_pipeline_service import (
        _decide_router_seed_before_freeze,
    )

    store = Mock()
    store.get_shot_seed.return_value = {"seed": 4242, "seed_locked": False}
    # The helper imports get_storage from app.data.storage at call time; patch there.
    import app.data.storage as storage_module

    old = storage_module.get_storage
    storage_module.get_storage = lambda *_a, **_k: store
    try:
        assert _decide_router_seed_before_freeze(project_id="p", shot_id="s") == 4242
    finally:
        storage_module.get_storage = old
    store.save_shot_seed.assert_not_called()


def test_f9_seed_helper_fail_soft_without_storage():
    """Unit-pin: without a durable store no seed is invented (today's behavior)."""
    from app.services.scene_production_pipeline_service import (
        _decide_router_seed_before_freeze,
    )

    import app.data.storage as storage_module

    old = storage_module.get_storage
    storage_module.get_storage = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no store"))
    try:
        assert _decide_router_seed_before_freeze(project_id="p", shot_id="s") is None
    finally:
        storage_module.get_storage = old


@pytest.mark.asyncio
async def test_f9_decided_seed_takes_no_submit_mutation(tmp_path, monkeypatch):
    """A job whose seed was decided before the freeze takes no mutation after authorization."""
    from app.services import render as render_module

    artifact = _r45_build()  # hand-frozen with seed 43: decided before any durable write
    job, storage = _r45_create(artifact, tmp_path, monkeypatch)

    boundary: dict = {}

    class _NoTransportAdapter:
        async def submit_job(self, current, *, reference_storage=None):
            # Snapshot exactly what would reach the provider and compare it
            # against the durable row at that instant: any post-authorization
            # mutation (the F9 bug shape) fails here.
            boundary["at_adapter"] = current.input_payload.model_dump(mode="json")
            boundary["durable_at_adapter"] = storage.get_job(current.id).input_payload.model_dump(mode="json")
            current.status = "rendering"
            return current

    monkeypatch.setattr(render_module, "get_adapter", lambda *args, **kwargs: _NoTransportAdapter())
    for name in (
        "_run_continuity_review",
        "_run_render_quality_check",
        "_run_character_reference_lock",
    ):
        monkeypatch.setattr(render_module, name, AsyncMock())
    service = render_module.RenderService()
    service._jobs[job.id] = storage.get_job(job.id)
    before = storage.get_job(job.id).input_payload.model_dump(mode="json")
    assert (before.get("parameters") or {}).get("seed") == 43
    result = await service.submit_job(job.id)
    assert boundary["at_adapter"] == boundary["durable_at_adapter"]
    assert (boundary["at_adapter"].get("parameters") or {}).get("seed") == 43
    assert (boundary["durable_at_adapter"].get("parameters") or {}).get("seed") == 43
    assert result.input_payload.parameters["seed"] == 43
    assert storage.get_shot_seed(R45_PROJECT, job.shot_id) is None


def test_f9_seed_mutation_after_last_write_still_denied(tmp_path, monkeypatch):
    """The F9 bug shape — mutating the seed after the last durable write — is still denied."""
    from app.services.production_authorization_service import authorize_runway_submission

    artifact = _r45_build()
    job, storage = _r45_create(artifact, tmp_path, monkeypatch)
    job.input_payload.parameters = dict(job.input_payload.parameters or {}, seed=999)
    decision = authorize_runway_submission(job, storage=storage, require_durable=True)
    assert decision.allowed is False
    assert decision.reason == "durable_render_job_identity_mismatch"


# ── F8: freeze {} + digest-linked selection evidence ───────────────────────────


def test_f8_router_freeze_empty_creative_with_evidence(phase6, monkeypatch):
    """A pipeline Router batch freezes {} creative params and records evidence, not silence."""
    import json

    from app.services.generation_contract import (
        ROUTER_SELECTION_EVIDENCE_KEYS,
        FrozenGenerationContract,
    )

    _prepare_approved_successor(phase6)
    pipeline = _b1_pipeline(phase6)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID,
        project=phase6["project"], provider="runway_router",
    )
    assert batch.get("ready") is True
    for entry in batch["entries"]:
        frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        assert json.loads(frozen.creative_parameters_json) == {}
        evidence = entry.get("router_selection_evidence")
        assert isinstance(evidence, dict)
        assert set(evidence["selection"]).issubset(set(ROUTER_SELECTION_EVIDENCE_KEYS))
        assert "character_focus" in evidence["selection"]
        assert evidence["contract_digest"] == frozen.creative_digest()
        assert evidence["contract_digest"] == entry["generation_contract_digest"]
    manifest_rows = {row["shot_id"]: row for row in batch["manifest"]["shots"]}
    for entry in batch["entries"]:
        assert manifest_rows[entry["shot_id"]]["parameters"] == {}


def test_f8_non_router_freeze_keeps_selection_keys(phase6, monkeypatch):
    """Non-router batches keep the nine selection keys frozen and carry no evidence."""
    import json

    from app.services.generation_contract import FrozenGenerationContract

    _prepare_approved_successor(phase6)
    pipeline = _b1_pipeline(phase6)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID,
        project=phase6["project"], provider="simulated",
    )
    assert batch.get("ready") is True
    for entry in batch["entries"]:
        frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        assert sorted(json.loads(frozen.creative_parameters_json)) != []
        assert "router_selection_evidence" not in entry


def _b1_create_with_evidence(artifact: dict, tmp_path, monkeypatch, evidence, *, storage_tag="0", extra_parameters=None):
    """Hand-built Router job creation with caller-supplied selection evidence."""
    from app.access_context import access_user_id
    from app.data.storage import DatabaseStorage
    from app.models import StudioProject
    from app.services import render as render_module
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / f"r45b1-evidence-storage-{storage_tag}"))
    monkeypatch.setattr(render_module, "_storage", storage)
    monkeypatch.setattr(
        render_module, "get_adapter",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("creation must not touch provider adapters")
        ),
    )
    from app.models.storyboard_blueprint import (
        StoryboardBlueprint,
        StoryboardBlueprintStatus,
        StoryboardBlueprintVersion,
        StoryboardShot,
        StoryboardShotStatus,
    )

    storage.save_project(StudioProject(project_id=R45_PROJECT, title="R4.5 B1"))
    storage.access_save_user({"username": "owner-r45", "user_id": "owner-r45"}, create=True)
    storage.access_claim_project(R45_PROJECT, "owner-r45")
    storage.save_storyboard_blueprint(StoryboardBlueprint(
        blueprint_id="board-r45", project_id=R45_PROJECT, scene_id=R45_SCENE,
        current_version_id="test-board-v1", approved_version_id="test-board-v1",
        status=StoryboardBlueprintStatus.APPROVED,
    ))
    storage.save_storyboard_blueprint_version(StoryboardBlueprintVersion(
        version_id="test-board-v1", blueprint_id="board-r45", project_id=R45_PROJECT,
        scene_id=R45_SCENE, status=StoryboardBlueprintStatus.APPROVED,
        approved_at="2026-10-10T12:00:00Z", approved_by="owner-r45",
        metadata={"production_approval": {"actor_id": "owner-r45", "actor_authenticated": True}},
    ))
    storage.save_storyboard_shot(StoryboardShot(
        storyboard_shot_id="board-r45", blueprint_id="board-r45", version_id="test-board-v1",
        project_id=R45_PROJECT, scene_id=R45_SCENE, shot_id=R45_SHOT, shot_number=1,
        status=StoryboardShotStatus.APPROVED,
    ))
    manifest = artifact["manifest"]
    contract_record = artifact["contract_record"]
    frozen = FrozenGenerationContract.from_record(contract_record)
    token = access_user_id.set("owner-r45")
    try:
        job = RenderService().create_job(
            project_id=R45_PROJECT,
            shot_id=R45_SHOT,
            provider="runway_router",
            prompt=frozen.prompt,
            parameters={
                "dialogue_handoff": contract_record["payload"]["dialogue_handoff"],
                "dialogue_lines": [],
                "scene_coverage": contract_record["payload"]["scene_coverage"],
                "scene_coverage_shot": contract_record["payload"]["scene_coverage_shot"],
                "camera_plan": contract_record["payload"]["camera_plan"],
                "camera_provenance": contract_record["payload"]["camera_provenance"],
                "camera_instructions": contract_record["payload"]["camera_instructions"],
                "camera_source_digest": contract_record["payload"]["camera_source_digest"],
                "camera_source_project_id": contract_record["payload"]["camera_source_project_id"],
                "camera_source_scene_id": contract_record["payload"]["camera_source_scene_id"],
                "camera_source_shot_id": contract_record["payload"]["camera_source_shot_id"],
                "camera_target_project_id": contract_record["payload"]["camera_target_project_id"],
                "camera_target_scene_id": contract_record["payload"]["camera_target_scene_id"],
                "camera_target_shot_id": contract_record["payload"]["camera_target_shot_id"],
                **(extra_parameters or {}),
            },
            reference_assets=[row["uri"] for row in manifest["shots"][0]["reference_binding"]],
            generation_contract=contract_record,
            creative_manifest=manifest,
            creative_manifest_fingerprint=artifact["fingerprint"],
            frozen_reference_binding=[dict(row) for row in manifest["shots"][0]["reference_binding"]],
            dialogue_handoff=contract_record["payload"]["dialogue_handoff"],
            prepared_generation_contract=contract_record,
            metadata={"router_selection_evidence": copy.deepcopy(evidence)},
        )
    finally:
        access_user_id.reset(token)
    return job, storage


def _b1_good_evidence(artifact: dict) -> dict:
    from app.services.generation_contract import (
        ROUTER_SELECTION_EVIDENCE_KEYS,
        FrozenGenerationContract,
    )

    contract_record = artifact["contract_record"]
    digest = FrozenGenerationContract.from_record(contract_record).creative_digest()
    return {
        "selection": {key: f"evidence-{key}" for key in ROUTER_SELECTION_EVIDENCE_KEYS},
        "contract_digest": digest,
    }


def test_f8_linked_evidence_persists_with_job(tmp_path, monkeypatch):
    """Digest-linked evidence is accepted at creation and persisted with the proof."""
    artifact = _r45_build()
    evidence = _b1_good_evidence(artifact)
    job, storage = _b1_create_with_evidence(artifact, tmp_path, monkeypatch, evidence)
    persisted = (storage.get_job(job.id).metadata or {}).get("router_selection_evidence")
    assert persisted == evidence


def test_f8_mismatched_evidence_digest_rejected(tmp_path, monkeypatch):
    """A selection-evidence entry whose digest does not match is rejected at creation."""
    artifact = _r45_build()
    evidence = _b1_good_evidence(artifact)
    evidence["contract_digest"] = "0" * 64
    with pytest.raises(ValueError, match="does not match the frozen generation contract"):
        _b1_create_with_evidence(artifact, tmp_path, monkeypatch, evidence)


def test_f8_tampered_evidence_entry_rejected(tmp_path, monkeypatch):
    """Malformed evidence (non-selection keys, non-dict selection) is rejected at creation."""
    artifact = _r45_build()
    bad_selection = _b1_good_evidence(artifact)
    bad_selection["selection"] = {"creative_requirement_smuggled": True, **bad_selection["selection"]}
    with pytest.raises(ValueError, match="non-selection keys"):
        _b1_create_with_evidence(artifact, tmp_path, monkeypatch, bad_selection)
    bad_shape = _b1_good_evidence(artifact)
    bad_shape["selection"] = ["not", "a", "dict"]
    with pytest.raises(ValueError, match="malformed"):
        _b1_create_with_evidence(artifact, tmp_path, monkeypatch, bad_shape, storage_tag="1")


def test_f8_evidence_with_nonempty_creative_rejected(tmp_path, monkeypatch):
    """Evidence alongside non-empty frozen creative parameters is rejected (no silent drop)."""
    artifact = _r45_build()
    evidence = _b1_good_evidence(artifact)
    # Forge a contract whose creative parameters are non-empty by freezing the
    # same approved values plus one creative key through the public freeze API.
    import copy as _copy

    from app.services.generation_contract import (
        FrozenGenerationContract,
        freeze_generation_contract,
    )

    record = artifact["contract_record"]
    payload = record["payload"]
    parameters = dict(payload.get("creative_parameters") or {})
    assert parameters == {}
    parameters["injected_creative_demand"] = "must reach the wire"
    _params = {
        "duration": payload["duration"],
        "aspect_ratio": payload["aspect_ratio"],
        "resolution": payload["resolution"],
        "seed": payload["seed"],
        "audio_intent": "generate",
        "negative_prompt": payload["negative_prompt"],
        "camera_plan": payload["camera_plan"],
        "camera_provenance": payload["camera_provenance"],
        "camera_instructions": payload["camera_instructions"],
        "camera_source_digest": payload["camera_source_digest"],
        "camera_source_project_id": payload["camera_source_project_id"],
        "camera_source_scene_id": payload["camera_source_scene_id"],
        "camera_source_shot_id": payload["camera_source_shot_id"],
        "camera_target_project_id": payload["camera_target_project_id"],
        "camera_target_scene_id": payload["camera_target_scene_id"],
        "camera_target_shot_id": payload["camera_target_shot_id"],
        "reference_roles": [ref["studio_role"] for ref in payload["references"]],
        "dialogue_handoff": payload["dialogue_handoff"],
        "scene_coverage": payload["scene_coverage"],
        "scene_coverage_shot": payload["scene_coverage_shot"],
        **parameters,
    }
    forged = freeze_generation_contract(
        shot_id=payload["shot_id"],
        prompt=payload["prompt"],
        negative_prompt=payload["negative_prompt"],
        reference_assets=[dict(ref) for ref in payload["references"]],
        parameters=_params,
        dialogue_handoff=_copy.deepcopy(payload["dialogue_handoff"]),
        scene_coverage=_copy.deepcopy(payload["scene_coverage"]),
        scene_coverage_shot=_copy.deepcopy(payload["scene_coverage_shot"]),
    )
    # Rebuild a consistent triple around the forged contract (same pattern the
    # shared-gates harness uses for tampered artifacts).
    from dataclasses import replace as _replace

    from app.services.shot_manifest import recompute_manifest_fingerprint

    forged_artifact = _copy.deepcopy(artifact)
    forged_manifest = forged_artifact["manifest"]
    forged_manifest["shots"][0]["parameters"] = dict(
        FrozenGenerationContract.from_record(forged.to_record()).payload()["creative_parameters"]
    )
    forged_manifest["shots"][0]["generation_contract_digest"] = forged.creative_digest()
    forged_manifest["manifest_fingerprint"] = ""
    forged_manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(forged_manifest)
    forged = _replace(forged, manifest_fingerprint=forged_manifest["manifest_fingerprint"])
    forged_manifest["shots"][0]["generation_contract_digest"] = forged.creative_digest()
    forged_artifact["contract_record"] = forged.to_record()
    forged_artifact["fingerprint"] = forged_manifest["manifest_fingerprint"]
    forged_evidence = _b1_good_evidence(forged_artifact)
    with pytest.raises(ValueError, match="requires empty frozen creative parameters"):
        _b1_create_with_evidence(
            forged_artifact, tmp_path, monkeypatch, forged_evidence,
            extra_parameters={"injected_creative_demand": "must reach the wire"},
        )
    # And the unchanged reconstruction gate still rejects the non-empty creative.
    from app.services.providers.runway_router_provider import (
        reconstruct_runway_router_video_request,
    )

    with pytest.raises(ValueError, match="cannot represent frozen creative parameters"):
        reconstruct_runway_router_video_request(
            forged_artifact["contract_record"], forged_artifact["manifest"]
        )


def test_f8_pipeline_nonempty_creative_still_rejected_by_reconstruction(phase6, monkeypatch):
    """The unchanged reconstruction gate rejects pipeline contracts that still carry selection keys."""
    from app.services.providers.runway_router_provider import (
        reconstruct_runway_router_video_request,
    )

    _prepare_approved_successor(phase6)
    pipeline = _b1_pipeline(phase6)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID,
        project=phase6["project"], provider="simulated",
    )
    entry = batch["entries"][0]
    with pytest.raises(ValueError, match="cannot represent frozen creative parameters"):
        reconstruct_runway_router_video_request(entry["generation_contract"], batch["manifest"])


def test_f8_evidence_tamper_after_persist_denied(tmp_path, monkeypatch):
    """Post-persist mutation of the evidence entry is denied by durable identity."""
    from app.services.production_authorization_service import authorize_runway_submission

    artifact = _r45_build()
    evidence = _b1_good_evidence(artifact)
    job, storage = _b1_create_with_evidence(artifact, tmp_path, monkeypatch, evidence)
    durable = storage.get_job(job.id)
    tampered_meta = dict(durable.metadata or {})
    tampered_evidence = dict(tampered_meta["router_selection_evidence"])
    tampered_evidence["selection"] = {"character_focus": ["Mallory"]}
    tampered_meta["router_selection_evidence"] = tampered_evidence
    durable.metadata = tampered_meta
    storage.save_job(durable)
    # The durable row now differs from the in-memory authorized snapshot.
    decision = authorize_runway_submission(job, storage=storage, require_durable=True)
    assert decision.allowed is False
    assert decision.reason == "durable_render_job_identity_mismatch"


@pytest.mark.parametrize("key", F7_COMPARED_KEYS)
def test_f7_tampered_compared_key_still_mismatches(tmp_path, monkeypatch, key):
    """Altering any compared key after creation still fails closed with zero transport."""
    artifact = _r45_build()
    job, storage = _r45_create(artifact, tmp_path, monkeypatch)
    calls: list = []
    adapter = _router_adapter_with_tripwire(monkeypatch, calls)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)

    durable = storage.get_job(job.id)
    tampered = dict(durable.input_payload.parameters or {})
    assert key in tampered
    tampered[key] = {"tampered": True}
    durable.input_payload.parameters = tampered
    storage.save_job(durable)

    submitted = asyncio.run(
        adapter._submit_job_after_authorization(
            storage.get_job(job.id), authority_storage=storage, reference_storage=storage
        )
    )
    assert submitted.status == "failed"
    assert _reason(submitted) == "mutable_render_input_mismatch"
    assert calls == []
