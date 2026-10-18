"""SCENE 002 regression, part 2 — reference gate fails closed at pipeline level.

Test-only. Synthetic fixtures only. No live calls of any kind.

Drives the ``except`` block in
``SceneProductionPipelineService.prepare_scene_batch`` (the handler that sets
``reference_binding = []``): canonical character + setting refs plus a
storyboard frame, with a validation failure injected at the canonical
identity binding step.

Asserts:
  1. the shot is reported not-ready with a ``reference gate:`` blocker;
  2. ``preflight_batch_authorization`` rejects the batch (``upstream_blockers``);
  3. zero jobs are created;
  4. no provider is contacted;
  5. the storyboard frame never appears as the sole reference on any request.
"""

from __future__ import annotations

import socket
import tempfile
from types import SimpleNamespace
from typing import Any

PROJECT_ID = "project-refgate-failclosed-regression"
SCENE_ID = "scene_regression_refgate"
SHOT_ID = "scene_regression_refgate_shot_001"
CHARACTER_ID = "char-regression-refgate"
SETTING_ID = "set-regression-refgate"
CHARACTER_URL = "https://cdn.example.test/refgate-ava-face.png"
SETTING_URL = "https://cdn.example.test/refgate-harbor-env.png"
STORYBOARD_URL = "https://cdn.example.test/refgate-board-frame.png"


def _binding() -> list[dict[str, Any]]:
    return [
        {
            "ref_id": "ref-reggate-ava-face",
            "uri": CHARACTER_URL,
            "target_type": "character",
            "target_id": CHARACTER_ID,
            "role": "face",
            "category": "face",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "ref-reggate-harbor-env",
            "project_id": PROJECT_ID,
            "uri": SETTING_URL,
            "target_type": "setting",
            "target_id": SETTING_ID,
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "environment",
        },
    ]


def _requirements(binding: list[dict[str, Any]]) -> dict[str, Any]:
    char_rows = [dict(r) for r in binding if r.get("target_type") == "character"]
    setting_rows = [dict(r) for r in binding if r.get("target_type") == "setting"]
    return {
        "scene_id": SCENE_ID,
        "character_ids": [CHARACTER_ID],
        "characters": {
            CHARACTER_ID: {
                "name": "Ava",
                "urls": [r["uri"] for r in char_rows],
                "references": char_rows,
            }
        },
        "setting_id": SETTING_ID,
        "setting_urls": [r["uri"] for r in setting_rows],
        "setting_references": setting_rows,
        "allowed_urls": [r["uri"] for r in binding],
    }


class _FakeRenderService:
    """Minimal job sink: prepare/preflight must never create jobs."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.jobs: dict[str, Any] = {}

    def create_job(self, **kwargs: Any) -> Any:  # pragma: no cover - must stay uncalled
        self.created.append(dict(kwargs))
        raise AssertionError("reference-gate failure must not create jobs")


class _FakeAudioService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []


class _FakeStitchingService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []


def _block_network(monkeypatch) -> dict[str, list]:
    """Patch provider/LLM/network clients to raise on any live contact."""
    calls: dict[str, list] = {"adapter": [], "socket": []}

    def _forbidden_adapter(*args: Any, **kwargs: Any) -> Any:
        calls["adapter"].append({"args": args, "kwargs": kwargs})
        raise AssertionError("reference-gate failure must not contact a provider adapter")

    monkeypatch.setattr("app.services.render.get_adapter", _forbidden_adapter)

    class _ForbiddenSocket(socket.socket):
        def connect(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
            calls["socket"].append({"args": args})
            raise AssertionError("network contact is forbidden in this test")

    monkeypatch.setattr(socket, "socket", _ForbiddenSocket)

    def _forbidden_create_connection(*args: Any, **kwargs: Any) -> Any:
        calls["socket"].append({"args": args})
        raise AssertionError("network contact is forbidden in this test")

    monkeypatch.setattr(socket, "create_connection", _forbidden_create_connection)
    # Common LLM/provider clients: fail closed if anything tries a live call.
    for target in (
        "boto3.client",
        "botocore.client.BaseClient._make_api_call",
        "urllib.request.urlopen",
    ):
        try:
            monkeypatch.setattr(
                target,
                lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError(f"live call forbidden: {target}")
                ),
            )
        except Exception:
            pass
    return calls


def _prepare_with_injected_validation_failure(monkeypatch):
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )

    binding = _binding()
    scene = {
        "scene_id": SCENE_ID,
        "heading": "INT. REGRESSION ROOM - DAY",
        "text": "A lamp glows beside a closed book.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": PROJECT_ID,
        "script_text": "INT. REGRESSION ROOM - DAY\nA lamp glows beside a closed book.",
        "execution_summary": {"scenes": [scene]},
    }
    canonical_uris = [row["uri"] for row in binding]
    reference_assets = [STORYBOARD_URL, *canonical_uris]
    board_parameters: dict[str, Any] = {
        "duration": 5,
        "ratio": "16:9",
        "storyboard": {
            "version_id": "approved-refgate-version",
            "storyboard_shot_id": "board-refgate-shot-1",
        },
        "storyboard_frame_url": STORYBOARD_URL,
    }
    board_shot = SimpleNamespace(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        shot_id=SHOT_ID,
        shot_number=1,
        storyboard_shot_id="board-refgate-shot-1",
        version_id="approved-refgate-version",
        status="approved",
        updated_at="2026-10-01T00:00:01+00:00",
        prompt="originating-refgate-prompt-1",
        duration_seconds=5,
        parameters=dict(board_parameters),
        reference_assets=list(reference_assets),
        source_refs=list(reference_assets),
        camera_plan={"camera": "Hold", "framing": "Wide"},
        render_contract=SimpleNamespace(
            provider_neutral_prompt="originating-refgate-prompt-1",
            structured_parameters={"camera_plan": {"camera": "Hold", "framing": "Wide"}},
            duration_seconds=5,
            aspect_ratio="16:9",
            reference_assets=list(reference_assets),
        ),
        metadata={},
    )
    monkeypatch.setattr(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.scene_render_inputs",
        lambda _project_id, _scene_id: [board_shot],
    )

    def _resolve_requirements(**kwargs: Any) -> dict[str, Any]:
        return _requirements(binding)

    monkeypatch.setattr(
        "app.services.reference_validation.resolve_scene_reference_requirements",
        _resolve_requirements,
    )

    def _injected_failure(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("injected canonical validation failure")

    # This is the call inside the try block that the regression covers: forcing
    # it to raise drives the `except` handler that sets reference_binding = [].
    monkeypatch.setattr(
        "app.services.reference_validation.reference_binding_for_requirements",
        _injected_failure,
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.validate_generation_context",
        lambda **kwargs: SimpleNamespace(blockers=[]),
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.create_generation_context",
        lambda **kwargs: SimpleNamespace(
            generation_context_id=f"ctx-{kwargs['shot_id']}",
            scene_version="scene-version",
            shot_version=f"version-{kwargs['shot_id']}",
            reference_version="test",
            to_dict=lambda: {"shot_id": kwargs["shot_id"]},
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.reference_version",
        lambda **kwargs: "test",
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.enforce_shot_limit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.estimate_batch",
        lambda *, provider, shots: {"provider": provider, "per_shot": [], "estimated": False},
    )
    from app.services.storyboard_blueprint_service import storyboard_blueprint_service

    monkeypatch.setattr(
        storyboard_blueprint_service.storage,
        "get_storyboard_shot",
        lambda storyboard_shot_id: board_shot,
    )

    from app.services.scene_coverage_contract import build_scene_coverage_contract

    probe_coverage, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID,
        project=project,
        scene=scene,
        shots=[{"shot_id": SHOT_ID, "scene_id": SCENE_ID, "parameters": {}}],
        reference_requirements={
            "setting_id": SETTING_ID,
            "characters": _requirements(binding)["characters"],
            "reference_binding": binding,
        },
    )
    creator_decisions = [
        {
            "obligation_type": "content",
            "obligation_id": row["content_id"],
            "status": "ASSIGNED",
            "shot_id": SHOT_ID,
            "reason": "",
        }
        for row in probe_coverage["content_units"]
    ]
    creator_decisions.extend(
        [
            {
                "obligation_type": "shot_content",
                "obligation_id": SHOT_ID,
                "status": "UNRESOLVED",
                "shot_id": None,
                "reason": "",
            },
            {
                "obligation_type": "shot_dialogue",
                "obligation_id": SHOT_ID,
                "status": "INTENTIONAL_SILENCE",
                "reason": "The approved shot contains no spoken dialogue.",
            },
        ]
    )
    board_shot.parameters["creator_coverage_decisions"] = creator_decisions

    render = _FakeRenderService()
    service = SceneProductionPipelineService(
        render_svc=render,  # type: ignore[arg-type]
        audio_svc=_FakeAudioService(),  # type: ignore[arg-type]
        stitching_svc=_FakeStitchingService(),  # type: ignore[arg-type]
        backend_root=tempfile.gettempdir(),  # type: ignore[arg-type]
    )
    batch = service.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=project,
        provider="simulated",
    )
    return service, render, batch


def _all_observed_reference_lists(batch: dict[str, Any], render: _FakeRenderService) -> list[list[str]]:
    observed: list[list[str]] = []
    for entry in batch.get("entries", []):
        refs = entry.get("references")
        if isinstance(refs, list):
            observed.append([str(u) for u in refs])
        binding = entry.get("reference_binding")
        if isinstance(binding, list):
            observed.append([str(r.get("uri") or "") for r in binding if isinstance(r, dict)])
        contract = entry.get("generation_contract")
        if isinstance(contract, dict):
            payload_refs = ((contract.get("payload") or {}).get("references") or [])
            if isinstance(payload_refs, list):
                observed.append(
                    [str(r.get("uri") or "") for r in payload_refs if isinstance(r, dict)]
                )
        manifest_binding = None
        try:
            manifest_binding = entry.get("generation_settings", {}).get("frozen_reference_binding")
        except Exception:
            manifest_binding = None
        if isinstance(manifest_binding, list):
            observed.append(
                [str(r.get("uri") or "") for r in manifest_binding if isinstance(r, dict)]
            )
    manifest = batch.get("manifest") or {}
    for row in manifest.get("shots", []) or []:
        if isinstance(row, dict) and isinstance(row.get("reference_binding"), list):
            observed.append(
                [str(r.get("uri") or "") for r in row["reference_binding"] if isinstance(r, dict)]
            )
        if isinstance(row, dict) and isinstance(row.get("references"), list):
            observed.append([str(u) for u in row["references"]])
    for call in render.created:
        assets = call.get("reference_assets")
        if isinstance(assets, list):
            observed.append([str(u) for u in assets])
    return observed


def test_reference_gate_validation_failure_fails_closed_end_to_end(monkeypatch):
    network_calls = _block_network(monkeypatch)
    service, render, batch = _prepare_with_injected_validation_failure(monkeypatch)

    # 1. The shot is reported not-ready with a `reference gate:` blocker.
    assert batch["ready"] is False
    entries = [r for r in batch["entries"] if r.get("shot_id") == SHOT_ID]
    assert len(entries) == 1
    entry = entries[0]
    gate_blockers = [b for b in (entry.get("blockers") or []) if b.startswith("reference gate:")]
    assert gate_blockers, f"expected a 'reference gate:' blocker, got {entry.get('blockers')}"
    assert any("injected canonical validation failure" in b for b in gate_blockers)
    # The except handler clears the binding instead of reducing it to the frame.
    assert entry.get("reference_binding") == []
    assert any(
        f"Shot {SHOT_ID}: reference gate:" in b for b in (batch.get("blockers") or [])
    )

    # 2. Preflight rejects the batch on upstream blockers (no second failure invented).
    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=batch["entries"],
        shot_manifest=batch["manifest"],
        expected_digests=None,
    )
    assert report["ready"] is False
    shot_reports = [r for r in report["shots"] if r.get("shot_id") == SHOT_ID]
    assert len(shot_reports) == 1
    assert shot_reports[0]["ok"] is False
    assert shot_reports[0]["failure_code"] == "upstream_blockers"

    # 3/4. Zero jobs created; no provider contact.
    assert render.created == []
    assert render.jobs == {}
    assert network_calls["adapter"] == []
    assert network_calls["socket"] == []

    # 5. The storyboard frame never appears as the sole reference on any request.
    for uri_list in _all_observed_reference_lists(batch, render):
        assert uri_list != [STORYBOARD_URL], (
            f"storyboard frame must never be the sole reference, got {uri_list}"
        )
    binding_uris = {
        str(r.get("uri") or "") for r in (entry.get("reference_binding") or []) if isinstance(r, dict)
    }
    assert STORYBOARD_URL not in binding_uris
