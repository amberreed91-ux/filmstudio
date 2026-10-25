"""Phase 6: runway_router ceiling enforcement on the pipeline submit path.

Gate-adding change only: selected runway_router shots are priced with one
advisory non-billing dry-run each (built from the same frozen entry the
real submit sends) before the spend guard. Refusals are the only new
behavior; nothing already allowed becomes refused.

Transport rule for this file: every provider call is a stubbed function —
no network, no jobs, no spend, no live DB. Hermetic tmp dirs only.

Fail-at-HEAD note: the over-ceiling and unknown-cost router tests below
fail on HEAD (no estimator exists; router estimates stay unpriced and ack
waves them through). They pass with the estimator wired in.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any

import pytest

from app.services.generation_cost_gate import (
    GenerationCostGate,
    generation_cost_gate,
)
from app.services.stability import ValidationError
from conftest import run_async
from test_r45_shared_router_gates import _r45_build
from test_scene_pipeline_shot_filter import (
    _generate,
    _harness,
    _project5,
)


# ── Unit: estimator input equality (amendment 1) ──────────────────────────

def _dry_run_result(*, credits: Any = 150, model: str = "seedance2_5") -> dict[str, Any]:
    return {
        "status": "dry_run",
        "url": None,
        "meta": {"estimated_cost_credits": credits, "resolved_model": model},
    }


def _stub_submit(monkeypatch: pytest.MonkeyPatch, calls: list, result: dict) -> None:
    from app.services.providers import runway_router_provider

    def _fake(prompt: str, **kwargs: Any) -> dict:
        calls.append({"prompt": prompt, **kwargs})
        return copy.deepcopy(result)

    monkeypatch.setattr(
        runway_router_provider, "submit_runway_router_video_render", _fake
    )


def test_estimator_input_matches_reconstruction_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dry-run input is built from the same frozen entry the submit sends.

    promptText (camera-projected), duration, referenceImages (remapped roles),
    configId and dryRun must equal an independent reconstruction's fields.
    """
    from app.services.providers.runway_router_provider import (
        project_frozen_camera_plan_prompt,
        reconstruct_runway_router_video_request,
    )

    artifact = _r45_build()
    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits=150))

    gate = GenerationCostGate()
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record=artifact["contract_record"],
        manifest=artifact["manifest"],
    )

    assert picture["estimated"] is True
    assert picture["estimated_credits"] == 150
    assert picture["model"] == "seedance2_5"
    assert picture["advisory"] is True
    assert picture["estimate_source"] == "runway_router_dry_run"

    assert len(calls) == 1
    sent_body = calls[0]["request_payload"]
    expected_body = reconstruct_runway_router_video_request(
        artifact["contract_record"], artifact["manifest"], dry_run=True,
    )
    for key in ("configId", "dryRun"):
        assert sent_body[key] == expected_body[key]
    sent_input, expected_input = sent_body["input"], expected_body["input"]
    assert sent_input["promptText"] == expected_input["promptText"]
    assert sent_input["duration"] == expected_input["duration"]
    assert sent_input["referenceImages"] == expected_input["referenceImages"]
    assert sent_input["aspectRatio"] == expected_input["aspectRatio"]

    # Camera projection proven: promptText is the frozen prompt projected
    # through the frozen camera plan, not the raw contract prompt.
    from app.services.generation_contract import FrozenGenerationContract

    contract = FrozenGenerationContract.from_record(artifact["contract_record"])
    assert sent_input["promptText"] == project_frozen_camera_plan_prompt(
        contract.prompt, contract.payload()["camera_plan"]
    )
    assert sent_input["promptText"] != contract.prompt
    # Duration proven: the frozen duration, not a default.
    assert sent_input["duration"] == contract.duration
    # Remapped roles proven: wire roles are the frozen router roles.
    assert sent_input["referenceImages"] == [
        {"uri": ref.uri, "role": ref.role} for ref in contract.references
    ]


def test_estimator_reconstruction_failure_is_unknown() -> None:
    gate = GenerationCostGate()
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record={"payload": {}},
        manifest={"manifest_fingerprint": "nope"},
    )
    assert picture["estimated"] is False
    assert picture["estimated_credits"] is None
    assert picture["failure_class"] == "reconstruction_failed"
    assert picture["advisory"] is True


def test_estimator_malformed_cost_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _r45_build()
    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits="n/a"))
    gate = GenerationCostGate()
    picture = gate.estimate_router_shot_via_dry_run(
        contract_record=artifact["contract_record"],
        manifest=artifact["manifest"],
    )
    assert picture["estimated"] is False
    assert picture["failure_class"] == "ValueError"


def test_router_timeout_seconds_reported() -> None:
    """Amendment 4: the production router timeout is 300 s."""
    from app.services.providers.runway_router_provider import (
        get_runway_router_timeout_seconds,
    )

    assert get_runway_router_timeout_seconds() == 300.0


# ── Service: refusal matrix (stubbed estimator, hermetic harness) ─────────

def _stub_estimator(monkeypatch: pytest.MonkeyPatch, pictures: dict) -> list:
    """Stub the gate estimator; pictures maps shot_id -> cost picture."""
    seen: list = []

    def _fake(self, *, contract_record, manifest):
        seen.append(contract_record)
        shot = (contract_record.get("payload") or {}).get("shot_id")
        return copy.deepcopy(pictures.get(shot, {
            "model": None, "duration_seconds": 5, "estimated_credits": None,
            "estimated": False, "estimate_source": "runway_router_dry_run",
            "advisory": True, "failure_class": "dry_run_failed",
        }))

    monkeypatch.setattr(
        GenerationCostGate, "estimate_router_shot_via_dry_run", _fake
    )
    return seen


def _known(credits: float) -> dict[str, Any]:
    return {
        "model": "seedance2_5", "duration_seconds": 5,
        "estimated_credits": credits, "estimated": True,
        "estimate_source": "runway_router_dry_run", "advisory": True,
        "failure_class": None,
    }


def test_router_over_ceiling_refused_no_ack_bypass(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "100")
    _stub_estimator(monkeypatch, {"scene_001_shot_002": _known(200.0)})
    with pytest.raises(ValidationError) as excinfo:
        _generate(
            service, _project5(), storyboard_shot_ids=["sbs-002"],
            acknowledge_unknown_cost=True,
        )
    assert "ceiling" in str(excinfo.value.message)
    assert "advisory" in str(excinfo.value.message)
    assert render.created == []
    assert render.submits == []


def test_router_under_ceiling_proceeds(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "150")
    _stub_estimator(monkeypatch, {"scene_001_shot_002": _known(51.0)})
    result = _generate(
        service, _project5(), storyboard_shot_ids=["sbs-002"],
        acknowledge_unknown_cost=True,
    )
    assert len(render.created) == 1
    assert len(render.submits) == 1
    assert result["shot_filter"]["selected_shot_ids"] == ["scene_001_shot_002"]


def test_router_failed_estimate_refused_despite_ack(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "150")
    _stub_estimator(monkeypatch, {})
    with pytest.raises(ValidationError) as excinfo:
        _generate(
            service, _project5(), storyboard_shot_ids=["sbs-002"],
            acknowledge_unknown_cost=True,
        )
    assert "acknowledge_unknown_cost" in str(excinfo.value.message)
    assert "advisory" in str(excinfo.value.message)
    assert render.created == []
    assert render.submits == []


def test_non_router_batch_never_touches_estimator(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import generation_cost_gate as gate_module

    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)

    def _tripwire(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("non-router batch must not call the router estimator")

    monkeypatch.setattr(
        gate_module.GenerationCostGate,
        "estimate_router_shot_via_dry_run",
        _tripwire,
    )
    result = run_async(service.generate_scene(
        project_id="project_filter_test",
        scene_id="scene_001",
        project=_project5(),
        provider="happyhorse",
        storyboard_shot_ids=["sbs-002"],
    ))
    assert len(render.created) == 1
    assert result["shot_filter"]["selected_shot_ids"] == ["scene_001_shot_002"]


def test_second_project_independent_after_refusal(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "150")
    _stub_estimator(monkeypatch, {
        "scene_001_shot_002": _known(51.0),
    })
    project_b = _project5()
    project_b["project_id"] = "project_b"
    result = run_async(service.generate_scene(
        project_id="project_b",
        scene_id="scene_001",
        project=project_b,
        provider="runway_router",
        storyboard_shot_ids=["sbs-002"],
        acknowledge_unknown_cost=True,
    ))
    assert len(render.created) == 1
    assert result["shot_filter"]["selected_shot_ids"] == ["scene_001_shot_002"]


# ── Amendment 3: stamped cost_estimate changes no creative fields ──────────

def test_estimate_method_leaves_contract_and_manifest_byte_identical(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct: stamping touches cost_estimate and nothing else."""
    from test_r45_shared_router_gates import R45_SHOT

    service, _, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    artifact = _r45_build()
    entry: dict[str, Any] = {
        "shot_id": R45_SHOT,
        "duration_seconds": 6,
        "cost_estimate": {
            "model": None, "duration_seconds": 6, "estimated_credits": None,
            "estimated": False,
        },
        "generation_contract": copy.deepcopy(artifact["contract_record"]),
    }
    manifest = copy.deepcopy(artifact["manifest"])
    contract_before = copy.deepcopy(entry["generation_contract"])
    manifest_before = copy.deepcopy(manifest)

    calls: list = []
    _stub_submit(monkeypatch, calls, _dry_run_result(credits=51))
    run_async(service._estimate_filtered_router_shots(
        project_id="proj-r45-gates",
        provider="runway_router",
        selected_entries=[entry],
        shot_manifest=manifest,
    ))

    assert entry["generation_contract"] == contract_before
    assert manifest == manifest_before
    from app.services.shot_manifest import recompute_manifest_fingerprint

    assert manifest["manifest_fingerprint"] == recompute_manifest_fingerprint(manifest)
    assert entry["cost_estimate"]["estimated"] is True
    assert entry["cost_estimate"]["estimated_credits"] == 51


# ── Amendment 4: hung stub refused within the timeout ──────────────────────

def test_hung_dry_run_refused_within_timeout(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_r45_shared_router_gates import R45_SHOT

    service, _, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    monkeypatch.setenv("RUNWAY_ROUTER_TIMEOUT_SECONDS", "0.2")

    from app.services.providers import runway_router_provider

    def _hang(prompt: str, **kwargs: Any) -> dict:
        threading.Event().wait(60)
        raise AssertionError("hung stub must not return")

    monkeypatch.setattr(
        runway_router_provider, "submit_runway_router_video_render", _hang
    )
    artifact = _r45_build()
    entry: dict[str, Any] = {
        "shot_id": R45_SHOT,
        "duration_seconds": 6,
        "cost_estimate": {
            "model": None, "duration_seconds": 6, "estimated_credits": None,
            "estimated": False,
        },
        "generation_contract": artifact["contract_record"],
    }
    started = time.monotonic()
    run_async(service._estimate_filtered_router_shots(
        project_id="proj-r45-gates",
        provider="runway_router",
        selected_entries=[entry],
        shot_manifest=artifact["manifest"],
    ))
    elapsed = time.monotonic() - started
    assert elapsed < 30
    assert entry["cost_estimate"]["estimated"] is False
    assert entry["cost_estimate"]["failure_class"] == "dry_run_timeout"
    # The follow-on refusal closes the gate even with ack semantics on.
    with pytest.raises(ValidationError) as excinfo:
        service._refuse_unestimated_router_shots(
            project_id="proj-r45-gates",
            selected_entries=[entry],
        )
    assert "acknowledge_unknown_cost" in str(excinfo.value.message)
