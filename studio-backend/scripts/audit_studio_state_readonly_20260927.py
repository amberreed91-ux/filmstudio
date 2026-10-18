#!/usr/bin/env python3
"""READ-ONLY Studio state audit — 2026-09-27 recovery session.

Inventories auth rows, project ownership, and canonical storyboard evidence
across every surviving store. Opens every database COPY in a temp dir so the
originals (including their WAL files) are never touched. Makes no writes to
any project artifact, makes no network/provider calls, prints sentinels so
output can be checked for truncation.

Run from repo root:  python3 studio-backend/scripts/audit_studio_state_readonly_20260927.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "studio-backend"

EVIDENCE_IDS = [
    "project_5907c60cddbc",
    "sbv_dbafa23cf4a1",
    "sbs_77d3ae4fe1e9",
]
EVIDENCE_NUMBERS = ["916483", "259c21e05769bf63", "c66c7e8e573b00ec"]

STORES = [
    ("LIVE-DB", BACKEND / "data/studio.db"),
    ("PREAPPROVAL-20260926-1616", BACKEND / ".validation/scene002_approval_20260926/studio.db.pre-approval-backup"),
    ("PREAPPROVAL-WAL-20260926-1616", BACKEND / ".validation/scene002_approval_20260926/studio.db-wal.pre-approval-backup"),
    ("NIGHTLY-20260926", BACKEND / "backups/studio_20260926_160722.db"),
    ("NIGHTLY-20260925", BACKEND / "backups/studio_20260925_160721.db"),
    ("PREREPAIR-20260927", BACKEND / "data/recovery_artifacts_20260927/studio.db.pre-repair-20260927"),
    ("QUARANTINED-WAL-20260926", BACKEND / "data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728"),
]


def open_copy(db_path: Path, wal_path: Path | None, workdir: Path) -> sqlite3.Connection | None:
    """Copy db (+wal) to workdir and open the copy. Never opens the original."""
    if not db_path.exists():
        return None
    tmp_db = workdir / "audit_copy.db"
    shutil.copy2(db_path, tmp_db)
    if wal_path and wal_path.exists():
        shutil.copy2(wal_path, workdir / "audit_copy.db-wal")
    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        return [{"__error__": str(exc)}]


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def main() -> int:
    print("AUDIT-START", datetime.now().isoformat(timespec="seconds"))
    findings: dict[str, dict] = {}

    with tempfile.TemporaryDirectory(prefix="studio-audit-") as td:
        workdir = Path(td)

        for label, db_path in STORES:
            wal = None
            if "WAL" in label:
                wal = db_path  # the artifact IS a wal; pair it with its base db
                base = db_path.with_name(db_path.name.replace("-wal", "").replace(".wal", ""))
                # pre-approval wal pairs with the pre-approval backup db
                if not base.exists():
                    base = BACKEND / ".validation/scene002_approval_20260926/studio.db.pre-approval-backup"
                db_path = base
            conn = open_copy(db_path, wal, workdir)
            if conn is None:
                findings[label] = {"status": "ARTIFACT NOT FOUND", "path": str(db_path)}
                continue

            info: dict = {"path": str(db_path)}
            info["integrity"] = q(conn, "PRAGMA integrity_check;")[0][0] if table_exists(conn, "sqlite_master") else "?"
            for table in ("access_users", "project_owners", "projects", "storyboard_blueprint_versions", "storyboard_shots"):
                info[table] = q(conn, f"SELECT count(*) AS n FROM {table};")[0]["n"] if table_exists(conn, table) else "NO TABLE"
            users = q(conn, "SELECT username FROM access_users;") if table_exists(conn, "access_users") else []
            info["usernames"] = sorted(str(r["username"]) for r in users if "username" in r.keys()) if users and "__error__" not in users[0] else users
            owners = q(conn, "SELECT project_id FROM project_owners;") if table_exists(conn, "project_owners") else []
            info["owned_project_ids"] = sorted(str(r["project_id"]) for r in owners if "project_id" in r.keys()) if owners and "__error__" not in owners[0] else owners

            # evidence search inside this db
            hits: dict[str, list[str]] = {}
            for eid in EVIDENCE_IDS:
                found_in = []
                for table in ("projects", "storyboard_blueprint_versions", "storyboard_shots"):
                    if not table_exists(conn, table):
                        continue
                    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table});")]
                    for col in cols:
                        try:
                            n = q(conn, f"SELECT count(*) AS n FROM {table} WHERE {col} LIKE ?;", (f"%{eid}%",))[0]["n"]
                            if n:
                                found_in.append(f"{table}.{col}({n})")
                        except sqlite3.Error:
                            continue
                hits[eid] = found_in
            for num in EVIDENCE_NUMBERS:
                found_in = []
                for table in ("storyboard_shots", "storyboard_blueprint_versions"):
                    if not table_exists(conn, table):
                        continue
                    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table});")]
                    for col in cols:
                        try:
                            n = q(conn, f"SELECT count(*) AS n FROM {table} WHERE {col} LIKE ?;", (f"%{num}%",))[0]["n"]
                            if n:
                                found_in.append(f"{table}.{col}({n})")
                        except sqlite3.Error:
                            continue
                hits[num] = found_in
            info["evidence_hits"] = hits
            findings[label] = info
            conn.close()

        # project_state_store.json (live) — plain JSON, no sqlite
        section("PROJECT STATE STORE (live)")
        store_path = BACKEND / "data/project_state_store.json"
        if store_path.exists():
            payload = json.loads(store_path.read_text(encoding="utf-8"))
            projects = payload.get("projects", {})
            print("path:", store_path)
            print("total projects:", len(projects))
            target = projects.get("project_5907c60cddbc")
            print("project_5907c60cddbc present:", bool(target))
            if target:
                print("  title:", target.get("title"))
                print("  updated_at:", target.get("updated_at"))
                print("  approved_scenes:", len(target.get("approved_scenes") or []))
            raw = json.dumps(payload)
            for eid in EVIDENCE_IDS + EVIDENCE_NUMBERS:
                print(f"contains {eid}:", eid in raw)
        else:
            print("STORE NOT FOUND:", store_path)

    section("DATABASE LINEAGE SUMMARY")
    for label, info in findings.items():
        print(f"\n--- {label}")
        if info.get("status"):
            print(" ", info["status"], info.get("path", ""))
            continue
        print("  path:", info["path"])
        print("  integrity:", info["integrity"])
        print("  access_users:", info["access_users"], "| project_owners:", info["project_owners"],
              "| projects:", info["projects"])
        print("  usernames:", info["usernames"])
        print("  owned_project_ids:", info["owned_project_ids"])
        for eid, where in info["evidence_hits"].items():
            print(f"  evidence {eid}: {where if where else 'not present'}")

    print("\nAUDIT-END (complete — if you can read this line, output was not truncated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
