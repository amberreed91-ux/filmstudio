#!/usr/bin/env python3
"""List projects that can meaningfully exercise the paid render phase.

Read-only inspection only: this script opens the studio SQLite database and
reports whether each real project has shots, locked character references, and a
prior completed render for before/after comparison.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_ROOT / "data" / "studio.db"


def _loads_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _project_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT project_id, data FROM projects ORDER BY project_id"))


def _shot_ids(conn: sqlite3.Connection, project_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT shot_id
        FROM shots
        WHERE project_id = ?
        ORDER BY shot_id
        """,
        (project_id,),
    )
    return [str(row["shot_id"]) for row in rows]


def _locked_reference_count(conn: sqlite3.Connection, project_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM character_reference_locks
        WHERE project_id = ? AND lock_status = 'locked'
        """,
        (project_id,),
    ).fetchone()
    return int(row["count"] or 0)


def _completed_render_shot_ids(conn: sqlite3.Connection, project_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT shot_id
        FROM render_jobs
        WHERE project_id = ? AND status = 'complete'
        ORDER BY shot_id
        """,
        (project_id,),
    )
    return [str(row["shot_id"]) for row in rows]


def build_report() -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        projects: list[dict[str, Any]] = []
        viable: list[dict[str, Any]] = []
        for project_row in _project_rows(conn):
            project_id = str(project_row["project_id"])
            project_data = _loads_json(project_row["data"])
            shot_ids = _shot_ids(conn, project_id)
            locked_references = _locked_reference_count(conn, project_id)
            completed_shot_ids = _completed_render_shot_ids(conn, project_id)
            comparable_completed_shot_ids = sorted(set(shot_ids) & set(completed_shot_ids))
            is_viable = bool(shot_ids) and locked_references > 0 and bool(comparable_completed_shot_ids)
            project = {
                "project_id": project_id,
                "title": str(project_data.get("title") or ""),
                "shots": {
                    "count": len(shot_ids),
                    "shot_ids": shot_ids,
                },
                "locked_character_references": locked_references,
                "prior_completed_render": {
                    "present": bool(completed_shot_ids),
                    "shot_ids": completed_shot_ids,
                    "comparable_shot_ids": comparable_completed_shot_ids,
                },
                "viable_render_target": is_viable,
            }
            projects.append(project)
            if is_viable:
                viable.append(
                    {
                        "project_id": project_id,
                        "title": project["title"],
                        "completed_render_shot_ids": completed_shot_ids,
                        "comparable_completed_shot_ids": comparable_completed_shot_ids,
                    }
                )

        conclusion = "VIABLE RENDER TARGETS" if viable else "NO VIABLE RENDER TARGET"
        return {
            "database": str(DB_PATH),
            "projects": projects,
            "viable_render_targets": viable,
            "conclusion": conclusion,
        }
    finally:
        conn.close()


def main() -> int:
    report = build_report()
    print(json.dumps(report, indent=2))
    print(f"\n{report['conclusion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
