from __future__ import annotations

import sqlite3
import os
from pathlib import Path

import pytest

from app.services.database_backup import DatabaseBackup


@pytest.fixture
def backup_dir(tmp_path):
    return str(tmp_path / "backups")


@pytest.fixture
def sample_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test (value) VALUES ('hello')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def db_backup(sample_db, backup_dir):
    return DatabaseBackup(db_path=sample_db, backup_dir=backup_dir, max_backups=3)


class TestDatabaseBackup:
    def test_creates_backup_directory(self, tmp_path):
        backup_dir = str(tmp_path / "new_backups")
        assert not os.path.exists(backup_dir)
        db_backup = DatabaseBackup(db_path="/dev/null", backup_dir=backup_dir)
        assert os.path.exists(backup_dir)

    def test_create_backup_produces_file(self, db_backup):
        result = db_backup.create_backup()
        assert "backup_path" in result
        assert os.path.exists(result["backup_path"])
        assert result["size_bytes"] > 0
        assert result["duration_ms"] >= 0

    def test_backup_is_valid_sqlite(self, db_backup):
        result = db_backup.create_backup()
        conn = sqlite3.connect(result["backup_path"])
        cursor = conn.execute("SELECT value FROM test WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        assert row == ("hello",)

    def test_backup_filename_has_prefix(self, db_backup):
        result = db_backup.create_backup()
        filename = os.path.basename(result["backup_path"])
        assert filename.startswith("studio_")
        assert filename.endswith(".db")

    def test_backup_rotation_respects_max(self, db_backup):
        paths = []
        for _ in range(5):
            paths.append(db_backup.create_backup())
        status = db_backup.get_status()
        assert status["total_backups"] <= 3

    def test_get_status_empty(self, tmp_path):
        db_backup = DatabaseBackup(
            db_path=str(tmp_path / "dummy.db"),
            backup_dir=str(tmp_path / "empty_backups"),
        )
        status = db_backup.get_status()
        assert status["total_backups"] == 0
        assert status["last_backup"] is None
        assert status["max_retention"] == 7

    def test_get_status_after_backup(self, db_backup):
        db_backup.create_backup()
        status = db_backup.get_status()
        assert status["total_backups"] == 1
        assert status["last_backup"] is not None
        assert status["last_backup"]["size_bytes"] > 0

    def test_rotation_removes_oldest(self, db_backup):
        for _ in range(4):
            db_backup.create_backup()
        status = db_backup.get_status()
        assert status["total_backups"] <= 3
