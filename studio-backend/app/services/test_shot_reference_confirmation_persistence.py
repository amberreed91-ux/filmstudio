"""Durable project-scoped confirmation persistence and recovery (R4.2).

Proves that explicit shot reference-binding confirmations survive reloads
and navigation, stay scoped to their exact project and shot, and are
revalidated against current production state before any generation
submission. A persisted confirmation is evidence of a previous explicit
approval - never authorization: every submission path re-resolves the
current binding, recomputes the digest with the authoritative verifier,
and runs the full R4.1A batch preflight.

Isolated storage + fake pipeline services only. No providers, no renders.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services import render as render_module
from app.services.reference_asset_service import ReferenceAssetService
from app.services.stability import ValidationError
from app.services.test_confirmed_reference_binding_handoff import (
    OTHER_SHOT_ID,
    PROJECT_ID,
    SCENE_ID,
    SHOT_IDS,
    _pipeline as _handoff_pipeline,
    _proposal_digests,
    _seed,
)
from app.services.test_scene_production_pipeline_service import _project
from conftest import run_async


def _fresh_service() -> ReferenceAssetService:
    # A new service instance against the same isolated storage (reload).
    return ReferenceAssetService()


def _stored_digests() -> dict[str, str]:
    return {
        shot_id: _fresh_service().resolve_shot_binding(PROJECT_ID, shot_id)["binding_digest"]
        for shot_id in SHOT_IDS
    }


def _record_all() -> dict[str, str]:
    recorded = {}
    for shot_id in SHOT_IDS:
        fresh = _fresh_service().resolve_shot_binding(PROJECT_ID, shot_id)
        recorded[shot_id] = _fresh_service().record_shot_confirmation(
            PROJECT_ID, shot_id, fresh["binding_digest"]
        )["confirmed_digest"]
    return recorded


def _forbid_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(provider, config):
        raise AssertionError("rejected batch must not reach a provider adapter")

    monkeypatch.setattr(render_module, "get_adapter", _forbidden)


def test_valid_confirmation_persisted_and_retrieved(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service = _fresh_service()
    fresh = service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])

    recorded = service.record_shot_confirmation(PROJECT_ID, SHOT_IDS[0], fresh["binding_digest"])

    assert recorded["status"] == "confirmed"
    assert recorded["project_id"] == PROJECT_ID
    assert recorded["shot_id"] == SHOT_IDS[0]
    assert recorded["scene_id"] == SCENE_ID
    assert recorded["confirmed_digest"] == fresh["binding_digest"]
    assert recorded["created_at"]
    assert recorded["updated_at"]


def test_confirmation_survives_new_frontend_session(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _record_all()

    # A brand-new service instance (a reloaded Desk, a fresh room) recovers
    # the same server-backed state without any transient route memory.
    recovered = _fresh_service().get_shot_confirmation(PROJECT_ID, SHOT_IDS[0])
    current = _fresh_service().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    assert recovered["status"] == "confirmed"
    assert recovered["confirmed_digest"] == current["binding_digest"]


def test_scene_recovery_after_navigation(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _record_all()

    first = _fresh_service().list_scene_confirmations(PROJECT_ID, SCENE_ID)
    assert first["count"] == 2
    assert {row["shot_id"] for row in first["confirmations"]} == set(SHOT_IDS)
    assert {row["status"] for row in first["confirmations"]} == {"confirmed"}

    # Navigate away and back: fresh instances, same recovered verdicts.
    second = _fresh_service().list_scene_confirmations(PROJECT_ID, SCENE_ID)
    assert second == first


def test_confirmation_not_reusable_across_projects(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _record_all()

    assert _fresh_service().get_shot_confirmation("project_other", SHOT_IDS[0])["status"] == "missing"
    other_digest = _fresh_service().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding_digest"]
    with pytest.raises(ValidationError, match="verif"):
        _fresh_service().record_shot_confirmation("project_other", SHOT_IDS[0], other_digest)


def test_confirmation_not_reusable_across_shots(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _record_all()

    assert _fresh_service().get_shot_confirmation(PROJECT_ID, OTHER_SHOT_ID)["status"] == "missing"
    other_digest = _fresh_service().resolve_shot_binding(PROJECT_ID, OTHER_SHOT_ID)["binding_digest"]
    with pytest.raises(ValidationError, match="stale"):
        _fresh_service().record_shot_confirmation(PROJECT_ID, SHOT_IDS[0], other_digest)


def _swap_setting_url(storage: DatabaseStorage, url: str) -> None:
    storage.delete_reference_asset("ref-office", PROJECT_ID)
    storage.save_reference_asset({
        "ref_id": "ref-office-v2",
        "project_id": PROJECT_ID,
        "target_type": "setting",
        "target_id": "set-office",
        "kind": "environment",
        "image_url": url,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })


def test_changed_binding_makes_prior_confirmation_stale(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    before = _record_all()
    assert _fresh_service().get_shot_confirmation(PROJECT_ID, SHOT_IDS[0])["status"] == "confirmed"

    _swap_setting_url(storage, "https://assets.example.test/office-v2.png")

    recovered = _fresh_service().get_shot_confirmation(PROJECT_ID, SHOT_IDS[0])
    assert recovered["status"] == "stale"
    assert recovered["confirmed_digest"] == before[SHOT_IDS[0]]
    assert recovered["current_digest"] != before[SHOT_IDS[0]]


def test_revoked_reference_fails_closed_on_revalidation(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    recorded = _record_all()
    storage.delete_reference_asset("ref-dre-face", PROJECT_ID)

    recovered = _fresh_service().get_shot_confirmation(PROJECT_ID, SHOT_IDS[0])
    assert recovered["status"] in ("stale", "unverifiable")
    with pytest.raises(ValidationError, match="stale|cannot be verified"):
        _fresh_service().record_shot_confirmation(
            PROJECT_ID, SHOT_IDS[0], recorded[SHOT_IDS[0]]
        )


def test_missing_setting_authority_blocks_required_submission(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    service, render = _handoff_pipeline(tmp_path)
    _record_all()
    storage.delete_reference_asset("ref-office", PROJECT_ID)
    _forbid_providers(monkeypatch)

    with pytest.raises(ValidationError, match="cannot be verified|stale|setting"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=_stored_digests(),
            require_persisted_confirmation=True,
        ))
    assert render.created == []
    assert render.jobs == {}


def test_missing_confirmation_blocks_required_submission(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _handoff_pipeline(tmp_path)
    _forbid_providers(monkeypatch)

    with pytest.raises(ValidationError, match="no durable reference-binding confirmation"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=_proposal_digests(),
            require_persisted_confirmation=True,
        ))
    assert render.created == []
    assert render.jobs == {}


def test_missing_confirmation_reported_per_shot_without_job_creation(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    batch = service.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=_project(),
    )
    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=deepcopy(batch["entries"]),
        shot_manifest=deepcopy(batch["manifest"]),
        expected_digests=None,
        require_persisted_confirmation=True,
    )
    assert report["ready"] is False
    assert {row["shot_id"] for row in report["shots"] if not row["ok"]} == set(SHOT_IDS)
    assert {row["failure_code"] for row in report["shots"] if not row["ok"]} == {"missing_confirmation"}


def test_tampered_confirmation_record_blocks_required_submission(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    service, render = _handoff_pipeline(tmp_path)
    _record_all()
    row = storage.get_shot_reference_confirmation(PROJECT_ID, SHOT_IDS[0])
    assert row is not None
    storage.save_shot_reference_confirmation({**row, "confirmed_digest": "f" * 64})

    assert _fresh_service().get_shot_confirmation(PROJECT_ID, SHOT_IDS[0])["status"] == "stale"
    _forbid_providers(monkeypatch)
    with pytest.raises(ValidationError, match="stale|does not match"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=_stored_digests(),
            require_persisted_confirmation=True,
        ))
    assert render.created == []
    assert render.jobs == {}


def test_carried_digest_mismatching_durable_record_blocks(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    _record_all()
    batch = service.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=_project(),
    )
    carried = _stored_digests()
    carried[SHOT_IDS[0]] = "0" * 64
    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=deepcopy(batch["entries"]),
        shot_manifest=deepcopy(batch["manifest"]),
        expected_digests=carried,
        require_persisted_confirmation=True,
    )
    assert report["ready"] is False
    failed = [row for row in report["shots"] if row["shot_id"] == SHOT_IDS[0]]
    assert len(failed) == 1 and not failed[0]["ok"]
    assert failed[0]["failure_code"] in ("confirmation_mismatch", "confirmed_reference_binding_stale")


def test_stale_blocks_until_rerecorded(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    service, render = _handoff_pipeline(tmp_path)
    _record_all()
    _swap_setting_url(storage, "https://assets.example.test/office-v2.png")
    _forbid_providers(monkeypatch)

    with pytest.raises(ValidationError, match="stale|does not match"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=_stored_digests(),
            require_persisted_confirmation=True,
        ))
    assert render.created == []

    # A new explicit confirmation of the CURRENT binding restores the path.
    for shot_id in SHOT_IDS:
        fresh = _fresh_service().resolve_shot_binding(PROJECT_ID, shot_id)
        recorded = _fresh_service().record_shot_confirmation(PROJECT_ID, shot_id, fresh["binding_digest"])
        assert recorded["status"] == "confirmed"
    monkeypatch.delattr(render_module, "get_adapter", raising=False)
    result = run_async(service.generate_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=_project(),
        expected_reference_binding_digests=_stored_digests(),
        require_persisted_confirmation=True,
    ))
    assert result["status"] == "complete"
    assert [call["shot_id"] for call in render.created] == SHOT_IDS


def test_batch_with_one_unconfirmed_shot_creates_zero_jobs(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _handoff_pipeline(tmp_path)
    fresh = _fresh_service().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    _fresh_service().record_shot_confirmation(PROJECT_ID, SHOT_IDS[0], fresh["binding_digest"])
    _forbid_providers(monkeypatch)

    with pytest.raises(ValidationError, match="no durable reference-binding confirmation"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=_proposal_digests(),
            require_persisted_confirmation=True,
        ))
    assert render.created == []
    assert render.jobs == {}


def test_read_only_paths_never_write_confirmations(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    service = _fresh_service()
    service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    assert service.get_shot_confirmation(PROJECT_ID, SHOT_IDS[0])["status"] == "missing"
    assert service.list_scene_confirmations(PROJECT_ID, SCENE_ID)["count"] == 0

    pipeline, _ = _handoff_pipeline(tmp_path)
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=_project(),
    )
    pipeline.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=deepcopy(batch["entries"]),
        shot_manifest=deepcopy(batch["manifest"]),
        expected_digests=None,
    )
    assert storage.list_shot_reference_confirmations_for_scene(PROJECT_ID, SCENE_ID) == []
    assert storage.get_shot_reference_confirmation(PROJECT_ID, SHOT_IDS[0]) is None


def test_rerecording_same_binding_refreshes_without_duplicates(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service = _fresh_service()
    fresh = service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    first = service.record_shot_confirmation(PROJECT_ID, SHOT_IDS[0], fresh["binding_digest"])
    second = service.record_shot_confirmation(PROJECT_ID, SHOT_IDS[0], fresh["binding_digest"])
    assert second["status"] == "confirmed"
    assert service.list_scene_confirmations(PROJECT_ID, SCENE_ID)["count"] == 1
    assert first["confirmed_digest"] == second["confirmed_digest"]
