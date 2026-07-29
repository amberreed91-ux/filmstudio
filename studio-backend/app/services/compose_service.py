import asyncio
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import httpx

from app.data.storage import get_storage
from app.models import RenderJobModel
from app.utils.helpers import (
    derive_scene_id_from_shot_id,
    derive_shot_number_from_shot_id,
)

logger = logging.getLogger(__name__)

COMPOSED_DIR = Path(__file__).resolve().parents[2] / "static" / "composed"
AUDIO_SCORES_DIR = Path(__file__).resolve().parents[2] / "static" / "audio" / "scores"
AUDIO_DIALOGUE_DIR = Path(__file__).resolve().parents[2] / "static" / "audio" / "dialogue"
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
    """Extract shot order from manual and auto-split shot IDs."""
    return derive_shot_number_from_shot_id(shot_id)


def _scene_id_from_shot_id(shot_id: str) -> str:
    """Extract scene ID from manual and auto-split shot IDs."""
    return derive_scene_id_from_shot_id(shot_id)


async def compose_scene_for_delivery(project_id: str, scene_id: str) -> dict:
    """Canonical scene delivery path: per-shot CosyVoice bake then assembly."""
    from app.services.scene_assembly_service import scene_assembly_service

    return await scene_assembly_service.assemble_completed_scene(
        project_id=project_id,
        scene_id=scene_id,
    )


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


# ---------------------------------------------------------------------------
# Audio Generation Helpers
# ---------------------------------------------------------------------------

def _get_audio_generation_service():
    """Lazy-import the audio generation service."""
    from app.services.audio_generation_service import audio_generation_service
    return audio_generation_service


async def generate_scene_dialogue(project_id: str, scene_id: str, scene_content: str | None = None) -> list[str]:
    """
    Generate dialogue audio for a scene from extracted dialogue lines.
    Returns list of WAV file paths, or empty list on failure.
    Dialogue failure NEVER blocks compose.
    """
    dialogue_paths: list[str] = []
    try:
        dialogue_dir = AUDIO_DIALOGUE_DIR / project_id
        dialogue_dir.mkdir(parents=True, exist_ok=True)

        if not scene_content:
            return dialogue_paths

        dialogue_pattern = re.compile(
            r'(?:^|\n)\s*([A-Z][A-Z\s.]+(?:V\.O\.|O\.S\.|\(CONT\'?D\))?)\s*\n\s*(.*?)(?=\n[A-Z][A-Z\s.]+(?:V\.O\.|O\.S\.|\(CONT\'?D\))?\s*\n|\Z)',
            re.DOTALL,
        )
        matches = dialogue_pattern.findall(scene_content)

        if not matches:
            simpler_matches = re.findall(r'(?:^|\n)\s*([A-Z][A-Z\s]+):\s*(.*)', scene_content)
            matches = [(m[0], m[1].strip()) for m in simpler_matches]

        for idx, (character, line) in enumerate(matches):
            line = line.strip()
            if not line:
                continue
            line_clean = re.sub(r'\([^)]*\)', '', line).strip()
            if not line_clean:
                continue

            dialogue_path = dialogue_dir / f"{scene_id}_{idx:03d}.wav"
            if dialogue_path.exists():
                dialogue_paths.append(str(dialogue_path))
                continue

            service = _get_audio_generation_service()
            caps = service.capabilities()
            if caps.get("tts_available", False) and not caps.get("mock_mode", True):
                logger.info("Generating dialogue for %s/%s line %d: %s", project_id, scene_id, idx, character)
                result = await service.generate_dialogue(
                    scene_id=scene_id, project_id=project_id,
                    scene_description=line_clean,
                )
                file_path = result.get("file_path") if isinstance(result, dict) else None
                if file_path and os.path.exists(file_path):
                    import shutil
                    shutil.copy2(file_path, dialogue_path)
                    dialogue_paths.append(str(dialogue_path))
                    continue
                logger.warning("TTS returned no file for line %d, skipping", idx)
            else:
                logger.info("TTS not available, skipping dialogue for %s/%s line %d", project_id, scene_id, idx)

        return dialogue_paths

    except Exception as e:
        logger.warning("Dialogue generation failed for %s/%s (non-blocking): %s", project_id, scene_id, e)
        return []


async def compose_scene_with_audio(
    project_id: str,
    scene_id: str,
    score_path: str | None = None,
    dialogue_paths: list[str] | None = None,
    audio_brief: dict | None = None,
) -> dict:
    """Compose shots then mix audio. Audio failure never blocks video compose."""
    video_result = await compose_scene(project_id, scene_id)
    video_only_path = video_result.get("composed_url", "")
    if not video_only_path:
        return video_result

    score_path_final = score_path

    if audio_brief:
        mood = str(audio_brief.get("mood", "") or "")
        logger.info("Audio Director brief applied: %s", mood)
        if audio_brief.get("silence_flag") is True:
            silence_path = AUDIO_SCORES_DIR / project_id / f"{scene_id}_score.wav"
            silence_path.parent.mkdir(parents=True, exist_ok=True)
            if not silence_path.exists():
                from app.services.audio_generation_service import _write_silence_wav
                _write_silence_wav(silence_path, duration_seconds=30.0)
            score_path_final = str(silence_path)
        else:
            score_notes = audio_brief.get("score_notes")
            if score_notes:
                score_path_final = await generate_scene_score(
                    project_id, scene_id, score_prompt=score_notes
                )

    if not score_path_final:
        score_path_final = await generate_scene_score(project_id, scene_id)

    dialogue_files = dialogue_paths or []
    if not dialogue_files:
        scene_content = _get_scene_script_content(project_id, scene_id)
        dialogue_files = await generate_scene_dialogue(project_id, scene_id, scene_content)
    if not score_path_final and not dialogue_files:
        logger.info("No audio for %s/%s, returning video-only", project_id, scene_id)
        return video_result
    output_dir = COMPOSED_DIR / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{scene_id}_audio.mp4"
    local_video_path = _resolve_local_path(video_only_path)
    try:
        if not local_video_path or not os.path.exists(local_video_path):
            logger.warning("Local video path not found for %s", video_only_path)
            return video_result
        cmd = ["ffmpeg", "-y", "-i", local_video_path]
        filter_parts = []
        audio_idx = 0
        if score_path_final and os.path.exists(score_path_final):
            cmd += ["-i", score_path_final]
            audio_idx += 1
            filter_parts.append(f"[{audio_idx}:a]volume=0.3[score_in]")
        for d_idx, d_path in enumerate(dialogue_files):
            if os.path.exists(d_path):
                cmd += ["-i", d_path]
                audio_idx += 1
                is_vo = "V.O." in d_path or "vo_" in d_path
                vol = "0.5" if is_vo else "0.8"
                filter_parts.append(f"[{audio_idx}:a]volume={vol}[d{d_idx}_in]")
        if not filter_parts:
            logger.info("No audio inputs for %s/%s", project_id, scene_id)
            return video_result
        mix_labels = [p.split("[")[1].split("]")[0].split("=")[0] for p in filter_parts]
        fc = ";".join(filter_parts)
        fc += f";{''.join([l + '+' for l in mix_labels])[:-1]}amix=inputs={len(filter_parts)}:duration=first[aout]"
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_path)]
        r = __import__("subprocess").run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            logger.warning("Audio mix failed for %s/%s: %s", project_id, scene_id, r.stderr[:300])
            return video_result
        duration_seconds = None
        try:
            prob = __import__("subprocess").run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)], capture_output=True, text=True, timeout=10)
            if prob.returncode == 0 and prob.stdout.strip():
                duration_seconds = float(prob.stdout.strip())
        except Exception:
            pass
        composed_url = f"http://localhost:8010/static/composed/{project_id}/{scene_id}_audio.mp4"
        get_storage("sqlite").save_scene_composition(project_id, scene_id, composed_url, video_result.get("shot_count", 0), duration_seconds)
        logger.info("Composed %s/%s with audio -> %s", project_id, scene_id, composed_url)
        return {"composed_url": composed_url, "shot_count": video_result.get("shot_count", 0), "duration_seconds": duration_seconds, "project_id": project_id, "scene_id": scene_id, "has_audio": True}
    except Exception as e:
        logger.warning("Audio mix failed for %s/%s: %s", project_id, scene_id, e)
        return video_result


def _resolve_local_path(url_or_path: str) -> str | None:
    if url_or_path.startswith("http://localhost:8010/"):
        lp = url_or_path.replace("http://localhost:8010", "")
        if lp.startswith("/"):
            lp = lp[1:]
        return str(Path(__file__).resolve().parents[2] / lp)
    if os.path.exists(url_or_path):
        return url_or_path
    return None


async def _get_scene_sound_advisory(project_id: str, scene_id: str) -> Dict[str, str] | None:
    """Pull cached sound_advisory from the scene record if available."""
    try:
        from app.services.project_store import project_store
        project = project_store.get_project(project_id)
        if not project or not isinstance(project, dict):
            return None
        for s in (project.get("execution_summary") or {}).get("scenes") or []:
            if isinstance(s, dict) and s.get("scene_id") == scene_id:
                return s.get("sound_advisory") or None
    except Exception as exc:
        logger.warning("Could not load sound advisory for %s/%s: %s", project_id, scene_id, exc)
    return None


async def generate_scene_score(
    project_id: str,
    scene_id: str,
    score_notes: str | None = None,
    score_prompt: str | None = None,
) -> str | None:
    """Generate a score track for a scene via the Audio Generation Service.

    If score_prompt is provided, it overrides the default prompt. Otherwise the
    cached sound_advisory for the scene is consulted, falling back to an empty
    mood and score_notes if nothing is cached.
    """
    from app.services.audio_generation_service import audio_generation_service

    mood = ""
    if not score_notes:
        advisory = _get_scene_sound_advisory(project_id, scene_id)
        if advisory:
            mood = str(advisory.get("mood", "") or "")
            score_notes = str(advisory.get("score_notes", "") or "")

    result = await audio_generation_service.generate_score(
        scene_id=scene_id,
        project_id=project_id,
        mood=mood,
        score_notes=score_notes or "",
        prompt=score_prompt,
    )
    file_path = result.get("file_path") if isinstance(result, dict) else None
    if file_path and os.path.exists(file_path):
        return str(file_path)
    return None


def _get_scene_script_content(project_id: str, scene_id: str) -> str | None:
    try:
        from app.services.project_store import project_store
        project = project_store.get_project(project_id)
        if not project or not isinstance(project, dict):
            return None
        for s in (project.get("execution_summary") or {}).get("scenes") or []:
            if isinstance(s, dict) and s.get("scene_id") == scene_id:
                return str(
                    s.get("scene_text")
                    or s.get("text")
                    or s.get("content")
                    or s.get("description")
                    or s.get("heading")
                    or ""
                )
        return None
    except Exception as e:
        logger.warning("Could not fetch scene content for %s/%s: %s", project_id, scene_id, e)
        return None
