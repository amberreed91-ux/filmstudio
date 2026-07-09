"""Unit tests for AudioDirectorService."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch, AsyncMock

import pytest

from app.models.script_intelligence import SoundAdvisory
from app.services.audio_director_service import (
    _build_context,
    _derive_act_position,
    _load_scene,
    generate_scene_audio_brief,
)


def _scene(scene_id: str, **overrides) -> dict:
    defaults = {
        "scene_id": scene_id,
        "heading": f"EXT. LOCATION - DAY",
        "description": f"Description for {scene_id}",
        "emotional_tone": "melancholic",
        "characters": ["Elena"],
    }
    defaults.update(overrides)
    return defaults


def _project(project_id: str, scenes: list[dict]) -> dict:
    return {
        "project_id": project_id,
        "title": "Test Film",
        "execution_summary": {"scenes": scenes},
    }


class TestLoadScene:
    def test_returns_scene_when_found(self):
        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            result = _load_scene("p1", "scene_001")
            assert result["scene_id"] == "scene_001"

    def test_returns_none_when_project_missing(self):
        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = None
            assert _load_scene("p1", "scene_001") is None

    def test_returns_none_when_scene_missing(self):
        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            assert _load_scene("p1", "scene_002") is None


class TestDeriveActPosition:
    def test_first_third(self):
        scenes = [_scene(f"scene_{i:03d}") for i in range(1, 7)]
        assert _derive_act_position(_scene("scene_001"), scenes) == "act_1"

    def test_second_third(self):
        scenes = [_scene(f"scene_{i:03d}") for i in range(1, 7)]
        assert _derive_act_position(_scene("scene_003"), scenes) == "act_2"

    def test_last_third(self):
        scenes = [_scene(f"scene_{i:03d}") for i in range(1, 7)]
        assert _derive_act_position(_scene("scene_006"), scenes) == "act_3"

    def test_unknown_when_missing(self):
        assert _derive_act_position(_scene("scene_001"), []) == "unknown"


class TestBuildContext:
    def test_includes_description_and_emotional_target(self):
        scene = _scene("scene_001", emotional_tone="tense", characters=["Elena", "Marcus"])
        result = _build_context(scene, [_scene("scene_001")])
        assert "Description for scene_001" in result
        assert "tense" in result
        assert "Elena" in result
        assert "Marcus" in result

    def test_falls_back_to_neutral_when_no_emotional_target(self):
        scene = _scene("scene_001")
        del scene["emotional_tone"]
        result = _build_context(scene, [_scene("scene_001")])
        assert "neutral" in result


class TestGenerateSceneAudioBrief:
    @patch("app.services.audio_director_service.call_llm", new_callable=AsyncMock)
    async def test_returns_sound_advisory(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "mood": "tense",
            "score_notes": "Low strings with a ticking clock.",
            "ambient_notes": "Rain on glass, distant siren.",
            "silence_flag": False,
            "tempo": "medium",
            "instrumentation": ["cello", "piano", "percussion"],
        })

        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            result = await generate_scene_audio_brief("p1", "scene_001", None)

        assert isinstance(result, SoundAdvisory)
        assert result.mood == "tense"
        assert "Low strings" in result.score_notes
        assert "Rain" in result.ambient_notes
        assert result.silence_flag is False

    @patch("app.services.audio_director_service.call_llm", new_callable=AsyncMock)
    async def test_ignores_extra_fields_from_llm(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "mood": "melancholic",
            "score_notes": "Solo violin over distant ocean.",
            "ambient_notes": "Waves, gull cries.",
            "silence_flag": True,
            "tempo": "slow",
            "instrumentation": ["violin", "string pad"],
        })

        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            result = await generate_scene_audio_brief("p1", "scene_001", None)

        assert result.mood == "melancholic"
        with pytest.raises(AttributeError):
            _ = result.tempo

    async def test_raises_404_when_scene_missing(self):
        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            with pytest.raises(Exception) as exc_info:
                await generate_scene_audio_brief("p1", "scene_002", None)
            assert exc_info.value.status_code == 404

    @patch("app.services.audio_director_service.call_llm", new_callable=AsyncMock)
    async def test_raises_500_on_llm_failure(self, mock_llm):
        mock_llm.side_effect = RuntimeError("Groq down")

        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            with pytest.raises(Exception) as exc_info:
                await generate_scene_audio_brief("p1", "scene_001", None)
            assert exc_info.value.status_code == 500

    @patch("app.services.audio_director_service.call_llm", new_callable=AsyncMock)
    async def test_raises_500_on_bad_json(self, mock_llm):
        mock_llm.return_value = "Not valid JSON"

        with patch("app.services.audio_director_service.project_store") as mock_store:
            mock_store.get_project.return_value = _project("p1", [_scene("scene_001")])
            with pytest.raises(Exception) as exc_info:
                await generate_scene_audio_brief("p1", "scene_001", None)
            assert exc_info.value.status_code == 500
