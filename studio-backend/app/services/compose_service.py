import asyncio
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import httpx

from app.data.storage import get_storage
from app.models import RenderJobModel

logger = logging.getLogger(__name__)

COMPOSED_DIR = Path(__file__).resolve().parents[2] / "static" / "composed"
STATIC_URL_PREFIX = "http://localhost:8010"


def check_ffmpeg() -> None:
    """Verify FFmpeg is installed and available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg not found. Install with: brew install ffmpeg"
            )
    except FileNotFoundError:
        raise RuntimeError(
            f"FFmpeg not found. Install with: brew install ffmpeg"
        )


def _extract_shot_number(shot_id: str) -> int:
    """Extract numeric shot number from a shot_id like 'scene_001_shot_003'."""
    match = re.search(r"_shot_(\d+)$", shot_id)
    if match:
        return int(match[1])
    return 0


def _scene_id_from_shot_id(shot_id: str) -> str:
    """Extract scene ID from a shot_id like 'scene_001_shot_003'."""
    return shot_id.split("_shot_")[0] if "_shot_" in shot_id else ""


async def compose_scene(project_id: str, scene_id: str) -> dict:
    """Compose all completed shots for a scene into a single video using FFmpeg."""
    check_ffmpeg()

    storage = get_storage("sqlite")

    # Get all render jobs for this project
    all_jobs = storage.list_jobs(project_id=project_id, limit=500)

    # Filter to only completed jobs for this scene, and map to shot number
    scene_jobs: list[RenderJobModel] = []
    for job in all_jobs:
        if job.status != "complete":
            continue
        if _scene_id_from_shot_id(job.shot_id) != scene_id:
            continue
        asset_url = (
            job.output_payload.asset_url if job.output_payload else None
        )
        if not asset_url:
            continue
        scene_jobs.append(job)

    if len(scene_jobs) < 2:
        raise ValueError(
            f"Need at least 2 completed shots with valid URLs to compose. "
            f"Found {len(scene_jobs)}."
        )

    # Group by shot number, keep most recent per shot
    shot_map: dict[int, RenderJobModel] = {}
    for job in scene_jobs:
        shot_num = _extract_shot_number(job.shot_id)
        if shot_num == 0:
            continue
        existing = shot_map.get(shot_num)
        if existing is None or job.created_at > existing.created_at:
            shot_map[shot_num] = job

    # Sort by shot number ascending
    sorted_shots = sorted(shot_map.items(), key=lambda x: x[0])
    shot_urls = [job.output_payload.asset_url for _, job in sorted_shots]

    if len(shot_urls) < 2:
        raise ValueError(
            f"Need at least 2 shots with valid URLs to compose. "
            f"Found {len(shot_urls)}."
        )

    # Download and concatenate
    with tempfile.TemporaryDirectory() as tmpdir:
        input_files = []
        async with httpx.AsyncClient() as client:
            for i, url in enumerate(shot_urls):
                response = await client.get(url, timeout=60)
                response.raise_for_status()
                filepath = os.path.join(tmpdir, f"shot_{i:03d}.mp4")
                with open(filepath, "wb") as f:
                    f.write(response.content)
                input_files.append(filepath)

        # Create FFmpeg concat file
        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for filepath in input_files:
                f.write(f"file '{filepath}'\n")

        # Ensure output directory exists
        output_dir = COMPOSED_DIR / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{scene_id}.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr}")

        # Get duration from ffprobe
        duration_seconds = None
        try:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe.returncode == 0 and probe.stdout.strip():
                duration_seconds = float(probe.stdout.strip())
        except Exception:
            pass

    composed_url = f"{STATIC_URL_PREFIX}/static/composed/{project_id}/{scene_id}.mp4"

    # Save to scene_compositions table
    storage.save_scene_composition(
        project_id=project_id,
        scene_id=scene_id,
        composed_url=composed_url,
        shot_count=len(shot_urls),
        duration_seconds=duration_seconds,
    )

    logger.info(
        "Composed scene %s for project %s: %d shots, %.1fs → %s",
        scene_id, project_id, len(shot_urls), duration_seconds or 0, composed_url,
    )

    return {
        "composed_url": composed_url,
        "shot_count": len(shot_urls),
        "duration_seconds": duration_seconds,
        "project_id": project_id,
        "scene_id": scene_id,
    }


async def get_scene_composition(project_id: str, scene_id: str) -> dict | None:
    """Retrieve a previously composed scene video."""
    storage = get_storage("sqlite")
    return storage.get_scene_composition(project_id, scene_id)
