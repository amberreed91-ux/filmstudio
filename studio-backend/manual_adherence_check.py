#!/usr/bin/env python3
"""
Manual Adherence Scoring Test Script

This script allows you to test the adherence scoring system with real images
and expected slot text. It calls the AdherenceService directly to score
frames against expectations using the Gemini vision model.

Usage:
    python manual_adherence_check.py \
        --frames frame1.jpg frame2.jpg frame3.jpg \
        --character "weathered hand, pale skin, visible veins" \
        --action "reaching slowly toward ancient artifact" \
        --camera "extreme closeup, shallow focus" \
        --lighting "dim candlelight, warm amber glow" \
        --environment "dusty stone pedestal, gothic chamber"

Requirements:
    - GEMINI_API_KEY must be set in environment for vision scoring
    - GROQ_API_KEY can optionally be set for corrective diff generation (text-only)
    - Frame files must exist and be readable
    - Exactly 3 frame paths must be provided (10%, 50%, 90% positions)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.services.adherence_service import AdherenceService, AdherenceScore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("manual_adherence_check")


def validate_frames(frame_paths: list[str]) -> None:
    """Validate that all frame paths exist and are readable."""
    if len(frame_paths) != 3:
        raise ValueError(f"Expected exactly 3 frames, got {len(frame_paths)}")
    
    for path in frame_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Frame file not found: {path}")
        if not os.path.isfile(path):
            raise ValueError(f"Path is not a file: {path}")
        if not os.access(path, os.R_OK):
            raise PermissionError(f"Cannot read frame file: {path}")


def format_adherence_score(score: AdherenceScore) -> str:
    """Format an AdherenceScore for human-readable output."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"ADHERENCE SCORE REPORT")
    lines.append("=" * 80)
    lines.append(f"Shot ID: {score.shot_id}")
    lines.append(f"Attempt: {score.attempt_n}")
    lines.append(f"Frames Scored: {score.frames_scored}")
    lines.append(f"Overall Adherence Score: {score.adherence_score:.1f}/100")
    lines.append(f"Verdict: {score.verdict.upper()}")
    lines.append("")
    
    lines.append("DIMENSION SCORES:")
    lines.append("-" * 80)
    for dim_name, dim_score in score.dimensions.items():
        lines.append(f"\n{dim_name.upper().replace('_', ' ')}: {dim_score.score:.1f}/100")
        lines.append(f"  Expected:  {dim_score.expected}")
        lines.append(f"  Observed:  {dim_score.observed}")
        lines.append(f"  Evidence:  {dim_score.evidence}")
    
    lines.append("")
    lines.append("TEMPORAL DRIFT:")
    lines.append("-" * 80)
    lines.append(f"  Start (10%): {score.temporal_drift['start_score']:.1f}/100")
    lines.append(f"  End (90%):   {score.temporal_drift['end_score']:.1f}/100")
    drift_delta = score.temporal_drift['end_score'] - score.temporal_drift['start_score']
    lines.append(f"  Delta:       {drift_delta:+.1f}")
    
    if score.failed_slots:
        lines.append("")
        lines.append("FAILED DIMENSIONS (score < 50):")
        lines.append("-" * 80)
        for slot in score.failed_slots:
            lines.append(f"  - {slot}")
    
    lines.append("=" * 80)
    return "\n".join(lines)


async def run_adherence_check(
    frames: list[str],
    character_state: str,
    action: str,
    camera: str,
    lighting: str,
    environment: str,
    shot_id: str = "manual_test",
    attempt_n: int = 1,
) -> AdherenceScore:
    """
    Run adherence scoring with the provided frames and expected slots.
    
    Args:
        frames: List of 3 frame file paths (10%, 50%, 90% positions)
        character_state: Expected character state text
        action: Expected action text
        camera: Expected camera direction text
        lighting: Expected lighting text
        environment: Expected environment persistence text
        shot_id: Shot identifier (default: "manual_test")
        attempt_n: Attempt number (default: 1)
    
    Returns:
        AdherenceScore with full scoring details
    """
    # Validate inputs
    validate_frames(frames)
    
    if not os.getenv("GEMINI_API_KEY"):
        raise EnvironmentError(
            "GEMINI_API_KEY not found in environment. "
            "Please set it before running this script."
        )
    
    # Build expected slots dict
    expected_slots = {
        "character_state": character_state,
        "action": action,
        "camera": camera,
        "lighting": lighting,
        "environment_persistence": environment,
    }
    
    logger.info(f"Starting adherence check for shot: {shot_id}, attempt: {attempt_n}")
    logger.info(f"Frames: {frames}")
    logger.info(f"Expected slots: {json.dumps(expected_slots, indent=2)}")
    
    # Create service and run scoring
    service = AdherenceService()
    
    score = await service.score_render_attempt(
        shot_id=shot_id,
        attempt_n=attempt_n,
        video_url="manual_test",  # Not used for scoring
        expected_slots=expected_slots,
        extracted_frames=frames,
    )
    
    logger.info(f"Adherence check complete: {score.adherence_score:.1f}/100, verdict={score.verdict}")
    
    return score


def main():
    parser = argparse.ArgumentParser(
        description="Test adherence scoring with real images and expected slot text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python manual_adherence_check.py \\
        --frames frame_10pct.jpg frame_50pct.jpg frame_90pct.jpg \\
        --character "weathered hand, pale skin" \\
        --action "reaching toward artifact" \\
        --camera "extreme closeup" \\
        --lighting "dim candlelight" \\
        --environment "stone pedestal"
        """,
    )
    
    parser.add_argument(
        "--frames",
        nargs=3,
        required=True,
        metavar=("FRAME_10PCT", "FRAME_50PCT", "FRAME_90PCT"),
        help="Paths to 3 frame images (10%%, 50%%, 90%% positions)",
    )
    
    parser.add_argument(
        "--character",
        required=True,
        help="Expected character state text",
    )
    
    parser.add_argument(
        "--action",
        required=True,
        help="Expected action text",
    )
    
    parser.add_argument(
        "--camera",
        required=True,
        help="Expected camera direction text",
    )
    
    parser.add_argument(
        "--lighting",
        required=True,
        help="Expected lighting text",
    )
    
    parser.add_argument(
        "--environment",
        required=True,
        help="Expected environment persistence text",
    )
    
    parser.add_argument(
        "--shot-id",
        default="manual_test",
        help="Shot identifier (default: manual_test)",
    )
    
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Attempt number (default: 1)",
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report",
    )
    
    args = parser.parse_args()
    
    try:
        # Run the adherence check
        score = asyncio.run(
            run_adherence_check(
                frames=args.frames,
                character_state=args.character,
                action=args.action,
                camera=args.camera,
                lighting=args.lighting,
                environment=args.environment,
                shot_id=args.shot_id,
                attempt_n=args.attempt,
            )
        )
        
        # Output results
        if args.json:
            # Output raw JSON for programmatic consumption
            output = {
                "shot_id": score.shot_id,
                "attempt_n": score.attempt_n,
                "adherence_score": score.adherence_score,
                "verdict": score.verdict,
                "frames_scored": score.frames_scored,
                "dimensions": {
                    name: {
                        "score": dim.score,
                        "evidence": dim.evidence,
                        "expected": dim.expected,
                        "observed": dim.observed,
                    }
                    for name, dim in score.dimensions.items()
                },
                "temporal_drift": score.temporal_drift,
                "failed_slots": score.failed_slots,
            }
            print(json.dumps(output, indent=2))
        else:
            # Output human-readable report
            print()
            print(format_adherence_score(score))
            print()
        
        # Exit with code based on verdict
        if score.verdict == "pass":
            sys.exit(0)
        elif score.verdict == "correctable":
            sys.exit(1)
        else:  # manual_review
            sys.exit(2)
    
    except Exception as e:
        logger.error(f"Adherence check failed: {e}", exc_info=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
