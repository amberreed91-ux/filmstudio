#!/usr/bin/env python3
"""Convert a performed dialogue take with ElevenLabs Voice Changer.

This is speech-to-speech voice conversion, not text-to-speech. The uploaded
audio carries the timing, content, and performance; ``--voice-id`` selects the
target timbre.

Usage:
    ELEVENLABS_API_KEY=... python scripts/convert_elevenlabs_voice_changer.py \
        --input studio-backend/outputs/voice_conversion_scene_002/human_takes/dre_take_01.wav \
        --voice-id <elevenlabs-target-voice-id> \
        --output studio-backend/outputs/voice_conversion_scene_002/converted/dre_take_01_converted.wav
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.elevenlabs.io/v1/speech-to-speech"
DEFAULT_MODEL_ID = os.environ.get("ELEVENLABS_STS_MODEL_ID", "eleven_multilingual_sts_v2")
DEFAULT_OUTPUT_FORMAT = os.environ.get("ELEVENLABS_STS_OUTPUT_FORMAT", "mp3_44100_128")
VOICE_CHANGER_PRICE_PER_MINUTE_USD = 0.120


def _ffprobe(path: Path) -> dict[str, Any]:
    cmd = [
        os.environ.get("FFPROBE_BIN", "ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    return json.loads(subprocess.check_output(cmd, text=True))


def _duration_seconds(probe: dict[str, Any]) -> float:
    try:
        return float((probe.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _multipart_form(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----codex-voice-conversion-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {media_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), boundary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run ElevenLabs speech-to-speech voice conversion on a real performance take.",
    )
    parser.add_argument("--input", required=True, help="Source human performance audio.")
    parser.add_argument("--voice-id", required=True, help="Target ElevenLabs voice ID.")
    parser.add_argument("--output", required=True, help="Converted audio output path.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT)
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional JSON manifest path. Defaults to <output>.json.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"status": "error", "error": "ELEVENLABS_API_KEY is not set."}, indent=2))
        return 1

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size <= 44:
        print(json.dumps({"status": "error", "error": f"missing or empty input: {input_path}"}, indent=2))
        return 1

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest
        else output_path.with_suffix(output_path.suffix + ".json")
    )

    source_probe = _ffprobe(input_path)
    source_seconds = _duration_seconds(source_probe)
    body, boundary = _multipart_form(
        fields={"model_id": args.model_id},
        file_field="audio",
        file_path=input_path,
    )
    url = f"{API_URL}/{args.voice_id}?output_format={args.output_format}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "audio/*",
        },
        method="POST",
    )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio_bytes = resp.read()
            http_status = resp.status
    except urllib.error.HTTPError as exc:
        elapsed = time.time() - started
        error_body = exc.read().decode("utf-8", errors="replace")[:1000]
        print(
            json.dumps(
                {
                    "status": "error",
                    "http_status": exc.code,
                    "elapsed_seconds": round(elapsed, 3),
                    "error_body": error_body,
                },
                indent=2,
            )
        )
        return 2
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        elapsed = time.time() - started
        print(
            json.dumps(
                {
                    "status": "error",
                    "elapsed_seconds": round(elapsed, 3),
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 2

    output_path.write_bytes(audio_bytes)
    elapsed = time.time() - started
    estimated_cost = source_seconds / 60.0 * VOICE_CHANGER_PRICE_PER_MINUTE_USD
    manifest = {
        "status": "complete",
        "provider": "elevenlabs",
        "api": "voice_changer_speech_to_speech",
        "source_audio": str(input_path),
        "source_audio_probe": source_probe,
        "target_voice_id": args.voice_id,
        "model_id": args.model_id,
        "output_format": args.output_format,
        "output": str(output_path),
        "http_status": http_status,
        "output_bytes": len(audio_bytes),
        "api_elapsed_seconds": round(elapsed, 3),
        "estimated_cost_usd": round(estimated_cost, 6),
        "pricing_basis": {
            "price_per_processed_minute_usd": VOICE_CHANGER_PRICE_PER_MINUTE_USD,
            "source_duration_seconds": source_seconds,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if output_path.exists() and output_path.stat().st_size > 44 else 3


if __name__ == "__main__":
    raise SystemExit(main())
