"""
Assembly Routes - chain composed scenes into a full film with audio
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.storage import get_storage
from app.services.compose_service import (
    compose_scene_for_delivery,
    STATIC_URL_PREFIX,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects")

FILMS_DIR = Path(__file__).resolve().parents[2] / "static" / "films"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


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
    project = _load_project(project_id)
    if not project:
        return 0
    summary = project.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    if isinstance(scenes, list):
        return len(scenes)
    return 0


def _load_project(project_id: str) -> dict | None:
    try:
        from app.services.project_store import project_store
        project = project_store.get_project(project_id)
        if isinstance(project, dict):
            return project
    except Exception:
        pass
    try:
        storage = get_storage("sqlite")
        persisted = storage.get_project(project_id)
        if isinstance(persisted, dict):
            return persisted
        if hasattr(persisted, "model_dump"):
            return persisted.model_dump(mode="json")
    except Exception:
        return None
    return None


def _scene_pipeline_compositions(project_id: str) -> list[dict]:
    project = _load_project(project_id)
    if not project:
        return []
    summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
    raw_rows = summary.get("scene_pipeline_assemblies")
    if not isinstance(raw_rows, list):
        return []
    rows: list[dict] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        scene_id = str(row.get("scene_id") or "").strip()
        output_url = str(row.get("output_url") or "").strip()
        if not scene_id or not output_url or row.get("status") not in {"complete", "completed", "existing"}:
            continue
        rows.append(
            {
                "scene_id": scene_id,
                "composed_url": output_url,
                "shot_count": int(row.get("clip_count") or len(row.get("shot_ids") or []) or 1),
                "duration_seconds": row.get("duration_seconds"),
                "has_audio": bool(
                    row.get("soundtrack_status") == "manual_post_render"
                    or row.get("soundtrack_status") == "generated"
                    or "_audio" in output_url
                    or "with_audio" in output_url
                ),
                "source": "scene_pipeline",
            }
        )
    return rows


def _merged_scene_compositions(project_id: str, storage_compositions: list[dict] | None = None) -> list[dict]:
    merged: dict[str, dict] = {}
    for comp in storage_compositions or []:
        if not isinstance(comp, dict):
            continue
        scene_id = str(comp.get("scene_id") or "").strip()
        if scene_id:
            merged[scene_id] = comp
    for comp in _scene_pipeline_compositions(project_id):
        merged[comp["scene_id"]] = comp
    return list(merged.values())


def _resolve_local_video_path(url_or_path: str) -> Path | None:
    value = str(url_or_path or "").strip()
    if not value:
        return None
    if value.startswith("file://"):
        parsed = urlparse(value)
        path = Path(parsed.path)
        return path if path.exists() else None
    if value.startswith("/outputs/"):
        path = BACKEND_ROOT / value.lstrip("/")
        return path if path.exists() else None
    if value.startswith("outputs/"):
        path = BACKEND_ROOT / value
        return path if path.exists() else None
    if value.startswith(f"{STATIC_URL_PREFIX}/"):
        local = value.replace(f"{STATIC_URL_PREFIX}/", "", 1)
        path = BACKEND_ROOT / local
        return path if path.exists() else None
    path = Path(value)
    if path.is_absolute() and path.exists():
        return path
    return None


async def _materialize_scene_video(client: httpx.AsyncClient, url_or_path: str, destination: str) -> bool:
    local_path = _resolve_local_video_path(url_or_path)
    if local_path is not None:
        shutil.copy2(local_path, destination)
        return True
    response = await client.get(url_or_path, timeout=120)
    response.raise_for_status()
    with open(destination, "wb") as f:
        f.write(response.content)
    return True


@router.post("/{project_id}/assemble-film")
async def assemble_film_endpoint(project_id: str):
    storage = get_storage("sqlite")
    compositions = _merged_scene_compositions(project_id, storage.list_scene_compositions_for_project(project_id))
    scenes_total = _get_scene_count(project_id)

    if not compositions and scenes_total > 0:
        logger.info("No compositions for %s, composing all scenes first", project_id)
        try:
            project = _load_project(project_id)
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
                            await compose_scene_for_delivery(project_id, scene_id)
                        except Exception as e:
                            logger.warning("Could not compose %s/%s: %s", project_id, scene_id, e)
                    compositions = _merged_scene_compositions(project_id, storage.list_scene_compositions_for_project(project_id))
        except Exception as e:
            logger.warning("Auto-compose failed for %s: %s", project_id, e)

    if not compositions:
        raise HTTPException(status_code=400, detail="No scene compositions found")

    sorted_comps = sorted(compositions, key=lambda c: c.get("scene_id", ""))
    has_audio = any(c.get("has_audio") or "_audio.mp4" in c.get("composed_url", "") or "with_audio" in c.get("composed_url", "") for c in sorted_comps)

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
                    filepath = os.path.join(tmpdir, f"scene_{i:03d}.mp4")
                    if await _materialize_scene_video(client, url, filepath):
                        input_files.append(filepath)
                except Exception as e:
                    logger.warning("Failed to load scene video %s: %s", url, e)

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
    compositions = _merged_scene_compositions(project_id, storage.list_scene_compositions_for_project(project_id))
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
