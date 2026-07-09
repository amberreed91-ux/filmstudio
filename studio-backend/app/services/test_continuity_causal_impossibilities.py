"""
Tests for check_causal_impossibilities in ContinuityIntelligenceService.

Covers:
- Returns empty list when no conflicts exist
- Correctly flags character presence contradiction (high severity)
- Correctly flags location contradiction (high severity)
- Severity assigned correctly based on confidence
- Returns safe defaults when no graph exists
- Never uses alarming language ("error", "impossible")
- Always includes uncertainty_notes
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
    causal_events: Optional[List[str]] = None,
    causal_consequences: Optional[List[str]] = None,
) -> CinematicMemoryRecord:
    meta: Dict[str, Any] = {"scene_id": scene_id}
    if causal_events:
        meta["causal_events"] = causal_events
    if causal_consequences:
        meta["causal_consequences"] = causal_consequences
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id=f"asset-{memory_id}",
        keyframe_id=f"kf-{memory_id}",
        memory_type="keyframe_memory",
        created_at="2026-01-01T00:00:00Z",
        metadata=meta,
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


# ── 1. No conflicts when scene is clean ───────────────────────────────────────

class TestNoConflicts:

    def test_returns_empty_impossibilities_when_no_prior_events(self):
        svc = _svc([])
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Alice"]},
            film_id="film1",
        )
        assert result["impossibilities"] == []

    def test_returns_empty_when_no_contradiction(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        # Alice is present — no conflict with Marcus departing
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Alice"]},
            film_id="film1",
        )
        assert result["impossibilities"] == []

    def test_advisory_is_clean_when_no_conflicts(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["door locked"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"location": "office"},
            film_id="film1",
        )
        assert "conflict" not in result["advisory"].lower() or "no causal" in result["advisory"].lower()

    def test_no_conflict_when_different_character(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Elena"]},
            film_id="film1",
        )
        assert result["impossibilities"] == []

    def test_no_conflict_for_current_scene_events(self):
        """Events established IN the current scene should not flag against themselves."""
        memories = [
            _make_memory("m1", "film1", "scene_02", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        # scene_02 events are not "prior" — no flag
        assert result["impossibilities"] == []


# ── 2. Character presence contradiction ──────────────────────────────────────

class TestCharacterPresenceContradiction:

    def test_flags_departed_character_as_present(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        assert len(result["impossibilities"]) >= 1
        flag = result["impossibilities"][0]
        assert "marcus" in flag["description"].lower()
        assert flag["conflicting_event"] == "Marcus departed"
        assert flag["established_at"] == "scene_01"

    def test_flags_deceased_character_as_present(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Elena died"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Elena"]},
            film_id="film1",
        )
        assert len(result["impossibilities"]) >= 1
        flag = result["impossibilities"][0]
        assert "elena" in flag["description"].lower()

    def test_character_contradiction_is_high_severity(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        high_flags = [i for i in result["impossibilities"] if i["severity"] == "high"]
        assert len(high_flags) >= 1

    def test_character_contradiction_established_at_is_correct(self):
        memories = [
            _make_memory("m1", "film1", "scene_03", causal_events=["Bob fled"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_05",
            scene_data={"characters_present": ["Bob"]},
            film_id="film1",
        )
        if result["impossibilities"]:
            assert result["impossibilities"][0]["established_at"] == "scene_03"

    def test_camelcase_characters_present_detected(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"charactersPresent": ["Marcus"]},
            film_id="film1",
        )
        assert len(result["impossibilities"]) >= 1


# ── 3. Location contradiction ─────────────────────────────────────────────────

class TestLocationContradiction:

    def test_flags_destroyed_location(self):
        memories = [
            _make_memory("m1", "film1", "scene_01",
                         causal_events=["warehouse destroyed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"location": "warehouse"},
            film_id="film1",
        )
        assert len(result["impossibilities"]) >= 1
        flag = result["impossibilities"][0]
        assert "warehouse" in flag["description"].lower()
        assert flag["established_at"] == "scene_01"

    def test_location_contradiction_is_high_severity(self):
        memories = [
            _make_memory("m1", "film1", "scene_01",
                         causal_events=["warehouse destroyed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"location": "warehouse"},
            film_id="film1",
        )
        high_flags = [i for i in result["impossibilities"] if i["severity"] == "high"]
        assert len(high_flags) >= 1

    def test_flags_unavailable_location(self):
        memories = [
            _make_memory("m1", "film1", "scene_01",
                         causal_events=["vault sealed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"location": "vault"},
            film_id="film1",
        )
        assert len(result["impossibilities"]) >= 1

    def test_no_location_flag_for_different_location(self):
        memories = [
            _make_memory("m1", "film1", "scene_01",
                         causal_events=["warehouse destroyed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"location": "office"},
            film_id="film1",
        )
        location_flags = [
            i for i in result["impossibilities"]
            if "office" in i["description"].lower()
        ]
        assert len(location_flags) == 0


# ── 4. Severity assignment ────────────────────────────────────────────────────

class TestSeverityAssignment:

    def test_explicit_field_contradiction_is_high(self):
        """Character listed in characters_present after being established as departed → high."""
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Alice departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Alice"]},
            film_id="film1",
        )
        severities = {i["severity"] for i in result["impossibilities"]}
        assert "high" in severities

    def test_severity_values_are_valid(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        valid = {"low", "medium", "high"}
        for imp in result["impossibilities"]:
            assert imp["severity"] in valid, f"Invalid severity: {imp['severity']}"

    def test_severity_never_critical(self):
        """Severity must never be 'critical' — avoid alarming language."""
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        for imp in result["impossibilities"]:
            assert imp["severity"] != "critical"


# ── 5. Safe defaults when no graph exists ─────────────────────────────────────

class TestSafeDefaults:

    def test_no_storage_returns_safe_default(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.check_causal_impossibilities(
            scene_id="scene_01",
            scene_data={"characters_present": ["Alice"]},
            film_id="film_x",
        )
        assert result["impossibilities"] == []
        assert isinstance(result["advisory"], str)
        assert isinstance(result["uncertainty_notes"], list)

    def test_empty_memories_returns_safe_default(self):
        svc = _svc([])
        result = svc.check_causal_impossibilities(
            scene_id="scene_01",
            scene_data={"characters_present": ["Alice"]},
            film_id="film_x",
        )
        assert result["impossibilities"] == []

    def test_empty_film_id_returns_safe_default(self):
        svc = _svc([_make_memory("m1", "film1", "scene_01", causal_events=["Alice departed"])])
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Alice"]},
            film_id="",
        )
        assert result["impossibilities"] == []

    def test_result_always_has_required_keys(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.check_causal_impossibilities("s1", {}, "f1")
        assert "impossibilities" in result
        assert "advisory" in result
        assert "uncertainty_notes" in result

    def test_impossibility_always_has_required_keys(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        for imp in result["impossibilities"]:
            assert "description" in imp
            assert "conflicting_event" in imp
            assert "established_at" in imp
            assert "severity" in imp


# ── 6. Language guardrails ────────────────────────────────────────────────────

class TestLanguageGuardrails:

    def test_description_never_uses_word_error(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        for imp in result["impossibilities"]:
            assert "error" not in imp["description"].lower()

    def test_description_never_uses_word_impossible(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        for imp in result["impossibilities"]:
            assert "impossible" not in imp["description"].lower()

    def test_advisory_never_uses_word_error(self):
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        assert "error" not in result["advisory"].lower()

    def test_uncertainty_notes_present_for_low_medium(self):
        """Low/medium severity findings must include uncertainty_notes."""
        memories = [
            # Weak signal: event mentions destruction but location match is indirect
            _make_memory("m1", "film1", "scene_01",
                         causal_events=["the old warehouse was destroyed"],
                         causal_consequences=["warehouse key lost"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={
                "description": "They meet near the warehouse key storage area.",
                "location": "storage",
            },
            film_id="film1",
        )
        # The general hedge is always added
        assert len(result["uncertainty_notes"]) >= 1

    def test_always_includes_general_uncertainty_note(self):
        """A general hedge about string matching must always be present."""
        memories = [
            _make_memory("m1", "film1", "scene_01", causal_events=["Marcus departed"]),
        ]
        svc = _svc(memories)
        result = svc.check_causal_impossibilities(
            scene_id="scene_02",
            scene_data={"characters_present": ["Marcus"]},
            film_id="film1",
        )
        assert any("string matching" in n.lower() or "advisory" in n.lower()
                   for n in result["uncertainty_notes"])


# ── 7. Route integration — causal_check attached to TransitionRead ────────────

class TestRouteIntegration:
    """Verify the route attaches causal_check to each TransitionRead."""

    def test_transition_read_has_causal_check_field(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Causal Test Film"})
        assert created.status_code == 200
        project_id = created.json()["project_id"]

        payload = {
            "scenes": [
                {"scene_id": "s1", "emotional_target": "tense", "location": "office"},
                {"scene_id": "s2", "emotional_target": "calm", "location": "park"},
            ],
            "mode": "passive",
            "strictness": "medium",
        }
        resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scene-continuity-intelligence",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "transition_reads" in data
        for tr in data["transition_reads"]:
            # causal_check key must be present (may be null if no graph)
            assert "causal_check" in tr

    def test_causal_check_has_required_keys_when_present(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Causal Keys Test"})
        project_id = created.json()["project_id"]

        payload = {
            "scenes": [
                {"scene_id": "s1", "location": "lab"},
                {"scene_id": "s2", "location": "lab"},
            ],
            "mode": "passive",
            "strictness": "low",
        }
        resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scene-continuity-intelligence",
            json=payload,
        )
        assert resp.status_code == 200
        for tr in resp.json()["transition_reads"]:
            cc = tr.get("causal_check")
            if cc is not None:
                assert "impossibilities" in cc
                assert "advisory" in cc
                assert "uncertainty_notes" in cc
