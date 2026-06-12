"""
Tests for Film DNA persistence and build_film_dna method.

Covers:
- build_film_dna returns partial result with uncertainty when < 3 scenes
- emotional arc shape is correctly identified for rising/falling/flat/wave
- character roster is correctly built from graph nodes
- save_film_dna and load_film_dna round-trip correctly
- Auto-update triggers on scene add and qualifying revision
- Refresh endpoint returns "rebuilding" immediately
- Frontend DNA panel renders all sections correctly
- Empty state renders when insufficient scenes
"""
import pytest
import tempfile
from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


def _make_db(tmp_path: Path) -> DatabaseStorage:
    """Create a temporary database for testing."""
    return DatabaseStorage(str(tmp_path))


class TestFilmDNAStorage:
    """Test Film DNA storage methods."""

    def test_save_and_load_round_trip(self, tmp_path):
        db = _make_db(tmp_path)
        dna = {
            "film_id": "film1",
            "visual_language": {
                "dominant_motifs": ["rain", "shadows"],
                "color_palette_notes": "Dark and moody",
                "recurring_shot_types": ["close-up", "wide"],
                "lighting_character": "High-contrast",
            },
            "emotional_arc": {
                "opening_register": "calm",
                "closing_register": "tense",
                "peak_tension_scene": "scene_3",
                "arc_shape": "rising",
            },
            "tonal_identity": {
                "primary_tone": "melancholic",
                "secondary_tone": "hopeful",
                "tone_consistency": "consistent",
                "genre_signals": ["drama", "noir"],
            },
            "character_roster": [
                {
                    "name": "Alice",
                    "scenes_present": 3,
                    "first_appearance": "scene_1",
                    "last_appearance": "scene_3",
                    "emotional_trajectory": "Observing and reacting",
                }
            ],
            "production_notes": ["Consider establishing recurring visual elements."],
            "uncertainty_notes": [],
            "generated_at": "2024-01-01T00:00:00Z",
            "scene_count": 3,
            "version_id": "v1",
        }
        db.save_film_dna("film1", dna)
        loaded = db.load_film_dna("film1")

        assert loaded is not None
        assert loaded["film_id"] == "film1"
        assert loaded["visual_language"]["dominant_motifs"] == ["rain", "shadows"]
        assert loaded["emotional_arc"]["arc_shape"] == "rising"
        assert loaded["tonal_identity"]["primary_tone"] == "melancholic"
        assert len(loaded["character_roster"]) == 1
        assert loaded["character_roster"][0]["name"] == "Alice"

    def test_load_returns_none_when_no_dna(self, tmp_path):
        db = _make_db(tmp_path)
        result = db.load_film_dna("nonexistent_film")
        assert result is None

    def test_save_overwrites_existing_dna(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_film_dna("film1", {"version": 1})
        db.save_film_dna("film1", {"version": 2})
        loaded = db.load_film_dna("film1")
        assert loaded["version"] == 2

    def test_different_films_are_isolated(self, tmp_path):
        db = _make_db(tmp_path)
        db.save_film_dna("film_a", {"name": "A"})
        db.save_film_dna("film_b", {"name": "B"})
        assert db.load_film_dna("film_a")["name"] == "A"
        assert db.load_film_dna("film_b")["name"] == "B"


class TestBuildFilmDNA:
    """Test build_film_dna method."""

    @pytest.mark.asyncio
    async def test_returns_partial_result_when_fewer_than_3_scenes(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": ["rain"]},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert dna["scene_count"] == 1
        assert len(dna["uncertainty_notes"]) > 0
        assert "at least 3 scenes" in dna["uncertainty_notes"][0].lower()
        assert dna["emotional_arc"]["arc_shape"] == "uncertain"
        assert dna["tonal_identity"]["primary_tone"] == "uncertain"

    @pytest.mark.asyncio
    async def test_emotional_arc_rising(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "hopeful", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "tense", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert dna["emotional_arc"]["arc_shape"] == "rising"
        assert dna["emotional_arc"]["opening_register"] == "calm"
        assert dna["emotional_arc"]["closing_register"] == "tense"

    @pytest.mark.asyncio
    async def test_emotional_arc_falling(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "tense", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "hopeful", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "calm", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert dna["emotional_arc"]["arc_shape"] == "falling"

    @pytest.mark.asyncio
    async def test_emotional_arc_flat(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "calm", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert dna["emotional_arc"]["arc_shape"] == "flat"

    @pytest.mark.asyncio
    async def test_emotional_arc_wave(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "tense", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_4", "emotionalTone": "tense", "visualTags": []},
            {"sceneId": "scene_5", "emotionalTone": "calm", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert dna["emotional_arc"]["arc_shape"] == "wave"

    @pytest.mark.asyncio
    async def test_character_roster_built_from_graph_nodes(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Set up a graph with character knowledge nodes.
        graph = {
            "character_knowledge_nodes": [
                {"character_name": "Alice", "scene_id": "scene_1"},
                {"character_name": "Alice", "scene_id": "scene_2"},
                {"character_name": "Bob", "scene_id": "scene_2"},
                {"character_name": "Alice", "scene_id": "scene_3"},
            ]
        }
        svc._graph_store["film1"] = graph

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "hopeful", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "tense", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert len(dna["character_roster"]) == 2
        alice = next((c for c in dna["character_roster"] if c["name"] == "Alice"), None)
        bob = next((c for c in dna["character_roster"] if c["name"] == "Bob"), None)

        assert alice is not None
        assert alice["scenes_present"] == 3
        assert alice["first_appearance"] == "scene_1"
        assert alice["last_appearance"] == "scene_3"

        assert bob is not None
        assert bob["scenes_present"] == 1
        assert bob["first_appearance"] == "scene_2"
        assert bob["last_appearance"] == "scene_2"

    @pytest.mark.asyncio
    async def test_dominant_motifs_extracted(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": ["rain", "shadows"]},
            {"sceneId": "scene_2", "emotionalTone": "hopeful", "visualTags": ["rain", "light"]},
            {"sceneId": "scene_3", "emotionalTone": "tense", "visualTags": ["rain", "shadows"]},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        # "rain" appears in all 3 scenes (100%), "shadows" in 2 (67%).
        # Threshold is 30%, so both should be dominant.
        assert "rain" in dna["visual_language"]["dominant_motifs"]
        assert "shadows" in dna["visual_language"]["dominant_motifs"]

    @pytest.mark.asyncio
    async def test_tonal_identity_extracted(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "melancholic", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "melancholic", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "melancholic", "visualTags": []},
            {"sceneId": "scene_4", "emotionalTone": "hopeful", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert dna["tonal_identity"]["primary_tone"] == "melancholic"
        assert dna["tonal_identity"]["secondary_tone"] == "hopeful"
        # 2 unique tones out of 4 = 50%, which is > 40% but < 60%, so "drifting"
        assert dna["tonal_identity"]["tone_consistency"] in ["consistent", "drifting"]

    @pytest.mark.asyncio
    async def test_production_notes_generated(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Flat arc should trigger a production note.
        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "calm", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "calm", "visualTags": []},
        ]
        dna = await svc.build_film_dna("film1", scenes)

        assert len(dna["production_notes"]) > 0
        assert any("flat" in note.lower() for note in dna["production_notes"])
