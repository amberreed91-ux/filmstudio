"""Central DB-path resolver + fail-closed live-DB guard.

Every entry point (server, script, test) that opens a SQLite database must
resolve its path through :func:`resolve_db_dir` / :func:`resolve_db_file`
and open it through :func:`open_db_readwrite` / :func:`open_db_readonly`.

Rules (see mission Part 2):
- The default database directory is a dev-copy location OUTSIDE the live
  path (``studio-backend/data-dev``), never ``studio-backend/data``.
- Opening the live path requires BOTH ``STUDIO_ALLOW_LIVE_DB=1`` AND
  ``STUDIO_PRIMARY_WRITER=1``. Otherwise startup fails closed with
  :class:`LiveDatabaseRefused` naming both flags.
- Tests can NEVER resolve the live path: under pytest the guard refuses
  unconditionally, with no flag override.
- Read-only opens (``mode=ro`` URI) cannot WAL-checkpoint, but they still
  go through this module so the scan test has a single choke point.

Why construction-time: instantiating ``DatabaseStorage`` against a WAL
database rewrites main+WAL (checkpoint) with zero row changes (proven in
a sandbox probe). The guard therefore fires BEFORE any ``sqlite3.connect``
or schema init, not after.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # studio-backend/
LIVE_DB_DIR = BACKEND_ROOT / "data"
LIVE_DB_FILE = LIVE_DB_DIR / "studio.db"
DEV_DIR_NAME = "data-dev"


class LiveDatabaseRefused(RuntimeError):
    """Raised when code tries to open the live DB without both opt-in flags."""


def _under_pytest() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is not None or "pytest" in sys.modules


def _flags_present() -> bool:
    return (
        os.getenv("STUDIO_ALLOW_LIVE_DB") == "1"
        and os.getenv("STUDIO_PRIMARY_WRITER") == "1"
    )


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.expanduser().resolve() == b.expanduser().resolve()
    except Exception:
        return False


def is_live_path(path: str | Path) -> bool:
    """True if *path* is the live DB file or a file inside the live DB dir."""
    p = Path(path).expanduser()
    if _same_path(p, LIVE_DB_FILE):
        return True
    try:
        return _same_path(p.resolve().parent, LIVE_DB_DIR) and p.suffix in {
            ".db",
            ".wal",
            ".shm",
            ".db-wal",
            ".db-shm",
        }
    except Exception:
        return False


def assert_live_open_allowed(
    target: str | Path,
    *,
    _live_dir: Path = LIVE_DB_DIR,
    _force_test: bool | None = None,
) -> None:
    """Fail closed if *target* is the live DB without both opt-in flags.

    ``_live_dir`` / ``_under_pytest`` are injectable for unit tests so the
    real live path is never touched by the test suite.
    """
    p = Path(target).expanduser()
    live_file = _live_dir / "studio.db"
    live = _same_path(p, live_file) or _same_path(p, _live_dir)
    if not live:
        try:
            rp = p.resolve()
            live = rp == live_file.resolve() or rp.parent == _live_dir.resolve()
        except Exception:
            live = False
    if not live:
        return
    under_test = _force_test if _force_test is not None else _under_pytest()
    if under_test:
        raise LiveDatabaseRefused(
            "refusing: tests can never resolve the live DB path "
            f"({target}); use tmp_path / an isolated copy"
        )
    if os.getenv("STUDIO_ALLOW_LIVE_DB") != "1" or os.getenv("STUDIO_PRIMARY_WRITER") != "1":
        raise LiveDatabaseRefused(
            "refusing to open the live DB path "
            f"({target}); set BOTH STUDIO_ALLOW_LIVE_DB=1 and "
            "STUDIO_PRIMARY_WRITER=1 to opt in explicitly"
        )


def resolve_db_dir(
    explicit: str | Path | None = None,
    *,
    _live_dir: Path = LIVE_DB_DIR,
) -> Path:
    """Resolve the database DIRECTORY every entry point must use.

    Precedence: explicit arg > STUDIO_STORAGE_PATH env > pytest-isolated
    ``/tmp`` dir > dev-copy default (``studio-backend/data-dev``).
    Raises :class:`LiveDatabaseRefused` if the result is the live dir.
    """
    if explicit is not None:
        resolved = Path(explicit).expanduser()
    elif os.getenv("STUDIO_STORAGE_PATH"):
        resolved = Path(os.getenv("STUDIO_STORAGE_PATH", "")).expanduser()
    elif _under_pytest():
        resolved = Path(f"/tmp/studio-backend-pytest-{os.getpid()}")
    else:
        resolved = Path(
            os.getenv("STUDIO_DEV_DB_DIR") or (BACKEND_ROOT / DEV_DIR_NAME)
        ).expanduser()
    if _same_path(resolved, _live_dir):
        assert_live_open_allowed(resolved / "studio.db", _live_dir=_live_dir)
    return resolved


def resolve_db_file(explicit: str | Path | None = None) -> Path:
    """Resolve the full ``studio.db`` FILE path with the live guard applied."""
    if explicit is not None and Path(explicit).suffix != "":
        assert_live_open_allowed(explicit)
        return Path(explicit).expanduser()
    return resolve_db_dir(explicit) / "studio.db"


def open_db_readonly(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite DB strictly read-only (WAL-checkpoint-immune)."""
    uri = f"file:{Path(path).expanduser()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def open_db_readwrite(
    path: str | Path, *, timeout: float = 30.0
) -> sqlite3.Connection:
    """Guarded read-write open: refuses the live path without both flags."""
    assert_live_open_allowed(path)
    return sqlite3.connect(str(Path(path).expanduser()), timeout=timeout)


def backup_database(source: str | Path, dest: str | Path) -> None:
    """Online-backup copy guarded the same way as any live open.

    The source open is read-write (as required by the backup API's source
    handle) and therefore refuses the live path without both opt-in flags.
    """
    assert_live_open_allowed(source)
    src = open_db_readwrite(source, timeout=60.0)
    dst = sqlite3.connect(str(Path(dest).expanduser()))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
