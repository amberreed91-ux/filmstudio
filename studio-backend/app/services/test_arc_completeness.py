"""
Tests for arc completeness analysis.

Covers:
- Tension mapping correctly categorizes emotional tones
- Complete arc correctly identified (low → peak → releasing)
- Incomplete arc correctly identified (missing releasing phase)
- Confidence is never returned as "high"
- Arc completeness is attached to Film DNA correctly
"""
import pytest
from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


def _make_db(tmp_path: Path) -> DatabaseStorage:
    """Create a temporary database for testing."""
    return DatabaseStorage(str(tmp_path))


class TestCheckArcCompleteness:
    """Test check_arc_completeness method."""

    @pytest.mark.asyncio
    async def test_tension_mapping_categorizes_correctly(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral"},
            {"sceneId": "scene_2", "emotionalTone": "tense"},
            {"sceneId": "scene_3", "emotionalTone": "contemplative"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert arc["tension_curve"][0]["tension_read"] == "low"
        assert arc["tension_curve"][1]["tension_read"] in ["building", "peak"]
        assert arc["tension_curve"][2]["tension_read"] == "releasing"

    @pytest.mark.asyncio
    async def test_complete_arc_identified(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Complete arc: low → building → peak → releasing
        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral"},
            {"sceneId": "scene_2", "emotionalTone": "tension"},
            {"sceneId": "scene_3", "emotionalTone": "confrontation"},
            {"sceneId": "scene_4", "emotionalTone": "contemplative"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert arc["arc_read"] == "complete"
        assert "recognizable progression" in arc["resolution_read"].lower()

    @pytest.mark.asyncio
    async def test_incomplete_arc_identified(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Incomplete arc: low → building → peak (no releasing)
        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral"},
            {"sceneId": "scene_2", "emotionalTone": "tension"},
            {"sceneId": "scene_3", "emotionalTone": "confrontation"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert arc["arc_read"] == "incomplete"
        assert "does not clearly release" in arc["resolution_read"].lower()

    @pytest.mark.asyncio
    async def test_ambiguous_arc_identified(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Ambiguous arc: no clear pattern
        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "hopeful"},
            {"sceneId": "scene_2", "emotionalTone": "melancholic"},
            {"sceneId": "scene_3", "emotionalTone": "joyful"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert arc["arc_read"] in ["ambiguous", "uncertain"]

    @pytest.mark.asyncio
    async def test_confidence_never_high(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Even with many scenes, confidence should never be "high"
        scenes = [
            {"sceneId": f"scene_{i}", "emotionalTone": "neutral"}
            for i in range(10)
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert arc["confidence"] in ["low", "medium"]
        assert arc["confidence"] != "high"

    @pytest.mark.asyncio
    async def test_missing_beats_identified(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Arc with only peak, missing low and releasing
        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "confrontation"},
            {"sceneId": "scene_2", "emotionalTone": "tension"},
            {"sceneId": "scene_3", "emotionalTone": "confrontation"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert len(arc["missing_beats"]) > 0
        # Should identify missing low baseline and releasing phase
        missing_text = " ".join(arc["missing_beats"]).lower()
        assert "low" in missing_text or "baseline" in missing_text or "releasing" in missing_text

    @pytest.mark.asyncio
    async def test_insufficient_scenes_returns_uncertain(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert arc["arc_read"] == "uncertain"
        assert len(arc["uncertainty_notes"]) > 0
        assert "at least 3 scenes" in arc["uncertainty_notes"][0].lower()

    @pytest.mark.asyncio
    async def test_uncertainty_note_always_present(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral"},
            {"sceneId": "scene_2", "emotionalTone": "tension"},
            {"sceneId": "scene_3", "emotionalTone": "contemplative"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        # Should always have uncertainty note about performance context
        assert any(
            "performance context" in note.lower()
            for note in arc["uncertainty_notes"]
        )

    @pytest.mark.asyncio
    async def test_tension_curve_has_all_fields(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral"},
            {"sceneId": "scene_2", "emotionalTone": "tension"},
            {"sceneId": "scene_3", "emotionalTone": "contemplative"},
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert len(arc["tension_curve"]) == 3
        for entry in arc["tension_curve"]:
            assert "scene_id" in entry
            assert "order_index" in entry
            assert "tension_read" in entry
            assert "note" in entry

    @pytest.mark.asyncio
    async def test_pacing_observations_generated(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        # Multiple peak scenes should trigger pacing observation
        scenes = [
            {"sceneId": f"scene_{i}", "emotionalTone": "confrontation"}
            for i in range(5)
        ]

        arc = await svc.check_arc_completeness("film1", scenes)

        assert len(arc["pacing_observations"]) > 0


class TestFilmDNAWithArcCompleteness:
    """Test that arc completeness is attached to Film DNA."""

    @pytest.mark.asyncio
    async def test_film_dna_includes_arc_completeness(self, tmp_path):
        db = _make_db(tmp_path)
        svc = ContinuityIntelligenceService(storage=db)

        scenes = [
            {"sceneId": "scene_1", "emotionalTone": "neutral", "visualTags": []},
            {"sceneId": "scene_2", "emotionalTone": "tension", "visualTags": []},
            {"sceneId": "scene_3", "emotionalTone": "contemplative", "visualTags": []},
        ]

        dna = await svc.build_film_dna("film1", scenes)

        assert "arc_completeness" in dna
        assert "arc_read" in dna["arc_completeness"]
        assert "tension_curve" in dna["arc_completeness"]
        assert len(dna["arc_completeness"]["tension_curve"]) == 3
