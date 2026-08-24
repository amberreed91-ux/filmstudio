#!/usr/bin/env python3
"""Score an already-rendered clip against its expected slots. No render, no spend.

Extracts the three frames the scorer expects (10%, 50%, 90% of duration) and
runs AdherenceService against them, using whichever provider
ADHERENCE_VISION_PROVIDER selects. Prints the model that produced the score
alongside the numbers, because a score without its scorer attached cannot be
compared to anything measured later.

    python scripts/score_rendered_shot.py \
      --video outputs/renders/<project>/<job>.mp4 \
      --character "MAYA, lean, late 20s, grey work jacket" \
      --action "sets the kettle down and turns toward the window" \
      --camera "slow push in, eye level" \
      --lighting "single warm practical, deep shadow" \
      --environment "cramped kitchen at dusk"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass


def _duration_seconds(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _extract_frames(video: Path, out_dir: Path) -> list[str]:
    duration = _duration_seconds(video)
    frames: list[str] = []
    for label, fraction in (("10", 0.10), ("50", 0.50), ("90", 0.90)):
        target = out_dir / f"frame_{label}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{duration * fraction:.3f}",
                "-i", str(video),
                "-frames:v", "1", "-q:v", "2",
                str(target),
            ],
            check=True,
        )
        if not target.is_file():
            raise RuntimeError(f"ffmpeg produced no frame at {fraction:.0%}")
        frames.append(str(target))
    return frames


async def _score(frames: list[str], args) -> None:
    from app.services.adherence_service import AdherenceService

    service = AdherenceService()
    print(
        f"provider={service._vision_provider!r} model={service._vision_model!r}",
        file=sys.stderr,
    )

    score = await service.score_render_attempt(
        shot_id=args.shot_id,
        attempt_n=1,
        video_url=str(args.video),
        expected_slots={
            "character_state": args.character,
            "action": args.action,
            "camera": args.camera,
            "lighting": args.lighting,
            "environment_persistence": args.environment,
        },
        extracted_frames=frames,
    )

    print(json.dumps({
        "shot_id": score.shot_id,
        "adherence_score": score.adherence_score,
        "verdict": score.verdict,
        "scored_by_provider": score.scored_by_provider,
        "scored_by_model": score.scored_by_model,
        "dimensions": {
            name: {
                "score": dim.score,
                "expected": dim.expected,
                "observed": dim.observed,
                "evidence": dim.evidence,
            }
            for name, dim in score.dimensions.items()
        },
        "temporal_drift": score.temporal_drift,
        "failed_slots": score.failed_slots,
        "proposed_corrections": score.proposed_corrections,
    }, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--character", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--lighting", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--shot-id", default="manual_scored_shot")
    parser.add_argument(
        "--keep-frames",
        type=Path,
        default=None,
        help="Directory to keep the extracted frames in, for eyeballing what the scorer saw.",
    )
    args = parser.parse_args()

    video = args.video if args.video.is_absolute() else (BACKEND_ROOT / args.video)
    if not video.is_file():
        parser.error(f"video not found: {video}")

    if args.keep_frames:
        args.keep_frames.mkdir(parents=True, exist_ok=True)
        frames = _extract_frames(video, args.keep_frames)
        print(f"frames kept in {args.keep_frames}", file=sys.stderr)
        asyncio.run(_score(frames, args))
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        frames = _extract_frames(video, Path(tmp))
        asyncio.run(_score(frames, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
