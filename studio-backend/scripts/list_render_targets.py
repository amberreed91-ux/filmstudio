#!/usr/bin/env python3
"""List projects that can meaningfully exercise the paid render phase.

Read-only inspection only: this script opens the studio SQLite database and
reports whether each project has shots, locked character references, and a
prior completed render for before/after comparison.

Projects are enumerated from the union of every table that carries a
project_id, not from the `projects` table alone. A project whose child rows
survived but whose parent row did not would otherwise be invisible here, and
such a project can still hold the only locked character references in the
database. Those ids are reported with `orphaned: true` and are never treated as
viable render targets until the parent row is restored.
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


# Every table consulted when enumerating project ids. `projects` is the parent;
# the rest are children that can outlive it.
PROJECT_ID_SOURCES = (
    "projects",
    "shots",
    "character_reference_locks",
    "render_jobs",
)


def _project_data_map(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Return the parsed `data` blob for each project that still has a parent row."""
    rows = conn.execute("SELECT project_id, data FROM projects")
    return {str(row["project_id"]): _loads_json(row["data"]) for row in rows}


def _all_project_ids(conn: sqlite3.Connection) -> list[str]:
    """Collect project ids from the parent table and from every child table."""
    project_ids: set[str] = set()
    for table in PROJECT_ID_SOURCES:
        rows = conn.execute(f'SELECT DISTINCT project_id FROM "{table}"')  # noqa: S608 - fixed table names
        project_ids.update(str(row["project_id"]) for row in rows if row["project_id"])
    return sorted(project_ids)


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
        orphaned_ids: list[str] = []
        data_map = _project_data_map(conn)
        for project_id in _all_project_ids(conn):
            project_data = data_map.get(project_id, {})
            is_orphaned = project_id not in data_map
            shot_ids = _shot_ids(conn, project_id)
            locked_references = _locked_reference_count(conn, project_id)
            completed_shot_ids = _completed_render_shot_ids(conn, project_id)
            comparable_completed_shot_ids = sorted(set(shot_ids) & set(completed_shot_ids))
            is_viable = (
                not is_orphaned
                and bool(shot_ids)
                and locked_references > 0
                and bool(comparable_completed_shot_ids)
            )
            project = {
                "project_id": project_id,
                "title": str(project_data.get("title") or ""),
                "orphaned": is_orphaned,
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
            if is_orphaned:
                orphaned_ids.append(project_id)
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
            "orphaned_project_ids": orphaned_ids,
            "conclusion": conclusion,
        }
    finally:
        conn.close()


def main() -> int:
    report = build_report()
    print(json.dumps(report, indent=2))
    if report["orphaned_project_ids"]:
        print(
            "\nORPHANED (child rows present, no `projects` row): "
            + ", ".join(report["orphaned_project_ids"])
        )
    print(f"\n{report['conclusion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
