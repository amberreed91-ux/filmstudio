"""Generic environment canonical authority (Phase R2.3).

Pins the explicit, server-enforced designation contract for *generic* (non
Scene 002) environment references, and the reconciliation between the creator
sync writer and the production setting resolver:

- only an explicit designation (or the creator approval the sync mirrors) can
  make an environment reference canonical;
- designation is scoped to the exact project + canonical setting entity, requires
  an approved usable environment row, and is exclusive;
- the sync writes the same target identity the resolver consumes;
- a client-supplied ``canonical`` flag can never confer authority;
- missing or ambiguous canonical authority fails closed.

Isolated temporary storage and fake clients only: no providers, no renders, no
production state, no live project data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.reference_assets import router
from app.services import reference_validation as validation
from app.services.reference_asset_service import (
    SCENE002_PROJECT_ID,
    SCENE002_SETTING_ID,
    ReferenceAssetService,
    _env_ref_id,
)
from app.services.stability import ValidationError

PROJECT = "film-generic"
SCENE = "scene_010"
SETTING = "loc-harbor"
SHOT = f"{SCENE}_shot_001"


@pytest.fixture
def storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "generic-authority"))


@pytest.fixture
def scoped(storage: DatabaseStorage, monkeypatch) -> DatabaseStorage:
    """A project whose scene resolves a real canonical setting entity.

    Mirrors the resolver's own contract: a project-scoped universe ``location``
    node whose ``first_scene``/``last_scene`` are this scene, plus the scene's
    structured ``setting_id``. Read-only fixtures; no live project is touched.
    """
    storage.save_universe_node({
        "node_id": SETTING,
        "project_id": PROJECT,
        "node_type": "location",
        "name": "Harbor",
        "first_scene": SCENE,
        "last_scene": SCENE,
    })
    monkeypatch.setattr(
        validation.project_store,
        "get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [{
                    "scene_id": SCENE,
                    "scene_name": "Harbor at dawn",
                    "setting_id": SETTING,
                    "character_ids": [],
                }]
            },
        } if project_id == PROJECT else None,
    )
    return storage


def _asset(
    ref_id: str,
    *,
    project_id: str = PROJECT,
    target_type: str = "setting",
    target_id: str = SETTING,
    kind: str = "environment",
    category: str = "wide",
    canonical: bool = False,
    approval_state: str = "approved",
    source_kind: str = "uploaded",
    image_url: str | None = None,
) -> dict:
    return {
        "ref_id": ref_id,
        "project_id": project_id,
        "target_type": target_type,
        "target_id": target_id,
        "kind": kind,
        "category": category,
        "image_url": image_url if image_url is not None else f"https://cdn.example/{ref_id}.png",
        "canonical": canonical,
        "approval_state": approval_state,
        "source_kind": source_kind,
    }


def _save_approved_previs(storage: DatabaseStorage, scene_id: str = SCENE) -> str:
    """Record one creator-approved Previs frame for a scene (the sync's input)."""
    image_path = f"/previs-assets/{PROJECT}/{scene_id}_shot_001_storyboard_qwen.png"
    storage.save_previs_image(
        PROJECT,
        scene_id,
        f"{scene_id}_shot_001",
        image_path,
        f"job_{scene_id}",
        "complete",
        "test",
        False,
    )
    # The sync reads the `approved` flag; set it directly like the
    # established creator-sync fixtures do.
    import sqlite3

    conn = sqlite3.connect(storage.db_path)
    conn.execute("UPDATE previs_images SET approved = 1 WHERE image_path = ?", (image_path,))
    conn.commit()
    conn.close()
    return image_path


def _client(storage: DatabaseStorage, monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    from app.routes import reference_assets as routes

    monkeypatch.setattr(routes, "reference_asset_service", ReferenceAssetService(storage))
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Generic designation success
# ═══════════════════════════════════════════════════════════════════════════

def test_designate_approved_environment_reference_is_canonical(scoped):
    service = ReferenceAssetService(scoped)
    scoped.save_reference_asset(_asset("ref_set_wide"))

    designated = service.designate_setting_reference_canonical(PROJECT, SETTING, "ref_set_wide")

    assert designated["ref_id"] == "ref_set_wide"
    assert bool(designated["canonical"]) is True
    assert designated["approval_state"] == "approved"
    row = scoped.get_reference_asset("ref_set_wide")
    assert bool(row["canonical"]) is True
    # The consumer's contract resolves against the exact canonical setting entity.
    references = validation._approved_setting_references(scoped, project_id=PROJECT, setting_id=SETTING)
    assert [item["ref_id"] for item in references] == ["ref_set_wide"]


def test_designation_requires_the_setting_entity_to_resolve(storage, monkeypatch):
    """A scene-labelled or phantom setting target can never receive authority."""
    monkeypatch.setattr(validation.project_store, "get_project", lambda project_id: None)
    service = ReferenceAssetService(storage)
    storage.save_reference_asset(_asset("ref_set_orphan", target_id="scene_010"))

    with pytest.raises(ValidationError) as exc:
        service.designate_setting_reference_canonical(PROJECT, "scene_010", "ref_set_orphan")
    assert exc.value.metadata["failure_type"] == "setting_identity_unproven"
    assert bool(storage.get_reference_asset("ref_set_orphan")["canonical"]) is False


def test_designation_is_exclusive_and_clears_competing_canonical_anchor(scoped):
    service = ReferenceAssetService(scoped)
    scoped.save_reference_asset(_asset("ref_set_first", canonical=True))
    scoped.save_reference_asset(_asset("ref_set_second"))

    service.designate_setting_reference_canonical(PROJECT, SETTING, "ref_set_second")

    assert bool(scoped.get_reference_asset("ref_set_second")["canonical"]) is True
    assert bool(scoped.get_reference_asset("ref_set_first")["canonical"]) is False
    references = validation._approved_setting_references(scoped, project_id=PROJECT, setting_id=SETTING)
    assert [item["ref_id"] for item in references] == ["ref_set_second"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed matrix
# ═══════════════════════════════════════════════════════════════════════════

def test_designation_fails_closed_for_ineligible_references(scoped):
    service = ReferenceAssetService(scoped)
    ineligible = [
        ("ref_candidate", _asset("ref_candidate", approval_state="candidate")),
        ("ref_rejected", _asset("ref_rejected", approval_state="rejected")),
        ("ref_wrong_kind", _asset("ref_wrong_kind", kind="character_face")),
        ("ref_wrong_setting", _asset("ref_wrong_setting", target_id="loc-elsewhere")),
        ("ref_wrong_target_type", _asset("ref_wrong_target_type", target_type="character", target_id="maya")),
        ("ref_unusable", _asset("ref_unusable", image_url="/tmp/not-a-served-asset.png")),
        ("ref_foreign", _asset("ref_foreign", project_id="film-other")),
    ]
    for _ref_id, row in ineligible:
        scoped.save_reference_asset(row)

    for ref_id, _row in ineligible:
        with pytest.raises((ValueError, LookupError)):
            service.designate_setting_reference_canonical(PROJECT, SETTING, ref_id)
        # No ineligible row is ever promoted, and the row itself is otherwise untouched.
        stored = scoped.get_reference_asset(ref_id)
        assert bool(stored["canonical"]) is False, ref_id
        assert stored["approval_state"] == _row["approval_state"], ref_id

    scoped.save_reference_asset(_asset("ref_approved_anchor", canonical=True))
    with pytest.raises(LookupError):
        service.designate_setting_reference_canonical(PROJECT, SETTING, "ref_missing")
    # A failed designation leaves existing canonical authority untouched.
    assert bool(scoped.get_reference_asset("ref_approved_anchor")["canonical"]) is True


def test_designation_rejects_blank_identifiers(scoped):
    service = ReferenceAssetService(scoped)
    scoped.save_reference_asset(_asset("ref_set_wide"))
    for args in (("", SETTING, "ref_set_wide"), (PROJECT, "", "ref_set_wide"), (PROJECT, SETTING, "")):
        with pytest.raises(ValueError):
            service.designate_setting_reference_canonical(*args)
    assert bool(scoped.get_reference_asset("ref_set_wide")["canonical"]) is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. Canonical target consistency between the sync writer and the consumer
# ═══════════════════════════════════════════════════════════════════════════

def test_sync_writes_the_identity_the_production_consumer_resolves(scoped):
    service = ReferenceAssetService(scoped)
    _save_approved_previs(scoped)

    result = service.sync_creator_references(PROJECT)

    assert result["environment_stills"] == 1
    ref_id = _env_ref_id(PROJECT, SCENE)
    row = scoped.get_reference_asset(ref_id)
    # The audited mismatch: the sync used to write target_id = scene_id, which no
    # consumer accepts. It must now write the canonical setting entity identity.
    assert row["target_id"] == SETTING
    assert row["target_type"] == "setting"
    assert row["approval_state"] == "approved"
    assert bool(row["canonical"]) is True
    requirements = validation.resolve_scene_reference_requirements(
        project_id=PROJECT, scene_id=SCENE, storage=scoped,
    )
    assert requirements["setting_id"] == SETTING
    assert requirements["setting_urls"] == [row["image_url"]]


def test_sync_is_idempotent_and_keeps_the_canonical_identity(scoped):
    service = ReferenceAssetService(scoped)
    _save_approved_previs(scoped)
    service.sync_creator_references(PROJECT)
    ref_id = _env_ref_id(PROJECT, SCENE)
    first = scoped.get_reference_asset(ref_id)

    # Re-sync upserts the same deterministic row in place (the count reflects
    # rows mirrored this run, not rows created): no duplicate is produced.
    assert service.sync_creator_references(PROJECT)["environment_stills"] == 1
    second = scoped.get_reference_asset(ref_id)

    assert second["ref_id"] == first["ref_id"]
    assert second["image_url"] == first["image_url"]
    assert second["target_id"] == SETTING
    assert bool(second["canonical"]) is True


def test_sync_falls_back_to_the_scene_scope_when_no_setting_entity_resolves(storage, monkeypatch):
    """Unresolvable scenes keep the historical scene-scoped row (deterministic id).

    Production already fails closed for these scenes at setting identity
    provenance, so the fallback cannot authorize anything.
    """
    monkeypatch.setattr(validation.project_store, "get_project", lambda project_id: None)
    service = ReferenceAssetService(storage)
    _save_approved_previs(storage)

    assert service.sync_creator_references(PROJECT)["environment_stills"] == 1
    row = storage.get_reference_asset(_env_ref_id(PROJECT, SCENE))
    assert row["target_id"] == SCENE
    with pytest.raises(ValidationError):
        validation.resolve_scene_reference_requirements(
            project_id=PROJECT, scene_id=SCENE, storage=storage,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Confirm endpoint hardening
# ═══════════════════════════════════════════════════════════════════════════

def test_confirm_strips_client_supplied_canonical_at_the_service(scoped):
    service = ReferenceAssetService(scoped)
    payload = _asset("proposal_abc", canonical=True)

    from app.models.consistency import ReferenceAsset

    stored = service.confirm(PROJECT, ReferenceAsset(**payload))

    assert bool(stored["canonical"]) is False
    persisted = scoped.get_reference_asset(stored["ref_id"])
    assert bool(persisted["canonical"]) is False
    assert persisted["approval_state"] == "approved"


def test_confirm_route_ignores_client_canonical_and_still_confirms(scoped, monkeypatch):
    client = _client(scoped, monkeypatch)
    from app.models.consistency import ReferenceAsset

    response = client.post(
        f"/api/f51/studio/projects/{PROJECT}/reference-assets",
        json=ReferenceAsset(**_asset("proposal_route", canonical=True)).model_dump(mode="json"),
    )

    assert response.status_code == 200
    saved = response.json()["reference_asset"]
    assert bool(saved["canonical"]) is False
    persisted = scoped.get_reference_asset(saved["ref_id"])
    assert persisted is not None
    assert bool(persisted["canonical"]) is False
    # Ordinary confirmation still works and still creates a usable row.
    assert persisted["approval_state"] == "approved"

    # The client flag conferred no authority: the setting still has no canonical anchor.
    with pytest.raises(ValidationError) as exc:
        validation.resolve_scene_reference_requirements(
            project_id=PROJECT, scene_id=SCENE, storage=scoped,
        )
    assert exc.value.metadata["failure_type"] == "canonical_setting_reference_missing"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Ambiguity protection
# ═══════════════════════════════════════════════════════════════════════════

def test_competing_canonical_anchors_fail_closed_in_the_generic_resolver(scoped):
    """Two canonical anchors for one generic setting are ambiguous, so resolution refuses."""
    scoped.save_reference_asset(_asset("ref_ambig_a", canonical=True))
    scoped.save_reference_asset(_asset("ref_ambig_b", canonical=True))

    with pytest.raises(ValidationError) as exc:
        validation.resolve_scene_reference_requirements(
            project_id=PROJECT, scene_id=SCENE, storage=scoped,
        )
    assert exc.value.metadata["failure_type"] == "canonical_setting_reference_ambiguous"

    # An explicit designation resolves the ambiguity rather than picking for the creator.
    ReferenceAssetService(scoped).designate_setting_reference_canonical(PROJECT, SETTING, "ref_ambig_b")
    requirements = validation.resolve_scene_reference_requirements(
        project_id=PROJECT, scene_id=SCENE, storage=scoped,
    )
    assert requirements["setting_urls"] == [scoped.get_reference_asset("ref_ambig_b")["image_url"]]


# ═══════════════════════════════════════════════════════════════════════════
# 6. End-to-end generic consumption through the shot resolver
# ═══════════════════════════════════════════════════════════════════════════

def test_designated_anchor_is_selected_by_the_shot_resolver(scoped):
    service = ReferenceAssetService(scoped)
    scoped.save_reference_asset(_asset("ref_set_wide"))
    scoped.save_reference_asset(_asset("ref_set_detail", category="detail"))

    service.designate_setting_reference_canonical(PROJECT, SETTING, "ref_set_detail")
    binding = service.resolve_shot_binding(PROJECT, SHOT)

    assert binding["setting_id"] == SETTING
    assert [row["ref_id"] for row in binding["binding"] if row["target_type"] == "setting"] == ["ref_set_detail"]
    assert binding["allowed_urls"] == [scoped.get_reference_asset("ref_set_detail")["image_url"]]


def test_shot_resolver_fails_closed_without_canonical_authority(scoped):
    service = ReferenceAssetService(scoped)
    scoped.save_reference_asset(_asset("ref_set_only_approved"))

    with pytest.raises(ValidationError) as exc:
        service.resolve_shot_binding(PROJECT, SHOT)
    assert exc.value.metadata["failure_type"] == "canonical_setting_reference_missing"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Synchronization never downgrades or contradicts a valid designation
# ═══════════════════════════════════════════════════════════════════════════

def test_sync_never_downgrades_or_competes_with_an_explicit_designation(scoped):
    service = ReferenceAssetService(scoped)
    scoped.save_reference_asset(_asset("ref_set_designated"))
    service.designate_setting_reference_canonical(PROJECT, SETTING, "ref_set_designated")
    _save_approved_previs(scoped)

    service.sync_creator_references(PROJECT)
    service.sync_creator_references(PROJECT)

    # The creator's designation still holds sole canonical authority.
    assert bool(scoped.get_reference_asset("ref_set_designated")["canonical"]) is True
    synced = scoped.get_reference_asset(_env_ref_id(PROJECT, SCENE))
    assert synced["approval_state"] == "approved"
    assert bool(synced["canonical"]) is False
    references = validation._approved_setting_references(scoped, project_id=PROJECT, setting_id=SETTING)
    assert [item["ref_id"] for item in references] == ["ref_set_designated"]


def test_sync_preserves_its_own_existing_canonical_row(scoped):
    service = ReferenceAssetService(scoped)
    _save_approved_previs(scoped)
    service.sync_creator_references(PROJECT)

    # Re-sync mirrors the same deterministic row in place and keeps its
    # canonical authority: exactly one row for the scene, still canonical.
    assert service.sync_creator_references(PROJECT)["environment_stills"] == 1
    rows = scoped.list_reference_assets(PROJECT, kind="environment")
    assert len(rows) == 1
    assert bool(scoped.get_reference_asset(_env_ref_id(PROJECT, SCENE))["canonical"]) is True


# ═══════════════════════════════════════════════════════════════════════════
# 8. Route contract (generic) and Scene 002 separation
# ═══════════════════════════════════════════════════════════════════════════

def test_designate_route_contract(scoped, monkeypatch):
    client = _client(scoped, monkeypatch)
    scoped.save_reference_asset(_asset("ref_set_wide"))
    scoped.save_reference_asset(_asset("ref_set_candidate", approval_state="candidate"))
    path = f"/api/f51/studio/projects/{PROJECT}/reference-library/setting/{SETTING}"

    ok = client.post(f"{path}/ref_set_wide/canonical", json={"canonical": True})
    assert ok.status_code == 200
    assert bool(ok.json()["reference_asset"]["canonical"]) is True

    candidate = client.post(f"{path}/ref_set_candidate/canonical", json={"canonical": True})
    assert candidate.status_code == 400
    assert bool(scoped.get_reference_asset("ref_set_candidate")["canonical"]) is False

    missing = client.post(f"{path}/ref_missing/canonical", json={"canonical": True})
    assert missing.status_code == 404

    # The body cannot request a non-canonical "designation".
    assert client.post(f"{path}/ref_set_wide/canonical", json={"canonical": False}).status_code == 422


def test_generic_paths_refuse_the_scene002_exact_pair(storage, monkeypatch):
    client = _client(storage, monkeypatch)
    storage.save_reference_asset(_asset(
        "ref_set_scene002", project_id=SCENE002_PROJECT_ID, target_id=SCENE002_SETTING_ID,
    ))

    response = client.post(
        f"/api/f51/studio/projects/{SCENE002_PROJECT_ID}/reference-library/setting/"
        f"{SCENE002_SETTING_ID}/ref_set_scene002/canonical",
        json={"canonical": True},
    )
    assert response.status_code == 400
    assert bool(storage.get_reference_asset("ref_set_scene002")["canonical"]) is False

    with pytest.raises(ValueError):
        ReferenceAssetService(storage).designate_setting_reference_canonical(
            SCENE002_PROJECT_ID, SCENE002_SETTING_ID, "ref_set_scene002",
        )


def test_scene002_anchor_listing_semantics_are_unchanged(storage):
    """The exact Scene 002 path keeps its id-bound listing contract."""
    storage.save_reference_asset(_asset(
        "ref_set_a", project_id=SCENE002_PROJECT_ID, target_id=SCENE002_SETTING_ID, canonical=True,
    ))
    storage.save_reference_asset(_asset(
        "ref_set_b", project_id=SCENE002_PROJECT_ID, target_id=SCENE002_SETTING_ID, canonical=True,
    ))

    rows = validation._approved_setting_references(
        storage, project_id=SCENE002_PROJECT_ID, setting_id=SCENE002_SETTING_ID,
    )
    # Both id-bound anchors are still listed (this listing is order-agnostic): the exact
    # Scene 002 path is governed by its explicit decision, and its listing contract is
    # deliberately unchanged by the generic ambiguity guard.
    assert {row["ref_id"] for row in rows} == {"ref_set_a", "ref_set_b"}
