"""Recovery lineage safeguards — added after the 2026-09-27 hard-reset incident.

The incident: the modern working database was replaced on the live path overnight
Sept 26→27 while the JSON project state store (which never carries storyboard
artifacts) was treated as the recovery source. Projects came back as empty shells
and the creative estate vanished from the live view. Three gaps made that possible:

1. No immutable snapshot is taken automatically before destructive operations
   (restore, repair, replace, reconcile).
2. A restore is accepted after ``integrity_check`` alone — no application-level
   invariant check (a project that previously had storyboard artifacts can come
   back with zero, and SQLite will still say "ok").
3. Render preparation never verifies the resolved database lineage, so a
   recovered-from-the-wrong-lineage shell can reach the provider seam.

This module closes those gaps with three fail-closed primitives:

- :func:`capture_recovery_snapshot` — immutable, hash-pinned snapshot of the
  live database trio + state store + git identity before anything destructive.
- :func:`verify_restore_invariants` — application-level post-restore check that
  compares per-project creative-artifact counts against a manifest; a project
  that had artifacts before and has none after is a HARD failure.
- :func:`verify_render_lineage` — pre-render lineage check: the resolved
  database must be the same file identity recorded in the project state store's
  lineage registration (and must not be an unregistered/replaced file).

Design rules honored here: fail closed (unknown → refuse), no silent
substitutions, WAL files are never opened/renamed/checkpointed by this module
(they are only ever *copied byte-for-byte* beside their own database file),
and no credentials are read or logged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from app.data.db_guard import open_db_readonly
from typing import Any

logger = logging.getLogger("studio-recovery-guard")

# Tables whose per-project row counts define "the creative estate survived".
# Derived/advisory tables are deliberately excluded: they are rebuildable and
# their absence must not block recovery, per the canonical-vs-derived rule.
CREATIVE_INVARIANT_TABLES: tuple[str, ...] = (
    "storyboard_blueprints",
    "storyboard_blueprint_versions",
    "storyboard_shots",
    "previs_images",
    "scene_memories",
    "characters",
    "reference_assets",
    "universe_nodes",
    "render_jobs",
    "video_assets",
    "knowledge_atoms",
    "knowledge_bibles",
    "knowledge_bible_sections",
)

LINEAGE_FILENAME = "database_lineage.json"
SNAPSHOT_DIRNAME = "recovery-snapshots"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_identity(repo_root: Path) -> dict[str, str]:
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
        return {"branch": branch, "commit": commit[:12]}
    except Exception:  # noqa: BLE001 — git absence must never block a snapshot
        return {"branch": "unknown", "commit": "unknown"}


def capture_recovery_snapshot(
    db_path: Path | str,
    reason: str,
    repo_root: Path | str | None = None,
    extra_files: list[Path | str] | None = None,
) -> dict[str, Any]:
    """Capture an immutable, hash-pinned snapshot before a destructive operation.

    Copies (never moves) the database file plus any ``-wal``/``-shm`` companions
    into ``<db parent>/recovery-snapshots/<timestamp>-<reason>/`` and writes a
    ``snapshot_manifest.json`` with SHA-256 hashes, git identity, and the reason.
    The snapshot directory is best-effort made read-only (0o555).

    Returns the manifest dict. Raises on failure — a snapshot that cannot be
    taken must stop the destructive operation (fail closed).
    """
    db_path = Path(db_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"cannot snapshot missing database: {db_path}")
    repo_root = Path(repo_root) if repo_root else db_path.parents[2]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "-" for c in reason)[:60]
    snap_dir = db_path.parent / SNAPSHOT_DIRNAME / f"{stamp}-{safe_reason}"
    snap_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
        "captured_at": _utcnow(),
        "reason": reason,
        "database": db_path.name,
        "files": {},
        "git": _git_identity(repo_root),
    }
    for candidate in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        if candidate.exists():
            target = snap_dir / candidate.name
            shutil.copy2(candidate, target)  # byte-for-byte copy; never opens or renames
            manifest["files"][candidate.name] = {
                "bytes": target.stat().st_size,
                "sha256": _sha256_file(target),
            }
    for extra in extra_files or []:
        extra_path = Path(extra)
        if extra_path.exists():
            target = snap_dir / extra_path.name
            shutil.copy2(extra_path, target)
            manifest["files"][extra_path.name] = {
                "bytes": target.stat().st_size,
                "sha256": _sha256_file(target),
            }
    (snap_dir / "snapshot_manifest.json").write_text(json.dumps(manifest, indent=2))
    try:
        os.chmod(snap_dir, 0o555)
    except OSError:
        pass
    logger.warning("RECOVERY SNAPSHOT captured: %s (reason=%s)", snap_dir, reason)
    return manifest


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _project_creative_counts(db_path: Path) -> dict[str, dict[str, int]]:
    """Per-project row counts for the creative invariant tables. Opens the DB
    with ``mode=ro`` on the resolved path WITHOUT touching any WAL sidecar —
    suitable for closed/restored snapshots. Live-lineage reads should be done
    on a copy (see forensic tooling) or with the backend stopped."""
    conn = open_db_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        counts: dict[str, dict[str, int]] = {}
        for table in CREATIVE_INVARIANT_TABLES:
            if not _table_exists(conn, table):
                continue
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "project_id" not in cols:
                continue
            for row in conn.execute(
                f"SELECT project_id, count(*) AS n FROM {table} GROUP BY project_id"
            ):
                counts.setdefault(row["project_id"], {})[table] = row["n"]
        return counts
    finally:
        conn.close()


def verify_restore_invariants(
    restored_db_path: Path | str,
    expected_counts: dict[str, dict[str, int]],
    *,
    minimum_total_atoms: int = 0,
) -> dict[str, Any]:
    """Application-level post-restore verification. ``integrity_check`` is NOT
    enough (see module docstring). A project present in ``expected_counts`` with
    creative rows that comes back with zero (or far fewer) is a hard failure.

    Parameters
    ----------
    restored_db_path: the database that would become live after the restore.
    expected_counts: per-project per-table counts captured BEFORE the operation,
        e.g. from the manifest written by :func:`capture_recovery_snapshot` or
        any pre-operation baseline (see ``build_expected_counts``).
    minimum_total_atoms: optional floor for knowledge_atoms across projects;
        0 disables the floor.
    """
    restored_db_path = Path(restored_db_path)
    report: dict[str, Any] = {
        "checked_at": _utcnow(),
        "database": str(restored_db_path),
        "ok": True,
        "failures": [],
        "projects_checked": sorted(expected_counts.keys()),
    }
    try:
        actual = _project_creative_counts(restored_db_path)
    except sqlite3.Error as exc:
        return {
            **report,
            "ok": False,
            "failures": [f"cannot read restored database: {exc}"],
        }

    for project_id, expected_tables in sorted(expected_counts.items()):
        actual_tables = actual.get(project_id, {})
        for table, expected_n in sorted(expected_tables.items()):
            actual_n = actual_tables.get(table, 0)
            if expected_n > 0 and actual_n == 0:
                report["failures"].append(
                    f"{project_id}: {table} had {expected_n} rows before, 0 after "
                    "(creative estate lost — restore must fail)"
                )
            elif actual_n < expected_n:
                report["failures"].append(
                    f"{project_id}: {table} row count regressed "
                    f"({expected_n} -> {actual_n})"
                )
    if minimum_total_atoms:
        total_atoms = sum(
            counts.get("knowledge_atoms", 0) for counts in actual.values()
        )
        if total_atoms < minimum_total_atoms:
            report["failures"].append(
                f"knowledge_atoms total {total_atoms} < required floor {minimum_total_atoms}"
            )
    report["ok"] = not report["failures"]
    return report


def build_expected_counts(db_path: Path | str, project_ids: list[str] | None = None) -> dict[str, dict[str, int]]:
    """Build the pre-operation baseline consumed by :func:`verify_restore_invariants`."""
    counts = _project_creative_counts(Path(db_path))
    if project_ids is None:
        return counts
    return {pid: counts[pid] for pid in project_ids if pid in counts}


def _database_fingerprint(db_path: Path) -> dict[str, Any]:
    """Identity of a database FILE (not its content): inode/device identity plus
    schema version. Content hashes and sizes change on every legitimate write,
    so they are recorded as informational only — enforcement below keys on the
    file identity (which changes when a different file is swapped onto the
    path, exactly what happened in the 2026-09-27 incident) and on mid-runtime
    schema changes (which should only ever happen at startup, before
    registration)."""
    st = db_path.stat()
    fingerprint: dict[str, Any] = {
        "st_dev": st.st_dev,
        "st_ino": st.st_ino,
        "bytes": st.st_size,
        "sha256_first1m": "",
        "schema_version": None,
    }
    try:
        conn = open_db_readonly(db_path)
        try:
            fingerprint["schema_version"] = conn.execute("PRAGMA schema_version").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return fingerprint


def write_lineage_registration(
    db_path: Path | str,
    repo_root: Path | str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Record the database identity the app is currently running against.

    Writes ``<data dir>/database_lineage.json`` with the file (inode) identity,
    schema version, and git identity. :func:`verify_render_lineage` compares
    the live file against this registration and fails closed on mismatch.
    """
    db_path = Path(db_path).resolve()
    fingerprint = _database_fingerprint(db_path)
    registration = {
        "registered_at": _utcnow(),
        "db_path": str(db_path),
        **fingerprint,
        "git": _git_identity(Path(repo_root) if repo_root else db_path.parents[2]),
    }
    if project_id:
        registration["project_id"] = project_id
    out = db_path.parent / LINEAGE_FILENAME
    out.write_text(json.dumps(registration, indent=2))
    logger.info("Database lineage registered: %s", out)
    return registration


def verify_render_lineage(
    db_path: Path | str,
    repo_root: Path | str | None = None,
    strict: bool | None = None,
) -> dict[str, Any]:
    """Fail-closed pre-render lineage check.

    Compares the currently-resolved database file against the registration
    written by :func:`write_lineage_registration`.

    - Registration exists and file identity/schema changed → HARD FAIL
      (this is exactly the 2026-09-27 replace-the-live-db incident).
    - Registration missing → allowed with a warning by default (ephemeral
      test databases, first run before registration). Set ``strict=True`` or
      env ``STUDIO_LINEAGE_STRICT=1`` to make even a missing registration a
      refusal. The backend registers automatically at startup, so production
      runs with full protection either way.
    """
    db_path = Path(db_path).resolve()
    reg_path = db_path.parent / LINEAGE_FILENAME
    if strict is None:
        strict = os.getenv("STUDIO_LINEAGE_STRICT", "").strip().lower() in ("1", "true", "yes")
    report: dict[str, Any] = {"checked_at": _utcnow(), "db_path": str(db_path), "ok": False}
    if not db_path.exists():
        report["reason"] = "database file missing"
        return report
    if not reg_path.exists():
        if strict:
            report["reason"] = (
                f"no lineage registration at {reg_path}; run write_lineage_registration "
                "once after a trusted startup, before any render"
            )
            return report
        report["ok"] = True
        report["warning"] = "lineage unregistered — replacement detection inactive for this database"
        return report
    try:
        registration = json.loads(reg_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        report["reason"] = f"lineage registration unreadable: {exc}"
        return report
    current = _database_fingerprint(db_path)

    mismatches = []
    reg_ino = registration.get("st_ino")
    cur_ino = current.get("st_ino")
    if reg_ino is not None and cur_ino is not None and reg_ino != cur_ino:
        mismatches.append(
            f"database file replaced (inode {reg_ino} -> {cur_ino}) — a different "
            "file is on the live path since registration"
        )
    if registration.get("schema_version") != current.get("schema_version"):
        mismatches.append(
            f"schema_version changed {registration.get('schema_version')} -> "
            f"{current.get('schema_version')} mid-runtime"
        )
    if mismatches:
        report["reason"] = "database lineage changed since registration: " + "; ".join(mismatches)
        return report
    report["ok"] = True
    report["registration"] = registration
    return report
