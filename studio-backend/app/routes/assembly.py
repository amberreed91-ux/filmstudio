"""
Assembly Routes - chain composed scenes into a full film with audio
"""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.storage import get_storage
from app.services.compose_service import (
    compose_scene,
    compose_scene_with_audio,
    STATIC_URL_PREFIX,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects")

FILMS_DIR = Path(__file__).resolve().parents[2] / "static" / "films"


class AssemblyStatusResponse(BaseModel):
    scenes_with_compositions: int
    scenes_total: int
    film_assembled: bool
    film_url: str | None
    has_audio: bool


class AssembleFilmResponse(BaseModel):
    film_url: str
    scene_count: int
    total_duration_seconds: float | None
    has_audio: bool


_assembly_status: dict[str, dict] = {}


def _get_scene_count(project_id: str) -> int:
    try:
        from app.services.project_store import project_store
        project = project_store.get_project(project_id)
        if not project or not isinstance(project, dict):
            return 0
        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") or []
        if isinstance(scenes, list):
            return len(scenes)
        return 0
    except Exception:
        return 0


@router.post("/{project_id}/assemble-film")
async def assemble_film_endpoint(project_id: str):
    storage = get_storage("sqlite")
    compositions = storage.list_scene_compositions_for_project(project_id)
    scenes_total = _get_scene_count(project_id)

    if not compositions and scenes_total > 0:
        logger.info("No compositions for %s, composing all scenes first", project_id)
        try:
            from app.services.project_store import project_store
            project = project_store.get_project(project_id)
            if project and isinstance(project, dict):
                summary = project.get("execution_summary") or {}
                scenes = summary.get("scenes") or []
                if isinstance(scenes, list):
                    for scene in scenes:
                        if not isinstance(scene, dict):
                            continue
                        scene_id = scene.get("scene_id")
                        if not scene_id:
                            continue
                        try:
                            result = await compose_scene_with_audio(project_id, scene_id)
                            if not isinstance(result, dict) or not result.get("composed_url"):
                                await compose_scene(project_id, scene_id)
                        except Exception as e:
                            logger.warning("Could not compose %s/%s: %s", project_id, scene_id, e)
                    compositions = storage.list_scene_compositions_for_project(project_id)
        except Exception as e:
            logger.warning("Auto-compose failed for %s: %s", project_id, e)

    if not compositions:
        raise HTTPException(status_code=400, detail="No scene compositions found")

    sorted_comps = sorted(compositions, key=lambda c: c.get("scene_id", ""))
    has_audio = any("_audio.mp4" in c.get("composed_url", "") for c in sorted_comps)

    films_dir = FILMS_DIR / project_id
    films_dir.mkdir(parents=True, exist_ok=True)
    output_path = films_dir / "the_last_tide.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        input_files = []
        async with httpx.AsyncClient() as client:
            for i, comp in enumerate(sorted_comps):
                url = comp.get("composed_url", "")
                if not url:
                    continue
                try:
                    response = await client.get(url, timeout=120)
                    response.raise_for_status()
                    filepath = os.path.join(tmpdir, f"scene_{i:03d}.mp4")
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    input_files.append(filepath)
                except Exception as e:
                    logger.warning("Failed to download %s: %s", url, e)

        if len(input_files) < 1:
            raise HTTPException(status_code=400, detail="No scene videos could be downloaded")

        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for fp in input_files:
                f.write(f"file '{fp}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"FFmpeg error: {result.stderr[:500]}")

    total_duration = sum(c.get("duration_seconds") or 0 for c in sorted_comps)
    total_duration_seconds = total_duration if total_duration > 0 else None

    film_url = f"{STATIC_URL_PREFIX}/static/films/{project_id}/the_last_tide.mp4"
    storage.save_film(project_id=project_id, film_url=film_url, scene_count=len(sorted_comps), total_duration_seconds=total_duration_seconds, has_audio=has_audio)

    _assembly_status[project_id] = {
        "scenes_with_compositions": len(sorted_comps),
        "scenes_total": scenes_total or len(sorted_comps),
        "film_assembled": True,
        "film_url": film_url,
        "has_audio": has_audio,
    }

    logger.info("Assembled film for %s: %d scenes, %.1fs, audio=%s", project_id, len(sorted_comps), total_duration_seconds or 0, has_audio)
    return AssembleFilmResponse(film_url=film_url, scene_count=len(sorted_comps), total_duration_seconds=total_duration_seconds, has_audio=has_audio)


@router.get("/{project_id}/assembly-status")
async def get_assembly_status(project_id: str):
    storage = get_storage("sqlite")
    cached = _assembly_status.get(project_id)
    if cached:
        return cached
    film = storage.get_film(project_id)
    compositions = storage.list_scene_compositions_for_project(project_id)
    scenes_total = _get_scene_count(project_id)
    if film:
        result = {
            "scenes_with_compositions": len(compositions),
            "scenes_total": scenes_total or len(compositions),
            "film_assembled": True,
            "film_url": film.get("film_url"),
            "has_audio": bool(film.get("has_audio", False)),
        }
        _assembly_status[project_id] = result
        return result
    return {
        "scenes_with_compositions": len(compositions),
        "scenes_total": scenes_total or 0,
        "film_assembled": False,
        "film_url": None,
        "has_audio": False,
    }
