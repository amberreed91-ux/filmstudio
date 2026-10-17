"""R4.5 session A2 — downstream gate survey probe (TEST-ONLY; evidence instrument).

Question answered: after R4.5 session A unified the role / comparison / scope
gates, which gates remain between a pipeline-built generic Runway-Router batch
and a *mocked* adapter dispatch — and what would production have to produce to
satisfy each one?

Design (mirrors tests/test_r44_step2c_production_path_probe.py):

* the REAL production path — approved Scene Direction successor ->
  ``prepare_scene_batch`` -> ``preflight_batch_authorization`` ->
  ``generate_scene(provider="runway_router")`` -> ``RenderService.create_job`` ->
  the real ``RunwayRouterAdapter`` with a recording transport double;
* test-only storage (the phase6 tmp fixture), synthetic data, sockets blocked by
  the r43k plugin, and a provider tripwire (the transport double records calls);
* at each refusal the probe records the gate and then satisfies it INSIDE THE
  TEST — by constructing the expected value, never by editing production code or
  relaxing a check. After R4.5 session B1 the F7 (store more), F9 (seed before
  freeze) and F8 (freeze {} + selection evidence) gates are satisfied IN
  PRODUCTION, so the ONLY stand-in the probe needs is:
    - ``reference_projection_declaration_missing`` -> a clearly labelled
      TEST-ONLY stand-in authorization record built from the job's own persisted
      frozen binding. It is a test double of DATA, never of a gate, is never
      persisted outside the temporary test storage, and is NOT a proposal for
      the production authority model (R4.5 owner decision 3).

The probe prints one machine-readable line, ``R45A2_GATE_FINDINGS <json>``, and
asserts only the outcomes this session is authorized to record.

No production code, schema, stored contract, or Scene 002 path is touched. No
network is reached. No real authority is minted outside the temporary test
storage.
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock

import pytest

from test_multishot_integrity_phase6_e2e import (  # real production pipeline fixture
    PROJECT_ID,
    SCENE_ID,
    SHOT_IDS,
    FakeAudioService,
    FakeStitchingService,
    _prepare_approved_successor,
    phase6,
)

PROBE_ROUTER_CONFIG_ID = "r45a2-router"
PROBE_OWNER = "r45a2-owner"
GATE_CAP = 8


def _transport_capture(calls: list[dict]):
    """Recording Router transport double: dry-run, submit, then a poll."""

    def _capture(url, *, method="GET", payload=None, api_key=None):
        calls.append({"url": url, "method": method, "payload": copy.deepcopy(payload)})
        if method == "POST" and payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": PROBE_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        if method == "POST":
            return {
                "dryRun": False,
                "id": "r45a2-task",
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": PROBE_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        return {
            "id": "r45a2-task",
            "status": "SUCCEEDED",
            "output": ["https://cdn.test/r45a2.mp4"],
        }

    return _capture


def _reason(job) -> str:
    return str(((job.metadata or {}).get("router_execution") or {}).get("reason") or "")


def _failures(job) -> str:
    return str(((job.metadata or {}).get("provider_failure") or {}).get("reason") or "")


@pytest.mark.asyncio
async def test_r45a2_downstream_gate_survey(phase6, monkeypatch: pytest.MonkeyPatch):
    from app.access_context import access_user_id
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.models.storyboard_blueprint import StoryboardBlueprintStatus
    from app.services import generation_cost_gate, render as render_module
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.providers import runway_router_provider
    from app.services.reference_validation import reference_binding_digest
    from app.services.runway_reference_projection import (
        AUTHORIZATION_METADATA_KEY,
        AUTHORIZATION_POLICY_ID,
        canonical_bindings_from_contract,
        compute_source_fingerprints,
    )
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )
    from app.services.stability import ValidationError

    fixture = phase6
    storage = fixture["storage"]
    backend_root = fixture["backend_root"]
    _prepare_approved_successor(fixture)

    findings: dict = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "shot_ids": list(SHOT_IDS),
        "gate_cap": GATE_CAP,
    }

    # ── Test doubles (no network; sockets blocked by the r43k plugin) ────────
    transport_calls: list[dict] = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("RUNWAY_ROUTER_CONFIG_ID", PROBE_ROUTER_CONFIG_ID)
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

    adapter_attempts: list[dict] = []

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

    class _RecordingRouterAdapter(RunwayRouterAdapter):
        """Records that submission reached the adapter boundary, then runs the
        REAL adapter code up to the (mocked) provider transport."""

        async def submit_job(self, job, *, reference_storage=None):
            adapter_attempts.append(
                {"job_id": job.id, "shot_id": job.shot_id, "provider": job.provider}
            )
            return await super().submit_job(job, reference_storage=reference_storage)

    def _fake_get_adapter(provider, config=None):
        if provider == "runway_router":
            return _RecordingRouterAdapter(router_config)
        raise AssertionError(f"probe only expects router jobs, got provider={provider!r}")

    monkeypatch.setattr(render_module, "get_adapter", _fake_get_adapter)

    render_svc = render_module.RenderService()
    pipeline = SceneProductionPipelineService(
        render_svc=render_svc,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        backend_root=backend_root,
    )

    # Owner authority required by create_job's router branch.
    storage.access_save_user({"username": PROBE_OWNER, "user_id": PROBE_OWNER}, create=True)
    storage.access_claim_project(PROJECT_ID, PROBE_OWNER)

    # ── 1. The batch, built by the real pipeline for the Router provider ─────
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=fixture["project"], provider="runway_router"
    )
    findings["prepare_ready"] = bool(batch.get("ready"))
    findings["entry_shot_ids"] = [row["shot_id"] for row in batch["entries"]]
    findings["contract_studio_roles"] = [
        [ref.get("studio_role") for ref in FrozenGenerationContract.from_record(
            entry["generation_contract"]
        ).payload()["references"]]
        for entry in batch["entries"]
    ]
    findings["contract_creative_parameters"] = [
        sorted(
            json.loads(FrozenGenerationContract.from_record(entry["generation_contract"]).creative_parameters_json)
        )
        for entry in batch["entries"]
    ]

    authorization = pipeline.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=batch["entries"],
        shot_manifest=batch["manifest"],
        expected_digests=None,
    )
    findings["preflight_ready"] = bool(authorization.get("ready"))
    findings["preflight_failures"] = [
        {"shot_id": row.get("shot_id"), "failure_code": row.get("failure_code")}
        for row in authorization.get("shots", [])
        if not row.get("ok")
    ]

    # ── 2. Gate 3 (production authority at creation): provision the approved
    # storyboard owner-approval shape the fixture lacks. Test scaffolding via
    # production storage APIs only; it mints no gate and no authority model.
    manifest = batch["manifest"]
    storyboard_version_id = str((manifest.get("storyboard") or {}).get("storyboard_version") or "")
    version = storage.get_storyboard_blueprint_version(storyboard_version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = version.approved_at or "2026-10-16T00:00:00+00:00"
    version.approved_by = PROBE_OWNER
    version.metadata = {
        **(version.metadata or {}),
        "production_approval": {"actor_id": PROBE_OWNER, "actor_authenticated": True},
    }
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.current_version_id = storyboard_version_id
    blueprint.approved_version_id = storyboard_version_id
    storage.save_storyboard_blueprint(blueprint)
    for row in manifest.get("shots", []):
        shot = storage.get_storyboard_shot(str(row.get("storyboard_shot_id") or ""))
        if shot is not None:
            shot.status = StoryboardBlueprintStatus.APPROVED
            storage.save_storyboard_shot(shot)
    findings["creation_authority_provisioned"] = {
        "storyboard_version_id": storyboard_version_id,
        "storyboard_shot_ids": [
            str(row.get("storyboard_shot_id") or "") for row in manifest.get("shots", [])
        ],
    }

    # Read-only diagnostic wrapper: records the exact sub-condition behind a
    # durable identity denial on the production leg (no behaviour change).
    import app.services.production_authorization_service as _authorization_module

    identity_diagnostics: list[dict] = []
    _original_authorize = _authorization_module.authorize_runway_submission

    def _diagnostic_authorize(job, *, storage, require_durable=True):
        decision = _original_authorize(job, storage=storage, require_durable=require_durable)
        if not decision.allowed and decision.reason == "durable_render_job_identity_mismatch":
            durable = storage.get_job(job.id)
            durable_meta = dict(getattr(durable, "metadata", None) or {}) if durable else {}
            job_meta = dict(job.metadata or {})
            durable_meta.pop("production_authorization", None)
            job_meta.pop("production_authorization", None)
            identity_diagnostics.append({
                "durable_is_none": durable is None,
                "only_in_job_metadata": sorted(set(job_meta) - set(durable_meta)),
                "only_in_durable_metadata": sorted(set(durable_meta) - set(job_meta)),
                "differing_metadata_keys": sorted(
                    key for key in set(durable_meta) & set(job_meta)
                    if durable_meta[key] != job_meta[key]
                ),
                "input_payload_equal": bool(durable) and durable.input_payload.model_dump(mode="json")
                == job.input_payload.model_dump(mode="json"),
                "differing_input_keys": sorted(
                    key for key in set(durable.input_payload.model_dump(mode="json"))
                    | set(job.input_payload.model_dump(mode="json"))
                    if durable.input_payload.model_dump(mode="json").get(key)
                    != job.input_payload.model_dump(mode="json").get(key)
                ) if durable else [],
                "durable_seed": (durable.input_payload.parameters or {}).get("seed") if durable else None,
                "job_seed": (job.input_payload.parameters or {}).get("seed"),
                "actor_in_job": job_meta.get("production_request_actor_id"),
                "actor_in_durable": durable_meta.get("production_request_actor_id"),
            })
        return decision

    monkeypatch.setattr(_authorization_module, "authorize_runway_submission", _diagnostic_authorize)

    # ── 3. Unmodified production entry: generate_scene(provider=runway_router)
    token = access_user_id.set(PROBE_OWNER)
    try:
        try:
            result = await pipeline.generate_scene(
                project_id=PROJECT_ID,
                scene_id=SCENE_ID,
                project=fixture["project"],
                provider="runway_router",
            )
            findings["generate_scene"] = {
                "status": result.get("status"),
                "shots": [
                    {"shot_id": row.get("shot_id"), "status": row.get("status")}
                    for row in (result.get("shots") or [])
                ],
            }
        except ValidationError as exc:
            findings["generate_scene"] = {
                "raised": "ValidationError",
                "message": str(getattr(exc, "message", exc))[:300],
                "stage": str(getattr(exc, "stage", "")),
            }
        except Exception as exc:  # noqa: BLE001 — recorded, never swallowed silently
            findings["generate_scene"] = {
                "raised": type(exc).__name__,
                "message": str(exc)[:300],
            }
    finally:
        access_user_id.reset(token)

    jobs_after_production_entry = storage.list_jobs(PROJECT_ID)
    findings["jobs_after_production_entry"] = [
        {"job_id": job.id, "shot_id": job.shot_id, "status": job.status,
         "reason": _reason(job), "error": str(job.error_message or "")[:200],
         "has_selection_evidence": bool(
             ((job.metadata or {}).get("router_selection_evidence") or {}).get("contract_digest")
         )}
        for job in jobs_after_production_entry
    ]
    findings["transport_calls_after_production_entry"] = [
        {"method": row["method"], "dry_run": bool((row["payload"] or {}).get("dryRun"))}
        for row in transport_calls
    ]
    production_entry_identity_diff = []
    for durable_job in jobs_after_production_entry:
        in_memory = render_svc._jobs.get(durable_job.id)
        if in_memory is None:
            production_entry_identity_diff.append({"job_id": durable_job.id, "in_memory": False})
            continue
        durable_meta = dict(durable_job.metadata or {})
        memory_meta = dict(in_memory.metadata or {})
        production_entry_identity_diff.append({
            "job_id": durable_job.id,
            "only_in_memory_metadata": sorted(set(memory_meta) - set(durable_meta)),
            "only_in_durable_metadata": sorted(set(durable_meta) - set(memory_meta)),
            "differing_metadata_keys": sorted(
                key for key in set(durable_meta) & set(memory_meta)
                if durable_meta[key] != memory_meta[key]
            ),
            "input_payload_equal": durable_job.input_payload.model_dump(mode="json")
            == in_memory.input_payload.model_dump(mode="json"),
        })
    findings["production_entry_identity_diff"] = production_entry_identity_diff
    findings["production_entry_identity_diagnostics"] = identity_diagnostics

    # ── 3b. Production submit entry point (render.submit_job): the seed is
    # decided before the freeze (B1 F9), so a freshly created job is driven
    # through the real submit entry exactly once with no in-test seed.
    production_submit_probe: dict = {}
    token = access_user_id.set(PROBE_OWNER)
    try:
        seed_job = render_svc.create_job(
            project_id=PROJECT_ID,
            shot_id=batch["entries"][0]["shot_id"],
            provider="runway_router",
            prompt=batch["entries"][0]["prompt"],
            reference_assets=list(batch["entries"][0]["references"]),
            parameters=copy.deepcopy(batch["entries"][0]["generation_settings"]),
            generation_contract=batch["entries"][0]["generation_contract"],
            prepared_generation_contract=batch["entries"][0]["generation_contract"],
            frozen_reference_binding=copy.deepcopy(batch["entries"][0]["reference_binding"]),
            creative_manifest_fingerprint=batch["manifest"]["manifest_fingerprint"],
            creative_manifest=batch["manifest"],
            dialogue_handoff=copy.deepcopy(batch["entries"][0]["dialogue_handoff"]),
            # Production data generate_scene forwards; the direct create here
            # carries it the same way (not a gate stand-in).
            metadata={"router_selection_evidence": copy.deepcopy(
                batch["entries"][0]["router_selection_evidence"]
            )},
        )
    finally:
        access_user_id.reset(token)
    durable_seed_job = storage.get_job(seed_job.id)
    production_submit_probe["seed_before"] = (durable_seed_job.input_payload.parameters or {}).get("seed")
    try:
        submitted = await render_svc.submit_job(seed_job.id)
        production_submit_probe["raised"] = ""
    except Exception as exc:  # noqa: BLE001
        submitted = storage.get_job(seed_job.id)
        production_submit_probe["raised"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    production_submit_probe["status"] = getattr(submitted, "status", "")
    production_submit_probe["reason"] = _reason(submitted) if submitted is not None else ""
    production_submit_probe["error"] = str(getattr(submitted, "error_message", "") or "")[:240]
    production_submit_probe["transport_calls"] = len(transport_calls)
    findings["production_submit_entry_probe"] = production_submit_probe

    # ── 4. Ordered gate walk: create_job + real adapter, remedies in-test ───
    # B1: the F7/F9/F8 gates are satisfied in production; no in-test input
    # alignment or seed satisfaction remains. Only the TEST-ONLY authorization
    # stand-in below is still needed (F5, decided separately).
    def _declare_test_only_authorization(job, storage) -> None:
        """Gate remedy (F5 stand-in): a TEST-ONLY authorization record containing
        exactly the fields the adapter reads, built from the job's own persisted
        frozen binding. DATA double only; not a production authority model.

        Decision A1: the stand-in rejected identity is additionally persisted
        as a genuine rejected-state row, so the adapter's exact-equality
        check verifies against real fixture data."""
        record = job.metadata["creative_generation_contract"]
        binding = job.metadata.get("frozen_reference_binding")
        rows = canonical_bindings_from_contract(record)
        setting = next(row for row in rows if row.get("target_type") == "setting")
        frozen_manifest = job.metadata["creative_generation_manifest"]
        version_id = str((frozen_manifest.get("storyboard") or {}).get("storyboard_version") or "")
        fingerprints = compute_source_fingerprints(rows, backend_root=backend_root)
        job.metadata[AUTHORIZATION_METADATA_KEY] = {
            "authorization_policy_id": AUTHORIZATION_POLICY_ID,
            "authorized_environment_ref_id": str(setting.get("ref_id") or ""),
            "rejected_environment_ref_ids": ["ref-r45a2-test-only-rejected-stand-in"],
            "frozen_reference_binding": copy.deepcopy(binding),
            "frozen_reference_binding_sha256": reference_binding_digest(binding),
            "project_id": PROJECT_ID,
            "scene_id": str((frozen_manifest.get("scene") or {}).get("scene_id") or SCENE_ID),
            "setting_id": str(setting.get("target_id") or ""),
            "current_version_id": version_id,
            "approved_version_id": version_id,
            "storyboard_version_id": version_id,
            "source_fingerprint": fingerprints[str(setting.get("ref_id") or "")],
        }
        storage.save_reference_asset({
            "ref_id": "ref-r45a2-test-only-rejected-stand-in",
            "project_id": PROJECT_ID,
            "kind": "environment",
            "image_url": "https://fixture.invalid/r45a2-rejected-stand-in.png",
            "target_type": "setting",
            "target_id": str(setting.get("target_id") or ""),
            "category": "environment",
            "approval_state": "rejected",
            "canonical": False,
            "source_kind": "confirmed",
        })

    ordered_gates: list[dict] = []
    per_shot: dict = {}

    for entry in batch["entries"]:
        shot_id = str(entry["shot_id"])
        record: dict = {"shot_id": shot_id}
        token = access_user_id.set(PROBE_OWNER)
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
                # Production data generate_scene forwards; the direct create
                # here carries it the same way (not a gate stand-in).
                metadata={"router_selection_evidence": copy.deepcopy(
                    entry["router_selection_evidence"]
                )},
            )
        except Exception as exc:  # noqa: BLE001
            record["creation_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            per_shot[shot_id] = record
            continue
        finally:
            access_user_id.reset(token)

        record["created_job_id"] = job.id
        record["input_parameter_keys"] = sorted((job.input_payload.parameters or {}).keys())
        record["mutable_keys_absent_at_creation"] = sorted(
            key for key in ("scene_coverage", "scene_coverage_shot", "dialogue_handoff")
            if key not in (job.input_payload.parameters or {})
        )
        # B1: the seed is decided before the freeze and the selection evidence
        # is digest-linked at creation; both ride the real production path.
        record["seed_at_creation"] = (job.input_payload.parameters or {}).get("seed")
        record["selection_evidence"] = copy.deepcopy((job.metadata or {}).get("router_selection_evidence"))

        adapter = _RecordingRouterAdapter(router_config)
        refusals: list[dict] = []
        final = None
        while True:
            durable = storage.get_job(job.id) or job
            final = await adapter._submit_job_after_authorization(
                durable, authority_storage=storage, reference_storage=storage
            )
            if final.status == "complete":
                break
            reason = _reason(final) or _failures(final)
            refusals.append({
                "order": len(ordered_gates) + len(refusals) + 1,
                "reason": reason,
                "status": final.status,
                "error_message": str(final.error_message or "")[:240],
            })
            if reason == "reference_projection_declaration_missing":
                _declare_test_only_authorization(final, storage)
            else:
                break
            storage.save_job(final)
            if len(refusals) >= GATE_CAP:
                refusals.append({"order": len(ordered_gates) + len(refusals) + 1,
                                 "reason": "GATE_CAP_REACHED", "status": final.status,
                                 "error_message": ""})
                break

        record["refusals"] = refusals
        record["final_status"] = final.status if final is not None else ""
        record["final_reason"] = _reason(final) if final is not None else ""
        record["final_error"] = str(getattr(final, "error_message", "") or "")[:240]
        per_shot[shot_id] = record
        ordered_gates.extend(refusals)

    findings["ordered_gates"] = ordered_gates
    findings["per_shot"] = per_shot
    # B1: the production entry (generate_scene -> submit -> adapter) now stops
    # at the declaration gate — the seed lock takes no post-authorization
    # mutation, so the durable-identity denial is gone. The remaining refusal
    # is the F5 authorization record, still without a production minter.
    findings["ordered_gates_with_production_entry"] = (
        [{"order": 1, "reason": _reason(jobs_after_production_entry[0]),
          "error": str(jobs_after_production_entry[0].error_message or "")[:240],
          "where": "render.submit_job -> adapter declaration gate (production entry)"}]
        if jobs_after_production_entry else []
    ) + ordered_gates
    findings["adapter_attempt_count"] = len(adapter_attempts)
    findings["transport_calls"] = [
        {"method": row["method"], "dry_run": bool((row["payload"] or {}).get("dryRun"))}
        for row in transport_calls
    ]
    jobs = storage.list_jobs(PROJECT_ID)
    findings["final_job_count"] = len(jobs)
    findings["final_job_states"] = [
        {"job_id": job.id, "shot_id": job.shot_id, "status": job.status, "reason": _reason(job)}
        for job in jobs
    ]

    print("\nR45A2_GATE_FINDINGS " + json.dumps(findings, sort_keys=True, default=str))

    # ── Preconditions / recorded outcomes ───────────────────────────────────
    assert findings["prepare_ready"] is True
    assert findings["entry_shot_ids"] == list(SHOT_IDS)
    assert findings["preflight_ready"] is True
    assert findings["preflight_failures"] == []
    # B1: every freshly created job already matches its frozen inputs, carries
    # a decided seed and digest-linked selection evidence, so the walk meets
    # only the declaration gate and then dispatches once the test supplies
    # the TEST-ONLY stand-in record.
    for shot_id in SHOT_IDS:
        record = per_shot[shot_id]
        assert "creation_error" not in record, record
        assert record["mutable_keys_absent_at_creation"] == [], record
        assert record["seed_at_creation"] is not None, record
        evidence = record["selection_evidence"]
        assert isinstance(evidence, dict) and isinstance(evidence.get("selection"), dict), record
        assert evidence.get("contract_digest"), record
        reasons = [row["reason"] for row in record["refusals"]]
        assert reasons == ["reference_projection_declaration_missing"], reasons
        assert record["final_status"] in {"complete", "pending", "queued", "rendering"}, record
    assert findings["transport_calls"], "the mocked adapter must have received a dispatch"
    assert all(
        row["method"] in {"GET", "POST"} for row in findings["transport_calls"]
    )
    # The production entry reaches the adapter with its durable snapshot
    # intact (no post-authorization mutation) and stops at the declaration
    # gate — the remaining refusal, still without a production minter.
    production_entry = findings["jobs_after_production_entry"]
    assert len(production_entry) == 1 and production_entry[0]["status"] == "failed"
    assert production_entry[0]["reason"] == "reference_projection_declaration_missing"
    assert "declared, authorized projection" in production_entry[0]["error"]
    # The generate_scene production path forwards the digest-linked selection
    # evidence into the created job's metadata.
    assert production_entry[0]["has_selection_evidence"] is True, production_entry
    assert findings["production_entry_identity_diagnostics"] == []
    for diff in findings["production_entry_identity_diff"]:
        assert diff.get("input_payload_equal") is True, diff
    assert findings["transport_calls_after_production_entry"] == []
    # The production submit entry advances to the same declaration gate with
    # no in-test seed: the seed was decided before the freeze.
    submit_probe = findings["production_submit_entry_probe"]
    assert submit_probe["seed_before"] is not None, submit_probe
    assert submit_probe["reason"] == "reference_projection_declaration_missing", submit_probe
