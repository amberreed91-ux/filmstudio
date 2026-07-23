from __future__ import annotations

import asyncio
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

    def collect_scene_jobs(
        self,
        project_id: str,
        scene_id: str,
    ) -> list[tuple[int, RenderJobModel]]:
        storage = self.storage or get_storage("sqlite")
        jobs = storage.list_jobs(project_id=project_id, limit=500)
        latest_by_number: dict[int, RenderJobModel] = {}
        for job in jobs:
            if getattr(job, "status", "") != "complete":
                continue
            shot_id = str(getattr(job, "shot_id", "") or "")
            if derive_scene_id_from_shot_id(shot_id) != scene_id:
                continue
            output = getattr(job, "output_payload", None)
            if not str(getattr(output, "asset_url", "") or "").strip():
                continue
            number = derive_shot_number_from_shot_id(shot_id)
            if number <= 0:
                continue
            existing = latest_by_number.get(number)
            if existing is None or str(job.created_at) > str(existing.created_at):
                latest_by_number[number] = job
        return sorted(latest_by_number.items())

    async def assemble_completed_scene(
        self,
        *,
        project_id: str,
        scene_id: str,
        dialogue_provider: str = "cosyvoice",
        score_ambient_provider: str | None = None,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        timer = start_timer()
        jobs = self.collect_scene_jobs(project_id, scene_id)
        if len(jobs) < 2:
            raise StateError(
                f"Need at least 2 completed shots to assemble {scene_id}; found {len(jobs)}",
                stage="scene_assembly_discovery",
                metadata={"project_id": project_id, "scene_id": scene_id},
            )

        output_dir = self.composed_root / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{scene_id}_audio.mp4"
        if output_path.exists() and not overwrite:
            return self._result(project_id, scene_id, jobs, output_path, [], "existing")

        scene_text, characters = self._scene_context(project_id, scene_id)
        shot_records: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix=f"scene_assembly_{scene_id}_") as temp:
            work_dir = Path(temp)
            normalized: list[Path] = []
            async with httpx.AsyncClient(follow_redirects=True) as client:
                for index, (shot_number, job) in enumerate(jobs, start=1):
                    shot_timer = start_timer()
                    raw_path = work_dir / f"shot_{index:03d}_raw.mp4"
                    await self._materialize_job_asset(client, job, raw_path)

                    params = (
                        getattr(getattr(job, "input_payload", None), "parameters", None)
                        or {}
                    )
                    dialogue = await self.audio_service.generate_shot_dialogue(
                        project_id=project_id,
                        scene_id=scene_id,
                        shot_id=job.shot_id,
                        scene_text=scene_text,
                        dialogue_lines=params.get("dialogue_lines"),
                        dialogue_line_range=params.get("dialogue_line_range"),
                        characters=characters,
                        split_reason=params.get("split_reason"),
                        provider=dialogue_provider,
                        scene_context={"shot_number": shot_number, "scene_id": scene_id},
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
                            on_audio_overrun="freeze_last_frame",
                        )
                        merged_path = Path(str(merge.get("file_path") or ""))
                        if merge.get("status") == TrackStatus.COMPLETE and merged_path.exists():
                            clip_path = merged_path
                            merged = True

                    canonical = work_dir / f"shot_{index:03d}_canonical.mp4"
                    self._normalize_clip(clip_path, canonical)
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
            if provider != "none":
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
        result = self._result(
            project_id,
            scene_id,
            jobs,
            output_path,
            shot_records,
            "complete",
        )
        result["score_ambient_provider"] = provider
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

    def _normalize_clip(self, source: Path, destination: Path) -> None:
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
            "duration_seconds": self._probe_duration(output_path),
            "has_audio": self._has_audio(output_path),
            "shots": shots,
        }


scene_assembly_service = SceneAssemblyService()
