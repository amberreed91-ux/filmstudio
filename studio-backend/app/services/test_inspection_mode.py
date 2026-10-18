from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.inspect_scene_direction_snapshot import (
    APPROVED_VERSION_ID,
    LIVE_DB,
    PROJECT_ID,
    SCENE_ID,
    ReadOnlySceneStorage,
    _copied_db,
    _semantic_snapshot,
    check_inspection_decision_state,
)


ROOT = Path(__file__).resolve().parents[2]


def _inspect_in_subprocess(copy: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = """
import json, os, sys
from pathlib import Path
copy = Path(sys.argv[1])
os.environ['STUDIO_PROJECT_STORE_PATH'] = str(copy.parent / 'isolated-project-state.json')
import scripts.inspect_scene_direction_snapshot as module
report = module.inspect_scene(copy)
print(json.dumps(report))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(copy)], cwd=ROOT, env=env,
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_inspection_import_skips_normal_lifecycle_singletons_and_creates_no_data(tmp_path):
    copy = _copied_db(tmp_path, LIVE_DB)
    report = _inspect_in_subprocess(copy)
    assert report["version_id"] == APPROVED_VERSION_ID
    assert report["inspection_port"] is None
    assert report["runtime_database_is_live_database"] is False
    assert report["singleton_storage_redirected_to_copy"] is True
    assert report["project_store_file_created"] is False
    assert report["imported_inspection_modules"] == {
        "scene_direction_service": True,
        "scene_coverage_contract": True,
        "scene_direction_models": True,
        "storyboard_models": True,
    }
    assert report["runtime_guards"]["readonly_copy_connections"] > 0
    assert report["runtime_guards"]["worker_thread_start_attempts"] == 0
    assert report["runtime_guards"]["network_attempts"] == 0
    assert report["runtime_guards"]["process_start_attempts"] == 0
    assert all(not imported for imported in report["isolated_imports"].values())
    assert not (copy.parent / "isolated-project-state.json").exists()


def test_inspection_uses_immutable_readonly_copy_and_never_live_path(tmp_path):
    copy = _copied_db(tmp_path, LIVE_DB)
    before = {suffix: _sha256(Path(str(copy) + suffix)) if Path(str(copy) + suffix).exists() else None
              for suffix in ("", "-wal", "-shm")}
    before_live = _sha256(LIVE_DB)
    storage = ReadOnlySceneStorage(copy)
    report = _inspect_in_subprocess(copy)
    after = {suffix: _sha256(Path(str(copy) + suffix)) if Path(str(copy) + suffix).exists() else None
             for suffix in ("", "-wal", "-shm")}
    assert storage.db_path != LIVE_DB.resolve()
    assert not os.path.samefile(storage.db_path, LIVE_DB)
    assert before == after
    assert before_live == _sha256(LIVE_DB)
    assert report["version_id"] == APPROVED_VERSION_ID
    assert report["runtime_database_is_live_database"] is False
    assert report["schema_mutation_possible"] is False
    assert report["project_store_file_created"] is False
    assert report["coverage"] == {
        "content_obligations": 40,
        "dialogue_obligations": 10,
        "shot_content_dispositions": 5,
        "shot_dialogue_dispositions": 5,
    }
    assert report["saved"] is report["saved_decisions_present"]
    if report["decision_assertions_skipped"]:
        # The approved board legitimately carries creator decisions; only the
        # pristine-state gates are bypassed, never content or isolation gates.
        assert report["saved_decisions_present"] is True
    else:
        assert report["saved"] is False
    assert report["unassigned_obligations"] == 50
    if not report["decision_assertions_skipped"]:
        assert report["decision_status_counts"]["UNASSIGNED"] == 60
    assert report["provider_contacted"] is False
    assert report["job_created"] is False
    assert report["render_occurred"] is False
    assert report["queues_started"] is False
    assert report["runway_polling_started"] is False
    assert report["job_recovery_called"] is False
    assert report["lease_recovery_called"] is False
    assert report["training_refresh_called"] is False
    assert report["backup_created"] is False
    assert report["demo_seed_called"] is False


def test_service_read_calls_are_bounded_and_no_write_or_job_methods_are_used(tmp_path):
    copy = _copied_db(tmp_path, LIVE_DB)
    storage = ReadOnlySceneStorage(copy)
    with pytest.raises(sqlite3.OperationalError):
        with storage._connect() as connection:
            connection.execute("CREATE TABLE inspection_must_not_write(value INTEGER)")
    result = _inspect_in_subprocess(copy)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    # The live board carries a later draft; inspection must still select approved.
    assert blueprint.current_version_id != blueprint.approved_version_id
    assert result["version_id"] == blueprint.approved_version_id == APPROVED_VERSION_ID
    # The second get_project call supports the scene setting identity read model;
    # both project reads are bounded and read-only.
    assert result["storage_calls"] == [
        "get_storyboard_blueprint",
        "get_storyboard_blueprint_version",
        "list_storyboard_shots",
        "get_project",
        "get_project",
    ]
    assert result["production_storage_guards"] == {
        "production_storage_factory_called": False,
        "database_storage_initialized": False,
        "inspection_storage_factory_calls": 1,
        "singleton_storage_redirected_to_copy": True,
    }
    assert result["runtime_database_is_live_database"] is False
    assert result["schema_mutation_possible"] is False
    assert result["runtime_guards"]["worker_thread_start_attempts"] == 0
    assert result["runtime_guards"]["network_attempts"] == 0
    assert result["runtime_guards"]["process_start_attempts"] == 0
    assert result["database_storage_initialized"] is False
    assert result["production_storage_factory_called"] is False
    assert result["inspection_storage_factory_calls"] == 1
    assert result["coverage"]["content_obligations"] == 40
    assert result["coverage"]["dialogue_obligations"] == 10
    assert result["unassigned_obligations"] == 50
    if not result["decision_assertions_skipped"]:
        assert result["decision_status_counts"]["UNASSIGNED"] == 60
    assert result["provider_contacted"] is False
    assert result["job_created"] is False
    assert result["render_occurred"] is False
    assert result["queues_started"] is False
    assert result["runway_polling_started"] is False
    assert result["job_recovery_called"] is False
    assert result["lease_recovery_called"] is False
    assert result["training_refresh_called"] is False
    assert result["backup_created"] is False
    assert result["demo_seed_called"] is False


def test_inspection_runtime_keeps_all_five_approved_prompts_camera_and_references_identical(tmp_path):
    copy = _copied_db(tmp_path, LIVE_DB)
    storage = ReadOnlySceneStorage(copy)
    before = _semantic_snapshot(storage, PROJECT_ID, SCENE_ID)
    report = _inspect_in_subprocess(copy)
    after = _semantic_snapshot(storage, PROJECT_ID, SCENE_ID)
    assert before == after
    assert before["version_id"] == APPROVED_VERSION_ID
    assert before["version_status"] == "approved"
    assert before["expected_shot_count"] == 5
    assert len(before["prompt_hashes"]) == 5
    assert len(before["camera_plan_hashes"]) == 5
    assert before["reference_hashes"]["DRE"]
    assert before["reference_hashes"]["MAYA"]
    assert before["reference_hashes"]["environment"]
    assert report["saved"] is report["saved_decisions_present"]
    if report["decision_assertions_skipped"]:
        assert report["saved_decisions_present"] is True
    else:
        assert report["saved"] is False
    assert report["creator_decisions_recorded"] is False
    assert report["runtime_database_is_live_database"] is False
    assert report["coverage"]["content_obligations"] == 40
    assert report["coverage"]["dialogue_obligations"] == 10
    assert report["unassigned_obligations"] == 50
    if not report["decision_assertions_skipped"]:
        assert report["decision_status_counts"]["UNASSIGNED"] == 60
    assert report["provider_contacted"] is False
    assert report["job_created"] is False
    assert report["render_occurred"] is False
    assert report["queues_started"] is False
    assert report["runway_polling_started"] is False
    assert report["job_recovery_called"] is False
    assert report["lease_recovery_called"] is False
    assert report["training_refresh_called"] is False
    assert report["backup_created"] is False
    assert report["demo_seed_called"] is False
    assert report["runtime_guards"]["network_attempts"] == 0
    assert report["runtime_guards"]["process_start_attempts"] == 0
    assert report["runtime_guards"]["worker_thread_start_attempts"] == 0


def test_inspection_rejects_the_live_database_path(tmp_path):
    with pytest.raises(RuntimeError, match="live DB"):
        ReadOnlySceneStorage(LIVE_DB)


def _decision_gate_direction(*, saved, decision_statuses, obligation_statuses):
    from types import SimpleNamespace

    from app.models.scene_direction import CoverageDecision, CoverageObligation

    return SimpleNamespace(
        saved=saved,
        coverage_decisions=[
            CoverageDecision(obligation_type="content", obligation_id=f"c{i}", status=status,
                             shot_id="scene_002_shot_001" if status == "ASSIGNED" else None)
            for i, status in enumerate(decision_statuses)
        ],
        coverage_obligations=[
            CoverageObligation(obligation_type="dialogue", obligation_id=f"d{i}",
                               source_text="line", status=status,
                               shot_id="scene_002_shot_001" if status == "ASSIGNED" else None)
            for i, status in enumerate(obligation_statuses)
        ],
    )


def test_decision_gates_pass_for_pristine_direction():
    direction = _decision_gate_direction(
        saved=False,
        decision_statuses=["UNASSIGNED", "UNASSIGNED"],
        obligation_statuses=["UNASSIGNED"],
    )
    assert check_inspection_decision_state(direction) is False


def test_decision_gates_skip_only_for_saved_direction():
    direction = _decision_gate_direction(
        saved=True,
        decision_statuses=["ASSIGNED", "UNASSIGNED"],
        obligation_statuses=["ASSIGNED"],
    )
    assert check_inspection_decision_state(direction) is True


def test_decision_gates_raise_for_assigned_rows_without_saved_state():
    direction = _decision_gate_direction(
        saved=False,
        decision_statuses=["ASSIGNED"],
        obligation_statuses=["UNASSIGNED"],
    )
    with pytest.raises(RuntimeError, match="Unexpected creator decision"):
        check_inspection_decision_state(direction)
