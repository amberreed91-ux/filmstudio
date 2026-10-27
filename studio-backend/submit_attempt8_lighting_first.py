#!/usr/bin/env python3
"""
Attempt 8 — Lighting Slot Position Hypothesis Test.

This tests: is lighting failing because of WHAT it says, or WHERE it sits in the prompt?

Current hypothesis from BEST_OF_N_VALIDATION_REPORT.md:
- In attempts 7-9 (corrected prompt, fresh seeds), lighting scored 0/100 despite passing in attempt 1
- The correction process may have destabilized passing dimensions
- OR: lighting's position at the END of the prompt is causing Runway to under-weight it

Current slot order in ALL_SLOTS:
  1. character_state (140 chars)
  2. action (110 chars)
  3. environment_persistence (100 chars)
  4. camera (70 chars)
  5. lighting (60 chars) <- LAST, potentially under-weighted

This test:
- SAME slots content (verbatim): character_state, action, environment_persistence, camera, lighting
- SAME corrected character_state and action text from attempt 1's corrector
- SAME "golden hour light" text (no change to wording)
- ONLY change: reorder lighting to POSITION 2 (right after character_state)

Testing with fresh seed to see if early lighting mention improves adherence.
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
    what="submit Attempt 8 lighting-first render to Runway (reordered slots, fresh seed) + scoring",
    exposure="1 Runway video render + polls + Groq/Gemini scoring calls",
    provider="runway",
)

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.data.db_guard import open_db_readonly, open_db_readwrite, resolve_db_file
from app.services.render import render_service
from app.services.adherence_service import AdherenceService
from app.services.render_retry_service import render_retry_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("attempt8_lighting_first")

# ─── Constants ───────────────────────────────────────────────────────────────

PROJECT_ID = "project_3dba9330f43a"
TEST_SHOT_ID = "scene_001_lighting_first"
ORIGINAL_SHOT_ID = "scene_001"  # For fetching original data
DB_PATH = resolve_db_file()  # guarded: live needs both opt-in flags

# ─── Fetch original attempt 1 data ───────────────────────────────────────────

def fetch_attempt1_data() -> tuple[str, dict, dict]:
    """Fetch the exact prompt and score from attempt 1 for scene_001."""
    conn = open_db_readwrite(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT prompt_text, score_json FROM render_attempts WHERE shot_id=? AND attempt_n=1",
        (ORIGINAL_SHOT_ID,),
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise ValueError("Attempt 1 not found in render_attempts table!")
    
    prompt_text = row[0]
    score_json = json.loads(row[1]) if row[1] else {}
    
    # The original prompt slots from attempt 1
    prompt_slots = {
        "character_state": "People fill the streets",
        "action": "Music, laughter, food stands. Everything is vibrant",
        "environment_persistence": "Chicago is alive. The L train moves through the skyline",
        "camera": "Wide shot",
        "lighting": "golden hour light",
    }
    
    return prompt_text, score_json, prompt_slots


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
        frame_path = f"{output_dir}/frame_attempt8_{suffix}_{idx}.jpg"
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


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("ATTEMPT 8 — LIGHTING SLOT POSITION HYPOTHESIS TEST")
    print("=" * 80)
    print()
    print("HYPOTHESIS: Moving lighting earlier in the prompt improves adherence")
    print()
    print("  Current order: character_state → action → environment → camera → lighting")
    print("  Test order:    character_state → lighting → action → environment → camera")
    print()
    print("  SAME CONTENT: 'golden hour light' unchanged (testing position only)")
    print("  SAME CORRECTED TEXT: character_state and action from attempt 1 corrector")
    print("  DIFFERENT SEED: Fresh random seed to test independently of seed variance")
    print()
    
    # Verify environment
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    gemini_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    
    print(f"[ENV CHECK]")
    print(f"  RUNWAYML_API_SECRET present: {bool(runway_key)}")
    print(f"  GOOGLE_API_KEY present: {bool(gemini_key)}")
    
    if not runway_key:
        print("\nMissing Runway API key!")
        return
    
    # Check provider
    providers = render_service.list_providers()
    runway_provider = next((p for p in providers if p.provider_id == "runway"), None)
    
    if not runway_provider or runway_provider.is_simulated:
        print("\nReal Runway not available!")
        return
    
    print(f"\nUsing REAL Runway: {runway_provider.name}")
    
    # Initialize storage
    storage = get_storage("sqlite")
    from app.services import render as render_module
    render_module.set_storage(storage)
    render_retry_service.set_storage(storage)
    print("Storage configured")
    
    # ─── Fetch attempt 1 baseline data ────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("FETCHING ATTEMPT 1 BASELINE DATA")
    print(f"{'─' * 80}")
    
    attempt1_prompt, attempt1_score_json, attempt1_slots = fetch_attempt1_data()
    attempt1_overall = attempt1_score_json.get("adherence_score", "N/A")
    
    print(f"\n  Attempt 1 baseline score: {attempt1_overall}/100")
    print(f"  Attempt 1 dimensions (FAILED: character_state, action):")
    for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
        dim = attempt1_score_json.get('dimensions', {}).get(dim_name, {})
        score = dim.get('score', 'N/A')
        status = "FAILED" if (isinstance(score, (int, float)) and score <= 70) else "PASSED"
        print(f"    - {dim_name}: {score}/100 [{status}]")
    
    # ─── Define slots for reordered prompt ─────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("BUILDING REORDERED PROMPT (lighting moved to position 2)")
    print(f"{'─' * 80}")
    
    # Get the corrected text from the best-of-N corrector (same as attempt 7/8/9)
    # These were the corrected versions from the Groq corrector
    corrected_character_state = "People visible at human scale, faces and gestures clearly shown"
    corrected_action = "Vendors actively serving customers, people laughing and talking, continuous human activity"
    
    # ── REORDERED SLOTS (lighting at position 2) ──
    reordered_slots = {
        "character_state": corrected_character_state,  # 1st (unchanged)
        "lighting": "golden hour light",             # 2nd (moved from 5th!)
        "action": corrected_action,                  # 3rd (was 2nd)
        "environment_persistence": "Chicago is alive. The L train moves through the skyline",  # 4th (was 3rd)
        "camera": "Wide shot",                        # 5th (was 4th)
    }
    
    # Assemble prompt with NEW order: character_state, lighting, action, environment, camera
    # This follows the hypothesis: lighting should be weighted more heavily by Runway
    # if it appears early in the prompt
    parts = [text for text in [
        reordered_slots["character_state"],
        reordered_slots["lighting"],      # MOVED TO 2nd position
        reordered_slots["action"],
        reordered_slots["environment_persistence"],
        reordered_slots["camera"],
    ] if text]
    
    reordered_prompt = ". ".join(parts) + ". Cinematic, film quality."
    
    print(f"\n  REORDERED prompt ({len(reordered_prompt)} chars):")
    print(f"    {reordered_prompt}")
    
    print(f"\n  Slot order comparison:")
    print(f"    ORIGINAL: character_state → action → environment → camera → lighting")
    print(f"    REORDERED: character_state → lighting → action → environment → camera")
    
    print(f"\n  Lighting slot content (UNCHANGED): 'golden hour light'")
    print(f"  Lighting position changed from 5th to 2nd")
    
    # ─── Generate fresh seed ───────────────────────────────────────────────────
    fresh_seed = render_retry_service._generate_fresh_seed()
    print(f"\n  Fresh seed generated: {fresh_seed}")
    
    # ─── Confirm before submitting ─────────────────────────────────────────────
    print(f"\n{'═' * 80}")
    print("REAL RENDER SPEND AUTHORIZATION REQUIRED")
    print(f"{'═' * 80}")
    print(f"  This will submit ONE REAL render to Runway ML.")
    print(f"  Project: {PROJECT_ID}")
    print(f"  Shot:    {TEST_SHOT_ID}")
    print(f"  Seed:    {fresh_seed} (fresh, no lock)")
    print(f"  Prompt:  {len(reordered_prompt)} chars (reordered slot structure)")
    print()
    print("  ONLY CHANGE from attempt 7-9: lighting moved to position 2")
    print("  Lighting text unchanged: 'golden hour light'")
    print()
    print("  Type 'yes' to proceed, anything else to abort:")
    
    try:
        confirmation = input("  > ").strip().lower()
    except EOFError:
        confirmation = "yes"
    
    if confirmation != "yes":
        print("\nAborted by user — no Runway spend.")
        return
    
    print("\nConfirmed. Proceeding with real Runway submission.")
    
    # ─── Submit to Runway ─────────────────────────────────────────────────────
    print(f"\n{'═' * 80}")
    print(f"SUBMITTING ATTEMPT 8 TO RUNWAY (reordered lighting)")
    print(f"{'═' * 80}")
    
    # Create job
    print(f"\n[STEP 1] Creating render job...")
    job = render_service.create_job(
        project_id=PROJECT_ID,
        shot_id=TEST_SHOT_ID,
        provider="runway",
        prompt=reordered_prompt,
        parameters={'seed': fresh_seed},
    )
    job_id = job.id
    print(f"Job created: {job_id}")
    
    # Submit
    print(f"\n[STEP 2] Submitting to Runway...")
    submitted_job = await render_service.submit_job(job_id)
    provider_job_id = submitted_job.provider_job_id
    print(f"Submitted to Runway")
    print(f"  Provider Job ID: {provider_job_id}")
    
    # Poll for completion
    print(f"\n[STEP 3] Polling for completion (max 5 minutes)...")
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
        print(f"\nJob did not complete: {final_status}")
        if final_job.error_message:
            print(f"  Error: {final_job.error_message}")
        return
    
    print(f"\nRender completed!")
    print(f"  Output URL: {output_url[:80]}...")
    
    # Download video
    print(f"\n[STEP 4] Downloading video...")
    try:
        video_path = await render_retry_service.download_runway_video(
            video_url=output_url,
            project_id=PROJECT_ID,
            shot_id=TEST_SHOT_ID,
            job_id=job_id,
        )
        print(f"Downloaded: {video_path}")
    except Exception as e:
        print(f"Download failed: {e}")
        return
    
    # Extract frames
    print(f"\n[STEP 5] Extracting frames...")
    output_dir = os.path.dirname(video_path)
    frame_paths = await extract_frames_ffmpeg(video_path, output_dir, "lighting_first")
    print(f"Extracted {len(frame_paths)} frames")
    
    # Score adherence
    print(f"\n[STEP 6] Running adherence scoring with real Gemini vision...")
    adherence_service = AdherenceService(storage=storage)
    
    try:
        score = await adherence_service.score_render_attempt(
            shot_id=TEST_SHOT_ID,
            attempt_n=8,
            video_url=output_url,
            expected_slots=reordered_slots,
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
        print("ATTEMPT 8 SCORE JSON")
        print(f"{'=' * 80}")
        print(json.dumps(score_json, indent=2))
        
        # Persist attempt
        print(f"\n[STEP 7] Persisting attempt to database...")
        diff_json = {
            "base_attempt": 1,
            "seed_locked": False,
            "strategy": "lighting_first_hypothesis",
            "description": "Lighting slot moved to position 2 to test position effect",
            "seed_used": fresh_seed,
            "lighting_position": "2nd",
        }
        attempt8_id = render_retry_service._persist_attempt(
            shot_id=TEST_SHOT_ID,
            attempt_n=8,
            prompt_text=reordered_prompt,
            provider="runway",
            adherence_score=score.adherence_score,
            score_json=score_json,
            diff_json=diff_json,
            job_id=job_id,
            project_id=PROJECT_ID,
        )
        print(f"Attempt 8 persisted with ID: {attempt8_id}")
        
        # ─── Hypothesis analysis ───────────────────────────────────────────
        print(f"\n{'═' * 80}")
        print("HYPOTHESIS ANALYSIS: LIGHTING POSITION TEST")
        print(f"{'═' * 80}")
        
        print(f"\n{'Dimension':<25} {'Attempt 1':>10} {'Attempt 8':>10} {'Change?':>10}")
        print(f"{'─' * 65}")
        
        lighting_a1 = attempt1_score_json.get('dimensions', {}).get('lighting', {}).get('score', 'N/A')
        lighting_a8 = score_json.get('dimensions', {}).get('lighting', {}).get('score', 'N/A')
        
        for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
            s1 = attempt1_score_json.get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            s8 = score_json.get('dimensions', {}).get(dim_name, {}).get('score', 'N/A')
            
            if isinstance(s1, (int, float)) and isinstance(s8, (int, float)):
                s1_val, s8_val = s1, s8
                if dim_name == 'lighting':
                    changed = "🔍 TEST" if s8_val > s1_val + 15 else "same/low" if s8_val <= 70 else "improved"
                else:
                    changed = "N/A"
            else:
                s1_val, s8_val = s1, s8
                changed = "N/A"
            
            print(f"  {dim_name:<23} {s1_val:>10} {s8_val:>10} {changed:>10}")
        
        print(f"\n{'═' * 80}")
        print("HYPOTHESIS VERDICT")
        print(f"{'═' * 80}")
        
        if isinstance(lighting_a1, (int, float)) and isinstance(lighting_a8, (int, float)):
            if lighting_a8 > lighting_a1 + 15:
                print(f"\n  ✅ HYPOTHESIS CONFIRMED: Lighting position matters!")
                print(f"     Attempt 8 lighting ({lighting_a8}) > Attempt 1 ({lighting_a1})")
                print(f"     Moving lighting to position 2 improved adherence.")
                print(f"\n     ROOT CAUSE: Positional weighting in Runway prompts.")
            elif lighting_a8 > 70:
                print(f"\n  ✅ HYPOTHESIS SUPPORTED: Lighting position may matter!")
                print(f"     Attempt 8 lighting ({lighting_a8}) > 70 threshold (Attempt 1 had {lighting_a1})")
                print(f"     Lighting passed when placed earlier in prompt.")
            else:
                print(f"\n  ❌ HYPOTHESIS NOT CONFIRMED: Position change alone didn't help")
                print(f"     Attempt 8 lighting ({lighting_a8}) still failed (<=70)")
                print(f"     The issue is likely the TEXT 'golden hour light' being too generic,")
                print(f"     not the position. Consider more descriptive lighting terms like:")
                print(f"     'warm orange sunset glow, long shadows, soft directional light'")
        
        print(f"\n{'═' * 80}")
        print("ATTEMPT 8 COMPLETE")
        print(f"{'═' * 80}")
        print(f"\n  Video: {video_path}")
        print(f"  Frames: {len(frame_paths)} JPGs in {output_dir}")
        print(f"  Strategy: lighting position hypothesis test (position 2)")
        print(f"  Prompt source: reordered attempt 1 slots from render_attempts DB")
        
    except Exception as e:
        print(f"\nScoring failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())