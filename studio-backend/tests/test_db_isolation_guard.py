"""DB isolation guard tests (Part 2) — all tmp_path / isolated-DB only.

Proves: the live DB path cannot be opened or instantiated by default;
opening it requires BOTH opt-in flags; tests can never resolve it even
with the flags; the default resolves to a dev-copy location.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.data import db_guard
from app.data.db_guard import (
    LIVE_DB_DIR,
    LIVE_DB_FILE,
    LiveDatabaseRefused,
    assert_live_open_allowed,
    is_live_path,
    open_db_readonly,
    open_db_readwrite,
    resolve_db_dir,
    resolve_db_file,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _standin_live(tmp_path: Path) -> Path:
    d = tmp_path / "standin-live"
    d.mkdir()
    return d


# -- refusal: no flags ------------------------------------------------------

def test_resolve_live_dir_refuses_without_flags(tmp_path):
    live = _standin_live(tmp_path)
    with pytest.raises(LiveDatabaseRefused):
        resolve_db_dir(explicit=live, _live_dir=live)


def test_resolve_live_file_refuses_without_flags(tmp_path):
    live = _standin_live(tmp_path)
    with pytest.raises(LiveDatabaseRefused):
        assert_live_open_allowed(live / "studio.db", _live_dir=live)


def test_assert_refuses_with_only_one_flag(tmp_path, monkeypatch):
    live = _standin_live(tmp_path)
    target = live / "studio.db"
    monkeypatch.delenv("STUDIO_ALLOW_LIVE_DB", raising=False)
    monkeypatch.delenv("STUDIO_PRIMARY_WRITER", raising=False)
    with pytest.raises(LiveDatabaseRefused):
        assert_live_open_allowed(target, _live_dir=live)
    monkeypatch.setenv("STUDIO_ALLOW_LIVE_DB", "1")
    with pytest.raises(LiveDatabaseRefused):
        assert_live_open_allowed(target, _live_dir=live)
    monkeypatch.delenv("STUDIO_ALLOW_LIVE_DB")
    monkeypatch.setenv("STUDIO_PRIMARY_WRITER", "1")
    with pytest.raises(LiveDatabaseRefused):
        assert_live_open_allowed(target, _live_dir=live)


# -- allowed with both flags (stand-in live dir only, never the real one) ---

def test_allowed_with_both_flags_on_standin(tmp_path, monkeypatch):
    live = _standin_live(tmp_path)
    target = live / "studio.db"
    monkeypatch.setenv("STUDIO_ALLOW_LIVE_DB", "1")
    monkeypatch.setenv("STUDIO_PRIMARY_WRITER", "1")
    # _force_test=False simulates the (non-test) operator context the flags
    # are for; under real pytest the guard refuses unconditionally (see next).
    assert_live_open_allowed(target, _live_dir=live, _force_test=False)
    conn = open_db_readwrite(target)
    conn.execute("CREATE TABLE t (a TEXT)")
    conn.execute("INSERT INTO t VALUES ('x')")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    conn.close()


def test_non_live_paths_always_allowed(tmp_path, monkeypatch):
    monkeypatch.delenv("STUDIO_ALLOW_LIVE_DB", raising=False)
    monkeypatch.delenv("STUDIO_PRIMARY_WRITER", raising=False)
    other = tmp_path / "elsewhere" / "studio.db"
    assert_live_open_allowed(other, _live_dir=tmp_path / "standin-live")
    assert not is_live_path(other)


# -- construction-time guard -------------------------------------------------

def test_database_storage_init_refuses_live_without_flags(tmp_path):
    from app.data.storage import DatabaseStorage

    with pytest.raises(LiveDatabaseRefused):
        DatabaseStorage(str(LIVE_DB_DIR))


def test_database_storage_init_refuses_live_even_with_flags():
    """Tests can NEVER resolve the live path — flags do not override."""
    from app.data.storage import DatabaseStorage

    os.environ["STUDIO_ALLOW_LIVE_DB"] = "1"
    os.environ["STUDIO_PRIMARY_WRITER"] = "1"
    try:
        with pytest.raises(LiveDatabaseRefused):
            DatabaseStorage(str(LIVE_DB_DIR))
    finally:
        del os.environ["STUDIO_ALLOW_LIVE_DB"]
        del os.environ["STUDIO_PRIMARY_WRITER"]


# -- suite-wide guard: live open trips inside the test process --------------

def test_suite_guard_trips_on_live_rw_open():
    """The conftest sqlite patch refuses live RW opens with no override."""
    with pytest.raises(LiveDatabaseRefused):
        sqlite3.connect(str(LIVE_DB_FILE))


def test_suite_guard_allows_ro_uri(tmp_path):
    """Read-only opens cannot checkpoint and stay permitted (tmp copy)."""
    src = tmp_path / "r.db"
    c0 = sqlite3.connect(str(src))
    c0.execute("CREATE TABLE t (a TEXT)")
    c0.commit()
    c0.close()
    conn = open_db_readonly(src)
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    conn.close()


def test_pytest_default_storage_is_isolated():
    """Under pytest the default storage dir is the isolated tmp dir."""
    import tempfile
    resolved = resolve_db_dir()
    assert not is_live_path(resolved / "studio.db")
    assert str(resolved).startswith(tempfile.gettempdir())


# -- default (non-pytest) resolves to dev-copy location ----------------------

def test_default_resolves_to_dev_copy_outside_live():
    """Fresh interpreter (no pytest in sys.modules): default is data-dev."""
    code = (
        "import sys; assert 'pytest' not in sys.modules; "
        "from app.data.db_guard import resolve_db_dir; print(resolve_db_dir())"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("STUDIO_STORAGE_PATH", "STUDIO_DEV_DB_DIR", "PYTEST_CURRENT_TEST")
    }
    env["PATH"] = os.environ.get("PATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    resolved = Path(result.stdout.strip())
    assert resolved == BACKEND_ROOT / "data-dev", resolved
    assert resolved != LIVE_DB_DIR


# -- read-only helper is checkpoint-immune ------------------------------------

def test_open_db_readonly_cannot_write(tmp_path):
    db = tmp_path / "r.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (a TEXT)")
    conn.commit()
    conn.close()
    ro = open_db_readonly(db)
    assert ro.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO t VALUES ('x')")
    ro.close()


# -- data-dev is git-ignored ---------------------------------------------------

def test_dev_copy_dir_is_gitignored():
    repo = BACKEND_ROOT.parent
    inside_repo = (
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo),
            capture_output=True,
            timeout=30,
        ).returncode
        == 0
    )
    if not inside_repo:
        pytest.skip("no git worktree here (e.g. clean-export archive)")
    result = subprocess.run(
        ["git", "check-ignore", "-q", "studio-backend/data-dev/"],
        cwd=str(repo),
        timeout=30,
    )
    assert result.returncode == 0, "studio-backend/data-dev/ must be git-ignored"


# -- live-server scripts stay out of default collection -----------------------

def _collect_root_scope(extra_env: dict | None = None):
    repo = BACKEND_ROOT.parent
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--continue-on-collection-errors",
        ],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    node_ids = [
        line
        for line in result.stdout.splitlines()
        if "::" in line
    ]
    return node_ids


_LIVE_SCRIPT_FILES = [
    "test_project_creation_fix.py",
    "test_corrector_direct.py",
    "test_corrector_variations.py",
    "test_defensive_validation.py",
]


def test_live_scripts_present_but_not_collected_by_default():
    """Amendment 1: files stay in place; root scope drops exactly the 8."""
    for name in _LIVE_SCRIPT_FILES:
        assert (BACKEND_ROOT / name).is_file(), f"{name} must not be moved"
    node_ids = _collect_root_scope()
    leaked = [n for n in node_ids if any(n.endswith(f) or f + "::" in n for f in _LIVE_SCRIPT_FILES)]
    assert leaked == [], f"live scripts collected by default: {leaked[:5]}"


def test_live_scripts_reenabled_with_opt_in():
    node_ids = _collect_root_scope({"STUDIO_ALLOW_LIVE_SCRIPTS": "1"})
    found = [n for n in node_ids if any(f + "::" in n for f in _LIVE_SCRIPT_FILES)]
    # 8 node IDs (1 + 1 + 2 + 4) proved in the Part 1 evidence pass
    assert len(found) == 8, f"expected 8 opt-in node IDs, got {len(found)}"
