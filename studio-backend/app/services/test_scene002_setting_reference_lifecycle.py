from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.consistency import ReferenceAsset
from app.models.scene_direction import SaveSceneDirection, SceneDirection, SettingReferenceDecision

from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.project_store import ProjectStore
from app.services.scene_direction_service import SceneDirectionService
from app.services.reference_asset_service import (
    LEGACY_SCENE002_REFERENCE_ID,
    SCENE002_PROJECT_ID,
    SCENE002_SETTING_ID,
    ReferenceAssetService,
)
from app.services.reference_validation import resolve_scene_reference_requirements
from app.services.stability import StateError, ValidationError

PROJECT_ID = "project_5907c60cddbc"
SCENE_ID = "scene_002"
SHARED_URI = "https://assets.example.test/scene002-setting.png"
LEGACY_URI = "https://assets.example.test/legacy-scene-frame.png"


def _legacy_row() -> dict:
    return {
        "ref_id": LEGACY_SCENE002_REFERENCE_ID,
        "project_id": PROJECT_ID,
        "kind": "environment",
        "image_url": LEGACY_URI,
        "source_shot_id": f"{SCENE_ID}_shot_001",
        "target_type": None,
        "target_id": None,
        "approval_state": "approved",
        "canonical": False,
        "source_kind": "confirmed",
    }


def _setting_row(ref_id: str, *, uri: str = SHARED_URI, project_id: str = PROJECT_ID,
                 target_type: str = "setting", target_id: str = SCENE002_SETTING_ID,
                 kind: str = "environment", approval_state: str = "approved",
                 canonical: bool = True) -> dict:
    return {
        "ref_id": ref_id,
        "project_id": project_id,
        "kind": kind,
        "image_url": uri,
        "source_shot_id": None,
        "target_type": target_type,
        "target_id": target_id,
        "category": "environment",
        "approval_state": approval_state,
        "canonical": canonical,
        "source_kind": "confirmed",
    }


def _authority_fields(row: dict | None) -> dict:
    return {
        key: row.get(key) if key != "canonical" else bool(row.get(key))
        for key in ("ref_id", "project_id", "kind", "image_url", "source_shot_id",
                    "target_type", "target_id", "approval_state", "canonical", "source_kind")
    } if isinstance(row, dict) else {}


def _store_setting_entity(storage: DatabaseStorage) -> None:
    storage.save_universe_node({
        "node_id": SCENE002_SETTING_ID,
        "project_id": PROJECT_ID,
        "node_type": "location",
        "name": "Synthetic exact setting entity",
        "first_scene": SCENE_ID,
        "last_scene": SCENE_ID,
    })


def test_create_only_setting_candidate_has_fresh_exact_scope_and_does_not_reuse_legacy(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "create"))
    _store_setting_entity(storage)
    storage.save_reference_asset(_legacy_row())
    legacy_before = storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)

    created = ReferenceAssetService(storage).create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)

    assert created["ref_id"].startswith("ref_set_")
    assert created["ref_id"] != LEGACY_SCENE002_REFERENCE_ID
    assert created["project_id"] == PROJECT_ID
    assert (created["target_type"], created["target_id"]) == ("setting", SCENE002_SETTING_ID)
    assert created["kind"] == "environment"
    assert created["approval_state"] == "candidate"
    assert created["canonical"] in (False, 0)
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy_before)


def test_same_uri_is_retained_on_two_distinct_reference_ids(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "same-uri"))
    _store_setting_entity(storage)
    service = ReferenceAssetService(storage)

    first = service.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)
    second = service.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)

    assert first["ref_id"] != second["ref_id"]
    rows = storage.list_reference_assets(
        project_id=PROJECT_ID, target_type="setting", target_id=SCENE002_SETTING_ID,
    )
    assert {row["ref_id"] for row in rows} == {first["ref_id"], second["ref_id"]}
    assert {row["image_url"] for row in rows} == {SHARED_URI}
    assert all(row["approval_state"] == "candidate" for row in rows)


def test_create_only_id_collision_fails_without_replacing_existing_row(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "collision"))
    original = _setting_row("ref_set_collision", uri="https://assets.example.test/original.png", canonical=False,
                            approval_state="candidate")
    storage.save_reference_asset(original)

    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        storage.create_scene002_setting_reference(
            ref_id="ref_set_collision", project_id=PROJECT_ID, image_url=SHARED_URI,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    assert storage.get_reference_asset("ref_set_collision")["image_url"] == original["image_url"]
    assert storage.get_reference_asset("ref_set_collision")["approval_state"] == "candidate"


def test_generic_create_only_reference_collision_preserves_existing_row(tmp_path):
    import sqlite3

    storage = DatabaseStorage(str(tmp_path / "generic-create-collision"))
    original = _setting_row("ref_collision", uri="https://assets.example.test/kept.png")
    storage.save_reference_asset(original)

    with pytest.raises(sqlite3.IntegrityError):
        storage.create_reference_asset({**original, "image_url": "https://assets.example.test/replacement.png"})

    assert storage.get_reference_asset("ref_collision")["image_url"] == original["image_url"]


def test_approval_changes_only_approval_state_and_canonical_designation_only_canonical(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "separated"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    service = ReferenceAssetService(storage)
    peer = _setting_row("ref_set_peer", canonical=True)
    storage.save_reference_asset(peer)
    peer_before = storage.get_reference_asset(peer["ref_id"])
    created = service.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)
    before = storage.get_reference_asset(created["ref_id"])

    approved = service.approve_scene002_setting_reference(PROJECT_ID, created["ref_id"])
    assert approved["approval_state"] == "approved"
    after_approval = storage.get_reference_asset(created["ref_id"])
    for key in before:
        if key != "approval_state":
            assert after_approval[key] == before[key]

    canonical = service.designate_scene002_setting_reference_canonical(PROJECT_ID, created["ref_id"])
    assert canonical["canonical"] in (True, 1)
    after_canonical = storage.get_reference_asset(created["ref_id"])
    for key in after_approval:
        if key != "canonical":
            assert after_canonical[key] == after_approval[key]
    assert _authority_fields(storage.get_reference_asset(peer["ref_id"])) == _authority_fields(peer_before)
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)


def test_approval_and_canonical_operations_fail_closed_for_wrong_scope_kind_or_state(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "closed"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    storage.save_reference_asset(_setting_row("wrong-project", project_id="project-other", canonical=False,
                                              approval_state="candidate"))
    storage.save_reference_asset(_setting_row("wrong-target", target_id="scene_002", canonical=False,
                                              approval_state="candidate"))
    storage.save_reference_asset(_setting_row("wrong-target-type", target_type="scene", canonical=False,
                                              approval_state="candidate"))
    storage.save_reference_asset(_setting_row("wrong-kind", kind="character_full", canonical=False,
                                              approval_state="candidate"))
    storage.save_reference_asset(_setting_row("already-approved", canonical=False, approval_state="approved"))
    storage.save_reference_asset(_setting_row("canonical-candidate", canonical=True, approval_state="candidate"))
    service = ReferenceAssetService(storage)

    with pytest.raises(LookupError):
        service.approve_scene002_setting_reference(PROJECT_ID, "wrong-project")
    for ref_id in (LEGACY_SCENE002_REFERENCE_ID, "wrong-target", "wrong-target-type", "wrong-kind"):
        with pytest.raises(LookupError):
            service.approve_scene002_setting_reference(PROJECT_ID, ref_id)
    with pytest.raises(ValueError):
        service.approve_scene002_setting_reference(PROJECT_ID, "already-approved")
    with pytest.raises(ValueError):
        service.approve_scene002_setting_reference(PROJECT_ID, "canonical-candidate")

    with pytest.raises(LookupError):
        service.designate_scene002_setting_reference_canonical(PROJECT_ID, "wrong-project")
    for ref_id in (LEGACY_SCENE002_REFERENCE_ID, "wrong-target", "wrong-target-type", "wrong-kind"):
        with pytest.raises(LookupError):
            service.designate_scene002_setting_reference_canonical(PROJECT_ID, ref_id)
    designated = service.designate_scene002_setting_reference_canonical(PROJECT_ID, "already-approved")
    assert designated["canonical"] in (True, 1)
    assert designated["approval_state"] == "approved"
    with pytest.raises(ValueError):
        service.designate_scene002_setting_reference_canonical(PROJECT_ID, "canonical-candidate")
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)
    assert _authority_fields(storage.get_reference_asset("already-approved"))["canonical"] is True


def test_scoped_picker_read_is_sync_free_and_does_not_write(tmp_path, monkeypatch):
    from app.routes import reference_assets as routes

    storage = DatabaseStorage(str(tmp_path / "picker"))
    _store_setting_entity(storage)
    storage.save_reference_asset(_legacy_row())
    service = ReferenceAssetService(storage)
    candidate = service.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)
    before = storage.list_reference_assets(project_id=PROJECT_ID)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("sync must not run through the scoped picker")

    monkeypatch.setattr(service, "sync_creator_references", forbidden)
    monkeypatch.setattr(routes, "reference_asset_service", service)
    response = routes.list_scene002_setting_references(PROJECT_ID, SCENE002_SETTING_ID)

    assert response["reference_assets"] == [candidate]
    assert storage.list_reference_assets(project_id=PROJECT_ID) == before
    assert LEGACY_SCENE002_REFERENCE_ID not in {row["ref_id"] for row in response["reference_assets"]}


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), color=(12, 34, 56)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_upload_creates_fresh_exact_candidate_and_never_touches_legacy(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "upload"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    service = ReferenceAssetService(storage)
    outputs = tmp_path / "outputs"

    first = service.upload_scene002_setting_candidate(PROJECT_ID, _png_bytes(), outputs_dir=outputs)
    second = service.upload_scene002_setting_candidate(PROJECT_ID, _png_bytes(), outputs_dir=outputs)

    for created in (first, second):
        assert created["ref_id"].startswith("ref_set_")
        assert created["ref_id"] != LEGACY_SCENE002_REFERENCE_ID
        assert created["project_id"] == PROJECT_ID
        assert (created["target_type"], created["target_id"]) == ("setting", SCENE002_SETTING_ID)
        assert created["kind"] == "environment"
        assert created["approval_state"] == "candidate"
        assert created["canonical"] in (False, 0)
        assert created["image_url"].startswith("/outputs/")
        assert (outputs / created["image_url"].removeprefix("/outputs/")).is_file()
    assert first["ref_id"] != second["ref_id"]
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)


def test_upload_identity_collision_cannot_replace_an_existing_reference(tmp_path, monkeypatch):
    from types import SimpleNamespace as _SimpleNamespace

    from app.services import reference_asset_service as service_module

    storage = DatabaseStorage(str(tmp_path / "upload-collision"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    fixed = _SimpleNamespace(hex="a" * 32)
    colliding_id = f"ref_set_{fixed.hex}"
    original = _setting_row(colliding_id, uri="https://assets.example.test/kept-upload.png",
                            canonical=False, approval_state="candidate")
    storage.save_reference_asset(original)
    monkeypatch.setattr(service_module, "uuid4", lambda: fixed)

    with pytest.raises(ValueError, match="already exists"):
        ReferenceAssetService(storage).upload_scene002_setting_candidate(
            PROJECT_ID, _png_bytes(), outputs_dir=tmp_path / "outputs-collision",
        )

    assert storage.get_reference_asset(colliding_id)["image_url"] == original["image_url"]
    assert storage.get_reference_asset(colliding_id)["approval_state"] == "candidate"
    assert storage.get_reference_asset(colliding_id)["canonical"] in (False, 0)
    assert not list((tmp_path / "outputs-collision").rglob("*.png"))
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)


def test_upload_rejects_wrong_project_and_wrong_entity_scope(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "upload-scope"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    service = ReferenceAssetService(storage)

    with pytest.raises(LookupError):
        service.upload_scene002_setting_candidate("project-other", _png_bytes(),
                                                  outputs_dir=tmp_path / "outputs-other")
    with pytest.raises(ValueError):
        service.upload_scene002_setting_candidate(PROJECT_ID, b"not an image",
                                                  outputs_dir=tmp_path / "outputs-invalid")

    assert storage.list_reference_assets(project_id=PROJECT_ID, target_type="setting",
                                         target_id=SCENE002_SETTING_ID) == []
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)


def test_upload_route_is_exact_scoped_and_sync_free(tmp_path, monkeypatch):
    import asyncio
    from io import BytesIO

    from app.routes import reference_assets as routes
    from app.services import reference_asset_service as service_module
    from fastapi import HTTPException
    from starlette.datastructures import UploadFile as StarletteUploadFile

    storage = DatabaseStorage(str(tmp_path / "upload-route"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    service = ReferenceAssetService(storage)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy creator sync must never run for the exact-setting lifecycle")

    outputs = tmp_path / "route-outputs"
    monkeypatch.setattr(service, "sync_creator_references", forbidden)
    monkeypatch.setattr(routes, "reference_asset_service", service)
    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: outputs)

    async def _call(setting_id: str):
        return await routes.upload_scene002_setting_reference(
            PROJECT_ID, setting_id,
            file=StarletteUploadFile(BytesIO(_png_bytes()), filename="setting.png"),
        )

    with pytest.raises(HTTPException) as wrong_target:
        asyncio.run(_call("scene_002"))
    assert wrong_target.value.status_code == 404

    response = asyncio.run(_call(SCENE002_SETTING_ID))
    created = response["reference_asset"]
    assert created["ref_id"].startswith("ref_set_")
    assert created["ref_id"] != LEGACY_SCENE002_REFERENCE_ID
    assert (created["target_type"], created["target_id"]) == ("setting", SCENE002_SETTING_ID)
    assert created["approval_state"] == "candidate"
    assert created["canonical"] in (False, 0)
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)


def test_creator_lifecycle_api_routes_use_separate_exact_id_actions(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes import reference_assets as routes

    storage = DatabaseStorage(str(tmp_path / "creator-api"))
    _store_setting_entity(storage)
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    service = ReferenceAssetService(storage)
    peer = _setting_row("ref_set_same_uri_peer", uri=SHARED_URI, canonical=False)
    storage.save_reference_asset(peer)
    peer_before = storage.get_reference_asset(peer["ref_id"])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("creator API must never run legacy creator sync")

    monkeypatch.setattr(service, "sync_creator_references", forbidden)
    monkeypatch.setattr(routes, "reference_asset_service", service)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    base = f"/api/f51/studio/projects/{PROJECT_ID}/setting-references/{SCENE002_SETTING_ID}"

    registered = client.post(base, json={"image_url": SHARED_URI})
    assert registered.status_code == 200, registered.text
    candidate = registered.json()["reference_asset"]
    ref_id = candidate["ref_id"]
    assert ref_id.startswith("ref_set_")
    assert ref_id != LEGACY_SCENE002_REFERENCE_ID
    assert candidate["project_id"] == PROJECT_ID
    assert (candidate["target_type"], candidate["target_id"]) == ("setting", SCENE002_SETTING_ID)
    assert candidate["kind"] == "environment"
    assert candidate["approval_state"] == "candidate"
    assert candidate["canonical"] in (False, 0)

    # Canonical designation cannot be combined with or substituted for approval.
    assert client.post(f"{base}/{ref_id}/canonical", json={"canonical": True}).status_code == 409
    before_approval = storage.get_reference_asset(ref_id)
    approved_response = client.post(f"{base}/{ref_id}/approve")
    assert approved_response.status_code == 200, approved_response.text
    approved = approved_response.json()["reference_asset"]
    assert approved["approval_state"] == "approved"
    assert approved["canonical"] in (False, 0)
    after_approval = storage.get_reference_asset(ref_id)
    assert {key: value for key, value in after_approval.items() if key != "approval_state"} == {
        key: value for key, value in before_approval.items() if key != "approval_state"
    }

    canonical_response = client.post(f"{base}/{ref_id}/canonical", json={"canonical": True})
    assert canonical_response.status_code == 200, canonical_response.text
    designated = canonical_response.json()["reference_asset"]
    assert designated["ref_id"] == ref_id
    assert designated["project_id"] == PROJECT_ID
    assert (designated["target_type"], designated["target_id"]) == ("setting", SCENE002_SETTING_ID)
    assert designated["kind"] == "environment"
    assert designated["approval_state"] == "approved"
    assert designated["canonical"] in (True, 1)
    assert _authority_fields(storage.get_reference_asset(peer["ref_id"])) == _authority_fields(peer_before)
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)

    # The UI's exact scoped GET does not sync and does not write.
    before_read = storage.list_reference_assets(project_id=PROJECT_ID)
    scoped_read = client.get(base)
    assert scoped_read.status_code == 200, scoped_read.text
    assert scoped_read.json()["target_id"] == SCENE002_SETTING_ID
    assert {row["ref_id"] for row in scoped_read.json()["reference_assets"]} == {ref_id, peer["ref_id"]}
    assert LEGACY_SCENE002_REFERENCE_ID not in {row["ref_id"] for row in scoped_read.json()["reference_assets"]}
    assert storage.list_reference_assets(project_id=PROJECT_ID) == before_read

    assert client.get(f"/api/f51/studio/projects/{PROJECT_ID}/setting-references/scene_002").status_code == 404
    assert client.get(f"/api/f51/studio/projects/project-other/setting-references/{SCENE002_SETTING_ID}").status_code == 404
    assert client.post(f"/api/f51/studio/projects/project-other/setting-references/{SCENE002_SETTING_ID}",
                       json={"image_url": SHARED_URI}).status_code == 404


def test_generic_confirm_cannot_promote_exact_setting_and_id_collision_does_not_replace(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "confirm"))
    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    service = ReferenceAssetService(storage)

    combined = ReferenceAsset(
        ref_id="proposal_setting",
        project_id=PROJECT_ID,
        kind="environment",
        image_url=SHARED_URI,
        target_type="setting",
        target_id=SCENE002_SETTING_ID,
        approval_state="approved",
        canonical=True,
    )
    with pytest.raises(ValueError, match="separate"):
        service.confirm(PROJECT_ID, combined)
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(legacy)

    collision = ReferenceAsset(
        ref_id="proposal_env_collision",
        project_id=PROJECT_ID,
        kind="character_full",
        image_url=SHARED_URI,
    )
    storage.save_reference_asset({**collision.model_dump(mode="json"), "ref_id": "ref_env_collision"})
    with pytest.raises(ValueError, match="already exists"):
        service.confirm(PROJECT_ID, collision.model_copy(update={"ref_id": "proposal_env_collision"}))


def test_exact_setting_selection_survives_same_uri_and_preflight_rechecks_current_authority(monkeypatch):
    from app.services import reference_validation as validation

    selected = _setting_row("ref_set_selected")
    duplicate_uri = _setting_row("ref_set_same-uri")

    class SelectedReferenceStorage:
        def __init__(self):
            self.row = selected.copy()
            self.universe_nodes = [{
                "node_id": SCENE002_SETTING_ID, "project_id": PROJECT_ID,
                "node_type": "location", "first_scene": SCENE_ID, "last_scene": SCENE_ID,
            }]
            self.blueprint = SimpleNamespace(
                project_id=PROJECT_ID, scene_id=SCENE_ID, current_version_id="version-current",
                approved_version_id="version-current",
            )
            self.version = SimpleNamespace(
                version_id="version-current", project_id=PROJECT_ID, scene_id=SCENE_ID,
                status="approved",
                metadata={"scene_direction": {"setting_reference_decision": {
                    "canonical_setting_id": SCENE002_SETTING_ID, "reference_id": "ref_set_selected",
                }}},
            )

        def get_reference_asset(self, ref_id):
            return self.row.copy() if self.row and self.row.get("ref_id") == ref_id else None

        def get_universe_nodes(self, project_id):
            return [row for row in self.universe_nodes if row["project_id"] == project_id]

        def list_reference_assets(self, **kwargs):
            return [row.copy() for row in (self.row, duplicate_uri)
                    if row and row["project_id"] == kwargs.get("project_id")
                    and row["target_type"] == kwargs.get("target_type")
                    and row["target_id"] == kwargs.get("target_id")]

        def get_storyboard_blueprint(self, project_id, scene_id):
            return self.blueprint

        def get_storyboard_blueprint_version(self, version_id):
            return self.version if version_id == self.version.version_id else None

    storage = SelectedReferenceStorage()
    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: {
        "project_id": PROJECT_ID,
        "execution_summary": {"scenes": [{"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID}]},
    })
    requirements = resolve_scene_reference_requirements(
        project_id=PROJECT_ID, scene_id=SCENE_ID, storage=storage,
        scene={"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID},
    )
    assert requirements["setting_references"][0]["ref_id"] == "ref_set_selected"
    assert requirements["setting_references"][0]["uri"] == duplicate_uri["image_url"]
    assert requirements["setting_references"][0]["project_id"] == PROJECT_ID

    for changed in (
        None,
        {**selected, "project_id": "project-other"},
        {**selected, "target_id": "scene_002"},
        {**selected, "target_type": "scene"},
        {**selected, "kind": "character_full"},
        {**selected, "approval_state": "candidate"},
        {**selected, "canonical": False},
        {**selected, "image_url": "file:///not-an-image.png"},
        {**selected, "image_url": ""},
    ):
        storage.row = changed
        with pytest.raises(ValidationError):
            resolve_scene_reference_requirements(
                project_id=PROJECT_ID, scene_id=SCENE_ID, storage=storage,
                scene={"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID},
            )


def test_scene002_setting_preflight_rejects_legacy_scene_target_even_if_approved(monkeypatch):
    from app.services import reference_validation as validation

    legacy_targeted = _setting_row(
        LEGACY_SCENE002_REFERENCE_ID, target_id=SCENE002_SETTING_ID, canonical=True, approval_state="approved",
    )

    class LegacyOnlyStorage:
        def get_universe_nodes(self, project_id):
            return [{"node_id": SCENE002_SETTING_ID, "project_id": project_id, "node_type": "location",
                     "first_scene": SCENE_ID, "last_scene": SCENE_ID}]

        def list_reference_assets(self, **_kwargs):
            return [legacy_targeted]

    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: {
        "project_id": PROJECT_ID,
        "execution_summary": {"scenes": [{"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID}]},
    })
    with pytest.raises(ValidationError):
        resolve_scene_reference_requirements(
            project_id=PROJECT_ID, scene_id=SCENE_ID, storage=LegacyOnlyStorage(),
            scene={"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID},
        )


def test_scene_direction_options_and_successor_save_preserve_exact_authority(tmp_path):
    text = "EXT. CHICAGO RIVER - DAY\nMaya studies the water.\nMAYA\nKeep it."
    project = StudioProject(
        project_id=PROJECT_ID,
        title="Scene 002 authority fixture",
        script_text=text,
        execution_summary={
            "scenes": [{
                "scene_id": SCENE_ID,
                "setting_id": SCENE002_SETTING_ID,
                "description": "Fixture scene description.",
                "text": text,
                "characters": [],
            }],
            "dialogue_lines": [{
                "line_id": "scene002-line-1", "scene_id": SCENE_ID,
                "character_name": "MAYA", "text": "Keep it.",
            }],
        },
    )
    storage = DatabaseStorage(str(tmp_path / "scene-direction"))
    storage.save_project(project)
    storage.save_universe_node({
        "node_id": SCENE002_SETTING_ID, "project_id": PROJECT_ID,
        "node_type": "location", "name": "Exact setting entity",
        "first_scene": SCENE_ID, "last_scene": SCENE_ID,
    })
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path / "scene-state.json"))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(
        project_id=PROJECT_ID, scene_id=SCENE_ID, shot_count=1,
    )
    source = detail["version"]
    source.status = StoryboardBlueprintStatus.APPROVED
    source.approved_at = "2026-10-01T00:00:00+00:00"
    source.approved_by = "synthetic creator"
    detail["blueprint"].status = StoryboardBlueprintStatus.APPROVED
    detail["blueprint"].approved_version_id = source.version_id
    storage.save_storyboard_blueprint_version(source)
    storage.save_storyboard_blueprint(detail["blueprint"])

    legacy = _legacy_row()
    storage.save_reference_asset(legacy)
    candidate = ReferenceAssetService(storage).create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)
    ReferenceAssetService(storage).approve_scene002_setting_reference(PROJECT_ID, candidate["ref_id"])
    ReferenceAssetService(storage).designate_scene002_setting_reference_canonical(PROJECT_ID, candidate["ref_id"])
    same_uri = _setting_row("ref_set_other_canonical", canonical=True)
    storage.save_reference_asset(same_uri)

    before_legacy = storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)
    before_selected = storage.get_reference_asset(candidate["ref_id"])
    data = service.get(PROJECT_ID, SCENE_ID)
    assert data.canonical_setting_id == SCENE002_SETTING_ID
    assert {option.ref_id for option in data.setting_reference_options} == {
        candidate["ref_id"], "ref_set_other_canonical",
    }
    assert LEGACY_SCENE002_REFERENCE_ID not in {option.ref_id for option in data.setting_reference_options}
    assert data.setting_reference_decision is None
    assert data.coverage_blocked
    # Selecting a reference never generates coverage decisions of its own.
    assert all(row.status == "UNASSIGNED" for row in data.coverage_decisions)

    blueprint_id = detail["blueprint"].blueprint_id
    source_shots = {
        shot.shot_id: shot
        for shot in storage.list_storyboard_shots(blueprint_id, source.version_id)
    }

    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID,
        reference_id=candidate["ref_id"],
    )
    payload = SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
                  for shot in data.shots],
        setting_reference_decision=decision,
    )
    source_snapshot = storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode="json")
    with pytest.raises(StateError):
        service.save(PROJECT_ID, SCENE_ID, payload.model_copy(update={"expected_version_id": "stale-version"}))
    assert storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode="json") == source_snapshot
    assert _authority_fields(storage.get_reference_asset(candidate["ref_id"])) == _authority_fields(before_selected)

    saved = service.save(PROJECT_ID, SCENE_ID, payload)
    successor = storage.get_storyboard_blueprint_version(saved.version_id)
    assert successor.status == StoryboardBlueprintStatus.DRAFT
    assert successor.source_version_id == source.version_id
    persisted = successor.metadata["scene_direction"]["setting_reference_decision"]
    assert persisted == {
        "canonical_setting_id": SCENE002_SETTING_ID,
        "reference_id": candidate["ref_id"],
    }
    assert storage.get_storyboard_blueprint_version(source.version_id).status == StoryboardBlueprintStatus.APPROVED
    assert _authority_fields(storage.get_reference_asset(candidate["ref_id"])) == _authority_fields(before_selected)
    assert _authority_fields(storage.get_reference_asset(LEGACY_SCENE002_REFERENCE_ID)) == _authority_fields(before_legacy)
    assert saved.coverage_blocked

    # 21. Saving the setting reference decision never auto-generates coverage
    # decisions: every obligation keeps the exact state it had before the save.
    assert {(row.obligation_type, row.obligation_id, row.status, row.shot_id, row.reason)
            for row in saved.coverage_decisions} == {
        (row.obligation_type, row.obligation_id, row.status, row.shot_id, row.reason)
        for row in data.coverage_decisions
    }
    assert all(row.status == "UNASSIGNED" for row in saved.coverage_decisions)

    # 22. Prompts, camera plans, dialogue wording/assignments, and multishot
    # data are carried over untouched — only creator coverage keys change.
    successor_metadata = dict(successor.metadata)
    assert successor_metadata.pop("scene_direction") is not None
    source_metadata = {key: value for key, value in
                       storage.get_storyboard_blueprint_version(source.version_id).metadata.items()
                       if key != "continuity_review"}
    assert successor_metadata == source_metadata
    scene_direction_metadata = successor.metadata["scene_direction"]
    assert scene_direction_metadata["dialogue"] == [line.model_dump() for line in data.dialogue]
    assert scene_direction_metadata["coverage_decisions"] == [row.model_dump() for row in data.coverage_decisions]

    successor_shots = {
        shot.shot_id: shot
        for shot in storage.list_storyboard_shots(blueprint_id, saved.version_id)
    }
    assert set(successor_shots) == set(source_shots)
    creator_owned_keys = {
        "creator_coverage_decisions", "covered_content_ids", "dialogue_disposition",
        "dialogue_disposition_reason", "content_coverage_disposition", "content_coverage_reason",
    }
    for shot_id, before_shot in source_shots.items():
        after_shot = successor_shots[shot_id]
        assert after_shot.render_contract.provider_neutral_prompt == before_shot.render_contract.provider_neutral_prompt
        assert after_shot.render_contract.prompt_components == before_shot.render_contract.prompt_components
        assert after_shot.render_contract.reference_assets == before_shot.render_contract.reference_assets
        assert after_shot.render_contract.seed == before_shot.render_contract.seed
        assert after_shot.render_contract.seed_locked == before_shot.render_contract.seed_locked
        assert after_shot.intent == before_shot.intent
        assert after_shot.visual_plan == before_shot.visual_plan
        assert after_shot.continuity_plan == before_shot.continuity_plan
        assert {key: value for key, value in after_shot.render_contract.structured_parameters.items()
                if key not in creator_owned_keys} == {
            key: value for key, value in before_shot.render_contract.structured_parameters.items()
            if key not in creator_owned_keys
        }
        clone_owned_keys = {"handoff_frame_url", "source_storyboard_shot_id", "source_version_id"}
        assert {key: value for key, value in after_shot.metadata.items() if key not in clone_owned_keys} == {
            key: value for key, value in before_shot.metadata.items() if key not in clone_owned_keys
        }


def test_scene_direction_keeps_all_60_plus_coverage_obligations_blocking(tmp_path):
    body = "\n".join(f"Canonical visual obligation {index:02d}." for index in range(1, 61))
    script = f"EXT. TEST LOCATION - DAY\n{body}"
    project = StudioProject(
        project_id=PROJECT_ID,
        title="60 obligation coverage fixture",
        script_text=script,
        execution_summary={"scenes": [{
            "scene_id": SCENE_ID,
            "setting_id": SCENE002_SETTING_ID,
            "heading": "EXT. TEST LOCATION - DAY",
            "text": script,
            "characters": [],
        }], "dialogue_lines": []},
    )
    storage = DatabaseStorage(str(tmp_path / "coverage-obligations"))
    storage.save_project(project)
    _store_setting_entity(storage)
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path / "coverage-state.json"))
    service.blueprints.project_store.save_project(project.model_dump())
    service.blueprints.get_or_create_blueprint(project_id=PROJECT_ID, scene_id=SCENE_ID, shot_count=1)

    direction = service.get(PROJECT_ID, SCENE_ID)

    unresolved_content = [
        row for row in direction.coverage_obligations
        if row.obligation_type == "content" and row.status == "UNASSIGNED"
    ]
    assert len(unresolved_content) >= 60
    assert direction.coverage_blocked
    assert any("coverage" in blocker.lower() or "content" in blocker.lower()
               for blocker in direction.coverage_blockers)


def test_synthetic_40_10_five_shot_setting_workflow_keeps_all_60_unresolved(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes.scene_direction import get_service, router as scene_direction_router
    from app.services import reference_validation as validation

    dialogue_rows = []
    body_lines = []
    for index in range(1, 11):
        speaker = "MAYA" if index % 2 else "DRE"
        text = f"Synthetic dialogue line {index:02d}."
        body_lines.append(text)
        dialogue_rows.append({
            "line_id": f"fixture-dialogue-{index:02d}",
            "scene_id": SCENE_ID,
            "character_name": speaker,
            "text": text,
        })
    body_lines.extend(f"Synthetic content obligation {index:02d}." for index in range(1, 31))
    scene_text = "\n".join(body_lines)
    script = f"EXT. SYNTHETIC RIVER - DAY\n{scene_text}"
    project = StudioProject(
        project_id=PROJECT_ID,
        title="Hermetic Scene 002 creator workflow",
        script_text=script,
        execution_summary={
            "scenes": [{
                "scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID,
                "heading": "EXT. SYNTHETIC RIVER - DAY", "text": scene_text,
                "description": "Synthetic approved previs context.",
                "characters": ["MAYA", "DRE"],
            }],
            "dialogue_lines": dialogue_rows,
        },
    )
    storage = DatabaseStorage(str(tmp_path / "sixty-obligation-db"))
    storage.save_project(project)
    _store_setting_entity(storage)
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path / "sixty-obligation-state.json"))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(
        project_id=PROJECT_ID, scene_id=SCENE_ID, shot_count=5,
    )
    source = detail["version"]
    source.status = StoryboardBlueprintStatus.APPROVED
    source.approved_at = "2026-10-02T00:00:00+00:00"
    source.approved_by = "synthetic creator"
    detail["blueprint"].status = StoryboardBlueprintStatus.APPROVED
    detail["blueprint"].approved_version_id = source.version_id
    storage.save_storyboard_blueprint_version(source)
    storage.save_storyboard_blueprint(detail["blueprint"])

    before = service.get(PROJECT_ID, SCENE_ID)
    counts = {
        "content": sum(row.obligation_type == "content" for row in before.coverage_obligations),
        "dialogue": sum(row.obligation_type == "dialogue" for row in before.coverage_obligations),
        "shot_content": sum(row.obligation_type == "shot_content" for row in before.coverage_decisions),
        "shot_dialogue": sum(row.obligation_type == "shot_dialogue" for row in before.coverage_decisions),
    }
    assert counts == {"content": 40, "dialogue": 10, "shot_content": 5, "shot_dialogue": 5}
    assert len(before.coverage_decisions) == 60
    assert len(before.shots) == 5
    assert all(row.status == "UNASSIGNED" for row in before.coverage_decisions)
    assert before.coverage_blocked

    refs = ReferenceAssetService(storage)
    candidate = refs.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)
    refs.approve_scene002_setting_reference(PROJECT_ID, candidate["ref_id"])
    refs.designate_scene002_setting_reference_canonical(PROJECT_ID, candidate["ref_id"])
    approved_reference_before = _authority_fields(storage.get_reference_asset(candidate["ref_id"]))
    source_shots = storage.list_storyboard_shots(detail["blueprint"].blueprint_id, source.version_id)
    source_shot_snapshot = [shot.model_dump(mode="json") for shot in source_shots]

    scene_direction_app = FastAPI()
    scene_direction_app.include_router(scene_direction_router)
    scene_direction_app.dependency_overrides[get_service] = lambda: service
    scene_direction_client = TestClient(scene_direction_app)
    scene_direction_url = f"/api/f51/studio/projects/{PROJECT_ID}/scenes/{SCENE_ID}/direction"
    get_response = scene_direction_client.get(scene_direction_url)
    assert get_response.status_code == 200, get_response.text
    data = SceneDirection.model_validate(get_response.json())
    assert {option.ref_id for option in data.setting_reference_options} == {candidate["ref_id"]}
    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID,
        reference_id=candidate["ref_id"],
    )
    payload = SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
                  for shot in data.shots],
        setting_reference_decision=decision,
    )
    versions_before_stale = storage.list_storyboard_blueprint_versions(detail["blueprint"].blueprint_id)
    source_before_stale = storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode="json")
    stale = payload.model_copy(update={"expected_version_id": "stale-synthetic-version"})
    stale_response = scene_direction_client.put(scene_direction_url, json=stale.model_dump(mode="json"))
    assert stale_response.status_code == 409
    assert len(storage.list_storyboard_blueprint_versions(detail["blueprint"].blueprint_id)) == len(versions_before_stale)
    assert storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode="json") == source_before_stale
    assert _authority_fields(storage.get_reference_asset(candidate["ref_id"])) == approved_reference_before

    save_response = scene_direction_client.put(scene_direction_url, json=payload.model_dump(mode="json"))
    assert save_response.status_code == 200, save_response.text
    saved = SceneDirection.model_validate(save_response.json())
    assert saved.version_id != source.version_id
    assert saved.version_status == "draft"
    successor = storage.get_storyboard_blueprint_version(saved.version_id)
    assert successor.source_version_id == source.version_id
    assert successor.metadata["scene_direction"]["setting_reference_decision"] == {
        "canonical_setting_id": SCENE002_SETTING_ID,
        "reference_id": candidate["ref_id"],
    }
    assert storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode="json") == source_before_stale
    assert [shot.model_dump(mode="json") for shot in storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, source.version_id,
    )] == source_shot_snapshot
    assert _authority_fields(storage.get_reference_asset(candidate["ref_id"])) == approved_reference_before
    successor_shots = storage.list_storyboard_shots(detail["blueprint"].blueprint_id, saved.version_id)
    assert len(saved.shots) == len(source_shot_snapshot) == len(successor_shots) == 5
    decision_owned_keys = {
        "creator_coverage_decisions", "covered_content_ids", "dialogue_disposition",
        "dialogue_disposition_reason", "content_coverage_disposition", "content_coverage_reason",
    }
    clone_owned_metadata_keys = {"source_storyboard_shot_id", "source_version_id", "handoff_frame_url"}
    for original, successor_shot in zip(source_shot_snapshot, successor_shots):
        current = successor_shot.model_dump(mode="json")
        assert current["shot_id"] == original["shot_id"]
        assert current["shot_number"] == original["shot_number"]
        assert current["render_contract"]["provider_neutral_prompt"] == original["render_contract"]["provider_neutral_prompt"]
        assert current["render_contract"]["reference_assets"] == original["render_contract"]["reference_assets"]
        original_parameters = dict(original["render_contract"]["structured_parameters"])
        current_parameters = dict(current["render_contract"]["structured_parameters"])
        for key in decision_owned_keys:
            original_parameters.pop(key, None)
            current_parameters.pop(key, None)
        assert current_parameters == original_parameters
        assert current["visual_plan"] == original["visual_plan"]
        assert current["intent"] == original["intent"]
        assert current["continuity_plan"] == original["continuity_plan"]
        original_metadata = {key: value for key, value in original["metadata"].items()
                             if key not in clone_owned_metadata_keys}
        current_metadata = {key: value for key, value in current["metadata"].items()
                            if key not in clone_owned_metadata_keys}
        assert current_metadata == original_metadata
    successor_metadata = dict(successor.metadata)
    assert successor_metadata.pop("scene_direction")["setting_reference_decision"] == {
        "canonical_setting_id": SCENE002_SETTING_ID,
        "reference_id": candidate["ref_id"],
    }
    assert successor_metadata == source_before_stale["metadata"]
    assert {(row.obligation_type, row.obligation_id, row.status, row.shot_id, row.reason)
            for row in saved.coverage_decisions} == {
        (row.obligation_type, row.obligation_id, row.status, row.shot_id, row.reason)
        for row in data.coverage_decisions
    }
    assert len(saved.coverage_decisions) == 60
    assert all(row.status == "UNASSIGNED" for row in saved.coverage_decisions)

    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: project.model_dump(mode="json"))
    # Saving the explicit selection creates a current draft successor. The
    # decision is persisted and editable, but cannot authorize production until
    # that exact successor version is approved.
    with pytest.raises(ValidationError, match="no explicit Scene Direction setting reference decision exists"):
        resolve_scene_reference_requirements(
            project_id=PROJECT_ID, scene_id=SCENE_ID, storage=storage,
            scene={"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID},
        )
    assert storage.get_storyboard_blueprint_version(saved.version_id).metadata["scene_direction"]["setting_reference_decision"] == {
        "canonical_setting_id": SCENE002_SETTING_ID,
        "reference_id": candidate["ref_id"],
    }
    assert _authority_fields(storage.get_reference_asset(candidate["ref_id"])) == approved_reference_before


def test_scene002_lifecycle_preflight_rejects_legacy_reference_id_for_exact_setting(monkeypatch):
    from app.services import reference_validation as validation

    legacy = _setting_row(
        LEGACY_SCENE002_REFERENCE_ID, canonical=True, approval_state="approved",
    )

    class LegacyReferenceStorage:
        def __init__(self):
            self.version = SimpleNamespace(
                version_id="version-current", project_id=PROJECT_ID, scene_id=SCENE_ID,
                status="approved",
                metadata={"scene_direction": {"setting_reference_decision": {
                    "canonical_setting_id": SCENE002_SETTING_ID,
                    "reference_id": LEGACY_SCENE002_REFERENCE_ID,
                }}},
            )

        def get_reference_asset(self, ref_id):
            return legacy if ref_id == LEGACY_SCENE002_REFERENCE_ID else None

        def get_universe_nodes(self, project_id):
            return [{"node_id": SCENE002_SETTING_ID, "project_id": project_id,
                     "node_type": "location", "first_scene": SCENE_ID, "last_scene": SCENE_ID}]

        def get_storyboard_blueprint(self, project_id, scene_id):
            return SimpleNamespace(project_id=project_id, scene_id=scene_id,
                                   current_version_id="version-current",
                                   approved_version_id="")

        def get_storyboard_blueprint_version(self, version_id):
            return self.version if version_id == self.version.version_id else None

        def list_reference_assets(self, **_kwargs):
            return [legacy]

    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: {
        "project_id": PROJECT_ID,
        "execution_summary": {"scenes": [{"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID}]},
    })
    with pytest.raises(ValidationError):
        resolve_scene_reference_requirements(
            project_id=PROJECT_ID, scene_id=SCENE_ID,
            storage=LegacyReferenceStorage(),
            scene={"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID},
        )


def test_id_bound_setting_anchor_list_keeps_duplicate_uri_reference_ids():
    from app.services.reference_validation import _approved_setting_references

    class DuplicateURIStorage:
        def list_reference_assets(self, **_kwargs):
            return [
                _setting_row("ref_set_a", canonical=True),
                _setting_row("ref_set_b", canonical=True),
            ]

    rows = _approved_setting_references(
        DuplicateURIStorage(), project_id=PROJECT_ID, setting_id=SCENE002_SETTING_ID,
    )
    assert [row["ref_id"] for row in rows] == ["ref_set_a", "ref_set_b"]


def test_scene_direction_exact_options_exclude_unapproved_wrong_scope_and_legacy(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "options"))
    rows = [
        _setting_row("ref_set_good", canonical=True, approval_state="approved"),
        _setting_row("ref_set_candidate", canonical=True, approval_state="candidate"),
        _setting_row("ref_set_noncanonical", canonical=False, approval_state="approved"),
        _setting_row("ref_set_wrong_project", project_id="project-other", canonical=True),
        _setting_row("ref_env_6b726885ed67ae4d", canonical=True),
    ]
    for row in rows:
        storage.save_reference_asset(row)
    options = SceneDirectionService(storage)._setting_reference_options(PROJECT_ID, SCENE002_SETTING_ID)
    assert {row.ref_id for row in options} == {"ref_set_good"}
    assert all(row.ref_id != LEGACY_SCENE002_REFERENCE_ID for row in options)


def test_scene_direction_rejects_stale_selected_reference_without_mutation(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "stale-selection"))
    _store_setting_entity(storage)
    project = StudioProject(
        project_id=PROJECT_ID, title="stale selection",
        script_text="EXT. CHICAGO RIVER - DAY\nMAYA\nKeep it.",
        execution_summary={"scenes": [{"scene_id": SCENE_ID, "setting_id": SCENE002_SETTING_ID,
                                          "text": "MAYA\nKeep it.", "characters": []}],
                           "dialogue_lines": []},
    )
    storage.save_project(project)
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path / "stale-state.json"))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(project_id=PROJECT_ID, scene_id=SCENE_ID, shot_count=1)
    source = detail["version"]
    source.status = StoryboardBlueprintStatus.APPROVED
    source.approved_at = "2026-10-01T00:00:00+00:00"
    source.approved_by = "synthetic creator"
    detail["blueprint"].status = StoryboardBlueprintStatus.APPROVED
    detail["blueprint"].approved_version_id = source.version_id
    storage.save_storyboard_blueprint_version(source)
    storage.save_storyboard_blueprint(detail["blueprint"])
    data = service.get(PROJECT_ID, SCENE_ID)
    row = _setting_row("ref_set_deauthorized", canonical=True)
    storage.save_reference_asset(row)
    data = service.get(PROJECT_ID, SCENE_ID)
    payload = SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[decision.model_dump() for decision in data.coverage_decisions],
        handoffs=[shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
                  for shot in data.shots],
        setting_reference_decision=SettingReferenceDecision(
            canonical_setting_id=SCENE002_SETTING_ID, reference_id="ref_set_deauthorized",
        ),
    )
    storage.update_reference_asset_state("ref_set_deauthorized", PROJECT_ID, "rejected")
    source_snapshot = storage.get_storyboard_blueprint_version(data.version_id).model_dump(mode="json")
    with pytest.raises(ValidationError):
        service.save(PROJECT_ID, SCENE_ID, payload)
    assert storage.get_storyboard_blueprint_version(data.version_id).model_dump(mode="json") == source_snapshot
    assert storage.get_reference_asset("ref_set_deauthorized")["canonical"] in (True, 1)
