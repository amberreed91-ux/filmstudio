"""Option A: materialized price probe for local-reference router shots.

Stubbed transport only: every provider call is a stubbed function — no
network, no uploads, no spend, no live DB. Hermetic temp dirs only.

The probe (RunwayRouterAdapter.price_with_materialized_reference) reuses
the submit path's materialization and its dry-run branch, then stops: the
live POST is structurally unreachable, no job row is created, and the
price picture never carries the alias.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig
from app.services.scene_production_pipeline_service import (
    SceneProductionPipelineService,
)
from app.services.stability import ValidationError
from app.services.test_scene_production_pipeline_service import (
    FakeAudioService,
    FakeRenderService,
    FakeStitchingService,
)
from conftest import run_async


def _adapter() -> RunwayRouterAdapter:
    return RunwayRouterAdapter(
        ProviderConfig(provider_id="runway_router", name="Runway Router")
    )


def _local_probe_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[dict[str, Any], dict[int, tuple[str, bytes]]]:
    """Frozen (contract, manifest, binding) triple with file-backed local refs."""
    import test_r45_shared_router_gates as r45
    from test_r45_shared_router_gates import _r45_build

    roles = ("face", "environment")
    files: dict[int, tuple[str, bytes]] = {}
    for index in range(len(roles)):
        data = f"probe-bytes-{index}-".encode("utf-8") + bytes([index + 1]) * 64
        target = tmp_path / "outputs" / f"probe-ref-{index}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[index] = (f"/outputs/probe-ref-{index}.png", data)
    real_binding = r45._r45_raw_binding

    def _local_binding(
        *, roles: Any = roles, project_id: str = r45.R45_PROJECT
    ) -> list[dict[str, Any]]:
        rows = real_binding(roles=roles, project_id=project_id)
        for index, row in enumerate(rows):
            row["uri"] = files[index][0]
        return rows

    monkeypatch.setattr(r45, "_r45_raw_binding", _local_binding)
    return _r45_build(roles=roles), files


def _stub_uploads(
    calls_json: list[dict[str, Any]], calls_multipart: list[dict[str, Any]]
) -> tuple[Any, Any]:
    def _fake_post_json(
        url: str, payload: dict[str, Any], api_key: Any = None
    ) -> dict[str, Any]:
        calls_json.append({"url": url, "payload": dict(payload)})
        filename = str(payload.get("filename") or "file.bin")
        return {
            "uploadUrl": "https://upload.test/complete",
            "fields": {"key": "k", "policy": "p"},
            "runwayUri": f"runway://ephemeral-probe-{filename}",
        }

    def _fake_post_multipart(
        upload_url: str,
        fields: dict[str, str],
        file_bytes: bytes,
        filename: str,
    ) -> None:
        calls_multipart.append({
            "upload_url": upload_url,
            "byte_count": len(file_bytes),
            "filename": filename,
        })

    return _fake_post_json, _fake_post_multipart


def _stub_ephemeral_transport(
    monkeypatch: pytest.MonkeyPatch,
    calls_json: list[dict[str, Any]],
    calls_multipart: list[dict[str, Any]],
) -> None:
    """Stub the ephemeral uploader's default transport (pipeline path).

    The pipeline invokes the probe without seams, so the module-level
    defaults are replaced instead. No network occurs.
    """
    from app.services import runway_ephemeral_upload as ephemeral

    post_json, post_multipart = _stub_uploads(calls_json, calls_multipart)
    monkeypatch.setattr(ephemeral, "_default_post_json", post_json)
    monkeypatch.setattr(ephemeral, "_default_post_multipart", post_multipart)


def _stub_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[dict[str, Any]],
    *,
    credits: float = 77.0,
    model: str = "probe-model-1",
) -> None:
    """Replace the provider submit; any non-dry-run call raises."""
    from app.services.providers import runway_router_provider as provider

    def _fake(prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        if kwargs.get("dry_run") is not True:
            raise AssertionError("probe issued a non-dry-run provider call")
        payload = kwargs.get("request_payload") or {}
        if not isinstance(payload, dict) or payload.get("dryRun") is not True:
            raise AssertionError("probe issued a provider call without dryRun:true")
        images = (payload.get("input") or {}).get("referenceImages") or []
        for item in images:
            uri = str(item.get("uri") or "")
            assert uri.startswith("runway://"), f"probe dry-run refs must be real aliases, got {uri!r}"
            assert "dry-run-placeholder" not in uri, "probe must never send placeholder URIs"
            assert not uri.startswith("/outputs"), "probe must never send local paths"
        return {
            "status": "dry_run",
            "url": None,
            "file_path": None,
            "error": None,
            "meta": {
                "estimated_cost_credits": credits,
                "resolved_model": model,
            },
        }

    monkeypatch.setattr(provider, "submit_runway_router_video_render", _fake)


def _probe_kwargs(
    artifact: dict[str, Any], tmp_path: Path, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    import test_r45_shared_router_gates as r45

    kwargs: dict[str, Any] = {
        "contract_record": artifact["contract_record"],
        "manifest_record": artifact["manifest"],
        "reference_binding": artifact["binding"],
        "project_id": r45.R45_PROJECT,
        "shot_id": r45.R45_SHOT,
        "backend_root": tmp_path,
        # Dummy credential: the stubbed _post_json/_post_multipart doubles
        # below receive but never use it; no real secret exists in tests.
        "api_key": "test-key",
    }
    if extra:
        kwargs.update(extra)
    return kwargs


# ── 1. numeric price ──────────────────────────────────────────────────────

def test_probe_returns_numeric_price_for_local_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    calls_json: list[dict[str, Any]] = []
    calls_multipart: list[dict[str, Any]] = []
    post_json, post_multipart = _stub_uploads(calls_json, calls_multipart)
    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls, credits=77.0)

    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(artifact, tmp_path, {
            "_post_json": post_json, "_post_multipart": post_multipart,
        })
    )

    assert picture["estimated"] is True
    assert picture["estimated_credits"] == 77.0
    assert picture["model"] == "probe-model-1"
    assert picture["estimate_source"] == "runway_router_materialized_probe"
    assert picture["advisory"] is True
    assert picture["failure_class"] is None
    assert picture["uri_placeholders_used"] is False
    assert len(calls_json) == 2
    assert len(calls_multipart) == 2
    assert all(call["byte_count"] > 0 for call in calls_multipart)
    assert len(dry_calls) == 1


# ── 2. live POST structurally unreachable ─────────────────────────────────

def test_probe_never_issues_live_post_poll_or_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    post_json, post_multipart = _stub_uploads([], [])
    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls, credits=51.0)

    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(artifact, tmp_path, {
            "_post_json": post_json, "_post_multipart": post_multipart,
        })
    )

    # The stub raises on any non-dry-run call, so reaching this line proves
    # the live path was never taken.
    assert picture["estimated"] is True
    assert all(call.get("dry_run") is True for call in dry_calls)
    assert "runway_task_id" not in picture
    assert "task_id" not in picture


# ── 3. fingerprint mismatch transmits zero bytes ──────────────────────────

def test_probe_fingerprint_mismatch_transmits_zero_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    calls_json: list[dict[str, Any]] = []
    calls_multipart: list[dict[str, Any]] = []
    post_json, post_multipart = _stub_uploads(calls_json, calls_multipart)
    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls)
    ref_ids = [str(row.get("ref_id")) for row in artifact["binding"]]

    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(artifact, tmp_path, {
            "source_fingerprints": {ref_id: "0" * 64 for ref_id in ref_ids},
            "_post_json": post_json, "_post_multipart": post_multipart,
        })
    )

    assert picture["estimated"] is False
    assert picture["failure_class"] == "source_fingerprint_mismatch"
    assert calls_json == []
    assert calls_multipart == []
    assert dry_calls == []


# ── 4. expired alias fails closed ─────────────────────────────────────────

def test_probe_expired_alias_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    calls_json: list[dict[str, Any]] = []
    calls_multipart: list[dict[str, Any]] = []
    post_json, post_multipart = _stub_uploads(calls_json, calls_multipart)
    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls)
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    record = {
        "materialization_timestamp": stale,
        "provider_uris": {
            str(row.get("ref_id")): "runway://ephemeral-stale-alias"
            for row in artifact["binding"]
        },
    }

    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(artifact, tmp_path, {
            "materialization": record,
            "_post_json": post_json, "_post_multipart": post_multipart,
        })
    )

    assert picture["estimated"] is False
    assert picture["failure_class"] == "materialization_expired"
    assert calls_json == []
    assert calls_multipart == []
    assert dry_calls == []


# ── 5. no alias forwarded ─────────────────────────────────────────────────

def test_probe_picture_carries_no_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json

    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    post_json, post_multipart = _stub_uploads([], [])
    _stub_dry_run(monkeypatch, [])

    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(artifact, tmp_path, {
            "_post_json": post_json, "_post_multipart": post_multipart,
        })
    )

    assert picture["estimated"] is True
    assert "runway://" not in _json.dumps(picture)
    assert "provider_uris" not in picture
    assert "materialization_digest" not in picture
    assert "materialization_expires_at" not in picture


# ── 6. second-project isolation ───────────────────────────────────────────

def test_probe_second_project_isolation_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    calls_json: list[dict[str, Any]] = []
    calls_multipart: list[dict[str, Any]] = []
    post_json, post_multipart = _stub_uploads(calls_json, calls_multipart)
    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls)

    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(artifact, tmp_path, {
            "project_id": "proj-foreign",
            "_post_json": post_json, "_post_multipart": post_multipart,
        })
    )

    assert picture["estimated"] is False
    assert picture["failure_class"] == "project_scope_mismatch"
    assert calls_json == []
    assert calls_multipart == []
    assert dry_calls == []


# ── 7. allocation logging ─────────────────────────────────────────────────

def test_probe_logs_its_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import test_r45_shared_router_gates as r45

    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    post_json, post_multipart = _stub_uploads([], [])
    _stub_dry_run(monkeypatch, [])

    with caplog.at_level(logging.INFO, logger="studio-render"):
        picture = _adapter().price_with_materialized_reference(
            **_probe_kwargs(artifact, tmp_path, {
                "_post_json": post_json, "_post_multipart": post_multipart,
            })
        )

    assert picture["estimated"] is True
    assert "ROUTER_PRICE_PROBE_MATERIALIZED" in caplog.text
    assert r45.R45_SHOT in caplog.text


# ── 8. pipeline: probe price over ceiling refuses with no job row ─────────

def test_pipeline_probe_price_over_ceiling_refuses_no_job_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import test_r45_shared_router_gates as r45

    artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "100")
    # Dummy credential for the probe's allocation step; the stubbed
    # transport below never dials, so no real secret exists in this test.
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    transport_json: list[dict[str, Any]] = []
    transport_multipart: list[dict[str, Any]] = []
    _stub_ephemeral_transport(monkeypatch, transport_json, transport_multipart)
    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls, credits=200.0)
    (tmp_path / "outputs" / "renders").mkdir(parents=True, exist_ok=True)
    render = FakeRenderService(tmp_path / "outputs" / "renders")
    service = SceneProductionPipelineService(
        backend_root=tmp_path,
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
    )
    entry = {
        "shot_id": r45.R45_SHOT,
        "storyboard_shot_id": "board-r45",
        "generation_contract": copy.deepcopy(artifact["contract_record"]),
        "reference_binding": copy.deepcopy(artifact["binding"]),
        "duration_seconds": 5,
    }
    selected = [entry]

    run_async(service._estimate_filtered_router_shots(
        project_id=r45.R45_PROJECT,
        provider="runway_router",
        selected_entries=selected,
        shot_manifest=copy.deepcopy(artifact["manifest"]),
    ))

    estimate = entry.get("cost_estimate") or {}
    assert estimate.get("estimated") is True
    assert estimate.get("estimate_source") == "runway_router_materialized_probe"
    assert estimate.get("estimated_credits") == 200.0
    assert estimate.get("uri_placeholders_used") is False
    service._refuse_unestimated_router_shots(
        project_id=r45.R45_PROJECT, selected_entries=selected
    )
    with pytest.raises(ValidationError):
        service._enforce_filtered_spend_guards(
            project_id=r45.R45_PROJECT,
            provider="runway_router",
            selected_entries=selected,
            acknowledge_unknown_cost=True,
        )
    assert render.created == []


# ── 9. placeholder path preserved for non-local refs ─────────────────────

def test_entry_detection_preserves_placeholder_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_r45_shared_router_gates import _r45_build

    https_artifact = _r45_build()
    assert SceneProductionPipelineService._entry_has_local_router_refs(
        https_artifact["contract_record"]
    ) is False

    local_artifact, _ = _local_probe_artifact(monkeypatch, tmp_path)
    assert SceneProductionPipelineService._entry_has_local_router_refs(
        local_artifact["contract_record"]
    ) is True

    dry_calls: list[dict[str, Any]] = []
    _stub_dry_run(monkeypatch, dry_calls)
    picture = _adapter().price_with_materialized_reference(
        **_probe_kwargs(https_artifact, tmp_path)
    )
    assert picture["estimated"] is False
    assert picture["failure_class"] == "no_local_references"
    assert dry_calls == []
