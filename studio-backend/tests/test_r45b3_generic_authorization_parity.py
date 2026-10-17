"""R4.5 session B3.1 — generic projection-authorization parity matrix (T4).

Proves preflight, creation, reconstruction, and the adapter agree on
identical artifacts now that the projection authorization is minted by the
production pipeline (F5 via ``scene_mint_service``):

* P1 preflight (with persisted-confirmation enforcement) is ready;
* P2 ``create_job`` persists the minted record byte-identical to the entry;
* P3 ``reconstruct_runway_router_video_request`` composes the wire
  referenceImages from the frozen proof (F8: empty creative parameters);
* P4 the real ``RunwayRouterAdapter`` dispatches through the declared
  authorization branch to a mocked transport, and its wire referenceImages
  are byte-identical to P3's.

Negative controls: no mint flag leaves entries byte-identical (None record);
no persisted confirmation blocks the batch with zero jobs; a tampered or
cross-shot record is refused by the adapter with zero transport calls.

No live provider contact: sockets blocked by the r43k plugin, Router
transport replaced by a recording double.
"""
from __future__ import annotations

import copy
import json
from unittest.mock import AsyncMock

import pytest

from test_multishot_integrity_phase6_e2e import (  # real production pipeline fixture
    CHECKPOINT_G_OWNER,
    CHECKPOINT_G_REJECTED_ENV_REF_ID,
    CHECKPOINT_G_ROUTER_CONFIG_ID,
    PROJECT_ID,
    SCENE_ID,
    SHOT_IDS,
    FakeAudioService,
    FakeStitchingService,
    _prepare_approved_successor,
    phase6,
)

PARITY_OWNER = CHECKPOINT_G_OWNER
PARITY_ROUTER_CONFIG_ID = "r45b3-parity-router"
REJECTED_ENV_REF_ID = CHECKPOINT_G_REJECTED_ENV_REF_ID

EXPECTED_REFERENCE_IMAGES = {
    SHOT_IDS[0]: [
        {"uri": "https://fixture.invalid/char-ivo.png", "role": "reference"},
        {"uri": "https://fixture.invalid/glassworks.png", "role": "reference"},
    ],
    SHOT_IDS[1]: [
        {"uri": "https://fixture.invalid/char-neri.png", "role": "reference"},
        {"uri": "https://fixture.invalid/glassworks.png", "role": "reference"},
    ],
}


def _transport_capture(calls: list[dict]):
    def _capture(url, *, method="GET", payload=None, api_key=None):
        calls.append({"url": url, "method": method, "payload": copy.deepcopy(payload)})
        if method == "POST" and payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": PARITY_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        if method == "POST":
            return {
                "dryRun": False,
                "id": "r45b3-task",
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": PARITY_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        return {
            "id": "r45b3-task",
            "status": "SUCCEEDED",
            "output": ["https://cdn.test/r45b3.mp4"],
        }

    return _capture


def _harness(monkeypatch: pytest.MonkeyPatch, storage, transport_calls: list[dict]):
    from app.services import generation_cost_gate, render as render_module
    from app.services.providers import runway_router_provider

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("RUNWAY_ROUTER_CONFIG_ID", PARITY_ROUTER_CONFIG_ID)
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setattr(
        runway_router_provider, "_runway_router_request", _transport_capture(transport_calls)
    )
    monkeypatch.setattr(runway_router_provider.time, "sleep", lambda *_: None)
    monkeypatch.setattr(render_module, "_storage", storage)
    for name in (
        "_run_continuity_review",
        "_run_render_quality_check",
        "_run_character_reference_lock",
        "_notify_update",
    ):
        monkeypatch.setattr(render_module, name, AsyncMock())
    monkeypatch.setattr(
        generation_cost_gate.generation_cost_gate, "enforce_shot_limit", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        generation_cost_gate.generation_cost_gate, "estimate_batch", lambda **_k: {"estimated": False}
    )
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_a, **_k: storage)


def _fixture_setup(fixture, *, with_confirmations: bool, with_rejected: bool = True):
    """Owner claim, optional genuine rejected row, optional durable confirmations."""
    from app.services.reference_asset_service import ReferenceAssetService

    storage = fixture["storage"]
    _prepare_approved_successor(fixture)
    storage.access_save_user({"username": PARITY_OWNER, "user_id": PARITY_OWNER}, create=True)
    storage.access_claim_project(PROJECT_ID, PARITY_OWNER)
    if with_rejected:
        storage.save_reference_asset({
            "ref_id": REJECTED_ENV_REF_ID,
            "project_id": PROJECT_ID,
            "kind": "environment",
            "image_url": "https://fixture.invalid/glassworks-alt.png",
            "target_type": "setting",
            "target_id": "set-glassworks-fixture",
            "category": "environment",
            "approval_state": "rejected",
            "canonical": False,
            "source_kind": "confirmed",
        })
    if with_confirmations:
        binder = ReferenceAssetService(storage)
        for shot_id in SHOT_IDS:
            fresh = binder.resolve_shot_binding(PROJECT_ID, shot_id)
            binder.record_shot_confirmation(PROJECT_ID, shot_id, fresh["binding_digest"])
    return storage


def _provision_owner_authority(storage, manifest):
    from app.models.storyboard_blueprint import StoryboardBlueprintStatus

    version_id = str((manifest.get("storyboard") or {}).get("storyboard_version") or "")
    assert version_id
    version = storage.get_storyboard_blueprint_version(version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = version.approved_at or "2026-10-16T00:00:00+00:00"
    version.approved_by = PARITY_OWNER
    version.metadata = {
        **(version.metadata or {}),
        "production_approval": {"actor_id": PARITY_OWNER, "actor_authenticated": True},
    }
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.current_version_id = version_id
    blueprint.approved_version_id = version_id
    storage.save_storyboard_blueprint(blueprint)
    for row in manifest.get("shots", []):
        shot = storage.get_storyboard_shot(str(row.get("storyboard_shot_id") or ""))
        if shot is not None:
            shot.status = StoryboardBlueprintStatus.APPROVED
            storage.save_storyboard_shot(shot)


def _pipeline(fixture, render_svc):
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    return SceneProductionPipelineService(
        render_svc=render_svc,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        backend_root=fixture["backend_root"],
    )


@pytest.mark.asyncio
async def test_parity_preflight_creation_reconstruction_adapter_agree(
    phase6, monkeypatch: pytest.MonkeyPatch
):
    from app.access_context import access_user_id
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.services import render as render_module
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.providers.runway_router_provider import (
        reconstruct_runway_router_video_request,
    )
    from app.services.reference_validation import (
        contract_comparison_binding,
        reference_binding_digest,
    )

    fixture = phase6
    storage = _fixture_setup(fixture, with_confirmations=True)
    transport_calls: list[dict] = []
    _harness(monkeypatch, storage, transport_calls)

    render_svc = render_module.RenderService()
    pipeline = _pipeline(fixture, render_svc)

    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="runway_router",
        mint_generic_authorization=True,
    )
    assert batch["ready"] is True, batch["blockers"]

    # ── P1: preflight with persisted-confirmation enforcement ─────────────
    authorization = pipeline.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=batch["entries"],
        shot_manifest=batch["manifest"],
        expected_digests=None,
        require_persisted_confirmation=True,
    )
    assert authorization["ready"] is True
    assert [row for row in authorization["shots"] if not row["ok"]] == []

    _provision_owner_authority(storage, batch["manifest"])

    findings: dict = {"shots": {}}
    router_config = ProviderConfig(
        provider_id="runway_router",
        name="Runway Model Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "model_routing"],
    )

    for entry in batch["entries"]:
        shot_id = str(entry["shot_id"])
        record: dict = {"shot_id": shot_id}
        manifest_row = next(
            row for row in batch["manifest"].get("shots", []) if row.get("shot_id") == shot_id
        )

        # The three binding views are identical artifacts.
        frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        canonical_refs = [
            row for row in frozen.payload()["references"]
            if isinstance(row, dict) and row.get("source") == "canonical_reference_binding"
        ]
        record["binding_digest_matches_record"] = (
            reference_binding_digest(entry["reference_binding"])
            == entry["reference_projection_authorization"]["frozen_reference_binding_sha256"]
        )
        record["comparison_shapes_identical"] = (
            contract_comparison_binding(manifest_row.get("reference_binding"))
            == contract_comparison_binding(canonical_refs)
            == contract_comparison_binding(entry["reference_binding"])
        )

        # ── P3: reconstruction composes the wire references ──────────────
        wire = reconstruct_runway_router_video_request(
            entry["generation_contract"], batch["manifest"], config_id=PARITY_ROUTER_CONFIG_ID
        )
        record["reconstructed_reference_images"] = (wire.get("input") or {}).get("referenceImages")

        # ── P2: creation persists the minted record byte-identical ────────
        token = access_user_id.set(PARITY_OWNER)
        try:
            job = render_svc.create_job(
                project_id=PROJECT_ID,
                shot_id=shot_id,
                provider="runway_router",
                prompt=entry["prompt"],
                reference_assets=list(entry["references"]),
                parameters=copy.deepcopy(entry["generation_settings"]),
                generation_contract=entry["generation_contract"],
                prepared_generation_contract=entry["generation_contract"],
                frozen_reference_binding=copy.deepcopy(entry["reference_binding"]),
                generation_context_id=str(entry.get("generation_context_id", "")),
                creative_manifest_fingerprint=batch["manifest"]["manifest_fingerprint"],
                creative_manifest=batch["manifest"],
                dialogue_handoff=copy.deepcopy(entry["dialogue_handoff"]),
                # Production-faithful stamp: generate_scene carries the entry
                # record into job metadata via _batch_authorized_job_metadata.
                metadata={
                    "reference_projection_authorization": copy.deepcopy(
                        entry["reference_projection_authorization"]
                    ),
                    "router_selection_evidence": copy.deepcopy(entry["router_selection_evidence"]),
                },
            )
        finally:
            access_user_id.reset(token)
        record["created_job_id"] = job.id
        record["creation_preserves_authorization"] = (
            (job.metadata or {}).get("reference_projection_authorization")
            == entry["reference_projection_authorization"]
        )
        record["creation_preserves_binding"] = (
            (job.metadata or {}).get("frozen_reference_binding") == entry["reference_binding"]
        )

        # ── P4: the real adapter dispatches through the declared branch ──
        submitted = await RunwayRouterAdapter(router_config)._submit_job_after_authorization(
            job, authority_storage=storage, reference_storage=storage
        )
        record["adapter_status"] = submitted.status
        record["adapter_reason"] = str(
            ((submitted.metadata or {}).get("router_execution") or {}).get("reason") or ""
        )
        findings["shots"][shot_id] = record

    submit_payloads = [
        row["payload"] for row in transport_calls
        if row["method"] == "POST" and not (row["payload"] or {}).get("dryRun")
    ]
    findings["submit_count"] = len(submit_payloads)
    findings["submit_reference_images"] = [
        (payload.get("input") or {}).get("referenceImages") for payload in submit_payloads
    ]

    print("\nR45B3_PARITY_FINDINGS " + json.dumps(findings, sort_keys=True, default=str))

    for shot_id in SHOT_IDS:
        record = findings["shots"][shot_id]
        assert record["binding_digest_matches_record"] is True, record
        assert record["comparison_shapes_identical"] is True, record
        assert record["reconstructed_reference_images"] == EXPECTED_REFERENCE_IMAGES[shot_id], record
        assert record["creation_preserves_authorization"] is True, record
        assert record["creation_preserves_binding"] is True, record
        assert record["adapter_status"] == "complete", record
    # Adapter wire references are byte-identical to reconstruction references.
    assert findings["submit_count"] == len(SHOT_IDS)
    for wire_images, shot_id in zip(findings["submit_reference_images"], SHOT_IDS):
        assert wire_images == EXPECTED_REFERENCE_IMAGES[shot_id]


def test_dry_run_without_mint_flag_stays_byte_identical(phase6):
    """No mint flag: generic Router entries carry no record (preview parity)."""
    from app.services import render as render_module
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService
    from test_multishot_integrity_phase6_e2e import FakeAudioService, FakeStitchingService

    fixture = phase6
    storage = _fixture_setup(fixture, with_confirmations=True)
    render_module._storage = storage
    try:
        pipeline = SceneProductionPipelineService(
            render_svc=render_module.RenderService(),
            audio_svc=FakeAudioService(),
            stitching_svc=FakeStitchingService(),
            backend_root=fixture["backend_root"],
        )
        batch = pipeline.prepare_scene_batch(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="runway_router",
        )
    finally:
        render_module._storage = None
    assert batch["ready"] is True
    assert all(entry["reference_projection_authorization"] is None for entry in batch["entries"])
    assert all(entry["generic_authorization_audit"] is None for entry in batch["entries"])


@pytest.mark.asyncio
async def test_mint_without_confirmation_blocks_batch_with_zero_jobs(
    phase6, monkeypatch: pytest.MonkeyPatch
):
    """Mint gating is fail-closed: no confirmation rows, no entries, no jobs."""
    from app.services import render as render_module
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService
    from app.services.stability import ValidationError
    from test_multishot_integrity_phase6_e2e import FakeAudioService, FakeStitchingService

    fixture = phase6
    storage = _fixture_setup(fixture, with_confirmations=False)
    transport_calls: list[dict] = []
    _harness(monkeypatch, storage, transport_calls)

    pipeline = _pipeline(fixture, render_module.RenderService())
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="runway_router",
        mint_generic_authorization=True,
    )
    assert batch["ready"] is False
    assert any("reference gate" in blocker for blocker in batch["blockers"])
    assert pipeline._prepared_scene_batches == {}
    with pytest.raises(ValidationError):
        await pipeline.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="runway_router",
            require_persisted_confirmation=True,
        )
    assert storage.list_jobs(PROJECT_ID) == []
    assert transport_calls == []


@pytest.mark.asyncio
async def test_adapter_refuses_tampered_or_cross_shot_record(
    phase6, monkeypatch: pytest.MonkeyPatch
):
    from app.access_context import access_user_id
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.services import render as render_module

    fixture = phase6
    storage = _fixture_setup(fixture, with_confirmations=True)
    transport_calls: list[dict] = []
    _harness(monkeypatch, storage, transport_calls)

    render_svc = render_module.RenderService()
    pipeline = _pipeline(fixture, render_svc)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="runway_router",
        mint_generic_authorization=True,
    )
    assert batch["ready"] is True
    _provision_owner_authority(storage, batch["manifest"])

    router_config = ProviderConfig(
        provider_id="runway_router",
        name="Runway Model Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "model_routing"],
    )
    adapter = RunwayRouterAdapter(router_config)
    reasons: list[str] = []

    def _create(shot_id: str):
        entry = next(row for row in batch["entries"] if row["shot_id"] == shot_id)
        token = access_user_id.set(PARITY_OWNER)
        try:
            return render_svc.create_job(
                project_id=PROJECT_ID,
                shot_id=shot_id,
                provider="runway_router",
                prompt=entry["prompt"],
                reference_assets=list(entry["references"]),
                parameters=copy.deepcopy(entry["generation_settings"]),
                generation_contract=entry["generation_contract"],
                prepared_generation_contract=entry["generation_contract"],
                frozen_reference_binding=copy.deepcopy(entry["reference_binding"]),
                generation_context_id=str(entry.get("generation_context_id", "")),
                creative_manifest_fingerprint=batch["manifest"]["manifest_fingerprint"],
                creative_manifest=batch["manifest"],
                dialogue_handoff=copy.deepcopy(entry["dialogue_handoff"]),
                metadata={
                    "reference_projection_authorization": copy.deepcopy(
                        entry["reference_projection_authorization"]
                    ),
                    "router_selection_evidence": copy.deepcopy(entry["router_selection_evidence"]),
                },
            )
        finally:
            access_user_id.reset(token)

    # Tampered record: authorized environment replaced by the rejected row.
    job = _create(SHOT_IDS[0])
    job.metadata["reference_projection_authorization"] = {
        **job.metadata["reference_projection_authorization"],
        "authorized_environment_ref_id": REJECTED_ENV_REF_ID,
    }
    storage.save_job(job)
    refused = await adapter._submit_job_after_authorization(
        job, authority_storage=storage, reference_storage=storage
    )
    reasons.append(str(((refused.metadata or {}).get("router_execution") or {}).get("reason") or ""))
    assert refused.status == "failed"

    # Cross-shot record: shot 1's authorization presented on shot 2's job.
    other = _create(SHOT_IDS[1])
    first_record = next(row for row in batch["entries"] if row["shot_id"] == SHOT_IDS[0])[
        "reference_projection_authorization"
    ]
    other.metadata["reference_projection_authorization"] = copy.deepcopy(first_record)
    storage.save_job(other)
    refused = await adapter._submit_job_after_authorization(
        other, authority_storage=storage, reference_storage=storage
    )
    reasons.append(str(((refused.metadata or {}).get("router_execution") or {}).get("reason") or ""))
    assert refused.status == "failed"

    assert reasons == ["reference_authorization_mismatch", "reference_authorization_mismatch"], reasons
    assert transport_calls == []


# ── Decision A1: exact equality replaces the non-empty rule ────────────────

def _a1_router_config():
    from app.models import ProviderConfig

    return ProviderConfig(
        provider_id="runway_router",
        name="Runway Model Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "model_routing"],
    )


def _a1_create(render_svc, batch, entry):
    from app.access_context import access_user_id

    shot_id = str(entry["shot_id"])
    token = access_user_id.set(PARITY_OWNER)
    try:
        return render_svc.create_job(
            project_id=PROJECT_ID,
            shot_id=shot_id,
            provider="runway_router",
            prompt=entry["prompt"],
            reference_assets=list(entry["references"]),
            parameters=copy.deepcopy(entry["generation_settings"]),
            generation_contract=entry["generation_contract"],
            prepared_generation_contract=entry["generation_contract"],
            frozen_reference_binding=copy.deepcopy(entry["reference_binding"]),
            generation_context_id=str(entry.get("generation_context_id", "")),
            creative_manifest_fingerprint=batch["manifest"]["manifest_fingerprint"],
            creative_manifest=batch["manifest"],
            dialogue_handoff=copy.deepcopy(entry["dialogue_handoff"]),
            metadata={
                "reference_projection_authorization": copy.deepcopy(
                    entry["reference_projection_authorization"]
                ),
                "router_selection_evidence": copy.deepcopy(entry["router_selection_evidence"]),
            },
        )
    finally:
        access_user_id.reset(token)


@pytest.mark.asyncio
async def test_a1_single_environment_scene_completes_end_to_end(
    phase6, monkeypatch: pytest.MonkeyPatch
):
    """A1: no rejected rows live means an empty rejected enumeration, and the
    full prepare -> create -> adapter path completes (previously refused)."""
    from app.adapters import RunwayRouterAdapter
    from app.services import render as render_module

    fixture = phase6
    storage = _fixture_setup(fixture, with_confirmations=True, with_rejected=False)
    transport_calls: list[dict] = []
    _harness(monkeypatch, storage, transport_calls)

    render_svc = render_module.RenderService()
    pipeline = _pipeline(fixture, render_svc)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="runway_router",
        mint_generic_authorization=True,
    )
    assert batch["ready"] is True, batch["blockers"]
    for entry in batch["entries"]:
        assert entry["reference_projection_authorization"]["rejected_environment_ref_ids"] == []
    _provision_owner_authority(storage, batch["manifest"])

    for entry in batch["entries"]:
        job = _a1_create(render_svc, batch, entry)
        submitted = await RunwayRouterAdapter(_a1_router_config())._submit_job_after_authorization(
            job, authority_storage=storage, reference_storage=storage
        )
        assert submitted.status == "complete", submitted.error_message
    assert len([row for row in transport_calls if row["method"] == "POST"]) >= len(SHOT_IDS)


@pytest.mark.asyncio
async def test_a1_live_rejected_drift_refused_at_adapter(
    phase6, monkeypatch: pytest.MonkeyPatch
):
    """A1: a rejected row flipped to approved after prepare makes the live
    set differ from the record; the adapter refuses fail-closed."""
    from app.adapters import RunwayRouterAdapter
    from app.services import render as render_module

    fixture = phase6
    storage = _fixture_setup(fixture, with_confirmations=True, with_rejected=True)
    transport_calls: list[dict] = []
    _harness(monkeypatch, storage, transport_calls)

    render_svc = render_module.RenderService()
    pipeline = _pipeline(fixture, render_svc)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="runway_router",
        mint_generic_authorization=True,
    )
    assert batch["ready"] is True, batch["blockers"]
    _provision_owner_authority(storage, batch["manifest"])

    entry = next(row for row in batch["entries"] if row["shot_id"] == SHOT_IDS[0])
    job = _a1_create(render_svc, batch, entry)

    # Drift after prepare: the rejected row is approved live.
    assert storage.save_reference_asset({
        "ref_id": REJECTED_ENV_REF_ID,
        "project_id": PROJECT_ID,
        "kind": "environment",
        "image_url": "https://fixture.invalid/glassworks-alt.png",
        "target_type": "setting",
        "target_id": "set-glassworks-fixture",
        "category": "environment",
        "approval_state": "approved",
        "canonical": False,
        "source_kind": "confirmed",
    })
    refused = await RunwayRouterAdapter(_a1_router_config())._submit_job_after_authorization(
        job, authority_storage=storage, reference_storage=storage
    )
    assert refused.status == "failed"
    reason = str(((refused.metadata or {}).get("router_execution") or {}).get("reason") or "")
    assert reason == "unlisted_environment_authority", reason
    assert transport_calls == []
