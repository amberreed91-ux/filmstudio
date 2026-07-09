"""
Tests for motif thread analysis in ContinuityIntelligenceService.

Covers:
- Motif nodes are created from scene tags correctly
- ECHOES edges are created between same-value motif nodes
- get_motif_thread_analysis correctly identifies active/resolved/abandoned
- dominant_motif is the most reinforced
- unresolved_motifs are correctly identified
- Endpoint returns honest empty state when no graph exists
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.models import CinematicMemoryRecord
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_memory(
    memory_id: str,
    project_id: str,
    scene_id: str,
    visual_tags: Optional[List[str]] = None,
) -> CinematicMemoryRecord:
    """Build a CinematicMemoryRecord with visual_tags and scene_id in metadata."""
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id=f"asset-{memory_id}",
        keyframe_id=f"kf-{memory_id}",
        memory_type="keyframe_memory",
        visual_tags=visual_tags or [],
        created_at="2026-01-01T00:00:00Z",
        metadata={"scene_id": scene_id},
    )


class _MockStorage:
    def __init__(self, memories: Optional[List[CinematicMemoryRecord]] = None):
        self._memories = memories or []

    def list_cinematic_memory_for_project(self, project_id: str) -> List[CinematicMemoryRecord]:
        return [m for m in self._memories if m.project_id == project_id]

    def list_continuity_issues_for_project(self, project_id: str):
        return []

    def save_continuity_issue(self, issue):
        return issue

    def delete_continuity_issues_for_project(self, project_id: str):
        return 0


def _svc(memories: Optional[List[CinematicMemoryRecord]] = None) -> ContinuityIntelligenceService:
    return ContinuityIntelligenceService(storage=_MockStorage(memories))


def _film(n_scenes: int, tags_per_scene: Optional[List[List[str]]] = None) -> List[CinematicMemoryRecord]:
    """Build n_scenes memory records for 'film1', optionally with per-scene tags."""
    mems = []
    for i in range(n_scenes):
        tags = (tags_per_scene[i] if tags_per_scene else []) or []
        mems.append(_make_memory(f"m{i+1}", "film1", f"scene_{i+1:02d}", visual_tags=tags))
    return mems


# ── 1. Motif nodes extracted from scene tags ──────────────────────────────────

class TestExtractMotifNodes:

    def test_extracts_nodes_from_visual_tags(self):
        mems = _film(3, [["rain", "glass"], ["rain"], ["glass"]])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        motifs = [n["motif"] for n in nodes]
        assert "rain" in motifs
        assert "glass" in motifs

    def test_each_node_has_scene_id(self):
        mems = _film(3, [["rain"], ["rain"], ["rain"]])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        for node in nodes:
            assert node["scene_id"] != ""

    def test_each_node_has_motif_value(self):
        mems = _film(3, [["mirror"], [], []])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        assert any(n["motif"] == "mirror" for n in nodes)

    def test_empty_tags_produce_no_nodes(self):
        mems = _film(3, [[], [], []])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        assert nodes == []

    def test_tags_from_metadata_scene_data(self):
        """Tags stored in metadata["scene_data"]["tags"] are also extracted."""
        mem = CinematicMemoryRecord(
            memory_id="m1",
            project_id="film1",
            asset_id="a1",
            keyframe_id="kf1",
            memory_type="keyframe_memory",
            visual_tags=[],
            created_at="2026-01-01T00:00:00Z",
            metadata={"scene_id": "scene_01", "scene_data": {"tags": ["fog", "silence"]}},
        )
        svc = _svc([mem])
        nodes = svc._extract_motif_nodes_from_memories([mem])
        motifs = [n["motif"] for n in nodes]
        assert "fog" in motifs
        assert "silence" in motifs

    def test_duplicate_tags_in_same_scene_deduplicated(self):
        mems = _film(3, [["rain", "rain"], [], []])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        rain_nodes = [n for n in nodes if n["motif"] == "rain" and n["scene_id"] == "scene_01"]
        assert len(rain_nodes) == 1


# ── 2. ECHOES edges ───────────────────────────────────────────────────────────

class TestEchoesEdges:

    def test_echoes_edge_created_between_same_motif_in_different_scenes(self):
        mems = _film(3, [["rain"], ["rain"], []])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        edges = svc._build_echoes_edges(nodes)
        assert len(edges) >= 1
        assert any(e["motif"] == "rain" for e in edges)

    def test_echoes_edge_type_is_ECHOES(self):
        mems = _film(3, [["mirror"], ["mirror"], []])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        edges = svc._build_echoes_edges(nodes)
        for e in edges:
            assert e["edge_type"] == "ECHOES"

    def test_echoes_edge_from_is_first_occurrence(self):
        mems = _film(4, [["glass"], [], ["glass"], ["glass"]])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        edges = svc._build_echoes_edges(nodes)
        glass_edges = [e for e in edges if e["motif"] == "glass"]
        assert all(e["from_scene_id"] == "scene_01" for e in glass_edges)

    def test_no_echoes_edge_for_single_occurrence(self):
        mems = _film(3, [["unique"], [], []])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        edges = svc._build_echoes_edges(nodes)
        unique_edges = [e for e in edges if e["motif"] == "unique"]
        assert len(unique_edges) == 0

    def test_multiple_echoes_edges_for_motif_in_many_scenes(self):
        mems = _film(4, [["rain"], ["rain"], ["rain"], ["rain"]])
        svc = _svc(mems)
        nodes = svc._extract_motif_nodes_from_memories(mems)
        edges = svc._build_echoes_edges(nodes)
        rain_edges = [e for e in edges if e["motif"] == "rain"]
        # First → second, first → third, first → fourth = 3 edges
        assert len(rain_edges) == 3

    def test_echoes_edges_returned_in_analysis(self):
        mems = _film(4, [["rain"], ["rain"], ["rain"], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert "echoes_edges" in result
        assert isinstance(result["echoes_edges"], list)


# ── 3. Status classification ──────────────────────────────────────────────────

class TestMotifStatusClassification:

    def test_active_motif_appears_in_last_two_scenes(self):
        # 4 scenes, motif in scenes 1 and 4 → active (last 2 = scenes 3,4)
        mems = _film(4, [["rain"], [], [], ["rain"]])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        rain = next((m for m in result["motifs"] if m["motif"] == "rain"), None)
        assert rain is not None
        assert rain["status"] == "active"

    def test_resolved_motif_appears_3plus_times_and_closes_in_final_third(self):
        # 6 scenes, motif in 1,2,3,6 → last seen in scene_06 (final third = 5,6) → resolved
        mems = _film(6, [["fog"], ["fog"], ["fog"], [], [], ["fog"]])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        fog = next((m for m in result["motifs"] if m["motif"] == "fog"), None)
        assert fog is not None
        assert fog["status"] == "resolved"

    def test_abandoned_motif_appears_2plus_times_not_in_final_third(self):
        # 6 scenes, motif in 1,2 only → last seen scene_02, final third = 5,6 → abandoned
        mems = _film(6, [["mirror"], ["mirror"], [], [], [], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        mirror = next((m for m in result["motifs"] if m["motif"] == "mirror"), None)
        assert mirror is not None
        assert mirror["status"] == "abandoned"

    def test_introduced_once_is_active(self):
        # Motif only in scene 1 of 4 → active (just introduced)
        mems = _film(4, [["shadow"], [], [], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        shadow = next((m for m in result["motifs"] if m["motif"] == "shadow"), None)
        assert shadow is not None
        assert shadow["status"] == "active"

    def test_introduced_at_is_first_scene(self):
        mems = _film(4, [[], ["rain"], ["rain"], ["rain"]])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        rain = next((m for m in result["motifs"] if m["motif"] == "rain"), None)
        assert rain is not None
        assert rain["introduced_at"] == "scene_02"

    def test_last_seen_at_is_final_occurrence(self):
        mems = _film(5, [["glass"], ["glass"], [], [], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        glass = next((m for m in result["motifs"] if m["motif"] == "glass"), None)
        assert glass is not None
        assert glass["last_seen_at"] == "scene_02"

    def test_reinforced_at_excludes_introduction(self):
        mems = _film(4, [["rain"], ["rain"], ["rain"], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        rain = next((m for m in result["motifs"] if m["motif"] == "rain"), None)
        assert rain is not None
        assert rain["introduced_at"] not in rain["reinforced_at"]
        assert len(rain["reinforced_at"]) == 2

    def test_thread_read_is_non_empty_string(self):
        mems = _film(4, [["rain"], ["rain"], [], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        for m in result["motifs"]:
            assert isinstance(m["thread_read"], str)
            assert len(m["thread_read"]) > 0


# ── 4. Dominant motif ─────────────────────────────────────────────────────────

class TestDominantMotif:

    def test_dominant_motif_is_most_reinforced(self):
        # rain: scenes 1,2,3,4 → reinforced 3 times
        # fog:  scenes 1,2     → reinforced 1 time
        mems = _film(5, [
            ["rain", "fog"],
            ["rain", "fog"],
            ["rain"],
            ["rain"],
            [],
        ])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert result["dominant_motif"] == "rain"

    def test_dominant_motif_is_none_when_no_motifs(self):
        svc = _svc([])
        result = svc.get_motif_thread_analysis("film1")
        assert result["dominant_motif"] is None

    def test_dominant_motif_present_when_single_motif(self):
        mems = _film(4, [["rain"], ["rain"], ["rain"], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert result["dominant_motif"] == "rain"


# ── 5. Unresolved motifs ──────────────────────────────────────────────────────

class TestUnresolvedMotifs:

    def test_abandoned_motifs_appear_in_unresolved_list(self):
        # 6 scenes: mirror abandoned (scenes 1,2), rain active (scenes 1,5,6)
        mems = _film(6, [
            ["mirror", "rain"],
            ["mirror"],
            [],
            [],
            ["rain"],
            ["rain"],
        ])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert "mirror" in result["unresolved_motifs"]
        assert "rain" not in result["unresolved_motifs"]

    def test_unresolved_motifs_empty_when_all_resolved_or_active(self):
        # 6 scenes: rain active (last 2), fog resolved (3+ times, closes in final third)
        mems = _film(6, [
            ["rain", "fog"],
            ["fog"],
            ["fog"],
            [],
            ["rain"],
            ["rain", "fog"],
        ])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert result["unresolved_motifs"] == []

    def test_unresolved_motifs_is_list(self):
        mems = _film(4, [["rain"], ["rain"], [], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert isinstance(result["unresolved_motifs"], list)


# ── 6. Empty / safe defaults ──────────────────────────────────────────────────

class TestEmptyAndSafeDefaults:

    def test_no_storage_returns_empty_state(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.get_motif_thread_analysis("film1")
        assert result["motifs"] == []
        assert result["dominant_motif"] is None
        assert "visual tags" in result["advisory"].lower() or "motif" in result["advisory"].lower()

    def test_no_memories_returns_empty_state(self):
        svc = _svc([])
        result = svc.get_motif_thread_analysis("film1")
        assert result["motifs"] == []

    def test_fewer_than_3_scenes_returns_empty_state(self):
        mems = _film(2, [["rain"], ["rain"]])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        assert result["motifs"] == []
        assert "3 scenes" in result["advisory"] or "visual tags" in result["advisory"].lower()

    def test_empty_state_advisory_mentions_visual_tags(self):
        svc = _svc([])
        result = svc.get_motif_thread_analysis("film1")
        assert "visual tags" in result["advisory"].lower()

    def test_result_always_has_required_keys(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.get_motif_thread_analysis("film1")
        for key in ("motifs", "unresolved_motifs", "dominant_motif", "advisory", "echoes_edges"):
            assert key in result

    def test_motif_thread_has_all_required_keys(self):
        mems = _film(4, [["rain"], ["rain"], ["rain"], []])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        for m in result["motifs"]:
            for key in ("motif", "introduced_at", "reinforced_at", "last_seen_at",
                        "status", "thread_read", "uncertainty_note"):
                assert key in m, f"Missing key '{key}' in motif thread"

    def test_status_values_are_valid(self):
        mems = _film(6, [
            ["rain", "fog"],
            ["rain"],
            ["fog"],
            [],
            ["rain"],
            ["rain"],
        ])
        svc = _svc(mems)
        result = svc.get_motif_thread_analysis("film1")
        valid = {"active", "resolved", "abandoned"}
        for m in result["motifs"]:
            assert m["status"] in valid


# ── 7. Endpoint integration ───────────────────────────────────────────────────

class TestMotifThreadsEndpoint:

    def test_endpoint_returns_200_for_valid_project(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Motif Test Film"})
        assert created.status_code == 200
        project_id = created.json()["project_id"]

        resp = client.get(f"/api/f51/studio/projects/{project_id}/motif-threads")
        assert resp.status_code == 200

    def test_endpoint_returns_404_for_missing_project(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/f51/studio/projects/nonexistent-proj/motif-threads")
        assert resp.status_code == 404

    def test_endpoint_returns_honest_empty_state_when_no_graph(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Empty Motif Film"})
        project_id = created.json()["project_id"]

        resp = client.get(f"/api/f51/studio/projects/{project_id}/motif-threads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["motifs"] == []
        assert data["dominant_motif"] is None
        assert isinstance(data["advisory"], str)
        assert len(data["advisory"]) > 0

    def test_endpoint_response_has_required_keys(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Keys Test Film"})
        project_id = created.json()["project_id"]

        resp = client.get(f"/api/f51/studio/projects/{project_id}/motif-threads")
        data = resp.json()
        for key in ("motifs", "unresolved_motifs", "dominant_motif", "advisory", "echoes_edges"):
            assert key in data
