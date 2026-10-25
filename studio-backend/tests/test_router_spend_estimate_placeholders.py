"""Placeholder-URI spend estimates for local-path references (stubbed transport).

Frozen entries whose references are local paths Runway cannot fetch are
priced with deterministic ``runway://dry-run-placeholder/`` stand-ins
substituted into deep copies — same count, order, and roles, no bytes
read, no upload, frozen artifacts untouched. Such pictures carry
``materialization_required=True`` (price advisory on URI identity).

Transport rule for this file: every provider call is a stubbed function —
no network, no jobs, no spend, no live DB. Hermetic temp dirs only.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from app.services.generation_cost_gate import GenerationCostGate
from app.services.stability import ValidationError
from test_r45_shared_router_gates import _r45_build
from test_router_spend_gate_phase6 import _stub_estimator
from test_scene_pipeline_shot_filter import _generate, _harness, _project5

PLACEHOLDER_PREFIX = "runway://dry-run-placeholder/"


def _stub_submit(monkeypatch: pytest.MonkeyPatch, calls: list, result=None, exc=None):
    from app.services.providers import runway_router_provider

    def _fake(prompt: str, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        if exc is not None:
            raise exc
        return copy.deepcopy(result)

    monkeypatch.setattr(
        runway_router_provider, "submit_runway_router_video_render", _fake
    )


def _dry_run_result(*, credits=150, model="seedance2_5"):
    return {
        "status": "dry_run",
        "url": None,
        "meta": {"estimated_cost_credits": credits, "resolved_model": model},
    }


def _local_ref_artifact(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Build the R45 triple with local-path reference URIs from the start.

    Patching the raw binding keeps coverage, freeze, and manifest mutually
    consistent (URIs flow through every layer together).
    """
    import test_r45_shared_router_gates as r45
    from app.services.generation_contract import FrozenGenerationContract

    real_binding = r45._r45_raw_binding

    def _local_binding(*, roles=("face", "environment"), project_id=r45.R45_PROJECT):
        rows = real_binding(roles=roles, project_id=project_id)
        for index, row in enumerate(rows):
            row["uri"] = f"/outputs/test-local/ref-{index}.png"
        return rows

    monkeypatch.setattr(r45, "_r45_raw_binding", _local_binding)
    artifact = _r45_build()
    frozen = FrozenGenerationContract.from_record(artifact["contract_record"])
    return {
        "contract_record": artifact["contract_record"],
        "manifest": artifact["manifest"],
        "original_uris": [ref.uri for ref in frozen.references],
        "original_roles": [ref.role for ref in frozen.references],
        "shot_id": frozen.shot_id,
    }


# ── Case 1: local-ref shot estimates with placeholders ────────────────────

def test_local_ref_shot_estimates_with_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _local_ref_artifact(monkeypatch)
    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits=150))

    gate = GenerationCostGate()
    before_record = copy.deepcopy(artifact["contract_record"])
    before_manifest = copy.deepcopy(artifact["manifest"])
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record=artifact["contract_record"],
        manifest=artifact["manifest"],
    )

    assert picture["estimated"] is True
    assert picture["estimated_credits"] == 150
    assert picture["materialization_required"] is True
    assert picture["uri_placeholders_used"] is True
    assert picture["failure_class"] is None
    assert picture["advisory"] is True
    # Frozen artifacts byte-identical: substitution ran on copies only.
    assert artifact["contract_record"] == before_record
    assert artifact["manifest"] == before_manifest

    assert len(calls) == 1
    sent_images = calls[0]["request_payload"]["input"]["referenceImages"]
    assert len(sent_images) == len(artifact["original_uris"])
    assert [item["role"] for item in sent_images] == artifact["original_roles"]
    assert all(item["uri"].startswith(PLACEHOLDER_PREFIX) for item in sent_images)
    # Same count/order/roles the real projection would forward.
    assert calls[0]["references"] is not None
    assert [ref["role"] for ref in calls[0]["references"]] == artifact["original_roles"]


# ── Case 2: count/role drift still fails closed ───────────────────────────

def test_placeholder_count_drift_still_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _local_ref_artifact(monkeypatch)
    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits=150))
    # Drop one binding row: substituted reconstruction must contradict.
    row = next(
        shot for shot in artifact["manifest"]["shots"]
        if shot.get("shot_id") == artifact["shot_id"]
    )
    row["reference_binding"] = row["reference_binding"][:-1]

    gate = GenerationCostGate()
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record=artifact["contract_record"],
        manifest=artifact["manifest"],
    )
    assert picture["estimated"] is False
    assert picture["failure_class"] == "reconstruction_failed"
    assert picture["materialization_required"] is False
    assert calls == []


# ── Case 3: genuinely malformed refs refuse (never placeholders) ─────────

def test_malformed_role_refuses_without_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.shot_manifest import recompute_manifest_fingerprint

    artifact = _local_ref_artifact(monkeypatch)
    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits=150))
    # Corrupt the manifest binding role: the frozen entry contradicts its
    # manifest, which is genuinely malformed (not a local-URI condition).
    # The stale record fingerprint fails first; either way no placeholders.
    row = next(
        shot for shot in artifact["manifest"]["shots"]
        if shot.get("shot_id") == artifact["shot_id"]
    )
    row["reference_binding"][0]["role"] = "bogus-role"
    artifact["manifest"]["manifest_fingerprint"] = recompute_manifest_fingerprint(
        artifact["manifest"]
    )

    gate = GenerationCostGate()
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record=artifact["contract_record"],
        manifest=artifact["manifest"],
    )
    assert picture["estimated"] is False
    assert picture["failure_class"] == "reconstruction_failed"
    assert picture["materialization_required"] is False
    assert picture["uri_placeholders_used"] is False
    assert calls == []


# ── Amendment 1: placeholder guards ───────────────────────────────────────

def test_real_request_body_refuses_placeholders() -> None:
    from app.services.providers.runway_router_provider import (
        build_runway_router_image_request,
        build_runway_router_video_request,
    )

    refs = [{"image_url": PLACEHOLDER_PREFIX + "r1", "role": "reference"}]
    with pytest.raises(ValueError, match="placeholder"):
        build_runway_router_video_request(
            "prompt", config_id="test-router", references=refs, dry_run=False,
        )
    with pytest.raises(ValueError, match="placeholder"):
        build_runway_router_image_request(
            "prompt", config_id="test-router", references=refs, dry_run=False,
        )
    # Dry-run bodies accept placeholders: the estimator needs them.
    body = build_runway_router_video_request(
        "prompt", config_id="test-router", references=refs, dry_run=True,
    )
    assert body["input"]["referenceImages"][0]["uri"].startswith(PLACEHOLDER_PREFIX)


def test_persist_guards_refuse_placeholders() -> None:
    from app.services.generation_contract import (
        FrozenGenerationContract,
        GenerationContractError,
        freeze_generation_contract,
    )
    from app.services.shot_manifest import build_shot_manifest

    artifact = _r45_build()
    frozen = FrozenGenerationContract.from_record(artifact["contract_record"])
    bad_refs = tuple(
        replace(ref, uri=PLACEHOLDER_PREFIX + (ref.ref_id or "x"))
        if index == 0 else ref
        for index, ref in enumerate(frozen.references)
    )
    import hashlib
    import json

    tampered = replace(frozen, references=bad_refs).to_record()
    with pytest.raises(GenerationContractError, match="placeholder"):
        FrozenGenerationContract.from_record(tampered)

    rows = [
        {
            "uri": PLACEHOLDER_PREFIX + "r1", "role": "reference",
            "studio_role": "reference", "category": "c", "source": "s",
            "ref_id": "r1", "target_type": "character", "target_id": "t",
            "canonical": True, "approval_state": "approved",
            "source_kind": "confirmed",
        }
    ]
    with pytest.raises(GenerationContractError, match="placeholder"):
        freeze_generation_contract(
            shot_id="s", prompt="p", reference_assets=rows,
            parameters={"duration": 5, "aspect_ratio": "16:9"},
        )
    with pytest.raises(ValueError, match="placeholder"):
        build_shot_manifest(
            project_id="p", scene_id="s", scene=None, scene_version="v",
            storyboard_version="b",
            entries=[{
                "shot_id": "s", "references": [PLACEHOLDER_PREFIX + "r1"],
                "reference_binding": [{"ref_id": "r1", "uri": PLACEHOLDER_PREFIX + "r1"}],
            }],
        )


# ── Case 6 (estimator half): failed placeholder estimate never estimates ─

def test_failed_placeholder_estimate_marks_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _local_ref_artifact(monkeypatch)
    calls: list = []
    _stub_submit(monkeypatch, calls, None, exc=RuntimeError("no route"))

    gate = GenerationCostGate()
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record=artifact["contract_record"],
        manifest=artifact["manifest"],
    )
    assert picture["estimated"] is False
    assert picture["failure_class"] == "RuntimeError"
    assert picture["materialization_required"] is True
    assert picture["uri_placeholders_used"] is True


# ── Case 6 (pipeline half): failed placeholder estimate + ack still refuses

def test_failed_placeholder_estimate_refused_despite_ack(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "150")
    _stub_estimator(monkeypatch, {
        "scene_001_shot_002": {
            "model": None, "duration_seconds": 5, "estimated_credits": None,
            "estimated": False, "estimate_source": "runway_router_dry_run",
            "advisory": True, "failure_class": "dry_run_failed",
            "materialization_required": True, "uri_placeholders_used": True,
        },
    })
    with pytest.raises(ValidationError) as excinfo:
        _generate(
            service, _project5(), storyboard_shot_ids=["sbs-002"],
            acknowledge_unknown_cost=True,
        )
    assert "acknowledge_unknown_cost" in str(excinfo.value.message)
    assert render.created == []
    assert render.submits == []


# ── Case: second project independent after placeholder estimate ──────────

def test_second_project_independent_after_placeholder_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _local_ref_artifact(monkeypatch)
    second = _local_ref_artifact(monkeypatch)
    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits=40))

    gate = GenerationCostGate()
    first_picture = gate.estimate_router_shot_via_dry_run(
        contract_record=first["contract_record"], manifest=first["manifest"]
    )
    second_picture = gate.estimate_router_shot_via_dry_run(
        contract_record=second["contract_record"], manifest=second["manifest"]
    )
    assert first_picture["estimated"] is True
    assert second_picture["estimated"] is True
    assert len(calls) == 2
    assert first["contract_record"] == second["contract_record"]
    assert first["manifest"] == second["manifest"]
