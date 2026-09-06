from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.data.storage import get_storage
from app.models.film_delivery import AssemblyStatusResponse, AssembleFilmResponse
from app.services.project_persistence_service import project_persistence_service
from app.services.scene_assembly_service import SceneAssemblyService, scene_assembly_service
from app.services.take_selection_service import TakeSelectionService
from app.services.scene_audio_source_service import SceneAudioSourceService
from app.services.stability import StateError, ValidationError, PlaybackError, PersistenceError, log_stage_event, start_timer, elapsed_ms


class FilmDeliveryService:
    def __init__(self, storage=None, projects=None, scenes=None, backend_root=None, project_loader=None):
        self._storage = storage
        self.projects = projects or project_persistence_service
        self.project_loader = project_loader or self.projects.load
        self.scenes = scenes or scene_assembly_service
        self.root = Path(backend_root or Path(__file__).resolve().parents[2])
        self.audio_sources = getattr(scenes, "audio_sources", None) or SceneAudioSourceService(self.root / "outputs" / "audio")


    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    def _inputs(self, project_id):
        project = self.project_loader(project_id)
        if not project:
            raise StateError("Project not found", stage="film_delivery")
        summary = project.get("execution_summary") or {}
        order = [str(row.get("scene_id") or "").strip() for row in summary.get("scenes", []) if isinstance(row, dict)]
        if not order or any(not scene for scene in order) or len(order) != len(set(order)):
            raise StateError("Save a scene list with distinct scene IDs before assembling", stage="film_delivery")
        compositions = {row["scene_id"]: row for row in self.storage.list_scene_compositions_for_project(project_id)}
        for row in summary.get("scene_pipeline_assemblies", []):
            if not isinstance(row, dict) or row.get("status") not in {"complete", "completed", "existing"} or not row.get("output_url"):
                continue
            sid = row.get("scene_id")
            current = compositions.get(sid)
            if current is None or str(row.get("updated_at") or "") > str(current.get("updated_at") or ""):
                compositions[sid] = {**row, "composed_url": row["output_url"]}
        return order, compositions

    def _scene_outdated(self, project_id, scene_id, composition):
        if not composition or not composition.get("composed_url"):
            return True
        manifest = self.storage.get_delivery_manifest(project_id, scene_id)
        choices = self.storage.list_take_choices(project_id, scene_id)
        try:
            jobs = TakeSelectionService(self.storage).resolve(project_id, scene_id)
            audio_inputs = self.audio_sources.snapshot(project_id, scene_id, [job.shot_id for _, job in jobs])
        except (StateError, ValidationError):
            return True
        if not manifest or manifest.get("composed_url") != composition["composed_url"]:
            # Legacy scene edits have no audio fingerprint. A supplied recording
            # or explicit take choice requires a fresh, traceable assembly.
            return bool(choices) or any(audio_inputs.values())
        return ([job.id for _, job in jobs] != manifest.get("job_ids")
                or audio_inputs != manifest.get("audio_inputs"))

    def status(self, project_id: str) -> AssemblyStatusResponse:
        order, compositions = self._inputs(project_id)
        stale = [sid for sid in order if self._scene_outdated(project_id, sid, compositions.get(sid))]
        film = self.storage.get_film(project_id)
        manifest = self.storage.get_delivery_manifest(project_id, "__film__")
        scene_urls = [compositions.get(sid, {}).get("composed_url") for sid in order]
        outdated = bool(film) and (bool(stale) or not manifest or manifest.get("scene_ids") != order or manifest.get("scene_urls") != scene_urls or manifest.get("film_url") != film.get("film_url"))
        return AssemblyStatusResponse(scenes_with_compositions=sum(bool(compositions.get(sid, {}).get("composed_url")) for sid in order), scenes_total=len(order), film_assembled=bool(film) and not outdated, film_url=film.get("film_url") if film else None, has_audio=bool(film and film.get("has_audio")), film_outdated=outdated, scenes_needing_assembly=stale)

    async def _materialize(self, client, value: str, target: Path):
        parsed = urlparse(value)
        if parsed.path.startswith(("/outputs/", "/static/")) and (not parsed.netloc or parsed.hostname in {"localhost", "127.0.0.1"}):
            source = (self.root / parsed.path.lstrip("/")).resolve()
            if not source.is_relative_to(self.root.resolve()) or not source.is_file():
                raise PlaybackError("A saved scene video is missing", stage="film_delivery_media")
            await asyncio.to_thread(shutil.copy2, source, target)
        elif not parsed.scheme and Path(value).is_absolute():
            source = Path(value).resolve()
            if not source.is_relative_to(self.root.resolve()) or not source.is_file():
                raise PlaybackError("Scene video is outside the project media store", stage="film_delivery_media")
            await asyncio.to_thread(shutil.copy2, source, target)
        elif parsed.scheme in {"https", "http"}:
            response = await client.get(value, timeout=120)
            response.raise_for_status()
            target.write_bytes(response.content)
        else:
            raise PlaybackError("Scene has an unsupported video location", stage="film_delivery_media")

    async def assemble(self, project_id: str) -> AssembleFilmResponse:
        timer = start_timer()
        order, compositions = self._inputs(project_id)
        for sid in order:
            if self._scene_outdated(project_id, sid, compositions.get(sid)):
                # Failure aborts the film; never silently omit an unavailable scene.
                await self.scenes.assemble_completed_scene(project_id=project_id, scene_id=sid, allow_audio_generation=False)
                _, refreshed = self._inputs(project_id)
                compositions[sid] = refreshed.get(sid)
                if self._scene_outdated(project_id, sid, compositions[sid]):
                    raise StateError("Take choices changed during scene assembly. Assemble again.", stage="film_delivery", metadata={"scene_id": sid})
        scene_urls = [compositions[sid]["composed_url"] for sid in order]
        directory = self.root / "static" / "films" / project_id
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"film_{uuid4().hex[:12]}.mp4"
        try:
            with tempfile.TemporaryDirectory(prefix="film_delivery_") as temp:
                work = Path(temp)
                normalized = []
                expected_duration = 0.0
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    for index, url in enumerate(scene_urls):
                        source = work / f"scene_{index:03d}.mp4"
                        await self._materialize(client, url, source)
                        seconds = await asyncio.to_thread(SceneAssemblyService._probe_duration, source)
                        streams = await asyncio.to_thread(SceneAssemblyService._probe_streams, source)
                        video = next((row for row in streams if row.get("codec_type") == "video"), None)
                        if not video or not seconds or seconds <= 0:
                            raise PlaybackError("A scene has no playable video", stage="film_delivery_media", metadata={"scene_id": order[index]})
                        if index == 0:
                            width, height = int(video["width"]), int(video["height"])
                            width, height = width + width % 2, height + height % 2
                        expected_duration += seconds
                        target = work / f"normalized_{index:03d}.mp4"
                        # Preserve the first scene's canvas; letterbox other scenes.
                        command = ["ffmpeg", "-y", "-i", str(source)]
                        audio = any(row.get("codec_type") == "audio" for row in streams)
                        if not audio:
                            command += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                        command += ["-map", "0:v:0", "-map", "0:a:0" if audio else "1:a:0", "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24", "-af", "apad", "-t", str(seconds), "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(target)]
                        await asyncio.to_thread(SceneAssemblyService._run_ffmpeg, command, "film_delivery_normalize")
                        normalized.append(target)
                candidate = work / "film.mp4"
                await asyncio.to_thread(self.scenes._concat, normalized, candidate)
                duration = await asyncio.to_thread(SceneAssemblyService._probe_duration, candidate)
                if not duration or abs(duration - expected_duration) > max(0.3, len(order) * 0.1):
                    raise PlaybackError("The export duration does not match the complete scene list", stage="film_delivery_verify")
                await asyncio.to_thread(SceneAssemblyService._run_ffmpeg, ["ffmpeg", "-v", "error", "-i", str(candidate), "-f", "null", "-"], "film_delivery_decode")
                shutil.copy2(candidate, output)
            film_url = f"http://localhost:8010/static/films/{project_id}/{output.name}"
            result = AssembleFilmResponse(film_url=film_url, scene_count=len(order), total_duration_seconds=duration, has_audio=SceneAssemblyService._has_audio(output))
            current_order, current_compositions = self._inputs(project_id)
            if (current_order != order
                    or [current_compositions.get(sid, {}).get("composed_url") for sid in order] != scene_urls
                    or any(self._scene_outdated(project_id, sid, current_compositions.get(sid)) for sid in order)):
                raise StateError("The cut or recordings changed during export. Rebuild to deliver the current version.", stage="film_delivery_inputs", metadata={"project_id": project_id})
            self.storage.save_film(project_id=project_id, **result.model_dump())
            self.storage.save_delivery_manifest(project_id, "__film__", {"film_url": film_url, "scene_ids": order, "scene_urls": scene_urls})
        except (StateError, PlaybackError, PersistenceError):
            raise
        except Exception as exc:
            raise PlaybackError("Film delivery failed; the previous export is preserved", stage="film_delivery", metadata={"cause": type(exc).__name__}) from exc
        log_stage_event(project_id=project_id, job_id=None, provider="ffmpeg", stage="film_delivery", duration_ms=elapsed_ms(timer), extra={"scene_count": len(order), "film_url": film_url})
        return result
