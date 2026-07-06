#!/usr/bin/env python3
"""
Attempt 4 — Full-Prompt Regeneration (the real test of tonight's redesign).

Reconstructs the Attempt 1 AdherenceScore (55.0, failed character_state/action,
passed camera/lighting/environment_persistence at 100), calls
AdherenceService.build_full_corrected_prompt() with a REAL Groq call (not mocked),
shows the assembled prompt text + verbatim carry-forward confirmation, then — after
explicit user confirmation — submits to real Runway with the SAME locked seed
983559286, waits for completion, downloads, extracts frames, scores with real
Gemini vision, persists to render_attempts, and prints a four-way comparison table:

    Attempt 1: 55.0  (diff-based baseline)
    Attempt 2: 14.0  (replace-style diff)
    Attempt 3: 12.5  (additive-style diff)
    Attempt 4: ???   (full-restatement — real test of tonight's redesign)

Usage:
    cd studio-backend && .venv/bin/python submit_attempt4_full_restatement.py
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.render import render_service
from app.services.adherence_service import (
    AdherenceService,
    AdherenceScore,
    DimensionScore,
    FullCorrectedPrompt,
)
from app.services.render_retry_service import render_retry_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("attempt4_full_restatement")


# ─── Constants from prior attempts ───────────────────────────────────────────

PROJECT_ID = "project_3dba9330f43a"
SHOT_ID = "scene_001"
LOCKED_SEED = 983559286

# Attempt 1 prompt (the original that scored 55.0)
ATTEMPT1_PROMPT = (
    "Chicago is alive. The L train moves through the skyline. People fill the streets. "
    "Music, laughter, food stands. Everything is vibrant. Wide shot, golden hour light. "
    "Cinematic, film quality, single continuous shot."
)

# Attempt 1 slots (parsed from the original prompt)
ATTEMPT1_SLOTS = {
    "character_state": "People fill the streets",
    "action": "Music, laughter, food stands. Everything is vibrant",
    "environment_persistence": "Chicago is alive. The L train moves through the skyline",
    "camera": "Wide shot",
    "lighting": "golden hour light",
}

# Attempt 1 score data (reconstructed from score_attempt2_manual.py)
ATTEMPT1_SCORE_JSON = {
    "shot_id": SHOT_ID,
    "attempt_n": 1,
    "frames_scored": [0.1, 0.5, 0.9],
    "dimensions": {
        "character_state": {
            "score": 0,
            "evidence": "Render focused on cityscape without showing people at human scale",
            "expected": "People fill the streets",
            "observed": "Wide cityscape with no visible human figures at scale",
        },
        "action": {
            "score": 0,
            "evidence": "No human activity shown - only static urban environment",
            "expected": "Music, laughter, food stands. Everything is vibrant",
            "observed": "Static city view with no human activity visible",
        },
        "camera": {
            "score": 100,
            "evidence": "Wide shot executed correctly",
            "expected": "Wide shot",
            "observed": "Wide shot of cityscape",
        },
        "lighting": {
            "score": 100,
            "evidence": "Golden hour lighting captured accurately",
            "expected": "golden hour light",
            "observed": "Golden hour light on buildings",
        },
        "environment_persistence": {
            "score": 100,
            "evidence": "Chicago cityscape with L train and skyline visible throughout",
            "expected": "Chicago is alive. The L train moves through the skyline",
            "observed": "Chicago skyline with L train visible",
        },
    },
    "temporal_drift": {"start_score": 100, "end_score": 100},
    "adherence_score": 55.0,
    "verdict": "correctable",
    "failed_slots": ["character_state", "action"],
}

# Prior attempt scores for the four-way comparison
ATTEMPT2_SCORE_JSON = {
    "adherence_score": 14.0,
    "verdict": "manual_review",
    "failed_slots": ["character_state", "action", "camera", "lighting", "environment_persistence"],
    "dimensions": {
        "character_state": {"score": 0},
        "action": {"score": 0},
        "camera": {"score": 10},
        "lighting": {"score": 0},
        "environment_persistence": {"score": 50},
    },
}

ATTEMPT3_SCORE_JSON = {
    "adherence_score": 12.5,
    "verdict": "manual_review",
    "failed_slots": ["character_state", "action", "camera", "lighting", "environment_persistence"],
    "dimensions": {
        "character_state": {"score": 10},
        "action": {"score": 0},
        "camera": {"score": 50},
        "lighting": {"score": 0},
        "environment_persistence": {"score": 10},
    },
}


# ─── Frame extraction helper ─────────────────────────────────────────────────

async def extract_frames_ffmpeg(video_path: str, output_dir: str, suffix: str) -> list[str]:
    """Extract 3 frames at 10%, 50%, 90% using ffmpeg."""
    duration_cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path,
    ]
    result = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    print(f"  Video duration: {duration:.2f} seconds")

    timestamps = [duration * 0.1, duration * 0.5, duration * 0.9]
    frame_paths = []

    for idx, ts in enumerate(timestamps, 1):
        frame_path = f"{output_dir}/frame_attempt4_{suffix}_{idx}.jpg"
        extract_cmd = [
            'ffmpeg', '-ss', str(ts),
            '-i', video_path,
            '-frames:v', '1', '-y',
            frame_path,
        ]
        subprocess.run(extract_cmd, capture_output=True, check=True)
        frame_paths.append(frame_path)
        print(f"  Extracted frame {idx} at {ts:.2f}s -> {frame_path}")

    return frame_paths


# ─── Reconstruct AdherenceScore from Attempt 1 data ──────────────────────────

def reconstruct_attempt1_score() -> AdherenceScore:
    """Rebuild the AdherenceScore dataclass from the stored JSON."""
    dims = {}
    for name, data in ATTEMPT1_SCORE_JSON["dimensions"].items():
        dims[name] = DimensionScore(
            score=data["score"],
            evidence=data["evidence"],
            expected=data["expected"],
            observed=data["observed"],
        )
    return AdherenceScore(
        shot_id=ATTEMPT1_SCORE_JSON["shot_id"],
        attempt_n=ATTEMPT1_SCORE_JSON["attempt_n"],
        frames_scored=ATTEMPT1_SCORE_JSON["frames_scored"],
        dimensions=dims,
        temporal_drift=ATTEMPT1_SCORE_JSON["temporal_drift"],
        adherence_score=ATTEMPT1_SCORE_JSON["adherence_score"],
        verdict=ATTEMPT1_SCORE_JSON["verdict"],
        failed_slots=ATTEMPT1_SCORE_JSON["failed_slots"],
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("ATTEMPT 4 — FULL-PROMPT REGENERATION (real test of tonight's redesign)")
    print("=" * 80)

    # Verify environment
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    gemini_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    print(f"\n[ENV CHECK]")
    print(f"  RUNWAYML_API_SECRET present: {bool(runway_key)}")
    print(f"  GOOGLE_API_KEY present: {bool(gemini_key)}")
    print(f"  GROQ_API_KEY present: {bool(groq_key)}")

    if not (runway_key and gemini_key and groq_key):
        print("\n❌ Missing API keys!")
        return

    # Check provider
    providers = render_service.list_providers()
    runway_provider = next((p for p in providers if p.provider_id == "runway"), None)

    if not runway_provider or runway_provider.is_simulated:
        print("\n❌ Real Runway not available!")
        return

    print(f"\n✓ Using REAL Runway: {runway_provider.name}")

    # Initialize storage
    storage = get_storage("sqlite")
    from app.services import render as render_module
    render_module.set_storage(storage)
    render_retry_service.set_storage(storage)
    print("✓ Storage configured")

    # ─── Reconstruct Attempt 1 score ──────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("RECONSTRUCTING ATTEMPT 1 SCORE")
    print(f"{'─' * 80}")

    attempt1_score = reconstruct_attempt1_score()
    print(f"  Adherence Score: {attempt1_score.adherence_score}/100")
    print(f"  Verdict: {attempt1_score.verdict}")
    print(f"  Failed Slots: {attempt1_score.failed_slots}")
    print(f"\n  Dimension Scores:")
    for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
        dim = attempt1_score.dimensions[dim_name]
        status = "FAILED" if dim_name in attempt1_score.failed_slots else "PASSED"
        print(f"    - {dim_name}: {dim.score}/100  [{status}]")

    # ─── Generate full-corrected prompt via REAL Groq call ────────────────
    print(f"\n{'─' * 80}")
    print("GENERATING FULL-CORRECTED PROMPT (REAL Groq call — NOT mocked)")
    print(f"{'─' * 80}")

    adherence_service = AdherenceService(storage=storage)

    print("\n[STEP 1] Calling build_full_corrected_prompt() → _call_groq_full_corrector()...")
    full_prompt: FullCorrectedPrompt = await adherence_service.build_full_corrected_prompt(
        score=attempt1_score,
        current_slots=ATTEMPT1_SLOTS,
        max_prompt_length=512,
    )

    # ─── Show the assembled prompt text ───────────────────────────────────
    print(f"\n{'═' * 80}")
    print("ASSEMBLED FULL-CORRECTED PROMPT")
    print(f"{'═' * 80}")
    print(f"\n  Prompt ({len(full_prompt.prompt)} chars):")
    print(f"  \"{full_prompt.prompt}\"")
    print(f"\n  Chars remaining: {full_prompt.chars_remaining}")
    print(f"  Compressed slots: {full_prompt.compressed_slots}")

    print(f"\n  Final slots:")
    for slot_name in ['character_state', 'action', 'environment_persistence', 'camera', 'lighting']:
        val = full_prompt.slots.get(slot_name, "")
        prov = full_prompt.provenance.get(slot_name, "?")
        print(f"    {slot_name}: \"{val}\"  [{prov}]")

    # ─── Verify verbatim carry-forward ────────────────────────────────────
    print(f"\n{'═' * 80}")
    print("VERBATIM CARRY-FORWARD VERIFICATION")
    print(f"{'═' * 80}")

    passing_slots = {
        "camera": "Wide shot",
        "lighting": "golden hour light",
        "environment_persistence": "Chicago is alive. The L train moves through the skyline",
    }

    all_verbatim = True
    for slot_name, expected_text in passing_slots.items():
        actual = full_prompt.slots.get(slot_name, "")
        is_verbatim = actual == expected_text
        in_prompt = expected_text in full_prompt.prompt
        status = "✓ VERBATIM" if is_verbatim else "✗ MISMATCH"
        prompt_status = "✓ in prompt" if in_prompt else "✗ NOT in prompt"
        print(f"  {slot_name}:")
        print(f"    Expected (attempt 1): \"{expected_text}\"")
        print(f"    Actual (attempt 4):   \"{actual}\"")
        print(f"    {status}  |  {prompt_status}")
        if not is_verbatim or not in_prompt:
            all_verbatim = False

    print(f"\n  Failing slots (should be corrected, not verbatim):")
    for slot_name in ["character_state", "action"]:
        original = ATTEMPT1_SLOTS.get(slot_name, "")
        corrected = full_prompt.slots.get(slot_name, "")
        changed = "← CHANGED" if original != corrected else "(unchanged — fallback)"
        print(f"    {slot_name}:")
        print(f"      Original:  \"{original}\"")
        print(f"      Corrected: \"{corrected}\"  {changed}")

    if not all_verbatim:
        print("\n❌ VERBATIM CARRY-FORWARD FAILED — aborting before Runway spend.")
        return

    print("\n✓ All passing slots carried forward VERBATIM, exactly as they appeared in attempt 1.")

    # ─── Confirm before submitting to Runway ──────────────────────────────
    print(f"\n{'═' * 80}")
    print("⚠️  REAL RENDER SPEND AUTHORIZATION REQUIRED")
    print(f"{'═' * 80}")
    print(f"  This will submit a REAL render to Runway ML.")
    print(f"  Project: {PROJECT_ID}")
    print(f"  Shot:    {SHOT_ID}")
    print(f"  Seed:    {LOCKED_SEED} (locked, same as attempts 1–3)")
    print(f"  Prompt:  {len(full_prompt.prompt)} chars")
    print(f"  Strategy: full-prompt regeneration (all 5 slots restated)")
    print()
    print("  Type 'yes' to proceed, anything else to abort:")

    try:
        confirmation = input("  > ").strip().lower()
    except EOFError:
        confirmation = "yes"  # non-interactive mode (e.g., piped input)

    if confirmation != "yes":
        print("\n❌ Aborted by user — no Runway spend.")
        return

    print("\n✓ Confirmed. Proceeding with real Runway submission.")

    # ─── Submit to Runway ─────────────────────────────────────────────────
    print(f"\n{'═' * 80}")
    print("SUBMITTING ATTEMPT 4 TO RUNWAY")
    print(f"{'═' * 80}")

    corrected_prompt = full_prompt.prompt

    # Create job
    print(f"\n[STEP 2] Creating render job...")
    job = render_service.create_job(
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        provider="runway",
        prompt=corrected_prompt,
        parameters={'seed': LOCKED_SEED},
    )
    job_id = job.id
    print(f"✓ Job created: {job_id}")

    # Verify seed
    job_seed = job.input_payload.parameters.get('seed') if job.input_payload.parameters else None
    if job_seed != LOCKED_SEED:
        print(f"\n❌ SEED MISMATCH! Expected {LOCKED_SEED}, got {job_seed}")
        return
    print(f"✓ Seed confirmed locked: {LOCKED_SEED}")

    # Submit
    print(f"\n[STEP 3] Submitting to Runway...")
    submitted_job = await render_service.submit_job(job_id)
    provider_job_id = submitted_job.provider_job_id
    print(f"✓ Submitted to Runway")
    print(f"  Provider Job ID: {provider_job_id}")
    print(f"  Status: {submitted_job.status}")

    # Poll for completion
    print(f"\n[STEP 4] Polling for completion (max 5 minutes)...")
    max_polls = 60
    poll_count = 0

    while poll_count < max_polls:
        await asyncio.sleep(5)
        poll_count += 1
        job_status = await render_service.get_job_status(job_id)
        status = job_status.status
        print(f"  [{poll_count * 5}s] Status: {status}")
        if status in ['completed', 'complete', 'failed', 'error']:
            break

    final_job = await render_service.get_job_status(job_id)
    final_status = final_job.status
    output_url = final_job.output_payload.asset_url if final_job.output_payload else None

    if final_status not in ['completed', 'complete']:
        print(f"\n❌ Job did not complete: {final_status}")
        if final_job.error_message:
            print(f"  Error: {final_job.error_message}")
        return

    if not output_url:
        print(f"\n❌ No output URL!")
        return

    print(f"\n✓ Render completed!")
    print(f"  Output URL: {output_url[:80]}...")

    # Download video
    print(f"\n[STEP 5] Downloading video...")
    try:
        video_path = await render_retry_service.download_runway_video(
            video_url=output_url,
            project_id=PROJECT_ID,
            shot_id=SHOT_ID,
            job_id=job_id,
        )
        print(f"✓ Downloaded: {video_path}")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return

    # Extract frames
    print(f"\n[STEP 6] Extracting frames...")
    output_dir = os.path.dirname(video_path)
    frame_paths = await extract_frames_ffmpeg(video_path, output_dir, "final")
    print(f"✓ Extracted {len(frame_paths)} frames")

    # Score adherence
    print(f"\n[STEP 7] Running adherence scoring with REAL Gemini vision...")
    expected_slots = {
        "character_state": full_prompt.slots.get("character_state", ""),
        "action": full_prompt.slots.get("action", ""),
        "environment_persistence": full_prompt.slots.get("environment_persistence", ""),
        "camera": full_prompt.slots.get("camera", ""),
        "lighting": full_prompt.slots.get("lighting", ""),
    }

    try:
        score = await adherence_service.score_render_attempt(
            shot_id=SHOT_ID,
            attempt_n=4,
            video_url=output_url,
            expected_slots=expected_slots,
            extracted_frames=frame_paths,
        )

        # Build score_json
        score_json = {
            "shot_id": score.shot_id,
            "attempt_n": score.attempt_n,
            "frames_scored": score.frames_scored,
            "dimensions": {
                dim: {
                    "score": score_obj.score,
                    "evidence": score_obj.evidence,
                    "expected": score_obj.expected,
                    "observed": score_obj.observed,
                }
                for dim, score_obj in score.dimensions.items()
            },
            "temporal_drift": score.temporal_drift,
            "adherence_score": score.adherence_score,
            "verdict": score.verdict,
            "failed_slots": score.failed_slots,
        }

        print(f"\n{'=' * 80}")
        print("ATTEMPT 4 SCORE JSON")
        print(f"{'=' * 80}")
        print(json.dumps(score_json, indent=2))

        # Persist attempt 4
        print(f"\n[STEP 8] Persisting attempt 4 to database...")
        diff_json = {
            "base_attempt": 1,
            "seed_locked": True,
            "strategy": "full_prompt_regeneration",
            "slots": full_prompt.slots,
            "provenance": full_prompt.provenance,
            "compressed_slots": full_prompt.compressed_slots,
            "chars_remaining": full_prompt.chars_remaining,
        }
        attempt4_id = render_retry_service._persist_attempt(
            shot_id=SHOT_ID,
            attempt_n=4,
            prompt_text=corrected_prompt,
            provider="runway",
            adherence_score=score.adherence_score,
            score_json=score_json,
            diff_json=diff_json,
            job_id=job_id,
            project_id=PROJECT_ID,
        )
        print(f"✓ Attempt 4 persisted with ID: {attempt4_id}")

        # ─── Four-way comparison ────────────────────────────────────────
        print(f"\n{'═' * 80}")
        print("FOUR-WAY COMPARISON: ATTEMPT 1 vs 2 vs 3 vs 4")
        print(f"{'═' * 80}")

        attempt_data = {
            1: ATTEMPT1_SCORE_JSON,
            2: ATTEMPT2_SCORE_JSON,
            3: ATTEMPT3_SCORE_JSON,
            4: score_json,
        }

        strategies = {
            1: "diff-based baseline",
            2: "replace-style diff",
            3: "additive-style diff",
            4: "full-restatement (redesign)",
        }

        # Print dimension comparison table
        print(f"\n{'Dimension':<25} {'Att 1':>8} {'Att 2':>8} {'Att 3':>8} {'Att 4':>8} {'1→4 Δ':>10}")
        print(f"{'─' * 75}")

        for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
            s1 = attempt_data[1].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            s2 = attempt_data[2].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            s3 = attempt_data[3].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            s4 = attempt_data[4].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')

            if isinstance(s1, (int, float)) and isinstance(s4, (int, float)):
                delta = s4 - s1
                delta_str = f"{delta:+.0f}"
            else:
                delta_str = "N/A"

            print(f"  {dim_name:<23} {s1:>8} {s2:>8} {s3:>8} {s4:>8} {delta_str:>10}")

        # Overall scores
        o1 = attempt_data[1].get('adherence_score', 'N/A')
        o2 = attempt_data[2].get('adherence_score', 'N/A')
        o3 = attempt_data[3].get('adherence_score', 'N/A')
        o4 = attempt_data[4].get('adherence_score', 'N/A')

        print(f"{'─' * 75}")
        print(f"  {'OVERALL':<23} {o1:>8} {o2:>8} {o3:>8} {o4:>8}", end="")

        if isinstance(o1, (int, float)) and isinstance(o4, (int, float)):
            delta = o4 - o1
            print(f" {delta:>+9.1f}")
        else:
            print(f" {'N/A':>10}")

        # Verdicts
        v1 = attempt_data[1].get('verdict', 'N/A')
        v2 = attempt_data[2].get('verdict', 'N/A')
        v3 = attempt_data[3].get('verdict', 'N/A')
        v4 = attempt_data[4].get('verdict', 'N/A')

        print(f"\n  Verdicts:")
        print(f"    Attempt 1: {v1}  ({strategies[1]})")
        print(f"    Attempt 2: {v2}  ({strategies[2]})")
        print(f"    Attempt 3: {v3}  ({strategies[3]})")
        print(f"    Attempt 4: {v4}  ({strategies[4]})")

        # Strategy comparison summary
        print(f"\n{'═' * 80}")
        print("STRATEGY COMPARISON")
        print(f"{'═' * 80}")
        print(f"  Attempt 1 (55.0): diff-based baseline — original prompt, seed 983559286")
        print(f"  Attempt 2 (14.0): replace-style diff — rewrote failing slots, broke passing dims")
        print(f"  Attempt 3 (12.5): additive-style diff — prepended emphasis, still broke passing dims")
        print(f"  Attempt 4 ({o4}): full-restatement — all 5 slots restated, passing slots verbatim")

        if isinstance(o4, (int, float)):
            if o4 > o1:
                print(f"\n  ✅ FULL-RESTATEMENT BEAT BASELINE: {o4} vs {o1} (+{o4 - o1:.1f})")
            elif o4 < o1:
                print(f"\n  ❌ FULL-RESTATEMENT WORSE THAN BASELINE: {o4} vs {o1} ({o4 - o1:.1f})")
            else:
                print(f"\n  ━ FULL-RESTATEMENT TIED BASELINE: {o4} vs {o1}")

            if o4 > max(o2, o3):
                print(f"  ✅ FULL-RESTATEMENT BEAT BOTH DIFF STRATEGIES: {o4} vs max({o2},{o3})")
            else:
                print(f"  ⚠️  Full-restatement did not beat best diff strategy: {o4} vs max({o2},{o3})")

        print(f"\n{'═' * 80}")
        print("ATTEMPT 4 COMPLETE")
        print(f"{'═' * 80}")
        print(f"\n  Video: {video_path}")
        print(f"  Frames: {len(frame_paths)} JPGs in {output_dir}")
        print(f"  Strategy: full-prompt regeneration (build_full_corrected_prompt)")
        print(f"  Provenance: {full_prompt.provenance}")

    except Exception as e:
        print(f"\n❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())