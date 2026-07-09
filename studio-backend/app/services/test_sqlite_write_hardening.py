from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobModel, RenderJobOutput, StudioProject


def _make_storage(tmp_path):
    return DatabaseStorage(str(tmp_path / "storage"))


def test_write_retry_succeeds_after_transient_lock(tmp_path):
    storage = _make_storage(tmp_path)
    calls = {"n": 0}

    def _op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    result = storage._execute_write_with_retry("unit_test_retry", _op)
    assert result == "ok"
    assert calls["n"] == 3


def test_write_retry_does_not_swallow_non_lock_errors(tmp_path):
    storage = _make_storage(tmp_path)

    def _op():
        raise sqlite3.OperationalError("no such table: missing")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        storage._execute_write_with_retry("unit_test_non_lock", _op)


def test_save_job_still_enforces_foreign_key_when_schema_requires_parent(tmp_path):
    storage = _make_storage(tmp_path)

    with storage._get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS render_jobs")
        conn.execute("DROP TABLE IF EXISTS projects")
        conn.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.execute(
            """
            CREATE TABLE render_jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                shot_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_job_id TEXT,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL,
                input_payload TEXT,
                output_payload TEXT,
                error_message TEXT,
                last_polled_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                recovery_status TEXT NOT NULL DEFAULT 'none',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(project_id)
            )
            """
        )
        conn.commit()

    job = RenderJobModel(
        id="job-fk-test",
        project_id="missing-project",
        shot_id="shot_001",
        provider="runway",
        status="complete",
        progress=100,
        output_payload=RenderJobOutput(asset_url="/outputs/mock-video/sample.mp4"),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )

    with pytest.raises(sqlite3.IntegrityError):
        storage.save_job(job)


def test_save_project_works_with_schema_variants(tmp_path):
    storage = _make_storage(tmp_path)

    project = StudioProject(project_id="project-schema-variant", title="Schema Variant")

    # Variant A: with updated_at only
    with storage._get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS projects")
        conn.execute(
            "CREATE TABLE projects (project_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.commit()
    storage.save_project(project)

    with storage._get_connection() as conn:
        row = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (project.project_id,)).fetchone()
        assert row is not None

    # Variant B: minimal schema
    with storage._get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS projects")
        conn.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.commit()
    storage.save_project(project)

    with storage._get_connection() as conn:
        row = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (project.project_id,)).fetchone()
        assert row is not None


def test_save_job_persists_after_retry_wrapper(tmp_path):
    storage = _make_storage(tmp_path)
    project = StudioProject(project_id="project-persist", title="Persist")
    storage.save_project(project)

    job = RenderJobModel(
        id="job-persist-001",
        project_id=project.project_id,
        shot_id="scene_001_shot_001",
        provider="runway",
        status="complete",
        progress=100,
        output_payload=RenderJobOutput(asset_url="/outputs/mock-video/sample.mp4"),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )

    storage.save_job(job)
    persisted = storage.get_job(job.id)
    assert persisted is not None
    assert persisted.id == job.id
    assert persisted.project_id == project.project_id
    assert (persisted.output_payload.asset_url if persisted.output_payload else None) == "/outputs/mock-video/sample.mp4"


def test_sqlite_pragmas_wal_and_busy_timeout_applied(tmp_path):
    storage = _make_storage(tmp_path)
    with storage._get_connection() as conn:
        journal_row = conn.execute("PRAGMA journal_mode").fetchone()
        busy_row = conn.execute("PRAGMA busy_timeout").fetchone()
        fk_row = conn.execute("PRAGMA foreign_keys").fetchone()

    assert journal_row is not None
    assert str(journal_row[0]).lower() == "wal"
    assert busy_row is not None
    assert int(busy_row[0]) >= 5000
    assert fk_row is not None
    assert int(fk_row[0]) == 1
