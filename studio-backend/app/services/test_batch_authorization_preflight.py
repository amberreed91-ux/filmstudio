"""Fail-closed multi-shot batch authorization preflight (R4.1A).

Proves the all-or-nothing guarantee: every required shot binding passes
preflight before the system creates any job for the batch; if any shot
fails, zero jobs are created. Covers all 14 required safety properties
using isolated storage + fake pipeline services. No providers, no renders.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from app.services import render as render_module
from app.services.generation_contract import freeze_generation_contract
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
from app.services.test_scene_production_pipeline_service import (
    FakeAudioService,
    FakeRenderService,
    FakeStitchingService,
    _gated_pipeline,
    _project,
)
from conftest import run_async


def _pipeline(tmp_path: Path, **kwargs):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    render = FakeRenderService(outputs_dir)
    service = _gated_pipeline(
        tmp_path,
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        **kwargs,
    )
    return service, render


def _forbidden_adapter(monkeypatch: pytest.MonkeyPatch):
    def _forbidden(provider, config):
        raise AssertionError("preflight rejection must not reach a provider adapter")

    monkeypatch.setattr(render_module, "get_adapter", _forbidden)


def _synthetic_entry(shot_id: str, binding: list, manifest_provider: str = "") -> dict:
    return {
        "shot_id": shot_id,
        "reference_binding": deepcopy(binding),
        "manifest_provider": manifest_provider,
        "blockers": [],
        "generation_contract": None,
        "reference_projection_authorization": None,
    }


def _synthetic_manifest(entries: list) -> dict:
    return {
        "shots": [
            {"shot_id": entry["shot_id"], "reference_binding": deepcopy(entry["reference_binding"])}
            for entry in entries
        ],
        "manifest_fingerprint": "fp-synthetic",
    }


def _binding_row(ref_id: str, target_type: str, target_id: str, uri: str, role: str = "reference") -> dict:
    return {
        "ref_id": ref_id,
        "uri": uri,
        "target_type": target_type,
        "target_id": target_id,
        "role": role,
        "category": "",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "character_face" if target_type == "character" else "environment",
    }


def _frozen_record(shot_id: str, rows: list) -> dict:
    contract_rows = [
        {
            "uri": row["uri"],
            "studio_role": row.get("role") or "reference",
            "source": "canonical_reference_binding",
            "ref_id": row.get("ref_id") or "",
            "target_type": row.get("target_type") or "",
            "target_id": row.get("target_id") or "",
            "category": row.get("category") or "",
            "canonical": bool(row.get("canonical")),
            "approval_state": row.get("approval_state") or "approved",
            "source_kind": row.get("source_kind") or "confirmed",
            "kind": row.get("kind") or "",
        }
        for row in rows
    ]
    frozen = freeze_generation_contract(
        shot_id=shot_id, prompt="test prompt", reference_assets=contract_rows, parameters={}
    )
    return frozen.to_record()


def _failed_by_code(report: dict, code: str) -> list:
    return [row for row in report["shots"] if not row["ok"] and row["failure_code"] == code]


# ── 1. All shots pass: execution proceeds on the preflighted bindings ──────

def test_valid_batch_passes_preflight_and_generates(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=_noop_entries(service, tmp_path),
        shot_manifest=_noop_manifest(service, tmp_path),
        expected_digests=dict(digests),
    )
    assert report["ready"] is True
    assert report["failed_count"] == 0
    assert all(row["digest"] == "verified" for row in report["shots"])

    result = run_async(service.generate_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=_project(),
        expected_reference_binding_digests=dict(digests),
    ))
    assert result["status"] == "complete"
    assert [call["shot_id"] for call in render.created] == SHOT_IDS


def _noop_entries(service, tmp_path):
    batch = service.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=_project()
    )
    return batch["entries"]


def _noop_manifest(service, tmp_path):
    batch = service.prepare_scene_batch(
        project_id=PROJECT_ID, scene_id=SCENE_ID, project=_project()
    )
    return batch["manifest"]


# ── 2/3/4. First / middle / final shot fails: zero jobs ────────────────────

def test_first_shot_stale_digest_creates_zero_jobs(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    _forbidden_adapter(monkeypatch)
    digests = _proposal_digests()
    digests[SHOT_IDS[0]] = "0" * 64

    with pytest.raises(ValidationError, match="stale"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=digests,
        ))

    assert render.created == []
    assert render.jobs == {}


def test_middle_shot_failure_rejects_whole_batch(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    binding = fresh["binding"]
    middle_id = "scene_001_shot_003"
    entries = [
        _synthetic_entry(SHOT_IDS[0], binding),
        _synthetic_entry(middle_id, binding),
        _synthetic_entry(SHOT_IDS[1], binding),
    ]
    manifest = _synthetic_manifest(entries)
    digests = {
        SHOT_IDS[0]: fresh["binding_digest"],
        middle_id: "0" * 64,
        SHOT_IDS[1]: fresh["binding_digest"],
    }

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=entries,
        shot_manifest=manifest,
        expected_digests=digests,
    )

    assert report["ready"] is False
    assert report["shot_count"] == 3
    assert [row["shot_id"] for row in report["shots"]] == [SHOT_IDS[0], middle_id, SHOT_IDS[1]]
    assert report["shots"][0]["ok"] is True
    assert report["shots"][2]["ok"] is True
    assert report["shots"][1]["ok"] is False
    assert report["shots"][1]["failure_code"] == "confirmed_reference_binding_stale"


def test_final_shot_stale_digest_creates_zero_jobs(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()
    digests[SHOT_IDS[-1]] = "0" * 64
    before = deepcopy(render.created)

    with pytest.raises(ValidationError, match="stale"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=digests,
        ))

    assert render.created == before == []
    # Regression: the valid early shot left no partial job behind.
    assert not [call for call in render.created if call["shot_id"] == SHOT_IDS[0]]


# ── 5/10. Over-capacity binding rejected before job creation ───────────────

def _capacity_rows(count: int) -> list:
    # Pipeline-realistic studio roles: character anchors are `face`, the
    # setting anchor is `environment` (R4.5 session A, owner-authorized).
    rows = [
        _binding_row(f"ref-face-{index}", "character", "char-dre", f"https://assets.example.test/dre-{index}.png", role="face")
        for index in range(count - 1)
    ]
    rows.append(_binding_row("ref-office", "setting", "set-office", "https://assets.example.test/office.png", role="environment"))
    return rows


def test_over_capacity_binding_rejected_with_structured_report(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    rows = _capacity_rows(6)
    shot_id = SHOT_IDS[0]
    entry = _synthetic_entry(shot_id, rows, manifest_provider="runway_router")
    entry["generation_contract"] = _frozen_record(shot_id, rows)

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is False
    failed = _failed_by_code(report, "unsupported_reference_capacity")
    assert len(failed) == 1
    assert failed[0]["failure_category"] == "reference_capacity"
    assert failed[0]["policy_version"] == "v2"
    assert "4" in (failed[0]["message"] or "")


def _retarget_batch_references(batch, rows_by_shot: dict):
    """Retarget every batch layer to a new per-shot binding, consistently.

    Coverage, entries, frozen contracts, manifest rows, and the manifest
    fingerprint are all refreshed together so the establish frozen-contract
    verification still passes and only the authorization preflight judges
    the new bindings.
    """
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.shot_manifest import recompute_manifest_fingerprint

    coverage = batch["scene_coverage"]
    # Pass 1: coverage carries the new approved bindings first — frozen
    # contracts snapshot the whole coverage object at freeze time.
    for entry in batch["entries"]:
        shot_id = str(entry.get("shot_id"))
        rows = deepcopy(rows_by_shot[shot_id])
        cov_row = next(row for row in coverage.get("shots", []) if row.get("shot_id") == shot_id)
        cov_row["approved_reference_bindings"] = deepcopy(rows)
        cov_row["approved_reference_ids"] = [row["ref_id"] for row in rows]
    # Pass 2: entries + frozen contracts.
    for entry in batch["entries"]:
        shot_id = str(entry.get("shot_id"))
        rows = deepcopy(rows_by_shot[shot_id])
        entry["reference_binding"] = deepcopy(rows)
        entry["references"] = [row["uri"] for row in rows]
        entry["reference_roles"] = [row["role"] for row in rows]
        entry["manifest_provider"] = "runway_router"
        entry["generation_settings"]["frozen_reference_binding"] = deepcopy(rows)
        contract_rows = [
            {
                "uri": row["uri"], "studio_role": row.get("role") or "reference",
                "source": "canonical_reference_binding",
                "ref_id": row.get("ref_id") or "", "target_type": row.get("target_type") or "",
                "target_id": row.get("target_id") or "", "category": row.get("category") or "",
                "canonical": True, "approval_state": "approved",
                "source_kind": row.get("source_kind") or "confirmed", "kind": row.get("kind") or "",
            }
            for row in rows
        ]
        frozen = freeze_generation_contract(
            shot_id=shot_id,
            prompt=entry["prompt"],
            reference_assets=contract_rows,
            parameters=entry.get("generation_settings") or {},
            dialogue_handoff=entry.get("dialogue_handoff"),
            scene_coverage=entry.get("scene_coverage"),
            scene_coverage_shot=entry.get("shot_coverage"),
        )
        entry["generation_contract"] = frozen.to_record()
        entry["generation_contract_digest"] = frozen.creative_digest()
        manifest_row = next(
            row for row in batch["manifest"]["shots"] if row.get("shot_id") == shot_id
        )
        manifest_row["reference_binding"] = deepcopy(rows)
        manifest_row["references"] = [row["uri"] for row in rows]
        manifest_row["reference_roles"] = [row["role"] for row in rows]
    # Pass 3: fingerprint over the final manifest; entries + frozen follow.
    new_fingerprint = recompute_manifest_fingerprint(batch["manifest"])
    batch["manifest"]["manifest_fingerprint"] = new_fingerprint
    for entry in batch["entries"]:
        entry["manifest_fingerprint"] = new_fingerprint
        frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        frozen = replace(frozen, manifest_fingerprint=new_fingerprint)
        entry["generation_contract"] = frozen.to_record()
        entry["generation_contract_digest"] = frozen.creative_digest()


def test_over_capacity_batch_creates_zero_jobs_end_to_end(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _forbidden_adapter(monkeypatch)

    def _over_capacity(batch):
        rows = [
            _binding_row("ref-dre-face", "character", "char-dre", "https://assets.example.test/dre.png", role="face"),
            _binding_row("ref-office", "setting", "set-office", "https://assets.example.test/office.png", role="environment"),
        ] + [
            _binding_row(
                f"ref-dre-face-{index}", "character", "char-dre",
                f"https://assets.example.test/dre-{index}.png",
                role="face",
            )
            for index in range(2, 6)
        ]
        _retarget_batch_references(batch, {entry["shot_id"]: rows for entry in batch["entries"]})

    service, render = _pipeline(tmp_path, prepared_mutator=_over_capacity)
    digests = _proposal_digests()

    with pytest.raises(ValidationError) as exc_info:
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=dict(digests),
        ))

    assert exc_info.value.metadata.get("failure_type") == "batch_authorization_preflight_rejected"
    authorization = exc_info.value.metadata.get("authorization") or {}
    assert authorization.get("ready") is False
    assert _failed_by_code(authorization, "unsupported_reference_capacity")
    assert render.created == []
    assert render.jobs == {}


def test_valid_router_batch_passes_preflight(tmp_path, monkeypatch):
    """Guard against an over-strict gate: a normalized Router batch passes."""
    _seed(tmp_path, monkeypatch)

    def _router_normalized(batch):
        rows = [
            _binding_row("ref-dre-face", "character", "char-dre", "https://assets.example.test/dre.png", role="face"),
            _binding_row("ref-office", "setting", "set-office", "https://assets.example.test/office.png", role="environment"),
        ]
        _retarget_batch_references(batch, {entry["shot_id"]: rows for entry in batch["entries"]})

    service, render = _pipeline(tmp_path, prepared_mutator=_router_normalized)
    digests = _proposal_digests()

    result = run_async(service.generate_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=_project(),
        provider="runway_router",
        expected_reference_binding_digests=dict(digests),
    ))
    assert result["status"] == "complete"
    assert [call["shot_id"] for call in render.created] == SHOT_IDS


# ── 6. Stale / mismatched digest ───────────────────────────────────────────

def test_wrong_shot_digest_rejected_before_any_job_creation(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()
    digests[SHOT_IDS[0]] = ReferenceAssetService().resolve_shot_binding(
        PROJECT_ID, OTHER_SHOT_ID
    )["binding_digest"]

    with pytest.raises(ValidationError, match="stale"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=digests,
        ))

    assert render.created == []


# ── 7. Invalid / unauthorized references ───────────────────────────────────

def test_unapproved_reference_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    rows = deepcopy(fresh["binding"])
    rows[0] = {**rows[0], "approval_state": "candidate"}
    entry = _synthetic_entry(SHOT_IDS[0], rows)

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is False
    failed = _failed_by_code(report, "unapproved_reference")
    assert len(failed) == 1
    assert failed[0]["failure_category"] == "reference_authorization"


# ── 8. Invalid / ambiguous setting authority ───────────────────────────────

def test_ambiguous_setting_authority_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    rows = deepcopy(fresh["binding"]) + [
        _binding_row("ref-office-2", "setting", "set-office", "https://assets.example.test/office-2.png")
    ]
    entry = _synthetic_entry(SHOT_IDS[0], rows)

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is False
    failed = _failed_by_code(report, "ambiguous_setting_authority")
    assert len(failed) == 1
    assert failed[0]["failure_category"] == "setting_authority"


def test_missing_setting_authority_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    rows = [row for row in fresh["binding"] if row.get("target_type") != "setting"]
    assert rows
    entry = _synthetic_entry(SHOT_IDS[0], rows)

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is False
    assert _failed_by_code(report, "missing_setting_authority")


# ── 9. Scene 002 projection v1 preserved ───────────────────────────────────

def test_scene002_v1_authorization_proof_preserved(tmp_path, monkeypatch):
    from app.services.reference_validation import SCENE002_PROJECT_ID, reference_binding_digest

    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    rows = _capacity_rows(4)[:4] + [
        _binding_row("ref-extra", "character", "char-dre", "https://assets.example.test/extra.png")
    ]
    authorization = {"frozen_reference_binding_sha256": reference_binding_digest(rows)}
    entry = _synthetic_entry("scene_002_shot_001", rows)
    entry["reference_projection_authorization"] = authorization

    report = service.preflight_batch_authorization(
        project_id=SCENE002_PROJECT_ID,
        scene_id="scene_002",
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is True
    assert report["shots"][0]["policy_version"] == "v1"


def test_scene002_v1_tampered_proof_rejected(tmp_path, monkeypatch):
    from app.services.reference_validation import SCENE002_PROJECT_ID

    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    entry = _synthetic_entry("scene_002_shot_001", _capacity_rows(4))
    entry["reference_projection_authorization"] = {"frozen_reference_binding_sha256": "0" * 64}

    report = service.preflight_batch_authorization(
        project_id=SCENE002_PROJECT_ID,
        scene_id="scene_002",
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is False
    assert _failed_by_code(report, "missing_reference_authority")


# ── 11. No rejection path touches jobs or providers ────────────────────────

def test_preflight_itself_creates_no_jobs_and_contacts_no_provider(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _handoff_pipeline(tmp_path)
    _forbidden_adapter(monkeypatch)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    entry = _synthetic_entry(SHOT_IDS[0], deepcopy(fresh["binding"]))

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests={SHOT_IDS[0]: fresh["binding_digest"]},
    )

    assert report["ready"] is True
    assert render.created == []


def test_rejected_batch_leaves_entries_untouched(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()
    digests[SHOT_IDS[1]] = "0" * 64

    with pytest.raises(ValidationError):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=digests,
        ))

    assert render.created == []
    assert render.jobs == {}


# ── 13. Duplicate / malformed shot identifiers ─────────────────────────────

def test_duplicate_shot_ids_rejected_and_fully_reported(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    entries = [
        _synthetic_entry(SHOT_IDS[0], deepcopy(fresh["binding"])),
        _synthetic_entry(SHOT_IDS[0], deepcopy(fresh["binding"])),
    ]

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=entries,
        shot_manifest=_synthetic_manifest(entries),
        expected_digests=None,
    )

    assert report["ready"] is False
    # No shot is skipped: every entry receives its own structured result.
    assert len(report["shots"]) == 2
    assert _failed_by_code(report, "duplicate_shot_id")


def test_malformed_shot_ids_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    entries = [{"shot_id": ""}, {"shot_id": None}, {"no_shot_id": True}]

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=entries,
        shot_manifest=_synthetic_manifest([]),
        expected_digests=None,
    )

    assert report["ready"] is False
    assert len(_failed_by_code(report, "malformed_shot_id")) == 3


def test_upstream_blocked_shot_reported_without_invented_failures(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    entry = _synthetic_entry(SHOT_IDS[0], [])
    entry["blockers"] = ["reference gate: no approved canonical environment reference is available"]

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([entry]),
        expected_digests=None,
    )

    assert report["ready"] is False
    assert _failed_by_code(report, "upstream_blockers")


def test_missing_manifest_row_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, _ = _handoff_pipeline(tmp_path)
    fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    entry = _synthetic_entry(SHOT_IDS[0], deepcopy(fresh["binding"]))

    report = service.preflight_batch_authorization(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        entries=[entry],
        shot_manifest=_synthetic_manifest([]),
        expected_digests=None,
    )

    assert report["ready"] is False
    assert _failed_by_code(report, "missing_generation_contract")
