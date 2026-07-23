#!/usr/bin/env python3
"""Validate ElevenLabs dialogue TTS with a real API call.

Same rigour as scripts/generate_ace_step_score.py — makes one real
ElevenLabs TTS request, saves the audio, and reports character count,
estimated credits consumed, and API response time.

Usage:
    ELEVENLABS_API_KEY=sk_...  python scripts/generate_elevenlabs_dialogue.py \
        --text "I remember the way the light fell that afternoon." \
        --output outputs/elevenlabs_validation/validation.wav
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")
DEFAULT_OUTPUT_FORMAT = os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32")
PRICING_PER_1K = {
    "eleven_flash_v2_5": 0.05,
    "eleven_turbo_v2_5": 0.05,
    "eleven_multilingual_v2": 0.10,
    "eleven_v3": 0.10,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a dialogue WAV via the ElevenLabs TTS API (real call).",
    )
    parser.add_argument(
        "--text",
        default="I remember the way the light fell that afternoon.",
        help="Dialogue line to synthesize.",
    )
    parser.add_argument(
        "--output",
        default="outputs/elevenlabs_validation/validation.wav",
        help="Output WAV path (will be normalised to PCM 16-bit mono 22050 Hz).",
    )
    parser.add_argument(
        "--voice-id",
        default=os.environ.get("ELEVENLABS_DEFAULT_VOICE_ID", DEFAULT_VOICE_ID),
        help="ElevenLabs voice ID.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help="ElevenLabs model ID.",
    )
    parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        help="ElevenLabs output format (codec_sample_rate_bitrate).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({
            "status": "error",
            "error": "ELEVENLABS_API_KEY is not set in the environment.",
        }, indent=2))
        return 1

    text = args.text.strip()
    char_count = len(text)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    url = (
        f"{ELEVENLABS_API_URL}/{args.voice_id}"
        f"?output_format={args.output_format}"
    )
    body = json.dumps({
        "text": text,
        "model_id": args.model_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio_bytes = resp.read()
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        elapsed = time.time() - started
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        print(json.dumps({
            "status": "error",
            "http_status": exc.code,
            "elapsed_seconds": round(elapsed, 2),
            "error": str(exc),
            "error_body": error_body,
            "chars_sent": char_count,
        }, indent=2))
        return 2
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        elapsed = time.time() - started
        print(json.dumps({
            "status": "error",
            "elapsed_seconds": round(elapsed, 2),
            "error": str(exc),
            "chars_sent": char_count,
        }, indent=2))
        return 2

    elapsed = time.time() - started

    # Write raw provider output, then normalise to WAV via FFmpeg.
    raw_path = output.parent / f"{output.stem}_raw.mp3"
    raw_path.write_bytes(audio_bytes)

    ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
    norm_cmd = [
        ffmpeg_bin, "-y",
        "-i", str(raw_path),
        "-ac", "1",
        "-ar", "22050",
        "-sample_fmt", "s16",
        str(output),
    ]
    norm_result = subprocess.run(norm_cmd, capture_output=True, text=True, timeout=30)
    raw_path.unlink(missing_ok=True)

    if norm_result.returncode != 0:
        print(json.dumps({
            "status": "error",
            "error": "FFmpeg normalisation failed",
            "ffmpeg_stderr": norm_result.stderr[-500:],
            "chars_sent": char_count,
            "elapsed_seconds": round(elapsed, 2),
        }, indent=2))
        return 3

    price_per_1k = PRICING_PER_1K.get(args.model_id, 0.10)
    estimated_cost = round(char_count / 1000 * price_per_1k, 6)

    payload = {
        "status": "complete",
        "http_status": status_code,
        "output": str(output),
        "exists": output.exists(),
        "bytes": output.stat().st_size if output.exists() else 0,
        "chars_sent": char_count,
        "model_id": args.model_id,
        "voice_id": args.voice_id,
        "output_format": args.output_format,
        "estimated_credits_consumed": estimated_cost,
        "pricing_per_1k_chars": price_per_1k,
        "api_elapsed_seconds": round(elapsed, 2),
        "raw_audio_bytes": len(audio_bytes),
    }
    print(json.dumps(payload, indent=2))
    return 0 if output.exists() and output.stat().st_size > 44 else 4


if __name__ == "__main__":
    raise SystemExit(main())
