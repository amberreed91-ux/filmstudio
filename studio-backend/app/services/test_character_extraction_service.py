import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, PropertyMock
from app.services.character_extraction_service import character_extraction_service


class TestCharacterExtractionService:

    def test_empty_script_returns_no_updates(self):
        """Test that empty script text returns early without processing."""
        async def run_test():
            result = await character_extraction_service.extract_and_update_characters(
                project_id="test_project",
                script_text="",
                scene_characters=["JOHN"]
            )
            assert result["updated"] == 0
            assert result["skipped"] == 0

        asyncio.run(run_test())

    def test_no_characters_returns_no_updates(self):
        """Test that empty character list returns early without processing."""
        async def run_test():
            result = await character_extraction_service.extract_and_update_characters(
                project_id="test_project",
                script_text="Some script content",
                scene_characters=[]
            )
            assert result["updated"] == 0
            assert result["skipped"] == 0

        asyncio.run(run_test())

    @patch('app.services.character_extraction_service.call_llm')
    @patch.object(character_extraction_service, 'storage')
    def test_extracts_character_details_from_script(self, mock_storage, mock_call_llm):
        """Test that character details are extracted from script using LLM."""
        # Mock storage
        mock_storage.get_all_character_memories.return_value = []

        # Mock LLM response
        mock_call_llm.return_value = '''{
            "appearance_traits": ["tall", "dark hair"],
            "personality_traits": ["brave", "determined"],
            "speech_patterns": ["speaks clearly", "uses formal language"],
            "mannerisms": ["paces when thinking"],
            "physical_quirks": ["limps slightly"],
            "wardrobe": ["wears suits", "carries a briefcase"],
            "backstory_notes": "Former detective turned private investigator"
        }'''

        async def run_test():
            result = await character_extraction_service.extract_and_update_characters(
                project_id="test_project",
                script_text="INT. OFFICE - DAY\nJOHN enters. He is tall with dark hair, wearing a suit.",
                scene_characters=["JOHN"]
            )

            assert result["updated"] == 1
            assert result["skipped"] == 0
            assert len(result["errors"]) == 0

            # Verify save_character_memory was called
            mock_storage.save_character_memory.assert_called_once()
            call_args = mock_storage.save_character_memory.call_args[0][0]
            assert call_args["project_id"] == "test_project"
            assert call_args["character_name"] == "JOHN"
            assert "tall" in call_args["appearance_traits"]
            assert "brave" in call_args["personality_traits"]

        asyncio.run(run_test())

    @patch('app.services.character_extraction_service.call_llm')
    @patch.object(character_extraction_service, 'storage')
    def test_does_not_overwrite_existing_fields(self, mock_storage, mock_call_llm):
        """Test that existing character fields are not overwritten."""
        # Mock storage with existing character
        mock_storage.get_all_character_memories.return_value = [
            {
                "project_id": "test_project",
                "character_id": "char_john",
                "character_name": "JOHN",
                "appearance_traits": ["existing trait"],
                "personality_traits": [],
                "speech_patterns": [],
                "mannerisms": [],
                "physical_quirks": [],
                "wardrobe": [],
                "backstory_notes": ""
            }
        ]

        # Mock LLM response
        mock_call_llm.return_value = '''{
            "appearance_traits": ["new trait"],
            "personality_traits": ["brave"],
            "speech_patterns": [],
            "mannerisms": [],
            "physical_quirks": [],
            "wardrobe": [],
            "backstory_notes": ""
        }'''

        async def run_test():
            result = await character_extraction_service.extract_and_update_characters(
                project_id="test_project",
                script_text="Script content",
                scene_characters=["JOHN"]
            )

            # Should still update (new fields added)
            assert result["updated"] == 1

            # Verify existing appearance_traits was preserved
            call_args = mock_storage.save_character_memory.call_args[0][0]
            assert "existing trait" in call_args["appearance_traits"]
            assert "new trait" not in call_args["appearance_traits"]  # Should not overwrite
            assert "brave" in call_args["personality_traits"]  # Should add to empty field

        asyncio.run(run_test())

    @patch('app.services.character_extraction_service.call_llm')
    @patch.object(character_extraction_service, 'storage')
    def test_handles_llm_error_gracefully(self, mock_storage, mock_call_llm):
        """Test that LLM errors are handled gracefully."""
        mock_storage.get_all_character_memories.return_value = []

        # Mock LLM error
        mock_call_llm.side_effect = Exception("LLM API error")

        async def run_test():
            result = await character_extraction_service.extract_and_update_characters(
                project_id="test_project",
                script_text="Script content",
                scene_characters=["JOHN"]
            )

            # New character record is still saved with empty fields on extraction failure
            assert result["updated"] == 1
            assert len(result["errors"]) == 0

        asyncio.run(run_test())

    @patch('app.services.character_extraction_service.call_llm')
    @patch.object(character_extraction_service, 'storage')
    def test_filters_by_project_id(self, mock_storage, mock_call_llm):
        """Test that only characters from the specified project are affected."""
        # Storage already filters by project_id; return empty for test_project
        mock_storage.get_all_character_memories.return_value = []

        mock_call_llm.return_value = '''{
            "appearance_traits": [],
            "personality_traits": [],
            "speech_patterns": [],
            "mannerisms": [],
            "physical_quirks": [],
            "wardrobe": [],
            "backstory_notes": ""
        }'''

        async def run_test():
            result = await character_extraction_service.extract_and_update_characters(
                project_id="test_project",
                script_text="Script content",
                scene_characters=["JANE"]
            )

            # Should treat as new character (not found in test_project)
            assert result["updated"] == 1

            # Verify save was called with correct project_id
            call_args = mock_storage.save_character_memory.call_args[0][0]
            assert call_args["project_id"] == "test_project"

        asyncio.run(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
