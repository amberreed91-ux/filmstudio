#!/usr/bin/env python3
"""Read-only diagnostic for the studio SQLite storage target.

The render adherence script must use the same database as the running app. This
tool reports where get_storage("sqlite") would point, scans every studio.db under
the repo in read-only mode, and states whether the target project is present.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_PROJECT_ID = "project_3dba9330f43a"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _resolved_get_storage_db() -> Path:
    storage_path = os.getenv("STUDIO_STORAGE_PATH")
    if storage_path:
        return Path(storage_path).expanduser() / "studio.db"
    return BACKEND_ROOT / "data" / "studio.db"


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(db_path.resolve()))}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _project_ids(db_path: Path) -> tuple[list[str], str | None]:
    if not db_path.exists():
        return [], "missing"
    try:
        with _connect_readonly(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
            ).fetchall()
            if not rows:
                return [], "no projects table"
            project_rows = conn.execute(
                "SELECT project_id FROM projects ORDER BY project_id"
            ).fetchall()
    except Exception as exc:
        return [], repr(exc)
    return [str(row[0]) for row in project_rows], None


def _format_ids(project_ids: list[str]) -> str:
    if not project_ids:
        return "[]"
    return "[" + ", ".join(project_ids) + "]"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose which SQLite studio.db contains the target project."
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    args = parser.parse_args()

    _load_env_file(BACKEND_ROOT / ".env")

    target_project_id = args.project_id
    resolved_db = _resolved_get_storage_db().resolve()
    studio_dbs = sorted({path.resolve() for path in REPO_ROOT.rglob("studio.db")})
    if resolved_db not in studio_dbs:
        studio_dbs.insert(0, resolved_db)

    print(f"TARGET_PROJECT_ID={target_project_id}")
    print(f"BACKEND_ROOT={BACKEND_ROOT}")
    print(f"REPO_ROOT={REPO_ROOT}")
    print(f"ENV_STUDIO_STORAGE_PATH={os.getenv('STUDIO_STORAGE_PATH') or '<unset>'}")
    print(f"GET_STORAGE_SQLITE_DB={resolved_db}")
    print(f"GET_STORAGE_SQLITE_DB_EXISTS={resolved_db.exists()}")
    print()

    resolved_has_target = False
    other_hits: list[Path] = []

    for db_path in studio_dbs:
        project_ids, error = _project_ids(db_path)
        target_present = target_project_id in project_ids
        if db_path == resolved_db:
            resolved_has_target = target_present
            label = "get_storage sqlite target"
        else:
            label = "other repo studio.db"
            if target_present:
                other_hits.append(db_path)
        print(f"DATABASE={db_path}")
        print(f"  role={label}")
        print(f"  exists={db_path.exists()}")
        print(f"  project_ids={_format_ids(project_ids)}")
        print(f"  target_present={target_present}")
        if error:
            print(f"  error={error}")
        print()

    if resolved_has_target:
        conclusion = "target_project_found_in_get_storage_database"
    elif other_hits:
        conclusion = "target_project_found_in_different_database"
    else:
        conclusion = "target_project_not_found_in_any_repo_database"
    print(f"CONCLUSION={conclusion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
