"""Render isolated bare and instructed Scene_002 clone comparisons.

This harness deliberately bypasses ``AudioPipelineService`` instruction
building so the bare pass sends ``instruction=None`` and plain screenplay text.
The instructed pass uses explicit, reviewed directions below; every provider
instruction is shorter than CosyVoice's 100-character limit.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from app.script_guard import refuse_non_approved_provider

refuse_non_approved_provider(
    __file__,
    what="render bare vs instructed scene_002 clone comparisons via CosyVoice TTS",
    provider="dashscope",
)

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from app.services.audio.cosyvoice_tts_service import CosyVoiceTTSService


PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_002"
OUTPUT_ROOT = BACKEND_ROOT / "outputs" / "voice_clone_scene_002" / "comparison"
CLONE_MANIFEST = (
    BACKEND_ROOT / "outputs" / "voice_clone_scene_002" / "voice_clone_manifest.json"
)
PREFLIGHT = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "scene_002_directed_dialogue_preflight.json"
)

SHORT_INSTRUCTIONS = {
    "I need you to understand something.": (
        "Tense, controlled; justify himself before the unforgivable. Low and careful."
    ),
    "That's funny.": (
        "Bitter and flat, not amused. Short and dry; almost no lift on 'funny'."
    ),
    "What?": (
        "Caught off guard and defensive. Pause briefly, then clip the word."
    ),
    "You always say that right before you do something you know is wrong.": (
        "Quiet recognition, wounded by the pattern. Measured; never raise the volume."
    ),
    "Things changed.": (
        "Thin defensive cover, making betrayal sound practical. Small and compressed."
    ),
    "No. People changed.": (
        "Controlled hurt hardening into moral clarity. Separate correction from verdict."
    ),
    "There's not enough. You have to understand that. There is not enough for everyone.": (
        "Strained rationalizing, almost pleading for absolution. Repeat lands heavier."
    ),
    "So you decided that for all of us.": (
        "Low disbelief turning to indictment. Steady; pressure falls after 'you'."
    ),
    "Someone had to.": (
        "Ashamed but forcing resolve. Pause, then quiet and final."
    ),
    "I remember dying. So why am I here?": (
        "Quiet and disoriented, inside the shock. Soft, searching; air before the question."
    ),
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return payload


def _normalize_to_wav(source: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg normalization failed: {result.stderr[-800:]}")


def _duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr[-800:]}")
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise RuntimeError(f"Audio has no positive duration: {path}")
    return duration


def _write_silence(path: Path, seconds: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            str(seconds),
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg silence generation failed: {result.stderr[-800:]}")


def _concat(inputs: list[Path], destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    concat_file = destination.with_suffix(".concat.txt")
    concat_file.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in inputs),
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr[-800:]}")
    finally:
        concat_file.unlink(missing_ok=True)


def _line_records(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for shot in preflight.get("shots") or []:
        shot_id = str(shot.get("shot_id") or "")
        for line in shot.get("line_instructions") or []:
            text = str(line.get("text") or "").strip()
            if not shot_id or not text:
                continue
            records.append(
                {
                    "shot_id": shot_id,
                    "line_index": int(line.get("line_index") or 0),
                    "character": str(line.get("character") or "").strip().upper(),
                    "text": text,
                    "ssml_text": (
                        (line.get("instruction_sources") or {})
                        .get("ssml_text", {})
                        .get("value")
                    ),
                    "full_performance_direction": line.get("performance_direction"),
                }
            )
    if len(records) != 10:
        raise RuntimeError(f"Expected 10 Scene_002 lines across four shots, got {len(records)}")
    return records


def _validate_instructions(records: list[dict[str, Any]]) -> None:
    missing = [record["text"] for record in records if record["text"] not in SHORT_INSTRUCTIONS]
    if missing:
        raise RuntimeError(f"Missing compact instructions: {missing}")
    too_long = {
        text: len(instruction)
        for text, instruction in SHORT_INSTRUCTIONS.items()
        if len(instruction) > 100
    }
    if too_long:
        raise RuntimeError(f"Instructions exceed 100 characters: {too_long}")


def render(mode: str) -> Path:
    if mode not in {"bare", "instructed"}:
        raise ValueError(f"Unsupported mode: {mode}")
    clone_manifest = _load_json(CLONE_MANIFEST)
    preflight = _load_json(PREFLIGHT)
    records = _line_records(preflight)
    _validate_instructions(records)

    model = str(clone_manifest.get("voice_clone_model") or "")
    cast = clone_manifest.get("cast") or {}
    voices = {
        character: str((cast.get(character) or {}).get("voice_id") or "")
        for character in ("MAYA", "DRE")
    }
    if not model or not all(voices.values()):
        raise RuntimeError("Clone model or voice IDs are missing from the clone manifest")

    mode_dir = OUTPUT_ROOT / mode
    line_dir = mode_dir / "lines"
    shot_dir = mode_dir / "shots"
    line_dir.mkdir(parents=True, exist_ok=True)
    shot_dir.mkdir(parents=True, exist_ok=True)
    service = CosyVoiceTTSService(model=model)

    rendered: list[dict[str, Any]] = []
    shot_lines: dict[str, list[Path]] = {}
    for global_index, record in enumerate(records):
        character = record["character"]
        voice = voices.get(character)
        if not voice:
            raise RuntimeError(f"No cloned voice configured for {character}")
        instruction = (
            SHORT_INSTRUCTIONS[record["text"]] if mode == "instructed" else None
        )
        tts_text = (
            str(record.get("ssml_text") or record["text"])
            if mode == "instructed"
            else record["text"]
        )
        stem = (
            f"{global_index:02d}_{record['shot_id']}_"
            f"{record['line_index']:02d}_{character.lower()}"
        )
        raw_path = line_dir / f"{stem}.mp3"
        wav_path = line_dir / f"{stem}.wav"
        service.synthesize_dialogue(
            text=tts_text,
            voice=voice,
            output_path=raw_path,
            instruction=instruction,
        )
        _normalize_to_wav(raw_path, wav_path)
        duration = _duration(wav_path)
        rendered.append(
            {
                **record,
                "provider_text": tts_text,
                "instruction": instruction,
                "instruction_length": len(instruction) if instruction else 0,
                "voice": voice,
                "raw_path": str(raw_path),
                "wav_path": str(wav_path),
                "duration_seconds": duration,
            }
        )
        shot_lines.setdefault(record["shot_id"], []).append(wav_path)

    gap_path = mode_dir / "gap_300ms.wav"
    _write_silence(gap_path, 0.3)
    shot_paths: list[Path] = []
    for shot_id, paths in shot_lines.items():
        sequence: list[Path] = []
        for index, path in enumerate(paths):
            if index:
                sequence.append(gap_path)
            sequence.append(path)
        shot_path = shot_dir / f"{shot_id}_{mode}.wav"
        _concat(sequence, shot_path)
        shot_paths.append(shot_path)

    scene_sequence: list[Path] = []
    for index, path in enumerate(shot_paths):
        if index:
            scene_sequence.append(gap_path)
        scene_sequence.append(path)
    listen_track = mode_dir / f"scene_002_{mode}_clone_listen_track.wav"
    _concat(scene_sequence, listen_track)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "mode": mode,
        "provider": "dashscope",
        "model": model,
        "instruction_parameter": (
            "omitted (None)" if mode == "bare" else "explicit compact directions"
        ),
        "bare_plain_text_only": mode == "bare",
        "ssml_reused": mode == "instructed",
        "voices": voices,
        "line_count": len(rendered),
        "shot_count": len(shot_paths),
        "lines": rendered,
        "shots": [
            {
                "shot_id": path.stem.removesuffix(f"_{mode}"),
                "path": str(path),
                "duration_seconds": _duration(path),
            }
            for path in shot_paths
        ],
        "listen_track": str(listen_track),
        "listen_track_duration_seconds": _duration(listen_track),
    }
    manifest_path = mode_dir / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("bare", "instructed"))
    args = parser.parse_args()
    render(args.mode)
