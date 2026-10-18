"""Creator-approved visual sync tests (visual training reference availability).

The visual-training panels ("Train This Look" / "Train This Setting") read the
confirmed reference_assets registry. Approval state, however, lives in the
character continuity document (locked looks) and previs rows (approved
storyboard stills). These tests pin the sync that mirrors those approvals into
the registry so approved references actually show up in the training UI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services.reference_asset_service import (
    ReferenceAssetService,
    _casting_look_folder,
    _casting_ref_id,
    _env_ref_id,
    _look_ref_id,
    browser_view_asset_dict,
)


@pytest.fixture
def storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "sync.db"))


@pytest.fixture
def service(storage: DatabaseStorage) -> ReferenceAssetService:
    return ReferenceAssetService(storage)


def _approved_character(project_id: str, character_id: str, **approval_fields) -> dict:
    """A character row with a locked look in its continuity document."""
    approval = {
        "status": "locked",
        "version": 1,
        "approved_at": "2026-09-21T12:00:00+00:00",
        **approval_fields,
    }
    document = {"appearance_approval": approval}
    return {
        "id": character_id,
        "project_id": project_id,
        "name": "Maya",
        "continuity_state_json": json.dumps(document),
    }


def _save_character(storage: DatabaseStorage, character: dict) -> None:
    storage.save_character(
        character["project_id"],
        character["name"],
        {
            "continuity_state_json": character["continuity_state_json"],
            "id": character["id"],
        },
    )


def _previs_row(
    project_id: str,
    scene_id: str,
    image_path: str,
    *,
    approved: bool = True,
    status: str = "complete",
    fallback: bool = False,
) -> dict:
    return {
        "id": f"previs_{scene_id}_{abs(hash(image_path)) % 99999}",
        "project_id": project_id,
        "scene_id": scene_id,
        "shot_id": f"{scene_id}_shot_001",
        "image_path": image_path,
        "job_id": f"job_{scene_id}",
        "status": status,
        "prompt_used": "test",
        "fallback": fallback,
        "approved": approved,
        "created_at": "2026-09-21T10:00:00",
        "updated_at": "2026-09-21T10:00:00",
    }


# ── Locked character looks sync ──────────────────────────────────────────────


def test_locked_look_becomes_character_references(service, storage):
    """A locked look with face + body images syncs as character_face/character_full."""
    storage.save_character(
        "film-a",
        "Maya",
        {
            "id": "chr_1",
            "continuity_state_json": json.dumps(
                {
                    "appearance_approval": {
                        "status": "locked",
                        "version": 2,
                        "approved_at": "2026-09-21T12:00:00+00:00",
                        "face_image_url": "/outputs/references/chr_1/face.png",
                        "body_image_url": "/outputs/references/chr_1/body.png",
                    }
                }
            ),
        },
    )

    result = service.sync_creator_references("film-a")

    assert result["character_looks"] == 2
    refs = {row["ref_id"]: row for row in storage.list_reference_assets("film-a")}
    assert refs[_look_ref_id("chr_1", "face")]["kind"] == "character_face"
    assert refs[_look_ref_id("chr_1", "face")]["image_url"] == "/outputs/references/chr_1/face.png"
    assert refs[_look_ref_id("chr_1", "full_body")]["kind"] == "character_full"


def test_draft_look_does_not_sync(service, storage):
    """A look that is not locked must never enter the confirmed registry."""
    storage.save_character(
        "film-a",
        "Maya",
        {
            "id": "chr_2",
            "continuity_state_json": json.dumps(
                {
                    "appearance_approval": {
                        "status": "draft",
                        "version": 0,
                        "face_image_url": "/outputs/references/chr_2/face.png",
                    }
                }
            ),
        },
    )

    result = service.sync_creator_references("film-a")

    assert result["synced"] == 0
    assert storage.list_reference_assets("film-a") == []


def test_sync_is_idempotent_and_updates_in_place(service, storage):
    """Re-syncing with a changed look updates the row instead of duplicating."""
    storage.save_character(
        "film-a",
        "Maya",
        {
            "id": "chr_3",
            "continuity_state_json": json.dumps(
                {
                    "appearance_approval": {
                        "status": "locked",
                        "version": 1,
                        "face_image_url": "/outputs/references/chr_3/v1.png",
                    }
                }
            ),
        },
    )
    service.sync_creator_references("film-a")

    # Re-approve a new look version with a new face image.
    storage.save_character(
        "film-a",
        "Maya",
        {
            "id": "chr_3",
            "continuity_state_json": json.dumps(
                {
                    "appearance_approval": {
                        "status": "locked",
                        "version": 2,
                        "face_image_url": "/outputs/references/chr_3/v2.png",
                    }
                }
            ),
        },
    )
    result = service.sync_creator_references("film-a")

    assert result["character_looks"] == 1
    rows = storage.list_reference_assets("film-a")
    assert len(rows) == 1
    assert rows[0]["image_url"] == "/outputs/references/chr_3/v2.png"


def test_sync_never_touches_explicitly_confirmed_rows(service, storage):
    """Rows confirmed through propose/confirm keep their ref_id and image."""
    storage.save_reference_asset(
        {
            "ref_id": "ref_manual",
            "project_id": "film-a",
            "kind": "environment",
            "image_url": "/outputs/reference-assets/manual.png",
        }
    )

    service.sync_creator_references("film-a")

    rows = {row["ref_id"]: row for row in storage.list_reference_assets("film-a")}
    assert rows["ref_manual"]["image_url"] == "/outputs/reference-assets/manual.png"


# ── Approved environment stills sync ─────────────────────────────────────────


def _install_previs(storage: DatabaseStorage, rows: list[dict]) -> None:
    for row in rows:
        storage.save_previs_image(
            row["project_id"],
            row["scene_id"],
            row["shot_id"],
            row["image_path"],
            row["job_id"],
            row["status"],
            row["prompt_used"],
            row["fallback"],
        )
    # The service reads the `approved` flag; set it directly for the rows
    # marked approved in the test fixture.
    import sqlite3

    conn = sqlite3.connect(storage.db_path)
    for row in rows:
        if row["approved"]:
            conn.execute(
                "UPDATE previs_images SET approved = 1 WHERE image_path = ?",
                (row["image_path"],),
            )
    conn.commit()
    conn.close()


def test_approved_environment_still_syncs(service, storage):
    storage.save_project  # project existence is not required for the sync
    _install_previs(
        storage,
        [
            _previs_row(
                "film-a",
                "scene_002",
                "/previs-assets/film-a/scene_002_shot_001_storyboard_qwen.png",
            )
        ],
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 1
    rows = storage.list_reference_assets("film-a", kind="environment")
    assert len(rows) == 1
    assert rows[0]["ref_id"] == _env_ref_id("film-a", "scene_002")
    assert rows[0]["image_url"] == "/previs-assets/film-a/scene_002_shot_001_storyboard_qwen.png"


def test_unapproved_storyboard_does_not_sync(service, storage):
    _install_previs(
        storage,
        [
            _previs_row(
                "film-a",
                "scene_003",
                "/previs-assets/film-a/scene_003_shot_001_storyboard_qwen.png",
                approved=False,
            )
        ],
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 0
    assert storage.list_reference_assets("film-a") == []


def test_newest_approved_still_wins_per_scene(service, storage):
    first = _previs_row("film-a", "scene_004", "/previs-assets/film-a/older.png")
    second = _previs_row("film-a", "scene_004", "/previs-assets/film-a/newer.png")
    second["updated_at"] = "2026-09-21T11:00:00"
    _install_previs(storage, [first, second])

    service.sync_creator_references("film-a")

    rows = storage.list_reference_assets("film-a", kind="environment")
    assert len(rows) == 1
    assert rows[0]["image_url"] == "/previs-assets/film-a/newer.png"


def test_legacy_row_with_matching_ref_id_is_upgraded_to_canonical(service, storage):
    """A legacy row (pre-recovery pipeline) carrying the SAME deterministic
    ref_id but stale metadata — empty target scope, canonical=0 — must be
    healed in place when the creator approves the previs frame. Skipping it
    on an image_url+kind match alone left the creator's approval invisible
    to the reference gate (scene_002 generation-preflight, 2026-09-28)."""
    from app.services.reference_asset_service import _env_ref_id

    ref_id = _env_ref_id("film-a", "scene_002")
    storage.save_reference_asset(
        {
            "ref_id": ref_id,
            "project_id": "film-a",
            "kind": "environment",
            "image_url": "/previs-assets/film-a/scene_002_shot_001_storyboard_qwen.png",
            "source_shot_id": "scene_002_shot_001",
            "created_at": "2026-09-06T07:44:28.120443+00:00",
            "approval_state": "approved",
            "canonical": 0,
            "source_kind": "confirmed",
        }
    )
    _install_previs(
        storage,
        [
            _previs_row(
                "film-a",
                "scene_002",
                "/previs-assets/film-a/scene_002_shot_001_storyboard_qwen.png",
            )
        ],
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 1
    rows = storage.list_reference_assets("film-a", kind="environment")
    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "setting"
    assert row["target_id"] == "scene_002"
    assert bool(row["canonical"]) is True
    assert row["approval_state"] == "approved"
    assert row["kind"] == "environment"


def test_approved_status_previs_syncs(service, storage):
    """``approve_previs_image`` sets status='approved'; the sync must accept it
    the same as status='complete' — an approved frame is a completed render."""
    _install_previs(
        storage,
        [
            _previs_row(
                "film-a",
                "scene_002",
                "/previs-assets/film-a/scene_002_shot_001_storyboard_qwen.png",
                status="approved",
            )
        ],
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 1
    rows = storage.list_reference_assets("film-a", kind="environment")
    assert len(rows) == 1


def test_approved_blueprint_storyboard_syncs_as_environment(service, storage):
    """The Previs approve action marks blueprint shots approved; those
    storyboard images are the approved environment look for the scene."""
    from app.models.storyboard_blueprint import (
        StoryboardShot,
        StoryboardShotStatus,
    )

    storage.save_storyboard_blueprint(
        {
            "blueprint_id": "sbp_1",
            "project_id": "film-a",
            "scene_id": "scene_002",
            "current_version_id": "ver_1",
            "approved_version_id": "ver_1",
            "status": "approved",
        }
    )
    storage.save_storyboard_shot(
        StoryboardShot(
            storyboard_shot_id="sbs_1",
            blueprint_id="sbp_1",
            version_id="ver_1",
            project_id="film-a",
            scene_id="scene_002",
            shot_id="scene_002_shot_001",
            shot_number=1,
            status=StoryboardShotStatus.APPROVED,
            storyboard_image_url="/previs-assets/film-a/scene_002_approved.png",
        )
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 1
    rows = storage.list_reference_assets("film-a", kind="environment")
    assert len(rows) == 1
    assert rows[0]["ref_id"] == _env_ref_id("film-a", "scene_002")
    assert rows[0]["image_url"] == "/previs-assets/film-a/scene_002_approved.png"


def test_unapproved_blueprint_does_not_sync(service, storage):
    from app.models.storyboard_blueprint import (
        StoryboardShot,
        StoryboardShotStatus,
    )

    storage.save_storyboard_blueprint(
        {
            "blueprint_id": "sbp_2",
            "project_id": "film-a",
            "scene_id": "scene_003",
            "current_version_id": "ver_1",
            "approved_version_id": None,
            "status": "draft",
        }
    )
    storage.save_storyboard_shot(
        StoryboardShot(
            storyboard_shot_id="sbs_2",
            blueprint_id="sbp_2",
            version_id="ver_1",
            project_id="film-a",
            scene_id="scene_003",
            shot_id="scene_003_shot_001",
            shot_number=1,
            status=StoryboardShotStatus.APPROVED,
            storyboard_image_url="/previs-assets/film-a/scene_003.png",
        )
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 0
    assert storage.list_reference_assets("film-a") == []


def test_incomplete_or_fallback_still_does_not_sync(service, storage):
    _install_previs(
        storage,
        [
            _previs_row("film-a", "scene_005", "/previs-assets/film-a/pending.png", status="pending"),
            _previs_row("film-a", "scene_006", "/previs-assets/film-a/fallback.png", fallback=True),
        ],
    )

    result = service.sync_creator_references("film-a")

    assert result["environment_stills"] == 0


def test_unserved_namespace_image_is_hidden_not_broken(service, storage):
    """A synced image outside served namespaces must not reach the browser.

    This is the exact regression the /media rows caused: rows existed, the
    training panel could not render their image_url, and the UI looked empty.
    """
    storage.save_reference_asset(
        {
            "ref_id": "ref_legacy",
            "project_id": "film-a",
            "kind": "character_face",
            "image_url": "/media/dead_row.png",
        }
    )

    listing = service.list_assets("film-a")

    assert listing == []


def test_browser_view_passes_through_http_urls():
    asset = {"ref_id": "r", "kind": "character_face", "image_url": "https://cdn.example/x.png"}
    assert browser_view_asset_dict(asset) == asset


# ── Route wiring ─────────────────────────────────────────────────────────────


def test_list_route_syncs_before_listing(storage, service, monkeypatch, tmp_path):
    """GET reference-assets syncs approved looks so the training panel sees them."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes import reference_assets as routes
    from app.services import reference_asset_service as service_module

    # The listing hides /outputs/ URLs whose file is missing; back the
    # approved face reference with a real file so it stays visible.
    outputs_dir = tmp_path / "outputs" / "references" / "chr_route"
    outputs_dir.mkdir(parents=True)
    (outputs_dir / "face.png").write_bytes(b"png")
    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: tmp_path / "outputs")

    storage.save_character(
        "film-route",
        "Maya",
        {
            "id": "chr_route",
            "continuity_state_json": json.dumps(
                {
                    "appearance_approval": {
                        "status": "locked",
                        "version": 1,
                        "face_image_url": "/outputs/references/chr_route/face.png",
                    }
                }
            ),
        },
    )

    monkeypatch.setattr(routes, "reference_asset_service", service)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    resp = client.get("/api/f51/studio/projects/film-route/reference-assets")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["reference_assets"][0]["image_url"] == "/outputs/references/chr_route/face.png"


# ── Generated casting candidates sync ──────────────────────────────────────


def _casting_character(project_id: str, character_id: str, jobs: list) -> dict:
    """A character row carrying casting jobs in its continuity document."""
    return {
        "id": character_id,
        "project_id": project_id,
        "name": "Maya",
        "continuity_state_json": json.dumps({"appearance_casting_jobs": jobs}),
    }


def _casting_job(job_id: str, urls: list) -> dict:
    return {
        "id": job_id,
        "status": "complete",
        "requested_count": len(urls),
        "images": urls,
        "direction": "softer light",
        "created_at": "2026-09-21T12:00:00+00:00",
    }


def _back_casing_file(monkeypatch, tmp_path, project_id: str, character_id: str, filename: str):
    """Point the sync at a tmp outputs tree containing one casting file."""
    from app.services import reference_asset_service as service_module

    folder = _casting_look_folder(project_id, character_id)
    target = tmp_path / "outputs" / folder / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")
    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: tmp_path / "outputs")
    return f"/outputs/{folder}/{filename}"


def test_casting_images_sync_as_unapproved_generated_candidates(service, storage, monkeypatch, tmp_path):
    """Finished casting portraits mirror as candidate/generated rows, never approved."""
    url = _back_casing_file(monkeypatch, tmp_path, "film-a", "chr_1", "a" * 32 + ".png")
    _save_character(storage, _casting_character("film-a", "chr_1", [_casting_job("job-1", [url])]))

    result = service.sync_creator_references("film-a")

    assert result["casting_candidates"] == 1
    row = storage.get_reference_asset(_casting_ref_id("job-1", url))
    assert row is not None
    assert row["approval_state"] == "candidate"
    assert row["canonical"] in (0, False)
    assert row["source_kind"] == "generated"
    assert row["kind"] == "character_face"
    assert row["target_type"] == "character" and row["target_id"] == "chr_1"
    assert row["source_shot_id"] == "casting:job-1"


def test_casting_sync_is_idempotent(service, storage, monkeypatch, tmp_path):
    """Re-syncing a finished set updates in place instead of duplicating."""
    url = _back_casing_file(monkeypatch, tmp_path, "film-a", "chr_1", "b" * 32 + ".png")
    _save_character(storage, _casting_character("film-a", "chr_1", [_casting_job("job-1", [url])]))

    first = service.sync_creator_references("film-a")
    second = service.sync_creator_references("film-a")

    assert first["casting_candidates"] == 1
    assert second["casting_candidates"] == 0
    assert second["synced"] == 0
    rows = [row for row in storage.list_reference_assets("film-a") if row["ref_id"] == _casting_ref_id("job-1", url)]
    assert len(rows) == 1


def test_casting_sync_never_downgrades_an_approved_row(service, storage, monkeypatch, tmp_path):
    """A candidate approved elsewhere stays approved across later syncs."""
    url = _back_casing_file(monkeypatch, tmp_path, "film-a", "chr_1", "c" * 32 + ".png")
    _save_character(storage, _casting_character("film-a", "chr_1", [_casting_job("job-1", [url])]))
    service.sync_creator_references("film-a")
    ref_id = _casting_ref_id("job-1", url)
    assert service.approve_supporting("film-a", ref_id)["approval_state"] == "approved"

    result = service.sync_creator_references("film-a")

    assert result["casting_candidates"] == 0
    assert storage.get_reference_asset(ref_id)["approval_state"] == "approved"


def test_casting_sync_skips_unusable_images(service, storage, monkeypatch, tmp_path):
    """Foreign-folder URLs, bad filenames, and missing files never sync."""
    from app.services import reference_asset_service as service_module

    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: tmp_path / "outputs")
    good = _back_casing_file(monkeypatch, tmp_path, "film-a", "chr_1", "d" * 32 + ".png")
    folder = _casting_look_folder("film-a", "chr_1")
    missing = f"/outputs/{folder}/{'e' * 32}.png"
    _save_character(
        storage,
        _casting_character(
            "film-a",
            "chr_1",
            [_casting_job("job-1", [
                "https://cdn.example/foreign.png",
                f"/outputs/{folder}/not-a-casting-file.png",
                missing,
                good,
            ])],
        ),
    )

    result = service.sync_creator_references("film-a")

    assert result["casting_candidates"] == 1
    rows = storage.list_reference_assets("film-a")
    assert [row["ref_id"] for row in rows] == [_casting_ref_id("job-1", good)]


def test_synced_casting_candidate_is_training_ineligible_until_approved(service, storage, monkeypatch, tmp_path):
    """The R1.2 approved-only gate rejects the synced candidate; approval opens it."""
    from app.models import ProviderConfig
    from app.services.visual_training_service import VisualTrainingService

    url = _back_casing_file(monkeypatch, tmp_path, "film-a", "chr_1", "f" * 32 + ".png")
    _save_character(storage, _casting_character("film-a", "chr_1", [_casting_job("job-1", [url])]))
    service.sync_creator_references("film-a")
    ref_id = _casting_ref_id("job-1", url)

    training = VisualTrainingService(storage=storage)
    training.register_provider_config(ProviderConfig(
        provider_id="fake-trainer", name="Fake", enabled=True, is_simulated=True,
        capabilities=["visual_training"], models=["fake-model"],
    ))
    from app.models import StudioProject

    storage.save_project(StudioProject(project_id="film-a", title="Film A"))

    import pytest

    from app.services.stability import ValidationError

    with pytest.raises(ValidationError, match="not approved for training"):
        training.create_training_job(
            project_id="film-a", visual_model_id=None, target_type="character",
            trigger_word="MAYA", source_asset_ids=[ref_id],
            provider="fake-trainer", provider_model="fake-model", configuration={},
        )
    service.approve_supporting("film-a", ref_id)
    job = training.create_training_job(
        project_id="film-a", visual_model_id=None, target_type="character",
        trigger_word="MAYA", source_asset_ids=[ref_id],
        provider="fake-trainer", provider_model="fake-model", configuration={},
    )
    assert job.status == "pending"


def test_list_route_survives_sync_failure(storage, service, monkeypatch):
    """A sync exception must not turn the read-only listing into a 500."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes.reference_assets import router

    def _boom(project_id):
        raise RuntimeError("sync exploded")

    monkeypatch.setattr("app.routes.reference_assets.reference_asset_service", service)
    monkeypatch.setattr(service, "sync_creator_references", _boom)
    storage.save_reference_asset(
        {
            "ref_id": "ref_keep",
            "project_id": "film-err",
            "kind": "style",
            "image_url": "https://cdn.example/keep.png",
        }
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/api/f51/studio/projects/film-err/reference-assets")

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
