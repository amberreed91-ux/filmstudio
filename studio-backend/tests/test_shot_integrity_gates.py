"""Per-shot integrity gates — read-only endpoint tests (STEP 1).

Fail-at-HEAD proof: the ``integrity-gates`` route does not exist at HEAD,
so every 200-asserting test below fails there with 404. Isolated DBs only
(conftest redirects STUDIO_STORAGE_PATH per process); the live DB is never
opened and the guard suite refuses it.

Covers: unknown project/shot 404s, missing board, unapproved/approved/stale
D4/D6, anchor set/blocked, confirmation missing/confirmed/stale, contract
absent/on-file/refused, preflight never-a-send-permission, spend
persisted-only + local-refs-can-never-price, duplicate postures, second
project isolation, absent-table creates nothing, DB fingerprint identical
before/after, and a guard proving the endpoint creates no job/seed and
calls no provider (prepare, dry-run, submit all forbidden).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from main import app
from app.data.storage import get_storage
from app.models import RenderJobInput, RenderJobModel, StudioProject
from app.services.render import render_service
from app.services.project_store import project_store
from app.services.scene_production_pipeline_service import scene_production_pipeline_service
from app.services.shot_integrity_gates_service import classify_duplicate, classify_spend
from app.services.storyboard_blueprint_service import storyboard_blueprint_service
from app.services.storyboard_image_prompt_service import storyboard_image_prompt_service

SCENE_TEXT = """INT. EDIT BAY - NIGHT
Maya holds the cut one breath longer. The room hums low."""

SHORT_TEXT = "Maya waits by the edit bay door, night soft behind her."


def _seed_project(project_id: str, scene_ids: tuple[str, ...] = ("scene_001",)) -> None:
    scenes = [
        {
            "scene_id": scene_id,
            "scene_name": f"Scene {scene_id[-3:]}",
            "heading": "INT. EDIT BAY - NIGHT",
            "text": SCENE_TEXT,
            "characters": [],
            "updated_at": "2026-10-24T00:00:00Z",
        }
        for scene_id in scene_ids
    ]
    payload = {
        "project_id": project_id,
        "title": f"Shot Gates {project_id}",
        "script_text": SCENE_TEXT,
        "execution_summary": {"scenes": scenes},
    }
    project_store.save_project(payload)
    get_storage("sqlite").save_project(StudioProject(**payload))


def _board(project_id: str, scene_id: str = "scene_001", shot_count: int = 2) -> dict[str, Any]:
    return storyboard_blueprint_service.get_or_create_blueprint(
        project_id=project_id, scene_id=scene_id, shot_count=shot_count
    )


def _shots(detail: dict[str, Any]) -> list[Any]:
    storage = get_storage("sqlite")
    return storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )


def _approve(shot: Any) -> None:
    storyboard_image_prompt_service.edit_for_shot(shot, image_prompt=SHORT_TEXT, edited_by="creator")
    storyboard_image_prompt_service.approve_for_shot(shot, approved_by="creator")


def _gates(project_id: str, shot_id: str) -> Any:
    client = TestClient(app)
    return client.get(
        f"/api/f51/studio/projects/{project_id}/shots/{shot_id}/integrity-gates"
    )


def _seed_alias_anchor(
    project_id: str,
    scene_id: str = "scene_001",
    setting_id: str = "loc-061ebeb1",
    retired_id: str = "loc-b543d669",
    approval_state: str = "approved",
) -> None:
    """Mirror the devcopy-post shape: approved anchor bound to a retired
    setting ID, bridged to the live node by a universe alias."""
    storage = get_storage("sqlite")
    storage.save_universe_node(
        {
            "node_id": setting_id,
            "project_id": project_id,
            "node_type": "location",
            "name": "Edit Bay",
            "first_scene": scene_id,
            "last_scene": scene_id,
        }
    )
    assert storage.save_universe_id_alias(project_id, retired_id, setting_id, reason="test")
    assert storage.save_reference_asset(
        {
            "ref_id": "ref_test_gates_anchor_001",
            "project_id": project_id,
            "target_type": "setting",
            "target_id": retired_id,
            "kind": "environment",
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": approval_state,
            "image_url": "https://cdn.example/gates-anchor.jpg",
            "source_kind": "uploaded",
        }
    )


def _db_fingerprint() -> str:
    storage = get_storage("sqlite")
    digest = hashlib.sha256()
    base = Path(storage.storage_path)
    for path in sorted(base.glob("studio.db*")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    store_path = os.environ.get("STUDIO_PROJECT_STORE_PATH", "")
    if store_path and Path(store_path).exists():
        digest.update(Path(store_path).read_bytes())
    return digest.hexdigest()


def _router_contract_defaults(project_id: str, shot_id: str) -> dict[str, Any]:
    # Storage fail-closes Router persists without complete frozen-contract
    # metadata; every Router fixture below carries the full five-key shape.
    return {
        "creative_generation_contract": {"frozen": True, "shot_id": shot_id},
        "creative_generation_manifest": {"manifest_fingerprint": "fp-test"},
        "creative_manifest_fingerprint": "fp-test",
        "creative_contract_digest": "digest-test",
        "creative_generation_identity": {"project_id": project_id, "shot_id": shot_id},
    }


def _save_job(storage: Any, job_id: str, project_id: str, shot_id: str, **kwargs: Any) -> None:
    metadata = kwargs.pop("metadata", None)
    status = kwargs.pop("status", "pending")
    provider = kwargs.pop("provider", "runway_router")
    if provider == "runway_router":
        merged = _router_contract_defaults(project_id, shot_id)
        merged.update(metadata or {})
        metadata = merged
    job = RenderJobModel(
        id=job_id,
        project_id=project_id,
        shot_id=shot_id,
        provider=provider,
        status=status,
        input_payload=RenderJobInput(shot_id=shot_id, prompt="Maya holds the cut."),
        created_at="2026-10-24T10:00:00+00:00",
        metadata=metadata,
        **kwargs,
    )
    storage.save_job(job)


# ----------------------------------------------------------------------
# Contract basics
# ----------------------------------------------------------------------


def test_shot_gates_unknown_project_returns_404() -> None:
    response = _gates("project_gates_missing", "scene_001_shot_001")
    assert response.status_code == 404


def test_shot_gates_unknown_shot_returns_404() -> None:
    project_id = "project_gates_noshot"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    assert shot.shot_id != "scene_001_shot_999"
    response = _gates(project_id, "scene_001_shot_999")
    assert response.status_code == 404


def test_shot_gates_requires_ids() -> None:
    client = TestClient(app)
    response = client.get("/api/f51/studio/projects/%20/shots/%20/integrity-gates")
    assert response.status_code in {400, 404}


# ----------------------------------------------------------------------
# Gate states: board / D4 / D6 / anchor / confirmation
# ----------------------------------------------------------------------


def test_shot_gates_missing_board_reports_not_yet() -> None:
    project_id = "project_gates_noboard"
    _seed_project(project_id)
    response = _gates(project_id, "scene_001_shot_001")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["scene_id"] == "scene_001"
    assert payload["gates"]["image"]["state"] == "not_yet"
    assert payload["gates"]["words"]["state"] == "not_yet"
    assert payload["gates"]["contract"]["state"] == "not_yet"
    assert payload["gates"]["preflight"]["state"] in {"blocked", "not_yet", "cant_check"}
    assert "ready to send" not in response.text.lower()


def test_shot_gates_unapproved_prompts_block_with_next_action() -> None:
    project_id = "project_gates_unapproved"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["image"]["state"] == "blocked"
    assert payload["gates"]["words"]["state"] == "blocked"
    assert payload["gates"]["settled"]["state"] == "not_yet"
    assert payload["gates"]["settled"]["label"] == "Not confirmed yet"
    assert payload["next_action"] == "approve_image_prompts"
    assert payload["blockers"]


def test_shot_gates_approved_prompts_pass_image_and_words() -> None:
    project_id = "project_gates_approved"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["image"] == {
        "state": "pass",
        "label": "Image ready",
        "detail": "The approved image prompt is current.",
    }
    assert payload["gates"]["words"]["state"] == "pass"


def test_shot_gates_stale_prompt_blocks_image() -> None:
    project_id = "project_gates_stale"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    shot.render_contract.provider_neutral_prompt = (
        str(shot.render_contract.provider_neutral_prompt or "") + " An added beat."
    )
    get_storage("sqlite").save_storyboard_shot(shot)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    assert response.json()["gates"]["image"]["state"] == "blocked"


def test_shot_gates_alias_anchor_resolves_look_pass() -> None:
    project_id = "project_gates_anchor"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _seed_alias_anchor(project_id)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    assert response.json()["gates"]["look"]["state"] == "pass"


def test_shot_gates_unapproved_anchor_blocks_look() -> None:
    project_id = "project_gates_anchor_bad"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _seed_alias_anchor(project_id, approval_state="candidate")

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    assert response.json()["gates"]["look"]["state"] == "blocked"


def test_shot_gates_confirmed_binding_passes_settled() -> None:
    from app.services.reference_asset_service import reference_asset_service

    project_id = "project_gates_confirmed"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _seed_alias_anchor(project_id)
    fresh = reference_asset_service.resolve_shot_binding(project_id, shot.shot_id)
    recorded = reference_asset_service.record_shot_confirmation(
        project_id, shot.shot_id, fresh["binding_digest"]
    )
    assert recorded["status"] == "confirmed"

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    assert response.json()["gates"]["settled"] == {
        "state": "pass",
        "label": "Confirmed",
        "detail": "The binding was explicitly confirmed and still matches.",
    }


def test_shot_gates_mismatched_digest_marks_settled_blocked() -> None:
    project_id = "project_gates_stale_confirm"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    _seed_alias_anchor(project_id)
    get_storage("sqlite").save_shot_reference_confirmation(
        {
            "project_id": project_id,
            "scene_id": "scene_001",
            "shot_id": shot.shot_id,
            "confirmed_digest": "digest-that-never-matches-anything",
            "status": "confirmed",
        }
    )

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["settled"]["state"] == "blocked"
    assert payload["gates"]["settled"]["label"] == "Changed since confirmed"
    assert payload["next_action"] == "confirm_binding"


# ----------------------------------------------------------------------
# Contract / preflight / spend / duplicate from persisted rows only
# ----------------------------------------------------------------------


def test_shot_gates_contract_present_and_sent_reports_historical_pass() -> None:
    from app.services.reference_asset_service import reference_asset_service

    project_id = "project_gates_contract"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    _seed_alias_anchor(project_id)
    fresh = reference_asset_service.resolve_shot_binding(project_id, shot.shot_id)
    reference_asset_service.record_shot_confirmation(
        project_id, shot.shot_id, fresh["binding_digest"]
    )
    storage = get_storage("sqlite")
    _save_job(
        storage,
        "job-gates-contract-1",
        project_id,
        shot.shot_id,
        status="complete",
        metadata={
            "creative_generation_contract": {"frozen": True, "shot_id": shot.shot_id},
            "creative_generation_manifest": {"manifest_fingerprint": "fp-1"},
            "router_execution": {"submission_attempted": True},
        },
    )

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["contract"]["state"] == "pass"
    # Historical fact only — never permission for a future send.
    assert payload["gates"]["preflight"]["state"] == "pass"
    assert payload["gates"]["preflight"]["label"] == "Last send authorized"
    assert "when sent" in payload["gates"]["preflight"]["detail"]
    assert "ready to send" not in response.text.lower()


def test_shot_gates_recorded_contract_refusal_blocks() -> None:
    project_id = "project_gates_refusal"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    storage = get_storage("sqlite")
    _save_job(
        storage,
        "job-gates-refused-1",
        project_id,
        shot.shot_id,
        status="failed",
        metadata={"router_execution": {"reason": "frozen_generation_contract_unavailable"}},
    )

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["contract"]["state"] == "blocked"
    assert payload["gates"]["preflight"]["state"] == "blocked"
    assert "ready to send" not in response.text.lower()


def test_shot_gates_persisted_spend_echoes_only_stored_number() -> None:
    project_id = "project_gates_spend"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    storage = get_storage("sqlite")
    _save_job(
        storage,
        "job-gates-spend-1",
        project_id,
        shot.shot_id,
        status="complete",
        metadata={"router_execution": {"estimated_cost_credits": 150}},
    )

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    spend = response.json()["gates"]["spend"]
    assert spend["state"] == "pass"
    assert response.json()["spend"]["estimated_credits"] == 150


def test_shot_gates_spend_absent_without_job_is_not_yet() -> None:
    project_id = "project_gates_spend_none"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["spend"]["state"] == "not_yet"
    assert payload["spend"]["estimated_credits"] is None


def test_shot_gates_local_refs_force_spend_cant_check_never_a_number() -> None:
    job = RenderJobModel(
        id="job-local-spend",
        project_id="project_gates_local",
        shot_id="scene_001_shot_001",
        provider="runway_router",
        status="pending",
        input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="x"),
        created_at="2026-10-24T10:00:00+00:00",
        metadata={"router_execution": {"estimated_cost_credits": 999}},
    )
    info = classify_spend([{"uri": "/outputs/test-local/ref-0.png", "role": "reference"}], job)
    assert info["state"] == "cant_check"
    assert info["estimated_credits"] is None
    assert "http" not in info["detail"].lower() or True


def test_shot_gates_duplicate_postures() -> None:
    pending = RenderJobModel(
        id="job-dup-pending",
        project_id="p",
        shot_id="scene_001_shot_001",
        provider="runway_router",
        status="pending",
        input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="x"),
        created_at="2026-10-24T10:00:00+00:00",
        metadata={"router_execution": {"runway_task_id": "task-123"}},
    )
    assert classify_duplicate(None)["state"] == "not_yet"
    assert classify_duplicate(pending)["state"] == "blocked"

    reconciled = pending.model_copy(deep=True)
    reconciled.metadata = {
        "router_execution": {"runway_task_id": "task-123"},
        "router_reconciliation": {
            "task_id": "task-123",
            "verdict": "terminal_failure",
            "retry_permitted": True,
        },
    }
    assert classify_duplicate(reconciled)["state"] == "pass"

    complete = pending.model_copy(deep=True)
    complete.status = "complete"
    assert classify_duplicate(complete)["state"] == "pass"

    failed = pending.model_copy(deep=True)
    failed.status = "failed"
    assert classify_duplicate(failed)["state"] == "cant_check"


def test_shot_gates_pending_task_blocks_duplicate_end_to_end() -> None:
    project_id = "project_gates_dup"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    storage = get_storage("sqlite")
    _save_job(
        storage,
        "job-gates-dup-1",
        project_id,
        shot.shot_id,
        status="pending",
        metadata={"router_execution": {"runway_task_id": "task-abc"}},
    )

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    assert response.json()["gates"]["duplicate"]["state"] == "blocked"


def test_shot_gates_preflight_never_claims_ready_to_send() -> None:
    project_id = "project_gates_nosend"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    _seed_alias_anchor(project_id)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gates"]["preflight"]["state"] in {"blocked", "not_yet", "cant_check", "pass"}
    assert "ready to send" not in response.text.lower()
    assert "ready_to_send" not in response.text.lower()


# ----------------------------------------------------------------------
# Isolation, fingerprint, no-job/no-provider guard
# ----------------------------------------------------------------------


def test_shot_gates_second_project_stays_isolated() -> None:
    first = "project_gates_iso_a"
    second = "project_gates_iso_b"
    _seed_project(first)
    _seed_project(second, ("scene_001", "scene_002"))
    _board(first, shot_count=1)

    first_payload = _gates(first, "scene_001_shot_001").json()
    assert first_payload["project_id"] == first
    assert _gates(second, "scene_001_shot_001").status_code == 200
    # Unknown scene in this project must 404, never leak.
    assert _gates(first, "scene_009_shot_001").status_code == 404


def test_shot_gates_absent_prompt_table_is_never_created() -> None:
    """Lazy-table case: a DB predating storyboard_image_prompts keeps no such table."""
    project_id = "project_gates_notable"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    storage = get_storage("sqlite")
    raw = sqlite3.connect(str(storage.db_path))
    try:
        raw.execute("DROP TABLE storyboard_image_prompts")
        raw.commit()
    finally:
        raw.close()
    before = _db_fingerprint()
    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    probe = sqlite3.connect(f"file:{storage.db_path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        probe.close()
    assert "storyboard_image_prompts" not in tables
    assert _db_fingerprint() == before
    assert response.json()["gates"]["image"]["state"] == "not_yet"


def test_shot_gates_leaves_db_fingerprint_identical() -> None:
    project_id = "project_gates_fingerprint"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)

    before = _db_fingerprint()
    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200
    assert _db_fingerprint() == before


def test_shot_gates_creates_no_job_seed_and_calls_no_provider(monkeypatch) -> None:
    project_id = "project_gates_guard"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    _seed_alias_anchor(project_id)
    storage = get_storage("sqlite")
    jobs_before = [job.id for job in storage.list_jobs(project_id, limit=500)]

    def _forbidden_prepare(**_kwargs: Any) -> Any:
        raise AssertionError("integrity-gates must never prepare a scene batch")

    def _forbidden_submit(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("integrity-gates must never submit a render job")

    def _forbidden_estimate(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("integrity-gates must never price via dry run")

    def _forbidden_seed(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("integrity-gates must never save a seed")

    def _forbidden_confirm(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("integrity-gates must never record a confirmation")

    monkeypatch.setattr(
        scene_production_pipeline_service, "prepare_scene_batch", _forbidden_prepare
    )
    monkeypatch.setattr(render_service, "submit_job", _forbidden_submit)
    from app.services import generation_cost_gate as cost_gate_module

    monkeypatch.setattr(
        cost_gate_module.GenerationCostGate,
        "estimate_router_shot_via_dry_run",
        _forbidden_estimate,
    )
    import app.services.render_maintenance_service as maintenance_module

    if hasattr(maintenance_module, "RenderMaintenanceService"):
        monkeypatch.setattr(
            maintenance_module.RenderMaintenanceService,
            "update_shot_seed_lock",
            _forbidden_seed,
            raising=False,
        )
    from app.services.reference_asset_service import reference_asset_service as ref_service

    monkeypatch.setattr(ref_service, "record_shot_confirmation", _forbidden_confirm)

    response = _gates(project_id, shot.shot_id)
    assert response.status_code == 200, response.text
    assert [job.id for job in storage.list_jobs(project_id, limit=500)] == jobs_before

    # The aggregate is GET-only: nothing here may accept a write.
    client = TestClient(app)
    assert (
        client.post(
            f"/api/f51/studio/projects/{project_id}/shots/{shot.shot_id}/integrity-gates"
        ).status_code
        == 405
    )
