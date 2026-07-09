#!/usr/bin/env python3
"""
LOOP 1 SMOKE TEST — MusicGen-small (facebook/musicgen-small)
Generates 8 seconds of music from a text prompt.
Saves to /tmp/smoke/music.wav, prints load + generation time separately.

Isolated venv: tests/venvs/music/
Run: python3 tests/smoke_music.py

Uses HuggingFace transformers (same weights as Meta AudioCraft MusicGen-small).
AudioCraft 1.3.0 hard-imports xformers at module load — no arm64 CPU wheel exists,
so this venv uses transformers instead. That isolation finding is part of Loop 1.
"""

import subprocess
import sys
import os
import time
import traceback
from pathlib import Path

VENV_DIR = Path(__file__).parent / "venvs" / "music"
OUTPUT_PATH = Path("/tmp/smoke/music.wav")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

PROMPT = "melancholic piano score, slow tempo, emotional, cinematic, solo piano"
DURATION_S = 8
MODEL_ID = "facebook/musicgen-small"


def ensure_venv():
    marker = VENV_DIR / ".music_ready"
    stale_audiocraft = VENV_DIR / "lib" / "python3.11" / "site-packages" / "audiocraft"
    if marker.exists() and stale_audiocraft.exists():
        print("[venv] Stale audiocraft venv detected — removing for transformers rebuild")
        marker.unlink()
    if marker.exists():
        print("[venv] MusicGen deps already installed — skipping")
        return

    print(f"[venv] Creating isolated venv at {VENV_DIR} ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    pip = VENV_DIR / "bin" / "pip"
    subprocess.run([str(pip), "install", "--quiet", "--upgrade", "pip"], check=True)

    print("[venv] Installing torch (CPU) + transformers + scipy...")
    t0 = time.time()
    subprocess.run(
        [str(pip), "install", "--quiet",
         "torch", "torchaudio",
         "--index-url", "https://download.pytorch.org/whl/cpu"],
        check=True,
    )
    subprocess.run(
        [str(pip), "install", "--quiet",
         "transformers>=4.40.0",
         "accelerate",
         "scipy",
         "numpy<2"],
        check=True,
    )
    marker.touch()
    print(f"[venv] MusicGen deps ready in {time.time() - t0:.1f}s")


def run_in_venv():
    venv_python = VENV_DIR / "bin" / "python"
    if sys.executable != str(venv_python):
        print(f"[venv] Re-launching inside venv: {venv_python}")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def main():
    print("=" * 60)
    print("SMOKE TEST: MusicGen-small")
    print("=" * 60)

    ensure_venv()
    run_in_venv()

    # --- Inside venv from here ---
    import torch  # noqa: PLC0415

    device = "cpu"
    print(f"[config] device={device}  torch={torch.__version__}")
    print(f"[config] model: {MODEL_ID}")
    print(f"[config] prompt: {PROMPT!r}")
    print(f"[config] duration: {DURATION_S}s")

    print("\n[load] Loading MusicGen-small (downloads ~2GB on first run)...")
    t_load_start = time.time()

    try:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration  # noqa: PLC0415

        processor = AutoProcessor.from_pretrained(MODEL_ID)
        model = MusicgenForConditionalGeneration.from_pretrained(MODEL_ID)
        model = model.to(device)
        model.eval()
    except Exception:
        print("\n[FAIL] Model load failed:")
        traceback.print_exc()
        sys.exit(1)

    t_load_end = time.time()
    load_time = t_load_end - t_load_start
    print(f"[load] Model loaded in {load_time:.2f}s")

    frame_rate = model.config.audio_encoder.frame_rate
    max_new_tokens = int(DURATION_S * frame_rate + 3)
    sample_rate = model.config.audio_encoder.sampling_rate

    print(f"\n[gen] Generating {DURATION_S}s of music ({max_new_tokens} tokens)...")
    t_gen_start = time.time()

    try:
        inputs = processor(text=[PROMPT], padding=True, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            audio_values = model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=3.0,
                max_new_tokens=max_new_tokens,
            )
    except Exception:
        print("\n[FAIL] Generation failed:")
        traceback.print_exc()
        sys.exit(1)

    t_gen_end = time.time()
    gen_time = t_gen_end - t_gen_start
    print(f"[gen] Generation complete in {gen_time:.2f}s")

    print(f"\n[save] Saving to {OUTPUT_PATH} ...")
    try:
        import scipy.io.wavfile as wavfile  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        audio = audio_values[0, 0].cpu().numpy()
        audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        wavfile.write(str(OUTPUT_PATH), sample_rate, audio_int16)
    except Exception:
        print("\n[FAIL] Save failed:")
        traceback.print_exc()
        sys.exit(1)

    file_size_kb = OUTPUT_PATH.stat().st_size // 1024
    print(f"[save] Saved: {OUTPUT_PATH}  ({file_size_kb} KB, {sample_rate}Hz)")

    print("\n" + "=" * 60)
    print("RESULT: SUCCESS")
    print(f"  Model load time : {load_time:.2f}s")
    print(f"  Generation time : {gen_time:.2f}s")
    print(f"  Total wall-clock: {load_time + gen_time:.2f}s")
    print(f"  Output          : {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
