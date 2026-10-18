"""Resolve app-served media URLs to on-disk paths inside the backend tree.

The backend serves generated media through the StaticFiles mounts declared
in ``main.py``::

    /outputs       -> <backend>/outputs/
    /previs-assets -> <backend>/outputs/previs/
    /static        -> <backend>/static/

Reference assets stored in the database (and storyboard stills) use these
web-root paths, but the *local* provider adapters (Phosphene LTX, MiniMax
H3 via ComfyUI) need real files to upload. This module is the single
shared mapping so every local adapter agrees on how to read them.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_MOUNT_DIRS: tuple[tuple[str, Path], ...] = (
    ("/previs-assets", _BACKEND_ROOT / "outputs" / "previs"),
    ("/outputs", _BACKEND_ROOT / "outputs"),
    ("/static", _BACKEND_ROOT / "static"),
)


def resolve_media_url_to_path(value: object) -> Path | None:
    """Map an app-served media URL to an existing local file.

    Accepts the mounted web-root forms (``/outputs/...``, with or without a
    query string) and returns the resolved :class:`~pathlib.Path` only when
    the file actually exists on disk. Anything else — empty values,
    absolute http(s) URLs, foreign paths, missing files — returns ``None``
    so callers can fall through to their own handling.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in ("", "http", "https"):
        return None
    path = unquote(parsed.path)
    for mount, root in _MOUNT_DIRS:
        if path == mount or path.startswith(mount + "/"):
            rel = path[len(mount):].lstrip("/")
            if not rel:
                return None
            candidate = root / rel
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                return None
    return None
