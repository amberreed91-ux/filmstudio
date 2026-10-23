"""Universe node-ID stability: alias resolution, stable rebuild, non-blocking absence.

Isolated-DB tests only (DatabaseStorage(tmp_path)); never touch live data.
Naming: every test carries the ``node_id`` comm so fixture-fingerprint runs
can gate on this family.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from app.data.storage import DatabaseStorage
from app.services import universe_id_resolution as uir
from app.services.universe_graph_service import universe_graph_service


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _scenes_two() -> list[dict]:
    """Two scenes yielding a character, two locations and theme lore."""
    return [
        {
            "scene_id": "scene_001",
            "characters": ["Maya"],
            "heading": "INT. MAYA'S KITCHEN - EVENING",
            "text": "Maya remembers the old garden and the grief.",
        },
        {
            "scene_id": "scene_002",
            "characters": ["Maya", "Dre"],
            "heading": "EXT. DOWNTOWN CHICAGO - AFTER THE APOCALYPSE",
            "text": "Memory and loss hang over the empty street.",
        },
    ]


def _svc(storage: DatabaseStorage):
    svc = universe_graph_service
    svc.storage = storage
    return svc


def _fp_table(storage: DatabaseStorage, table: str) -> str:
    conn = sqlite3.connect(storage.db_path)
    try:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        if not cols:
            return "missing"
        h = hashlib.sha256()
        for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
            h.update(repr(tuple(row)).encode("utf-8", "replace") + b"\n")
        n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        return f"{n}:{h.hexdigest()[:16]}"
    finally:
        conn.close()


def _ids(storage: DatabaseStorage, project_id: str) -> tuple[set[str], set[str]]:
    nodes = storage.get_universe_nodes(project_id)
    rels = storage.get_universe_relationships(project_id)
    return ({n["node_id"] for n in nodes}, {r["relationship_id"] for r in rels})


def _row_map(storage: DatabaseStorage, table: str, id_col: str,
             project_id: str) -> dict[str, tuple]:
    """Full rows (plus rowid) keyed by ID for one project."""
    conn = sqlite3.connect(storage.db_path)
    try:
        rows = conn.execute(
            f'SELECT rowid, * FROM "{table}" WHERE project_id = ? ORDER BY rowid',
            (project_id,),
        ).fetchall()
        cols = [c[0] for c in conn.execute(f'SELECT * FROM "{table}" LIMIT 0').description]
        id_idx = cols.index(id_col) + 1  # +1 for the leading rowid column
        return {str(r[id_idx]): tuple(r) for r in rows}
    finally:
        conn.close()




def _report_nodes(report: dict) -> list[dict]:
    """Report nodes as plain dicts regardless of model wrapping."""
    out = []
    for n in report["nodes"]:
        out.append(n.model_dump() if hasattr(n, "model_dump") else dict(n))
    return out

# ---------------------------------------------------------------------------
# 1. alias resolution
# ---------------------------------------------------------------------------

def test_node_id_alias_resolves_old_loc_id(tmp_path):
    """With an alias row, old IDs loc-c8f88b9c/loc-b543d669 resolve to new nodes."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-alias"
    nodes = _report_nodes(_svc(storage).rebuild_universe_graph_from_scenes(pid, _scenes_two()))
    loc_nodes = [n for n in nodes if n["node_type"] == "location"]
    assert len(loc_nodes) >= 2

    old_a, old_b = "loc-c8f88b9c", "loc-b543d669"
    storage.save_universe_id_alias(pid, old_a, loc_nodes[0]["node_id"], reason="test")
    storage.save_universe_id_alias(pid, old_b, loc_nodes[1]["node_id"], reason="test")

    got_a = uir.resolve_universe_node(storage, pid, old_a)
    got_b = uir.resolve_universe_node(storage, pid, old_b)
    assert got_a is not None and got_a["node_id"] == loc_nodes[0]["node_id"]
    assert got_b is not None and got_b["node_id"] == loc_nodes[1]["node_id"]

    # direct (non-alias) resolution still works
    direct = uir.resolve_universe_node(storage, pid, loc_nodes[0]["node_id"])
    assert direct is not None and direct["node_id"] == loc_nodes[0]["node_id"]

    # zero reference rows modified by resolution: resolver is read-only
    storage.save_reference_asset({
        "ref_id": "ref-alias-1", "project_id": pid, "kind": "environment",
        "image_url": "http://x/y.png", "target_type": "setting",
        "target_id": old_a, "approval_state": "approved",
    })
    before = _fp_table(storage, "reference_assets")
    uir.resolve_universe_node(storage, pid, old_a)
    assert _fp_table(storage, "reference_assets") == before


def test_node_id_no_alias_table_passthrough(tmp_path):
    """Absent alias table behaves exactly like today: exact hit or None."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-noalias"
    nodes = _report_nodes(_svc(storage).rebuild_universe_graph_from_scenes(pid, _scenes_two()))
    # no alias method ever called -> table must not exist
    with storage._get_connection() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "universe_id_aliases" not in names

    assert uir.resolve_universe_node(storage, pid, nodes[0]["node_id"]) is not None
    assert uir.resolve_universe_node(storage, pid, "loc-does-not-exist") is None
    # table still must not exist after read-only resolution of unknown id
    with storage._get_connection() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "universe_id_aliases" not in names


def test_node_id_alias_match_refuses_ambiguous(tmp_path):
    """Two same-name locations in different scenes: repair must not guess."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-ambig"
    svc = _svc(storage)
    scenes = [
        {"scene_id": "scene_A", "characters": ["Maya"],
         "heading": "INT. WAREHOUSE, DAY", "text": "Maya waits."},
        {"scene_id": "scene_B", "characters": ["Maya"],
         "heading": "EXT. WAREHOUSE, NIGHT", "text": "Maya returns."},
    ]
    svc.rebuild_universe_graph_from_scenes(pid, scenes)
    # legacy divergence: a second same-name location row tied to another scene
    storage.save_universe_node({
        "node_id": "loc-manual-second", "project_id": pid,
        "node_type": "location", "name": "Warehouse",
        "description": "legacy duplicate", "first_scene": "scene_B",
        "last_scene": "scene_B", "universe_tags": [],
    })
    nodes = [dict(r) for r in storage.get_universe_nodes(pid)]
    locs = [n for n in nodes if n["node_type"] == "location"]
    assert len(locs) == 2  # precondition: two same-name locations, diff scenes
    assert len({n["first_scene"] for n in locs}) == 2
    old = {"node_id": "loc-legacy-warehouse", "node_type": "location",
           "name": "Warehouse", "project_id": pid,
           "first_scene": "scene_A"}
    # strict match rule: exact (project, type, normalized name), one winner
    target, reason = uir.match_alias_candidate(nodes, old)
    assert target is None and reason == "ambiguous"
    result = svc.repair_universe_aliases(pid, [old])
    assert result["aliased"] == []
    assert result["ambiguous"] == [{"old_node_id": "loc-legacy-warehouse"}]
    assert storage.list_universe_id_aliases(pid) == []


# ---------------------------------------------------------------------------
# 2. stable rebuild
# ---------------------------------------------------------------------------

def test_node_id_rebuild_adopts_existing_ids(tmp_path):
    """First rebuild keeps the ID of every existing (project,type,name) match."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-adopt"
    svc = _svc(storage)
    scenes = _scenes_two()
    first_run = _report_nodes(svc.rebuild_universe_graph_from_scenes(pid, scenes))
    assert first_run  # precondition        # simulate legacy IDs: rename every node id (and its rel endpoints)
    with storage._get_connection() as conn:
            conn.execute("PRAGMA defer_foreign_keys = ON")
            cur = conn.cursor()
            for n in first_run:
                legacy = f"legacy-{n['node_id']}"
                cur.execute("UPDATE universe_nodes SET node_id=? WHERE node_id=? AND project_id=?",
                            (legacy, n["node_id"], pid))
                cur.execute("UPDATE universe_relationships SET from_node=? WHERE from_node=? AND project_id=?",
                            (legacy, n["node_id"], pid))
                cur.execute("UPDATE universe_relationships SET to_node=? WHERE to_node=? AND project_id=?",
                            (legacy, n["node_id"], pid))
            conn.commit()
    legacy_ids = {n["node_id"] for n in storage.get_universe_nodes(pid)}
    assert all(i.startswith("legacy-") for i in legacy_ids)

    report = svc.rebuild_universe_graph_from_scenes(pid, scenes)
    second_run = _report_nodes(report)
    kept = {n["node_id"] for n in second_run}
    assert kept == legacy_ids  # zero ID churn on the 24-node-shaped graph
    assert report["reused_ids"] == len(legacy_ids)
    assert report["deleted_nodes"] == []


def test_node_id_rebuild_twice_identical(tmp_path):
    """Double rebuild: byte-identical node/rel ID sets, no row growth."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-twice"
    svc = _svc(storage)
    scenes = _scenes_two()
    svc.rebuild_universe_graph_from_scenes(pid, scenes)
    ids_a = _ids(storage, pid)
    counts_a = (len(storage.get_universe_nodes(pid)),
                len(storage.get_universe_relationships(pid)))
    svc.rebuild_universe_graph_from_scenes(pid, scenes)
    assert _ids(storage, pid) == ids_a
    assert (len(storage.get_universe_nodes(pid)),
            len(storage.get_universe_relationships(pid))) == counts_a


def test_node_id_second_project_isolated(tmp_path):
    """Rebuilding project B never churns project A's IDs (synthetic 2nd project)."""
    storage = DatabaseStorage(tmp_path)
    svc = _svc(storage)
    svc.rebuild_universe_graph_from_scenes("proj-A", _scenes_two())
    other = [
        {"scene_id": "scene_001", "characters": ["Rook"],
         "heading": "EXT. HARBOR - DAWN", "text": "Rook faces redemption."},
    ]
    svc.rebuild_universe_graph_from_scenes("proj-B", other)
    ids_a_before = _ids(storage, "proj-A")
    svc.rebuild_universe_graph_from_scenes("proj-B", other)
    assert _ids(storage, "proj-A") == ids_a_before
    assert len(storage.get_universe_nodes("proj-B")) > 0


# ---------------------------------------------------------------------------
# 3. non-blocking absence
# ---------------------------------------------------------------------------

def test_node_id_absent_referenced_preserved_reported_not_blocking(tmp_path, caplog):
    """Referenced-but-absent node is preserved, logged, reported — never raises."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-absent"
    svc = _svc(storage)
    nodes = _report_nodes(svc.rebuild_universe_graph_from_scenes(pid, _scenes_two()))
    loc = next(n for n in nodes if n["node_type"] == "location")
    storage.save_reference_asset({
        "ref_id": "ref-absent-1", "project_id": pid, "kind": "environment",
        "image_url": "http://x/y.png", "target_type": "setting",
        "target_id": loc["node_id"], "approval_state": "approved",
    })
    # drop the scene that produced the location -> node absent from source
    trimmed = [s for s in _scenes_two()
               if s["scene_id"] != (loc.get("first_scene") or "")]
    assert trimmed and len(trimmed) < len(_scenes_two())

    with caplog.at_level("WARNING"):
        report = svc.rebuild_universe_graph_from_scenes(pid, trimmed)
    nodes2 = _report_nodes(report)
    assert any(n["node_id"] == loc["node_id"] for n in nodes2)  # preserved
    preserved_ids = [p["node_id"] for p in report["preserved_referenced"]]
    assert loc["node_id"] in preserved_ids
    entry = next(p for p in report["preserved_referenced"]
                 if p["node_id"] == loc["node_id"])
    assert "reference_assets" in entry["referencing"]
    assert any("UNIVERSE_NODE_PRESERVED" in r.message and
               f"project_id={pid}" in r.message and
               f"node_id={loc['node_id']}" in r.message and
               "reference_assets" in r.message
               for r in caplog.records)

    # scene-action path stays non-blocking: auto_populate swallows nothing,
    # raises nothing (route-level guards remain as backstop)
    svc._get_project_scenes = lambda _pid: trimmed  # noqa: SLF001
    svc.auto_populate_from_scenes(pid)  # must not raise


# ---------------------------------------------------------------------------
# 4. zero reference modification across rebuild
# ---------------------------------------------------------------------------

def test_node_id_rebuild_zero_reference_rows_modified(tmp_path):
    """Alias + rebuild touch zero reference rows (fingerprint before/after)."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-zeroref"
    svc = _svc(storage)
    report = svc.rebuild_universe_graph_from_scenes(pid, scenes := _scenes_two())
    nodes = _report_nodes(report)
    loc = next(n for n in nodes if n["node_type"] == "location")
    old_id = "loc-c8f88b9c"
    storage.save_universe_id_alias(pid, old_id, loc["node_id"], reason="test")
    storage.save_reference_asset({
        "ref_id": "ref-zero-1", "project_id": pid, "kind": "environment",
        "image_url": "http://x/y.png", "target_type": "setting",
        "target_id": old_id, "approval_state": "approved",
    })
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute(
            """INSERT INTO storyboard_blueprint_versions
               (version_id, blueprint_id, project_id, scene_id, version_number,
                status, change_reason, provenance_json, inspection_json, created_at)
               VALUES (?, ?, ?, ?, 1, 'draft', '', ?, '{}', datetime('now'))""",
            ("sbv_test1", "sbp_test1", pid, "scene_002",
             f'{{"setting_node_id": "{old_id}"}}'),
        )
        conn.commit()
    before = (_fp_table(storage, "reference_assets"),
              _fp_table(storage, "storyboard_blueprint_versions"))

    assert uir.resolve_universe_node(storage, pid, old_id)["node_id"] == loc["node_id"]
    svc.rebuild_universe_graph_from_scenes(pid, scenes)
    assert (_fp_table(storage, "reference_assets"),
            _fp_table(storage, "storyboard_blueprint_versions")) == before


# ---------------------------------------------------------------------------
# 5. cascade-free true upsert (no REPLACE delete, no FK cascade)
# ---------------------------------------------------------------------------

def _node_ids_by_type(nodes: list[dict], node_type: str) -> list[str]:
    return sorted(n["node_id"] for n in nodes if n["node_type"] == node_type)


def test_node_id_rebuild_rowids_stable(tmp_path):
    """Rebuild twice: node AND relationship rowids never move (no delete)."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-rowid"
    svc = _svc(storage)
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    before_nodes = _row_map(storage, "universe_nodes", "node_id", pid)
    before_rels = _row_map(storage, "universe_relationships", "relationship_id", pid)
    assert before_nodes and before_rels
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    after_nodes = _row_map(storage, "universe_nodes", "node_id", pid)
    after_rels = _row_map(storage, "universe_relationships", "relationship_id", pid)
    assert {k: v[0] for k, v in after_nodes.items()} == \
        {k: v[0] for k, v in before_nodes.items()}
    assert {k: v[0] for k, v in after_rels.items()} == \
        {k: v[0] for k, v in before_rels.items()}


def test_node_id_custom_relationship_survives_rebuild(tmp_path):
    """A user-authored (non-derived) relationship is byte-identical post-rebuild."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-customrel"
    svc = _svc(storage)
    nodes = _report_nodes(svc.rebuild_universe_graph_from_scenes(pid, _scenes_two()))
    char = _node_ids_by_type(nodes, "character")[0]
    loc = _node_ids_by_type(nodes, "location")[0]
    storage.save_universe_relationship({
        "relationship_id": "rel-user-custom-01", "project_id": pid,
        "from_node": char, "to_node": loc,
        "relationship_type": "custom-bond", "description": "user-authored note",
    })
    before = _row_map(storage, "universe_relationships", "relationship_id", pid)
    assert "rel-user-custom-01" in before
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    after = _row_map(storage, "universe_relationships", "relationship_id", pid)
    assert after["rel-user-custom-01"] == before["rel-user-custom-01"]


def test_node_id_created_at_stable_on_rerun(tmp_path):
    """Rebuild never rewrites created_at on nodes or relationships."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-createdat"
    svc = _svc(storage)
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    nodes_before = {n["node_id"]: n["created_at"]
                    for n in storage.get_universe_nodes(pid)}
    rels_before = {r["relationship_id"]: r["created_at"]
                   for r in storage.get_universe_relationships(pid)}
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    assert {n["node_id"]: n["created_at"]
            for n in storage.get_universe_nodes(pid)} == nodes_before
    assert {r["relationship_id"]: r["created_at"]
            for r in storage.get_universe_relationships(pid)} == rels_before


def test_node_id_created_ids_zero_on_unchanged_rerun(tmp_path):
    """Second identical rebuild: created_ids==0, everything unchanged."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-nop"
    svc = _svc(storage)
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    rep = svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    assert rep["created_ids"] == 0
    assert rep["updated_ids"] == []
    assert rep["deleted_nodes"] == []
    live = {n["node_id"] for n in storage.get_universe_nodes(pid)}
    live |= {r["relationship_id"] for r in storage.get_universe_relationships(pid)}
    assert set(rep["unchanged_ids"]) == live


def test_node_id_nonderived_rows_identical(tmp_path):
    """Non-derived custom node/rel: counts and per-row content identical."""
    storage = DatabaseStorage(tmp_path)
    pid = "proj-nonderived"
    svc = _svc(storage)
    svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    storage.save_universe_node({
        "node_id": "chr-user-custom-01", "project_id": pid,
        "node_type": "character", "name": "Zzz Underived",
        "description": "user note", "first_scene": None,
        "last_scene": None, "universe_tags": [],
    })
    nodes = _report_nodes(svc.rebuild_universe_graph_from_scenes(pid, _scenes_two()))
    char = _node_ids_by_type(nodes, "character")[0]
    storage.save_universe_relationship({
        "relationship_id": "rel-user-custom-02", "project_id": pid,
        "from_node": "chr-user-custom-01", "to_node": char,
        "relationship_type": "custom-bond", "description": "user note",
    })
    before_nodes = _row_map(storage, "universe_nodes", "node_id", pid)
    before_rels = _row_map(storage, "universe_relationships", "relationship_id", pid)
    rep = svc.rebuild_universe_graph_from_scenes(pid, _scenes_two())
    after_nodes = _row_map(storage, "universe_nodes", "node_id", pid)
    after_rels = _row_map(storage, "universe_relationships", "relationship_id", pid)
    assert len(after_nodes) == len(before_nodes)
    assert len(after_rels) == len(before_rels)
    assert after_nodes["chr-user-custom-01"] == before_nodes["chr-user-custom-01"]
    assert after_rels["rel-user-custom-02"] == before_rels["rel-user-custom-02"]
    preserved = {p["node_id"]: p["referencing"] for p in rep["preserved_referenced"]}
    assert preserved.get("chr-user-custom-01") == ["universe_relationships"]
