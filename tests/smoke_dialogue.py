#!/usr/bin/env python3
"""
LOOP 1 SMOKE TEST — Piper TTS
Synthesizes one line of dialogue using Piper TTS (ONNX, CPU-only).
Saves to /tmp/smoke/dialogue.wav, prints load + generation time separately.

Isolated venv: tests/venvs/dialogue_piper/
Run: python3 tests/smoke_dialogue.py

Piper is ONNX-based — no PyTorch needed. Voice model loaded from:
  tests/voices/en_US-lessac-medium.onnx
"""

import subprocess
import sys
import os
import time
import traceback
from pathlib import Path

VENV_DIR = Path(__file__).parent / "venvs" / "dialogue_piper"
VOICE_MODEL = Path(__file__).parent / "voices" / "en_US-lessac-medium.onnx"
OUTPUT_PATH = Path("/tmp/smoke/dialogue.wav")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SYNTH_TEXT = (
    "The light fades slowly over the rooftop, "
    "and she realizes this is the last time she will see the city like this."
)


def ensure_venv():
    marker = VENV_DIR / ".piper_ready"
    if marker.exists():
        print("[venv] Piper deps already installed — skipping")
        return

    print(f"[venv] Creating venv at {VENV_DIR} ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    pip = VENV_DIR / "bin" / "pip"
    subprocess.run([str(pip), "install", "--quiet", "--upgrade", "pip"], check=True)

    print("[venv] Installing piper-tts (ONNX — no build steps)...")
    t0 = time.time()
    subprocess.run([str(pip), "install", "--quiet", "piper-tts"], check=True)
    print(f"[venv] piper-tts installed in {time.time() - t0:.1f}s")

    marker.touch()
    print("[venv] Piper ready")


def run_in_venv():
    venv_python = VENV_DIR / "bin" / "python"
    if sys.executable != str(venv_python):
        print(f"[venv] Re-launching inside venv: {venv_python}")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def main():
    print("=" * 60)
    print("SMOKE TEST: Piper TTS (ONNX / CPU)")
    print("=" * 60)

    ensure_venv()
    run_in_venv()

    # --- Inside venv from here ---
    print(f"[config] voice model: {VOICE_MODEL}")
    print(f"[config] text: {SYNTH_TEXT!r}")

    # Verify voice model exists
    if not VOICE_MODEL.exists():
        print(f"\n[FAIL] Voice model not found: {VOICE_MODEL}")
        print("  Download it first:")
        print("    mkdir -p tests/voices")
        print("    curl -L -o tests/voices/en_US-lessac-medium.onnx \\")
        print("      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx")
        print("    curl -L -o tests/voices/en_US-lessac-medium.onnx.json \\")
        print("      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json")
        sys.exit(1)

    # ---- Step 1: Load Piper voice model (CPU only) ----
    print("\n[load] Loading Piper voice model...")
    t_load_start = time.time()

    try:
        import wave  # noqa: PLC0415
        from piper.voice import PiperVoice  # noqa: PLC0415

        voice = PiperVoice.load(
            str(VOICE_MODEL),
            use_cuda=False,  # CPU only — Piper is fast without GPU
        )
    except Exception:
        print("\n[FAIL] Model load failed:")
        traceback.print_exc()
        sys.exit(1)

    t_load_end = time.time()
    load_time = t_load_end - t_load_start
    print(f"[load] Model loaded in {load_time:.2f}s")

    # ---- Step 2: Synthesize dialogue to WAV ----
    print(f"\n[gen] Synthesizing dialogue...")
    t_gen_start = time.time()

    try:
        with wave.open(str(OUTPUT_PATH), "wb") as wav_file:
            voice.synthesize_wav(SYNTH_TEXT, wav_file)
    except Exception:
        print("\n[FAIL] Synthesis failed:")
        traceback.print_exc()
        sys.exit(1)

    t_gen_end = time.time()
    gen_time = t_gen_end - t_gen_start
    print(f"[gen] Dialogue generation complete in {gen_time:.2f}s")

    file_size_kb = OUTPUT_PATH.stat().st_size // 1024
    print(f"[save] Output: {OUTPUT_PATH}  ({file_size_kb} KB)")

    print("\n" + "=" * 60)
    print("RESULT: SUCCESS")
    print(f"  Model load time : {load_time:.2f}s")
    print(f"  Generation time : {gen_time:.2f}s")
    print(f"  Total wall-clock: {load_time + gen_time:.2f}s")
    print(f"  Output          : {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()