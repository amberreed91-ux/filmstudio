from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.data.storage import get_storage
from app.models import RenderJobModel
from app.services.audio_pipeline_service import (
    SCORE_AMBIENT_PROVIDER,
    TrackStatus,
    audio_pipeline_service,
)
from app.services.stability import (
    PlaybackError,
    ProviderError,
    StateError,
    elapsed_ms,
    log_stage_event,
    start_timer,
)
from app.utils.helpers import (
    derive_scene_id_from_shot_id,
    derive_shot_number_from_shot_id,
)

logger = logging.getLogger(__name__)


class SceneAssemblyService:
    """Bake per-shot dialogue, normalize streams, and assemble one scene video."""

    def __init__(
        self,
        *,
        storage: Any = None,
        audio_service: Any = None,
        backend_root: Path | None = None,
        composed_root: Path | None = None,
    ) -> None:
        self.storage = storage
        self.audio_service = audio_service or audio_pipeline_service
        self.backend_root = backend_root or Path(__file__).resolve().parents[2]
        self.composed_root = composed_root or (self.backend_root / "static" / "composed")
        from app.services.scene_audio_source_service import SceneAudioSourceService
        self.audio_sources = SceneAudioSourceService(getattr(self.audio_service, "output_base", self.backend_root / "outputs" / "audio"))


    def collect_scene_jobs(
        self,
        project_id: str,
        scene_id: str,
    ) -> list[tuple[int, RenderJobModel]]:
        from app.services.take_selection_service import TakeSelectionService
        return TakeSelectionService(self.storage or get_storage("sqlite")).resolve(project_id, scene_id)

    async def assemble_completed_scene(
        self,
        *,
        project_id: str,
        scene_id: str,
        dialogue_provider: str = "cosyvoice",
        score_ambient_provider: str | None = None,
        overwrite: bool = True,
        allow_audio_generation: bool = False,
    ) -> dict[str, Any]:
        timer = start_timer()
        jobs = self.collect_scene_jobs(project_id, scene_id)
        if not jobs:
            raise StateError(
                f"Need at least 1 completed shot to assemble {scene_id}; found {len(jobs)}",
                stage="scene_assembly_discovery",
                metadata={"project_id": project_id, "scene_id": scene_id},
            )

        audio_inputs = self.audio_sources.snapshot(project_id, scene_id, [job.shot_id for _, job in jobs])
        source_media = self.source_media_snapshot(jobs)
        output_dir = self.composed_root / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        from uuid import uuid4
        output_path = output_dir / f"{scene_id}_{uuid4().hex[:12]}_audio.mp4"
        if not overwrite:
            storage = self.storage or get_storage("sqlite")
            previous = storage.get_delivery_manifest(project_id, scene_id)
            if (
                previous
                and previous.get("job_ids") == [job.id for _, job in jobs]
                and previous.get("audio_inputs") == audio_inputs
                and previous.get("source_media") == source_media
            ):
                previous_path = self._local_path(previous.get("composed_url", ""))
                if previous_path and previous_path.is_file():
                    return self._result(project_id, scene_id, jobs, previous_path, [], "existing")

        scene_text, characters = self._scene_context(project_id, scene_id)
        shot_records: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix=f"scene_assembly_{scene_id}_") as temp:
            work_dir = Path(temp)
            normalized: list[Path] = []
            canvas: tuple[int, int] | None = None
            async with httpx.AsyncClient(follow_redirects=True) as client:
                for index, (shot_number, job) in enumerate(jobs, start=1):
                    shot_timer = start_timer()
                    raw_path = work_dir / f"shot_{index:03d}_raw.mp4"
                    await self._materialize_job_asset(client, job, raw_path)

                    params = (
                        getattr(getattr(job, "input_payload", None), "parameters", None)
                        or {}
                    )
                    dialogue_handoff = None
                    handoff_lines = []
                    if allow_audio_generation:
                        from app.services.generation_contract import verify_dialogue_handoff

                        metadata = getattr(job, "metadata", None)
                        metadata = metadata if isinstance(metadata, dict) else {}
                        dialogue_handoff = metadata.get("creative_dialogue_handoff")
                        if dialogue_handoff is None:
                            raise StateError(
                                f"Narrative shot audio has no frozen handoff for {job.shot_id}",
                                stage="scene_assembly_dialogue_integrity",
                                metadata={"job_id": job.id, "shot_id": job.shot_id},
                            )
                        if dialogue_handoff is not None:
                            frozen_dialogue = verify_dialogue_handoff(
                                dialogue_handoff,
                                scene_id=derive_scene_id_from_shot_id(job.shot_id),
                                shot_id=job.shot_id,
                            )
                            from app.services.dialogue_authority import is_placeholder_dialogue

                            if any(is_placeholder_dialogue(str(row.get("text") or "")) for row in frozen_dialogue["lines"]):
                                raise StateError(
                                    f"Frozen shot handoff contains placeholder dialogue for {job.shot_id}",
                                    stage="scene_assembly_dialogue_integrity",
                                    metadata={"job_id": job.id, "shot_id": job.shot_id},
                                )
                            handoff_lines = frozen_dialogue["lines"]
                            if params.get("dialogue_lines") is not None and params.get("dialogue_lines") != handoff_lines:
                                raise StateError(
                                    f"Render job dialogue does not match its frozen handoff for {job.shot_id}",
                                    stage="scene_assembly_dialogue_integrity",
                                    metadata={"job_id": job.id, "shot_id": job.shot_id},
                                )
                    dialogue = await self.audio_service.generate_shot_dialogue(
                        project_id=project_id,
                        scene_id=scene_id,
                        shot_id=job.shot_id,
                        scene_text=scene_text,
                        dialogue_lines=handoff_lines if allow_audio_generation else [],
                        dialogue_line_range=params.get("dialogue_line_range"),
                        characters=characters,
                        split_reason=params.get("split_reason"),
                        provider=dialogue_provider,
                        allow_generation=allow_audio_generation,
                        scene_context={"shot_number": shot_number, "scene_id": scene_id},
                        dialogue_handoff=dialogue_handoff,
                        dialogue_scene_id=derive_scene_id_from_shot_id(job.shot_id),
                    )
                    if dialogue.get("status") == TrackStatus.FAILED:
                        dialogue_source = dialogue.get("source") or "live_provider"
                        raise ProviderError(
                            f"{dialogue_source} dialogue failed for {job.shot_id}",
                            stage="scene_assembly_dialogue",
                            metadata={
                                "job_id": job.id,
                                "shot_id": job.shot_id,
                                "provider": dialogue.get("provider") or dialogue_provider,
                                "dialogue_source": dialogue_source,
                                "dialogue_source_path": dialogue.get("source_path"),
                                "line_errors": dialogue.get("line_errors") or [],
                            },
                        )

                    clip_path = raw_path
                    merged = False
                    dialogue_path = str(dialogue.get("file_path") or "")
                    if dialogue.get("status") != TrackStatus.SKIPPED and dialogue_path:
                        merge = await self.audio_service.merge_audio_onto_video(
                            project_id=project_id,
                            scene_id=scene_id,
                            video_path=raw_path,
                            audio_path=Path(dialogue_path),
                            replace_original=False,
                            on_audio_overrun="error",
                        )
                        if merge.get("status") != TrackStatus.COMPLETE:
                            raise StateError(
                                "Shot audio does not fit the chosen take. Adjust dialogue timing or choose a longer take.",
                                stage="scene_assembly_audio_timing",
                                metadata={"project_id": project_id, "job_id": job.id, "shot_id": job.shot_id, "audio_result": merge},
                            )
                        merged_path = Path(str(merge.get("file_path") or ""))
                        if merge.get("status") == TrackStatus.COMPLETE and merged_path.exists():
                            clip_path = merged_path
                            merged = True

                    canonical = work_dir / f"shot_{index:03d}_canonical.mp4"
                    if canvas is None:
                        video = next((row for row in self._probe_streams(clip_path) if row.get("codec_type") == "video"), None)
                        if not video:
                            raise PlaybackError("Chosen take has no video stream", stage="scene_assembly_normalize", metadata={"job_id": job.id})
                        width, height = int(video["width"]), int(video["height"])
                        canvas = (width + width % 2, height + height % 2)
                    self._normalize_clip(clip_path, canonical, canvas=canvas)
                    normalized.append(canonical)
                    shot_record = {
                        "shot_id": job.shot_id,
                        "shot_number": shot_number,
                        "dialogue_provider": dialogue.get("provider"),
                        "dialogue_source": dialogue.get("source"),
                        "dialogue_source_path": dialogue.get("source_path"),
                        "dialogue_status": dialogue.get("status"),
                        "dialogue_lines": dialogue.get("lines_generated", 0),
                        "dialogue_baked": merged,
                        "duration_seconds": self._probe_duration(canonical),
                    }
                    shot_records.append(shot_record)
                    log_stage_event(
                        project_id=project_id,
                        job_id=job.id,
                        provider=getattr(job, "provider", ""),
                        stage="scene_assembly_shot_bake",
                        duration_ms=elapsed_ms(shot_timer),
                        extra={
                            "scene_id": scene_id,
                            "shot_id": job.shot_id,
                            "dialogue_source": dialogue.get("source"),
                            "dialogue_source_path": dialogue.get("source_path"),
                        },
                    )

            concat_path = work_dir / "scene_concat.mp4"
            self._concat(normalized, concat_path)
            provider = (score_ambient_provider or SCORE_AMBIENT_PROVIDER or "none").strip().lower()
            final_source = concat_path
            score_status = "skipped"
            if allow_audio_generation and provider != "none":
                duration = self._probe_duration(concat_path) or 15.0
                score = await self.audio_service.generate_score_ambient(
                    scene_id=scene_id,
                    project_id=project_id,
                    mood="",
                    score_notes="",
                    ambient_notes="continuous scene bed; preserve continuity across shot boundaries",
                    duration_seconds=duration,
                    provider=provider,
                )
                score_path = Path(str(score.get("file_path") or ""))
                score_status = str(score.get("status") or "")
                if score_path.exists() and score.get("status") == TrackStatus.COMPLETE:
                    mixed_path = work_dir / "scene_mixed.mp4"
                    self._mix_score(concat_path, score_path, mixed_path)
                    final_source = mixed_path

            shutil.copy2(final_source, output_path)

        validation = self.validate_continuity(output_path, shot_records)
        if not validation["valid"]:
            raise PlaybackError(
                "Assembled scene failed audio continuity validation",
                stage="scene_assembly_validation",
                metadata=validation,
            )

        if self.audio_sources.snapshot(project_id, scene_id, [job.shot_id for _, job in jobs]) != audio_inputs:
            raise StateError("A recording changed during assembly. Rebuild the scene to use the new audio.", stage="scene_assembly_audio_inputs", metadata={"project_id": project_id, "scene_id": scene_id})
        if self.source_media_snapshot(jobs) != source_media:
            raise StateError(
                "A rendered shot changed during assembly. Rebuild the scene to use the current take.",
                stage="scene_assembly_video_inputs",
                metadata={"project_id": project_id, "scene_id": scene_id},
            )
        storage = self.storage or get_storage("sqlite")
        duration = self._probe_duration(output_path)
        composed_url = (
            f"http://localhost:8010/static/composed/{project_id}/{output_path.name}"
        )
        storage.save_scene_composition(
            project_id=project_id,
            scene_id=scene_id,
            composed_url=composed_url,
            shot_count=len(jobs),
            duration_seconds=duration,
        )
        storage.save_delivery_manifest(project_id, scene_id, {
            "composed_url": composed_url,
            "job_ids": [job.id for _, job in jobs],
            "audio_inputs": audio_inputs,
            "source_media": source_media,
        })
        result = self._result(
            project_id,
            scene_id,
            jobs,
            output_path,
            shot_records,
            "complete",
        )
        result["audio_generation_requested"] = allow_audio_generation
        result["score_ambient_provider"] = provider if allow_audio_generation else "none"
        result["score_ambient_status"] = score_status
        result["dialogue_provider_requested"] = dialogue_provider
        result["audio_continuity"] = validation
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=dialogue_provider,
            stage="scene_assembly_complete",
            duration_ms=elapsed_ms(timer),
            extra={"scene_id": scene_id, "shot_count": len(jobs)},
        )
        return result

    def source_media_snapshot(self, jobs: list[tuple[int, RenderJobModel]]) -> dict[str, dict[str, str]]:
        """Fingerprint the selected shot sources without contacting providers.

        Files inside the backend media root are content-hashed; hosted or
        out-of-root sources are bound to their exact URI and selected job ID.
        """
        snapshot: dict[str, dict[str, str]] = {}
        root = self.backend_root.resolve()
        for _, job in jobs:
            url = str(getattr(getattr(job, "output_payload", None), "asset_url", "") or "").strip()
            local = self._local_path(url)
            source_kind = "uri"
            material = url.encode("utf-8")
            if local is not None and local.is_file() and local.resolve().is_relative_to(root):
                resolved = local.resolve()
                source_kind = "local_sha256"
                digest = hashlib.sha256()
                with resolved.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
                fingerprint = digest.hexdigest()
            else:
                fingerprint = hashlib.sha256(material).hexdigest()
            snapshot[job.shot_id] = {
                "job_id": str(job.id),
                "asset_url": url,
                "source_kind": source_kind,
                "sha256": fingerprint,
            }
        return snapshot

    async def _materialize_job_asset(
        self,
        client: httpx.AsyncClient,
        job: RenderJobModel,
        destination: Path,
    ) -> None:
        url = str(job.output_payload.asset_url or "").strip()
        local = self._local_path(url)
        if local:
            shutil.copy2(local, destination)
            return
        try:
            response = await client.get(url, timeout=120)
            response.raise_for_status()
        except httpx.HTTPError as first_error:
            from app.services.render import render_service

            refreshed = await render_service.refresh_output_url(job.id)
            if not refreshed:
                raise ProviderError(
                    f"Could not load rendered shot {job.shot_id}: {first_error}",
                    stage="scene_assembly_download",
                    metadata={"job_id": job.id, "provider": job.provider},
                ) from first_error
            response = await client.get(refreshed, timeout=120)
            response.raise_for_status()
        destination.write_bytes(response.content)

    def _local_path(self, value: str) -> Path | None:
        parsed = urlparse(value)
        if parsed.scheme == "file":
            candidate = Path(parsed.path)
        elif not parsed.scheme:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = self.backend_root / value.lstrip("/")
        else:
            return None
        return candidate if candidate.exists() else None

    def _normalize_clip(self, source: Path, destination: Path, *, canvas: tuple[int, int] | None = None) -> None:
        duration = self._probe_duration(source)
        if not duration:
            raise PlaybackError(
                f"Cannot determine duration for {source}",
                stage="scene_assembly_normalize",
            )
        if self._has_audio(source):
            command = [
                "ffmpeg", "-y", "-i", str(source),
                "-filter:a", "apad",
                "-t", f"{duration:.6f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                str(destination),
            ]
        else:
            command = [
                "ffmpeg", "-y", "-i", str(source),
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-t", f"{duration:.6f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                str(destination),
            ]
        if canvas:
            width, height = canvas
            command[-1:-1] = ["-map", "0:v:0", "-map", "0:a:0" if self._has_audio(source) else "1:a:0",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24"]
        self._run_ffmpeg(command, "scene_assembly_normalize")

    def _concat(self, clips: list[Path], destination: Path) -> None:
        concat_file = destination.with_suffix(".txt")
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in clips),
            encoding="utf-8",
        )
        self._run_ffmpeg(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy", str(destination),
            ],
            "scene_assembly_concat",
        )

    def _mix_score(self, video: Path, score: Path, destination: Path) -> None:
        self._run_ffmpeg(
            [
                "ffmpeg", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(score),
                "-filter_complex",
                "[0:a:0]volume=1.0[dialogue];"
                "[1:a:0]volume=0.3[bed];"
                "[dialogue][bed]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac",
                "-shortest", str(destination),
            ],
            "scene_assembly_score_mix",
        )

    def validate_continuity(
        self,
        output_path: Path,
        shots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        streams = self._probe_streams(output_path)
        video = next((row for row in streams if row.get("codec_type") == "video"), None)
        audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
        total = self._probe_duration(output_path) or 0.0
        audio_duration = float((audio or {}).get("duration") or total or 0.0)
        duration_delta = abs(total - audio_duration)
        packet_timeline = self._probe_audio_packet_timeline(output_path)
        packet_continuous = (
            packet_timeline["packet_count"] > 0
            and packet_timeline["max_gap_seconds"] <= 0.05
            and packet_timeline["max_overlap_seconds"] <= 0.05
        )
        dialogue_complete = all(
            shot.get("dialogue_status") in {TrackStatus.COMPLETE, TrackStatus.SKIPPED}
            and (
                shot.get("dialogue_status") == TrackStatus.SKIPPED
                or shot.get("dialogue_baked") is True
            )
            for shot in shots
        )
        return {
            "valid": bool(
                video
                and audio
                and total > 0
                and duration_delta <= 0.15
                and packet_continuous
                and dialogue_complete
            ),
            "has_video": bool(video),
            "has_audio": bool(audio),
            "duration_seconds": round(total, 3),
            "audio_duration_seconds": round(audio_duration, 3),
            "duration_delta_seconds": round(duration_delta, 3),
            "shot_boundaries_seconds": self._shot_boundaries(shots),
            "audio_stream_padded_per_shot": True,
            "audio_packet_timeline": packet_timeline,
            "dialogue_complete_per_shot": dialogue_complete,
        }

    @staticmethod
    def _shot_boundaries(shots: list[dict[str, Any]]) -> list[float]:
        elapsed = 0.0
        boundaries: list[float] = []
        for shot in shots[:-1]:
            elapsed += float(shot.get("duration_seconds") or 0.0)
            boundaries.append(round(elapsed, 3))
        return boundaries

    def _scene_context(self, project_id: str, scene_id: str) -> tuple[str, list[str]]:
        try:
            from app.services.project_store import project_store

            project = project_store.get_project(project_id) or {}
            scenes = (project.get("execution_summary") or {}).get("scenes") or []
            for scene in scenes:
                if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                    text = str(
                        scene.get("scene_text")
                        or scene.get("text")
                        or scene.get("description")
                        or ""
                    )
                    characters = [
                        str(item).strip()
                        for item in (scene.get("characters") or [])
                        if str(item).strip()
                    ]
                    return text, characters
        except Exception as exc:
            logger.warning("Scene context unavailable for %s/%s: %s", project_id, scene_id, exc)
        return "", []

    @staticmethod
    def _run_ffmpeg(command: list[str], stage: str) -> None:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise PlaybackError(
                (result.stderr or result.stdout or "ffmpeg failed")[-1000:],
                stage=stage,
            )

    @staticmethod
    def _probe_duration(path: Path) -> float | None:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        try:
            return float(result.stdout.strip()) if result.returncode == 0 else None
        except ValueError:
            return None

    @staticmethod
    def _has_audio(path: Path) -> bool:
        return any(
            row.get("codec_type") == "audio"
            for row in SceneAssemblyService._probe_streams(path)
        )

    @staticmethod
    def _probe_streams(path: Path) -> list[dict[str, Any]]:
        import json

        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_streams",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        try:
            payload = json.loads(result.stdout or "{}")
            return payload.get("streams") if isinstance(payload.get("streams"), list) else []
        except ValueError:
            return []

    @staticmethod
    def _probe_audio_packet_timeline(path: Path) -> dict[str, Any]:
        import json

        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "packet=pts_time,duration_time",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "packet_count": 0,
                "max_gap_seconds": 0.0,
                "max_overlap_seconds": 0.0,
            }
        try:
            packets = json.loads(result.stdout or "{}").get("packets") or []
        except ValueError:
            packets = []
        previous_end: float | None = None
        max_gap = 0.0
        max_overlap = 0.0
        valid_packets = 0
        for packet in packets:
            if not isinstance(packet, dict):
                continue
            try:
                start = float(packet["pts_time"])
                duration = float(packet.get("duration_time") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            if previous_end is not None:
                delta = start - previous_end
                if delta > max_gap:
                    max_gap = delta
                elif delta < 0 and abs(delta) > max_overlap:
                    max_overlap = abs(delta)
            previous_end = start + max(duration, 0.0)
            valid_packets += 1
        return {
            "packet_count": valid_packets,
            "max_gap_seconds": round(max_gap, 6),
            "max_overlap_seconds": round(max_overlap, 6),
        }

    def _result(
        self,
        project_id: str,
        scene_id: str,
        jobs: list[tuple[int, RenderJobModel]],
        output_path: Path,
        shots: list[dict[str, Any]],
        status: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "project_id": project_id,
            "scene_id": scene_id,
            "composed_url": (
                f"http://localhost:8010/static/composed/{project_id}/{output_path.name}"
            ),
            "output_path": str(output_path),
            "shot_count": len(jobs),
            "shot_ids": [job.shot_id for _, job in jobs],
            "job_ids": [job.id for _, job in jobs],
            "duration_seconds": self._probe_duration(output_path),
            "has_audio": self._has_audio(output_path),
            "shots": shots,
        }


scene_assembly_service = SceneAssemblyService()
