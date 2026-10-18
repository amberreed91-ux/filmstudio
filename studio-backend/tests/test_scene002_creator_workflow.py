"""Creator decision workflow tests — scene_002 creator workflow workstream.

Covers the two creator decision classes identified by the creative-readiness
audit (docs/forensics/SCENE002_CREATIVE_READINESS_20260927.md):

1. Camera approval (``PrevisService.approve_ai_camera`` + its HTTP route):
   one explicit creator decision per shot, version-bound, immutable-approved
   board respected, single-shot scope, never provider-facing.
2. Canonical setting workflow (previs approve → sync_creator_references):
   scene-bound, duplicate-safe, and never triggered by mere viewing.

Every test asserts the recovered creative state is never silently mutated and
that no provider is contacted by any approval action.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage, get_storage
from app.models.storyboard_blueprint import (
    StoryboardShot,
    StoryboardShotRenderContract,
    StoryboardShotStatus,
    StoryboardShotVisualPlan,
)
from app.services.previs_service import PrevisService
from app.services.reference_asset_service import ReferenceAssetService, _env_ref_id
from app.services.stability import StateError

PROJECT = "project_5907c60cddbc"
SCENE = "scene_002"
OTHER_SCENE = "scene_001"
APPROVED_VERSION = "sbv_3b88a1e0ef95"
FRAMING = "Wide establishing shot. Camera far back. Full environment visible."


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def storage(tmp_path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "creator_workflow.db"))


@pytest.fixture
def service(storage: DatabaseStorage) -> PrevisService:
    # A renderer mock that fails ANY provider interaction: approval actions
    # must never reach a provider, so any call here fails the test loudly.
    renderer = MagicMock(side_effect=AssertionError("Provider must never be called by an approval action"))
    return PrevisService(storage=storage, renderer=renderer)


@pytest.fixture
def reference_service(storage: DatabaseStorage) -> ReferenceAssetService:
    return ReferenceAssetService(storage)


def _shot(
    storyboard_shot_id: str,
    shot_number: int,
    *,
    version_id: str = APPROVED_VERSION,
    project_id: str = PROJECT,
    scene_id: str = SCENE,
    status: StoryboardShotStatus = StoryboardShotStatus.APPROVED,
    camera_plan: dict[str, str] | None = None,
) -> StoryboardShot:
    structured: dict[str, Any] = {"duration": 5, "ratio": "16:9"}
    if camera_plan is not None:
        structured["camera_plan"] = camera_plan
    return StoryboardShot(
        storyboard_shot_id=storyboard_shot_id,
        blueprint_id="sbp_test",
        version_id=version_id,
        project_id=project_id,
        scene_id=scene_id,
        shot_id=f"{scene_id}_shot_{shot_number:03d}",
        shot_number=shot_number,
        status=status,
        visual_plan=StoryboardShotVisualPlan(framing=FRAMING),
        render_contract=StoryboardShotRenderContract(
            provider_neutral_prompt="Recovered board prompt.",
            structured_parameters=structured,
        ),
    )


def _install_board(storage: DatabaseStorage, shots: list[StoryboardShot]) -> None:
    # create_version resolves the scene through the project store/storage.
    from app.models import StudioProject
    from app.services.project_store import project_store

    project = {
        "project_id": PROJECT,
        "title": "I was reborn",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": SCENE,
                    "heading": "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE",
                    "text": "The frozen train sleeps across the river.",
                    "updated_at": "2026-09-26T00:00:00Z",
                },
                {
                    "scene_id": OTHER_SCENE,
                    "heading": "INT. APARTMENT - NIGHT",
                    "text": "Another scene entirely.",
                    "updated_at": "2026-09-26T00:00:00Z",
                },
            ]
        },
    }
    project_store.save_project(project)
    try:
        storage.save_project(StudioProject(**project))
    except Exception:
        pass

    storage.save_storyboard_blueprint(
        {
            "blueprint_id": "sbp_test",
            "project_id": PROJECT,
            "scene_id": SCENE,
            "current_version_id": APPROVED_VERSION,
            "approved_version_id": APPROVED_VERSION,
            "status": "approved",
        }
    )
    version_row = {
        "version_id": APPROVED_VERSION,
        "blueprint_id": "sbp_test",
        "project_id": PROJECT,
        "scene_id": SCENE,
        "version_number": 2,
        "status": "approved",
        "change_reason": "recovered",
    }
    storage.save_storyboard_blueprint_version(version_row)
    for shot in shots:
        storage.save_storyboard_shot(shot)


# ── Camera approval: service semantics ───────────────────────────────────────


def _board_shots(storage: DatabaseStorage) -> list[StoryboardShot]:
    return [
        _shot("sbs_a7648698ad00", 1),
        _shot("sbs_a8481a439ea5", 2),
        _shot("sbs_be2cce8fab93", 3),
        _shot("sbs_51d1500d227c", 4),
        _shot("sbs_0046fb5192f0", 5),
    ]


def test_creator_can_approve_one_camera_decision(service, storage):
    _install_board(storage, _board_shots(storage))
    result = service.approve_ai_camera(PROJECT, SCENE, "sbs_a7648698ad00")

    assert result["approved_by"] == "creator"
    assert result["approved_camera"] == {"framing": FRAMING}
    assert result["version_id"] != APPROVED_VERSION, "approval must land on a NEW draft version"
    draft = storage.get_storyboard_shot(result["storyboard_shot_id"])
    assert draft is not None
    plan = draft.render_contract.structured_parameters["camera_plan"]
    assert plan == {"framing": FRAMING}
    assert draft.metadata["last_change_reason"].startswith("AI_CAMERA_APPROVED_BY_USER:")


def test_one_approval_does_not_approve_the_other_four(service, storage):
    _install_board(storage, _board_shots(storage))
    service.approve_ai_camera(PROJECT, SCENE, "sbs_a7648698ad00")

    draft_version = storage.get_storyboard_blueprint_by_id("sbp_test").current_version_id
    clones = storage.list_storyboard_shots("sbp_test", draft_version)
    assert len(clones) == 5
    approved_clones = [
        shot
        for shot in clones
        if isinstance(shot.render_contract.structured_parameters, dict)
        and isinstance(shot.render_contract.structured_parameters.get("camera_plan"), dict)
    ]
    assert len(approved_clones) == 1, "exactly the requested shot may receive the camera plan"
    assert approved_clones[0].shot_number == 1


def test_approved_storyboard_version_remains_immutable(service, storage):
    _install_board(storage, _board_shots(storage))
    before = storage.get_storyboard_shot("sbs_a7648698ad00")
    service.approve_ai_camera(PROJECT, SCENE, "sbs_a7648698ad00")

    after = storage.get_storyboard_shot("sbs_a7648698ad00")
    assert after.version_id == before.version_id == APPROVED_VERSION
    assert after.render_contract.model_dump(mode="json") == before.render_contract.model_dump(mode="json")
    assert after.updated_at == before.updated_at
    assert "camera_plan" not in after.render_contract.structured_parameters


def test_stale_version_is_rejected(service, storage):
    _install_board(storage, _board_shots(storage))
    with pytest.raises(StateError) as excinfo:
        service.approve_ai_camera(
            PROJECT, SCENE, "sbs_a7648698ad00", expected_version_id="sbv_superseded_000"
        )
    assert excinfo.value.metadata["expected_version_id"] == "sbv_superseded_000"
    # Nothing changed anywhere.
    assert storage.get_storyboard_blueprint_by_id("sbp_test").current_version_id == APPROVED_VERSION


def test_matching_version_is_accepted(service, storage):
    _install_board(storage, _board_shots(storage))
    result = service.approve_ai_camera(
        PROJECT, SCENE, "sbs_a7648698ad00", expected_version_id=APPROVED_VERSION
    )
    assert result["approved_camera"]["framing"] == FRAMING


def test_already_approved_shot_refuses_double_approval(service, storage):
    approved_shot = _shot(
        "sbs_approved", 1, camera_plan={"framing": FRAMING}, status=StoryboardShotStatus.READY
    )
    storage.save_storyboard_blueprint(
        {
            "blueprint_id": "sbp_test",
            "project_id": PROJECT,
            "scene_id": SCENE,
            "current_version_id": "sbv_draft_1",
            "approved_version_id": None,
            "status": "draft",
        }
    )
    storage.save_storyboard_shot(approved_shot)

    with pytest.raises(StateError) as excinfo:
        service.approve_ai_camera(PROJECT, SCENE, "sbs_approved")
    assert "No AI-suggested camera values" in str(excinfo.value)


def test_scene_001_cannot_satisfy_scene_002_camera_state(service, storage):
    """A scene_001 shot id must never be approvable through scene_002's path."""
    _install_board(storage, _board_shots(storage))
    foreign = _shot("sbs_scene001_shot", 1, scene_id=OTHER_SCENE, version_id="sbv_scene001_v1")
    storage.save_storyboard_shot(foreign)

    with pytest.raises(StateError) as excinfo:
        service.approve_ai_camera(PROJECT, SCENE, "sbs_scene001_shot")
    assert "not found in project scene" in str(excinfo.value)
    # scene_002 board untouched: still on the approved version.
    assert storage.get_storyboard_blueprint_by_id("sbp_test").current_version_id == APPROVED_VERSION


def test_cross_project_shot_refused(service, storage):
    _install_board(storage, _board_shots(storage))
    foreign = _shot("sbs_other_project", 1, project_id="project_someone_else")
    storage.save_storyboard_shot(foreign)

    with pytest.raises(StateError):
        service.approve_ai_camera(PROJECT, SCENE, "sbs_other_project")


def test_locked_shot_cannot_be_approved(service, storage):
    locked = _shot("sbs_locked", 1)
    locked.locked = True
    storage.save_storyboard_blueprint(
        {
            "blueprint_id": "sbp_test",
            "project_id": PROJECT,
            "scene_id": SCENE,
            "current_version_id": "sbv_draft_1",
            "approved_version_id": None,
            "status": "draft",
        }
    )
    storage.save_storyboard_shot(locked)

    with pytest.raises(StateError) as excinfo:
        service.approve_ai_camera(PROJECT, SCENE, "sbs_locked")
    assert "locked" in str(excinfo.value).lower()


# ── Camera approval: HTTP route ──────────────────────────────────────────────


@pytest.fixture
def api(monkeypatch, storage: DatabaseStorage):
    from main import app
    from app.routes import previs_routes

    monkeypatch.setattr(previs_routes, "previs_service", PrevisService(storage=storage, renderer=MagicMock()))
    client = TestClient(app)
    return client


def test_camera_approval_route_creates_expected_draft_version(api, storage):
    _install_board(storage, _board_shots(storage))
    response = api.post(
        f"/api/f51/studio/projects/{PROJECT}/scenes/{SCENE}/camera-approvals/sbs_a7648698ad00",
        json={"approved_by": "creator", "expected_version_id": APPROVED_VERSION},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["approved_camera"] == {"framing": FRAMING}
    assert payload["version_id"] != APPROVED_VERSION

    draft = storage.get_storyboard_shot(payload["storyboard_shot_id"])
    assert draft.render_contract.structured_parameters["camera_plan"] == {"framing": FRAMING}


def test_camera_approval_route_records_exactly_which_decision(api, storage):
    _install_board(storage, _board_shots(storage))
    response = api.post(
        f"/api/f51/studio/projects/{PROJECT}/scenes/{SCENE}/camera-approvals/sbs_a7648698ad00",
        json={"approved_by": "director_rana", "expected_version_id": APPROVED_VERSION},
    )
    assert response.status_code == 200
    draft = storage.get_storyboard_shot(response.json()["storyboard_shot_id"])
    assert draft.metadata["last_change_reason"] == f"AI_CAMERA_APPROVED_BY_USER:director_rana"


def test_camera_approval_route_refuses_stale_version(api, storage):
    _install_board(storage, _board_shots(storage))
    response = api.post(
        f"/api/f51/studio/projects/{PROJECT}/scenes/{SCENE}/camera-approvals/sbs_a7648698ad00",
        json={"approved_by": "creator", "expected_version_id": "sbv_old_123456"},
    )
    assert response.status_code == 409
    assert "no longer belongs" in response.text


def test_camera_approval_route_never_batches(api, storage):
    """The route has no batch mode: one URL, one shot."""
    _install_board(storage, _board_shots(storage))
    response = api.post(
        f"/api/f51/studio/projects/{PROJECT}/scenes/{SCENE}/camera-approvals/sbs_a7648698ad00",
        json={"approved_by": "creator", "expected_version_id": APPROVED_VERSION},
    )
    assert response.status_code == 200
    draft_version = storage.get_storyboard_blueprint_by_id("sbp_test").current_version_id
    clones = storage.list_storyboard_shots("sbp_test", draft_version)
    assert len(clones) == 5
    assert sum(
        1
        for shot in clones
        if isinstance(shot.render_contract.structured_parameters, dict)
        and isinstance(shot.render_contract.structured_parameters.get("camera_plan"), dict)
    ) == 1


# ── Canonical setting workflow (previs approve → sync) ───────────────────────


def _previs_row(scene_id: str, *, approved: bool = False, status: str = "complete", path: str | None = None) -> dict:
    return {
        "id": f"previs_{scene_id}_main",
        "project_id": PROJECT,
        "scene_id": scene_id,
        "shot_id": f"{scene_id}_shot_001",
        "storyboard_shot_id": None,
        "image_path": path or f"/previs-assets/{PROJECT}/{scene_id}_frame.png",
        "job_id": f"job_{scene_id}",
        "status": status,
        "prompt_used": "test",
        "fallback": False,
        "approved": approved,
        "created_at": "2026-09-21T10:00:00",
        "updated_at": "2026-09-21T10:00:00",
    }


def _save_previs_rows(storage: DatabaseStorage, rows: list[dict]) -> None:
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
            image_id=row["id"],
        )
        if row["approved"]:
            # Production approve path: approve_previs_image flips approved=1,
            # status='approved' and supersedes any previously approved row.
            approved = storage.approve_previs_image(row["id"], row["project_id"], "creator")
            assert approved is not None, "fixture approval must succeed for a complete row"


def test_canonical_setting_workflow_creates_exactly_one_canonical_reference(reference_service, storage):
    _save_previs_rows(storage, [_previs_row(SCENE, approved=True, status="approved")])

    result = reference_service.sync_creator_references(PROJECT)

    assert result["environment_stills"] == 1
    rows = storage.list_reference_assets(PROJECT, kind="environment")
    canonical = [row for row in rows if row.get("canonical")]
    assert len(canonical) == 1
    row = canonical[0]
    assert row["ref_id"] == _env_ref_id(PROJECT, SCENE)
    assert row["target_type"] == "setting"
    assert row["target_id"] == SCENE
    assert row["canonical"] == 1 or row["canonical"] is True
    assert row["approval_state"] == "approved"
    assert row["kind"] == "environment"
    assert row["source_kind"] == "confirmed"


def test_approved_previs_with_status_approved_syncs(reference_service, storage):
    """The gap fix: ``approve_previs_image`` sets status='approved'; the sync
    must still mint the canonical row (previously complete-only)."""
    _save_previs_rows(storage, [_previs_row(SCENE, approved=True, status="approved")])
    result = reference_service.sync_creator_references(PROJECT)
    assert result["environment_stills"] == 1


def test_unapproved_previs_does_not_become_canonical(reference_service, storage):
    """Merely completing a render does NOT approve it: viewing is not approval."""
    _save_previs_rows(storage, [_previs_row(SCENE, approved=False, status="complete")])
    result = reference_service.sync_creator_references(PROJECT)
    assert result["environment_stills"] == 0
    assert storage.list_reference_assets(PROJECT) == []


def test_scene_001_cannot_become_scene_002_canonical_setting(reference_service, storage):
    """A scene_001 approved previs must mint only a scene_001 anchor — never
    satisfy scene_002's canonical setting requirement."""
    _save_previs_rows(
        storage,
        [
            _previs_row(SCENE, approved=False, status="complete"),
            _previs_row(OTHER_SCENE, approved=True, status="approved"),
        ],
    )
    result = reference_service.sync_creator_references(PROJECT)

    assert result["environment_stills"] == 1
    rows = storage.list_reference_assets(PROJECT, kind="environment")
    scene_002_canonical = [
        row
        for row in rows
        if row.get("target_id") == SCENE and (row.get("canonical") in (1, True))
    ]
    assert scene_002_canonical == [], "scene_001 asset must never satisfy scene_002"
    scene_001_canonical = [
        row for row in rows if row.get("target_id") == OTHER_SCENE and (row.get("canonical") in (1, True))
    ]
    assert len(scene_001_canonical) == 1
    assert scene_001_canonical[0]["ref_id"] == _env_ref_id(PROJECT, OTHER_SCENE)


def test_duplicate_canonical_setting_references_are_rejected(reference_service, storage):
    """Re-syncing is idempotent: the deterministic ref_id upserts in place —
    the workflow can never mint a second canonical row for a scene."""
    _save_previs_rows(storage, [_previs_row(SCENE, approved=True, status="approved")])
    reference_service.sync_creator_references(PROJECT)
    reference_service.sync_creator_references(PROJECT)

    rows = storage.list_reference_assets(PROJECT, kind="environment")
    canonical = [row for row in rows if row.get("canonical") in (1, True)]
    assert len(canonical) == 1
    assert len(rows) == 1


def test_merely_viewing_a_reference_does_not_approve_it(reference_service, storage):
    """Listing the reference library syncs approvals but must not promote
    candidates or unapproved rows into the canonical slot."""
    _save_previs_rows(storage, [_previs_row(SCENE, approved=False, status="complete")])

    reference_service.sync_creator_references(PROJECT)  # what the list endpoint does
    listing = reference_service.list_assets(PROJECT, "environment")

    assert listing == []
    assert storage.list_reference_assets(PROJECT) == []


def test_previs_approval_sets_flag_without_generation(service, storage, reference_service):
    """The approval service method flips the previs flag only — no provider
    interaction, no regeneration — and the synced row carries the same URL."""
    _save_previs_rows(storage, [_previs_row(SCENE, approved=False, status="complete")])
    row = storage.get_previs_image("previs_scene_002_main")
    approved = storage.approve_previs_image("previs_scene_002_main", PROJECT, "creator")
    assert approved is not None
    assert approved["approved"] is True
    assert approved["status"] == "approved"

    result = reference_service.sync_creator_references(PROJECT)
    assert result["environment_stills"] == 1
    canonical = [
        r for r in storage.list_reference_assets(PROJECT, kind="environment") if r.get("canonical") in (1, True)
    ][0]
    assert canonical["image_url"] == row["image_path"]


# ── Global invariants ────────────────────────────────────────────────────────


def test_camera_approval_never_touches_script_or_recovery_state(api, storage):
    _install_board(storage, _board_shots(storage))
    script_before = storage.get_project(PROJECT)
    lineage_before = storage.list_studio_version_lineage(PROJECT) if hasattr(storage, "list_studio_version_lineage") else None

    response = api.post(
        f"/api/f51/studio/projects/{PROJECT}/scenes/{SCENE}/camera-approvals/sbs_a7648698ad00",
        json={"approved_by": "creator", "expected_version_id": APPROVED_VERSION},
    )
    assert response.status_code == 200

    script_after = storage.get_project(PROJECT)
    assert (script_after.model_dump(mode="json") if hasattr(script_after, "model_dump") else script_after) == (
        script_before.model_dump(mode="json") if hasattr(script_before, "model_dump") else script_before
    )
    if lineage_before is not None:
        assert storage.list_studio_version_lineage(PROJECT) == lineage_before


def test_approval_actions_never_call_providers(service, storage):
    """The renderer mock raises on ANY call — a passing approval proves the
    action stayed entirely inside the local storage workflow."""
    _install_board(storage, _board_shots(storage))
    result = service.approve_ai_camera(PROJECT, SCENE, "sbs_a7648698ad00")
    assert result["approved_camera"]
    service._renderer.assert_not_called()


def test_route_registry_contains_no_batch_camera_endpoint():
    """Fail loudly if someone later adds a whole-scene camera approval — the
    audit requires decisions to stay per-shot and explicit."""
    from main import app

    # Enumerate through the OpenAPI schema — the canonical path registry that
    # stays correct regardless of how this FastAPI version wraps routers
    # internally (_IncludedRouter objects expose no reliable .path).
    schema_paths = set(app.openapi().get("paths") or {})
    camera_paths = {p for p in schema_paths if "camera-approval" in p}
    assert camera_paths == {
        f"/api/f51/studio/projects/{{project_id}}/scenes/{{scene_id}}/camera-approvals/{{storyboard_shot_id}}"
    }, camera_paths
