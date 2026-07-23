"""Tests for ElevenLabs voice resolution with per-project DB assignment.

Tests the updated resolution order:
1. Per-project DB assignment (characters.elevenlabs_voice_id)
2. ELEVENLABS_VOICE_MAP_JSON exact character match
3. ELEVENLABS_VOICE_MAP_JSON "default" entry
4. ELEVENLABS_DEFAULT_VOICE_ID env var

All DB operations use a temporary SQLite database — no real credits spent.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services import audio_pipeline_service as aps
from app.services.audio_pipeline_service import _resolve_cosyvoice_voice_id, _resolve_elevenlabs_voice_id
from app.data.storage import DatabaseStorage


@pytest.fixture
def temp_storage(tmp_path: Path, monkeypatch) -> DatabaseStorage:
    """Create a fresh SQLite storage instance in a temp directory.

    Patches ``get_storage`` so that ``_resolve_elevenlabs_voice_id`` uses
    this temp DB instead of the live one.
    """
    db_dir = tmp_path / "test_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    storage = DatabaseStorage(str(db_dir))
    monkeypatch.setattr("app.data.storage.get_storage", lambda *a, **kw: storage)
    return storage


@pytest.fixture
def isolated_env(monkeypatch):
    """Clear all ElevenLabs env vars for deterministic tests."""
    monkeypatch.delenv("ELEVENLABS_VOICE_MAP_JSON", raising=False)
    monkeypatch.delenv("ELEVENLABS_DEFAULT_VOICE_ID", raising=False)
    monkeypatch.setattr(aps, "ELEVENLABS_DEFAULT_VOICE_ID", "fallbackVoiceId")
    yield monkeypatch


class TestVoiceResolutionDbFirst:
    """Verify DB assignment takes priority over env-var fallbacks."""

    def test_db_assignment_wins_over_env_map(self, temp_storage, isolated_env):
        """When a character has a DB voice_id, it takes priority over ELEVENLABS_VOICE_MAP_JSON."""
        isolated_env.setenv(
            "ELEVENLABS_VOICE_MAP_JSON",
            '{"MARA": "envMaraVoice", "default": "envDefaultVoice"}',
        )
        temp_storage.save_character("proj-1", "MARA", {
            "elevenlabs_voice_id": "dbMaraVoice",
            "elevenlabs_voice_name": "Rachel",
        })
        result = _resolve_elevenlabs_voice_id("MARA", project_id="proj-1")
        assert result == "dbMaraVoice"

    def test_db_assignment_wins_over_env_default(self, temp_storage, isolated_env):
        """When a character has a DB voice_id, it takes priority over ELEVENLABS_DEFAULT_VOICE_ID."""
        isolated_env.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefaultVoice")
        temp_storage.save_character("proj-1", "ELI", {
            "elevenlabs_voice_id": "dbEliVoice",
        })
        result = _resolve_elevenlabs_voice_id("ELI", project_id="proj-1")
        assert result == "dbEliVoice"

    def test_falls_back_to_env_map_when_no_db_assignment(self, temp_storage, isolated_env):
        """When no DB assignment exists, fall back to ELEVENLABS_VOICE_MAP_JSON."""
        isolated_env.setenv(
            "ELEVENLABS_VOICE_MAP_JSON",
            '{"DRE": "envDreVoice", "default": "envDefaultVoice"}',
        )
        temp_storage.save_character("proj-1", "DRE", {})
        result = _resolve_elevenlabs_voice_id("DRE", project_id="proj-1")
        assert result == "envDreVoice"

    def test_falls_back_to_env_default_when_no_db_and_no_map(self, temp_storage, isolated_env):
        """When no DB assignment and no voice map, fall back to ELEVENLABS_DEFAULT_VOICE_ID."""
        isolated_env.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefaultVoice")
        temp_storage.save_character("proj-1", "CHILD", {})
        result = _resolve_elevenlabs_voice_id("CHILD", project_id="proj-1")
        assert result == "envDefaultVoice"

    def test_falls_back_to_map_default_for_unknown_character(self, temp_storage, isolated_env):
        """Unknown character with no DB record falls to voice map 'default'."""
        isolated_env.setenv(
            "ELEVENLABS_VOICE_MAP_JSON",
            '{"DRE": "envDreVoice", "default": "envDefaultVoice"}',
        )
        result = _resolve_elevenlabs_voice_id("UNKNOWN", project_id="proj-1")
        assert result == "envDefaultVoice"

    def test_no_project_id_skips_db_lookup(self, temp_storage, isolated_env):
        """When project_id is None, DB lookup is skipped (backward compat)."""
        isolated_env.setenv(
            "ELEVENLABS_VOICE_MAP_JSON",
            '{"DRE": "envDreVoice", "default": "envDefaultVoice"}',
        )
        temp_storage.save_character("proj-1", "DRE", {
            "elevenlabs_voice_id": "dbDreVoice",
        })
        result = _resolve_elevenlabs_voice_id("DRE")
        assert result == "envDreVoice"

    def test_empty_db_voice_id_falls_through(self, temp_storage, isolated_env):
        """A character record with empty voice_id does not block fallback."""
        isolated_env.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefaultVoice")
        temp_storage.save_character("proj-1", "MARA", {})
        result = _resolve_elevenlabs_voice_id("MARA", project_id="proj-1")
        assert result == "envDefaultVoice"

    def test_db_lookup_case_sensitive_name(self, temp_storage, isolated_env):
        """Character names in the DB are matched as-is (case-sensitive)."""
        isolated_env.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefaultVoice")
        temp_storage.save_character("proj-1", "MARA", {
            "elevenlabs_voice_id": "dbMaraVoice",
        })
        result_upper = _resolve_elevenlabs_voice_id("MARA", project_id="proj-1")
        assert result_upper == "dbMaraVoice"

    def test_per_project_isolation(self, temp_storage, isolated_env):
        """Voice assignments are per-project — same character name, different projects."""
        isolated_env.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefaultVoice")
        temp_storage.save_character("proj-a", "MARA", {
            "elevenlabs_voice_id": "voiceA",
        })
        temp_storage.save_character("proj-b", "MARA", {
            "elevenlabs_voice_id": "voiceB",
        })
        assert _resolve_elevenlabs_voice_id("MARA", project_id="proj-a") == "voiceA"
        assert _resolve_elevenlabs_voice_id("MARA", project_id="proj-b") == "voiceB"

    def test_raises_when_nothing_configured(self, temp_storage, isolated_env):
        """When no DB assignment, no voice map, and no default — raises ValueError."""
        isolated_env.delenv("ELEVENLABS_DEFAULT_VOICE_ID", raising=False)
        isolated_env.setattr(aps, "ELEVENLABS_DEFAULT_VOICE_ID", "")
        temp_storage.save_character("proj-1", "MARA", {})
        with pytest.raises(ValueError, match="No ElevenLabs voice ID configured"):
            _resolve_elevenlabs_voice_id("MARA", project_id="proj-1")


class TestStorageVoiceMethods:
    """Verify storage-level voice assignment methods."""

    def test_set_and_get_voice_by_name(self, temp_storage):
        """set_character_voice persists, get_character_voice_by_name retrieves."""
        created = temp_storage.save_character("proj-1", "MARA", {})
        char_id = created["id"]
        updated = temp_storage.set_character_voice(char_id, "proj-1", "v123", "Rachel")
        assert updated is not None
        assert updated["elevenlabs_voice_id"] == "v123"
        assert updated["elevenlabs_voice_name"] == "Rachel"
        retrieved = temp_storage.get_character_voice_by_name("proj-1", "MARA")
        assert retrieved == "v123"

    def test_clear_voice_assignment(self, temp_storage):
        """Setting voice_id to empty string clears the assignment."""
        created = temp_storage.save_character("proj-1", "ELI", {})
        char_id = created["id"]
        temp_storage.set_character_voice(char_id, "proj-1", "v456", "Adam")
        assert temp_storage.get_character_voice_by_name("proj-1", "ELI") == "v456"
        temp_storage.set_character_voice(char_id, "proj-1", "", "")
        assert temp_storage.get_character_voice_by_name("proj-1", "ELI") is None

    def test_get_voice_returns_none_for_unassigned(self, temp_storage):
        """get_character_voice_by_name returns None for a character with no voice."""
        temp_storage.save_character("proj-1", "CHILD", {})
        assert temp_storage.get_character_voice_by_name("proj-1", "CHILD") is None

    def test_get_voice_returns_none_for_nonexistent_character(self, temp_storage):
        """get_character_voice_by_name returns None for a character that doesn't exist."""
        assert temp_storage.get_character_voice_by_name("proj-1", "GHOST") is None

    def test_set_voice_nonexistent_character_returns_none(self, temp_storage):
        """set_character_voice returns None when the character doesn't exist."""
        result = temp_storage.set_character_voice("fake-id", "proj-1", "v789", "Test")
        assert result is None

    def test_save_character_preserves_voice_on_partial_update(self, temp_storage):
        """Saving a character with other fields but no voice_id preserves the existing voice."""
        created = temp_storage.save_character("proj-1", "MARA", {
            "elevenlabs_voice_id": "v123",
            "elevenlabs_voice_name": "Rachel",
        })
        char_id = created["id"]
        updated = temp_storage.save_character("proj-1", "MARA", {
            "look": "New look description",
        })
        assert updated["elevenlabs_voice_id"] == "v123"
        assert updated["elevenlabs_voice_name"] == "Rachel"
        assert updated["look"] == "New look description"


class TestProviderAwareCastingResolution:
    """Verify Casting assignments feed CosyVoice voice resolution."""

    def test_cosyvoice_casting_assignment_wins_over_env_default(self, temp_storage, monkeypatch):
        monkeypatch.setenv("COSYVOICE_DEFAULT_VOICE", "Cherry")
        created = temp_storage.save_character("proj-1", "DRE", {})
        temp_storage.set_character_voice_casting(
            created["id"],
            "proj-1",
            provider="cosyvoice",
            voice_id="cosyvoice-dre-clone-001",
            voice_name="Dre clone",
            source_type="clone",
            style_prompt="warm, guarded Chicago cadence",
        )

        result = _resolve_cosyvoice_voice_id("DRE", project_id="proj-1")

        assert result == "cosyvoice-dre-clone-001"

    def test_cosyvoice_resolution_ignores_other_provider_casting(self, temp_storage, monkeypatch):
        monkeypatch.setenv("COSYVOICE_DEFAULT_VOICE", "Cherry")
        created = temp_storage.save_character("proj-1", "DRE", {})
        temp_storage.set_character_voice_casting(
            created["id"],
            "proj-1",
            provider="fish_audio",
            voice_id="fish-dre-voice",
            voice_name="Dre Fish",
        )

        result = _resolve_cosyvoice_voice_id("DRE", project_id="proj-1")

        assert result == "Cherry"

    def test_set_and_get_provider_aware_casting_by_name(self, temp_storage):
        created = temp_storage.save_character("proj-1", "MAYA", {})
        temp_storage.set_character_voice_casting(
            created["id"],
            "proj-1",
            provider="cosyvoice",
            voice_id="qwen-designed-maya",
            voice_name="Maya designed voice",
            source_type="voice_design",
            style_prompt="steady but carrying dread",
        )

        casting = temp_storage.get_character_voice_casting_by_name(
            "proj-1",
            "MAYA",
            provider="cosyvoice",
        )

        assert casting == {
            "voice_provider": "cosyvoice",
            "voice_id": "qwen-designed-maya",
            "voice_name": "Maya designed voice",
            "voice_source_type": "voice_design",
            "voice_style_prompt": "steady but carrying dread",
        }
