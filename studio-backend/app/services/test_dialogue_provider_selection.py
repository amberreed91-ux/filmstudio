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
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import audio_pipeline_service as aps
from app.services.audio_pipeline_service import (
    AudioPipelineService,
    TrackStatus,
    _fish_audio_emotion_delimiters,
    _normalize_dialogue_provider,
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
    def test_default_is_piper(self):
        assert _normalize_dialogue_provider(None) == "piper"

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
    async def test_shot_dialogue_default_stays_piper(self, fake_piper, monkeypatch):
        """Without a provider override, default is Piper — even if ElevenLabs
        is configured, the default env var is piper."""
        monkeypatch.setattr(aps, "MOCK_MODE", False)
        monkeypatch.setattr(aps, "ELEVENLABS_API_KEY", "test-key")
        monkeypatch.setattr(aps, "ELEVENLABS_CONFIGURED", True)
        monkeypatch.setattr(aps, "DIALOGUE_PROVIDER", "piper")

        dialogue_lines = [{"character": "DRE", "text": "Hello."}]
        result = await aps.audio_pipeline_service.generate_shot_dialogue(
            project_id="proj-test",
            scene_id="scene_001",
            shot_id="shot_001",
            dialogue_lines=dialogue_lines,
        )
        assert result["status"] == TrackStatus.COMPLETE


# ─── Capabilities report ─────────────────────────────────────────────────────


class TestCapabilitiesReport:
    def test_capabilities_includes_elevenlabs_fields(self):
        caps = AudioPipelineService.capabilities()
        assert "dialogue_tts_provider" in caps
        assert "elevenlabs_configured" in caps
        assert "valid_dialogue_providers" in caps
        assert "elevenlabs" in caps["valid_dialogue_providers"]
        assert "piper" in caps["valid_dialogue_providers"]

    def test_capabilities_default_provider_is_piper(self, monkeypatch):
        monkeypatch.setattr(aps, "DIALOGUE_PROVIDER", "piper")
        caps = AudioPipelineService.capabilities()
        assert caps["dialogue_tts_provider"] == "piper"

    def test_capabilities_includes_fish_audio_fields(self):
        caps = AudioPipelineService.capabilities()
        assert "fish_audio_configured" in caps
        assert "fish_audio_model" in caps
        assert "fish_audio_failover_to_piper" in caps
        assert "valid_fish_audio_models" in caps
        assert "fish_audio" in caps["valid_dialogue_providers"]


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
