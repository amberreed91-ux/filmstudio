"""
Tests for continuity graph persistence in SQLite storage and ContinuityIntelligenceService.

Covers:
- save_continuity_graph / load_continuity_graph round-trip
- Graph survives a service restart (new service instance reads from storage)
- Version history is preserved correctly
- list_continuity_graph_versions returns versions in created_at order
- get_graph falls back to storage when not in memory
- Building a new graph uses stored graph as parent correctly
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from app.data.storage import DatabaseStorage
from app.models import CinematicMemoryRecord
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


# ── Storage helpers ───────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "test_graph_db"))


# ── 1. save / load round-trip ─────────────────────────────────────────────────

class TestSaveLoadRoundTrip:

    def test_save_and_load_returns_same_graph(self, tmp_path):
        db = _make_db(tmp_path)
        graph = {"nodes": [{"id": "n1", "type": "scene"}], "edges": [], "film_id": "film1"}
        db.save_continuity_graph("film1", graph)
        loaded = db.load_continuity_graph("film1")
        assert loaded is not None
        assert loaded["film_id"] == "film1"
        assert len(loaded["nodes"]) == 1

    def test_load_returns_none_when_no_graph(self, tmp_path):
        db = _make_db(tmp_path)
        result = db.load_continuity_graph("nonexistent_film")
        assert result is None

    def test_save_overwrites_existing_graph(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph("film1", {"version": 1})
        db.save_continuity_graph("film1", {"version": 2})
        loaded = db.load_continuity_graph("film1")
        assert loaded["version"] == 2

    def test_save_returns_true(self, tmp_path):
        db = _make_db(tmp_path)
        result = db.save_continuity_graph("film1", {"nodes": []})
        assert result is True

    def test_graph_with_nested_data_round_trips(self, tmp_path):
        db = _make_db(tmp_path)
        graph = {
            "motifs": [{"motif": "rain", "status": "active", "scene_appearances": ["s1", "s2"]}],
            "issues": [{"issue_id": "i1", "severity": "high"}],
            "advisory": "Test advisory.",
        }
        db.save_continuity_graph("film2", graph)
        loaded = db.load_continuity_graph("film2")
        assert loaded["motifs"][0]["motif"] == "rain"
        assert loaded["issues"][0]["issue_id"] == "i1"

    def test_different_films_are_isolated(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph("film_a", {"name": "A"})
        db.save_continuity_graph("film_b", {"name": "B"})
        assert db.load_continuity_graph("film_a")["name"] == "A"
        assert db.load_continuity_graph("film_b")["name"] == "B"


# ── 2. Graph survives service restart ─────────────────────────────────────────

class TestGraphSurvivesRestart:

    def test_graph_loaded_by_new_service_instance(self, tmp_path):
        """Simulate a restart by creating a second service instance with the same DB."""
        db = _make_db(tmp_path)
        graph = {"nodes": [{"id": "n1"}], "advisory": "Persisted graph."}
        db.save_continuity_graph("film1", graph)

        # New service instance — empty in-memory cache.
        svc2 = ContinuityIntelligenceService(storage=db)
        loaded = svc2.get_graph("film1")
        assert loaded is not None
        assert loaded["advisory"] == "Persisted graph."

    def test_in_memory_cache_empty_after_restart(self, tmp_path):
        """New instance starts with empty _graph_store."""
        db = _make_db(tmp_path)
        db.save_continuity_graph("film1", {"nodes": []})

        svc = ContinuityIntelligenceService(storage=db)
        # Cache is empty before first access.
        assert "film1" not in svc._graph_store

    def test_cache_warmed_after_get_graph(self, tmp_path):
        """After get_graph, the result is cached in memory."""
        db = _make_db(tmp_path)
        db.save_continuity_graph("film1", {"nodes": []})

        svc = ContinuityIntelligenceService(storage=db)
        svc.get_graph("film1")
        assert "film1" in svc._graph_store


# ── 3. Version history ────────────────────────────────────────────────────────

class TestVersionHistory:

    def test_save_version_and_load_version(self, tmp_path):
        db = _make_db(tmp_path)
        graph = {"nodes": [{"id": "n1"}], "version": "v1"}
        db.save_continuity_graph_version("film1", "ver-001", graph)
        loaded = db.load_continuity_graph_version("film1", "ver-001")
        assert loaded is not None
        assert loaded["version"] == "v1"

    def test_load_version_returns_none_for_missing(self, tmp_path):
        db = _make_db(tmp_path)
        result = db.load_continuity_graph_version("film1", "nonexistent-ver")
        assert result is None

    def test_version_is_immutable_insert_or_ignore(self, tmp_path):
        """Second save with same version_id should not overwrite."""
        db = _make_db(tmp_path)
        db.save_continuity_graph_version("film1", "ver-001", {"data": "original"})
        db.save_continuity_graph_version("film1", "ver-001", {"data": "overwrite"})
        loaded = db.load_continuity_graph_version("film1", "ver-001")
        assert loaded["data"] == "original"

    def test_multiple_versions_stored_independently(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph_version("film1", "ver-001", {"seq": 1})
        db.save_continuity_graph_version("film1", "ver-002", {"seq": 2})
        v1 = db.load_continuity_graph_version("film1", "ver-001")
        v2 = db.load_continuity_graph_version("film1", "ver-002")
        assert v1["seq"] == 1
        assert v2["seq"] == 2

    def test_version_film_id_isolation(self, tmp_path):
        """Versions for different films don't cross-contaminate."""
        db = _make_db(tmp_path)
        db.save_continuity_graph_version("film_a", "ver-001", {"film": "a"})
        # Same version_id, different film — load_version checks both film_id and version_id.
        result = db.load_continuity_graph_version("film_b", "ver-001")
        assert result is None


# ── 4. list_continuity_graph_versions order ───────────────────────────────────

class TestListVersionsOrder:

    def test_versions_returned_in_created_at_order(self, tmp_path):
        db = _make_db(tmp_path)
        # Insert with slight delay to ensure distinct created_at values.
        db.save_continuity_graph_version("film1", "ver-001", {"seq": 1})
        time.sleep(0.01)
        db.save_continuity_graph_version("film1", "ver-002", {"seq": 2})
        time.sleep(0.01)
        db.save_continuity_graph_version("film1", "ver-003", {"seq": 3})

        versions = db.list_continuity_graph_versions("film1")
        assert len(versions) == 3
        ids = [v["version_id"] for v in versions]
        assert ids == ["ver-001", "ver-002", "ver-003"]

    def test_list_returns_empty_for_no_versions(self, tmp_path):
        db = _make_db(tmp_path)
        versions = db.list_continuity_graph_versions("film_no_versions")
        assert versions == []

    def test_list_version_metadata_has_required_keys(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph_version("film1", "ver-001", {"nodes": []})
        versions = db.list_continuity_graph_versions("film1")
        assert len(versions) == 1
        v = versions[0]
        assert "version_id" in v
        assert "film_id" in v
        assert "created_at" in v
        # graph_json should NOT be in the list response (lightweight).
        assert "graph_json" not in v

    def test_list_only_returns_versions_for_requested_film(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph_version("film_a", "ver-a1", {})
        db.save_continuity_graph_version("film_b", "ver-b1", {})
        versions_a = db.list_continuity_graph_versions("film_a")
        assert len(versions_a) == 1
        assert versions_a[0]["version_id"] == "ver-a1"


# ── 5. get_graph falls back to storage ────────────────────────────────────────

class TestGetGraphFallback:

    def test_get_graph_returns_none_when_no_storage_and_no_cache(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.get_graph("film1")
        assert result is None

    def test_get_graph_returns_from_memory_cache(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)
        svc._graph_store["film1"] = {"source": "memory"}
        result = svc.get_graph("film1")
        assert result["source"] == "memory"

    def test_get_graph_falls_back_to_storage_when_not_in_cache(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph("film1", {"source": "storage"})
        svc = ContinuityIntelligenceService(storage=db)
        # Cache is empty.
        assert "film1" not in svc._graph_store
        result = svc.get_graph("film1")
        assert result is not None
        assert result["source"] == "storage"

    def test_get_graph_prefers_memory_over_storage(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph("film1", {"source": "storage"})
        svc = ContinuityIntelligenceService(storage=db)
        svc._graph_store["film1"] = {"source": "memory"}
        result = svc.get_graph("film1")
        assert result["source"] == "memory"

    def test_get_graph_returns_none_for_missing_film(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)
        result = svc.get_graph("nonexistent")
        assert result is None


# ── 6. _get_or_build_graph uses stored graph as parent ────────────────────────

class TestGetOrBuildGraph:

    def test_returns_empty_dict_when_no_stored_graph(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)
        parent = svc._get_or_build_graph("new_film")
        assert parent == {}

    def test_returns_stored_graph_when_exists(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_continuity_graph("film1", {"prior_issues": 3, "version": 1})
        svc = ContinuityIntelligenceService(storage=db)
        parent = svc._get_or_build_graph("film1")
        assert parent["prior_issues"] == 3

    def test_analyze_project_continuity_saves_graph(self, tmp_path):
        """After analyze_project_continuity, the graph is persisted to storage."""
        db = _make_db(tmp_path)

        class _MockFrameService:
            def list_analyses_for_project(self, project_id):
                return []

        svc = ContinuityIntelligenceService(
            storage=db,
            frame_analysis_service=_MockFrameService(),
        )
        svc.analyze_project_continuity("film1", overwrite=True)

        # Graph should now be in storage.
        stored = db.load_continuity_graph("film1")
        assert stored is not None
        assert "advisory_only" in stored

    def test_analyze_project_continuity_saves_version(self, tmp_path):
        """After analyze_project_continuity, a version snapshot is saved."""
        db = _make_db(tmp_path)

        class _MockFrameService:
            def list_analyses_for_project(self, project_id):
                return []

        svc = ContinuityIntelligenceService(
            storage=db,
            frame_analysis_service=_MockFrameService(),
        )
        svc.analyze_project_continuity("film1", overwrite=True)

        versions = db.list_continuity_graph_versions("film1")
        assert len(versions) >= 1

    def test_new_service_instance_uses_stored_graph_as_parent(self, tmp_path):
        """
        Simulate restart: first instance builds and saves a graph,
        second instance loads it as parent via _get_or_build_graph.
        """
        db = _make_db(tmp_path)
        prior_graph = {"advisory_only": True, "notes": ["Prior run."], "issues": []}
        db.save_continuity_graph("film1", prior_graph)

        # New instance — empty cache.
        svc2 = ContinuityIntelligenceService(storage=db)
        parent = svc2._get_or_build_graph("film1")
        assert parent["notes"] == ["Prior run."]

    def test_save_graph_updates_both_cache_and_storage(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)
        graph = {"nodes": [], "advisory": "Saved."}
        svc._save_graph("film1", graph)

        # In-memory cache updated.
        assert svc._graph_store["film1"]["advisory"] == "Saved."
        # Storage updated.
        stored = db.load_continuity_graph("film1")
        assert stored["advisory"] == "Saved."

    def test_save_graph_creates_version_entry(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)
        svc._save_graph("film1", {"nodes": []}, version_id="explicit-ver-001")

        versions = db.list_continuity_graph_versions("film1")
        assert any(v["version_id"] == "explicit-ver-001" for v in versions)

    def test_save_graph_without_storage_only_updates_cache(self):
        """When storage is None, _save_graph still updates the in-memory cache."""
        svc = ContinuityIntelligenceService(storage=None)
        svc._save_graph("film1", {"nodes": []})
        assert "film1" in svc._graph_store
