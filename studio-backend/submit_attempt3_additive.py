#!/usr/bin/env python3
"""
Attempt 3 - Additive Correction Strategy (strengthen/prepend_emphasis only).

Reconstructs the Attempt 1 AdherenceScore (55.0, failed character_state/action),
generates a corrective diff that is FORCED to use only "strengthen" or
"prepend_emphasis" operations (adding to existing text rather than rewriting it),
applies the diff, submits to Runway with the locked seed, scores the result,
and compares against Attempt 1 and Attempt 2.

Key difference from Attempt 2:
- Attempt 2 used "replace" ops → discarded original scene context → score 14.0
- Attempt 3 uses "strengthen"/"prepend_emphasis" → preserves original text →
  adds emphasis on the failing dimensions while keeping passing dimensions intact
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.script_guard import require_live_spend_gate

require_live_spend_gate(
    __file__,
    what="submit Attempt 3 additive-corrected render to Runway (locked seed) + Groq/Gemini scoring",
    exposure="1 Runway video render + polls + Groq/Gemini scoring calls",
    provider="runway",
)

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.render import render_service
from app.services.adherence_service import (
    AdherenceService,
    AdherenceScore,
    DimensionScore,
    CorrectionOp,
    CorrectiveDiff,
)
from app.services.render_retry_service import render_retry_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("attempt3_additive")


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

# Attempt 1 score data (from score_attempt2_manual.py reconstruction)
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
        frame_path = f"{output_dir}/frame_attempt3_{suffix}_{idx}.jpg"
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


# ─── Generate additive-only corrective diff ──────────────────────────────────

async def generate_additive_corrective_diff(
    score: AdherenceScore,
    current_slots: dict[str, str],
    chars_remaining: int,
) -> CorrectiveDiff:
    """
    Generate a corrective diff using ONLY strengthen/prepend_emphasis ops.

    We call the Groq corrector but override the system prompt to forbid
    "replace" operations. This forces the corrector to ADD emphasis to
    the existing slot text rather than rewriting it.
    """
    from groq import Groq

    failed_dims = [
        {
            "slot": slot,
            "expected": score.dimensions[slot].expected,
            "observed": score.dimensions[slot].observed,
            "evidence": score.dimensions[slot].evidence,
        }
        for slot in score.failed_slots
    ]

    failed_list = "\n".join([f"- {d['slot']}: {d['evidence']}" for d in failed_dims])
    current_slots_formatted = "\n".join(
        [f"  {k}: {v}" for k, v in current_slots.items()]
    )

    # System prompt that FORBIDS replace — only strengthen/prepend_emphasis
    system_prompt = """You are a prompt engineer fixing video generation prompts. You analyze vision scoring evidence to understand what went wrong and generate precise correction operations to fix it.

CRITICAL RULE — ADDITIVE ONLY:
You may ONLY use "strengthen" or "prepend_emphasis" operations. NEVER use "replace".
The goal is to ADD emphasis to the existing slot text, preserving the original
scene context that already works. Do NOT rewrite or discard existing slot content.

Rules:
1. Only generate ops for failed dimensions
2. Prescribe what you WANT to see, never describe what's missing.
   - BAD: "No specific character is present"
   - GOOD: "Crowds of people at street level, faces visible, actively moving"
3. For character/action consistency issues: prescribe specific visible human elements
4. Choose the right operation type:
   - "strengthen": ADD emphasis while keeping original text. Your new_text should be
     a short emphasis phrase that gets prepended to the original with a period.
     Example: new_text="Crowds of people visible at street level, faces clearly shown"
     → result: "Crowds of people visible at street level, faces clearly shown. People fill the streets"
   - "prepend_emphasis": add a short clarifying phrase at the start (use for continuity
     emphasis like "Throughout the shot,")
     Example: new_text="Throughout the shot, people are visible at human scale"
     → result: "Throughout the shot, people are visible at human scale, People fill the streets"
5. NEVER use "replace" — this is forbidden for this correction.
6. Keep new_text SHORT (under 80 chars) since it will be prepended to existing text.
7. Calculate char_delta accurately (new total length - old length, accounting for
   the prepended text plus separator)
8. Be specific in reason - explain what gap you're fixing
9. Respect character budget - don't exceed chars_remaining
10. Respond ONLY with valid JSON matching the exact schema

Response schema:
{
  "ops": [
    {
      "slot": "dimension_name",
      "op": "strengthen|prepend_emphasis",
      "old_text": "current text",
      "new_text": "short emphasis phrase to prepend",
      "reason": "why this fixes the issue",
      "char_delta": 0
    }
  ],
  "chars_remaining": <updated_budget>
}"""

    user_prompt = f"""These dimensions failed in the render:
{failed_list}

Current slots:
{current_slots_formatted}

Available character budget: {chars_remaining}

Generate ADDITIVE correction operations (strengthen or prepend_emphasis ONLY — NO replace).
The new_text should be a SHORT emphasis phrase that will be prepended to the existing
slot text, preserving the original content. Keep new_text under 80 characters."""

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    def _sync_call():
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2048,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content, response.choices[0].finish_reason

    print("\n[STEP 1] Calling Groq corrector (additive-only mode)...")
    response_text, finish_reason = await asyncio.to_thread(_sync_call)
    print(f"  Finish reason: {finish_reason}")

    result = json.loads(response_text)

    # Validate: reject any "replace" ops and convert to "strengthen"
    for op in result["ops"]:
        if op["op"] == "replace":
            print(f"  ⚠️  Corrector returned 'replace' for {op['slot']} — converting to 'strengthen'")
            op["op"] = "strengthen"
        if op["op"] not in ("strengthen", "prepend_emphasis"):
            raise ValueError(f"Invalid op type after filtering: {op['op']}")

    # Parse into CorrectionOp dataclasses
    ops = [
        CorrectionOp(
            slot=op["slot"],
            op=op["op"],
            old_text=op["old_text"],
            new_text=op["new_text"],
            reason=op["reason"],
            char_delta=op["char_delta"],
        )
        for op in result["ops"]
    ]

    diff = CorrectiveDiff(
        base_attempt=score.attempt_n,
        seed_locked=True,
        ops=ops,
        chars_remaining=result.get("chars_remaining", chars_remaining),
    )

    print(f"\n✓ Generated {len(ops)} additive operation(s):")
    for op in ops:
        print(f"  - {op.slot}: {op.op}")
        print(f"    Old: {op.old_text}")
        print(f"    New (emphasis): {op.new_text}")
        print(f"    Reason: {op.reason}")
        print(f"    Delta: {op.char_delta:+d}")

    return diff


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("ATTEMPT 3 - ADDITIVE CORRECTION (strengthen/prepend_emphasis only)")
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
        print(f"    - {dim_name}: {dim.score}/100")

    # ─── Generate additive corrective diff ────────────────────────────────
    print(f"\n{'─' * 80}")
    print("GENERATING ADDITIVE CORRECTIVE DIFF (strengthen/prepend_emphasis only)")
    print(f"{'─' * 80}")

    current_length = len(ATTEMPT1_PROMPT)
    chars_remaining = max(512 - current_length + 50, 0)
    print(f"  Current prompt length: {current_length} chars")
    print(f"  Chars remaining (budget): {chars_remaining}")

    diff = await generate_additive_corrective_diff(
        score=attempt1_score,
        current_slots=ATTEMPT1_SLOTS,
        chars_remaining=chars_remaining,
    )

    # ─── Apply the diff ───────────────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("APPLYING ADDITIVE DIFF TO SLOTS")
    print(f"{'─' * 80}")

    adherence_service = AdherenceService(storage=storage)
    corrected_slots = adherence_service.apply_diff(
        base_slots=ATTEMPT1_SLOTS,
        diff=diff,
        max_prompt_length=512,
    )

    print(f"\n  Corrected slots:")
    for slot_name in ['character_state', 'action', 'environment_persistence', 'camera', 'lighting']:
        old_val = ATTEMPT1_SLOTS.get(slot_name, "")
        new_val = corrected_slots.get(slot_name, "")
        changed = " ← CHANGED" if old_val != new_val else ""
        print(f"    {slot_name}: {new_val}{changed}")

    # Assemble the corrected prompt from slots
    parts = [text for text in [
        corrected_slots.get("character_state", ""),
        corrected_slots.get("action", ""),
        corrected_slots.get("environment_persistence", ""),
        corrected_slots.get("camera", ""),
        corrected_slots.get("lighting", ""),
    ] if text]
    corrected_prompt = ". ".join(parts) + ". Cinematic, film quality, single continuous shot."

    # Ensure under 512
    if len(corrected_prompt) > 512:
        corrected_prompt = corrected_prompt[:509] + "..."

    print(f"\n  Corrected prompt ({len(corrected_prompt)} chars):")
    print(f"  {corrected_prompt}")

    # Show what's preserved vs added
    print(f"\n  PRESERVATION CHECK:")
    for phrase in ["Chicago", "L train", "Wide shot", "golden hour"]:
        if phrase.lower() in corrected_prompt.lower():
            print(f"    ✓ '{phrase}' preserved")
        else:
            print(f"    ✗ '{phrase}' LOST!")

    # ─── Submit to Runway ─────────────────────────────────────────────────
    print(f"\n{'═' * 80}")
    print("SUBMITTING ATTEMPT 3 TO RUNWAY")
    print(f"{'═' * 80}")
    print(f"  Project: {PROJECT_ID}")
    print(f"  Shot: {SHOT_ID}")
    print(f"  Locked Seed: {LOCKED_SEED}")
    print(f"  Prompt length: {len(corrected_prompt)} chars")

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
    print(f"\n[STEP 7] Running adherence scoring with Gemini vision...")
    expected_slots = {
        "character_state": corrected_slots.get("character_state", ""),
        "action": corrected_slots.get("action", ""),
        "environment_persistence": corrected_slots.get("environment_persistence", ""),
        "camera": corrected_slots.get("camera", ""),
        "lighting": corrected_slots.get("lighting", ""),
    }

    try:
        score = await adherence_service.score_render_attempt(
            shot_id=SHOT_ID,
            attempt_n=3,
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
        print("ATTEMPT 3 SCORE JSON")
        print(f"{'=' * 80}")
        print(json.dumps(score_json, indent=2))

        # Persist attempt 3
        print(f"\n[STEP 8] Persisting attempt 3 to database...")
        attempt3_id = render_retry_service._persist_attempt(
            shot_id=SHOT_ID,
            attempt_n=3,
            prompt_text=corrected_prompt,
            provider="runway",
            adherence_score=score.adherence_score,
            score_json=score_json,
            diff_json={
                "base_attempt": 1,
                "seed_locked": True,
                "ops": [
                    {
                        "slot": op.slot,
                        "op": op.op,
                        "old_text": op.old_text,
                        "new_text": op.new_text,
                        "reason": op.reason,
                        "char_delta": op.char_delta,
                    }
                    for op in diff.ops
                ],
                "chars_remaining": diff.chars_remaining,
            },
            job_id=job_id,
            project_id=PROJECT_ID,
        )
        print(f"✓ Attempt 3 persisted with ID: {attempt3_id}")

        # ─── Three-way comparison ────────────────────────────────────────
        print(f"\n{'═' * 80}")
        print("THREE-WAY COMPARISON: ATTEMPT 1 vs ATTEMPT 2 vs ATTEMPT 3")
        print(f"{'═' * 80}")

        # Load all attempts from DB
        attempts = storage.list_render_attempts(project_id=PROJECT_ID, shot_id=SHOT_ID)
        attempts_sorted = sorted(attempts, key=lambda x: x.get('attempt_number', 0))

        attempt_data = {}
        for att in attempts_sorted:
            att_num = att.get('attempt_number')
            sj = att.get('score_json')
            if isinstance(sj, str):
                sj = json.loads(sj)
            if sj:
                attempt_data[att_num] = sj

        # Attempt 2 data (from the report if not in DB)
        if 2 not in attempt_data:
            attempt_data[2] = {
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

        # Ensure attempt 1 is present
        if 1 not in attempt_data:
            attempt_data[1] = ATTEMPT1_SCORE_JSON

        # Print dimension comparison table
        print(f"\n{'Dimension':<25} {'Attempt 1':>12} {'Attempt 2':>12} {'Attempt 3':>12} {'1→3 Δ':>10}")
        print(f"{'─' * 75}")

        for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
            s1 = attempt_data[1].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            s2 = attempt_data[2].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            s3 = attempt_data[3].get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')

            if isinstance(s1, (int, float)) and isinstance(s3, (int, float)):
                delta = s3 - s1
                delta_str = f"{delta:+.0f}"
            else:
                delta_str = "N/A"

            print(f"  {dim_name:<23} {s1:>10} {s2:>12} {s3:>12} {delta_str:>10}")

        # Overall scores
        o1 = attempt_data[1].get('adherence_score', 'N/A')
        o2 = attempt_data[2].get('adherence_score', 'N/A')
        o3 = attempt_data[3].get('adherence_score', 'N/A')

        print(f"{'─' * 75}")
        print(f"  {'OVERALL':<23} {o1:>10} {o2:>12} {o3:>12}", end="")

        if isinstance(o1, (int, float)) and isinstance(o3, (int, float)):
            delta = o3 - o1
            print(f" {delta:>+9.1f}")
        else:
            print(f" {'N/A':>10}")

        # Verdicts
        v1 = attempt_data[1].get('verdict', 'N/A')
        v2 = attempt_data[2].get('verdict', 'N/A')
        v3 = attempt_data[3].get('verdict', 'N/A')

        print(f"\n  Verdicts:")
        print(f"    Attempt 1: {v1}")
        print(f"    Attempt 2: {v2}")
        print(f"    Attempt 3: {v3}")

        # Strategy comparison
        print(f"\n{'═' * 80}")
        print("STRATEGY COMPARISON")
        print(f"{'═' * 80}")
        print(f"  Attempt 2: Used 'replace' ops → rewrote slots → score {o2}/100")
        print(f"    - Discarded original scene context")
        print(f"    - Broke passing dimensions (camera, lighting, environment)")
        print(f"  Attempt 3: Used 'strengthen'/'prepend_emphasis' → added to slots → score {o3}/100")
        print(f"    - Preserved original scene context")
        print(f"    - Added emphasis on failing dimensions")

        if isinstance(o2, (int, float)) and isinstance(o3, (int, float)):
            if o3 > o2:
                print(f"\n  ✅ ADDITIVE STRATEGY WINS: {o3} vs {o2} (+{o3 - o2:.1f})")
            elif o3 < o2:
                print(f"\n  ❌ ADDITIVE STRATEGY LOST: {o3} vs {o2} ({o3 - o2:.1f})")
            else:
                print(f"\n  ━ TIE: {o3} vs {o2}")

        if isinstance(o1, (int, float)) and isinstance(o3, (int, float)):
            if o3 > o1:
                print(f"  ✅ IMPROVED OVER ATTEMPT 1: {o3} vs {o1} (+{o3 - o1:.1f})")
            elif o3 < o1:
                print(f"  ❌ WORSE THAN ATTEMPT 1: {o3} vs {o1} ({o3 - o1:.1f})")
            else:
                print(f"  ━ SAME AS ATTEMPT 1: {o3} vs {o1}")

        print(f"\n{'═' * 80}")
        print("ATTEMPT 3 COMPLETE")
        print(f"{'═' * 80}")
        print(f"\n  Video: {video_path}")
        print(f"  Frames: {len(frame_paths)} JPGs in {output_dir}")
        print(f"  Ops used: {', '.join(set(op.op for op in diff.ops))}")

    except Exception as e:
        print(f"\n❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())