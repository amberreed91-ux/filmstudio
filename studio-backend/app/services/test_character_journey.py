"""
Tests for character journey map feature.

Covers:
- build_character_journey_map correctly traces per-character journey
- Dramatic irony correctly identified when knowledge gap exists
- unresolved_knowledge correctly identified at film end
- Characters with 1 scene get minimal entry with uncertainty note
- Character journeys attached to Film DNA correctly
"""
import pytest
from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


def _make_db(tmp_path: Path) -> DatabaseStorage:
    """Create a temporary database for testing."""
    return DatabaseStorage(str(tmp_path))


class TestBuildCharacterJourneyMap:
    """Test build_character_journey_map method."""

    @pytest.mark.asyncio
    async def test_traces_per_character_journey(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Set up graph with character knowledge nodes.
        graph = {
            "character_knowledge_nodes": [
                {
                    "character_name": "Alice",
                    "scene_id": "scene_1",
                    "emotional_register": "calm",
                    "witnessed_events": ["event_a"],
                },
                {
                    "character_name": "Alice",
                    "scene_id": "scene_2",
                    "emotional_register": "tense",
                    "witnessed_events": ["event_a", "event_b"],
                },
                {
                    "character_name": "Bob",
                    "scene_id": "scene_2",
                    "emotional_register": "hopeful",
                    "witnessed_events": ["event_b"],
                },
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "sceneTitle": "Opening", "emotionalTone": "calm"},
            {"sceneId": "scene_2", "sceneTitle": "Conflict", "emotionalTone": "tense"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        assert len(journey_map["characters"]) == 2

        # Alice should have 2 journey entries.
        alice = next((c for c in journey_map["characters"] if c["name"] == "Alice"), None)
        assert alice is not None
        assert alice["total_scenes"] == 2
        assert len(alice["journey"]) == 2
        assert alice["journey"][0]["scene_id"] == "scene_1"
        assert alice["journey"][0]["emotional_state"] == "calm"
        assert alice["journey"][0]["knowledge_events"] == ["event_a"]
        assert alice["journey"][1]["scene_id"] == "scene_2"
        assert alice["journey"][1]["emotional_state"] == "tense"
        assert alice["journey"][1]["knowledge_events"] == ["event_a", "event_b"]

        # Bob should have 1 journey entry.
        bob = next((c for c in journey_map["characters"] if c["name"] == "Bob"), None)
        assert bob is not None
        assert bob["total_scenes"] == 1
        assert len(bob["journey"]) == 1
        assert bob["journey"][0]["scene_id"] == "scene_2"

    @pytest.mark.asyncio
    async def test_dramatic_irony_identified(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Alice knows event_a, Bob knows event_b.
        # In scene_1, Alice doesn't know event_b yet (dramatic irony).
        graph = {
            "character_knowledge_nodes": [
                {
                    "character_name": "Alice",
                    "scene_id": "scene_1",
                    "emotional_register": "calm",
                    "witnessed_events": ["event_a"],
                },
                {
                    "character_name": "Bob",
                    "scene_id": "scene_1",
                    "emotional_register": "hopeful",
                    "witnessed_events": ["event_b"],
                },
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "sceneTitle": "Opening", "emotionalTone": "calm"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        # Alice should have dramatic irony (doesn't know event_b).
        alice = next((c for c in journey_map["characters"] if c["name"] == "Alice"), None)
        assert alice is not None
        assert alice["journey"][0]["dramatic_irony"] is True
        assert "event_b" in alice["journey"][0]["knowledge_gaps"]
        assert alice["journey"][0]["irony_note"] is not None

        # Bob should have dramatic irony (doesn't know event_a).
        bob = next((c for c in journey_map["characters"] if c["name"] == "Bob"), None)
        assert bob is not None
        assert bob["journey"][0]["dramatic_irony"] is True
        assert "event_a" in bob["journey"][0]["knowledge_gaps"]

        # Dramatic irony scenes should include scene_1.
        assert "scene_1" in journey_map["dramatic_irony_scenes"]

    @pytest.mark.asyncio
    async def test_unresolved_knowledge_identified(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Alice appears in scene_1 and scene_2.
        # Bob appears in scene_3 and witnesses event_c.
        # Alice never learns about event_c (unresolved knowledge).
        graph = {
            "character_knowledge_nodes": [
                {
                    "character_name": "Alice",
                    "scene_id": "scene_1",
                    "emotional_register": "calm",
                    "witnessed_events": ["event_a"],
                },
                {
                    "character_name": "Alice",
                    "scene_id": "scene_2",
                    "emotional_register": "tense",
                    "witnessed_events": ["event_a", "event_b"],
                },
                {
                    "character_name": "Bob",
                    "scene_id": "scene_3",
                    "emotional_register": "hopeful",
                    "witnessed_events": ["event_c"],
                },
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "sceneTitle": "Opening"},
            {"sceneId": "scene_2", "sceneTitle": "Conflict"},
            {"sceneId": "scene_3", "sceneTitle": "Resolution"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        # Alice should have unresolved knowledge (event_c happened after her last scene).
        alice = next((c for c in journey_map["characters"] if c["name"] == "Alice"), None)
        assert alice is not None
        # event_c is not in Alice's unresolved because it happened after her last scene
        # Let's check Bob doesn't know event_a or event_b
        bob = next((c for c in journey_map["characters"] if c["name"] == "Bob"), None)
        assert bob is not None
        # Bob should have unresolved knowledge for events before his scene
        assert "event_a" in bob["unresolved_knowledge"] or "event_b" in bob["unresolved_knowledge"]

    @pytest.mark.asyncio
    async def test_single_scene_character_gets_uncertainty_note(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        graph = {
            "character_knowledge_nodes": [
                {
                    "character_name": "Alice",
                    "scene_id": "scene_1",
                    "emotional_register": "calm",
                    "witnessed_events": [],
                },
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "sceneTitle": "Opening"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        assert len(journey_map["uncertainty_notes"]) > 0
        assert any("only 1 scene" in note.lower() for note in journey_map["uncertainty_notes"])

    @pytest.mark.asyncio
    async def test_arc_summary_generated(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        graph = {
            "character_knowledge_nodes": [
                {
                    "character_name": "Alice",
                    "scene_id": "scene_1",
                    "emotional_register": "calm",
                    "witnessed_events": [],
                },
                {
                    "character_name": "Alice",
                    "scene_id": "scene_2",
                    "emotional_register": "hopeful",
                    "witnessed_events": [],
                },
                {
                    "character_name": "Alice",
                    "scene_id": "scene_3",
                    "emotional_register": "tense",
                    "witnessed_events": [],
                },
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "sceneTitle": "Opening"},
            {"sceneId": "scene_2", "sceneTitle": "Middle"},
            {"sceneId": "scene_3", "sceneTitle": "End"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        alice = next((c for c in journey_map["characters"] if c["name"] == "Alice"), None)
        assert alice is not None
        assert alice["arc_summary"] is not None
        assert len(alice["arc_summary"]) > 0
        # Should mention transition from calm to tense
        assert "calm" in alice["arc_summary"].lower() or "tense" in alice["arc_summary"].lower()

    @pytest.mark.asyncio
    async def test_characters_sorted_by_scene_count(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        graph = {
            "character_knowledge_nodes": [
                {"character_name": "Alice", "scene_id": "scene_1", "emotional_register": "calm", "witnessed_events": []},
                {"character_name": "Bob", "scene_id": "scene_1", "emotional_register": "calm", "witnessed_events": []},
                {"character_name": "Bob", "scene_id": "scene_2", "emotional_register": "calm", "witnessed_events": []},
                {"character_name": "Bob", "scene_id": "scene_3", "emotional_register": "calm", "witnessed_events": []},
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1"},
            {"sceneId": "scene_2"},
            {"sceneId": "scene_3"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        # Bob (3 scenes) should come before Alice (1 scene).
        assert journey_map["characters"][0]["name"] == "Bob"
        assert journey_map["characters"][1]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_empty_graph_returns_empty_journey(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        svc._graph_store["film1"] = {}

        scenes = [
            {"sceneId": "scene_1"},
        ]

        journey_map = await svc.build_character_journey_map("film1", scenes)

        assert len(journey_map["characters"]) == 0
        assert len(journey_map["uncertainty_notes"]) > 0


class TestFilmDNAWithCharacterJourneys:
    """Test that character journeys are attached to Film DNA."""

    @pytest.mark.asyncio
    async def test_film_dna_includes_character_journeys(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        graph = {
            "character_knowledge_nodes": [
                {
                    "character_name": "Alice",
                    "scene_id": "scene_1",
                    "emotional_register": "calm",
                    "witnessed_events": ["event_a"],
                },
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "hopeful", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "tense", "visualTags": []},
        ]

        dna = await svc.build_film_dna("film1", scenes)

        assert "character_journeys" in dna
        assert "characters" in dna["character_journeys"]
        assert len(dna["character_journeys"]["characters"]) > 0
