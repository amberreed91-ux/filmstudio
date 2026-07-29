"""
FFmpegStitchingService

Stitches approved scene renders with transitions and mixed audio into a
single final MP4.

Audio mix levels:
  dialogue  100%
  score      40%
  ambient    60%

Transitions:
  cut / match_cut / smash_cut  → direct concat (no filter)
  dissolve / cross_dissolve    → xfade=fade, 0.5 s
  fade_to_black                → fade-out + fade-in through black, 0.8 s
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ffmpeg-stitching")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_OUTPUTS_ROOT = _BACKEND_ROOT / "outputs"
_AUDIO_ROOT = _OUTPUTS_ROOT / "audio"
_FINAL_FILMS_DIR = _OUTPUTS_ROOT / "final_films"
_FINAL_FILMS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory job store  {project_id: job_dict}
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}


def _new_job(project_id: str) -> Dict[str, Any]:
    return {
        "job_id": f"stitch_{project_id}_{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "status": "pending",          # pending | running | complete | failed
        "progress": 0,                # 0-100
        "current_scene": None,
        "scenes_total": 0,
        "scenes_done": 0,
        "output_path": None,
        "output_url": None,
        "error": None,
        "transitions_used": [],
        "scene_count": 0,
        "started_at": None,
        "finished_at": None,
        "advisory": "Stitching queued.",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except Exception:
        return False


def _ffmpeg_python_available() -> bool:
    try:
        import ffmpeg  # noqa: F401
        return True
    except ImportError:
        return False


def _get_project(project_id: str) -> Optional[Dict[str, Any]]:
    try:
        from app.services.project_store import project_store
        return project_store.get_project(project_id)
    except Exception as exc:
        logger.warning("Could not load project %s: %s", project_id, exc)
        return None


def _get_approved_scenes_in_order(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return scene dicts for approved scenes, in film_cut order."""
    approved_ids: List[str] = project.get("approved_scenes") or []
    if not approved_ids:
        return []

    summary = project.get("execution_summary") or {}
    all_scenes: List[Dict[str, Any]] = summary.get("scenes") or []
    scene_map = {
        str(s.get("scene_id", "")): s
        for s in all_scenes
        if isinstance(s, dict)
    }

    # Respect film_cut order if available
    film_cut = project.get("film_cut") or {}
    ordered_ids: List[str] = film_cut.get("scene_order") or film_cut.get("included_scenes") or approved_ids

    result = []
    for sid in ordered_ids:
        if sid in approved_ids and sid in scene_map:
            result.append(scene_map[sid])
    return result


def _get_render_video_url(project_id: str, scene_id: str) -> Optional[str]:
    """
    Try to find a completed render video URL for this scene.
    Checks render_service jobs for matching shot_id.
    """
    try:
        from app.services.render import render_service
        for job in render_service._jobs.values():
            job_scene = str(job.shot_id or "").split("_shot_")[0]
            if job_scene == scene_id and job.status == "complete":
                payload = job.output_payload or {}
                url = payload.get("asset_url") or payload.get("video_url") or payload.get("thumbnail_url")
                if url:
                    return str(url)
    except Exception as exc:
        logger.debug("render_service lookup failed for %s: %s", scene_id, exc)
    return None


def _get_audio_path(project_id: str, scene_id: str, track: str) -> Optional[Path]:
    """Return path to audio file if it exists."""
    p = _AUDIO_ROOT / project_id / scene_id / f"{track}_{scene_id}.wav"
    return p if p.exists() else None


def _silence_wav(duration: float, path: Path) -> None:
    """Generate a silent WAV file using ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )


def _get_video_duration(path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return 5.0  # fallback


# ---------------------------------------------------------------------------
# Core stitching logic
# ---------------------------------------------------------------------------

class FFmpegStitchingService:

    def capabilities(self) -> Dict[str, Any]:
        has_ffmpeg = _ffmpeg_available()
        has_ffmpeg_python = _ffmpeg_python_available()
        return {
            "ffmpeg_available": has_ffmpeg,
            "ffmpeg_python_available": has_ffmpeg_python,
            "mock_mode": not has_ffmpeg,
        }

    def get_job(self, project_id: str) -> Optional[Dict[str, Any]]:
        return _jobs.get(project_id)

    def _approved_editorial_transition_map(self, project_id: str) -> Dict[tuple[str, str], Dict[str, Any]]:
        plan = self._approved_editorial_stitch_plan(project_id)
        advisories = plan.get("transition_advisories") or []
        out: Dict[tuple[str, str], Dict[str, Any]] = {}
        for advisory in advisories:
            if not isinstance(advisory, dict):
                continue
            left = str(advisory.get("from_scene_id") or "").strip()
            right = str(advisory.get("to_scene_id") or "").strip()
            if left and right:
                out[(left, right)] = advisory
        return out

    def _approved_editorial_stitch_plan(self, project_id: str) -> Dict[str, Any]:
        try:
            from app.services.editorial_intelligence_service import editorial_intelligence_service

            return editorial_intelligence_service.latest_stitch_plan(project_id)
        except Exception as exc:
            logger.debug("Editorial stitch plan lookup failed for %s: %s", project_id, exc)
            return {"transition_advisories": [], "timing_adjustments": []}

    def _approved_editorial_timing_map(self, project_id: str) -> Dict[str, Dict[str, Any]]:
        plan = self._approved_editorial_stitch_plan(project_id)
        out: Dict[str, Dict[str, Any]] = {}
        for adjustment in plan.get("timing_adjustments") or []:
            if not isinstance(adjustment, dict):
                continue
            scene_id = str(adjustment.get("target_scene_id") or "").strip()
            adjustment_type = str(adjustment.get("adjustment_type") or "").strip()
            if scene_id and adjustment_type in {"tail_hold", "compress_duration", "tail_trim"}:
                out[scene_id] = adjustment
        return out

    # ------------------------------------------------------------------
    # Public entry point — starts background task
    # ------------------------------------------------------------------

    async def start_stitch(self, project_id: str) -> Dict[str, Any]:
        """Create a job and kick off background stitching."""
        job = _new_job(project_id)
        _jobs[project_id] = job

        if not _ffmpeg_available():
            # Mock mode — simulate progress
            asyncio.create_task(self._mock_stitch(project_id))
        else:
            asyncio.create_task(self._run_stitch(project_id))

        return job

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    async def _mock_stitch(self, project_id: str) -> None:
        job = _jobs[project_id]
        job["status"] = "running"
        job["started_at"] = time.time()
        job["advisory"] = "FFmpeg not found — running in mock mode."

        project = _get_project(project_id)
        scenes = _get_approved_scenes_in_order(project or {})
        job["scenes_total"] = len(scenes)
        job["scene_count"] = len(scenes)

        for i, scene in enumerate(scenes):
            job["current_scene"] = scene.get("scene_id")
            job["progress"] = int((i / max(len(scenes), 1)) * 90)
            await asyncio.sleep(0.5)
            job["scenes_done"] = i + 1

        # Fake output
        output_path = _FINAL_FILMS_DIR / f"{project_id}_final.mp4"
        job["output_path"] = str(output_path)
        job["output_url"] = f"/outputs/final_films/{project_id}_final.mp4"
        job["status"] = "complete"
        job["progress"] = 100
        job["finished_at"] = time.time()
        job["advisory"] = (
            f"Mock stitch complete — {len(scenes)} approved scenes assembled. "
            "Install FFmpeg for real video stitching."
        )
        job["transitions_used"] = ["cut"] * max(0, len(scenes) - 1)

    # ------------------------------------------------------------------
    # Real FFmpeg stitching
    # ------------------------------------------------------------------

    async def _run_stitch(self, project_id: str) -> None:
        job = _jobs[project_id]
        job["status"] = "running"
        job["started_at"] = time.time()

        try:
            project = _get_project(project_id)
            if not project:
                raise RuntimeError(f"Project {project_id} not found")

            scenes = _get_approved_scenes_in_order(project)
            if not scenes:
                raise RuntimeError("No approved scenes to stitch")

            job["scenes_total"] = len(scenes)
            job["scene_count"] = len(scenes)
            job["advisory"] = f"Stitching {len(scenes)} approved scenes..."

            output_path = _FINAL_FILMS_DIR / f"{project_id}_final.mp4"

            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._stitch_sync,
                project_id,
                scenes,
                str(output_path),
                job,
            )

            job["output_path"] = str(output_path)
            job["output_url"] = f"/outputs/final_films/{project_id}_final.mp4"
            job["status"] = "complete"
            job["progress"] = 100
            job["finished_at"] = time.time()
            job["advisory"] = (
                f"Film assembled — {len(scenes)} scenes, "
                f"{len(job['transitions_used'])} transitions applied."
            )

        except Exception as exc:
            logger.error("STITCH_FAILED | project=%s | %s", project_id, exc, exc_info=True)
            job["status"] = "failed"
            job["error"] = str(exc)
            job["finished_at"] = time.time()
            job["advisory"] = "Stitching encountered an error. Check logs."

    def _stitch_sync(
        self,
        project_id: str,
        scenes: List[Dict[str, Any]],
        output_path: str,
        job: Dict[str, Any],
    ) -> None:
        """Synchronous stitching — runs in thread pool."""
        with tempfile.TemporaryDirectory(prefix="stitch_") as tmpdir:
            tmp = Path(tmpdir)

            # ----------------------------------------------------------------
            # Step 1: Prepare per-scene mixed audio + video segments
            # ----------------------------------------------------------------
            segment_paths: List[str] = []
            transition_types: List[str] = []
            durations: List[float] = []
            editorial_transitions = self._approved_editorial_transition_map(project_id)
            editorial_timing = self._approved_editorial_timing_map(project_id)

            for i, scene in enumerate(scenes):
                scene_id = str(scene.get("scene_id", f"scene_{i}"))
                job["current_scene"] = scene_id
                job["progress"] = int((i / len(scenes)) * 80)
                job["scenes_done"] = i

                # --- Video source ---
                video_url = _get_render_video_url(project_id, scene_id)
                video_path: Optional[str] = None

                if video_url and video_url.startswith("/outputs/"):
                    local = _BACKEND_ROOT / video_url.lstrip("/")
                    if local.exists():
                        video_path = str(local)

                # --- Audio tracks ---
                dialogue = _get_audio_path(project_id, scene_id, "dialogue")
                score = _get_audio_path(project_id, scene_id, "score")
                ambient = _get_audio_path(project_id, scene_id, "ambient")

                # Determine duration
                if video_path:
                    duration = _get_video_duration(video_path)
                else:
                    duration = float(scene.get("duration_estimate") or 5.0)
                timing_adjustment = editorial_timing.get(scene_id) or {}
                if timing_adjustment.get("adjustment_type") in {"compress_duration", "tail_trim"}:
                    try:
                        duration = max(1.0, duration - float(timing_adjustment.get("seconds") or 0.0))
                    except Exception:
                        duration = duration

                # --- Mix audio ---
                mixed_audio = tmp / f"audio_{i}_{scene_id}.wav"
                self._mix_audio(
                    dialogue=str(dialogue) if dialogue else None,
                    score=str(score) if score else None,
                    ambient=str(ambient) if ambient else None,
                    duration=duration,
                    output=str(mixed_audio),
                    tmp=tmp,
                    idx=i,
                )

                # --- Build scene segment (video + mixed audio) ---
                segment = tmp / f"seg_{i}_{scene_id}.mp4"
                self._build_segment(
                    video_path=video_path,
                    audio_path=str(mixed_audio),
                    duration=duration,
                    output=str(segment),
                    tmp=tmp,
                    idx=i,
                )
                if timing_adjustment.get("adjustment_type") == "tail_hold":
                    try:
                        hold_seconds = max(0.0, min(float(timing_adjustment.get("seconds") or 0.0), 4.0))
                    except Exception:
                        hold_seconds = 0.0
                    if hold_seconds > 0:
                        held_segment = tmp / f"seg_{i}_{scene_id}_held.mp4"
                        self._apply_tail_hold(
                            input_path=str(segment),
                            output_path=str(held_segment),
                            hold_seconds=hold_seconds,
                        )
                        segment = held_segment
                        duration += hold_seconds
                durations.append(duration)
                segment_paths.append(str(segment))

                # --- Collect transition for next scene ---
                if i < len(scenes) - 1:
                    next_scene_id = str(scenes[i + 1].get("scene_id", f"scene_{i + 1}"))
                    editorial = editorial_transitions.get((scene_id, next_scene_id)) or {}
                    ta = editorial or scene.get("transition_advisory") or {}
                    t_type = str(
                        ta.get("recommended_transition_type")
                        or ta.get("transition_type")
                        or "cut"
                    ).lower()
                    if t_type == "hold_then_cut":
                        t_type = "cut"
                    transition_types.append(t_type)

            job["transitions_used"] = transition_types
            if editorial_transitions:
                job["editorial_transition_source"] = "editorial_intelligence"
            if editorial_timing:
                job["editorial_timing_source"] = "editorial_intelligence"
                job["editorial_timing_adjustments"] = list(editorial_timing.values())

            # ----------------------------------------------------------------
            # Step 2: Concatenate segments with transitions
            # ----------------------------------------------------------------
            job["progress"] = 85
            job["advisory"] = "Applying transitions and assembling final cut..."

            self._concat_with_transitions(
                segments=segment_paths,
                durations=durations,
                transitions=transition_types,
                output=output_path,
                tmp=tmp,
            )

            job["scenes_done"] = len(scenes)

    # ------------------------------------------------------------------
    # Audio mixing
    # ------------------------------------------------------------------

    def _mix_audio(
        self,
        dialogue: Optional[str],
        score: Optional[str],
        ambient: Optional[str],
        duration: float,
        output: str,
        tmp: Path,
        idx: int,
    ) -> None:
        """Mix dialogue (100%) + score (40%) + ambient (60%) to stereo WAV."""
        inputs = []
        filter_parts = []
        mix_labels = []
        stream_idx = 0

        def _add_track(path: Optional[str], volume: float, label: str) -> None:
            nonlocal stream_idx
            if path and Path(path).exists():
                inputs += ["-i", path]
                filter_parts.append(
                    f"[{stream_idx}:a]volume={volume},atrim=duration={duration}[{label}]"
                )
                mix_labels.append(f"[{label}]")
                stream_idx += 1

        _add_track(dialogue, 1.0, "d")
        _add_track(score, 0.4, "s")
        _add_track(ambient, 0.6, "a")

        if not mix_labels:
            # No audio at all — generate silence
            _silence_wav(duration, Path(output))
            return

        n = len(mix_labels)
        mix_filter = "".join(mix_labels) + f"amix=inputs={n}:duration=longest[out]"
        filter_complex = ";".join(filter_parts) + ";" + mix_filter

        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + [
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-t", str(duration),
                output,
            ]
        )
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)

    # ------------------------------------------------------------------
    # Segment builder
    # ------------------------------------------------------------------

    def _build_segment(
        self,
        video_path: Optional[str],
        audio_path: str,
        duration: float,
        output: str,
        tmp: Path,
        idx: int,
    ) -> None:
        """Combine video + mixed audio into a single MP4 segment."""
        if video_path and Path(video_path).exists():
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-t", str(duration),
                "-shortest",
                output,
            ]
        else:
            # No video — generate black video with audio
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s=1920x1080:r=24:d={duration}",
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-t", str(duration),
                "-shortest",
                output,
            ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)

    def _apply_tail_hold(self, input_path: str, output_path: str, hold_seconds: float) -> None:
        """Extend the final frame and audio bed for an editorial held beat."""
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter_complex",
            (
                f"[0:v]tpad=stop_mode=clone:stop_duration={hold_seconds}[v];"
                f"[0:a]apad=pad_dur={hold_seconds}[a]"
            ),
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)

    # ------------------------------------------------------------------
    # Concat with transitions
    # ------------------------------------------------------------------

    def _concat_with_transitions(
        self,
        segments: List[str],
        durations: List[float],
        transitions: List[str],
        output: str,
        tmp: Path,
    ) -> None:
        """
        Concatenate segments applying transitions between them.

        Strategy:
        - cut / match_cut / smash_cut → simple concat list
        - dissolve / cross_dissolve   → xfade=fade 0.5s
        - fade_to_black               → fade out + fade in 0.8s
        """
        if len(segments) == 1:
            # Single scene — just copy
            subprocess.run(
                ["ffmpeg", "-y", "-i", segments[0], "-c", "copy", output],
                capture_output=True,
                check=True,
                timeout=120,
            )
            return

        # Separate into groups: direct-cut runs vs xfade pairs
        # Build a chain using xfade filter for dissolve transitions,
        # and concat demuxer for cut transitions.
        # Simplest robust approach: process pair-by-pair, building up.

        current = segments[0]
        current_duration = durations[0]

        for i, (next_seg, t_type) in enumerate(zip(segments[1:], transitions)):
            next_duration = durations[i + 1]
            merged = str(tmp / f"merged_{i}.mp4")

            if t_type in ("dissolve", "cross_dissolve"):
                self._apply_xfade(
                    a=current,
                    b=next_seg,
                    a_duration=current_duration,
                    xfade_duration=0.5,
                    output=merged,
                )
                current_duration = current_duration + next_duration - 0.5
            elif t_type == "fade_to_black":
                self._apply_fade_to_black(
                    a=current,
                    b=next_seg,
                    a_duration=current_duration,
                    fade_duration=0.8,
                    output=merged,
                )
                current_duration = current_duration + next_duration
            else:
                # cut / match_cut / smash_cut — direct concat
                self._concat_direct([current, next_seg], merged)
                current_duration = current_duration + next_duration

            current = merged

        # Final copy to output
        subprocess.run(
            ["ffmpeg", "-y", "-i", current, "-c", "copy", output],
            capture_output=True,
            check=True,
            timeout=300,
        )

    def _apply_xfade(
        self,
        a: str,
        b: str,
        a_duration: float,
        xfade_duration: float,
        output: str,
    ) -> None:
        """Apply xfade=fade transition between two clips."""
        offset = max(0.0, a_duration - xfade_duration)
        cmd = [
            "ffmpeg", "-y",
            "-i", a,
            "-i", b,
            "-filter_complex",
            (
                f"[0:v][1:v]xfade=transition=fade:duration={xfade_duration}:offset={offset}[v];"
                f"[0:a][1:a]acrossfade=d={xfade_duration}[a]"
            ),
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-c:a", "aac",
            output,
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)

    def _apply_fade_to_black(
        self,
        a: str,
        b: str,
        a_duration: float,
        fade_duration: float,
        output: str,
    ) -> None:
        """Fade out clip A to black, then fade in clip B from black."""
        fade_out_start = max(0.0, a_duration - fade_duration)
        # Fade out A
        faded_a = output + "_fa.mp4"
        cmd_a = [
            "ffmpeg", "-y", "-i", a,
            "-vf", f"fade=t=out:st={fade_out_start}:d={fade_duration}",
            "-af", f"afade=t=out:st={fade_out_start}:d={fade_duration}",
            "-c:v", "libx264", "-c:a", "aac",
            faded_a,
        ]
        subprocess.run(cmd_a, capture_output=True, check=True, timeout=300)

        # Fade in B
        faded_b = output + "_fb.mp4"
        cmd_b = [
            "ffmpeg", "-y", "-i", b,
            "-vf", f"fade=t=in:st=0:d={fade_duration}",
            "-af", f"afade=t=in:st=0:d={fade_duration}",
            "-c:v", "libx264", "-c:a", "aac",
            faded_b,
        ]
        subprocess.run(cmd_b, capture_output=True, check=True, timeout=300)

        # Concat
        self._concat_direct([faded_a, faded_b], output)

    def _concat_direct(self, segments: List[str], output: str) -> None:
        """Concat segments using FFmpeg concat demuxer (no re-encode)."""
        list_file = output + "_list.txt"
        with open(list_file, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output,
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
ffmpeg_stitching_service = FFmpegStitchingService()
