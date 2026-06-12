"""
Tests for director intent functionality.

Covers:
- save and load director_intent round-trip correctly
- Merge behavior preserves existing fields when partial update sent
- Intent prefix is injected into render prompts when non-empty
- Intent prefix is omitted when intent is empty
- Render prompt includes intent context alongside graph context
"""
import pytest
from pathlib import Path
from datetime import datetime

from app.data.storage import DatabaseStorage
from app.models import StudioProject, SourceStats, RenderProvider
from app.utils.director_intent_injection import (
    build_director_intent_prefix,
    inject_director_intent_into_prompt,
)


def _make_db(tmp_path: Path) -> DatabaseStorage:
    """Create a temporary database for testing."""
    return DatabaseStorage(str(tmp_path))


class TestDirectorIntentStorage:
    """Test director intent storage methods."""

    def test_save_and_load_round_trip(self, tmp_path):
        """Test that save and load director_intent round-trip correctly."""
        db = _make_db(tmp_path)

        # Create a project
        project = StudioProject(
            project_id="proj-001",
            title="Test Project",
            updated_at=datetime.now().isoformat(),
            source_stats=SourceStats(),
            render_provider=RenderProvider(
                provider_name="test", provider_model="test", status="ready", mode="batch"
            ),
        )
        db.save_project(project)

        # Save director intent
        intent = {
            "genre": "Neo-noir thriller",
            "tone_references": ["Arrival", "Blade Runner 2049"],
            "emotional_target": "Contemplative unease",
            "visual_references": ["Deakins lighting", "handheld"],
            "what_success_looks_like": "A film that lingers",
            "what_to_avoid": ["Heavy exposition", "melodrama"],
        }

        success = db.save_director_intent("proj-001", intent)
        assert success is True

        # Load director intent
        loaded_intent = db.load_director_intent("proj-001")
        assert loaded_intent is not None
        assert loaded_intent["genre"] == "Neo-noir thriller"
        assert loaded_intent["tone_references"] == ["Arrival", "Blade Runner 2049"]
        assert loaded_intent["emotional_target"] == "Contemplative unease"
        assert loaded_intent["visual_references"] == ["Deakins lighting", "handheld"]
        assert loaded_intent["what_success_looks_like"] == "A film that lingers"
        assert loaded_intent["what_to_avoid"] == ["Heavy exposition", "melodrama"]
        assert "captured_at" in loaded_intent
        assert "last_updated" in loaded_intent

    def test_merge_behavior_preserves_existing_fields(self, tmp_path):
        """Test that merge behavior preserves existing fields when partial update sent."""
        db = _make_db(tmp_path)

        # Create a project
        project = StudioProject(
            project_id="proj-002",
            title="Test Project 2",
            updated_at=datetime.now().isoformat(),
            source_stats=SourceStats(),
        )
        db.save_project(project)

        # Save initial intent
        initial_intent = {
            "genre": "Drama",
            "tone_references": ["Moonlight"],
            "emotional_target": "Empathy",
        }
        db.save_director_intent("proj-002", initial_intent)

        # Update with partial intent
        partial_update = {
            "visual_references": ["Natural lighting"],
            "what_to_avoid": ["Sentimentality"],
        }
        db.save_director_intent("proj-002", partial_update)

        # Load and verify merge
        merged_intent = db.load_director_intent("proj-002")
        assert merged_intent["genre"] == "Drama"  # Preserved
        assert merged_intent["tone_references"] == ["Moonlight"]  # Preserved
        assert merged_intent["emotional_target"] == "Empathy"  # Preserved
        assert merged_intent["visual_references"] == ["Natural lighting"]  # Added
        assert merged_intent["what_to_avoid"] == ["Sentimentality"]  # Added

    def test_load_nonexistent_project_returns_none(self, tmp_path):
        """Test that loading intent for nonexistent project returns None."""
        db = _make_db(tmp_path)
        intent = db.load_director_intent("nonexistent-project")
        assert intent is None

    def test_save_to_nonexistent_project_returns_false(self, tmp_path):
        """Test that saving intent to nonexistent project returns False."""
        db = _make_db(tmp_path)
        intent = {"genre": "Drama"}
        success = db.save_director_intent("nonexistent-project", intent)
        assert success is False


class TestDirectorIntentInjection:
    """Test director intent injection into prompts."""

    def test_intent_prefix_injected_when_non_empty(self):
        """Test that intent prefix is injected into prompts when non-empty."""
        intent = {
            "genre": "Sci-fi",
            "tone_references": ["2001: A Space Odyssey"],
            "emotional_target": "Wonder and isolation",
        }

        prefix = build_director_intent_prefix(intent)

        assert "DIRECTOR INTENT:" in prefix
        assert "Genre: Sci-fi" in prefix
        assert "Tone references: 2001: A Space Odyssey" in prefix
        assert "Emotional target: Wonder and isolation" in prefix

    def test_intent_prefix_omitted_when_empty(self):
        """Test that intent prefix is omitted when intent is empty."""
        # Empty intent dict
        prefix = build_director_intent_prefix({})
        assert prefix == ""

        # None intent
        prefix = build_director_intent_prefix(None)
        assert prefix == ""

        # Intent with all None/empty fields
        intent = {
            "genre": None,
            "tone_references": [],
            "emotional_target": None,
            "visual_references": [],
            "what_success_looks_like": None,
            "what_to_avoid": [],
        }
        prefix = build_director_intent_prefix(intent)
        assert prefix == ""

    def test_intent_prefix_includes_only_non_empty_fields(self):
        """Test that intent prefix includes only non-empty fields."""
        intent = {
            "genre": "Horror",
            "tone_references": [],  # Empty
            "emotional_target": None,  # None
            "visual_references": ["Low-key lighting"],
            "what_success_looks_like": None,  # None
            "what_to_avoid": ["Jump scares"],
        }

        prefix = build_director_intent_prefix(intent)

        assert "Genre: Horror" in prefix
        assert "Tone references:" not in prefix  # Empty list excluded
        assert "Emotional target:" not in prefix  # None excluded
        assert "Visual references: Low-key lighting" in prefix
        assert "What success looks like:" not in prefix  # None excluded
        assert "Avoid: Jump scares" in prefix

    def test_inject_director_intent_into_prompt(self):
        """Test that director intent is injected into base prompt."""
        intent = {
            "genre": "Western",
            "emotional_target": "Moral ambiguity",
        }

        base_prompt = "A lone rider approaches the town at sunset."
        injected_prompt = inject_director_intent_into_prompt(base_prompt, intent)

        assert "DIRECTOR INTENT:" in injected_prompt
        assert "Genre: Western" in injected_prompt
        assert "Emotional target: Moral ambiguity" in injected_prompt
        assert "A lone rider approaches the town at sunset." in injected_prompt
        # Intent should come before base prompt
        assert injected_prompt.index("DIRECTOR INTENT:") < injected_prompt.index(
            "A lone rider"
        )

    def test_inject_empty_intent_returns_base_prompt(self):
        """Test that injecting empty intent returns base prompt unchanged."""
        base_prompt = "A scene description."

        # Empty intent
        injected_prompt = inject_director_intent_into_prompt(base_prompt, {})
        assert injected_prompt == base_prompt

        # None intent
        injected_prompt = inject_director_intent_into_prompt(base_prompt, None)
        assert injected_prompt == base_prompt

    def test_intent_prefix_formats_lists_correctly(self):
        """Test that lists are formatted correctly in intent prefix."""
        intent = {
            "tone_references": ["Film A", "Film B", "Film C"],
            "visual_references": ["Style 1", "Style 2"],
            "what_to_avoid": ["Cliche 1", "Cliche 2", "Cliche 3"],
        }

        prefix = build_director_intent_prefix(intent)

        assert "Tone references: Film A, Film B, Film C" in prefix
        assert "Visual references: Style 1, Style 2" in prefix
        assert "Avoid: Cliche 1, Cliche 2, Cliche 3" in prefix


class TestRenderPromptIntegration:
    """Test that render prompts include intent context alongside graph context."""

    def test_render_prompt_includes_intent_and_continuity(self, tmp_path):
        """Test that render prompt includes both intent and continuity context."""
        # This is an integration test that would require mocking the render service
        # For now, we verify the injection utility works correctly
        intent = {
            "genre": "Thriller",
            "emotional_target": "Suspense",
        }

        base_prompt = "Detective enters dark alley."
        continuity_context = (
            "\n\n[CINEMATIC CONTEXT]"
            "\nEmotional register: tense"
            "\nActive visual motifs: shadows, rain"
            "\nTonal direction: noir"
            "\nContinuity anchors: previous scene"
        )

        # Inject intent first
        prompt_with_intent = inject_director_intent_into_prompt(base_prompt, intent)

        # Then append continuity context
        final_prompt = prompt_with_intent + continuity_context

        # Verify both are present
        assert "DIRECTOR INTENT:" in final_prompt
        assert "Genre: Thriller" in final_prompt
        assert "Detective enters dark alley." in final_prompt
        assert "[CINEMATIC CONTEXT]" in final_prompt
        assert "Emotional register: tense" in final_prompt

        # Verify order: intent → base prompt → continuity
        intent_pos = final_prompt.index("DIRECTOR INTENT:")
        base_pos = final_prompt.index("Detective enters")
        continuity_pos = final_prompt.index("[CINEMATIC CONTEXT]")
        assert intent_pos < base_pos < continuity_pos
