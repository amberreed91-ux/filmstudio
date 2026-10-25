"""Desk gate-summary aggregate — read-only endpoint tests (pass 1, STEP 1c).

Fail-at-HEAD proof: the ``desk-gate-summary`` route does not exist at HEAD,
so every 200-asserting test below fails there with 404. Isolated DBs only
(conftest redirects STUDIO_STORAGE_PATH per process); the live DB is never
opened and the guard suite refuses it.

Covers: ready/blocked/missing/stale/unapproved/over-limit shots, empty
project, second synthetic project, DB fingerprint identical before/after,
and a guard test proving the endpoint creates no job and calls no provider.
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
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, StudioProject
from app.services.render import render_service
from app.services.project_store import project_store
from app.services.runway_prompt_length import RUNWAY_IMAGE_MAX_PROMPT_UTF16, utf16_length
from app.services.scene_production_pipeline_service import scene_production_pipeline_service
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
        "title": f"Desk Gate {project_id}",
        "script_text": SCENE_TEXT,
        "execution_summary": {"scenes": scenes},
    }
    project_store.save_project(payload)
    get_storage("sqlite").save_project(StudioProject(**payload))


def _board(project_id: str, scene_id: str = "scene_001", shot_count: int = 2) -> dict[str, Any]:
    return storyboard_blueprint_service.get_or_create_blueprint(
        project_id=project_id, scene_id=scene_id, shot_count=shot_count
    )


def _approve(shot: Any) -> None:
    storyboard_image_prompt_service.edit_for_shot(shot, image_prompt=SHORT_TEXT, edited_by="creator")
    storyboard_image_prompt_service.approve_for_shot(shot, approved_by="creator")


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


def _shots(detail: dict[str, Any]) -> list[Any]:
    storage = get_storage("sqlite")
    return storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )


# ----------------------------------------------------------------------
# Contract basics
# ----------------------------------------------------------------------


def test_desk_gate_summary_unknown_project_returns_404() -> None:
    client = TestClient(app)
    response = client.get("/api/f51/studio/projects/project_desk_missing/desk-gate-summary")
    assert response.status_code == 404


def test_desk_gate_summary_empty_project_returns_no_scenes() -> None:
    client = TestClient(app)
    project_id = "project_desk_empty"
    _seed_project(project_id, ())
    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["scene_count"] == 0
    assert payload["scenes"] == []
    assert payload["next_action"] == "add_scenes"


def test_desk_gate_summary_scene_without_board_points_to_create() -> None:
    client = TestClient(app)
    project_id = "project_desk_noboard"
    _seed_project(project_id, ("scene_001",))
    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    (scene,) = response.json()["scenes"]
    assert scene["board_state"] == "missing_board"
    assert scene["shots"] == []
    assert scene["next_action"] == "create_board"
    assert scene["blockers"]


# ----------------------------------------------------------------------
# Gate states: unapproved / ready / stale / over-limit / empty / missing
# ----------------------------------------------------------------------


def test_desk_gate_summary_unapproved_prompts_block_with_next_action() -> None:
    client = TestClient(app)
    project_id = "project_desk_unapproved"
    _seed_project(project_id)
    _board(project_id, shot_count=2)

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    (scene,) = response.json()["scenes"]
    assert scene["shot_count"] == 2
    for row in scene["shots"]:
        assert row["d4_state"] == "unapproved"
        assert row["d4_ready"] is False
        assert row["d6_state"] == "unapproved"
        assert row["d6_ready"] is False
        assert row["binding_confirmation"] == "missing"
    assert scene["next_action"] == "approve_image_prompts"
    assert scene["ready_shot_count"] == 0


def test_desk_gate_summary_covers_all_six_send_gate_conditions() -> None:
    client = TestClient(app)
    project_id = "project_desk_six_states"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=5)
    storage = get_storage("sqlite")
    shots = _shots(detail)

    _approve(shots[0])  # ready
    # shots[1] stays proposed -> unapproved
    _approve(shots[2])  # -> stale after canonical change
    shots[2].render_contract.provider_neutral_prompt = (
        str(shots[2].render_contract.provider_neutral_prompt or "") + " An added beat."
    )
    storage.save_storyboard_shot(shots[2])
    _approve(shots[3])  # -> over-limit
    long_text = "y" * (RUNWAY_IMAGE_MAX_PROMPT_UTF16 + 1)
    record = storage.get_storyboard_image_prompt(shots[3].storyboard_shot_id)
    assert record is not None
    storage.save_storyboard_image_prompt(
        {**record, "image_prompt": long_text, "utf16_length": utf16_length(long_text)}
    )
    _approve(shots[4])  # -> empty
    record = storage.get_storyboard_image_prompt(shots[4].storyboard_shot_id)
    assert record is not None
    storage.save_storyboard_image_prompt({**record, "image_prompt": "   "})

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    (scene,) = response.json()["scenes"]
    by_number = {row["shot_number"]: row for row in scene["shots"]}
    assert by_number[1]["d4_state"] == "ready"
    assert by_number[1]["d4_ready"] is True
    assert by_number[1]["d6_state"] == "ready"
    assert by_number[2]["d4_state"] == "unapproved"
    assert by_number[3]["d4_state"] == "stale"
    assert by_number[4]["d4_state"] == "over_limit"
    # Empty approved text passes the D4 row checks; the D6 resolver fails it closed.
    assert by_number[5]["d4_state"] == "ready"
    assert by_number[5]["d6_state"] == "empty"
    assert scene["next_action"] == "approve_image_prompts"

    # Missing: a shot whose prompt row was never written reads as missing.
    ghost = shots[0].model_copy(deep=True)
    ghost.storyboard_shot_id = "sbs_desk_gate_missing_row"
    assert storyboard_image_prompt_service.status_for_shot(ghost)["state"] == "missing"


def test_desk_gate_summary_failed_job_surfaces_latest_status() -> None:
    client = TestClient(app)
    project_id = "project_desk_failed_job"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    storage = get_storage("sqlite")
    storage.save_job(
        RenderJobModel(
            id="job-desk-failed-1",
            project_id=project_id,
            shot_id=shot.shot_id,
            provider="runway",
            status="failed",
            input_payload=RenderJobInput(shot_id=shot.shot_id, prompt="Maya holds the cut."),
            created_at="2026-10-24T10:00:00+00:00",
        )
    )

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    (row,) = response.json()["scenes"][0]["shots"]
    assert row["d4_ready"] is True
    assert row["d6_ready"] is True
    assert row["latest_job_status"] == "failed"
    assert row["latest_job_id"] == "job-desk-failed-1"
    assert row["has_media"] is False
    assert response.json()["scenes"][0]["next_action"] in {"confirm_setting_anchor", "retry_failed_jobs"}


def test_desk_gate_summary_complete_media_marks_coverage() -> None:
    client = TestClient(app)
    project_id = "project_desk_media"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    (shot,) = _shots(detail)
    _approve(shot)
    storage = get_storage("sqlite")
    storage.save_job(
        RenderJobModel(
            id="job-desk-complete-1",
            project_id=project_id,
            shot_id=shot.shot_id,
            provider="runway",
            status="complete",
            input_payload=RenderJobInput(shot_id=shot.shot_id, prompt="Maya holds the cut."),
            output_payload=RenderJobOutput(asset_url="https://cdn.example/desk-shot.mp4"),
            created_at="2026-10-24T11:00:00+00:00",
        )
    )

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    (row,) = response.json()["scenes"][0]["shots"]
    assert row["latest_job_status"] == "complete"
    assert row["has_media"] is True


# ----------------------------------------------------------------------
# Isolation, fingerprint, no-job/no-provider guard
# ----------------------------------------------------------------------


def test_desk_gate_summary_second_project_stays_isolated() -> None:
    client = TestClient(app)
    first = "project_desk_iso_a"
    second = "project_desk_iso_b"
    _seed_project(first)
    _seed_project(second, ("scene_001", "scene_002"))
    _board(first, shot_count=1)

    first_payload = client.get(f"/api/f51/studio/projects/{first}/desk-gate-summary").json()
    second_payload = client.get(f"/api/f51/studio/projects/{second}/desk-gate-summary").json()
    assert first_payload["scene_count"] == 1
    assert first_payload["scenes"][0]["shot_count"] == 1
    assert second_payload["scene_count"] == 2
    assert all(scene["next_action"] == "create_board" for scene in second_payload["scenes"])


def test_desk_gate_summary_absent_prompt_table_is_never_created() -> None:
    """Lazy-table case: a DB predating storyboard_image_prompts keeps no such table."""
    client = TestClient(app)
    project_id = "project_desk_notable"
    _seed_project(project_id)
    _board(project_id, shot_count=1)
    storage = get_storage("sqlite")
    raw = sqlite3.connect(str(storage.db_path))
    try:
        raw.execute("DROP TABLE storyboard_image_prompts")
        raw.commit()
    finally:
        raw.close()
    before = _db_fingerprint()
    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200, response.text
    probe = sqlite3.connect(f"file:{storage.db_path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        probe.close()
    assert "storyboard_image_prompts" not in tables
    assert _db_fingerprint() == before
    row = response.json()["scenes"][0]["shots"][0]
    assert row["d4_state"] == "missing"
    assert row["d6_state"] == "missing"


def test_desk_gate_summary_leaves_db_fingerprint_identical() -> None:
    client = TestClient(app)
    project_id = "project_desk_fingerprint"
    _seed_project(project_id)
    _board(project_id, shot_count=2)

    before = _db_fingerprint()
    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    assert _db_fingerprint() == before


def test_desk_gate_summary_creates_no_job_and_calls_no_provider(monkeypatch) -> None:
    client = TestClient(app)
    project_id = "project_desk_guard"
    _seed_project(project_id)
    _board(project_id, shot_count=2)
    storage = get_storage("sqlite")
    jobs_before = [job.id for job in storage.list_jobs(project_id, limit=500)]

    def _forbidden_prepare(**_kwargs: Any) -> Any:
        raise AssertionError("desk-gate-summary must never prepare a scene batch")

    def _forbidden_submit(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("desk-gate-summary must never submit a render job")

    monkeypatch.setattr(
        scene_production_pipeline_service, "prepare_scene_batch", _forbidden_prepare
    )
    monkeypatch.setattr(render_service, "submit_job", _forbidden_submit)

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200
    assert [job.id for job in storage.list_jobs(project_id, limit=500)] == jobs_before

    # The board aggregate is GET-only: nothing here may accept a write.
    assert client.post(f"/api/f51/studio/projects/{project_id}/desk-gate-summary").status_code == 405


# ----------------------------------------------------------------------
# Anchor truthfulness: set / blocked / unknown are distinct (STEP 1a fix).
# ----------------------------------------------------------------------


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
            "ref_id": "ref_test_anchor_001",
            "project_id": project_id,
            "target_type": "setting",
            "target_id": retired_id,
            "kind": "environment",
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": approval_state,
            "image_url": "https://cdn.example/anchor.jpg",
            "source_kind": "uploaded",
        }
    )


def test_desk_gate_summary_alias_bound_anchor_resolves_set() -> None:
    client = TestClient(app)
    project_id = "project_desk_alias"
    _seed_project(project_id)
    _board(project_id, shot_count=1)
    _seed_alias_anchor(project_id)

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200, response.text
    (row,) = response.json()["scenes"][0]["shots"]
    assert row["setting_anchor"] == "set"
    assert all("Setting anchor" not in blocker for blocker in response.json()["scenes"][0]["blockers"])


def test_desk_gate_summary_missing_project_store_still_evaluates_anchor() -> None:
    """False-blocked regression: without the project-store file the board
    used to report blocked (project_not_found swallowed). The scene the
    board already loaded is sufficient — the anchor is truly evaluated."""
    client = TestClient(app)
    project_id = "project_desk_nostore"
    _seed_project(project_id)
    _board(project_id, shot_count=1)
    _seed_alias_anchor(project_id)
    project_store.delete_project(project_id)

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200, response.text
    (row,) = response.json()["scenes"][0]["shots"]
    assert row["setting_anchor"] == "set"
    assert row["setting_anchor"] != "blocked"


def test_desk_gate_summary_unresolvable_project_reports_unknown_never_blocked(
    monkeypatch,
) -> None:
    from app.services import reference_validation as reference_validation_module
    from app.services.stability import ValidationError

    def _boom(**_kwargs: Any) -> Any:
        raise ValidationError(
            "Generation blocked: Scene scene_001. the project could not be resolved",
            stage="reference_validation",
            metadata={"failure_type": "project_not_found", "scene_id": "scene_001"},
        )

    monkeypatch.setattr(
        reference_validation_module, "resolve_scene_reference_requirements", _boom
    )
    client = TestClient(app)
    project_id = "project_desk_unknown"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    for shot in _shots(detail):
        _approve(shot)

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200, response.text
    scene = response.json()["scenes"][0]
    assert scene["shots"][0]["setting_anchor"] == "unknown"
    assert all(row["setting_anchor"] != "blocked" for row in scene["shots"])
    assert scene["next_action"] == "check_project_data"


def test_desk_gate_summary_unapproved_anchor_still_blocked() -> None:
    """A genuinely unevaluated-against gate (no approved anchor) stays
    blocked — unknown must not swallow real gate failures."""
    client = TestClient(app)
    project_id = "project_desk_unapproved"
    _seed_project(project_id)
    detail = _board(project_id, shot_count=1)
    for shot in _shots(detail):
        _approve(shot)
    _seed_alias_anchor(project_id, approval_state="candidate")

    response = client.get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")
    assert response.status_code == 200, response.text
    scene = response.json()["scenes"][0]
    assert scene["shots"][0]["setting_anchor"] == "blocked"
    assert scene["next_action"] == "confirm_setting_anchor"


def test_desk_gate_summary_anchor_verdicts_stay_project_isolated() -> None:
    ready_project = "project_desk_iso_ready"
    blocked_project = "project_desk_iso_blocked"
    _seed_project(ready_project)
    _board(ready_project, shot_count=1)
    _seed_alias_anchor(ready_project)
    project_store.delete_project(ready_project)
    _seed_project(blocked_project)
    blocked_detail = _board(blocked_project, shot_count=1)
    for shot in _shots(blocked_detail):
        _approve(shot)

    client = TestClient(app)
    ready = client.get(f"/api/f51/studio/projects/{ready_project}/desk-gate-summary").json()
    blocked = client.get(f"/api/f51/studio/projects/{blocked_project}/desk-gate-summary").json()
    assert ready["scenes"][0]["shots"][0]["setting_anchor"] == "set"
    assert blocked["scenes"][0]["shots"][0]["setting_anchor"] == "blocked"
    assert blocked["scenes"][0]["next_action"] == "confirm_setting_anchor"
