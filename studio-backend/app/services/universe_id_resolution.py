"""Central alias-aware universe node ID resolution.

Every code path that resolves a universe node by ID must go through
:func:`resolve_universe_node` (or :func:`resolve_setting_entity` for the
setting-entity case) instead of matching ``get_universe_nodes`` rows
directly. The resolver:

1. Returns the exact node when ``node_id`` exists in ``universe_nodes``.
2. Otherwise consults ``universe_id_aliases`` (``old_node_id`` ->
   ``current_node_id``) and returns the current node when the alias target
   still exists.
3. Otherwise returns ``None`` — it never guesses.

The alias table is created lazily by the storage write path only. Read paths
tolerate its absence (a missing table, or a storage double without alias
methods, behaves exactly like today: step 2 is skipped).

Alias creation rule (used by ``repair_universe_aliases`` on the service):
an old node maps to a current node only on an exact
``(project_id, node_type, normalized name)`` match with exactly one
candidate. Zero or multiple candidates means *no alias* — the caller must
preserve and report instead of picking. Matching never crosses projects.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Optional

logger = logging.getLogger("studio-universe-id-resolution")

_NODE_ID_PREFIXES = {
    "character": "char",
    "location": "loc",
    "lore": "lore",
    "object": "obj",
}


def normalize_universe_name(node_type: str, name: str) -> str:
    """Normalize a node name the same way rebuild keys are derived.

    Locations strip a leading INT./EXT./INT-EXT. heading prefix and keep the
    part before the first comma (mirrors the service's location extraction);
    everything is compared upper-cased and stripped.
    """
    text = str(name or "").strip()
    if str(node_type or "").lower() == "location":
        text = re.sub(r"^(INT\.|EXT\.|INT/EXT\.)\s*", "", text, flags=re.IGNORECASE).strip()
        text = text.split(",")[0].strip()
    return text.upper()


def stable_universe_key(project_id: str, node_type: str, name: str) -> tuple[str, str, str]:
    """Stable identity key: exact (project, lowercased type, normalized name)."""
    return (
        str(project_id or ""),
        str(node_type or "").lower(),
        normalize_universe_name(node_type, name),
    )


def stable_node_id(project_id: str, node_type: str, name: str) -> str:
    """Deterministic node ID for genuinely new nodes (hash scheme)."""
    prefix = _NODE_ID_PREFIXES.get(str(node_type or "").lower(), "obj")
    digest = hashlib.sha1(
        "|".join(stable_universe_key(project_id, node_type, name)).encode("utf-8")
    ).hexdigest()[:8]
    return f"{prefix}-{digest}"


def stable_relationship_id(project_id: str, from_node: str, to_node: str, rel_type: str) -> str:
    """Deterministic relationship ID from its endpoints and type."""
    digest = hashlib.sha1(
        "|".join(
            [str(project_id or ""), str(from_node or ""), str(to_node or ""), str(rel_type or "")]
        ).encode("utf-8")
    ).hexdigest()[:8]
    return f"rel-{digest}"


def _stored_nodes(storage: Any, project_id: str) -> list[dict]:
    reader = getattr(storage, "get_universe_nodes", None)
    if not callable(reader):
        return []
    try:
        return [row for row in (reader(project_id) or []) if isinstance(row, dict)]
    except Exception:  # noqa: BLE001 — a broken reader fails closed, never raises here
        return []


def _alias_target(storage: Any, node_id: str) -> Optional[str]:
    reader = getattr(storage, "get_universe_id_alias", None)
    if not callable(reader):
        return None
    try:
        row = reader(str(node_id))
    except Exception:  # noqa: BLE001 — missing table / broken store == no alias
        return None
    if isinstance(row, dict) and str(row.get("current_node_id") or "").strip():
        return str(row["current_node_id"]).strip()
    return None


def resolve_universe_node(storage: Any, project_id: str, node_id: str) -> Optional[dict]:
    """Resolve one universe node by ID, alias-aware, never guessing.

    Returns the node dict when ``node_id`` exists for the project, else the
    alias target node when a ``universe_id_aliases`` row maps it to a live
    node, else ``None``.
    """
    clean_id = str(node_id or "").strip()
    clean_project = str(project_id or "").strip()
    if not clean_id or not clean_project:
        return None
    nodes = _stored_nodes(storage, clean_project)
    for row in nodes:
        if str(row.get("project_id") or "") == clean_project and str(row.get("node_id") or "") == clean_id:
            return row
    target = _alias_target(storage, clean_id)
    if not target:
        return None
    for row in nodes:
        if str(row.get("project_id") or "") == clean_project and str(row.get("node_id") or "") == target:
            logger.info(
                "UNIVERSE_NODE_ALIAS_RESOLVED | project_id=%s node_id=%s current_node_id=%s",
                clean_project,
                clean_id,
                target,
            )
            return row
    return None


def resolve_setting_entity(storage: Any, project_id: str, setting_id: str) -> Optional[dict]:
    """Resolve a location-type setting entity by ID, alias-aware.

    Same as :func:`resolve_universe_node` but additionally requires the
    resolved row to be a ``location`` node for the project.
    """
    node = resolve_universe_node(storage, project_id, setting_id)
    if (
        node is not None
        and str(node.get("project_id") or "") == str(project_id or "").strip()
        and str(node.get("node_type") or "") == "location"
    ):
        return node
    return None


def match_alias_candidate(
    existing_nodes: list[dict], old_node: dict
) -> tuple[Optional[str], str]:
    """Apply the strict alias match rule for one old node row.

    Returns ``(current_node_id, "")`` on exactly one
    ``(project_id, node_type, normalized name)`` match, else
    ``(None, reason)`` where reason is ``"no_candidate"`` or ``"ambiguous"``.
    Never matches across projects and never picks among multiples.
    """
    if not isinstance(old_node, dict):
        return None, "no_candidate"
    key = stable_universe_key(
        str(old_node.get("project_id") or ""),
        str(old_node.get("node_type") or ""),
        str(old_node.get("name") or ""),
    )
    if not key[0] or not key[1] or not key[2]:
        return None, "no_candidate"
    candidates = [
        row
        for row in (existing_nodes or [])
        if isinstance(row, dict)
        and stable_universe_key(
            str(row.get("project_id") or ""),
            str(row.get("node_type") or ""),
            str(row.get("name") or ""),
        )
        == key
    ]
    if len(candidates) == 1:
        return str(candidates[0].get("node_id") or ""), ""
    if not candidates:
        return None, "no_candidate"
    return None, "ambiguous"
