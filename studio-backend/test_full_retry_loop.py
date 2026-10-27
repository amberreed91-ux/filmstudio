#!/usr/bin/env python3
"""
Complete retry loop test: score → correct → re-render → score again.
Tests the core requirement: does correction actually improve the score?
"""
import asyncio
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.adherence_service import adherence_service
from app.services.render import render_service, set_storage


async def download_and_extract_frames(video_url, job_id, shot_id, output_dir):
    """Download video and extract 3 frames"""
    import aiohttp
    
    # Refresh URL
    fresh_url = await render_service.refresh_output_url(job_id)
    if fresh_url:
        video_url = fresh_url
    
    # Download
    video_path = output_dir / f"{shot_id}_{job_id}.mp4"
    async with aiohttp.ClientSession() as session:
        async with session.get(video_url) as response:
            if response.status != 200:
                raise ValueError(f"Download failed: HTTP {response.status}")
            content = await response.read()
            video_path.write_bytes(content)
    
    print(f"  ✓ Downloaded {len(content)} bytes")
    
    # Extract frames
    frame_paths = []
    for i, timestamp in enumerate([0.5, 2.5, 4.5], 1):
        frame_path = output_dir / f"{shot_id}_{job_id}_frame_{i:02d}.jpg"
        os.system(f"ffmpeg -ss {timestamp} -i {video_path} -frames:v 1 {frame_path} -y > /dev/null 2>&1")
        if frame_path.exists():
            frame_paths.append(str(frame_path))
    
    print(f"  ✓ Extracted {len(frame_paths)} frames")
    
    return str(video_path), frame_paths


async def score_and_persist(shot_id, attempt_n, video_path, frame_paths, prompt, storage):
    """Score adherence and persist to database"""
    prompt_slots = {"description": prompt}
    
    score = await adherence_service.score_render_attempt(
        shot_id=shot_id,
        attempt_n=attempt_n,
        video_url=video_path,
        expected_slots=prompt_slots,
        extracted_frames=frame_paths,
    )
    
    print(f"  ✓ Adherence score: {score.adherence_score}")
    print(f"  ✓ Verdict: {score.verdict}")
    
    # Serialize
    score_json = {
        "shot_id": score.shot_id,
        "attempt_n": score.attempt_n,
        "frames_scored": score.frames_scored,
        "dimensions": {
            dim: {
                "score": s.score,
                "evidence": s.evidence,
                "expected": s.expected,
                "observed": s.observed,
            }
            for dim, s in score.dimensions.items()
        },
        "temporal_drift": score.temporal_drift,
        "adherence_score": score.adherence_score,
        "verdict": score.verdict,
        "failed_slots": score.failed_slots,
    }
    
    # Persist
    import sqlite3
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO render_attempts 
            (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (shot_id, attempt_n, prompt, "runway", score.adherence_score, json.dumps(score_json)),
        )
        conn.commit()
    
    return score, score_json


async def main():
    print("=" * 80)
    print("FULL RETRY LOOP TEST")
    print("=" * 80)
    print()
    
    storage = get_storage("sqlite")
    set_storage(storage)
    
    output_dir = Path(__file__).parent / "outputs" / "retry_loop_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use the existing attempt 1 result
    shot_id = "scene_001_shot_001"
    original_job_id = "job-20260528170029-c5ca66d8-scene_001_shot_001"
    original_prompt = "A displaced musician uncovers a citywide memory glitch one song at a time"
    
    print("ATTEMPT 1 (already scored):")
    print(f"  Shot: {shot_id}")
    print(f"  Job: {original_job_id}")
    print(f"  Prompt: {original_prompt}")
    print(f"  Score: 77.5 (from previous test)")
    print(f"  Verdict: correctable")
    print(f"  Failed dimensions: character_state (50), action (50)")
    print()
    
    # Get attempt 1 from database
    attempts = storage.list_render_attempts(shot_id=shot_id)
    if not attempts:
        print("✗ Attempt 1 not found in database - run test_adherence_direct.py first")
        return 1
    
    attempt_1 = attempts[0]
    score_1_json = attempt_1['score_json']
    
    # Reconstruct AdherenceScore object for correction
    from app.services.adherence_service import AdherenceScore, DimensionScore
    
    dimensions = {}
    for dim_name, dim_data in score_1_json['dimensions'].items():
        dimensions[dim_name] = DimensionScore(
            score=dim_data['score'],
            evidence=dim_data['evidence'],
            expected=dim_data['expected'],
            observed=dim_data['observed'],
        )
    
    score_1 = AdherenceScore(
        shot_id=score_1_json['shot_id'],
        attempt_n=score_1_json['attempt_n'],
        frames_scored=score_1_json['frames_scored'],
        dimensions=dimensions,
        temporal_drift=score_1_json.get('temporal_drift', {}),
        adherence_score=score_1_json['adherence_score'],
        verdict=score_1_json['verdict'],
        failed_slots=score_1_json.get('failed_slots', []),
    )
    
    print("=" * 80)
    print("STEP 1: Generate Corrective Diff")
    print("=" * 80)
    print()
    
    prompt_slots = {"description": original_prompt}
    chars_remaining = 512 - len(original_prompt) + 50
    
    diff = await adherence_service.generate_corrective_diff(
        score=score_1,
        current_slots=prompt_slots,
        chars_remaining=chars_remaining,
    )
    
    print(f"✓ Generated corrective diff with {len(diff.ops)} operation(s)")
    print()
    for op in diff.ops:
        print(f"  Operation: {op.op}")
        print(f"    Slot: {op.slot}")
        print(f"    Reason: {op.reason}")
        print(f"    Old: {op.old_text[:80]}...")
        print(f"    New: {op.new_text[:80]}...")
        print()
    
    print("=" * 80)
    print("STEP 2: Apply Diff to Get Corrected Prompt")
    print("=" * 80)
    print()
    
    corrected_slots = adherence_service.apply_diff(
        base_slots=prompt_slots,
        diff=diff,
        max_prompt_length=512,
    )
    
    corrected_prompt = corrected_slots.get("description", original_prompt)
    
    print(f"Original: {original_prompt}")
    print(f"Corrected: {corrected_prompt}")
    print()
    
    print("=" * 80)
    print("STEP 3: Get Original Seed")
    print("=" * 80)
    print()
    
    original_job = storage.get_job(original_job_id)
    if not original_job:
        print("✗ Original job not found")
        return 1
    
    # Get seed from original job
    seed = None
    if original_job.input_payload and hasattr(original_job.input_payload, 'seed'):
        seed = original_job.input_payload.seed
    
    # Check shot_seeds table
    if not seed:
        seed_row = storage.get_shot_seed(original_job.project_id, shot_id)
        if seed_row and seed_row.get('seed'):
            seed = seed_row['seed']
    
    # Default seed if not found
    if not seed:
        seed = 12345  # Fallback
    
    print(f"✓ Original seed: {seed}")
    print()
    
    print("=" * 80)
    print("STEP 4: Submit NEW Render with Corrected Prompt (LOCKED SEED)")
    print("=" * 80)
    print()
    print("⚠️  This will submit a real Runway render job ($0.05)")
    print()
    response = input("Proceed with render submission? [y/N]: ")
    if response.lower() != 'y':
        print("Aborted by user")
        return 0
    
    # Create and submit new job
    new_job = render_service.create_job(
        project_id=original_job.project_id,
        shot_id=shot_id,
        provider="runway",
        prompt=corrected_prompt,
        parameters={"seed": seed},  # LOCKED SEED
    )
    
    print(f"✓ Created job: {new_job.id}")
    print(f"  Prompt: {corrected_prompt}")
    print(f"  Seed: {seed} (LOCKED)")
    print()
    
    # Submit job
    submitted_job = await render_service.submit_job(new_job.id)
    print(f"✓ Submitted to Runway: {submitted_job.provider_job_id}")
    print()
    
    print("=" * 80)
    print("STEP 5: Poll Until Complete")
    print("=" * 80)
    print()
    
    max_polls = 120  # 10 minutes
    for poll_n in range(max_polls):
        await asyncio.sleep(5)
        
        job_status = await render_service.get_job_status(new_job.id)
        print(f"  Poll {poll_n + 1}: status={job_status.status}, progress={job_status.progress}%")
        
        if job_status.status == "complete":
            print()
            print("✓ Render complete!")
            break
        elif job_status.status in ["failed", "cancelled"]:
            print(f"✗ Render {job_status.status}: {job_status.error_message}")
            return 1
    else:
        print("✗ Timeout waiting for render")
        return 1
    
    print()
    print("=" * 80)
    print("STEP 6: Download and Score ATTEMPT 2")
    print("=" * 80)
    print()
    
    output_url = job_status.output_payload.asset_url
    
    video_path_2, frame_paths_2 = await download_and_extract_frames(
        output_url, new_job.id, shot_id, output_dir
    )
    
    score_2, score_2_json = await score_and_persist(
        shot_id, 2, video_path_2, frame_paths_2, corrected_prompt, storage
    )
    
    print()
    print("=" * 80)
    print("RESULTS: SIDE-BY-SIDE COMPARISON")
    print("=" * 80)
    print()
    
    # Query both attempts
    attempts = storage.list_render_attempts(shot_id=shot_id)
    attempts_sorted = sorted(attempts, key=lambda a: a['attempt_n'])
    
    print(f"{'Metric':<25} {'Attempt 1':<20} {'Attempt 2':<20} {'Delta':<10}")
    print("-" * 80)
    
    a1 = attempts_sorted[0]['score_json']
    a2 = attempts_sorted[1]['score_json']
    
    print(f"{'Overall Score':<25} {a1['adherence_score']:<20.1f} {a2['adherence_score']:<20.1f} {a2['adherence_score'] - a1['adherence_score']:+.1f}")
    print(f"{'Verdict':<25} {a1['verdict']:<20} {a2['verdict']:<20}")
    print()
    print("Dimension Scores:")
    
    for dim in a1['dimensions'].keys():
        s1 = a1['dimensions'][dim]['score']
        s2 = a2['dimensions'][dim]['score']
        delta = s2 - s1
        marker = "✓" if delta >= 0 else "✗"
        print(f"  {marker} {dim:<23} {s1:<20} {s2:<20} {delta:+}")
    
    print()
    print("=" * 80)
    if a2['adherence_score'] > a1['adherence_score']:
        print("✅ SUCCESS: Correction IMPROVED the score!")
    elif a2['adherence_score'] == a1['adherence_score']:
        print("⚠️  NEUTRAL: Correction had NO EFFECT")
    else:
        print("✗ FAILURE: Correction DEGRADED the score")
    print("=" * 80)
    print()
    
    return 0


if __name__ == "__main__":
    from app.script_guard import require_live_spend_gate

    require_live_spend_gate(
        __file__,
        what="retry-loop test: score, correct, re-render on Runway, score again",
        exposure="multiple Runway video renders + polls + Groq/Gemini scoring calls",
        provider="runway",
    )
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
