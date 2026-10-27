#!/usr/bin/env python3
"""
Direct test of adherence scoring with real job - bypasses keyframe complexity.
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


async def main():
    print("=" * 80)
    print("DIRECT ADHERENCE TEST (no keyframes)")
    print("=" * 80)
    print()
    
    print("Environment:")
    print(f"  GROQ_API_KEY: {'✓' if os.getenv('GROQ_API_KEY') else '✗'}")
    print()
    
    # Get storage
    storage = get_storage("sqlite")
    
    # Get a real completed job
    job_id = "job-20260528170029-c5ca66d8-scene_001_shot_001"
    job = storage.get_job(job_id)
    
    if not job:
        print(f"✗ Job not found")
        return 1
    
    print(f"Job: {job.id}")
    print(f"Shot: {job.shot_id}")
    print(f"Status: {job.status}")
    
    if not job.output_payload:
        print("✗ No output payload")
        return 1
    
    video_url = job.output_payload.asset_url
    print(f"URL: {video_url[:80]}...")
    print()
    
    # Get prompt
    prompt = "A displaced musician uncovers a citywide memory glitch one song at a time"
    print(f"Prompt: {prompt}")
    print()
    
    print("=" * 80)
    print("DOWNLOADING VIDEO")
    print("=" * 80)
    print()
    
    # Download video directly
    import aiohttp
    from app.services.render import render_service, set_storage
    set_storage(storage)
    
    # Refresh URL first
    print("Refreshing URL...")
    try:
        fresh_url = await render_service.refresh_output_url(job_id)
        if fresh_url:
            print(f"✓ URL refreshed")
            video_url = fresh_url
        else:
            print("⚠️  Refresh returned None, using original URL")
    except Exception as e:
        print(f"⚠️  Refresh failed: {e}")
    
    print()
    print(f"Downloading from: {video_url[:80]}...")
    
    output_dir = Path(__file__).parent / "outputs" / "test_downloads"
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"{job.shot_id}_test.mp4"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status != 200:
                    print(f"✗ Download failed: HTTP {response.status}")
                    print(f"Response: {await response.text()}")
                    return 1
                
                content = await response.read()
                video_path.write_bytes(content)
                
        print(f"✓ Downloaded {len(content)} bytes to {video_path}")
        print()
        
    except Exception as e:
        print(f"✗ Download error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("EXTRACTING KEYFRAMES")
    print("=" * 80)
    print()
    
    # Extract 3 frames using ffmpeg
    frame_dir = video_path.parent
    frame_paths = []
    
    duration = 5.0  # Approximate
    for i, timestamp in enumerate([0.5, 2.5, 4.5], 1):
        frame_path = frame_dir / f"frame_{i:02d}.jpg"
        cmd = f"ffmpeg -ss {timestamp} -i {video_path} -frames:v 1 {frame_path} -y"
        os.system(f"{cmd} > /dev/null 2>&1")
        if frame_path.exists():
            frame_paths.append(str(frame_path))
            print(f"✓ Extracted frame {i} at {timestamp}s")
        else:
            print(f"✗ Failed to extract frame {i}")
            return 1
    
    print(f"✓ Extracted {len(frame_paths)} frames")
    print()
    
    print("=" * 80)
    print("CALLING GROQ API FOR ADHERENCE SCORING")
    print("=" * 80)
    print()
    
    # Use video frames - for now just use the video URL
    # The adherence service can work with video URL alone if frames not provided
    prompt_slots = {"description": prompt}
    
    try:
        score = await adherence_service.score_render_attempt(
            shot_id=job.shot_id,
            attempt_n=1,
            video_url=str(video_path),  # Use local path
            expected_slots=prompt_slots,
            extracted_frames=frame_paths,  # Pass extracted frames
        )
        
        print("✓ Adherence scoring complete!")
        print()
        print(f"Score Summary:")
        print(f"  Overall Score: {score.adherence_score}")
        print(f"  Verdict: {score.verdict}")
        print(f"  Frames Scored: {score.frames_scored}")
        print()
        
        if score.dimensions:
            print("Dimensions:")
            for dim, dim_score in score.dimensions.items():
                print(f"  {dim}: {dim_score.score} - {dim_score.evidence[:80]}")
            print()
        
        # Serialize for database
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
        
        print("=" * 80)
        print("PERSISTING TO DATABASE")
        print("=" * 80)
        print()
        
        # Persist directly using storage
        import sqlite3
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO render_attempts 
                (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    job.shot_id,
                    1,
                    prompt,
                    "runway",
                    score.adherence_score,
                    json.dumps(score_json),
                ),
            )
            conn.commit()
        
        print("✓ Persisted to render_attempts table")
        print()
        
        # Query back
        attempts = storage.list_render_attempts(shot_id=job.shot_id)
        print(f"✓ Found {len(attempts)} attempt(s)")
        print()
        
        if attempts:
            for attempt in attempts:
                print("DATABASE ROW:")
                print(f"  Shot: {attempt['shot_id']}")
                print(f"  Attempt: {attempt['attempt_n']}")
                print(f"  Score: {attempt['adherence_score']}")
                print(f"  Provider: {attempt['provider']}")
                print()
                
                if attempt.get('score_json'):
                    print("SCORE_JSON (persisted):")
                    print(json.dumps(attempt['score_json'], indent=2)[:500])
                    print("...")
                    print()
        
        print("=" * 80)
        print("✅ SUCCESS - REAL API CALL COMPLETE")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"✗ Adherence scoring failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    from app.script_guard import refuse_non_approved_provider

    refuse_non_approved_provider(
        __file__,
        what="direct adherence scoring with real network scoring calls + render_attempts write",
        provider="groq",
    )
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
