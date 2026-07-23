"""Tests for ElevenLabs + Fish Audio dialogue TTS provider selection and text chunking.

Mirrors the pattern in test_audio_score_provider_selection.py:
  * Provider normalisation and validation
  * Per-call provider override dispatch
  * Silent fallback to Piper on provider failure (when failover enabled)
  * Re-raise on provider failure when failover disabled
  * Character-chunking logic (2,500-char free-tier cap)
  * Voice ID resolution
  * Fish Audio emotion-tag delimiter selection (S2 brackets vs S1 parentheses)
  * Fish Audio model validation at import time

All API calls are mocked — these tests never spend real credits.
"""
from __future__ import annotations

import os
import struct
import threading
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import audio_pipeline_service as aps
from app.routes import audio as audio_route
from app.data.storage import DatabaseStorage
from app.services.audio import cosyvoice_tts_service as cosyvoice_module
from app.services.audio.cosyvoice_tts_service import CosyVoiceTTSService
from app.services.audio_pipeline_service import (
    AudioPipelineService,
    TrackStatus,
    _build_dialogue_instruction,
    _cosyvoice_fixed_instruction,
    _cosyvoice_voice_instruction_mode,
    _dialogue_instruction_sources,
    _dialogue_tts_text,
    _fish_audio_emotion_delimiters,
    _normalize_dialogue_provider,
    _normalize_score_ambient_provider,
    _resolve_cosyvoice_voice_id,
    _resolve_elevenlabs_voice_id,
    _resolve_fish_audio_voice_id,
    _split_text_for_elevenlabs,
    _write_silence_wav,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _write_tone_wav(path: Path, duration: float = 0.2, sample_rate: int = 22050) -> None:
    """Write a minimal valid WAV with a non-silent tone."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x01\x00" * frames)


@pytest.fixture
def service(tmp_path: Path) -> AudioPipelineService:
    svc = AudioPipelineService()
    svc.output_base = tmp_path / "audio"
    svc.output_base.mkdir(parents=True, exist_ok=True)
    return svc


@pytest.fixture
def temp_storage(tmp_path: Path, monkeypatch) -> DatabaseStorage:
    db_dir = tmp_path / "test_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    storage = DatabaseStorage(str(db_dir))
    monkeypatch.setattr("app.data.storage.get_storage", lambda *a, **kw: storage)
    return storage


@pytest.fixture
def fake_piper(monkeypatch):
    """Stub Piper TTS to write a valid WAV instantly."""
    def _fake_piper_sync(self, text, output_path, voice=None):
        _write_tone_wav(output_path, duration=0.2)
    monkeypatch.setattr(AudioPipelineService, "_generate_piper_tts_sync", _fake_piper_sync)
    return _fake_piper_sync


@pytest.fixture
def fake_elevenlabs(monkeypatch):
    """Stub ElevenLabs TTS to write a valid WAV (via normalise) instantly."""
    def _fake_elevenlabs_sync(self, text, output_path, voice=None, character=None, project_id=None):
        _write_tone_wav(output_path, duration=0.2)
    monkeypatch.setattr(
        AudioPipelineService, "_generate_elevenlabs_tts_sync", _fake_elevenlabs_sync
    )
    return _fake_elevenlabs_sync


# ─── Provider normalisation ──────────────────────────────────────────────────


class TestDialogueProviderNormalisation:
    def test_default_is_cosyvoice(self):
        assert _normalize_dialogue_provider(None) == "cosyvoice"

    def test_elevenlabs_alias(self):
        assert _normalize_dialogue_provider("eleven") == "elevenlabs"
        assert _normalize_dialogue_provider("eleven_labs") == "elevenlabs"
        assert _normalize_dialogue_provider("eleven-labs") == "elevenlabs"

    def test_piper_alias(self):
        assert _normalize_dialogue_provider("piper-tts") == "piper"

    def test_auto_is_valid(self):
        assert _normalize_dialogue_provider("auto") == "auto"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="AUDIO_DIALOGUE_PROVIDER"):
            _normalize_dialogue_provider("azure")

    def test_case_insensitive(self):
        assert _normalize_dialogue_provider("ELEVENLABS") == "elevenlabs"
        assert _normalize_dialogue_provider("Piper") == "piper"


class TestScoreAmbientProviderNormalisation:
    def test_default_is_none(self):
        assert _normalize_score_ambient_provider(None) == "none"

    def test_aliases(self):
        assert _normalize_score_ambient_provider("off") == "none"
        assert _normalize_score_ambient_provider("disabled") == "none"
        assert _normalize_score_ambient_provider("no-provider") == "none"
        assert _normalize_score_ambient_provider("ace-step") == "ace_step"
        assert _normalize_score_ambient_provider("acestep") == "ace_step"
        assert _normalize_score_ambient_provider("musicgen-small") == "musicgen"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="AUDIO_SCORE_PROVIDER"):
            _normalize_score_ambient_provider("stable_audio")


# ─── Provider dispatch via _generate_dialogue_tts_sync ──────────────────────


class TestDialogueProviderDispatch:
    """The dispatch method selects the right provider and handles fallback."""

    def test_piper_calls_piper(self, service, fake_piper, tmp_path):
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="piper")
        assert out.exists()
        assert out.stat().st_size > 44

    def test_elevenlabs_calls_elevenlabs(
        self, service, fake_elevenlabs, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", True)
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="elevenlabs")
        assert out.exists()

    def test_elevenlabs_failover_to_piper_on_error(
        self, service, fake_piper, monkeypatch, tmp_path
    ):
        """When ELEVENLABS_FAILOVER_TO_PIPER is True, ElevenLabs failure
        silently falls back to Piper."""
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_FAILOVER_TO_PIPER", True)
        monkeypatch.setattr(aps, "PIPER_AVAILABLE", True)

        def _failing_elevenlabs(self, text, output_path, voice=None, character=None, project_id=None):
            raise RuntimeError("ElevenLabs API error: 401")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_elevenlabs_tts_sync", _failing_elevenlabs
        )

        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="elevenlabs")
        assert out.exists(), "Piper fallback should have written a WAV"

    def test_elevenlabs_no_failover_re_raises(
        self, service, monkeypatch, tmp_path
    ):
        """When ELEVENLABS_FAILOVER_TO_PIPER is False (default), ElevenLabs
        failure re-raises so the caller writes silence."""
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_FAILOVER_TO_PIPER", False)

        def _failing_elevenlabs(self, text, output_path, voice=None, character=None, project_id=None):
            raise RuntimeError("ElevenLabs API error: 402 payment required")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_elevenlabs_tts_sync", _failing_elevenlabs
        )

        out = tmp_path / "out.wav"
        with pytest.raises(RuntimeError, match="402"):
            service._generate_dialogue_tts_sync("hello", out, provider="elevenlabs")

    def test_auto_uses_elevenlabs_when_configured(
        self, service, fake_elevenlabs, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", True)
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="auto")
        assert out.exists()

    def test_auto_uses_piper_when_not_configured(
        self, service, fake_piper, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "")
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", False)
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="auto")
        assert out.exists()


# ─── Text chunking for 2,500-char free-tier cap ──────────────────────────────


class TestTextChunking:
    def test_short_text_returns_single_chunk(self):
        chunks = _split_text_for_elevenlabs("Hello world.", char_limit=2500)
        assert chunks == ["Hello world."]

    def test_exact_limit_returns_single_chunk(self):
        text = "a" * 2500
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_over_limit_splits(self):
        text = "a" * 2501
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert len(chunks) == 2
        assert all(len(c) <= 2500 for c in chunks)
        assert "".join(c.replace(" ", "") for c in chunks).replace(" ", "") == text

    def test_splits_at_sentence_boundary(self):
        # Build text that exceeds 2500 chars with a sentence boundary inside.
        sentence1 = "This is a long sentence. " + ("word " * 600).strip() + "."
        sentence2 = "Second sentence here."
        text = sentence1 + " " + sentence2
        assert len(text) > 2500, "test text must exceed the limit"
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert len(chunks) >= 2
        assert all(len(c) <= 2500 for c in chunks)
        # First chunk should end at a sentence boundary, not mid-word.
        assert chunks[0].rstrip().endswith(".") or chunks[0].rstrip().endswith(". ")

    def test_splits_at_comma_when_no_sentence_boundary(self):
        text = "word, " * 600 + "final word"
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert len(chunks) >= 2
        assert all(len(c) <= 2500 for c in chunks)

    def test_hard_split_when_no_boundary_found(self):
        # One continuous string with no spaces or punctuation.
        text = "x" * 5000
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert len(chunks) == 2
        assert all(len(c) <= 2500 for c in chunks)
        assert "".join(chunks) == text

    def test_no_truncation_all_text_preserved(self):
        long_text = ". ".join(f"Sentence number {i}" for i in range(500))
        chunks = _split_text_for_elevenlabs(long_text, char_limit=2500)
        assert all(len(c) <= 2500 for c in chunks)
        # Every word from the original must appear in the chunks.
        reconstructed = " ".join(chunks)
        for word in long_text.split():
            assert word in reconstructed

    def test_empty_chunks_filtered(self):
        text = "Short. " + " " * 3000 + "End."
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert all(c.strip() for c in chunks)

    def test_multiline_splits_at_newline(self):
        line1 = "x" * 2000
        line2 = "y" * 2000
        text = line1 + "\n" + line2
        chunks = _split_text_for_elevenlabs(text, char_limit=2500)
        assert len(chunks) == 2
        assert chunks[0].strip() == line1
        assert chunks[1].strip() == line2


# ─── Voice ID resolution ─────────────────────────────────────────────────────


class TestVoiceIdResolution:
    def test_default_voice_from_env(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "myVoice123")
        monkeypatch.delenv("ELEVENLABS_VOICE_MAP_JSON", raising=False)
        assert _resolve_elevenlabs_voice_id() == "myVoice123"

    def test_character_match_from_voice_map(self, monkeypatch):
        monkeypatch.setenv(
            "ELEVENLABS_VOICE_MAP_JSON",
            '{"DRE": "dreVoiceId", "MAYA": "mayaVoiceId", "default": "fallbackVoiceId"}',
        )
        monkeypatch.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_elevenlabs_voice_id("DRE") == "dreVoiceId"
        assert _resolve_elevenlabs_voice_id("maya") == "mayaVoiceId"

    def test_default_from_voice_map_when_no_character_match(self, monkeypatch):
        monkeypatch.setenv(
            "ELEVENLABS_VOICE_MAP_JSON",
            '{"DRE": "dreVoiceId", "default": "fallbackVoiceId"}',
        )
        monkeypatch.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_elevenlabs_voice_id("UNKNOWN_CHAR") == "fallbackVoiceId"

    def test_falls_back_to_env_default_when_voice_map_has_no_default(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_VOICE_MAP_JSON", '{"DRE": "dreVoiceId"}')
        monkeypatch.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_elevenlabs_voice_id("UNKNOWN_CHAR") == "envDefault"

    def test_raises_when_no_voice_configured(self, monkeypatch):
        monkeypatch.delenv("ELEVENLABS_DEFAULT_VOICE_ID", raising=False)
        monkeypatch.delenv("ELEVENLABS_VOICE_MAP_JSON", raising=False)
        monkeypatch.setattr(aps, "ELEVENLABS_DEFAULT_VOICE_ID", "")
        with pytest.raises(ValueError, match="No ElevenLabs voice ID configured"):
            _resolve_elevenlabs_voice_id()

    def test_invalid_voice_map_json_falls_back_to_env_default(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_VOICE_MAP_JSON", "{invalid json}")
        monkeypatch.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_elevenlabs_voice_id("DRE") == "envDefault"


# ─── Integration: generate_shot_dialogue with provider override ──────────────


class TestShotDialogueWithProvider:
    """generate_shot_dialogue accepts a provider override and dispatches."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            aps.audio_pipeline_service, "output_base", tmp_path / "audio"
        )

    @pytest.mark.asyncio
    async def test_shot_dialogue_with_elevenlabs_provider(
        self, fake_elevenlabs, monkeypatch
    ):
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", True)

        dialogue_lines = [
            {"character": "DRE", "text": "I remember the way the light fell."},
            {"character": "MAYA", "text": "So do I."},
        ]
        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_001",
            shot_id="shot_001",
            dialogue_lines=dialogue_lines,
            provider="elevenlabs",
        )
        assert result["status"] == TrackStatus.COMPLETE
        assert result["lines_generated"] == 2
        assert result["file_path"] is not None
        assert os.path.exists(result["file_path"])

    @pytest.mark.asyncio
    async def test_shot_dialogue_default_uses_cosyvoice(self, fake_cosyvoice, monkeypatch):
        """Without a provider override, default dialogue now uses CosyVoice."""
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", True)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        monkeypatch.setattr(aps, "DIALOGUE_PROVIDER", "cosyvoice")

        dialogue_lines = [{"character": "DRE", "text": "Hello."}]
        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_001",
            shot_id="shot_001",
            dialogue_lines=dialogue_lines,
        )
        assert result["status"] == TrackStatus.COMPLETE
        assert result["provider"] == "cosyvoice"


# ─── Capabilities report ─────────────────────────────────────────────────────


class TestCapabilitiesReport:
    def test_capabilities_includes_elevenlabs_fields(self):
        caps = AudioPipelineService.capabilities()
        assert "dialogue_tts_provider" in caps
        assert "elevenlabs_configured" in caps
        assert "valid_dialogue_providers" in caps
        assert "elevenlabs" in caps["valid_dialogue_providers"]
        assert "piper" in caps["valid_dialogue_providers"]

    def test_capabilities_default_provider_is_cosyvoice(self, monkeypatch):
        monkeypatch.setattr(aps, "DIALOGUE_PROVIDER", "cosyvoice")
        monkeypatch.setattr(aps, "SCORE_AMBIENT_PROVIDER", "none")
        caps = AudioPipelineService.capabilities()
        assert caps["dialogue_tts_provider"] == "cosyvoice"
        assert caps["score_ambient_provider"] == "none"

    def test_capabilities_includes_fish_audio_fields(self):
        caps = AudioPipelineService.capabilities()
        assert "fish_audio_configured" in caps
        assert "fish_audio_model" in caps
        assert "fish_audio_failover_to_piper" in caps
        assert "valid_fish_audio_models" in caps
        assert "fish_audio" in caps["valid_dialogue_providers"]

    def test_capabilities_includes_cosyvoice_fields(self):
        caps = AudioPipelineService.capabilities()
        assert "cosyvoice_configured" in caps
        assert "cosyvoice_model" in caps
        assert "cosyvoice_failover_to_piper" in caps
        assert "cosyvoice" in caps["valid_dialogue_providers"]
        assert "elevenlabs" in caps["valid_dialogue_providers"]


# ─── Fish Audio provider normalisation ───────────────────────────────────────


class TestFishAudioProviderNormalisation:
    def test_fish_audio_alias(self):
        assert _normalize_dialogue_provider("fish") == "fish_audio"
        assert _normalize_dialogue_provider("fishaudio") == "fish_audio"
        assert _normalize_dialogue_provider("fish-audio") == "fish_audio"

    def test_fish_audio_case_insensitive(self):
        assert _normalize_dialogue_provider("Fish_Audio") == "fish_audio"
        assert _normalize_dialogue_provider("FISH") == "fish_audio"

    def test_fish_audio_in_valid_set(self):
        assert "fish_audio" in aps.VALID_DIALOGUE_PROVIDERS


# ─── Fish Audio emotion-tag delimiters ───────────────────────────────────────


class TestFishAudioEmotionDelimiters:
    def test_s2_pro_uses_brackets(self):
        assert _fish_audio_emotion_delimiters("s2-pro") == ("[", "]")

    def test_s2_1_pro_uses_brackets(self):
        assert _fish_audio_emotion_delimiters("s2.1-pro") == ("[", "]")

    def test_s2_1_pro_free_uses_brackets(self):
        assert _fish_audio_emotion_delimiters("s2.1-pro-free") == ("[", "]")

    def test_s1_uses_parentheses(self):
        assert _fish_audio_emotion_delimiters("s1") == ("(", ")")

    def test_unknown_model_defaults_to_brackets(self):
        assert _fish_audio_emotion_delimiters("unknown") == ("[", "]")


# ─── Fish Audio model validation ─────────────────────────────────────────────


class TestFishAudioModelValidation:
    def test_valid_models_set(self):
        assert "s1" in aps.VALID_FISH_AUDIO_MODELS
        assert "s2-pro" in aps.VALID_FISH_AUDIO_MODELS
        assert "s2.1-pro" in aps.VALID_FISH_AUDIO_MODELS
        assert "s2.1-pro-free" in aps.VALID_FISH_AUDIO_MODELS

    def test_default_model_is_s2_pro(self):
        assert aps.FISH_AUDIO_MODEL == "s2-pro"


# ─── Fish Audio voice ID resolution ──────────────────────────────────────────


class TestFishAudioVoiceIdResolution:
    def test_default_voice_from_env(self, monkeypatch):
        monkeypatch.setenv("FISH_AUDIO_DEFAULT_VOICE_ID", "abc123def")
        monkeypatch.delenv("FISH_AUDIO_VOICE_MAP_JSON", raising=False)
        assert _resolve_fish_audio_voice_id() == "abc123def"

    def test_character_match_from_voice_map(self, monkeypatch):
        monkeypatch.setenv(
            "FISH_AUDIO_VOICE_MAP_JSON",
            '{"DRE": "dreVoiceId", "MAYA": "mayaVoiceId", "default": "fallbackVoiceId"}',
        )
        monkeypatch.setenv("FISH_AUDIO_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_fish_audio_voice_id("DRE") == "dreVoiceId"
        assert _resolve_fish_audio_voice_id("maya") == "mayaVoiceId"

    def test_default_from_voice_map_when_no_character_match(self, monkeypatch):
        monkeypatch.setenv(
            "FISH_AUDIO_VOICE_MAP_JSON",
            '{"DRE": "dreVoiceId", "default": "fallbackVoiceId"}',
        )
        monkeypatch.setenv("FISH_AUDIO_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_fish_audio_voice_id("UNKNOWN_CHAR") == "fallbackVoiceId"

    def test_falls_back_to_env_default_when_voice_map_has_no_default(self, monkeypatch):
        monkeypatch.setenv("FISH_AUDIO_VOICE_MAP_JSON", '{"DRE": "dreVoiceId"}')
        monkeypatch.setenv("FISH_AUDIO_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_fish_audio_voice_id("UNKNOWN_CHAR") == "envDefault"

    def test_raises_when_no_voice_configured(self, monkeypatch):
        monkeypatch.delenv("FISH_AUDIO_DEFAULT_VOICE_ID", raising=False)
        monkeypatch.delenv("FISH_AUDIO_VOICE_MAP_JSON", raising=False)
        with pytest.raises(ValueError, match="No Fish Audio voice ID configured"):
            _resolve_fish_audio_voice_id()

    def test_invalid_voice_map_json_falls_back_to_env_default(self, monkeypatch):
        monkeypatch.setenv("FISH_AUDIO_VOICE_MAP_JSON", "{invalid json}")
        monkeypatch.setenv("FISH_AUDIO_DEFAULT_VOICE_ID", "envDefault")
        assert _resolve_fish_audio_voice_id("DRE") == "envDefault"


# ─── Fish Audio provider dispatch via _generate_dialogue_tts_sync ────────────


@pytest.fixture
def fake_fish_audio(monkeypatch):
    """Stub Fish Audio TTS to write a valid WAV instantly."""
    def _fake_fish_audio_sync(
        self, text, output_path, voice=None, character=None,
        project_id=None, emotion_tag=None,
    ):
        _write_tone_wav(output_path, duration=0.2)
    monkeypatch.setattr(
        AudioPipelineService, "_generate_fish_audio_tts_sync", _fake_fish_audio_sync
    )
    return _fake_fish_audio_sync


class TestFishAudioProviderDispatch:
    """The dispatch method selects Fish Audio and handles fallback."""

    def test_fish_audio_calls_fish_audio(
        self, service, fake_fish_audio, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "FISH_AUDIO_API_KEY", "test-key")
        monkeypatch.setattr(aps, "FISH_AUDIO_CONFIGURED", True)
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="fish_audio")
        assert out.exists()

    def test_fish_audio_failover_to_piper_on_error(
        self, service, fake_piper, monkeypatch, tmp_path
    ):
        """When FISH_AUDIO_FAILOVER_TO_PIPER is True, Fish Audio failure
        silently falls back to Piper."""
        monkeypatch.setattr(aps, "FISH_AUDIO_API_KEY", "test-key")
        monkeypatch.setattr(aps, "FISH_AUDIO_FAILOVER_TO_PIPER", True)
        monkeypatch.setattr(aps, "PIPER_AVAILABLE", True)

        def _failing_fish_audio(
            self, text, output_path, voice=None, character=None,
            project_id=None, emotion_tag=None,
        ):
            raise RuntimeError("Fish Audio API error: 401")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_fish_audio_tts_sync", _failing_fish_audio
        )

        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="fish_audio")
        assert out.exists(), "Piper fallback should have written a WAV"

    def test_fish_audio_no_failover_re_raises(
        self, service, monkeypatch, tmp_path
    ):
        """When FISH_AUDIO_FAILOVER_TO_PIPER is False (default), Fish Audio
        failure re-raises so the caller writes silence."""
        monkeypatch.setattr(aps, "FISH_AUDIO_API_KEY", "test-key")
        monkeypatch.setattr(aps, "FISH_AUDIO_FAILOVER_TO_PIPER", False)

        def _failing_fish_audio(
            self, text, output_path, voice=None, character=None,
            project_id=None, emotion_tag=None,
        ):
            raise RuntimeError("Fish Audio API error: 402 payment required")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_fish_audio_tts_sync", _failing_fish_audio
        )

        out = tmp_path / "out.wav"
        with pytest.raises(RuntimeError, match="402"):
            service._generate_dialogue_tts_sync("hello", out, provider="fish_audio")

    def test_fish_audio_passes_emotion_tag(
        self, service, monkeypatch, tmp_path
    ):
        """emotion_tag is forwarded from dispatch to the provider method."""
        monkeypatch.setattr(aps, "FISH_AUDIO_API_KEY", "test-key")
        monkeypatch.setattr(aps, "FISH_AUDIO_CONFIGURED", True)

        captured: dict = {}

        def _capturing_fish_audio(
            self, text, output_path, voice=None, character=None,
            project_id=None, emotion_tag=None,
        ):
            captured["emotion_tag"] = emotion_tag
            _write_tone_wav(output_path, duration=0.2)

        monkeypatch.setattr(
            AudioPipelineService, "_generate_fish_audio_tts_sync", _capturing_fish_audio
        )

        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync(
            "hello", out, provider="fish_audio", emotion_tag="angry",
        )
        assert captured["emotion_tag"] == "angry"

    def test_fish_audio_emotion_tag_defaults_to_none(
        self, service, monkeypatch, tmp_path
    ):
        """When no emotion_tag is passed, it defaults to None."""
        monkeypatch.setattr(aps, "FISH_AUDIO_API_KEY", "test-key")
        monkeypatch.setattr(aps, "FISH_AUDIO_CONFIGURED", True)

        captured: dict = {}

        def _capturing_fish_audio(
            self, text, output_path, voice=None, character=None,
            project_id=None, emotion_tag=None,
        ):
            captured["emotion_tag"] = emotion_tag
            _write_tone_wav(output_path, duration=0.2)

        monkeypatch.setattr(
            AudioPipelineService, "_generate_fish_audio_tts_sync", _capturing_fish_audio
        )

        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="fish_audio")
        assert captured["emotion_tag"] is None


# ─── CosyVoice / Qwen-TTS provider selection ────────────────────────────────


@pytest.fixture
def fake_cosyvoice(monkeypatch):
    """Stub CosyVoice TTS to write a valid WAV instantly."""
    def _fake_cosyvoice_sync(
        self, text, output_path, voice=None, character=None, project_id=None,
        instruction=None,
    ):
        _write_tone_wav(output_path, duration=0.2)
    monkeypatch.setattr(
        AudioPipelineService, "_generate_cosyvoice_tts_sync", _fake_cosyvoice_sync
    )
    return _fake_cosyvoice_sync


class TestCosyVoiceProviderNormalisation:
    def test_cosyvoice_aliases(self):
        assert _normalize_dialogue_provider("cosy") == "cosyvoice"
        assert _normalize_dialogue_provider("cosy_voice") == "cosyvoice"
        assert _normalize_dialogue_provider("cosy-voice") == "cosyvoice"
        assert _normalize_dialogue_provider("qwen") == "cosyvoice"
        assert _normalize_dialogue_provider("qwen_tts") == "cosyvoice"
        assert _normalize_dialogue_provider("qwen-tts") == "cosyvoice"

    def test_cosyvoice_case_insensitive(self):
        assert _normalize_dialogue_provider("CosyVoice") == "cosyvoice"
        assert _normalize_dialogue_provider("QWEN-TTS") == "cosyvoice"

    def test_cosyvoice_in_valid_set(self):
        assert "cosyvoice" in aps.VALID_DIALOGUE_PROVIDERS


class TestCosyVoiceVoiceIdResolution:
    def test_default_voice_from_env(self, monkeypatch):
        monkeypatch.setenv("COSYVOICE_DEFAULT_VOICE", "longxiaoxia")
        monkeypatch.delenv("COSYVOICE_VOICE_MAP_JSON", raising=False)
        assert _resolve_cosyvoice_voice_id() == "longxiaoxia"

    def test_character_match_from_voice_map(self, monkeypatch):
        monkeypatch.setenv(
            "COSYVOICE_VOICE_MAP_JSON",
            '{"DRE": "voice-dre", "MAYA": "voice-maya", "default": "voice-default"}',
        )
        monkeypatch.setenv("COSYVOICE_DEFAULT_VOICE", "envDefault")
        assert _resolve_cosyvoice_voice_id("DRE") == "voice-dre"
        assert _resolve_cosyvoice_voice_id("maya") == "voice-maya"

    def test_default_from_voice_map_when_no_character_match(self, monkeypatch):
        monkeypatch.setenv(
            "COSYVOICE_VOICE_MAP_JSON",
            '{"DRE": "voice-dre", "default": "voice-default"}',
        )
        monkeypatch.setenv("COSYVOICE_DEFAULT_VOICE", "envDefault")
        assert _resolve_cosyvoice_voice_id("UNKNOWN_CHAR") == "voice-default"


class TestCosyVoiceInstructionResolution:
    def test_qwen_instruct_model_uses_freeform_instructions(self):
        assert (
            _cosyvoice_voice_instruction_mode("qwen3-tts-instruct-flash", "Cherry")
            == "qwen_freeform"
        )

    def test_longanwen_system_voice_has_no_cosyvoice_instruct(self):
        assert (
            _cosyvoice_voice_instruction_mode("cosyvoice-v3-flash", "longanwen_v3")
            == "none"
        )

    def test_cosyvoice_v3_longanyang_uses_fixed_instruction(self):
        assert (
            _cosyvoice_voice_instruction_mode("cosyvoice-v3-flash", "longanyang")
            == "cosyvoice_fixed"
        )

    def test_cosyvoice_v3_longwanjun_has_no_instruction_support(self):
        assert (
            _cosyvoice_voice_instruction_mode("cosyvoice-v3-flash", "longwanjun_v3")
            == "none"
        )

    def test_builds_fixed_chinese_instruction_for_cosyvoice_v3_system_voice(self):
        instruction, mode = _build_dialogue_instruction(
            {
                "character": "DRE",
                "text": "I need you to understand something.",
                "emotional_subtext": "tense and controlled under betrayal",
            },
            model="cosyvoice-v3-flash",
            voice="longanyang",
            scene_context={"audio_tension": "betrayal at gunpoint"},
        )

        assert mode == "cosyvoice_fixed"
        assert instruction == _cosyvoice_fixed_instruction("sad")

    def test_builds_per_line_freeform_instruction(self):
        line = {
            "character": "DRE",
            "text": "You good?",
            "emotional_subtext": "concern breaking through normalcy",
            "pacing_tag": "held back",
        }
        scene_context = {"audio_tension": "low", "director_note": "Hold the tension in the pause."}
        instruction, mode = _build_dialogue_instruction(
            line,
            model="qwen3-tts-instruct-flash",
            voice="Cherry",
            scene_context=scene_context,
        )
        sources = _dialogue_instruction_sources(line, scene_context)
        assert mode == "qwen_freeform"
        assert instruction
        assert "DRE" in instruction
        assert "concern breaking through normalcy" in instruction
        assert "Hold the tension" in instruction
        assert sources["emotional_subtext"] == {
            "source": "line.emotional_subtext",
            "value": "concern breaking through normalcy",
        }
        assert sources["pacing_tag"] == {"source": "line.pacing_tag", "value": "held back"}
        assert sources["scene_pressure"] == {"source": "scene_context.audio_tension", "value": "low"}
        assert sources["director_note"] == {
            "source": "scene_context.director_note",
            "value": "Hold the tension in the pause.",
        }

    def test_cosyvoice_clone_instruction_is_compact_and_keeps_direction(self):
        instruction, mode = _build_dialogue_instruction(
            {
                "character": "DRE",
                "text": "I need you to understand something.",
                "emotional_subtext": (
                    "tense and controlled, trying to justify himself before he "
                    "has said the unforgivable part"
                ),
                "pacing_tag": "low, careful, held in the throat",
            },
            model="cosyvoice-v3-flash",
            voice="cosyvoice-v3-flash-dre002-example",
            scene_context={"audio_tension": "betrayal at gunpoint"},
        )

        assert mode == "cosyvoice_freeform"
        assert instruction
        assert len(instruction) <= 100
        assert "tense and controlled" in instruction
        assert "low, careful" in instruction
        assert "natural, restrained" in instruction

    def test_builds_inferred_instruction_for_extracted_screenplay_line(self):
        instruction, mode = _build_dialogue_instruction(
            {
                "character": "DRE",
                "text": "You good? You're looking at me weird.",
            },
            model="qwen3-tts-instruct-flash",
            voice="Cherry",
            scene_context={"audio_tension": "low"},
        )

        assert mode == "qwen_freeform"
        assert instruction
        assert "casual concern" in instruction
        assert "scene pressure: low" in instruction
        sources = _dialogue_instruction_sources(
            {"character": "DRE", "text": "You good? You're looking at me weird."},
            {"audio_tension": "low"},
        )
        assert sources["emotional_subtext"] == {
            "source": "line_text_inference",
            "value": "casual concern, testing whether something is wrong",
        }

    def test_ssml_text_is_used_as_tts_payload_but_keeps_plain_line_text(self):
        line = {
            "character": "DRE",
            "text": "Someone had to.",
            "ssml_text": '<speak><break time="450ms"/>Someone had to.</speak>',
        }

        assert _dialogue_tts_text(line) == line["ssml_text"]
        assert _dialogue_instruction_sources(line)["ssml_text"] == {
            "source": "line.ssml_text",
            "value": line["ssml_text"],
        }

    def test_cosyvoice_v3_longwanjun_keeps_direction_but_sends_no_instruction(self):
        line = {
            "character": "MAYA",
            "text": "That's funny.",
            "emotional_subtext": "bitter and flat, not actually amused",
            "pacing_tag": "short, dry, almost no lift on funny",
        }

        instruction, mode = _build_dialogue_instruction(
            line,
            model="cosyvoice-v3-flash",
            voice="longwanjun_v3",
            scene_context={"audio_tension": "betrayal at gunpoint"},
        )

        assert mode == "none"
        assert instruction is None
        assert _dialogue_instruction_sources(line)["emotional_subtext"] == {
            "source": "line.emotional_subtext",
            "value": "bitter and flat, not actually amused",
        }


class TestSceneDialogueRouteResolution:
    def test_placeholder_execution_summary_lines_are_ignored(self, monkeypatch):
        import app.services.project_store as project_store_module

        fake_store = SimpleNamespace(
            get_project=lambda project_id: {
                "execution_summary": {
                    "dialogue_lines": [
                        {
                            "scene_id": "scene_003",
                            "character_name": "DRE",
                            "text": "DRE carries the beat with restrained subtext.",
                            "emotional_subtext": "restrained subtext",
                        }
                    ]
                }
            }
        )
        monkeypatch.setattr(project_store_module, "project_store", fake_store)

        assert audio_route._resolve_scene_dialogue_lines("project", "scene_003") is None

    def test_real_execution_summary_lines_are_preserved(self, monkeypatch):
        import app.services.project_store as project_store_module

        fake_store = SimpleNamespace(
            get_project=lambda project_id: {
                "execution_summary": {
                    "dialogue_lines": [
                        {
                            "scene_id": "scene_003",
                            "character_name": "DRE",
                            "text": "You good? You're looking at me weird.",
                            "emotional_subtext": "concern masked as casual banter",
                            "pacing_tag": "easy but watchful",
                        }
                    ]
                }
            }
        )
        monkeypatch.setattr(project_store_module, "project_store", fake_store)

        assert audio_route._resolve_scene_dialogue_lines("project", "scene_003") == [
            {
                "character": "DRE",
                "text": "You good? You're looking at me weird.",
                "emotional_subtext": "concern masked as casual banter",
                "pacing_tag": "easy but watchful",
            }
        ]


class TestCosyVoiceProviderDispatch:
    def test_cosyvoice_calls_cosyvoice(
        self, service, fake_cosyvoice, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="cosyvoice")
        assert out.exists()

    def test_qwen_tts_service_passes_instruction_to_dashscope(
        self, monkeypatch, tmp_path
    ):
        captured = {}

        monkeypatch.setattr(
            cosyvoice_module,
            "get_dashscope_config",
            lambda: SimpleNamespace(
                api_key="test-key",
                region="intl",
                workspace_id="test-workspace",
                native_api_base_url="https://dashscope-intl.aliyuncs.com/api/v1",
                native_websocket_api_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
            ),
        )
        monkeypatch.setattr(
            cosyvoice_module,
            "VoiceEnrollmentService",
            lambda: SimpleNamespace(),
        )

        def _fake_call(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output={"audio": {"data": "UklGRg=="}})

        monkeypatch.setattr(
            cosyvoice_module.dashscope.MultiModalConversation,
            "call",
            _fake_call,
        )

        instruction = "Perform DRE with quiet concern and held-back pacing."
        out = tmp_path / "qwen.mp3"
        CosyVoiceTTSService(model="qwen3-tts-instruct-flash").synthesize_dialogue(
            text="You good?",
            voice="Cherry",
            output_path=out,
            instruction=instruction,
        )

        assert out.exists()
        assert captured["model"] == "qwen3-tts-instruct-flash"
        assert captured["voice"] == "Cherry"
        assert captured["text"] == "You good?"
        assert captured["instructions"] == instruction
        assert captured["optimize_instructions"] is True
        assert captured["stream"] is False

    def test_cosyvoice_v3_collects_callback_audio_when_call_returns_none(
        self, monkeypatch, tmp_path
    ):
        captured = {}

        monkeypatch.setattr(
            cosyvoice_module,
            "get_dashscope_config",
            lambda: SimpleNamespace(
                api_key="test-key",
                region="intl",
                workspace_id="test-workspace",
                native_api_base_url="https://dashscope-intl.aliyuncs.com/api/v1",
                native_websocket_api_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
            ),
        )
        monkeypatch.setattr(
            cosyvoice_module,
            "VoiceEnrollmentService",
            lambda: SimpleNamespace(),
        )

        class FakeSpeechSynthesizer:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.callback = kwargs["callback"]

            def call(self, text, timeout_millis=None):
                captured["text"] = text
                captured["timeout_millis"] = timeout_millis
                self.callback.on_data(b"audio-bytes")
                self.callback.on_complete()
                return None

        monkeypatch.setattr(
            cosyvoice_module,
            "SpeechSynthesizer",
            FakeSpeechSynthesizer,
        )

        out = tmp_path / "cosy.mp3"
        CosyVoiceTTSService(model="cosyvoice-v3-flash").synthesize_dialogue(
            text="Someone had to.",
            voice="longanyang",
            output_path=out,
            instruction="Perform DRE with shame under resolve.",
        )

        assert out.read_bytes() == b"audio-bytes"
        assert captured["model"] == "cosyvoice-v3-flash"
        assert captured["voice"] == "longanyang"
        assert captured["instruction"] == "Perform DRE with shame under resolve."
        assert captured["text"] == "Someone had to."

    def test_cosyvoice_v3_waits_for_delayed_callback_audio_after_task_started(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            cosyvoice_module,
            "get_dashscope_config",
            lambda: SimpleNamespace(
                api_key="test-key",
                region="intl",
                workspace_id="test-workspace",
                native_api_base_url="https://dashscope-intl.aliyuncs.com/api/v1",
                native_websocket_api_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
            ),
        )
        monkeypatch.setattr(
            cosyvoice_module,
            "VoiceEnrollmentService",
            lambda: SimpleNamespace(),
        )
        monkeypatch.setattr(cosyvoice_module, "DEFAULT_TIMEOUT_MILLIS", 1000)

        class FakeSpeechSynthesizer:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]

            def call(self, text, timeout_millis=None):
                threading.Timer(0.01, self._finish).start()
                return None

            def _finish(self):
                self.callback.on_data(b"late-audio")
                self.callback.on_complete()

        monkeypatch.setattr(
            cosyvoice_module,
            "SpeechSynthesizer",
            FakeSpeechSynthesizer,
        )

        out = tmp_path / "cosy.mp3"
        CosyVoiceTTSService(model="cosyvoice-v3-flash").synthesize_dialogue(
            text="I need you to understand something.",
            voice="longanyang",
            output_path=out,
            instruction="Perform DRE with controlled tension.",
        )

        assert out.read_bytes() == b"late-audio"

    def test_cosyvoice_v3_no_audio_error_includes_provider_context(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            cosyvoice_module,
            "get_dashscope_config",
            lambda: SimpleNamespace(
                api_key="test-key",
                region="intl",
                workspace_id="test-workspace",
                native_api_base_url="https://dashscope-intl.aliyuncs.com/api/v1",
                native_websocket_api_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
            ),
        )
        monkeypatch.setattr(
            cosyvoice_module,
            "VoiceEnrollmentService",
            lambda: SimpleNamespace(),
        )
        monkeypatch.setattr(cosyvoice_module, "DEFAULT_MAX_RETRIES", 1)

        class FakeSpeechSynthesizer:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]

            def call(self, text, timeout_millis=None):
                self.callback.on_error("provider rejected instruction")
                return None

            def get_response(self):
                return '{"code":"InvalidParameter"}'

            def get_last_request_id(self):
                return "req-123"

        monkeypatch.setattr(
            cosyvoice_module,
            "SpeechSynthesizer",
            FakeSpeechSynthesizer,
        )

        out = tmp_path / "cosy.mp3"
        with pytest.raises(RuntimeError) as exc_info:
            CosyVoiceTTSService(model="cosyvoice-v3-flash").synthesize_dialogue(
                text="Someone had to.",
                voice="longanyang",
                output_path=out,
                instruction="Perform DRE with shame under resolve.",
            )

        message = str(exc_info.value)
        assert "CosyVoice returned no audio" in message
        assert "provider rejected instruction" in message
        assert "req-123" in message
        assert "InvalidParameter" in message

    def test_cosyvoice_clone_uses_dashscope_safe_prefix(self, monkeypatch):
        captured = {}

        monkeypatch.setattr(
            cosyvoice_module,
            "get_dashscope_config",
            lambda: SimpleNamespace(
                api_key="test-key",
                region="intl",
                workspace_id="test-workspace",
                native_api_base_url="https://dashscope-intl.aliyuncs.com/api/v1",
                native_websocket_api_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
            ),
        )

        class FakeEnrollment:
            def create_voice(self, **kwargs):
                captured.update(kwargs)
                return "casting123_voice"

        monkeypatch.setattr(cosyvoice_module, "VoiceEnrollmentService", FakeEnrollment)

        cloned = CosyVoiceTTSService().clone_voice_from_sample(
            audio_url="https://example.com/reference.wav",
            preferred_name="casting-comparison",
        )

        assert cloned.voice_id == "casting123_voice"
        assert cloned.preferred_name == "casting-comparison"
        assert captured["target_model"] == "cosyvoice-v3"
        assert captured["url"] == "https://example.com/reference.wav"
        assert captured["prefix"] == "castingcom"
        assert len(captured["prefix"]) <= 10

    def test_cosyvoice_failover_to_piper_on_error(
        self, service, fake_piper, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        monkeypatch.setattr(aps, "COSYVOICE_FAILOVER_TO_PIPER", True)
        monkeypatch.setattr(aps, "PIPER_AVAILABLE", True)

        def _failing_cosyvoice(
            self, text, output_path, voice=None, character=None, project_id=None,
            instruction=None,
        ):
            raise RuntimeError("CosyVoice API error: 401")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_cosyvoice_tts_sync", _failing_cosyvoice
        )

        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="cosyvoice")
        assert out.exists(), "Piper fallback should have written a WAV"

    def test_cosyvoice_no_failover_re_raises(
        self, service, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        monkeypatch.setattr(aps, "COSYVOICE_FAILOVER_TO_PIPER", False)

        def _failing_cosyvoice(
            self, text, output_path, voice=None, character=None, project_id=None,
            instruction=None,
        ):
            raise RuntimeError("CosyVoice API error: 402 payment required")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_cosyvoice_tts_sync", _failing_cosyvoice
        )

        out = tmp_path / "out.wav"
        with pytest.raises(RuntimeError, match="402"):
            service._generate_dialogue_tts_sync("hello", out, provider="cosyvoice")

    def test_auto_uses_cosyvoice_when_elevenlabs_absent_and_dashscope_configured(
        self, service, fake_cosyvoice, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", False)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="auto")
        assert out.exists()

    def test_auto_still_prefers_elevenlabs_when_both_configured(
        self, service, fake_elevenlabs, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", True)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)

        def _unexpected_cosyvoice(
            self, text, output_path, voice=None, character=None, project_id=None,
            instruction=None,
        ):
            raise AssertionError("auto should prefer ElevenLabs when configured")

        monkeypatch.setattr(
            AudioPipelineService, "_generate_cosyvoice_tts_sync", _unexpected_cosyvoice
        )

        out = tmp_path / "out.wav"
        service._generate_dialogue_tts_sync("hello", out, provider="auto")
        assert out.exists()


class TestShotDialogueWithCosyVoiceProvider:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            aps.audio_pipeline_service, "output_base", tmp_path / "audio"
        )

    @pytest.mark.asyncio
    async def test_shot_dialogue_with_cosyvoice_provider(
        self, fake_cosyvoice, monkeypatch
    ):
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)

        dialogue_lines = [
            {"character": "DRE", "text": "I remember the way the light fell."},
            {"character": "MAYA", "text": "So do I."},
        ]
        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_001",
            shot_id="shot_001",
            dialogue_lines=dialogue_lines,
            provider="cosyvoice",
        )
        assert result["status"] == TrackStatus.COMPLETE
        assert result["lines_generated"] == 2
        assert result["file_path"] is not None
        assert result["line_instructions"][0]["instruction"]
        assert result["line_instructions"][0]["instruction_mode"] == "qwen_freeform"
        assert os.path.exists(result["file_path"])

    @pytest.mark.asyncio
    async def test_shot_dialogue_uses_project_cosyvoice_casting(
        self, temp_storage, monkeypatch
    ):
        captured = []
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)

        created = temp_storage.save_character("proj-test", "DRE", {})
        temp_storage.set_character_voice_casting(
            created["id"],
            "proj-test",
            provider="cosyvoice",
            voice_id="cosyvoice-dre-clone-001",
            voice_name="Dre clone",
            source_type="clone",
        )

        def _fake_cosyvoice_sync(
            self, text, output_path, voice=None, character=None, project_id=None,
            instruction=None,
        ):
            captured.append(
                {
                    "voice": voice,
                    "character": character,
                    "project_id": project_id,
                    "instruction": instruction,
                }
            )
            _write_tone_wav(output_path, duration=0.2)

        monkeypatch.setattr(
            AudioPipelineService,
            "_generate_cosyvoice_tts_sync",
            _fake_cosyvoice_sync,
        )

        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_001",
            shot_id="shot_001",
            dialogue_lines=[{"character": "DRE", "text": "You good?"}],
            provider="cosyvoice",
        )

        assert result["status"] == TrackStatus.COMPLETE
        assert captured[0]["voice"] == "cosyvoice-dre-clone-001"
        assert captured[0]["character"] == "DRE"
        assert captured[0]["project_id"] == "proj-test"
        assert "casual concern" in captured[0]["instruction"]
        assert result["line_instructions"][0]["voice"] == "cosyvoice-dre-clone-001"
        assert result["line_instructions"][0]["instruction_sources"]["emotional_subtext"] == {
            "source": "line_text_inference",
            "value": "casual concern, testing whether something is wrong",
        }

    @pytest.mark.asyncio
    async def test_shot_dialogue_sends_ssml_payload_to_cosyvoice(
        self, monkeypatch
    ):
        captured = []
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)

        def _fake_cosyvoice_sync(
            self, text, output_path, voice=None, character=None, project_id=None,
            instruction=None,
        ):
            captured.append(
                {
                    "text": text,
                    "character": character,
                    "instruction": instruction,
                }
            )
            _write_tone_wav(output_path, duration=0.2)

        monkeypatch.setattr(
            AudioPipelineService,
            "_generate_cosyvoice_tts_sync",
            _fake_cosyvoice_sync,
        )

        ssml_text = '<speak>So you<break time="180ms"/> decided.</speak>'
        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_001",
            shot_id="shot_001",
            dialogue_lines=[
                {
                    "character": "MAYA",
                    "text": "So you decided.",
                    "ssml_text": ssml_text,
                    "emotional_subtext": "controlled indictment",
                }
            ],
            provider="cosyvoice",
        )

        assert result["status"] == TrackStatus.COMPLETE
        assert captured[0]["text"] == ssml_text
        assert result["line_instructions"][0]["text"] == "So you decided."
        assert result["line_instructions"][0]["tts_text"] == ssml_text
        assert "controlled indictment" in captured[0]["instruction"]

    @pytest.mark.asyncio
    async def test_shot_dialogue_omits_instruction_for_longwanjun_v3(
        self, monkeypatch
    ):
        captured = []
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        monkeypatch.setattr(aps, "COSYVOICE_MODEL", "cosyvoice-v3-flash")
        monkeypatch.setattr(
            aps,
            "_resolve_cosyvoice_voice_id",
            lambda character=None, project_id=None: "longwanjun_v3",
        )

        def _fake_cosyvoice_sync(
            self, text, output_path, voice=None, character=None, project_id=None,
            instruction=None,
        ):
            captured.append(
                {
                    "text": text,
                    "voice": voice,
                    "character": character,
                    "instruction": instruction,
                }
            )
            _write_tone_wav(output_path, duration=0.2)

        monkeypatch.setattr(
            AudioPipelineService,
            "_generate_cosyvoice_tts_sync",
            _fake_cosyvoice_sync,
        )

        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_002",
            shot_id="shot_scene_002_001",
            dialogue_lines=[
                {
                    "character": "MAYA",
                    "text": "That's funny.",
                    "emotional_subtext": "bitter and flat, not actually amused",
                    "pacing_tag": "short, dry, almost no lift on funny",
                }
            ],
            provider="cosyvoice",
            scene_context={"audio_tension": "betrayal at gunpoint"},
        )

        assert result["status"] == TrackStatus.COMPLETE
        assert captured[0]["voice"] == "longwanjun_v3"
        assert captured[0]["instruction"] is None
        assert result["line_instructions"][0]["instruction_mode"] == "none"
        assert result["line_instructions"][0]["instruction"] is None
        assert "bitter and flat" in result["line_instructions"][0]["performance_direction"]


class TestFullPipelineNoScoreAmbientProvider:
    @pytest.mark.asyncio
    async def test_default_pipeline_skips_score_and_ambient(
        self, service, fake_cosyvoice, monkeypatch
    ):
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "COSYVOICE_CONFIGURED", True)
        monkeypatch.setattr(aps, "DIALOGUE_PROVIDER", "cosyvoice")
        monkeypatch.setattr(aps, "SCORE_AMBIENT_PROVIDER", "none")

        async def _unexpected_score(*args, **kwargs):
            raise AssertionError("score generation should be skipped when provider is none")

        async def _unexpected_ambient(*args, **kwargs):
            raise AssertionError("ambient generation should be skipped when provider is none")

        async def _fake_mix(project_id, scene_id, dialogue_path, score_path=None, ambient_path=None):
            assert dialogue_path.exists()
            assert score_path is None
            assert ambient_path is None
            return {
                "track": "mixed",
                "status": TrackStatus.COMPLETE,
                "file_path": str(dialogue_path),
                "file_url": str(dialogue_path),
                "tracks_mixed": 1,
            }

        monkeypatch.setattr(service, "generate_score", _unexpected_score)
        monkeypatch.setattr(service, "generate_ambient", _unexpected_ambient)
        monkeypatch.setattr(service, "mix_audio_tracks", _fake_mix)

        result = await service.generate_full_pipeline(
            scene_id="scene_003",
            project_id="proj-test",
            dialogue_lines=[{"character": "DRE", "text": "You good?"}],
        )

        assert result["status"] == "complete"
        assert result["dialogue_provider"] == "cosyvoice"
        assert result["score_ambient_provider"] == "none"
        assert result["steps"]["score"]["status"] == TrackStatus.SKIPPED
        assert result["steps"]["ambient"]["status"] == TrackStatus.SKIPPED
        assert result["steps"]["score"]["file_path"] is None
        assert result["steps"]["ambient"]["file_path"] is None
        assert result["steps"]["mix"]["tracks_mixed"] == 1
        assert result["steps"]["dialogue"]["line_instructions"][0]["instruction"]
