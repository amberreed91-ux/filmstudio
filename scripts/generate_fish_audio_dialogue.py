#!/usr/bin/env python3
"""Validate Fish Audio dialogue TTS with a real API call.

Same structure as scripts/generate_elevenlabs_dialogue.py — makes one real
Fish Audio TTS request, saves the audio, and reports character count,
model used, emotion tag applied, and API response time.

Calls _generate_fish_audio_tts_sync directly (not through the dispatch) so
this exercises the actual provider path including emotion-tag formatting
and FFmpeg normalisation to WAV.

Usage:
    FISH_AUDIO_API_KEY=...  python scripts/generate_fish_audio_dialogue.py \
        --text "I told you not to come back here." \
        --emotion angry \
        --voice-id <reference_id> \
        --output outputs/fish_audio_validation/validation.wav
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_BACKEND_ROOT = str(Path(__file__).resolve().parents[1] / "studio-backend")
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
from app.script_guard import refuse_non_approved_provider

refuse_non_approved_provider(
    __file__,
    what="synthesize a dialogue WAV via the Fish Audio TTS API (real call, per-character billing)",
    provider="fish-audio",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a dialogue WAV via the Fish Audio TTS API (real call).",
    )
    parser.add_argument(
        "--text",
        default="I told you not to come back here.",
        help="Dialogue line to synthesize.",
    )
    parser.add_argument(
        "--output",
        default="outputs/fish_audio_validation/validation.wav",
        help="Output WAV path (will be normalised to PCM 16-bit mono 22050 Hz).",
    )
    parser.add_argument(
        "--voice-id",
        default=os.environ.get("FISH_AUDIO_DEFAULT_VOICE_ID", ""),
        help="Fish Audio reference_id (voice model ID). Required.",
    )
    parser.add_argument(
        "--emotion",
        default="angry",
        help='Emotion tag to prepend (e.g. "angry", "whispering", "sad").',
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("FISH_AUDIO_MODEL", "s2-pro"),
        help="Fish Audio model (s2-pro, s2.1-pro, s2.1-pro-free, s1).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("FISH_AUDIO_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({
            "status": "error",
            "error": "FISH_AUDIO_API_KEY is not set in the environment.",
        }, indent=2))
        return 1

    voice_id = args.voice_id.strip()
    if not voice_id:
        print(json.dumps({
            "status": "error",
            "error": (
                "No Fish Audio voice ID provided. Pass --voice-id or set "
                "FISH_AUDIO_DEFAULT_VOICE_ID. Find voice model IDs at "
                "https://fish.audio/voice-library/"
            ),
        }, indent=2))
        return 1

    text = args.text.strip()
    char_count = len(text)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    from app.services.audio_pipeline_service import (
        AudioPipelineService,
        FISH_AUDIO_API_KEY,
        FISH_AUDIO_MODEL,
        FISH_AUDIO_OUTPUT_FORMAT,
    )

    service = AudioPipelineService()

    started = time.time()
    try:
        service._generate_fish_audio_tts_sync(
            text=text,
            output_path=output,
            voice=voice_id,
            emotion_tag=args.emotion,
        )
    except Exception as exc:
        elapsed = time.time() - started
        print(json.dumps({
            "status": "error",
            "elapsed_seconds": round(elapsed, 2),
            "error": str(exc),
            "error_type": type(exc).__name__,
            "chars_sent": char_count,
            "voice_id": voice_id,
            "model": FISH_AUDIO_MODEL,
            "emotion": args.emotion,
        }, indent=2))
        return 2

    elapsed = time.time() - started

    payload = {
        "status": "complete",
        "output": str(output),
        "exists": output.exists(),
        "bytes": output.stat().st_size if output.exists() else 0,
        "chars_sent": char_count,
        "model": FISH_AUDIO_MODEL,
        "voice_id": voice_id,
        "emotion": args.emotion,
        "output_format": FISH_AUDIO_OUTPUT_FORMAT,
        "api_elapsed_seconds": round(elapsed, 2),
    }
    print(json.dumps(payload, indent=2))
    return 0 if output.exists() and output.stat().st_size > 44 else 4


if __name__ == "__main__":
    raise SystemExit(main())
