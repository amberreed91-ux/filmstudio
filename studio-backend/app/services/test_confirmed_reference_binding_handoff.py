"""Confirmed reference binding handoff (Phase C4).

Covers the server-verified connection between a Production Desk
per-shot binding proposal and the existing authorized job creation path:

* a valid Desk proposal traverses generate_scene and reaches job creation
  with the authorized references;
* the server never trusts the client digest or any client reference list —
  only a freshly resolved server binding decides;
* a reference revoked or changed after resolution is rejected;
* wrong-project and wrong-shot bindings are rejected;
* a rejected request creates no jobs and never invokes the adapter;
* the created job retains the binding digest and reference traceability;
* preview and confirmation alone create no jobs and invoke no providers.

Isolated storage + fake pipeline services only. No providers, no renders.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services import render as render_module
from app.services.reference_asset_service import ReferenceAssetService
from app.services.reference_validation import reference_binding_digest
from app.services.stability import ValidationError
from app.services.test_scene_production_pipeline_service import (
    _gated_pipeline,
    _project,
    FakeAudioService,
    FakeRenderService,
    FakeStitchingService,
)
from conftest import run_async

PROJECT_ID = "project_test"
SCENE_ID = "scene_001"
SHOT_IDS = ["scene_001_shot_001", "scene_001_shot_002"]
OTHER_SHOT_ID = "scene_002_shot_001"
DRE_FACE_URL = "https://assets.example.test/dre.png"
OFFICE_URL = "https://assets.example.test/office.png"
ANNEX_URL = "https://assets.example.test/annex.png"


def _storage(tmp_path: Path) -> DatabaseStorage:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return DatabaseStorage(str(db_dir))


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DatabaseStorage:
    """Seed the registry rows behind the sibling pipeline fixture's shots.

    Mirrors the hardcoded noop-batch references (Dre's face + office
    setting) as approved canonical registry rows so the authoritative
    resolver can independently re-resolve the same authorized binding.
    """
    storage = _storage(tmp_path)
    character = storage.save_character(
        PROJECT_ID,
        "Dre",
        {"visual_prompt_summary": "short dark hair, grey coat"},
    )

    from copy import deepcopy

    def fake_project(project_id: str):
        if project_id != PROJECT_ID:
            return None
        project = _project()
        # A second scene with a distinct setting gives scene_002 shots a
        # genuinely different authorized binding for wrong-shot coverage.
        project["execution_summary"]["scenes"].append({
            "scene_id": "scene_002",
            "description": "Dre waits in the annex.",
            "characters": ["Dre"],
            "setting_id": "set-annex",
        })
        return deepcopy(project)

    monkeypatch.setattr(
        "app.services.project_store.project_store.get_project",
        fake_project,
    )
    # The pipeline constructs ReferenceAssetService without explicit storage;
    # point the service-level fallback at this isolated database.
    monkeypatch.setattr(
        "app.services.reference_asset_service.get_storage",
        lambda name="sqlite": storage,
    )
    storage.save_universe_node({
        "node_id": "set-office",
        "project_id": PROJECT_ID,
        "node_type": "location",
        "name": "Office",
        "first_scene": SCENE_ID,
        "last_scene": SCENE_ID,
    })
    storage.save_reference_asset({
        "ref_id": "ref-dre-face",
        "project_id": PROJECT_ID,
        "target_type": "character",
        "target_id": character["id"],
        "kind": "character_face",
        "image_url": DRE_FACE_URL,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    storage.save_reference_asset({
        "ref_id": "ref-office",
        "project_id": PROJECT_ID,
        "target_type": "setting",
        "target_id": "set-office",
        "kind": "environment",
        "image_url": OFFICE_URL,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    storage.save_universe_node({
        "node_id": "set-annex",
        "project_id": PROJECT_ID,
        "node_type": "location",
        "name": "Annex",
        "first_scene": "scene_002",
        "last_scene": "scene_002",
    })
    storage.save_reference_asset({
        "ref_id": "ref-annex",
        "project_id": PROJECT_ID,
        "target_type": "setting",
        "target_id": "set-annex",
        "kind": "environment",
        "image_url": ANNEX_URL,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    return storage


def _proposal_digests() -> dict[str, str]:
    return {
        shot_id: ReferenceAssetService().resolve_shot_binding(PROJECT_ID, shot_id)["binding_digest"]
        for shot_id in SHOT_IDS
    }


def _pipeline(tmp_path: Path) -> tuple:
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    render = FakeRenderService(outputs_dir)
    service = _gated_pipeline(
        tmp_path,
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
    )
    return service, render


def test_valid_desk_proposal_traverses_server_authoritative_path(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()

    result = run_async(service.generate_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=_project(),
        expected_reference_binding_digests=dict(digests),
    ))

    assert result["status"] == "complete"
    assert [call["shot_id"] for call in render.created] == SHOT_IDS
    # The adapter-bound payloads carry exactly the freshly authorized
    # references for each shot — same identities, same URIs, same order,
    # no substitution. (Role vocabulary is owned by the prepared contract,
    # which the handoff never rewrites.)
    for shot_id in SHOT_IDS:
        fresh = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, shot_id)
        created = next(row for row in render.created if row["shot_id"] == shot_id)
        assert created["reference_assets"] == [row["uri"] for row in fresh["binding"]]
        assert [row["ref_id"] for row in created["frozen_reference_binding"]] == [
            row["ref_id"] for row in fresh["binding"]
        ]
        assert [row["uri"] for row in created["frozen_reference_binding"]] == [
            row["uri"] for row in fresh["binding"]
        ]


def test_tampered_digest_rejected_before_any_job_creation(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
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


def test_revoked_reference_after_resolve_is_rejected(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()

    storage.delete_reference_asset("ref-dre-face", PROJECT_ID)

    with pytest.raises(ValidationError, match="stale|cannot be verified"):
        run_async(service.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=_project(),
            expected_reference_binding_digests=digests,
        ))

    assert render.created == []
    assert render.jobs == {}


def test_wrong_shot_binding_is_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service = ReferenceAssetService()
    other_digest = service.resolve_shot_binding(PROJECT_ID, OTHER_SHOT_ID)["binding_digest"]
    assert other_digest != service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding_digest"]
    with pytest.raises(ValidationError, match="stale"):
        service.verify_confirmed_binding(PROJECT_ID, SHOT_IDS[0], other_digest)


def test_wrong_shot_digest_rejected_before_any_job_creation(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)
    digests = _proposal_digests()
    # A digest that is valid for a scene_002 shot proves nothing about a
    # scene_001 shot, even though both scenes feature Dre.
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
    assert render.jobs == {}


def test_wrong_project_binding_is_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service = ReferenceAssetService()
    digest = service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding_digest"]
    with pytest.raises(ValidationError, match="verif"):
        service.verify_confirmed_binding("other-project", SHOT_IDS[0], digest)


def test_server_does_not_trust_client_digest_or_reference_list(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service = ReferenceAssetService()

    # An attacker-shaped binding with a self-consistent digest is still
    # rejected: the digest must match current canonical truth, not itself.
    forged = [
        {**row, "uri": "https://cdn.example.test/attacker.png"}
        for row in service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding"]
    ]
    with pytest.raises(ValidationError, match="stale"):
        service.verify_confirmed_binding(
            PROJECT_ID, SHOT_IDS[0], reference_binding_digest(forged)
        )

    # An accepted confirmation returns only server-resolved data.
    digest = service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding_digest"]
    assert service.verify_confirmed_binding(PROJECT_ID, SHOT_IDS[0], digest) == \
        service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])


def test_created_job_carries_binding_digest_and_version_traceability(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    service, render = _pipeline(tmp_path)

    result = run_async(service.generate_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=_project(),
        expected_reference_binding_digests=_proposal_digests(),
    ))

    manifest = result["shot_manifest"]
    for shot_id in SHOT_IDS:
        created = next(row for row in render.created if row["shot_id"] == shot_id)
        manifest_row = next(row for row in manifest["shots"] if row["shot_id"] == shot_id)
        # The frozen binding reaches job creation byte-identical to the
        # manifest-frozen selection: the digest is retained in transit.
        assert reference_binding_digest(created["frozen_reference_binding"]) == \
            reference_binding_digest(manifest_row["reference_binding"])
        assert [row["ref_id"] for row in created["frozen_reference_binding"]] == \
            ["ref-dre-face", "ref-office"]
        # Version traceability travels with the creation call.
        assert created["creative_manifest_fingerprint"] == manifest["manifest_fingerprint"]
        assert created["generation_context_id"] == manifest_row.get("generation_context_id", "")


def test_preview_and_confirmation_create_no_jobs_and_invoke_no_providers(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(render_module, "_storage", storage)

    def _forbidden_adapter(provider, config):
        raise AssertionError("preview must not reach a provider adapter")

    monkeypatch.setattr(render_module, "get_adapter", _forbidden_adapter)

    service = ReferenceAssetService()
    first = service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    second = service.resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])
    service.verify_confirmed_binding(PROJECT_ID, SHOT_IDS[0], first["binding_digest"])

    assert first == second
    assert render_module.RenderService().list_jobs(PROJECT_ID) == []
