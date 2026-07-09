"""
FinalExportService
==================
Packages the stitched film for download with:
  - Optional title card (FFmpeg drawtext, black bg, white text, fade in/out)
  - Optional end card
  - Metadata embedding (title, artist/director, year, comment)
  - Resolution scaling (720p / 1080p / 4K)
  - Format selection (mp4 / mov)
  - Quality presets (low / medium / high → CRF values)

Export is ADDITIVE — the stitched source file is never modified.
Output: outputs/exports/{project_id}/{job_id}.{format}

Mock mode activates automatically when FFmpeg is not installed.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger("export-service")

# ---------------------------------------------------------------------------
# Export options model
# ---------------------------------------------------------------------------

class ExportOptions(BaseModel):
    include_title_card: bool = True
    title_card_duration: int = 3          # seconds
    include_end_card: bool = False
    end_card_duration: int = 3            # seconds
    resolution: str = "1080p"            # 720p | 1080p | 4K
    format: str = "mp4"                  # mp4 | mov
    quality: str = "high"               # low | medium | high
    filmmaker_name: Optional[str] = None  # override; falls back to project metadata


# ---------------------------------------------------------------------------
# Resolution / quality maps
# ---------------------------------------------------------------------------

RESOLUTION_MAP: Dict[str, tuple[int, int]] = {
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "4K":    (3840, 2160),
    "4k":    (3840, 2160),
}

QUALITY_CRF: Dict[str, int] = {
    "low":    28,
    "medium": 23,
    "high":   18,
}

FORMAT_CODEC: Dict[str, str] = {
    "mp4": "libx264",
    "mov": "libx264",   # H.264 in MOV container
}

FORMAT_MIME: Dict[str, str] = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FinalExportService:
    """
    Packages the stitched film into a final deliverable.

    Lazy-loads FFmpeg — mock mode if not available.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}   # project_id → job dict
        self._output_base = Path("outputs/exports")
        self._stitched_base = Path("outputs/final_films")
        self._output_base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Capability detection
    # ------------------------------------------------------------------

    def capabilities(self) -> Dict[str, Any]:
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        try:
            import ffmpeg as _ffmpeg  # noqa: F401
            ffmpeg_python_ok = True
        except ImportError:
            ffmpeg_python_ok = False
        return {
            "ffmpeg_available": ffmpeg_ok,
            "ffmpeg_python_available": ffmpeg_python_ok,
            "mock_mode": not (ffmpeg_ok and ffmpeg_python_ok),
        }

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def get_job(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(project_id)

    def _set_job(self, project_id: str, **kwargs: Any) -> Dict[str, Any]:
        job = self._jobs.setdefault(project_id, {})
        job.update(kwargs)
        return job

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_export(
        self,
        project_id: str,
        options: ExportOptions,
    ) -> Dict[str, Any]:
        """
        Kick off an export job in the background.
        Returns the initial job dict immediately.
        """
        job_id = str(uuid4())
        job = self._set_job(
            project_id,
            job_id=job_id,
            project_id=project_id,
            status="pending",
            progress=0,
            options=options.model_dump(),
            output_path=None,
            output_url=None,
            error=None,
            started_at=time.time(),
            finished_at=None,
            advisory="Export queued — assembling your film package.",
        )
        asyncio.create_task(self._run_export(project_id, job_id, options))
        return dict(job)

    # ------------------------------------------------------------------
    # Core export pipeline
    # ------------------------------------------------------------------

    async def _run_export(
        self,
        project_id: str,
        job_id: str,
        options: ExportOptions,
    ) -> None:
        caps = self.capabilities()
        if caps["mock_mode"]:
            await self._run_mock_export(project_id, job_id, options)
            return

        try:
            self._set_job(project_id, status="running", progress=5,
                          advisory="Locating stitched source file…")

            # 1. Find stitched source
            source = self._find_stitched_source(project_id)
            if source is None:
                raise FileNotFoundError(
                    "No stitched film found. Run /stitch first."
                )

            # 2. Resolve project metadata
            title, filmmaker = self._resolve_metadata(project_id, options)
            year = str(datetime.now().year)

            # 3. Prepare output path
            out_dir = self._output_base / project_id
            out_dir.mkdir(parents=True, exist_ok=True)
            ext = options.format.lower()
            out_path = out_dir / f"{job_id}.{ext}"

            self._set_job(project_id, progress=15,
                          advisory="Building export pipeline…")

            # 4. Build the FFmpeg pipeline
            await self.export_film(
                project_id=project_id,
                source_path=source,
                out_path=out_path,
                options=options,
                title=title,
                filmmaker=filmmaker,
                year=year,
            )

            self._set_job(project_id, progress=90,
                          advisory="Embedding metadata…")

            # 5. Embed metadata into the output file
            await self.embed_metadata(out_path, title, filmmaker, year)

            output_url = f"/outputs/exports/{project_id}/{job_id}.{ext}"
            self._set_job(
                project_id,
                status="complete",
                progress=100,
                output_path=str(out_path),
                output_url=output_url,
                finished_at=time.time(),
                advisory="Your film is ready for download.",
            )
            logger.info("EXPORT_COMPLETE | project=%s | out=%s", project_id, out_path)

        except Exception as exc:
            logger.error("EXPORT_FAILED | project=%s | %s", project_id, exc)
            self._set_job(
                project_id,
                status="failed",
                error=str(exc),
                finished_at=time.time(),
                advisory=f"Export failed: {exc}",
            )

    # ------------------------------------------------------------------
    # FFmpeg pipeline
    # ------------------------------------------------------------------

    async def export_film(
        self,
        project_id: str,
        source_path: Path,
        out_path: Path,
        options: ExportOptions,
        title: str,
        filmmaker: str,
        year: str,
    ) -> None:
        """
        Build the full export:
          title card → main film → end card → scale → encode
        All done in a single FFmpeg pass where possible.
        """
        import ffmpeg

        w, h = RESOLUTION_MAP.get(options.resolution, (1920, 1080))
        crf = QUALITY_CRF.get(options.quality, 18)
        codec = FORMAT_CODEC.get(options.format.lower(), "libx264")

        segments: list[Any] = []

        # --- Title card ---
        if options.include_title_card:
            self._set_job(project_id, progress=25, advisory="Generating title card…")
            tc = await self._build_title_card(
                title=title,
                subtitle=filmmaker,
                duration=options.title_card_duration,
                width=w,
                height=h,
            )
            segments.append(tc)

        # --- Main film ---
        self._set_job(project_id, progress=40, advisory="Scaling main film…")
        main = (
            ffmpeg
            .input(str(source_path))
            .video
            .filter("scale", w, h, force_original_aspect_ratio="decrease")
            .filter("pad", w, h, "(ow-iw)/2", "(oh-ih)/2")
        )
        main_audio = ffmpeg.input(str(source_path)).audio
        segments.append((main, main_audio))

        # --- End card ---
        if options.include_end_card:
            self._set_job(project_id, progress=55, advisory="Generating end card…")
            ec = await self._build_end_card(
                title=title,
                duration=options.end_card_duration,
                width=w,
                height=h,
            )
            segments.append(ec)

        self._set_job(project_id, progress=65, advisory="Concatenating segments…")

        # Concat all segments
        if len(segments) == 1:
            v_stream, a_stream = segments[0]
            out = ffmpeg.output(
                v_stream, a_stream,
                str(out_path),
                vcodec=codec,
                acodec="aac",
                crf=crf,
                preset="fast",
                movflags="+faststart",
            )
        else:
            v_streams = [s[0] for s in segments]
            a_streams = [s[1] for s in segments]
            concat = ffmpeg.concat(*[val for pair in zip(v_streams, a_streams) for val in pair],
                                   v=1, a=1)
            out = ffmpeg.output(
                concat,
                str(out_path),
                vcodec=codec,
                acodec="aac",
                crf=crf,
                preset="fast",
                movflags="+faststart",
            )

        self._set_job(project_id, progress=75, advisory="Encoding final film…")
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: out.overwrite_output().run(quiet=True),
        )

    async def _build_title_card(
        self,
        title: str,
        subtitle: str,
        duration: int,
        width: int,
        height: int,
    ) -> tuple[Any, Any]:
        """
        Generate a title card using FFmpeg lavfi + drawtext.
        Black background, white title (large), white subtitle (smaller).
        Fade in 1s, hold, fade out 1s.
        """
        import ffmpeg

        # Escape special chars for drawtext
        safe_title = title.replace("'", "\\'").replace(":", "\\:")
        safe_sub = subtitle.replace("'", "\\'").replace(":", "\\:")

        fade_in_end = 1.0
        fade_out_start = max(duration - 1.0, fade_in_end + 0.5)

        # Alpha expression: fade in then fade out
        alpha_expr = (
            f"if(lt(t,{fade_in_end}),t/{fade_in_end},"
            f"if(lt(t,{fade_out_start}),1,"
            f"({duration}-t)/({duration}-{fade_out_start})))"
        )

        title_size = max(48, height // 18)
        sub_size = max(28, height // 32)
        title_y = f"(h-text_h)/2-{title_size}"
        sub_y = f"(h+text_h)/2+{sub_size // 2}"

        drawtext_title = (
            f"text='{safe_title}':fontcolor=white:fontsize={title_size}:"
            f"x=(w-text_w)/2:y={title_y}:alpha='{alpha_expr}'"
        )
        drawtext_sub = (
            f"text='{safe_sub}':fontcolor=white@0.75:fontsize={sub_size}:"
            f"x=(w-text_w)/2:y={sub_y}:alpha='{alpha_expr}'"
        )

        black_video = (
            ffmpeg
            .input(f"color=c=black:s={width}x{height}:d={duration}", format="lavfi")
            .video
            .filter("drawtext", **self._parse_drawtext(drawtext_title))
            .filter("drawtext", **self._parse_drawtext(drawtext_sub))
        )
        silence = ffmpeg.input(f"anullsrc=r=44100:cl=stereo:d={duration}", format="lavfi").audio

        return (black_video, silence)

    async def _build_end_card(
        self,
        title: str,
        duration: int,
        width: int,
        height: int,
    ) -> tuple[Any, Any]:
        """Simple 'FIN' end card on black background."""
        import ffmpeg

        safe_title = title.replace("'", "\\'").replace(":", "\\:")
        font_size = max(36, height // 22)
        alpha_expr = f"if(lt(t,1),t,if(lt(t,{duration-1}),1,({duration}-t)))"

        drawtext_fin = (
            f"text='FIN':fontcolor=white:fontsize={font_size * 2}:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-{font_size}:alpha='{alpha_expr}'"
        )
        drawtext_title = (
            f"text='{safe_title}':fontcolor=white@0.6:fontsize={font_size}:"
            f"x=(w-text_w)/2:y=(h+text_h)/2+{font_size // 2}:alpha='{alpha_expr}'"
        )

        black_video = (
            ffmpeg
            .input(f"color=c=black:s={width}x{height}:d={duration}", format="lavfi")
            .video
            .filter("drawtext", **self._parse_drawtext(drawtext_fin))
            .filter("drawtext", **self._parse_drawtext(drawtext_title))
        )
        silence = ffmpeg.input(f"anullsrc=r=44100:cl=stereo:d={duration}", format="lavfi").audio

        return (black_video, silence)

    def _parse_drawtext(self, drawtext_str: str) -> Dict[str, Any]:
        """
        Convert a drawtext filter string into kwargs dict for ffmpeg-python.
        Handles simple key=value pairs (not nested quotes).
        """
        # ffmpeg-python accepts the whole string as the first positional arg
        # but it's cleaner to pass as a single string via **{"drawtext": ...}
        # We'll just return the raw string as the filter argument.
        return {"drawtext": drawtext_str}

    async def embed_metadata(
        self,
        video_path: Path,
        title: str,
        filmmaker: str,
        year: str,
    ) -> None:
        """
        Embed MP4/MOV metadata using FFmpeg -metadata flags.
        Operates on a temp copy then replaces the original.
        """
        import ffmpeg

        tmp = video_path.with_suffix(".meta_tmp" + video_path.suffix)
        try:
            (
                ffmpeg
                .input(str(video_path))
                .output(
                    str(tmp),
                    codec="copy",
                    **{
                        "metadata:g:0": f"title={title}",
                        "metadata:g:1": f"artist={filmmaker}",
                        "metadata:g:2": f"date={year}",
                        "metadata:g:3": f"comment=Exported from Film Studio",
                    },
                    movflags="+faststart",
                )
                .overwrite_output()
                .run(quiet=True)
            )
            tmp.replace(video_path)
        except Exception as exc:
            logger.warning("METADATA_EMBED_FAILED | %s | %s", video_path, exc)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_stitched_source(self, project_id: str) -> Optional[Path]:
        """Look for the stitched MP4 produced by FFmpegStitchingService."""
        candidate = self._stitched_base / f"{project_id}_final.mp4"
        if candidate.exists():
            return candidate
        # Also check stitching service job record
        try:
            from app.services.ffmpeg_stitching_service import ffmpeg_stitching_service
            job = ffmpeg_stitching_service.get_job(project_id)
            if job and job.get("output_path"):
                p = Path(job["output_path"])
                if p.exists():
                    return p
        except Exception:
            pass
        return None

    def _resolve_metadata(
        self,
        project_id: str,
        options: ExportOptions,
    ) -> tuple[str, str]:
        """Return (film_title, filmmaker_name) from project store."""
        title = "Untitled Film"
        filmmaker = options.filmmaker_name or "The Filmmaker"
        try:
            from app.services.project_store import project_store
            project = project_store.get_project(project_id)
            if isinstance(project, dict):
                t = str(project.get("title") or "").strip()
                if t:
                    title = t
                # filmmaker_name is a custom field some projects may have
                fn = str(project.get("filmmaker_name") or "").strip()
                if fn and not options.filmmaker_name:
                    filmmaker = fn
        except Exception as exc:
            logger.debug("Could not resolve project metadata: %s", exc)
        return title, filmmaker

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    async def _run_mock_export(
        self,
        project_id: str,
        job_id: str,
        options: ExportOptions,
    ) -> None:
        """Simulate export progress without FFmpeg."""
        steps = [
            (10, "Locating stitched source…"),
            (25, "Generating title card (mock)…"),
            (50, "Encoding film (mock)…"),
            (75, "Embedding metadata (mock)…"),
            (90, "Finalising package…"),
        ]
        for progress, msg in steps:
            self._set_job(project_id, status="running", progress=progress, advisory=msg)
            await asyncio.sleep(0.4)

        ext = options.format.lower()
        out_dir = self._output_base / project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        mock_path = out_dir / f"{job_id}.{ext}"
        mock_path.write_bytes(b"MOCK_EXPORT_FILE")

        output_url = f"/outputs/exports/{project_id}/{job_id}.{ext}"
        self._set_job(
            project_id,
            status="complete",
            progress=100,
            output_path=str(mock_path),
            output_url=output_url,
            finished_at=time.time(),
            advisory=(
                "Mock export complete — install FFmpeg for real encoding. "
                "Your film package is ready."
            ),
        )
        logger.info("EXPORT_MOCK_COMPLETE | project=%s", project_id)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

final_export_service = FinalExportService()
