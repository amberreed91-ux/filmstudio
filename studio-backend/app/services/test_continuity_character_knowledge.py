"""
Tests for character knowledge tracking in ContinuityIntelligenceService.

Covers:
- Character knowledge nodes are created for each character in a scene
- get_character_knowledge_at_scene returns correct known events
- get_character_knowledge_at_scene identifies knowledge gaps correctly
- check_reveal_timing correctly flags premature reveals
- check_reveal_timing returns is_premature=False when timing is valid
- All methods return safe defaults when no graph exists
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

import pytest

from app.models import CinematicMemoryRecord
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_memory(
    memory_id: str,
    asset_id: str,
    project_id: str,
    scene_id: str = "",
    characters: Optional[List[str]] = None,
    emotional_tags: Optional[List[str]] = None,
    causal_events: Optional[List[str]] = None,
    visual_tags: Optional[List[str]] = None,
) -> CinematicMemoryRecord:
    """Build a CinematicMemoryRecord with scene metadata embedded in metadata dict."""
    meta: Dict[str, Any] = {}
    if scene_id:
        meta["scene_id"] = scene_id
    if causal_events:
        meta["causal_events"] = causal_events
    if characters:
        meta["scene_data"] = {"characters_present": characters}
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id=asset_id,
        keyframe_id=f"kf-{memory_id}",
        memory_type="keyframe_memory",
        visual_tags=visual_tags or [],
        emotional_tags=emotional_tags or [],
        created_at="2026-01-01T00:00:00Z",
        metadata=meta,
    )


class _MockStorage:
    """Minimal mock storage that holds cinematic memory records."""

    def __init__(self, memories: Optional[List[CinematicMemoryRecord]] = None):
        self._memories: List[CinematicMemoryRecord] = memories or []

    def list_cinematic_memory_for_project(self, project_id: str) -> List[CinematicMemoryRecord]:
        return [m for m in self._memories if m.project_id == project_id]

    # Stubs required by analyze_project_continuity
    def list_continuity_issues_for_project(self, project_id: str):
        return []

    def save_continuity_issue(self, issue):
        return issue

    def delete_continuity_issues_for_project(self, project_id: str):
        return 0


def _make_service(memories: Optional[List[CinematicMemoryRecord]] = None) -> ContinuityIntelligenceService:
    return ContinuityIntelligenceService(storage=_MockStorage(memories))


# ── 1. Character knowledge nodes created for each character in a scene ────────

class TestExtractCharacterKnowledgeNodes:

    def test_creates_one_node_per_character(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice", "Bob"]},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=["event_a"],
        )
        assert len(nodes) == 2
        subjects = {n["subject"] for n in nodes}
        assert subjects == {"Alice", "Bob"}

    def test_node_type_is_character_knowledge_state(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice"]},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=[],
        )
        assert nodes[0]["node_type"] == "character_knowledge_state"

    def test_predicate_is_knows(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice"]},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=[],
        )
        assert nodes[0]["predicate"] == "knows"

    def test_value_contains_required_keys(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice"], "emotional_tone": "tense"},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=["event_a", "event_b"],
        )
        val = nodes[0]["value"]
        assert val["present_in_scene"] is True
        assert val["emotional_state"] == "tense"
        assert set(val["knowledge_events"]) == {"event_a", "event_b"}

    def test_confidence_is_always_inferred(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice"]},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=[],
        )
        assert nodes[0]["confidence"] == "inferred"

    def test_uncertainty_note_is_present(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice"]},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=[],
        )
        assert "uncertainty_note" in nodes[0]
        assert len(nodes[0]["uncertainty_note"]) > 0

    def test_accepts_camelcase_characters_present(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"charactersPresent": ["Charlie"]},
            scene_id="scene_02",
            film_id="film_x",
            active_causal_events=[],
        )
        assert len(nodes) == 1
        assert nodes[0]["subject"] == "Charlie"

    def test_accepts_emotionalTone_camelcase(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Dana"], "emotionalTone": "grief"},
            scene_id="scene_03",
            film_id="film_x",
            active_causal_events=[],
        )
        assert nodes[0]["value"]["emotional_state"] == "grief"

    def test_empty_characters_returns_empty_list(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": []},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=["event_a"],
        )
        assert nodes == []

    def test_no_characters_key_returns_empty_list(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"emotional_tone": "calm"},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=[],
        )
        assert nodes == []

    def test_film_id_and_scene_id_stored_on_node(self):
        svc = _make_service()
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Eve"]},
            scene_id="scene_05",
            film_id="film_abc",
            active_causal_events=[],
        )
        assert nodes[0]["film_id"] == "film_abc"
        assert nodes[0]["scene_id"] == "scene_05"


# ── 2. get_character_knowledge_at_scene — correct known events ────────────────

class TestGetCharacterKnowledgeAtScene:

    def _build_memories(self) -> List[CinematicMemoryRecord]:
        """
        Film timeline:
          scene_01 — Alice present, causal_event: "father_dies"
          scene_02 — Bob present (not Alice), causal_event: "will_revealed"
          scene_03 — Alice present, causal_event: "will_revealed" (Alice now learns it)
        """
        return [
            _make_memory(
                "mem1", "asset1", "film1",
                scene_id="scene_01",
                characters=["Alice"],
                emotional_tags=["grief"],
                causal_events=["father_dies"],
            ),
            _make_memory(
                "mem2", "asset2", "film1",
                scene_id="scene_02",
                characters=["Bob"],
                emotional_tags=["shock"],
                causal_events=["will_revealed"],
            ),
            _make_memory(
                "mem3", "asset3", "film1",
                scene_id="scene_03",
                characters=["Alice"],
                emotional_tags=["anger"],
                causal_events=["will_revealed"],
            ),
        ]

    def test_alice_knows_father_dies_after_scene_01(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_01", "film1")
        assert "father_dies" in result["knows"]

    def test_alice_does_not_know_will_revealed_after_scene_01(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_01", "film1")
        assert "will_revealed" not in result["knows"]

    def test_alice_knows_will_revealed_after_scene_03(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_03", "film1")
        assert "will_revealed" in result["knows"]

    def test_first_appeared_is_scene_01_for_alice(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_03", "film1")
        assert result["first_appeared"] == "scene_01"

    def test_scenes_present_lists_alice_scenes(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_03", "film1")
        assert "scene_01" in result["scenes_present"]
        assert "scene_03" in result["scenes_present"]
        assert "scene_02" not in result["scenes_present"]

    def test_emotional_state_reflects_last_seen_scene(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_03", "film1")
        assert result["emotional_state"] == "anger"

    def test_result_contains_uncertainty_note(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_01", "film1")
        assert "uncertainty_note" in result
        assert len(result["uncertainty_note"]) > 0

    def test_character_not_in_film_returns_empty_knows(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Zara", "scene_03", "film1")
        assert result["knows"] == []
        assert result["scenes_present"] == []


# ── 3. get_character_knowledge_at_scene — knowledge gaps ─────────────────────

class TestKnowledgeGaps:

    def _build_memories(self) -> List[CinematicMemoryRecord]:
        """
        scene_01 — Alice present, event: "secret_letter"
        scene_02 — Bob present, event: "hidden_room"   (Alice not present)
        """
        return [
            _make_memory(
                "mem1", "asset1", "film2",
                scene_id="scene_01",
                characters=["Alice"],
                causal_events=["secret_letter"],
            ),
            _make_memory(
                "mem2", "asset2", "film2",
                scene_id="scene_02",
                characters=["Bob"],
                causal_events=["hidden_room"],
            ),
        ]

    def test_alice_has_hidden_room_as_gap_after_scene_01(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_01", "film2")
        assert "hidden_room" in result["knowledge_gaps"]

    def test_alice_does_not_have_secret_letter_as_gap(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Alice", "scene_01", "film2")
        assert "secret_letter" not in result["knowledge_gaps"]

    def test_bob_has_secret_letter_as_gap_after_scene_02(self):
        svc = _make_service(self._build_memories())
        result = svc.get_character_knowledge_at_scene("Bob", "scene_02", "film2")
        assert "secret_letter" in result["knowledge_gaps"]


# ── 4. check_reveal_timing — premature reveals ────────────────────────────────

class TestCheckRevealTimingPremature:

    def _build_memories(self) -> List[CinematicMemoryRecord]:
        """
        scene_01 — Bob present, event: "murder_weapon_found"
        scene_02 — Alice present (Bob not present), event: "murder_weapon_found" still active
        scene_03 — Alice is confronted about the weapon (reveal scene)
                   Alice was never present when the event was established.
        """
        return [
            _make_memory(
                "mem1", "asset1", "film3",
                scene_id="scene_01",
                characters=["Bob"],
                causal_events=["murder_weapon_found"],
            ),
            _make_memory(
                "mem2", "asset2", "film3",
                scene_id="scene_02",
                characters=["Alice"],
                causal_events=["murder_weapon_found"],
            ),
        ]

    def test_reveal_is_premature_when_character_never_witnessed_event(self):
        """
        Alice was present in scene_02 where the event was active — so she DID witness it.
        Let's build a scenario where she was NOT present.
        """
        memories = [
            _make_memory(
                "mem1", "asset1", "film3b",
                scene_id="scene_01",
                characters=["Bob"],
                causal_events=["murder_weapon_found"],
            ),
            # scene_02: Alice is NOT present, event still active
            _make_memory(
                "mem2", "asset2", "film3b",
                scene_id="scene_02",
                characters=["Bob"],
                causal_events=["murder_weapon_found"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="murder_weapon_found",
            reveal_scene_id="scene_02",
            film_id="film3b",
        )
        assert result["is_premature"] is True
        assert "Alice" in result["reason"]
        assert result["established_at"] == "scene_01"

    def test_reason_is_natural_language_string(self):
        memories = [
            _make_memory(
                "mem1", "asset1", "film3c",
                scene_id="scene_01",
                characters=["Bob"],
                causal_events=["secret_code"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="secret_code",
            reveal_scene_id="scene_01",
            film_id="film3c",
        )
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    def test_established_at_is_scene_where_event_first_appeared(self):
        memories = [
            _make_memory(
                "mem1", "asset1", "film3d",
                scene_id="scene_01",
                characters=["Bob"],
                causal_events=["the_truth"],
            ),
            _make_memory(
                "mem2", "asset2", "film3d",
                scene_id="scene_02",
                characters=["Bob"],
                causal_events=["the_truth"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="the_truth",
            reveal_scene_id="scene_02",
            film_id="film3d",
        )
        assert result["is_premature"] is True
        assert result["established_at"] == "scene_01"


# ── 5. check_reveal_timing — valid timing ─────────────────────────────────────

class TestCheckRevealTimingValid:

    def test_not_premature_when_character_was_present(self):
        """
        Alice was present in scene_01 when the event was established.
        Reveal in scene_02 is valid.
        """
        memories = [
            _make_memory(
                "mem1", "asset1", "film4",
                scene_id="scene_01",
                characters=["Alice", "Bob"],
                causal_events=["the_confession"],
            ),
            _make_memory(
                "mem2", "asset2", "film4",
                scene_id="scene_02",
                characters=["Alice"],
                causal_events=["the_confession"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="the_confession",
            reveal_scene_id="scene_02",
            film_id="film4",
        )
        assert result["is_premature"] is False

    def test_established_at_is_populated_when_valid(self):
        memories = [
            _make_memory(
                "mem1", "asset1", "film4b",
                scene_id="scene_01",
                characters=["Alice"],
                causal_events=["the_letter"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="the_letter",
            reveal_scene_id="scene_01",
            film_id="film4b",
        )
        assert result["is_premature"] is False
        assert result["established_at"] != ""

    def test_reason_is_non_empty_when_valid(self):
        memories = [
            _make_memory(
                "mem1", "asset1", "film4c",
                scene_id="scene_01",
                characters=["Alice"],
                causal_events=["the_key"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="the_key",
            reveal_scene_id="scene_01",
            film_id="film4c",
        )
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0


# ── 6. Safe defaults when no graph exists ─────────────────────────────────────

class TestSafeDefaultsNoGraph:

    def test_get_character_knowledge_no_storage(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.get_character_knowledge_at_scene("Alice", "scene_01", "film_x")
        assert result["character"] == "Alice"
        assert result["as_of_scene"] == "scene_01"
        assert result["knows"] == []
        assert result["scenes_present"] == []
        assert result["knowledge_gaps"] == []
        assert "uncertainty_note" in result

    def test_get_character_knowledge_empty_memories(self):
        svc = _make_service([])
        result = svc.get_character_knowledge_at_scene("Bob", "scene_01", "film_x")
        assert result["knows"] == []
        assert result["scenes_present"] == []
        assert result["knowledge_gaps"] == []

    def test_check_reveal_timing_no_storage(self):
        svc = ContinuityIntelligenceService(storage=None)
        result = svc.check_reveal_timing("Alice", "some_event", "scene_01", "film_x")
        assert result["is_premature"] is False
        assert isinstance(result["reason"], str)
        assert result["established_at"] == ""

    def test_check_reveal_timing_empty_memories(self):
        svc = _make_service([])
        result = svc.check_reveal_timing("Alice", "some_event", "scene_01", "film_x")
        assert result["is_premature"] is False
        assert isinstance(result["reason"], str)
        assert result["established_at"] == ""

    def test_extract_nodes_no_storage_needed(self):
        """_extract_character_knowledge_nodes doesn't need storage."""
        svc = ContinuityIntelligenceService(storage=None)
        nodes = svc._extract_character_knowledge_nodes(
            scene={"characters_present": ["Alice"]},
            scene_id="scene_01",
            film_id="film_x",
            active_causal_events=[],
        )
        assert len(nodes) == 1
        assert nodes[0]["confidence"] == "inferred"

    def test_check_reveal_timing_unknown_event_returns_not_premature(self):
        """If the event was never established, we can't call it premature."""
        memories = [
            _make_memory(
                "mem1", "asset1", "film5",
                scene_id="scene_01",
                characters=["Alice"],
                causal_events=["other_event"],
            ),
        ]
        svc = _make_service(memories)
        result = svc.check_reveal_timing(
            character_name="Alice",
            knowledge_event="nonexistent_event",
            reveal_scene_id="scene_01",
            film_id="film5",
        )
        assert result["is_premature"] is False
        assert "nonexistent_event" in result["reason"]
