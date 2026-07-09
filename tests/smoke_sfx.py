#!/usr/bin/env python3
"""
SMOKE TEST — SFX via StableAudioOpen (stabilityai/stable-audio-open-1.0)
Uses diffusers.StableAudioPipeline (already installed in tests/venvs/video/).

Generates 5 seconds of ambience from a text prompt.
Saves to /tmp/smoke/sfx.wav, prints load + generation time separately.

Run: HF_TOKEN=your_token python3 tests/smoke_sfx.py
Uses venv: tests/venvs/video/ (same venv as LTX-Video smoke test — has diffusers 0.38.0 + scipy)

HF_TOKEN must be set in the environment to access the gated model.
"""

import subprocess
import sys
import os
import time
import traceback
from pathlib import Path

VENV_DIR = Path(__file__).parent / "venvs" / "video"  # diffusers 0.38.0 + scipy
OUTPUT_PATH = Path("/tmp/smoke/sfx.wav")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

PROMPT = "rooftop city ambience, wind, distant traffic, night, atmospheric"
DURATION_S = 5
MODEL_ID = "stabilityai/stable-audio-open-1.0"


def ensure_venv():
    marker = VENV_DIR / ".sfx_ready"
    if marker.exists():
        print("[venv] SFX deps already installed — skipping")
        return

    print(f"[venv] Checking venv at {VENV_DIR} ...")
    pip = VENV_DIR / "bin" / "pip"

    print("[venv] Ensuring scipy, soundfile, and torchsde are installed...")
    t0 = time.time()
    subprocess.run(
        [str(pip), "install", "--quiet", "scipy", "soundfile", "torchsde"],
        check=True,
    )
    marker.touch()
    print(f"[venv] SFX deps ready in {time.time() - t0:.1f}s")


def run_in_venv():
    venv_python = VENV_DIR / "bin" / "python"
    if sys.executable != str(venv_python):
        print(f"[venv] Re-launching inside venv: {venv_python}")
        env = os.environ.copy()
        env["HF_TOKEN"] = env.get("HF_TOKEN", "")
        os.execve(str(venv_python), [str(venv_python)] + sys.argv, env)


def main():
    print("=" * 60)
    print("SMOKE TEST: Stable Audio Open (SFX / ambience)")
    print("=" * 60)

    # Check HF_TOKEN early
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        print("[FATAL] HF_TOKEN environment variable not set.")
        print("  Get a token from https://huggingface.co/settings/tokens")
        print("  Accept the license at: https://huggingface.co/stabilityai/stable-audio-open-1.0")
        sys.exit(1)
    print(f"[auth] HF_TOKEN set (len={len(hf_token)})")

    ensure_venv()
    run_in_venv()
    sys.setrecursionlimit(10000)

    # --- Inside venv from here ---
    import torch  # noqa: PLC0415

    device = "cpu"
    print(f"[config] device={device}  torch={torch.__version__}")
    print(f"[config] model: {MODEL_ID}")
    print(f"[config] prompt: {PROMPT!r}")
    print(f"[config] duration: {DURATION_S}s")

    print("\n[load] Loading Stable Audio Open (downloads ~4GB on first run)...")
    t_load_start = time.time()

    try:
        from diffusers import StableAudioPipeline  # noqa: PLC0415

        pipe = StableAudioPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float32,
            token=hf_token,
        )
        pipe = pipe.to(device)
        from diffusers import DDIMScheduler  # noqa: PLC0415
        pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
    except Exception:
        print("\n[FAIL] Model load failed:")
        traceback.print_exc()
        sys.exit(1)

    t_load_end = time.time()
    load_time = t_load_end - t_load_start
    print(f"[load] Model loaded in {load_time:.2f}s")

    # Stable Audio Open generates at 44.1kHz — for 5 seconds we need ~220500 samples
    # The generate() method takes inference_steps and audio_end_in_s
    print(f"\n[gen] Generating {DURATION_S}s of ambience...")
    t_gen_start = time.time()

    try:
        with torch.no_grad():
            audio = pipe(
                prompt=PROMPT,
                num_inference_steps=50,
                audio_end_in_s=DURATION_S,
                num_waveforms_per_prompt=1,
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
        import soundfile as sf  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        audio_data = audio.audios[0].cpu().numpy()
        sample_rate = pipe.vae.sampling_rate

        # Normalize to int16
        audio_int16 = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        sf.write(str(OUTPUT_PATH), audio_int16.T, sample_rate)
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