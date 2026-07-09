#!/usr/bin/env python3
"""
LOOP 2: Single Shot End-to-End — Real Pipeline, Real Output
================================================================
Proves the full pipeline works as a system. One scene, three shots,
all four modalities wired together, one composited MP4 out.

Hardcoded scene definition (no UI, no API call):
  s1: empty rain-soaked street at night, neon reflections, wide shot — "Nothing ever changes here." — 4.0s
  s2: close up of a pay phone ringing, cinematic, shallow depth of field — "Or does it." — 3.0s
  s3: woman walking away into fog, long shot, moody — "" (no dialogue) — 5.0s
  music: "melancholic piano, sparse, cinematic, minor key"
  sfx:   "rain ambience, distant city sounds, night"

Generation (parallel per-shot via asyncio.gather):
  - Video via LTX-Video (diffusers LTXPipeline)
  - Dialogue via Piper TTS where dialogue is non-empty

Scene-level generation:
  - One music clip (MusicGen-small via transformers)
  - One SFX/ambience clip (Stable Audio Open via diffusers)

Composition (via FFmpeg):
  - Per shot: mix dialogue at 0dB, music ducked -12dB, SFX at -6dB
  - Concatenate all shots
  - Output: /tmp/studio/loop2_test.mp4 (H.264/AAC)

CPU/GPU: torch.cuda.is_available() auto-switch — no separate code paths.

Usage:
  HF_TOKEN=your_token python3 scripts/test_pipeline.py

Exit condition:
  /tmp/studio/loop2_test.mp4 exists, real size (> 100KB), plays video + synced audio.
"""

import asyncio
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

# ── Where to put things ───────────────────────────────────────────────
VENV_DIR = Path(__file__).parent.parent / "tests" / "venvs" / "pipeline"
OUTPUT_DIR = Path("/tmp/studio")
OUTPUT_FILE = OUTPUT_DIR / "loop2_test.mp4"
SCRATCH_DIR = OUTPUT_DIR / "scratch"

# Voice model for Piper
VOICE_MODEL = (
    Path(__file__).parent.parent / "tests" / "voices" / "en_US-lessac-medium.onnx"
)

# ── Hardcoded scene definition ────────────────────────────────────────
SCENE = {
    "scene_id": "loop2-test",
    "shots": [
        {
            "shot_id": "s1",
            "prompt": "empty rain-soaked street at night, neon reflections, wide shot",
            "dialogue": "Nothing ever changes here.",
            "duration_s": 4.0,
        },
        {
            "shot_id": "s2",
            "prompt": "close up of a pay phone ringing, cinematic, shallow depth of field",
            "dialogue": "Or does it.",
            "duration_s": 3.0,
        },
        {
            "shot_id": "s3",
            "prompt": "woman walking away into fog, long shot, moody",
            "dialogue": "",
            "duration_s": 5.0,
        },
    ],
    "music_prompt": "melancholic piano, sparse, cinematic, minor key",
    "sfx_prompt": "rain ambience, distant city sounds, night",
}

# ── Global device (set after torch import inside venv) ────────────────
DEVICE = "cpu"


# ══════════════════════════════════════════════════════════════════════
#  VENV BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════
def ensure_venv():
    """Create/verify the pipeline venv with ALL required deps."""
    marker = VENV_DIR / ".pipeline_ready"
    if marker.exists():
        print("[venv] All deps already installed — skipping")
        return

    print(f"[venv] Creating isolated venv at {VENV_DIR} ...")
    VENV_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    pip = VENV_DIR / "bin" / "pip"
    subprocess.run([str(pip), "install", "--quiet", "--upgrade", "pip"], check=True)

    t0 = time.time()

    # ── 1. Install PyTorch (CPU wheel, ~88MB) ──────────────────────
    # NOTE: Pin torch 2.12.0 explicitly — 2.12.1 has meta tensor issues
    # with diffusers+transformers 5.x on CPU
    print("[venv] Installing torch (CPU wheel, pinned 2.12.0)...")
    subprocess.run(
        [
            str(pip), "install", "--quiet",
            "torch==2.12.0", "torchaudio", "torchvision",
            "--index-url", "https://download.pytorch.org/whl/cpu",
        ],
        check=True,
    )

    # ── 2. Install diffusers + video deps (LTX-Video + StableAudio) ─
    print("[venv] Installing diffusers + video deps...")
    subprocess.run(
        [
            str(pip), "install", "--quiet",
            "diffusers>=0.30.0",
            "transformers>=4.40.0",
            "accelerate>=0.30.0",
            "sentencepiece",
            "imageio[ffmpeg]",
            "numpy<2",
            "scipy",
            "soundfile",
        ],
        check=True,
    )

    # ── 3. Install piper-tts (ONNX — no build steps) ───────────────
    print("[venv] Installing piper-tts...")
    subprocess.run(
        [str(pip), "install", "--quiet", "piper-tts"],
        check=True,
    )

    # ── 4. Verify torchsde for StableAudioOpen if needed ───────────
    #     (Some diffusers versions need it; install quietly)
    subprocess.run(
        [str(pip), "install", "--quiet", "torchsde"],
        check=False,  # optional
    )

    marker.touch()
    print(f"[venv] All deps installed in {time.time() - t0:.1f}s")


def run_in_venv():
    """Re-execute this script inside the pipeline venv."""
    venv_python = VENV_DIR / "bin" / "python"
    if sys.executable != str(venv_python):
        print(f"[venv] Re-launching inside venv: {venv_python}")
        env = os.environ.copy()
        env["HF_TOKEN"] = env.get("HF_TOKEN", "")
        os.execve(str(venv_python), [str(venv_python)] + sys.argv, env)


# ══════════════════════════════════════════════════════════════════════
#  GENERATION FUNCTIONS (inside venv)
# ══════════════════════════════════════════════════════════════════════
def generate_video(shot_id: str, prompt: str, duration_s: float) -> Path:
    """Generate a video clip using LTX-Video. Returns path to .mp4."""
    import torch  # noqa: PLC0415
    from diffusers import LTXPipeline  # noqa: PLC0415

    output_path = SCRATCH_DIR / f"{shot_id}_video.mp4"

    print(f"\n[VIDEO:{shot_id}] Generating video for: {prompt!r}")
    t0 = time.time()

    pipe = LTXPipeline.from_pretrained(
        "Lightricks/LTX-Video",
        torch_dtype=torch.float32,
        device_map=None,  # prevent meta-tensor init on torch 2.12.x
    )
    # CPU is the default after from_pretrained(); only move if non-CPU
    if DEVICE != "cpu":
        pipe = pipe.to(DEVICE)

    num_frames = max(25, int(duration_s * 24))  # 24fps, minimum 25 frames
    print(f"  [VIDEO:{shot_id}] num_frames={num_frames}, device={DEVICE}")

    result = pipe(
        prompt=prompt,
        negative_prompt="blurry, low quality, distorted",
        width=512,
        height=288,
        num_frames=num_frames,
        num_inference_steps=25,
        guidance_scale=3.0,
    )
    frames = result.frames[0]

    import imageio  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    writer = imageio.get_writer(str(output_path), fps=24, quality=7)
    for frame in frames:
        writer.append_data(np.array(frame))
    writer.close()

    size_kb = output_path.stat().st_size // 1024
    print(f"  [VIDEO:{shot_id}] Done in {time.time() - t0:.1f}s — {size_kb} KB")
    return output_path


def generate_dialogue(shot_id: str, text: str) -> Path | None:
    """Generate dialogue via Piper TTS. Returns path to .wav or None if empty."""
    if not text:
        return None

    import wave  # noqa: PLC0415
    from piper.voice import PiperVoice  # noqa: PLC0415

    output_path = SCRATCH_DIR / f"{shot_id}_dialogue.wav"

    print(f"\n[DIALOGUE:{shot_id}] Synthesizing: {text!r}")
    t0 = time.time()

    voice = PiperVoice.load(str(VOICE_MODEL), use_cuda=False)

    with wave.open(str(output_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    size_kb = output_path.stat().st_size // 1024
    print(f"  [DIALOGUE:{shot_id}] Done in {time.time() - t0:.1f}s — {size_kb} KB")
    return output_path


def generate_music() -> Path:
    """Generate scene-level music via MusicGen-small. Returns path to .wav."""
    import torch  # noqa: PLC0415
    from transformers import AutoProcessor, MusicgenForConditionalGeneration  # noqa: PLC0415

    output_path = SCRATCH_DIR / "music.wav"

    duration_s = sum(s["duration_s"] for s in SCENE["shots"])  # total scene length
    print(f"\n[MUSIC] Generating {duration_s}s music: {SCENE['music_prompt']!r}")
    t0 = time.time()

    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")
    model = model.to(DEVICE)
    model.eval()

    frame_rate = model.config.audio_encoder.frame_rate
    max_new_tokens = int(duration_s * frame_rate + 3)
    sample_rate = model.config.audio_encoder.sampling_rate

    inputs = processor(text=[SCENE["music_prompt"]], padding=True, return_tensors="pt")
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

    with torch.no_grad():
        audio_values = model.generate(
            **inputs,
            do_sample=True,
            guidance_scale=3.0,
            max_new_tokens=max_new_tokens,
        )

    import numpy as np  # noqa: PLC0415
    import scipy.io.wavfile as wavfile  # noqa: PLC0415

    audio = audio_values[0, 0].cpu().numpy()
    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    wavfile.write(str(output_path), sample_rate, audio_int16)

    size_kb = output_path.stat().st_size // 1024
    print(f"  [MUSIC] Done in {time.time() - t0:.1f}s — {size_kb} KB, {sample_rate} Hz")
    return output_path


def generate_sfx() -> Path:
    """Generate scene-level SFX/ambience via Stable Audio Open. Returns path to .wav."""
    import torch  # noqa: PLC0415
    from diffusers import StableAudioPipeline  # noqa: PLC0415
    from diffusers import DDIMScheduler  # noqa: PLC0415

    output_path = SCRATCH_DIR / "sfx.wav"
    hf_token = os.environ.get("HF_TOKEN", "")

    duration_s = sum(s["duration_s"] for s in SCENE["shots"])
    print(f"\n[SFX] Generating {duration_s}s ambience: {SCENE['sfx_prompt']!r}")
    t0 = time.time()

    pipe = StableAudioPipeline.from_pretrained(
        "stabilityai/stable-audio-open-1.0",
        torch_dtype=torch.float32,
        token=hf_token,
    )
    pipe = pipe.to(DEVICE)
    pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)

    with torch.no_grad():
        audio = pipe(
            prompt=SCENE["sfx_prompt"],
            num_inference_steps=50,
            audio_end_in_s=duration_s,
            num_waveforms_per_prompt=1,
        )

    import soundfile as sf  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    audio_data = audio.audios[0].cpu().numpy()
    sample_rate = pipe.vae.sampling_rate

    audio_int16 = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
    sf.write(str(output_path), audio_int16.T, sample_rate)

    size_kb = output_path.stat().st_size // 1024
    print(f"  [SFX] Done in {time.time() - t0:.1f}s — {size_kb} KB, {sample_rate} Hz")
    return output_path


async def generate_shot(shot: dict) -> dict:
    """Generate video + dialogue for a single shot (parallel within shot)."""
    shot_id = shot["shot_id"]

    # Run video + dialogue in parallel within each shot
    video_future = asyncio.to_thread(generate_video, shot_id, shot["prompt"], shot["duration_s"])
    dialogue_future = asyncio.to_thread(generate_dialogue, shot_id, shot["dialogue"])

    video_path, dialogue_path = await asyncio.gather(video_future, dialogue_future)

    return {
        "shot_id": shot_id,
        "video": video_path,
        "dialogue": dialogue_path,
        "duration_s": shot["duration_s"],
    }


async def generate_all_assets() -> tuple[list[dict], Path, Path]:
    """Generate all assets. Returns (shot_results, music_path, sfx_path)."""

    # ── Generate per-shot assets in parallel ────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 1: Generating per-shot video + dialogue (parallel)")
    print("=" * 60)
    shot_tasks = [generate_shot(shot) for shot in SCENE["shots"]]
    shot_results = await asyncio.gather(*shot_tasks)

    # ── Generate scene-level music + SFX (parallel) ────────────────
    print("\n" + "=" * 60)
    print("PHASE 2: Generating scene-level music + SFX (parallel)")
    print("=" * 60)
    music_future = asyncio.to_thread(generate_music)
    sfx_future = asyncio.to_thread(generate_sfx)
    music_path, sfx_path = await asyncio.gather(music_future, sfx_future)

    return shot_results, music_path, sfx_path


# ══════════════════════════════════════════════════════════════════════
#  FFMPEG COMPOSITION
# ══════════════════════════════════════════════════════════════════════
def build_shot_mix(
    shot: dict,
    shot_index: int,
    music_path: Path,
    sfx_path: Path,
) -> Path:
    """
    Build a single shot mix using FFmpeg:
      - Video from the shot's video clip
      - Audio: dialogue at 0dB + music segment at -12dB + SFX segment at -6dB

    The music and SFX are cropped to this shot's time window.
    Output: scratch/{shot_id}_mixed.mp4
    """
    shot_id = shot["shot_id"]
    output_path = SCRATCH_DIR / f"{shot_id}_mixed.mp4"

    # Calculate start time (cumulative from previous shots)
    start_time = sum(
        SCENE["shots"][i]["duration_s"] for i in range(shot_index)
    )
    duration = shot["duration_s"]

    print(f"\n[MIX:{shot_id}] Building mix (start={start_time:.1f}s, dur={duration:.1f}s)")

    # ── Build FFmpeg command ──────────────────────────────────────
    # Inputs:
    #   0: shot video (has no audio)
    #   1: music (will be cropped)
    #   2: sfx   (will be cropped)
    #   [3]: dialogue (optional)
    #
    # Filter graph:
    #   [1]atrim,volume=-12dB[music_trim]
    #   [2]atrim,volume=-6dB[sfx_trim]
    #   [3]volume=0dB[dialogue_trim]  (if dialogue exists)
    #   Then amix all audio streams, then map video + mixed audio.

    cmd = [
        "ffmpeg",
        "-y",  # overwrite output
        "-i", str(shot["video"]),
        "-ss", str(start_time),
        "-i", str(music_path),
        "-ss", str(start_time),
        "-i", str(sfx_path),
    ]

    # ── Build filter_complex ──────────────────────────────────────
    filter_parts = []

    # Trim music to shot duration and apply -12dB
    filter_parts.append(
        f"[1:a]atrim=start=0:duration={duration},volume=-12dB[music_trim]"
    )
    # Trim SFX to shot duration and apply -6dB
    filter_parts.append(
        f"[2:a]atrim=start=0:duration={duration},volume=-6dB[sfx_trim]"
    )

    audio_inputs = "[music_trim][sfx_trim]"
    audio_count = 2

    if shot["dialogue"] and shot["dialogue"] != "":
        dialogue_path = shot.get("dialogue_path")
        if dialogue_path and Path(dialogue_path).exists():
            cmd.extend(["-i", str(dialogue_path)])
            # Dialogue at full volume, cropped to match duration
            filter_parts.append(
                f"[{audio_count}:a]atrim=start=0:duration={duration},volume=0dB[dialogue_trim]"
            )
            audio_inputs += "[dialogue_trim]"
            audio_count += 1

    # Amix all audio streams
    filter_parts.append(f"{audio_inputs}amix=inputs={audio_count}:duration=first[aout]")

    # Map video from input 0 and mixed audio
    filter_complex = ";".join(filter_parts)

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "0:v:0",  # video from first input (shot video)
        "-map", "[aout]",  # mixed audio
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ])

    subprocess.run(cmd, check=True, capture_output=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  [MIX:{shot_id}] Done — {size_kb} KB")
    return output_path


def build_shot_mix_wrapper(shot_result: dict, shot_index: int, music_path: Path, sfx_path: Path) -> Path:
    """Wrapper for asyncio.to_thread."""
    return build_shot_mix(shot_result, shot_index, music_path, sfx_path)


def concatenate_shots(shot_paths: list[Path], output_path: Path):
    """Concatenate mixed shots via FFmpeg concat demuxer."""
    print(f"\n[CONCAT] Concatenating {len(shot_paths)} shots into {output_path}")

    # Create concat file
    concat_file = SCRATCH_DIR / "concat_list.txt"
    with open(concat_file, "w") as f:
        for sp in shot_paths:
            f.write(f"file '{sp}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    concat_file.unlink()  # clean up temp file


async def compose_film(
    shot_results: list[dict],
    music_path: Path,
    sfx_path: Path,
) -> Path:
    """Compose the final film: mix each shot, then concatenate."""
    print("\n" + "=" * 60)
    print("PHASE 3: Composing film — mixing + concatenation")
    print("=" * 60)

    # ── Attach dialogue paths to shot_results ──────────────────────
    # (shot_results already have "dialogue" key pointing to Path)
    for i, shot in enumerate(shot_results):
        if shot["dialogue"] and Path(shot["dialogue"]).exists():
            shot["dialogue_path"] = shot["dialogue"]
        else:
            shot["dialogue_path"] = None

    # ── Mix each shot (parallel) ───────────────────────────────────
    mix_tasks = [
        asyncio.to_thread(
            build_shot_mix_wrapper,
            shot,
            i,
            music_path,
            sfx_path,
        )
        for i, shot in enumerate(shot_results)
    ]
    mixed_paths = await asyncio.gather(*mix_tasks)

    # ── Concatenate all mixed shots ────────────────────────────────
    concatenate_shots(mixed_paths, OUTPUT_FILE)

    return OUTPUT_FILE


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    global DEVICE

    print("=" * 70)
    print("LOOP 2: Single Shot End-to-End Pipeline")
    print("=" * 70)
    print(f"Scene: {SCENE['scene_id']} — {len(SCENE['shots'])} shots")
    total_duration = sum(s["duration_s"] for s in SCENE["shots"])
    print(f"Total duration: {total_duration}s")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Scratch: {SCRATCH_DIR}")
    print()

    # ── Check HF_TOKEN early (needed for StableAudioOpen) ─────────
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        print("[FATAL] HF_TOKEN environment variable not set.")
        print("  Get a token from https://huggingface.co/settings/tokens")
        print("  Accept the license at: https://huggingface.co/stabilityai/stable-audio-open-1.0")
        sys.exit(1)
    print(f"[auth] HF_TOKEN set (len={len(hf_token)})")

    # ── Verify voice model exists ──────────────────────────────────
    if not VOICE_MODEL.exists():
        print(f"[FATAL] Voice model not found: {VOICE_MODEL}")
        print("  Download it first:")
        print("    curl -L -o tests/voices/en_US-lessac-medium.onnx \\")
        print("      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx")
        print("    curl -L -o tests/voices/en_US-lessac-medium.onnx.json \\")
        print("      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json")
        sys.exit(1)

    # ── Venv bootstrap ─────────────────────────────────────────────
    ensure_venv()
    run_in_venv()

    # ── Inside venv from here ──────────────────────────────────────
    import torch  # noqa: PLC0415

    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[config] PyTorch {torch.__version__} — device={DEVICE}")
    if DEVICE == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    # Eager-import all heavy libraries here (main thread) to avoid
    # race conditions when asyncio threads try to import simultaneously.
    from diffusers import LTXPipeline, StableAudioPipeline, DDIMScheduler  # noqa: PLC0415
    from transformers import AutoProcessor, MusicgenForConditionalGeneration  # noqa: PLC0415
    import imageio  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import scipy.io.wavfile as wavfile  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415

    # ── Set up directories ─────────────────────────────────────────
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Track wall-clock time ──────────────────────────────────────
    wall_start = time.time()

    try:
        # ── Generate all assets ────────────────────────────────────
        shot_results, music_path, sfx_path = asyncio.run(generate_all_assets())
        print("[GATE] All video + audio assets generated — proceeding to composition")
        print(f"  Shots: {len(shot_results)}, music={music_path}, sfx={sfx_path}")

        # ── Compose the film ───────────────────────────────────────
        print("[GATE] Starting film composition (FFmpeg mix + concat)")
        final_path = asyncio.run(compose_film(shot_results, music_path, sfx_path))
        print(f"[GATE] compose_film returned: {final_path}")
        print(f"[GATE] File exists after compose: {final_path.exists()}")

        wall_elapsed = time.time() - wall_start

        # ── Verify output ──────────────────────────────────────────
        print("[GATE] Verifying output file")
        print("\n" + "=" * 60)
        if final_path.exists():
            file_size_kb = final_path.stat().st_size // 1024
            print(f"[GATE] output_exists=True size_kb={file_size_kb}")
            print(f"  Output: {final_path}")
            print(f"  Size:   {file_size_kb} KB")

            if file_size_kb > 100:
                print("\n  ✓ EXIT CONDITION MET")
                print("  ✓ /tmp/studio/loop2_test.mp4 exists")
                print(f"  ✓ File size ({file_size_kb} KB) > 100 KB")
                print("  ✓ Video (H.264) + Audio (AAC) should play back")
            else:
                print(f"\n  ⚠ EXIT CONDITION PARTIAL — file exists but size ({file_size_kb} KB) < 100 KB")
        else:
            print(f"[GATE] output_exists=False — {final_path} does not exist")
            print(f"\n  ✗ EXIT CONDITION FAILED — {final_path} does not exist")

        print(f"\n  Total wall-clock time: {wall_elapsed:.1f}s")
        print(f"  ({total_duration}s of footage in {wall_elapsed:.1f}s)")

        print("\n" + "=" * 60)
        print("RESULT: LOOP 2 END-TO-END TEST COMPLETE")
        print("=" * 60)

    except Exception:
        print("\n[FAIL] Pipeline failed:")
        traceback.print_exc()
        sys.exit(1)

    # ── Clean up scratch? Keep for debugging ──────────────────────
    # import shutil
    # shutil.rmtree(SCRATCH_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()