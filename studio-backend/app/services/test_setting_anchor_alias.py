"""Setting-anchor alias awareness: gate-narrowing-safe widening, isolated DBs only.

Every test carries the ``node_id`` comm so fixture-fingerprint runs gate on
this family. Isolated doubles only; never touches live data. Read-only:
every test asserting a pass also asserts zero rows modified.

Covers: alias anchor satisfies the provenance gate; table-absent is
identical to today (silent); non-table lookup failure falls back exact-only
with a warning; both _asset_rows paths (SQL-filtered and full-list
fallback); dual old-IDs; cross-project old_id isolation; all negatives;
second synthetic project; fail-at-HEAD exact-only proof.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest

from app.services import reference_validation as rv
from app.services.stability import ValidationError


LIVE_A = "loc-061ebeb1"
OLD_A = "loc-b543d669"
LIVE_B = "loc-22222222"


def _live_node(node_id, project_id, *, name="Harbor Chapel", scene="scene_001"):
    return {
        "node_id": node_id, "project_id": project_id, "node_type": "location",
        "name": name, "first_scene": scene, "last_scene": scene,
    }


def _anchor(ref_id, project_id, target_id, *, canonical=True, approval_state="approved",
            kind="environment", image_url=None):
    return {
        "ref_id": ref_id, "project_id": project_id, "target_type": "setting",
        "target_id": target_id, "kind": kind, "image_url": image_url or f"https://cdn.example/{ref_id}.png",
        "canonical": canonical, "approval_state": approval_state,
    }


def _alias(old_id, current_id, project_id):
    return {"old_node_id": old_id, "current_node_id": current_id, "project_id": project_id}


class AliasStorage:
    """Filtered path: accepts target_type/target_id kwargs (SQL-filtered)."""

    def __init__(self, *, nodes, aliases, assets, alias_error=None):
        self._nodes = list(nodes)
        self._aliases = list(aliases)
        self._assets = list(assets)
        self._alias_error = alias_error

    def get_universe_nodes(self, project_id):
        return [dict(r) for r in self._nodes if r.get("project_id") == project_id]

    def get_universe_id_alias(self, old_node_id):
        for a in self._aliases:
            if a.get("old_node_id") == old_node_id:
                return dict(a)
        return None

    def list_universe_id_aliases(self, project_id):
        if self._alias_error is not None:
            raise self._alias_error
        return [dict(a) for a in self._aliases if a.get("project_id") == project_id]

    def list_reference_assets(self, project_id, limit=50, target_type=None, target_id=None, **_kw):
        rows = [dict(r) for r in self._assets if r.get("project_id") == project_id]
        if target_type:
            rows = [r for r in rows if r.get("target_type") == target_type]
        if target_id:
            rows = [r for r in rows if r.get("target_id") == target_id]
        return rows[:limit]


class FallbackAliasStorage(AliasStorage):
    """Full-list fallback path: rejects target_* kwargs with TypeError."""

    def list_reference_assets(self, project_id, limit=50, **kwargs):
        if "target_type" in kwargs or "target_id" in kwargs:
            raise TypeError("storage without filtered listing")
        return [dict(r) for r in self._assets if r.get("project_id") == project_id][:limit]


class NoAliasTableStorage:
    """Predates aliasing: no alias methods at all (missing-table equivalent)."""

    def __init__(self, *, nodes, assets):
        self._nodes = list(nodes)
        self._assets = list(assets)

    def get_universe_nodes(self, project_id):
        return [dict(r) for r in self._nodes if r.get("project_id") == project_id]

    def list_reference_assets(self, project_id, limit=50, target_type=None, target_id=None, **_kw):
        rows = [dict(r) for r in self._assets if r.get("project_id") == project_id]
        if target_type:
            rows = [row for row in rows if row.get("target_type") == target_type]
        if target_id:
            rows = [row for row in rows if row.get("target_id") == target_id]
        return rows[:limit]


def _snapshot(storage):
    nodes = getattr(storage, "_nodes", None)
    assets = getattr(storage, "_assets", None)
    aliases = getattr(storage, "_aliases", None)
    return (repr(nodes), repr(assets), repr(aliases))


def _storage_variants(*, nodes, aliases, assets, alias_error=None):
    return [
        AliasStorage(nodes=nodes, aliases=aliases, assets=assets, alias_error=alias_error),
        FallbackAliasStorage(nodes=nodes, aliases=aliases, assets=assets, alias_error=alias_error),
    ]


def test_node_id_alias_anchor_satisfies_provenance_gate():
    pid = "proj-alias-a"
    nodes = [_live_node(LIVE_A, pid)]
    aliases = [_alias(OLD_A, LIVE_A, pid)]
    assets = [_anchor("ref_upl_752d", pid, OLD_A)]
    for storage in _storage_variants(nodes=nodes, aliases=aliases, assets=assets):
        before = _snapshot(storage)
        entity = rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
        assert entity["id"] == LIVE_A
        refs = rv._approved_setting_references(storage, project_id=pid, setting_id=LIVE_A)
        assert [r["ref_id"] for r in refs] == ["ref_upl_752d"]
        assert refs[0]["target_id"] == LIVE_A
        assert _snapshot(storage) == before


def test_node_id_alias_table_absent_is_exact_only_silent(caplog):
    pid = "proj-alias-a"
    nodes = [_live_node(LIVE_A, pid)]
    assets = [_anchor("ref_upl_752d", pid, OLD_A)]
    storage = NoAliasTableStorage(nodes=nodes, assets=assets)
    with caplog.at_level(logging.WARNING, logger="studio-setting-anchor"):
        with pytest.raises(ValidationError) as exc:
            rv._verify_setting_identity_provenance(
                storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
    assert "canonical_setting_reference_missing" in str(getattr(exc.value, "metadata", {}))
    assert [r for r in caplog.records if r.name == "studio-setting-anchor"] == []
    # Exact anchor still passes without a table.
    storage_exact = NoAliasTableStorage(nodes=nodes, assets=[_anchor("ref_exact", pid, LIVE_A)])
    entity = rv._verify_setting_identity_provenance(
        storage=storage_exact, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
    assert entity["id"] == LIVE_A


def test_node_id_alias_operational_error_absent_is_silent(caplog):
    pid = "proj-alias-a"
    nodes = [_live_node(LIVE_A, pid)]
    aliases = [_alias(OLD_A, LIVE_A, pid)]
    assets = [_anchor("ref_upl_752d", pid, OLD_A)]
    storage = AliasStorage(
        nodes=nodes, aliases=aliases, assets=assets,
        alias_error=sqlite3.OperationalError("no such table: universe_id_aliases"))
    with caplog.at_level(logging.WARNING, logger="studio-setting-anchor"):
        with pytest.raises(ValidationError):
            rv._verify_setting_identity_provenance(
                storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
    assert [r for r in caplog.records if r.name == "studio-setting-anchor"] == []


def test_node_id_alias_lookup_failure_falls_back_exact_only_and_warns(caplog):
    pid = "proj-alias-a"
    nodes = [_live_node(LIVE_A, pid)]
    aliases = [_alias(OLD_A, LIVE_A, pid)]
    assets = [_anchor("ref_upl_752d", pid, OLD_A), _anchor("ref_exact", pid, LIVE_A)]
    storage = AliasStorage(nodes=nodes, aliases=aliases, assets=assets,
                            alias_error=RuntimeError("alias boom"))
    with caplog.at_level(logging.WARNING, logger="studio-setting-anchor"):
        entity = rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
    assert entity["id"] == LIVE_A
    assert any(r.name == "studio-setting-anchor" and r.levelno == logging.WARNING
               for r in caplog.records)
    refs = rv._approved_setting_references(storage, project_id=pid, setting_id=LIVE_A)
    assert [r["ref_id"] for r in refs] == ["ref_exact"]


def test_node_id_alias_both_asset_rows_paths_widen():
    pid = "proj-alias-a"
    nodes = [_live_node(LIVE_A, pid)]
    aliases = [_alias(OLD_A, LIVE_A, pid)]
    assets = [_anchor("ref_upl_752d", pid, OLD_A)]
    for storage in _storage_variants(nodes=nodes, aliases=aliases, assets=assets):
        assert rv._setting_anchor_target_ids(
            storage, project_id=pid, setting_id=LIVE_A) == {LIVE_A, OLD_A}
        rows = rv._setting_anchor_rows(storage, project_id=pid, setting_id=LIVE_A)
        assert [r["ref_id"] for r in rows] == ["ref_upl_752d"]


def test_node_id_alias_two_old_ids_both_widen():
    pid = "proj-alias-a"
    old2 = "loc-aaaa1111"
    nodes = [_live_node(LIVE_A, pid)]
    aliases = [_alias(OLD_A, LIVE_A, pid), _alias(old2, LIVE_A, pid)]
    assets = [_anchor("ref_one", pid, OLD_A), _anchor("ref_two", pid, old2)]
    for storage in _storage_variants(nodes=nodes, aliases=aliases, assets=assets):
        assert rv._setting_anchor_target_ids(
            storage, project_id=pid, setting_id=LIVE_A) == {LIVE_A, OLD_A, old2}
        entity = rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
        assert entity["id"] == LIVE_A
        refs = rv._approved_setting_references(storage, project_id=pid, setting_id=LIVE_A)
        assert sorted(r["ref_id"] for r in refs) == ["ref_one", "ref_two"]


def test_node_id_alias_same_old_id_other_project_never_widens():
    pid_a, pid_b = "proj-alias-a", "proj-alias-b"
    nodes = [_live_node(LIVE_A, pid_a), _live_node(LIVE_B, pid_b, name="Other Room")]
    aliases = [_alias(OLD_A, LIVE_A, pid_a)]
    assets = [_anchor("ref_b", pid_b, OLD_A), _anchor("ref_a", pid_a, OLD_A)]
    storage = AliasStorage(nodes=nodes, aliases=aliases, assets=assets)
    with pytest.raises(ValidationError) as exc:
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid_b, scene_id="scene_001", setting_id=LIVE_B)
    assert "canonical_setting_reference_missing" in str(getattr(exc.value, "metadata", {}))
    assert rv._approved_setting_references(storage, project_id=pid_b, setting_id=LIVE_B) == []
    # Owning project still widens.
    entity = rv._verify_setting_identity_provenance(
        storage=storage, project_id=pid_a, scene_id="scene_001", setting_id=LIVE_A)
    assert entity["id"] == LIVE_A


def test_node_id_alias_unapproved_anchor_still_fails():
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)], aliases=[_alias(OLD_A, LIVE_A, pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A, approval_state="candidate")])
    with pytest.raises(ValidationError) as exc:
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)
    assert "canonical_setting_reference_missing" in str(getattr(exc.value, "metadata", {}))


def test_node_id_alias_rejected_anchor_still_fails():
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)], aliases=[_alias(OLD_A, LIVE_A, pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A, approval_state="rejected")])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)


def test_node_id_alias_noncanonical_anchor_still_fails():
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)], aliases=[_alias(OLD_A, LIVE_A, pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A, canonical=False)])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)


def test_node_id_alias_non_environment_anchor_still_fails():
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)], aliases=[_alias(OLD_A, LIVE_A, pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A, kind="character_face")])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)


def test_node_id_alias_wrong_project_anchor_still_fails():
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)], aliases=[_alias(OLD_A, LIVE_A, pid)],
        assets=[_anchor("ref_other", "proj-other", OLD_A)])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)


def test_node_id_alias_ambiguous_alias_still_fails():
    pid = "proj-alias-a"
    dupe_name = "Harbor Chapel"
    nodes = [_live_node("loc-aaa11111", pid, name=dupe_name),
             _live_node("loc-bbb22222", pid, name=dupe_name)]
    storage = AliasStorage(nodes=nodes, aliases=[],
                            assets=[_anchor("ref_upl_752d", pid, OLD_A)])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id="loc-aaa11111")


def test_node_id_alias_stale_alias_still_fails():
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)],
        aliases=[_alias(OLD_A, "loc-deadbeef", pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A)])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)


def test_node_id_alias_cross_entity_alias_still_fails():
    pid = "proj-alias-a"
    other = "loc-other999"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid), _live_node(other, pid, name="Other Room")],
        aliases=[_alias(OLD_A, other, pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A)])
    with pytest.raises(ValidationError):
        rv._verify_setting_identity_provenance(
            storage=storage, project_id=pid, scene_id="scene_001", setting_id=LIVE_A)


def test_node_id_second_project_identical_shape_passes():
    pid = "proj-alias-b"
    live = "loc-bbbb1111"
    old = "loc-cccc2222"
    storage = AliasStorage(
        nodes=[_live_node(live, pid)], aliases=[_alias(old, live, pid)],
        assets=[_anchor("ref_b1", pid, old)])
    before = _snapshot(storage)
    entity = rv._verify_setting_identity_provenance(
        storage=storage, project_id=pid, scene_id="scene_001", setting_id=live)
    assert entity["id"] == live
    assert [r["ref_id"] for r in rv._approved_setting_references(
        storage, project_id=pid, setting_id=live)] == ["ref_b1"]
    assert _snapshot(storage) == before


def test_node_id_head_exact_only_would_fail_for_alias_anchor():
    """Fail-at-HEAD proof: exact-only lookup excludes the alias anchor."""
    pid = "proj-alias-a"
    storage = AliasStorage(
        nodes=[_live_node(LIVE_A, pid)], aliases=[_alias(OLD_A, LIVE_A, pid)],
        assets=[_anchor("ref_upl_752d", pid, OLD_A)])
    head_rows = rv._asset_rows(storage, project_id=pid, target_type="setting", target_id=LIVE_A)
    assert head_rows == []
    assert rv._setting_anchor_rows(storage, project_id=pid, setting_id=LIVE_A)[0]["ref_id"] == "ref_upl_752d"
