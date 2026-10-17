"""R4.4 step 2c — production-path Router dispatch probe (evidence instrument).

Question answered: can a representative multi-shot batch, built by the REAL
production pipeline (Scene Direction -> prepare_scene_batch ->
preflight_batch_authorization -> generate_scene -> RenderService.create_job ->
RunwayRouterAdapter), reach the Runway Model Router submission boundary?

The fixture reuses the Checkpoint G synthetic project (two approved character
face references + one canonical setting reference per shot). No network: the
r43k socket-block plugin is loaded by the run command and the Router transport
is replaced by a recording double.

The test prints a single machine-readable line, `R44_STEP2C_FINDINGS <json>`,
carrying every recorded observation. It asserts only preconditions; observed
outcomes are reported, not asserted, so this probe neither pins nor weakens a
production gate.
"""
from __future__ import annotations

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
    phase6,
    _prepare_approved_successor,
)

PROBE_ROUTER_CONFIG_ID = "r44-step2c-router"
PROBE_OWNER = "r44-step2c-owner"


def _transport_capture(calls: list[dict]):
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
                "id": "r44-step2c-task",
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": PROBE_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        return {
            "id": "r44-step2c-task",
            "status": "SUCCEEDED",
            "output": ["https://cdn.test/r44-step2c.mp4"],
        }

    return _capture


@pytest.mark.asyncio
async def test_r44_step2c_production_path_probe(phase6, monkeypatch: pytest.MonkeyPatch):
    from app.access_context import access_user_id
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.services import generation_cost_gate, render as render_module
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.providers import runway_router_provider
    from app.services.providers.runway_router_provider import (
        reconstruct_runway_router_video_request,
    )
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )
    from app.services.stability import ValidationError

    fixture = phase6
    storage = fixture["storage"]
    _prepare_approved_successor(fixture)

    findings: dict = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "shot_ids": list(SHOT_IDS),
    }

    # ── Test doubles (no network; socket connect is blocked by r43k plugin) ──
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

    from app.models import RenderJobOutput  # noqa: F401  (kept for symmetry with the fixture)

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
        backend_root=fixture["backend_root"],
    )

    # Owner authority required by create_job's router branch.
    storage.access_save_user(
        {"username": PROBE_OWNER, "user_id": PROBE_OWNER}, create=True
    )
    storage.access_claim_project(PROJECT_ID, PROBE_OWNER)

    # ── 1. Baseline: the batch itself is valid for the simulated provider ────
    simulated_batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=fixture["project"], provider="simulated"
    )
    findings["simulated_prepare_ready"] = bool(simulated_batch.get("ready"))
    findings["simulated_shot_ids"] = [row["shot_id"] for row in simulated_batch.get("shots", [])]

    # ── 2. The same batch prepared for the Router provider ───────────────────
    router_batch = None
    try:
        router_batch = pipeline.prepare_scene_batch(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="runway_router",
        )
        findings["router_prepare"] = {"ready": bool(router_batch.get("ready"))}
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed silently
        findings["router_prepare_error"] = {
            "type": type(exc).__name__,
            "message": str(getattr(exc, "message", exc))[:400],
            "stage": str(getattr(exc, "stage", "")),
        }

    prepared = router_batch if router_batch is not None else simulated_batch
    findings["prepared_provider_used"] = "runway_router" if router_batch is not None else "simulated"

    # ── 3. Batch authorization preflight (the route-level preflight surface) ─
    authorization = pipeline.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=prepared["entries"],
        shot_manifest=prepared["manifest"],
        expected_digests=None,
    )
    findings["preflight_ready"] = bool(authorization.get("ready"))
    findings["preflight_failures"] = [
        {
            "shot_id": row.get("shot_id"),
            "failure_code": row.get("failure_code"),
            "failure_category": row.get("failure_category"),
            "policy_version": row.get("policy_version"),
        }
        for row in authorization.get("shots", [])
        if not row.get("ok")
    ]

    # ── 4. Router reconstruction on pipeline-built frozen contracts ──────────
    reconstruction: dict = {}
    manifest_rows = {
        row["shot_id"]: row for row in prepared["manifest"].get("shots", []) if isinstance(row, dict)
    }
    ROUTER_ROLES = {"reference", "storyboard", "storyboard_last"}
    for entry in prepared["entries"]:
        shot_id = entry["shot_id"]
        record: dict = {}
        try:
            frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        except Exception as exc:  # noqa: BLE001
            reconstruction[shot_id] = {"contract_parse_error": f"{type(exc).__name__}: {exc}"}
            continue
        manifest_row = manifest_rows.get(shot_id) or {}
        record["manifest_binding_keys"] = [
            sorted(row.keys()) for row in (manifest_row.get("reference_binding") or [])
        ]
        record["contract_studio_roles"] = [ref.studio_role for ref in frozen.references]
        record["contract_ref_ids"] = [ref.ref_id for ref in frozen.references]
        record["role_allowlist_would_accept"] = all(
            ref.studio_role in ROUTER_ROLES for ref in frozen.references
        )

        # Mirror the reconstruction's expected_binding projection (no project_id)
        # against the manifest row the pipeline persisted, and isolate the delta.
        payload = frozen.payload()
        expected_binding = [
            {
                "ref_id": ref.get("ref_id"), "uri": ref.get("uri"),
                "target_type": ref.get("target_type"), "target_id": ref.get("target_id"),
                "role": ref.get("studio_role"), "category": ref.get("category"),
                "canonical": ref.get("canonical"), "approval_state": ref.get("approval_state"),
                "source_kind": ref.get("source_kind"),
                **({"kind": ref["kind"]} if ref.get("kind") else {}),
            }
            for ref in payload["references"]
        ]
        actual_binding = manifest_row.get("reference_binding") or []
        record["binding_delta"] = [
            {
                "index": index,
                "only_in_manifest": sorted(
                    set(actual_binding[index].keys()) - set(expected_binding[index].keys())
                ) if index < len(actual_binding) and index < len(expected_binding) else "count_mismatch",
                "only_in_contract_projection": sorted(
                    set(expected_binding[index].keys()) - set(actual_binding[index].keys())
                ) if index < len(actual_binding) and index < len(expected_binding) else "count_mismatch",
            }
            for index in range(max(len(actual_binding), len(expected_binding)))
        ]

        try:
            wire = reconstruct_runway_router_video_request(
                entry["generation_contract"],
                prepared["manifest"],
                config_id=PROBE_ROUTER_CONFIG_ID,
            )
            record["reconstruction"] = {
                "result": "passed",
                "reference_images": (wire.get("input") or {}).get("referenceImages"),
            }
        except Exception as exc:  # noqa: BLE001 — the exact gate outcome is the evidence
            record["reconstruction"] = {
                "result": "raised",
                "error": f"{type(exc).__name__}: {exc}"[:400],
            }
        reconstruction[shot_id] = record
    findings["reconstruction"] = reconstruction

    # ── 5. Production dispatch entry: generate_scene(provider="runway_router")
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
                "message": str(getattr(exc, "message", exc))[:400],
                "stage": str(getattr(exc, "stage", "")),
                "failure_type": str((getattr(exc, "metadata", None) or {}).get("failure_type") or ""),
            }
        except Exception as exc:  # noqa: BLE001
            findings["generate_scene"] = {
                "raised": type(exc).__name__,
                "message": str(exc)[:400],
            }
    finally:
        access_user_id.reset(token)

    jobs = storage.list_jobs(PROJECT_ID)
    findings["persisted_jobs"] = [
        {
            "job_id": job.id,
            "shot_id": job.shot_id,
            "provider": job.provider,
            "status": job.status,
            "error": str(getattr(job, "error_message", "") or "")[:200],
        }
        for job in jobs
    ]
    findings["job_count"] = len(jobs)
    findings["jobs_with_frozen_contract"] = [
        job.shot_id for job in jobs
        if isinstance(getattr(job, "metadata", None), dict)
        and "creative_generation_contract" in (job.metadata or {})
    ]
    findings["adapter_attempts"] = adapter_attempts
    findings["adapter_attempt_count"] = len(adapter_attempts)
    findings["transport_calls"] = [
        {"method": row["method"], "dry_run": bool((row["payload"] or {}).get("dryRun"))}
        for row in transport_calls
    ]

    # ── 6. Diagnostic: the next gate a pipeline-built Router job meets ───────
    # If preflight had passed, create_job is exactly what generate_scene would
    # call. Driving it directly records where a pipeline-built Router job stops.
    if router_batch is not None:
        entry = router_batch["entries"][0]

        # 6a. Mirror create_job's own frozen-proof comparisons so the exact
        # rejecting sub-condition is identified rather than inferred.
        frozen_for_create = FrozenGenerationContract.from_record(entry["generation_contract"])
        approved_payload = frozen_for_create.payload()
        canonical_refs = [
            row for row in approved_payload["references"]
            if isinstance(row, dict) and row.get("source") == "canonical_reference_binding"
        ]
        create_job_expected_binding = [
            {
                "ref_id": row["ref_id"], "uri": row["uri"],
                "target_type": row["target_type"], "target_id": row["target_id"],
                "role": row["studio_role"], "category": row["category"],
                "canonical": row["canonical"], "approval_state": row["approval_state"],
                "source_kind": row["source_kind"],
                **({"kind": row["kind"]} if row.get("kind") else {}),
            }
            for row in canonical_refs
        ]
        row_projection = [
            {
                "ref_id": row.get("ref_id"), "uri": row.get("uri"),
                "target_type": row.get("target_type"), "target_id": row.get("target_id"),
                "role": row.get("role"), "category": row.get("category"),
                "canonical": row.get("canonical"), "approval_state": row.get("approval_state"),
                "source_kind": row.get("source_kind"),
                **({"kind": row["kind"]} if row.get("kind") else {}),
            }
            for row in (entry.get("reference_binding") or [])
        ]
        create_manifest_row = next(
            (row for row in router_batch["manifest"].get("shots", [])
             if isinstance(row, dict) and row.get("shot_id") == entry["shot_id"]),
            {},
        )
        findings["create_job_gate_diagnostic"] = {
            "manifest_row_equals_contract_projection":
                create_manifest_row.get("reference_binding") == create_job_expected_binding,
            "row_projection_equals_contract_projection": row_projection == create_job_expected_binding,
            "row_projection_delta": [
                {
                    "index": index,
                    "only_in_binding_rows": sorted(
                        set(row_projection[index].keys()) - set(create_job_expected_binding[index].keys())
                    ) if index < len(row_projection) and index < len(create_job_expected_binding)
                    else "count_mismatch",
                }
                for index in range(max(len(row_projection), len(create_job_expected_binding)))
            ],
            "binding_rows_carry_project_id": [
                bool((row or {}).get("project_id")) for row in (entry.get("reference_binding") or [])
            ],
        }

        token = access_user_id.set(PROBE_OWNER)
        try:
            try:
                job = render_svc.create_job(
                    project_id=PROJECT_ID,
                    shot_id=entry["shot_id"],
                    provider="runway_router",
                    prompt=entry["prompt"],
                    reference_assets=list(entry["references"]),
                    parameters=copy.deepcopy(entry["generation_settings"]),
                    generation_contract=entry["generation_contract"],
                    prepared_generation_contract=entry["generation_contract"],
                    frozen_reference_binding=copy.deepcopy(entry.get("reference_binding") or []),
                    generation_context_id=str(entry.get("generation_context_id", "")),
                    creative_manifest_fingerprint=router_batch["manifest"]["manifest_fingerprint"],
                    creative_manifest=router_batch["manifest"],
                    dialogue_handoff=copy.deepcopy(entry["dialogue_handoff"]),
                )
                meta = job.metadata or {}
                findings["direct_create_job"] = {
                    "job_id": job.id,
                    "frozen_contract_persisted": "creative_generation_contract" in meta,
                    "frozen_reference_binding_persisted": "frozen_reference_binding" in meta,
                    "reference_projection_authorization_present":
                        "reference_projection_authorization" in meta,
                }
                submitted = await _RecordingRouterAdapter(router_config)._submit_job_after_authorization(
                    job, authority_storage=storage, reference_storage=storage
                )
                findings["direct_submit"] = {
                    "status": submitted.status,
                    "error": str(getattr(submitted, "error_message", "") or "")[:300],
                    "reason": str(
                        ((submitted.metadata or {}).get("router_execution") or {}).get("reason") or ""
                    ),
                    "provider_failure": str((submitted.metadata or {}).get("provider_failure") or "")[:300],
                }
            except Exception as exc:  # noqa: BLE001
                findings["direct_probe_error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        finally:
            access_user_id.reset(token)

    print("\nR44_STEP2C_FINDINGS " + json.dumps(findings, sort_keys=True, default=str))

    # Preconditions only — the probe must actually exercise the production path.
    assert findings["simulated_prepare_ready"] is True
    assert findings["simulated_shot_ids"] == list(SHOT_IDS)
    assert len(prepared["entries"]) == 2
    # R4.5 session A expectations (owner-recorded Oct 16, 2026): the
    # pipeline-built batch now passes the unified role, comparison and scope
    # gates and stops fail-closed afterwards. F5 (generic
    # projection-authorization builder) is deliberately not implemented, so no
    # pipeline job may reach the wire in this session.
    assert findings["preflight_ready"] is True
    assert findings["preflight_failures"] == []
    assert findings["create_job_gate_diagnostic"]["row_projection_equals_contract_projection"] is True
    assert findings["create_job_gate_diagnostic"]["binding_rows_carry_project_id"] == [False, True]
    for shot_id in SHOT_IDS:
        record = findings["reconstruction"][shot_id]
        # R4.5-B1 (F8, authorized): Router jobs freeze with empty creative
        # parameters, so the reconstruction passes its creative-parameters
        # gate and composes the wire referenceImages from the frozen proof.
        # The :783 comparison passes (only the scoped project_id key differs,
        # which the shared helper excludes). This probe runs without the F5
        # mint, so the batch still stops fail-closed at the declaration gate
        # below with zero jobs and zero transport calls.
        assert record["reconstruction"]["result"] == "passed"
        assert record["reconstruction"]["reference_images"] == [
            {"uri": uri, "role": "reference"}
            for uri in (
                ["https://fixture.invalid/char-ivo.png", "https://fixture.invalid/glassworks.png"]
                if shot_id == SHOT_IDS[0]
                else ["https://fixture.invalid/char-neri.png", "https://fixture.invalid/glassworks.png"]
            )
        ]
    # Creation's comparison and scope gates pass; the direct drive stops at
    # the pre-existing owner-authority gate (out of scope for this session).
    assert "storyboard_owner_approval_missing" in findings.get("direct_probe_error", "")
    assert findings["transport_calls"] == []
    assert findings["adapter_attempt_count"] == 0
    assert findings["job_count"] == 0
    assert all(entry.get("generation_contract") for entry in prepared["entries"])
