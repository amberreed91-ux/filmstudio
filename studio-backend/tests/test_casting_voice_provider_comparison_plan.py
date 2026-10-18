from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
import types
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_script_module():
    path = _BACKEND_ROOT / "scripts" / "plan_casting_voice_provider_comparison.py"
    spec = importlib.util.spec_from_file_location("plan_casting_voice_provider_comparison", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_reference_wav(path: Path, *, duration_seconds: float = 3.2) -> None:
    sample_rate = 8000
    frame_count = int(sample_rate * duration_seconds)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frame_count)


def test_casting_comparison_plan_records_reference_hash_and_consent_gate(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference-audio")
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", raising=False)

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://example.com/reference.wav",
            voice_prompt="warm, tired, guarded",
            sample_text=["You good?", "Keep your voice down."],
            emotion_instruction=["casual concern", "controlled unease"],
        )
    )

    assert report["network_used"] is False
    assert report["reference_audio_sha256"] == hashlib.sha256(b"reference-audio").hexdigest()
    assert report["reference_readiness"] == {
        "local_reference_file_exists": True,
        "local_reference_usable": False,
        "direct_public_audio_url_usable": True,
        "shared_reference_ready": False,
    }
    assert report["sample_texts"] == ["You good?", "Keep your voice down."]
    assert report["emotion_instructions"] == ["casual concern", "controlled unease"]
    command = report["live_comparison_readiness"]["readiness_packet_command_template"]
    assert "--sample-text 'You good?'" in command
    assert "--sample-text 'Keep your voice down.'" in command
    assert "--emotion-instruction 'casual concern'" in command
    assert "--emotion-instruction 'controlled unease'" in command
    assert report["consent_gate"]["granted"] is False
    assert "usable reference audio clip" in report["providers"]["fish_audio_s2_pro_clone"]["missing"]
    assert "explicit consent env" in report["live_comparison_readiness"]["missing"]
    evaluation = report["human_evaluation_template"]
    assert evaluation["sample_rows"][0]["text"] == "You good?"
    assert evaluation["sample_rows"][1]["emotion_instruction"] == "controlled unease"
    assert evaluation["provider_decision"]["selected_path"] == ""
    assert "use concrete listening evidence instead of numeric scores" in evaluation["purpose"]
    assert "score" not in json_like_keys(evaluation)
    assert "rating" not in json_like_keys(evaluation)


def test_casting_comparison_plan_records_ready_shared_reference(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", raising=False)

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://example.com/reference.wav",
            voice_prompt="warm, tired, guarded",
            sample_text=None,
            emotion_instruction=None,
        )
    )

    assert report["reference_readiness"]["shared_reference_ready"] is True
    assert report["live_comparison_readiness"]["missing"] == [
        "FISH_AUDIO_API_KEY",
        "DASHSCOPE_API_KEY",
        "explicit consent env",
    ]
    assert "prepared reference clip" in report["recommended_decision_now"]["reason"]
    assert "without a reference clip" not in report["recommended_decision_now"]["reason"]


def test_casting_comparison_command_template_quotes_all_samples_and_emotions():
    module = _load_script_module()

    command = module._build_readiness_command_template(
        ["You good? You're looking at me weird.", "Keep your voice down."],
        ["casual concern, held back rather than melodramatic", "controlled unease, low and clipped"],
    )

    assert "--sample-text 'You good? You'\"'\"'re looking at me weird.'" in command
    assert "--sample-text 'Keep your voice down.'" in command
    assert "--emotion-instruction 'casual concern, held back rather than melodramatic'" in command
    assert "--emotion-instruction 'controlled unease, low and clipped'" in command


def test_casting_comparison_plan_marks_ready_only_with_inputs_keys_and_consent(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", "I_APPROVE_EXTERNAL_VOICE_COMPARISON")

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://example.com/reference.wav",
            voice_prompt="warm, tired, guarded",
            sample_text=None,
            emotion_instruction=None,
        )
    )

    assert report["providers"]["fish_audio_s2_pro_clone"]["can_run_live_comparison"] is True
    assert report["providers"]["cosyvoice_voice_clone"]["can_run_live_comparison"] is True
    assert report["sample_texts"] == [
        "You good? You're looking at me weird.",
        "Keep your voice down.",
    ]
    assert len(report["human_evaluation_template"]["sample_rows"]) == 2
    assert report["live_comparison_readiness"]["can_run_after_consent"] is True
    assert report["live_comparison_readiness"]["missing"] == []
    assert "ready to run" in report["recommended_decision_now"]["reason"]
    assert "credentials are exported" not in report["recommended_decision_now"]["reason"]
    assert report["human_evaluation_template"]["decision_options"] == [
        "keep_fish_audio_for_casting",
        "use_cosyvoice_qwen_stack_for_casting",
        "defer_pending_more_samples",
    ]


def test_live_comparison_requires_full_readiness(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", raising=False)

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://example.com/reference.wav",
            voice_prompt="warm, tired, guarded",
            sample_text=None,
            emotion_instruction=None,
        )
    )

    with pytest.raises(SystemExit, match="Live comparison is not ready"):
        module._assert_live_ready(report)


def test_casting_comparison_rejects_invalid_reference_audio_for_live_readiness(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"not-a-real-audio-file")
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", "I_APPROVE_EXTERNAL_VOICE_COMPARISON")

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://example.com/reference.wav",
            voice_prompt="warm, tired, guarded",
            sample_text=None,
            emotion_instruction=None,
        )
    )

    assert report["providers"]["fish_audio_s2_pro_clone"]["can_run_live_comparison"] is False
    assert "usable reference audio clip" in report["providers"]["fish_audio_s2_pro_clone"]["missing"]
    assert "usable reference audio clip" in report["live_comparison_readiness"]["missing"]
    assert report["live_comparison_readiness"]["can_run_after_consent"] is False


def test_casting_comparison_rejects_youtube_page_as_public_reference_audio_url(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", "I_APPROVE_EXTERNAL_VOICE_COMPARISON")

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://youtu.be/lhVHHDdyPQg?si=UodU7G1kXPzcBwzb",
            voice_prompt="warm, tired, guarded",
            sample_text=None,
            emotion_instruction=None,
        )
    )

    assert report["providers"]["fish_audio_s2_pro_clone"]["can_run_live_comparison"] is True
    assert report["providers"]["cosyvoice_voice_clone"]["can_run_live_comparison"] is False
    assert "direct public audio URL" in report["providers"]["cosyvoice_voice_clone"]["missing"]
    assert "direct public audio URL for DashScope clone" in report["live_comparison_readiness"]["missing"]
    assert report["live_comparison_readiness"]["can_run_after_consent"] is False


def test_casting_comparison_rejects_archive_as_public_reference_audio_url(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", "I_APPROVE_EXTERNAL_VOICE_COMPARISON")

    report = module._build_report(
        argparse.Namespace(
            reference_audio=reference,
            public_reference_url="https://data.keithito.com/data/speech/LJSpeech-1.1.tar.gz",
            voice_prompt="warm, tired, guarded",
            sample_text=None,
            emotion_instruction=None,
        )
    )

    assert report["providers"]["fish_audio_s2_pro_clone"]["can_run_live_comparison"] is True
    assert report["providers"]["cosyvoice_voice_clone"]["can_run_live_comparison"] is False
    assert "direct public audio URL" in report["providers"]["cosyvoice_voice_clone"]["missing"]
    assert "direct public audio URL for DashScope clone" in report["live_comparison_readiness"]["missing"]
    assert report["live_comparison_readiness"]["can_run_after_consent"] is False


def test_live_comparison_manifest_with_faked_providers(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", "I_APPROVE_EXTERNAL_VOICE_COMPARISON")
    monkeypatch.setattr(module, "OUT_DIR", tmp_path / "reports")
    monkeypatch.setattr(module, "LIVE_OUT_DIR", tmp_path / "reports" / "casting_voice_provider_comparison")

    class FakeFishAudioProvider:
        def __init__(self):
            self.closed = False

        async def clone_voice(self, reference_audio_path: str, label: str) -> str:
            assert Path(reference_audio_path) == reference
            return "fish-voice-123"

        async def synthesize(self, text: str, voice_id: str, emotion_tag: str | None = None, format: str = "mp3"):
            return SimpleNamespace(audio_bytes=f"fish:{voice_id}:{emotion_tag}:{text}".encode(), format=format)

        async def close(self):
            self.closed = True

    class FakeCosyVoiceTTSService:
        def clone_voice_from_sample(self, *, audio_url: str, preferred_name: str, target_model: str = "cosyvoice-v3"):
            assert audio_url == "https://example.com/reference.wav"
            return SimpleNamespace(voice_id="cosy-voice-456", preferred_name=preferred_name)

        def synthesize_dialogue(self, *, text: str, voice: str, output_path: Path, instruction: str | None = None, **kwargs):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(f"cosy:{voice}:{instruction}:{text}".encode())
            return output_path

    fish_module = types.ModuleType("fish_audio_provider")
    fish_module.FishAudioProvider = FakeFishAudioProvider
    cosy_module = types.ModuleType("app.services.audio.cosyvoice_tts_service")
    cosy_module.CosyVoiceTTSService = FakeCosyVoiceTTSService
    monkeypatch.setitem(sys.modules, "fish_audio_provider", fish_module)
    monkeypatch.setitem(sys.modules, "app.services.audio.cosyvoice_tts_service", cosy_module)

    args = argparse.Namespace(
        reference_audio=reference,
        public_reference_url="https://example.com/reference.wav",
        voice_prompt="warm, tired, guarded",
        sample_text=["You good?", "Keep your voice down."],
        emotion_instruction=["casual concern", "controlled unease"],
        output_dir=tmp_path / "samples",
        voice_label="Dre comparison",
        fish_voice_id="",
    )
    report = module._build_report(args)

    live_report = asyncio.run(module._run_live_comparison(args, report))

    assert live_report["mode"] == "live"
    assert live_report["network_used"] is True
    assert live_report["provider_voice_ids"] == {
        "fish_audio_s2_pro_clone": "fish-voice-123",
        "cosyvoice_voice_clone": "cosy-voice-456",
    }
    assert live_report["sample_pair_count"] == 2
    assert live_report["side_by_side_complete"] is True
    assert len(live_report["samples"]) == 2
    assert Path(live_report["samples"][0]["fish_audio"]["path"]).exists()
    assert Path(live_report["samples"][0]["cosyvoice"]["path"]).exists()
    assert live_report["human_evaluation_template"]["sample_rows"][0]["preferred_provider_for_this_line"] == ""
    assert (tmp_path / "reports" / "casting_voice_provider_comparison_live.json").exists()


def test_live_comparison_writes_failure_manifest_for_provider_error(tmp_path: Path, monkeypatch):
    module = _load_script_module()
    reference = tmp_path / "reference.wav"
    _write_reference_wav(reference)
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("LIVE_CASTING_VOICE_COMPARISON_APPROVED", "I_APPROVE_EXTERNAL_VOICE_COMPARISON")
    monkeypatch.setattr(module, "OUT_DIR", tmp_path / "reports")
    monkeypatch.setattr(module, "LIVE_OUT_DIR", tmp_path / "reports" / "casting_voice_provider_comparison")

    class FakeResponse:
        status_code = 402
        text = "payment required"

    class FakeRequest:
        method = "POST"
        url = "https://api.fish.audio/v1/tts"

    class FishPaymentRequired(Exception):
        def __init__(self):
            super().__init__("Client error '402 Payment Required'")
            self.response = FakeResponse()
            self.request = FakeRequest()

    class FakeFishAudioProvider:
        async def clone_voice(self, reference_audio_path: str, label: str) -> str:
            return "fish-voice-123"

        async def synthesize(self, text: str, voice_id: str, emotion_tag: str | None = None, format: str = "mp3"):
            raise FishPaymentRequired()

        async def close(self):
            return None

    class FakeCosyVoiceTTSService:
        def clone_voice_from_sample(self, *, audio_url: str, preferred_name: str, target_model: str = "cosyvoice-v3"):
            return SimpleNamespace(voice_id="cosy-voice-456", preferred_name=preferred_name)

    fish_module = types.ModuleType("fish_audio_provider")
    fish_module.FishAudioProvider = FakeFishAudioProvider
    cosy_module = types.ModuleType("app.services.audio.cosyvoice_tts_service")
    cosy_module.CosyVoiceTTSService = FakeCosyVoiceTTSService
    monkeypatch.setitem(sys.modules, "fish_audio_provider", fish_module)
    monkeypatch.setitem(sys.modules, "app.services.audio.cosyvoice_tts_service", cosy_module)

    args = argparse.Namespace(
        reference_audio=reference,
        public_reference_url="https://example.com/reference.wav",
        voice_prompt="warm, tired, guarded",
        sample_text=["You good?", "Keep your voice down."],
        emotion_instruction=["casual concern", "controlled unease"],
        output_dir=tmp_path / "samples",
        voice_label="Dre comparison",
        fish_voice_id="",
    )
    report = module._build_report(args)

    with pytest.raises(SystemExit, match="Live comparison failed at fish_audio_synthesize_sample_1"):
        asyncio.run(module._run_live_comparison(args, report))

    failure_path = tmp_path / "reports" / "casting_voice_provider_comparison_live.json"
    failure_report = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure_report["mode"] == "live_failed"
    assert failure_report["network_used"] is True
    assert failure_report["failure_stage"] == "fish_audio_synthesize_sample_1"
    assert failure_report["failure"]["status_code"] == 402
    assert failure_report["failure"]["url"] == "https://api.fish.audio/v1/tts"
    assert failure_report["provider_voice_ids"] == {
        "fish_audio_s2_pro_clone": "fish-voice-123",
        "cosyvoice_voice_clone": "cosy-voice-456",
    }
    assert failure_report["side_by_side_complete"] is False
    assert failure_report["samples"] == []


def test_live_comparison_manifest_verifier_rejects_missing_provider_output(tmp_path: Path):
    module = _load_script_module()
    fish_path = tmp_path / "fish.mp3"
    fish_path.write_bytes(b"fish")

    with pytest.raises(RuntimeError, match="CosyVoice output"):
        module._assert_live_report_complete(
            {
                "mode": "live",
                "network_used": True,
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "sample_texts": ["You good?", "Keep your voice down."],
                "provider_voice_ids": {
                    "fish_audio_s2_pro_clone": "fish-voice-123",
                    "cosyvoice_voice_clone": "cosy-voice-456",
                },
                "samples": [
                    {
                        "index": 0,
                        "text": "You good?",
                        "fish_audio": {"path": str(fish_path)},
                        "cosyvoice": {"path": str(tmp_path / "missing-cosy.mp3")},
                    },
                    {
                        "index": 1,
                        "text": "Keep your voice down.",
                        "fish_audio": {"path": str(fish_path)},
                        "cosyvoice": {"path": str(tmp_path / "missing-cosy-2.mp3")},
                    },
                ],
            }
        )


def json_like_keys(value) -> str:
    if isinstance(value, dict):
        return " ".join(str(key) + " " + json_like_keys(child) for key, child in value.items())
    if isinstance(value, list):
        return " ".join(json_like_keys(item) for item in value)
    return ""
