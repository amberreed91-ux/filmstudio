"""sync=0 pure-read tests for the reference board GETs.

Read-only contract: GET reference-assets and GET reference-library accept an
optional ``sync`` query parameter. ``sync=0`` skips the best-effort creator
sync; the default (param absent or any non-zero value) preserves the existing
sync-on-read behavior.

These tests fail at HEAD (no ``sync`` param: the sync always runs, so the
perturbed rows are re-inserted and the fingerprints diverge).
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes import reference_assets as routes
from app.services.reference_asset_service import ReferenceAssetService


def _make_client(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path / "sync_param.db"))
    service = ReferenceAssetService(storage)
    monkeypatch.setattr(routes, "reference_asset_service", service)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), storage


def _approved_character(project_id: str, character_id: str) -> dict:
    return {
        "id": character_id,
        "project_id": project_id,
        "name": "Maya",
        "continuity_state_json": json.dumps(
            {
                "appearance_approval": {
                    "status": "locked",
                    "version": 1,
                    "approved_at": "2026-09-21T12:00:00+00:00",
                    "face_image_url": "https://cdn.example/maya.png",
                }
            }
        ),
    }


def _save_character(storage: DatabaseStorage, project_id: str, character_id: str) -> None:
    character = _approved_character(project_id, character_id)
    storage.save_character(
        project_id,
        character["name"],
        {"id": character["id"], "continuity_state_json": character["continuity_state_json"]},
    )


def _fingerprint(storage: DatabaseStorage, project_id: str) -> tuple:
    rows = storage.list_reference_assets(project_id=project_id, limit=200) or []
    return tuple(
        sorted(
            (
                str(row.get("ref_id")),
                str(row.get("image_url")),
                str(row.get("approval_state")),
                bool(row.get("canonical")),
            )
            for row in rows
        )
    )


def test_reference_assets_sync0_makes_no_writes(tmp_path, monkeypatch):
    client, storage = _make_client(tmp_path, monkeypatch)
    _save_character(storage, "film-sync0", "chr_maya")

    # Converge via the default (sync-on) read, then perturb: delete every row.
    resp = client.get("/api/f51/studio/projects/film-sync0/reference-assets")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    for row in storage.list_reference_assets(project_id="film-sync0", limit=200) or []:
        assert storage.delete_reference_asset(row["ref_id"], "film-sync0")
    assert _fingerprint(storage, "film-sync0") == ()

    # Pure reads must NOT re-insert the deleted sync rows: fingerprint identical.
    for _ in range(3):
        resp = client.get("/api/f51/studio/projects/film-sync0/reference-assets?sync=0")
        assert resp.status_code == 200
    assert _fingerprint(storage, "film-sync0") == ()


def test_reference_library_sync0_does_not_reinsert_deleted_rows(tmp_path, monkeypatch):
    client, storage = _make_client(tmp_path, monkeypatch)
    _save_character(storage, "film-lib0", "chr_maya")

    resp = client.get("/api/f51/studio/projects/film-lib0/reference-library/character/chr_maya")
    assert resp.status_code == 200
    assert resp.json()["canonical"] is not None
    for row in storage.list_reference_assets(project_id="film-lib0", limit=200) or []:
        assert storage.delete_reference_asset(row["ref_id"], "film-lib0")
    assert _fingerprint(storage, "film-lib0") == ()

    for _ in range(2):
        resp = client.get(
            "/api/f51/studio/projects/film-lib0/reference-library/character/chr_maya?sync=0"
        )
        assert resp.status_code == 200
    assert _fingerprint(storage, "film-lib0") == ()


def test_default_behavior_still_syncs(tmp_path, monkeypatch):
    client, storage = _make_client(tmp_path, monkeypatch)
    _save_character(storage, "film-default", "chr_maya")

    # sync=0 first: nothing is mirrored.
    resp = client.get("/api/f51/studio/projects/film-default/reference-assets?sync=0")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert _fingerprint(storage, "film-default") == ()

    # Default (no param) still syncs: the locked look appears.
    resp = client.get("/api/f51/studio/projects/film-default/reference-assets")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert len(_fingerprint(storage, "film-default")) == 1

    # Non-zero sync value also syncs.
    for row in storage.list_reference_assets(project_id="film-default", limit=200) or []:
        assert storage.delete_reference_asset(row["ref_id"], "film-default")
    resp = client.get("/api/f51/studio/projects/film-default/reference-assets?sync=1")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_second_project_isolation(tmp_path, monkeypatch):
    client, storage = _make_client(tmp_path, monkeypatch)
    _save_character(storage, "film-a", "chr_maya_a")
    _save_character(storage, "film-b", "chr_maya_b")

    resp = client.get("/api/f51/studio/projects/film-b/reference-assets?sync=0")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert _fingerprint(storage, "film-a") == ()
    assert _fingerprint(storage, "film-b") == ()

    # Default read on film-a syncs only film-a.
    resp = client.get("/api/f51/studio/projects/film-a/reference-assets")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert len(_fingerprint(storage, "film-a")) == 1
    assert _fingerprint(storage, "film-b") == ()


def test_absent_table_case_empty_project(tmp_path, monkeypatch):
    client, storage = _make_client(tmp_path, monkeypatch)

    # No characters, no reference_assets rows anywhere: pure read is a clean 200.
    resp = client.get("/api/f51/studio/projects/film-empty/reference-assets?sync=0")
    assert resp.status_code == 200
    assert resp.json() == {"reference_assets": [], "count": 0}

    resp = client.get(
        "/api/f51/studio/projects/film-empty/reference-library/character/chr_nobody?sync=0"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["canonical"] is None
    assert body["supporting"] == []
    assert body["candidates"] == []
    assert _fingerprint(storage, "film-empty") == ()
