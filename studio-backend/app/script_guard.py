"""Refuse-by-default gate for live-spend one-off scripts.

Why this module lives at ``app/script_guard.py`` and not ``app/data/``:
``app/__init__.py`` is a single comment line (no imports, no side effects),
so ``from app.script_guard import ...`` executes only this file plus the
empty package init. ``app/data/__init__.py`` instead imports
``app.data.storage`` (SQLite/DatabaseStorage, models, db guard chain), which
is exactly the heavyweight import a pre-spend gate must not trigger. The
guard itself is stdlib-only (``os``/``sys``/``logging``/``datetime``) so
importing it can never open a database, touch the network, or spend.

Placement contract (enforced by ``tests/test_live_spend_guard_scan.py``):
- Standalone scripts (never imported): invoke at module top level, after
  the ``sys.path`` insert and before ``dotenv``/``app.*``/network imports.
- Scripts also loaded as modules (importlib or ``import scripts.*``):
  invoke as the first statement of ``main()`` (or the ``__main__`` block);
  module top level must contain no spend/write calls.
- Scripts outside ``studio-backend/`` reuse their existing
  ``sys.path.insert(0, .../studio-backend)`` line; that path manipulation
  performs no import or I/O and is covered by the import-path test.

Gate contract:
- Runway-spend scripts call :func:`require_live_spend_gate`. The call
  returns only when BOTH ``STUDIO_ALLOW_LIVE_SPEND_SCRIPT=1`` (exact) AND
  ``--confirm-spend=<this-script-basename>`` (exact) are present and
  ``provider == "runway"``. Anything else refuses with exit code 2.
- Non-approved-provider scripts call :func:`refuse_non_approved_provider`,
  which always refuses (Runway is the only approved provider, D1-D6 stand).
- Refusal prints what the script would do plus the estimated exposure,
  never secrets (no env values, keys, key fragments, prompt text, or argv
  values — presence booleans only). Log timestamps use America/New_York.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import NoReturn

try:  # Python 3.11+ ships zoneinfo; fall back to UTC if tzdata is missing.
    from zoneinfo import ZoneInfo

    _LOCAL_TZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - environment without tzdata
    _LOCAL_TZ = timezone.utc

ENV_FLAG = "STUDIO_ALLOW_LIVE_SPEND_SCRIPT"
CONFIRM_PREFIX = "--confirm-spend="
APPROVED_PROVIDER = "runway"
EXIT_REFUSED = 2

logger = logging.getLogger("studio.script_guard")


def _now_iso() -> str:
    return datetime.now(_LOCAL_TZ).isoformat()


def _confirm_value() -> str | None:
    for arg in sys.argv[1:]:
        if arg.startswith(CONFIRM_PREFIX):
            return arg[len(CONFIRM_PREFIX):]
    return None


def _refuse(*, script: str, what: str, provider: str, exposure: str, reason: str) -> NoReturn:
    stamp = _now_iso()
    env_present = os.getenv(ENV_FLAG) == "1"
    confirm_present = _confirm_value() is not None
    lines = [
        f"[{stamp}] REFUSING live-spend script: {script}",
        f"  what: {what}",
        f"  provider: {provider}",
        f"  estimated exposure: {exposure}",
        f"  reason: {reason}",
        f"  env {ENV_FLAG}=1 present: {env_present}",
        f"  --confirm-spend=<basename> present: {confirm_present}",
    ]
    if provider != APPROVED_PROVIDER:
        lines.append(
            "  Runway is the only approved provider (D1-D6 stand); "
            "non-approved-provider scripts never run."
        )
    else:
        lines.append(
            f"  To proceed explicitly: export {ENV_FLAG}=1 and re-invoke with "
            f"--confirm-spend={script}."
        )
    message = "\n".join(lines)
    print(message, file=sys.stderr)
    logger.warning(
        "refusing live-spend script script=%s provider=%s reason=%s "
        "env_present=%s confirm_present=%s stamp=%s",
        script,
        provider,
        reason,
        env_present,
        confirm_present,
        stamp,
    )
    raise SystemExit(EXIT_REFUSED)


def require_live_spend_gate(
    script_file: str,
    *,
    what: str,
    exposure: str,
    provider: str = APPROVED_PROVIDER,
) -> None:
    """Allow a Runway-spend script to continue only on dual opt-in.

    Must be called before any spend-capable, network, or database work.
    Returns ``None`` when authorised; otherwise prints the refusal (what it
    would do + estimated exposure, no secrets) and raises ``SystemExit(2)``.
    """
    script = os.path.basename(script_file)
    if provider != APPROVED_PROVIDER:
        _refuse(
            script=script,
            what=what,
            provider=provider,
            exposure=exposure,
            reason=f"non-approved provider '{provider}'",
        )
    if os.getenv(ENV_FLAG) != "1" or _confirm_value() != script:
        _refuse(
            script=script,
            what=what,
            provider=provider,
            exposure=exposure,
            reason=(
                "dual opt-in missing: requires BOTH "
                f"{ENV_FLAG}=1 AND --confirm-spend={script}"
            ),
        )
    return None


def refuse_non_approved_provider(
    script_file: str,
    *,
    what: str,
    provider: str,
) -> None:
    """Unconditionally refuse scripts whose spend path is not Runway.

    Always prints the refusal and raises ``SystemExit(2)``, even when the
    dual opt-in is present. Keeps non-approved-provider one-offs unrunnable
    until an explicit owner decision migrates or decommissions them.
    """
    script = os.path.basename(script_file)
    _refuse(
        script=script,
        what=what,
        provider=provider,
        exposure="n/a - never authorised",
        reason=f"non-approved provider '{provider}'",
    )
