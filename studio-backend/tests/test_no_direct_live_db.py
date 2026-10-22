"""Repo-wide guardrail: no direct live-DB opens outside the central resolver.

Scans non-test source for:
  Rule A: ``sqlite3.connect(`` literals outside ``app/data/db_guard.py``.
  Rule B: live-path literals (``data/studio.db`` path spellings) outside
    ``app/data/db_guard.py`` (defines them) and the explicitly allowlisted
    files that carry their own live refusal plus test coverage.

Allowlist rationale:
- ``scripts/inspect_scene_direction_snapshot.py`` keeps a ``LIVE_DB``
  constant, but every use is copy-first + ``_assert_readonly_copy`` refusal
  (``resolved_copy == LIVE`` raises), and its tests run against copies.
- ``scripts/repair_orphaned_image_prompts.py`` defaults ``--db`` at the live
  path but refuses ``--apply`` against live (``REFUSING to --apply``) and
  opens through ``DatabaseStorage`` (centrally guarded since Part 2).
"""
from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

CONNECT_LITERAL = "sqlite3.connect("

PATH_LITERALS = (
    'data/studio.db',
    '"data" / "studio.db"',
    "'data' / 'studio.db'",
    '"data/studio.db"',
    "'data/studio.db'",
)

ALLOWLIST_CONNECT: set[str] = {
    # the central choke point itself
    "studio-backend/app/data/db_guard.py",
}

ALLOWLIST_PATH_LITERAL: set[str] = {
    "studio-backend/app/data/db_guard.py",  # canonical definition
    # own live refusal + copy-first reads + dedicated tests
    "studio-backend/scripts/inspect_scene_direction_snapshot.py",
    # --apply refusal + DatabaseStorage construction (centrally guarded)
    "studio-backend/scripts/repair_orphaned_image_prompts.py",
}

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "outputs"}
SKIP_SUFFIXES = (".pyc",)

# Frozen evidence / scratch subtrees: not entry points, never collected by the
# backend suite (testpaths = app tests). Documented here, not allowlisted.
SKIP_PREFIXES = (
    ".temp/",
    ".freebuff/",
    "studio-backend/.validation/",
    "studio-backend/data/",
    "studio-backend/reports/",
    "studio-backend/outputs/",
    "studio-backend/backups/",
    "studio-backend/static/",
    "studio-backend/deployment/",
    "studio-backend/models/",
)


def _scan_roots() -> list[Path]:
    return [
        BACKEND_ROOT / "app",
        BACKEND_ROOT / "scripts",
        REPO_ROOT / "scripts",
        REPO_ROOT / "tools",
    ]


def _top_level_files() -> list[Path]:
    files = list(BACKEND_ROOT.glob("*.py"))
    files += [REPO_ROOT / name for name in ("check_asset_urls.py", "health_check.py")]
    return [f for f in files if f.is_file()]


def _is_test_file(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or "tests" in path.parts
    )


def _iter_files():
    seen: set[Path] = set()
    for root in _scan_roots() + [BACKEND_ROOT, REPO_ROOT]:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = _rel(path)
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if rel.startswith(SKIP_PREFIXES):
                continue
            if path.suffix not in (".py",):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path
    for path in _top_level_files():
        if path not in seen:
            seen.add(path)
            yield path


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def test_no_direct_sqlite_connect_outside_guard():
    offenders = []
    for path in _iter_files():
        if _is_test_file(path):
            continue
        rel = _rel(path)
        if rel in ALLOWLIST_CONNECT:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if CONNECT_LITERAL in line:
                offenders.append(f"{rel}:{i}: {stripped[:120]}")
    assert offenders == [], (
        "direct sqlite3.connect outside app/data/db_guard.py:\n" + "\n".join(offenders)
    )


def test_no_live_path_literal_outside_allowlist():
    offenders = []
    for path in _iter_files():
        if _is_test_file(path):
            continue
        rel = _rel(path)
        if rel in ALLOWLIST_PATH_LITERAL:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "db_guard" in line:
                continue
            if any(lit in line for lit in PATH_LITERALS):
                offenders.append(f"{rel}:{i}: {stripped[:120]}")
    assert offenders == [], (
        "live-path literal outside allowlist:\n" + "\n".join(offenders)
    )
