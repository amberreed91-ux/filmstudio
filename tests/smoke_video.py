#!/usr/bin/env python3
"""
LOOP 1 SMOKE TEST — LTX-Video (Lightricks)
Generates a 2-second 512x288 clip, saves to /tmp/smoke/video.mp4
Prints wall-clock time for model load and generation separately.

Isolated venv: tests/venvs/video/
Run: python3 tests/smoke_video.py

Model: Lightricks/LTX-Video (~8GB download on first run)
"""

import subprocess
import sys
import os
import time
import traceback
from pathlib import Path

VENV_DIR = Path(__file__).parent / "venvs" / "video"
OUTPUT_PATH = Path("/tmp/smoke/video.mp4")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def ensure_venv():
    marker = VENV_DIR / ".video_ready"
    if marker.exists():
        print("[venv] LTX-Video deps already installed — skipping")
        return

    base_marker = VENV_DIR / ".base_ready"
    if not base_marker.exists():
        print(f"[venv] Creating shared venv at {VENV_DIR} ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        pip = VENV_DIR / "bin" / "pip"
        subprocess.run([str(pip), "install", "--quiet", "--upgrade", "pip"], check=True)
        print("[venv] Installing torch (CPU wheel, ~88MB)...")
        t0 = time.time()
        subprocess.run(
            [str(pip), "install", "--quiet",
             "torch", "torchaudio", "torchvision",
             "--index-url", "https://download.pytorch.org/whl/cpu"],
            check=True,
        )
        print(f"[venv] torch installed in {time.time() - t0:.1f}s")
        base_marker.touch()

    pip = VENV_DIR / "bin" / "pip"
    print("[venv] Installing diffusers + video deps...")
    t0 = time.time()
    subprocess.run(
        [str(pip), "install", "--quiet",
         "diffusers>=0.30.0",
         "transformers>=4.40.0",
         "accelerate>=0.30.0",
         "sentencepiece",
         "imageio[ffmpeg]",
         "numpy"],
        check=True,
    )
    marker.touch()
    print(f"[venv] video deps ready in {time.time() - t0:.1f}s")


def run_in_venv():
    venv_python = VENV_DIR / "bin" / "python"
    if sys.executable != str(venv_python):
        print(f"[venv] Re-launching inside venv: {venv_python}")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def main():
    print("=" * 60)
    print("SMOKE TEST: LTX-Video")
    print("=" * 60)

    ensure_venv()
    run_in_venv()

    # --- Inside venv from here ---
    import torch  # noqa: PLC0415

    # CPU only — no CUDA assumptions. LTX-Video MPS support is experimental.
    device = "cpu"
    print(f"[config] device={device}  torch={torch.__version__}")

    print("\n[load] Loading LTX-Video pipeline (~8GB download on first run)...")
    t_load_start = time.time()

    try:
        from diffusers import LTXPipeline  # noqa: PLC0415
        pipe = LTXPipeline.from_pretrained(
            "Lightricks/LTX-Video",
            torch_dtype=torch.float32,
        )
        pipe = pipe.to(device)
    except Exception:
        print("\n[FAIL] Model load failed:")
        traceback.print_exc()
        sys.exit(1)

    t_load_end = time.time()
    load_time = t_load_end - t_load_start
    print(f"[load] Model loaded in {load_time:.2f}s")

    print("\n[gen] Generating 2-second clip at 512x288 (25 steps)...")
    t_gen_start = time.time()

    try:
        result = pipe(
            prompt="A cinematic close-up of a candle flame flickering in a dark room",
            negative_prompt="blurry, low quality, distorted",
            width=512,
            height=288,
            num_frames=49,          # ~2s at 24fps
            num_inference_steps=25,
            guidance_scale=3.0,
        )
        frames = result.frames[0]   # list of PIL images
    except Exception:
        print("\n[FAIL] Generation failed:")
        traceback.print_exc()
        sys.exit(1)

    t_gen_end = time.time()
    gen_time = t_gen_end - t_gen_start
    print(f"[gen] Generation complete in {gen_time:.2f}s")

    print(f"\n[save] Saving {len(frames)} frames to {OUTPUT_PATH} ...")
    try:
        import imageio  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        writer = imageio.get_writer(str(OUTPUT_PATH), fps=24, quality=7)
        for frame in frames:
            writer.append_data(np.array(frame))
        writer.close()
    except Exception:
        print("\n[FAIL] Save failed:")
        traceback.print_exc()
        sys.exit(1)

    file_size_kb = OUTPUT_PATH.stat().st_size // 1024
    print(f"[save] Saved: {OUTPUT_PATH}  ({file_size_kb} KB)")

    print("\n" + "=" * 60)
    print("RESULT: SUCCESS")
    print(f"  Model load time : {load_time:.2f}s")
    print(f"  Generation time : {gen_time:.2f}s")
    print(f"  Total wall-clock: {load_time + gen_time:.2f}s")
    print(f"  Output          : {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
