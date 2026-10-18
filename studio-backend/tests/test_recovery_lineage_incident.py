"""Regression tests for the 2026-09-27 hard-reset / project-context-confusion incident.

Incident shape (see docs/forensics/FULL_PROJECT_CONTEXT_RECOVERY_20260927.md):
the modern working database was replaced on the live path overnight Sept 26→27.
Authentication failed; a prior session "restored" projects from the JSON state
store — which structurally carries NO storyboard artifacts — so every real film
came back as an empty shell and the entire creative estate (approved storyboard,
shots, previs, references, knowledge, characters) vanished from the live view.
SQLite ``integrity_check`` said "ok" the whole way through.

These tests pin the safeguards that must prevent a repeat:

1. snapshot  — a destructive operation captures an immutable hash-pinned snapshot
2. restore   — a restore that empties previously-populated creative tables FAILS
               application-level invariants even though integrity_check is ok
3. restore-ok — a faithful restore passes the same invariants
4. lineage   — replacing the database file on the live path is DETECTED
5. render    — render submission refuses (fail closed, permanent) against a
               replaced database; no provider call is attempted
6. invariant floor — knowledge-atom floors catch "rich shell, empty brain" restorations
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.services.recovery_lineage_guard import (
    build_expected_counts,
    capture_recovery_snapshot,
    verify_render_lineage,
    verify_restore_invariants,
    write_lineage_registration,
)

# ── fixture: a tiny "modern working database" with a creative estate ─────────


def _make_rich_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (project_id TEXT PRIMARY KEY, data TEXT);
        CREATE TABLE storyboard_blueprints (
            blueprint_id TEXT PRIMARY KEY, project_id TEXT, scene_id TEXT
        );
        CREATE TABLE storyboard_blueprint_versions (
            version_id TEXT PRIMARY KEY, project_id TEXT, scene_id TEXT, status TEXT
        );
        CREATE TABLE storyboard_shots (
            storyboard_shot_id TEXT PRIMARY KEY, project_id TEXT, version_id TEXT, status TEXT
        );
        CREATE TABLE previs_images (id TEXT PRIMARY KEY, project_id TEXT, scene_id TEXT);
        CREATE TABLE characters (id TEXT PRIMARY KEY, project_id TEXT, name TEXT);
        CREATE TABLE knowledge_atoms (atom_id TEXT PRIMARY KEY, project_id TEXT, content TEXT);
        """
    )
    pid = "project_rich"
    conn.execute("INSERT INTO projects VALUES (?, '{}')", (pid,))
    conn.execute(
        "INSERT INTO storyboard_blueprints VALUES ('bp1', ?, 'scene_001')", (pid,)
    )
    conn.execute(
        "INSERT INTO storyboard_blueprint_versions VALUES ('v1', ?, 'scene_001', 'approved')",
        (pid,),
    )
    for i in range(5):
        conn.execute(
            "INSERT INTO storyboard_shots VALUES (?, ?, 'v1', 'approved')",
            (f"shot{i}", pid),
        )
    conn.execute("INSERT INTO previs_images VALUES ('pv1', ?, 'scene_001')", (pid,))
    conn.execute("INSERT INTO characters VALUES ('c1', ?, 'MAYA')", (pid,))
    for i in range(20):
        conn.execute(
            "INSERT INTO knowledge_atoms VALUES (?, ?, ?)", (f"atom{i}", pid, "x")
        )
    conn.commit()
    conn.close()


def _make_shell_db(db_path: Path) -> None:
    """Same schema, project row only — the empty-shell restoration from the incident."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (project_id TEXT PRIMARY KEY, data TEXT);
        CREATE TABLE storyboard_blueprints (
            blueprint_id TEXT PRIMARY KEY, project_id TEXT, scene_id TEXT
        );
        CREATE TABLE storyboard_blueprint_versions (
            version_id TEXT PRIMARY KEY, project_id TEXT, scene_id TEXT, status TEXT
        );
        CREATE TABLE storyboard_shots (
            storyboard_shot_id TEXT PRIMARY KEY, project_id TEXT, version_id TEXT, status TEXT
        );
        CREATE TABLE previs_images (id TEXT PRIMARY KEY, project_id TEXT, scene_id TEXT);
        CREATE TABLE characters (id TEXT PRIMARY KEY, project_id TEXT, name TEXT);
        CREATE TABLE knowledge_atoms (atom_id TEXT PRIMARY KEY, project_id TEXT, content TEXT);
        """
    )
    conn.execute("INSERT INTO projects VALUES ('project_rich', '{}')")
    conn.commit()
    conn.close()


# ── 1. snapshot ──────────────────────────────────────────────────────────────


def test_snapshot_captures_hash_pinned_copy(tmp_path):
    db = tmp_path / "studio.db"
    _make_rich_db(db)
    manifest = capture_recovery_snapshot(db, reason="unit-test", repo_root=tmp_path)
    snap_dir = next((tmp_path / "recovery-snapshots").iterdir())
    assert (snap_dir / "studio.db").exists()
    assert (snap_dir / "snapshot_manifest.json").exists()
    assert manifest["files"]["studio.db"]["bytes"] > 0
    assert manifest["files"]["studio.db"]["sha256"]


def test_snapshot_refuses_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        capture_recovery_snapshot(tmp_path / "nope.db", reason="unit-test")


# ── 2/3. restore invariants ──────────────────────────────────────────────────


def test_restore_that_empties_creative_tables_fails_closed(tmp_path):
    rich = tmp_path / "rich.db"
    shell = tmp_path / "shell.db"
    _make_rich_db(rich)
    _make_shell_db(shell)

    baseline = build_expected_counts(rich, ["project_rich"])
    assert baseline["project_rich"]["storyboard_shots"] == 5

    report = verify_restore_invariants(shell, baseline)
    assert not report["ok"]
    assert any("storyboard_shots" in f and "0 after" in f for f in report["failures"])
    assert any("storyboard_blueprints" in f for f in report["failures"])
    assert any("knowledge_atoms" in f for f in report["failures"])


def test_faithful_restore_passes_invariants(tmp_path):
    rich = tmp_path / "rich.db"
    copy = tmp_path / "restored.db"
    _make_rich_db(rich)
    shutil.copy2(rich, copy)

    baseline = build_expected_counts(rich, ["project_rich"])
    report = verify_restore_invariants(copy, baseline)
    assert report["ok"], report["failures"]


def test_partial_regression_is_also_a_failure(tmp_path):
    rich = tmp_path / "rich.db"
    partial = tmp_path / "partial.db"
    _make_rich_db(rich)
    _make_rich_db(partial)
    conn = sqlite3.connect(partial)
    conn.execute("DELETE FROM storyboard_shots")  # shots lost, everything else kept
    conn.commit()
    conn.close()

    baseline = build_expected_counts(rich, ["project_rich"])
    report = verify_restore_invariants(partial, baseline)
    assert not report["ok"]
    # 5 -> 0 is caught by the hard zero-row branch (strongest possible message)
    assert any("storyboard_shots" in f for f in report["failures"])


def test_atom_floor_blocks_rich_shell_empty_brain(tmp_path):
    rich = tmp_path / "rich.db"
    thin = tmp_path / "thin.db"
    _make_rich_db(rich)
    _make_rich_db(thin)
    conn = sqlite3.connect(thin)
    conn.execute("DELETE FROM knowledge_atoms")
    conn.commit()
    conn.close()

    baseline = build_expected_counts(rich, ["project_rich"])
    report = verify_restore_invariants(thin, baseline, minimum_total_atoms=10)
    assert not report["ok"]
    assert any("knowledge_atoms" in f for f in report["failures"])


# ── 4. lineage replacement detection ─────────────────────────────────────────


def test_database_replacement_is_detected(tmp_path):
    db = tmp_path / "studio.db"
    _make_rich_db(db)
    write_lineage_registration(db, repo_root=tmp_path)

    # Normal case: same file, still ok
    report = verify_render_lineage(db)
    assert report["ok"], report.get("reason")

    # Incident case: a different file is swapped onto the live path
    replacement = tmp_path / "replacement.db"
    _make_shell_db(replacement)
    db.unlink()
    shutil.copy2(replacement, db)

    report = verify_render_lineage(db)
    assert not report["ok"]
    assert "replaced" in report["reason"]


def test_unregistered_database_is_allowed_with_warning_but_strict_mode_refuses(tmp_path):
    db = tmp_path / "studio.db"
    _make_rich_db(db)
    # Default (non-strict): ephemeral/test databases may render, with a warning.
    report = verify_render_lineage(db)
    assert report["ok"]
    assert "unregistered" in report.get("warning", "")
    # Strict mode (STUDIO_LINEAGE_STRICT=1) refuses to render unregistered.
    report = verify_render_lineage(db, strict=True)
    assert not report["ok"]
    assert "no lineage registration" in report["reason"]


def test_schema_change_midruntime_is_detected(tmp_path):
    db = tmp_path / "studio.db"
    _make_rich_db(db)
    write_lineage_registration(db, repo_root=tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE characters ADD COLUMN new_col TEXT")
    conn.commit()
    conn.close()
    report = verify_render_lineage(db)
    assert not report["ok"]
    assert "schema_version" in report["reason"]


# ── 5. render submission refuses against a replaced database ─────────────────


@pytest.mark.asyncio
async def test_render_submit_refuses_replaced_database(monkeypatch, tmp_path):
    """End of the chain: submit_job must fail closed, permanently, before any
    provider boundary, when the live database file was swapped after the app
    registered its identity."""
    from app.data.storage import DatabaseStorage
    from app.services.render import render_service

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    storage = DatabaseStorage(str(data_dir))
    try:
        # register the identity of the freshly-created (pytest) database
        write_lineage_registration(storage.db_path, repo_root=tmp_path)

        # minimal job in the in-memory registry
        from app.models import RenderJobModel

        job = RenderJobModel(
            id="job-lineage-test-1",
            project_id="project_lineage_test",
            shot_id="scene_001_shot_001",
            provider="simulated",
            prompt="x",
        )
        render_service._jobs[job.id] = job
        monkeypatch.setattr("app.services.render._storage", storage)

        # swap the database file (incident simulation) and re-register nothing
        shell = data_dir / "shell.db"
        _make_shell_db(shell)
        st_ino_before = storage.db_path.stat().st_ino
        storage.db_path.unlink()
        shutil.copy2(shell, storage.db_path)
        assert storage.db_path.stat().st_ino != st_ino_before

        # Pre-condition: the lineage guard itself detects the swap
        report = verify_render_lineage(storage.db_path)
        assert not report["ok"]

        result = await render_service.submit_job(job.id)
        assert result.status == "failed"
        assert "lineage" in (result.error_message or "").lower()
        metadata = result.metadata or {}
        assert metadata.get("render_lineage_failure", {}).get("category") == "permanent"
        # the job must never have been submitted to a provider adapter
        assert result.status != "rendering"
    finally:
        render_service._jobs.pop("job-lineage-test-1", None)
        storage.close()


# ── 6. project-context discovery sanity (the account-confusion surface) ──────


def test_project_without_owner_rows_is_reported_by_invariants(tmp_path):
    """After the incident, projects existed without ownership rows. The
    invariant baseline is keyed on creative tables; a project with a shell but
    zero creative rows anywhere produces no baseline entry — meaning a restore
    of the *shell alone* cannot pass silently against a baseline that knew the
    project was rich. This test pins that semantics."""
    rich = tmp_path / "rich.db"
    shell = tmp_path / "shell.db"
    _make_rich_db(rich)
    _make_shell_db(shell)
    baseline = build_expected_counts(rich)
    assert "project_rich" in baseline  # baseline knows the estate existed
    report = verify_restore_invariants(shell, baseline)
    assert not report["ok"]  # shell cannot impersonate the rich lineage
