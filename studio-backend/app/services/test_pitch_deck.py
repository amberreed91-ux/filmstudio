"""
Tests for Pitch Deck Service.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from app.services.pitch_deck_service import PitchDeckService


@pytest.fixture
def mock_storage():
    """Create a mock storage instance."""
    storage = Mock()
    
    # Mock project
    project = Mock()
    project.model_dump.return_value = {
        "project_id": "project_123",
        "title": "Test Film",
        "script_text": "A musician discovers a memory glitch in the city.",
    }
    storage.get_project.return_value = project
    
    # Mock Film DNA
    storage.load_film_dna.return_value = {
        "logline": "A displaced musician uncovers a citywide memory glitch one song at a time.",
        "primary_tone": "mysterious",
        "secondary_tone": "melancholic",
        "dominant_motifs": ["music", "memory", "urban decay"],
        "lighting_character": "moody with high contrast",
    }
    
    # Mock director intent
    storage.load_director_intent.return_value = {
        "concept": "The film explores how music can unlock forgotten memories.",
        "visual_references": ["Blade Runner", "Her"],
        "tone_references": ["noir", "sci-fi"],
    }
    
    # Mock continuity graph
    storage.load_continuity_graph.return_value = {
        "nodes": [
            {"element_type": "character", "element_id": "Alex", "scene_id": "scene_001"},
            {"element_type": "character", "element_id": "Alex", "scene_id": "scene_002"},
            {"element_type": "character", "element_id": "Alex", "scene_id": "scene_003"},
            {"element_type": "character", "element_id": "Maya", "scene_id": "scene_001"},
            {"element_type": "character", "element_id": "Maya", "scene_id": "scene_002"},
        ]
    }
    
    # Mock export packages
    storage.list_export_packages.return_value = []
    
    # Mock save
    storage.save_pitch_deck.return_value = True
    
    return storage


@pytest.fixture
def mock_arc_completeness():
    """Create mock arc completeness data."""
    return {
        "arc_shape": "rising action with ambiguous resolution",
        "resolution_read": "open-ended",
        "completeness_assessment": "Arc is well-developed with clear emotional beats",
        "character_arcs": [
            {
                "character_name": "Alex",
                "arc_summary": "Alex transforms from a lost musician to someone who understands the power of memory.",
            }
        ],
    }


@pytest.fixture
def service(mock_storage):
    """Create a PitchDeckService instance with mock storage."""
    service = PitchDeckService(storage=mock_storage)
    return service


@pytest.mark.asyncio
async def test_generate_pitch_deck_produces_correct_slide_count(service, mock_storage, mock_arc_completeness):
    """Test that generate_pitch_deck produces the correct number of slides."""
    # Mock arc completeness
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "festival")
    
    # Expected slides: logline, concept, visual language, 1 character (Alex), arc, tone, production note
    assert len(deck["slides"]) == 7
    
    # Verify slide types
    slide_types = [s["type"] for s in deck["slides"]]
    assert "logline" in slide_types
    assert "concept" in slide_types
    assert "visual_language" in slide_types
    assert "character" in slide_types
    assert "arc" in slide_types
    assert "tone" in slide_types
    assert "production_note" in slide_types


@pytest.mark.asyncio
async def test_logline_synthesized_from_film_dna(service, mock_storage, mock_arc_completeness):
    """Test that logline is synthesized from Film DNA when available."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "general")
    
    assert deck["logline"] == "A displaced musician uncovers a citywide memory glitch one song at a time."
    assert deck["logline"] != ""


@pytest.mark.asyncio
async def test_character_slides_generated_for_3plus_scene_characters_only(service, mock_storage, mock_arc_completeness):
    """Test that character slides are only generated for characters with 3+ scenes."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "investor")
    
    # Only Alex has 3+ scenes (Maya has 2)
    character_slides = [s for s in deck["slides"] if s["type"] == "character"]
    assert len(character_slides) == 1
    assert character_slides[0]["headline"] == "Alex"


@pytest.mark.asyncio
async def test_honest_note_always_present(service, mock_storage, mock_arc_completeness):
    """Test that honest_note is always present in the deck."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "festival")
    
    assert "honest_note" in deck
    assert deck["honest_note"] != ""
    assert "AI-drafted starting point" in deck["honest_note"]


@pytest.mark.asyncio
async def test_uncertainty_notes_present_when_film_dna_missing(service, mock_storage):
    """Test that uncertainty_notes are present when Film DNA is missing."""
    # Remove Film DNA
    mock_storage.load_film_dna.return_value = None
    
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=None)
    
    deck = await service.generate_pitch_deck("project_123", "general")
    
    assert "uncertainty_notes" in deck
    assert len(deck["uncertainty_notes"]) > 0
    # Check for any uncertainty note (Film DNA or arc analysis)
    assert any("not available" in note.lower() for note in deck["uncertainty_notes"])


@pytest.mark.asyncio
async def test_data_source_correctly_attributed_per_slide(service, mock_storage, mock_arc_completeness):
    """Test that data_source is correctly attributed for each slide."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "festival")
    
    # Check that all slides have data_source
    for slide in deck["slides"]:
        assert "data_source" in slide
        assert slide["data_source"] in [
            "film_dna",
            "character_journey",
            "director_intent",
            "arc_analysis",
            "synthesized",
            "export_package",
        ]


@pytest.mark.asyncio
async def test_storage_round_trip(service, mock_storage, mock_arc_completeness):
    """Test that storage round-trip works correctly."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "investor")
    
    # Verify save was called
    mock_storage.save_pitch_deck.assert_called_once()
    call_args = mock_storage.save_pitch_deck.call_args
    assert call_args[0][0] == "project_123"  # project_id
    assert call_args[0][1]["deck_id"] == deck["deck_id"]


@pytest.mark.asyncio
async def test_target_audience_stored_correctly(service, mock_storage, mock_arc_completeness):
    """Test that target_audience is stored correctly in the deck."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "festival")
    
    assert deck["target_audience"] == "festival"


@pytest.mark.asyncio
async def test_production_note_slide_with_export_package(service, mock_storage, mock_arc_completeness):
    """Test that production note slide uses export package when available."""
    # Add export package
    mock_storage.list_export_packages.return_value = [{"package_id": "export_123"}]
    mock_storage.load_export_package.return_value = {
        "package_id": "export_123",
        "honest_assembly_note": "Stitched film assembled from 5 completed render outputs.",
    }
    
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "general")
    
    production_slide = [s for s in deck["slides"] if s["type"] == "production_note"][0]
    assert "Stitched film assembled" in production_slide["body"]
    assert production_slide["data_source"] == "export_package"


@pytest.mark.asyncio
async def test_production_note_slide_without_export_package(service, mock_storage, mock_arc_completeness):
    """Test that production note slide shows 'In production' when no export package."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "general")
    
    production_slide = [s for s in deck["slides"] if s["type"] == "production_note"][0]
    assert "In production" in production_slide["body"]
    assert production_slide["data_source"] == "synthesized"


@pytest.mark.asyncio
async def test_visual_language_slide_includes_motifs(service, mock_storage, mock_arc_completeness):
    """Test that visual language slide includes dominant motifs from Film DNA."""
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    continuity_intelligence_service.check_arc_completeness = AsyncMock(return_value=mock_arc_completeness)
    
    deck = await service.generate_pitch_deck("project_123", "festival")
    
    visual_slide = [s for s in deck["slides"] if s["type"] == "visual_language"][0]
    assert "music" in visual_slide["body"] or "memory" in visual_slide["body"]
    assert visual_slide["data_source"] in ["film_dna", "director_intent", "synthesized"]
