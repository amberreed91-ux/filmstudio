from __future__ import annotations

import logging
import math
import struct
import wave
from pathlib import Path

from app.services import audio_pipeline_service as audio_module
from app.services.audio_pipeline_service import AudioPipelineService, TrackStatus
from app.services.generation_contract import freeze_dialogue_handoff
from conftest import run_async


def _silence(path: Path, duration: float = 0.1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 22050
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * int(sample_rate * duration))


def _tone_silence_tone(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 22050

    def tone_frames(duration: float) -> bytes:
        frames = int(sample_rate * duration)
        data = bytearray()
        for i in range(frames):
            sample = int(9000 * math.sin(2 * math.pi * 440 * (i / sample_rate)))
            data.extend(struct.pack("<h", sample))
        return bytes(data)

    def silence_frames(duration: float) -> bytes:
        return b"\x00\x00" * int(sample_rate * duration)

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(
            tone_frames(0.3)
            + silence_frames(0.35)
            + tone_frames(0.3)
            + silence_frames(0.1)
        )


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _service(tmp_path: Path) -> AudioPipelineService:
    service = AudioPipelineService()
    service.output_base = tmp_path / "audio"
    return service


def test_pre_supplied_shot_audio_bypasses_dialogue_provider(
    tmp_path: Path,
    monkeypatch,
    caplog,
):
    service = _service(tmp_path)
    supplied = (
        service.output_base
        / "project_real"
        / "scene_002"
        / "pre_supplied"
        / "shot_scene_002_001.wav"
    )
    _silence(supplied)

    monkeypatch.setattr(
        service,
        "_generate_dialogue_tts_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("dialogue provider must not be called")
        ),
    )
    caplog.set_level(logging.INFO, logger="audio-pipeline")
    result = run_async(
        service.generate_shot_dialogue(
            project_id="project_real",
            scene_id="scene_002",
            shot_id="shot_scene_002_001",
            dialogue_lines=[{"character": "MAYA", "text": "I remember."}],
            provider="cosyvoice",
            allow_generation=False,
        )
    )

    assert result["status"] == TrackStatus.COMPLETE
    assert result["provider"] == "cosyvoice"
    assert result["source"] == "pre_supplied"
    assert result["source_path"] == str(supplied)
    assert Path(result["file_path"]).is_file()
    assert "source=pre_supplied" in caplog.text
    assert str(supplied) in caplog.text


def test_pre_supplied_shot_audio_preserves_internal_pauses(
    tmp_path: Path,
    monkeypatch,
):
    service = _service(tmp_path)
    supplied = (
        service.output_base
        / "project_real"
        / "scene_002"
        / "pre_supplied"
        / "shot_scene_002_001.wav"
    )
    _tone_silence_tone(supplied)

    monkeypatch.setattr(
        service,
        "_generate_dialogue_tts_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("dialogue provider must not be called")
        ),
    )

    result = run_async(
        service.generate_shot_dialogue(
            project_id="project_real",
            scene_id="scene_002",
            shot_id="shot_scene_002_001",
            dialogue_lines=[
                {"character": "MAYA", "text": "So you decided."},
                {"character": "DRE", "text": "Someone had to."},
            ],
            provider="cosyvoice",
            allow_generation=False,
        )
    )

    assert result["status"] == TrackStatus.COMPLETE
    assert result["source"] == "pre_supplied"
    assert _duration(Path(result["file_path"])) >= 0.85


def test_missing_pre_supplied_audio_uses_live_provider_path(
    tmp_path: Path,
    monkeypatch,
):
    service = _service(tmp_path)
    calls: list[str] = []

    def fake_generate(text, output_path, **kwargs):
        calls.append(text)
        _silence(output_path)

    monkeypatch.setattr(audio_module, "MOCK_MODE", False)
    monkeypatch.setattr(service, "_generate_dialogue_tts_sync", fake_generate)
    dialogue_lines = [{"character": "MAYA", "text": "I remember."}]

    result = run_async(
        service.generate_shot_dialogue(
            project_id="project_real",
            scene_id="scene_002",
            shot_id="shot_scene_002_001",
            dialogue_lines=dialogue_lines,
            provider="piper",
            dialogue_handoff=freeze_dialogue_handoff(
                scene_id="scene_002",
                shot_id="shot_scene_002_001",
                lines=dialogue_lines,
            ),
        )
    )

    assert result["status"] == TrackStatus.COMPLETE
    assert result["source"] == "live_provider"
    assert calls == ["I remember."]


def test_invalid_pre_supplied_audio_fails_without_provider_fallback(
    tmp_path: Path,
    monkeypatch,
):
    service = _service(tmp_path)
    supplied = (
        service.output_base
        / "project_real"
        / "scene_002"
        / "pre_supplied"
        / "shot_scene_002_001.mp3"
    )
    supplied.parent.mkdir(parents=True)
    supplied.write_bytes(b"not audio")

    monkeypatch.setattr(
        service,
        "_normalize_audio_to_wav",
        lambda src, dst, trim_edge_silence=False: (_ for _ in ()).throw(
            ValueError("invalid audio")
        ),
    )
    monkeypatch.setattr(
        service,
        "_generate_dialogue_tts_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("dialogue provider must not be called")
        ),
    )

    result = run_async(
        service.generate_shot_dialogue(
            project_id="project_real",
            scene_id="scene_002",
            shot_id="shot_scene_002_001",
            dialogue_lines=[{"character": "MAYA", "text": "I remember."}],
            provider="cosyvoice",
            allow_generation=False,
        )
    )

    assert result["status"] == TrackStatus.FAILED
    assert result["source"] == "pre_supplied"
    assert result["file_path"] is None
    assert "live provider was not called" in result["advisory"]
