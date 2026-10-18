"""Tests for reference_assets DB persistence — the data-loss bug fix.

Three proof points:
  (a) Migration #30 creates the reference_assets table on a fresh DB
  (b) Storage-level: save_reference_asset survives a "restart" (new
      DatabaseStorage instance pointing at the same DB file)
  (c) Route-level: the confirm endpoint persists to DB and the GET
      list endpoint reads back after a simulated restart

The core bug: the confirm endpoint previously wrote to an in-memory dict
(_assets).  A server restart silently wiped all confirmed reference assets.
These tests prove that is no longer the case.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.services.reference_asset_service import ReferenceAssetService, reference_asset_service
from app.routes.reference_assets import router


# ── Helpers ─────────────────────────────────────────────────────────────────

def _sample_asset_dict(ref_id: str = "ref_test001", project_id: str = "proj-ra-001") -> dict:
    return {
        "ref_id": ref_id,
        "kind": "character_full",
        "image_url": "https://cdn.example.com/render.mp4",
        "source_shot_id": "shot-1",
        "project_id": project_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# (a) Migration test — table created on a fresh DB
# ═══════════════════════════════════════════════════════════════════════════

def test_migration_30_creates_reference_assets_table(tmp_path: Path):
    """A fresh DatabaseStorage must have the reference_assets table."""
    db = DatabaseStorage(str(tmp_path / "fresh_db"))

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='reference_assets'"
        )
        assert cursor.fetchone() is not None, "reference_assets table was not created"

        cursor.execute("PRAGMA table_info(reference_assets)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert "ref_id" in columns, "missing ref_id column"
        assert "project_id" in columns, "missing project_id column"
        assert "kind" in columns, "missing kind column"
        assert "image_url" in columns, "missing image_url column"
        assert "embedding" in columns, "missing embedding column"
        assert "source_shot_id" in columns, "missing source_shot_id column"
        assert "created_at" in columns, "missing created_at column"

        cursor.execute("SELECT version FROM schema_migrations WHERE version = 30")
        assert cursor.fetchone() is not None, "migration #30 was not recorded"


def test_migration_30_indexes_created(tmp_path: Path):
    """The migration creates project and source_shot indexes."""
    db = DatabaseStorage(str(tmp_path / "fresh_db"))

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_reference_assets_project'"
        )
        assert cursor.fetchone() is not None, "idx_reference_assets_project missing"

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_reference_assets_source_shot'"
        )
        assert cursor.fetchone() is not None, "idx_reference_assets_source_shot missing"


def test_migration_30_kind_check_constraint(tmp_path: Path):
    """The kind CHECK constraint rejects invalid values."""
    db = DatabaseStorage(str(tmp_path / "fresh_db"))

    with db._get_connection() as conn:
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO reference_assets (ref_id, project_id, kind, image_url) "
                "VALUES (?, ?, ?, ?)",
                ("ref_bad", "proj-x", "invalid_kind", "https://x.com/v.mp4"),
            )


# ═══════════════════════════════════════════════════════════════════════════
# (b) Storage-level persistence — survives a "restart"
# ═══════════════════════════════════════════════════════════════════════════

def test_save_and_list_reference_asset_survives_restart(tmp_path: Path):
    """Core bug proof: a new DatabaseStorage (simulating restart) can still
    read an asset saved by a prior instance."""
    db_path = str(tmp_path / "ra_db")

    # "Before restart" — save an asset
    db_before = DatabaseStorage(db_path)
    asset = _sample_asset_dict()
    assert db_before.save_reference_asset(asset) is True

    # Verify it's readable from the same instance
    rows = db_before.list_reference_assets(project_id="proj-ra-001")
    assert len(rows) == 1
    assert rows[0]["ref_id"] == "ref_test001"
    assert rows[0]["image_url"] == "https://cdn.example.com/render.mp4"

    # "After restart" — create a completely new instance pointing at the same file
    db_after = DatabaseStorage(db_path)
    rows_after = db_after.list_reference_assets(project_id="proj-ra-001")
    assert len(rows_after) == 1, (
        "DATA LOSS BUG: asset disappeared after simulated restart"
    )
    assert rows_after[0]["ref_id"] == "ref_test001"
    assert rows_after[0]["kind"] == "character_full"
    assert rows_after[0]["source_shot_id"] == "shot-1"


def test_get_reference_asset_by_id_after_restart(tmp_path: Path):
    """get_reference_asset retrieves a single asset by ID after restart."""
    db_path = str(tmp_path / "ra_db")

    db_before = DatabaseStorage(db_path)
    db_before.save_reference_asset(_sample_asset_dict(ref_id="ref_lookup"))

    db_after = DatabaseStorage(db_path)
    asset = db_after.get_reference_asset("ref_lookup")
    assert asset is not None
    assert asset["ref_id"] == "ref_lookup"
    assert asset["project_id"] == "proj-ra-001"


def test_list_reference_assets_filters_by_kind(tmp_path: Path):
    """list_reference_assets filters by kind."""
    db = DatabaseStorage(str(tmp_path / "ra_db"))
    db.save_reference_asset(_sample_asset_dict(ref_id="ref_a", project_id="proj-f"))
    db.save_reference_asset({
        "ref_id": "ref_b",
        "kind": "environment",
        "image_url": "https://cdn.example.com/env.jpg",
        "source_shot_id": "shot-2",
        "project_id": "proj-f",
    })

    all_assets = db.list_reference_assets(project_id="proj-f")
    assert len(all_assets) == 2

    char_only = db.list_reference_assets(project_id="proj-f", kind="character_full")
    assert len(char_only) == 1
    assert char_only[0]["ref_id"] == "ref_a"


def test_list_reference_assets_project_isolation(tmp_path: Path):
    """list_reference_assets only returns assets for the requested project."""
    db = DatabaseStorage(str(tmp_path / "ra_db"))
    db.save_reference_asset(_sample_asset_dict(ref_id="ref_p1", project_id="proj-A"))
    db.save_reference_asset(_sample_asset_dict(ref_id="ref_p2", project_id="proj-B"))

    a_only = db.list_reference_assets(project_id="proj-A")
    assert len(a_only) == 1
    assert a_only[0]["ref_id"] == "ref_p1"


def test_save_reference_asset_with_embedding_roundtrip(tmp_path: Path):
    """Embedding list is serialized to JSON and deserialized on read."""
    db_path = str(tmp_path / "ra_db")
    db = DatabaseStorage(db_path)
    db.save_reference_asset({
        "ref_id": "ref_emb",
        "kind": "character_face",
        "image_url": "https://cdn.example.com/face.jpg",
        "embedding": [0.1, 0.2, 0.3],
        "source_shot_id": "shot-1",
        "project_id": "proj-emb",
    })

    db_after = DatabaseStorage(db_path)
    asset = db_after.get_reference_asset("ref_emb")
    assert asset is not None
    assert asset["embedding"] == [0.1, 0.2, 0.3]


def test_save_reference_asset_rejects_empty_ref_id(tmp_path: Path):
    """save_reference_asset returns False for empty ref_id."""
    db = DatabaseStorage(str(tmp_path / "ra_db"))
    assert db.save_reference_asset({"ref_id": "", "project_id": "p", "kind": "character_full", "image_url": "x"}) is False


# ═══════════════════════════════════════════════════════════════════════════
# (c) Route-level persistence — confirm + GET list survives restart
# ═══════════════════════════════════════════════════════════════════════════

def test_confirm_then_list_survives_restart_via_routes(tmp_path: Path):
    """End-to-end bug proof: confirm via POST, simulate restart with a new
    DatabaseStorage, then GET list and confirm the asset is still there.

    This directly reproduces the original bug scenario:
      BEFORE FIX: confirm wrote to _assets dict; restart wiped it; no
                  GET endpoint existed to even check.
      AFTER FIX:  confirm writes to DB; new storage instance reads from
                  the same DB file; GET list returns the confirmed asset.
    """
    db_path = str(tmp_path / "route_db")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Phase 1: confirm an asset (using a real DB, not the in-memory dict)
    db_before = DatabaseStorage(db_path)
    with patch.object(reference_asset_service, "_storage", db_before):
        confirm_resp = client.post(
            "/api/f51/studio/projects/proj-restart-1/reference-assets",
            json={
                "ref_id": "proposal_abc123",
                "kind": "character_full",
                "image_url": "https://cdn.example.com/confirmed.mp4",
                "source_shot_id": "shot-42",
                "project_id": "proj-restart-1",
            },
        )

    assert confirm_resp.status_code == 200
    confirmed = confirm_resp.json()["reference_asset"]
    assert confirmed["ref_id"].startswith("ref_")
    assert confirmed["image_url"] == "https://cdn.example.com/confirmed.mp4"
    saved_ref_id = confirmed["ref_id"]

    # Phase 2: simulate a server restart — new DatabaseStorage, same file
    db_after = DatabaseStorage(db_path)

    # Phase 3: GET list — the asset must still be there
    with patch.object(reference_asset_service, "_storage", db_after):
        list_resp = client.get(
            "/api/f51/studio/projects/proj-restart-1/reference-assets",
        )

    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["count"] == 1, (
        f"DATA LOSS BUG: expected 1 asset after restart, got {body['count']}"
    )
    asset = body["reference_assets"][0]
    assert asset["ref_id"] == saved_ref_id
    assert asset["image_url"] == "https://cdn.example.com/confirmed.mp4"
    assert asset["source_shot_id"] == "shot-42"
    assert asset["project_id"] == "proj-restart-1"


def test_route_confirm_rejects_cross_project_ref(tmp_path: Path):
    """The project-isolation check must still reject mismatched project_id."""
    db = DatabaseStorage(str(tmp_path / "route_db"))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with patch.object(reference_asset_service, "_storage", db):
        resp = client.post(
            "/api/f51/studio/projects/proj-legit/reference-assets",
            json={
                "ref_id": "proposal_abc",
                "kind": "character_full",
                "image_url": "https://cdn.example.com/v.mp4",
                "source_shot_id": "shot-1",
                "project_id": "proj-attacker",
            },
        )

    assert resp.status_code == 400
    assert "does not match" in resp.json()["detail"]


def test_route_get_list_empty_for_project_with_no_assets(tmp_path: Path):
    """GET list returns empty list for a project with no confirmed assets."""
    db = DatabaseStorage(str(tmp_path / "route_db"))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with patch.object(reference_asset_service, "_storage", db):
        resp = client.get(
            "/api/f51/studio/projects/proj-empty/reference-assets",
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["reference_assets"] == []


# ═══════════════════════════════════════════════════════════════════════════
# (d) Browser-usable image URLs — broken reference image regression
# ═══════════════════════════════════════════════════════════════════════════
#
# The Character training UI renders ReferenceAsset.image_url directly (through
# buildStudioApiUrl), so the GET list endpoint must only return URLs the
# frontend can actually fetch: served namespaces pointing at real files, or
# absolute http(s) URLs. Historical DB rows carried /media/<file>.png URLs — a
# namespace the backend never mounted — which rendered as broken images.


def client_post_confirm(project_id: str, ref_id: str, image_url: str):
    """Confirm a reference asset through the API route (TestClient required)."""
    app = FastAPI()
    app.include_router(router)
    confirm_client = TestClient(app)
    return confirm_client.post(
        f"/api/f51/studio/projects/{project_id}/reference-assets",
        json={
            "ref_id": ref_id,
            "kind": "character_face",
            "image_url": image_url,
            "source_shot_id": None,
            "project_id": project_id,
        },
    )


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 1x1 PNG (smallest valid image), served byte-for-byte by StaticFiles.
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
        )
    )


def test_list_assets_hides_legacy_unserved_media_rows(tmp_path: Path):
    """Legacy /media/... rows (unserved namespace, file gone) are not returned.

    The browser previously received /media/vt_character_face.png → 404 → broken
    image. Such rows must never reach the frontend as image URLs. The DB row is
    untouched; only the listing view omits it.
    """
    db = DatabaseStorage(str(tmp_path / "view.db"))
    db.save_reference_asset(
        {
            "ref_id": "ref_legacy_media",
            "project_id": "proj-view",
            "kind": "character_face",
            "image_url": "/media/vt_character_face.png",
        }
    )
    service = ReferenceAssetService(storage=db)
    assets = service.list_assets("proj-view")
    assert assets == []
    # Storage still holds the row (view-level hiding, not data deletion).
    assert db.get_reference_asset("ref_legacy_media") is not None


def test_list_assets_repairs_legacy_media_rows_when_file_is_served(tmp_path: Path, monkeypatch):
    """A /media/<file>.png row whose file exists under the served outputs tree
    is repaired to its browser URL /outputs/reference-assets/<file>."""
    from app.services import reference_asset_service as service_module

    outputs_dir = tmp_path / "outputs"
    _write_png(outputs_dir / "reference-assets" / "repaired_face.png")
    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: outputs_dir)

    db = DatabaseStorage(str(tmp_path / "view.db"))
    db.save_reference_asset(
        {
            "ref_id": "ref_legacy_repairable",
            "project_id": "proj-view",
            "kind": "character_face",
            "image_url": "/media/repaired_face.png",
        }
    )
    service = ReferenceAssetService(storage=db)
    assets = service.list_assets("proj-view")
    assert len(assets) == 1
    assert assets[0]["image_url"] == "/outputs/reference-assets/repaired_face.png"


def test_list_assets_hides_outputs_urls_without_files(tmp_path: Path):
    """/outputs/... URLs pointing at missing files would 404 in the browser."""
    db = DatabaseStorage(str(tmp_path / "view.db"))
    db.save_reference_asset(
        {
            "ref_id": "ref_missing_file",
            "project_id": "proj-view",
            "kind": "character_full",
            "image_url": "/outputs/references/definitely-not-here.png",
        }
    )
    service = ReferenceAssetService(storage=db)
    assert service.list_assets("proj-view") == []


def test_list_assets_keeps_http_urls_and_served_files(tmp_path: Path):
    """Absolute http(s) URLs and existing /outputs files pass through untouched."""
    db = DatabaseStorage(str(tmp_path / "view.db"))
    db.save_reference_asset(
        {
            "ref_id": "ref_http",
            "project_id": "proj-view",
            "kind": "character_face",
            "image_url": "https://cdn.example.com/maya.png",
        }
    )
    db.save_reference_asset(
        {
            "ref_id": "ref_local_ok",
            "project_id": "proj-view",
            "kind": "environment",
            "image_url": "/outputs/reference-assets/real.png",
        }
    )
    service = ReferenceAssetService(storage=db)
    assets = service.list_assets("proj-view")
    urls = {a["ref_id"]: a["image_url"] for a in assets}
    assert urls["ref_http"] == "https://cdn.example.com/maya.png"


def test_route_list_returns_browser_usable_urls_and_they_serve_over_http(tmp_path: Path, monkeypatch):
    """Full HTTP contract: create a reference whose file exists, GET the list
    through the API route, then GET the image URL itself and require image
    bytes — the exact path the browser takes for Character reference cards."""
    from app.services import reference_asset_service as service_module

    outputs_dir = tmp_path / "outputs"
    _write_png(outputs_dir / "references" / "proj-view" / "face.png")
    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: outputs_dir)

    db = DatabaseStorage(str(tmp_path / "route_db"))
    with patch.object(reference_asset_service, "_storage", db):
        confirm_resp = client_post_confirm(
            "proj-view",
            "ref_browser_face",
            "/outputs/references/proj-view/face.png",
        )
    assert confirm_resp.status_code == 200

    app = FastAPI()
    app.include_router(router)
    from fastapi.staticfiles import StaticFiles

    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
    client = TestClient(app)

    with patch.object(reference_asset_service, "_storage", db):
        list_resp = client.get("/api/f51/studio/projects/proj-view/reference-assets")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["count"] == 1
    image_url = body["reference_assets"][0]["image_url"]
    # Browser-usable: a served absolute path, not a filesystem path or video id.
    assert image_url.startswith("/outputs/")
    assert image_url.endswith(".png")

    # The URL survives a real HTTP request and returns the image.
    img_resp = client.get(image_url)
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"].startswith("image/")
    assert img_resp.content.startswith(b"\x89PNG")
