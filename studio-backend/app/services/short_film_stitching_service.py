from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from app.models import SoundtrackConfig


@dataclass
class TitleCardConfig:
    enabled: bool = False
    title_text: str = ""
    subtitle_text: str = ""
    duration_seconds: int = 3
    style: str = "cinematic"
    background_color: str = "black"
    text_color: str = "white"


@dataclass
class EndCardConfig:
    enabled: bool = False
    text: str = "THE END"
    duration_seconds: int = 3
    style: str = "cinematic"


class ShortFilmStitchingService:
    def __init__(self, outputs_root: Path | None = None):
        backend_root = Path(__file__).resolve().parents[2]
        self.outputs_root = outputs_root or (backend_root / "outputs")

    @staticmethod
    def _string(value: Any) -> str:
        return value if isinstance(value, str) else ""

    @staticmethod
    def _list(value: Any) -> List[Any]:
        return value if isinstance(value, list) else []

    def collect_completed_project_outputs(self, project: Dict[str, Any]) -> List[Dict[str, str]]:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        render_rows = self._list(summary.get("one_button_render_jobs"))
        if not render_rows:
            return []

        scenes = self._list(summary.get("scenes"))
        scene_rank = {
            self._string(row.get("scene_id")): index
            for index, row in enumerate(scenes)
            if isinstance(row, dict) and self._string(row.get("scene_id"))
        }

        clips: List[Dict[str, str]] = []
        for row in render_rows:
            if not isinstance(row, dict):
                continue
            status = self._string(row.get("status")).strip().lower()
            if status != "complete":
                continue
            output_url = self._string(row.get("output_url")).strip()
            if not output_url:
                continue
            clips.append(
                {
                    "scene_id": self._string(row.get("scene_id")).strip(),
                    "shot_id": self._string(row.get("shot_id")).strip(),
                    "job_id": self._string(row.get("job_id")).strip(),
                    "output_url": output_url,
                }
            )

        def _rank(item: Dict[str, str]) -> Tuple[int, str]:
            scene_id = item.get("scene_id", "")
            return (scene_rank.get(scene_id, 9999), item.get("shot_id", ""))

        return sorted(clips, key=_rank)

    def collect_completed_scene_outputs(self, project: Dict[str, Any], scene_id: str) -> List[Dict[str, str]]:
        """Collect completed rendered shot outputs for one scene in shot order."""
        clean_scene_id = self._string(scene_id).strip()
        if not clean_scene_id:
            return []
        return [
            clip
            for clip in self.collect_completed_project_outputs(project)
            if self._string(clip.get("scene_id")).strip() == clean_scene_id
        ]

    def download_or_stream_clips_safely(self, clips: List[Dict[str, str]], work_dir: Path) -> List[Path]:
        ssl_context = self._build_ssl_context()
        files: List[Path] = []
        for index, clip in enumerate(clips, start=1):
            url = self._string(clip.get("output_url")).strip()
            if not url:
                continue
            target = work_dir / f"clip_{index:03d}.mp4"
            if self._is_simulated_asset_url(url):
                self.generate_simulated_video_clip(target, index)
                files.append(target)
                continue
            local_path = self._resolve_local_output_path(url)
            if local_path is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(local_path, target)
                files.append(target)
                continue
            with urllib.request.urlopen(url, timeout=60, context=ssl_context) as response:
                target.write_bytes(response.read())
            files.append(target)
        return files

    @staticmethod
    def _is_simulated_asset_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == "storage.example.com" and parsed.path.startswith("/assets/")

    def _resolve_local_output_path(self, url_or_path: str) -> Path | None:
        value = self._string(url_or_path).strip()
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme != "file":
            return None
        if parsed.scheme == "file":
            candidate = Path(parsed.path)
            return candidate if candidate.exists() else None
        if value.startswith("/outputs/"):
            candidate = self.outputs_root.parent / value.lstrip("/")
            return candidate if candidate.exists() else None
        if value.startswith("outputs/"):
            candidate = self.outputs_root.parent / value
            return candidate if candidate.exists() else None
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate if candidate.exists() else None
        return None

    def generate_simulated_video_clip(self, target: Path, index: int) -> Path:
        ffmpeg_bin = shutil_which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg_missing")
        target.parent.mkdir(parents=True, exist_ok=True)
        hue = (index * 47) % 360
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=1280x720:d=2,format=yuv420p,hue=h={hue}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(target),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "simulated_clip_generation_failed").strip()[:500])
        return target

    def _build_ssl_context(self) -> ssl.SSLContext:
        app_env = (os.getenv("APP_ENV") or "").strip().lower()
        insecure_requested = (os.getenv("RUNWAY_ALLOW_INSECURE_SSL") or "").strip().lower() == "true"
        if insecure_requested and app_env in {"local", "test"}:
            return ssl._create_unverified_context()

        bundle = (
            (os.getenv("RUNWAY_CA_BUNDLE") or "").strip()
            or (os.getenv("REQUESTS_CA_BUNDLE") or "").strip()
        )
        if bundle:
            return ssl.create_default_context(cafile=bundle)
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    def build_ffmpeg_concat_list(self, clip_paths: List[Path], work_dir: Path) -> Path:
        concat_path = work_dir / "concat_list.txt"
        lines: List[str] = []
        for path in clip_paths:
            escaped = path.as_posix().replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return concat_path

    @staticmethod
    def _normalize_duration_seconds(value: Any, default_value: int = 3) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = default_value
        return max(1, min(parsed, 12))

    @staticmethod
    def _escape_drawtext(value: str) -> str:
        return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    def generate_title_card_frame(self, work_dir: Path, config: TitleCardConfig) -> Path:
        ffmpeg_bin = shutil_which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg_missing")
        out_path = work_dir / "title_card.mp4"
        image_path = work_dir / "title_card.png"
        duration = self._normalize_duration_seconds(config.duration_seconds, 3)
        self._render_card_image(
            image_path=image_path,
            title=config.title_text.strip() or "Untitled",
            subtitle=config.subtitle_text.strip(),
            background_color=config.background_color,
            text_color=config.text_color,
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "title_card_generation_failed").strip()[:500])
        return out_path

    def generate_end_card_frame(self, work_dir: Path, config: EndCardConfig) -> Path:
        ffmpeg_bin = shutil_which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg_missing")
        out_path = work_dir / "end_card.mp4"
        image_path = work_dir / "end_card.png"
        duration = self._normalize_duration_seconds(config.duration_seconds, 3)
        self._render_card_image(
            image_path=image_path,
            title=config.text.strip() or "THE END",
            subtitle="",
            background_color="black",
            text_color="white",
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "end_card_generation_failed").strip()[:500])
        return out_path

    def _render_card_image(
        self,
        image_path: Path,
        title: str,
        subtitle: str,
        background_color: str,
        text_color: str,
    ) -> None:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception as exc:
            raise RuntimeError(f"card_image_dependency_missing: {exc}")

        image = Image.new("RGB", (1280, 720), color=background_color or "black")
        draw = ImageDraw.Draw(image)
        try:
            title_font = ImageFont.truetype("DejaVuSans.ttf", 64)
            subtitle_font = ImageFont.truetype("DejaVuSans.ttf", 34)
        except Exception:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        title_x = (1280 - title_w) // 2
        title_y = (720 // 2) - title_h - (18 if subtitle else 0)
        draw.text((title_x, title_y), title, fill=text_color or "white", font=title_font)

        if subtitle:
            sub_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
            sub_w = sub_bbox[2] - sub_bbox[0]
            sub_x = (1280 - sub_w) // 2
            sub_y = title_y + title_h + 24
            draw.text((sub_x, sub_y), subtitle, fill=text_color or "white", font=subtitle_font)

        image.save(image_path, format="PNG")

    def stitch_clips(self, concat_list_path: Path, output_path: Path, transcode: bool = False) -> Dict[str, Any]:
        ffmpeg_bin = shutil_which("ffmpeg")
        if not ffmpeg_bin:
            return {"status": "blocked", "blocker": "ffmpeg_missing"}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd: List[str] = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
        ]
        if transcode:
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"])
        else:
            cmd.extend(["-c", "copy"])
        cmd.append(str(output_path))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return {
                "status": "failed",
                "blocker": "stitch_failed",
                "error_message": (proc.stderr or proc.stdout or "ffmpeg failed").strip()[:500],
            }
        return {"status": "completed"}

    def validate_output_file(self, output_path: Path) -> Dict[str, Any]:
        if not output_path.exists():
            return {"valid": False, "blocker": "output_missing"}
        if output_path.stat().st_size <= 0:
            return {"valid": False, "blocker": "output_empty"}
        return {"valid": True, "size_bytes": output_path.stat().st_size}

    def _probe_duration_seconds(self, output_path: Path) -> float | None:
        ffprobe_bin = shutil_which("ffprobe")
        if not ffprobe_bin:
            return None
        cmd = [
            ffprobe_bin,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        try:
            payload = json.loads(proc.stdout or "{}")
            duration = float((payload.get("format") or {}).get("duration") or 0.0)
            return duration if duration > 0 else None
        except Exception:
            return None

    def _probe_has_audio_stream(self, output_path: Path) -> bool:
        ffprobe_bin = shutil_which("ffprobe")
        if not ffprobe_bin:
            return False
        cmd = [
            ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
        return bool((proc.stdout or "").strip())

    @staticmethod
    def _normalize_volume(value: Any, default_value: float = 0.25) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = default_value
        return max(0.0, min(parsed, 1.0))

    @staticmethod
    def _normalize_fade_seconds(value: Any, default_value: float = 1.0) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = default_value
        return max(0.0, min(parsed, 30.0))

    def create_placeholder_audio(self, work_dir: Path, duration_seconds: float) -> Path:
        ffmpeg_bin = shutil_which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg_missing")
        target = work_dir / "placeholder_ambient.wav"
        duration = max(1.0, float(duration_seconds or 1.0))
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=180:sample_rate=44100:duration={duration}",
            "-filter:a",
            "volume=0.06",
            str(target),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "placeholder_audio_failed").strip()[:500])
        return target

    def validate_audio_source(
        self,
        work_dir: Path,
        soundtrack_config: SoundtrackConfig,
        video_duration_seconds: float,
    ) -> tuple[Path | None, str | None]:
        source_type = (soundtrack_config.audio_source_type or "none").strip().lower()
        if source_type in {"", "none"}:
            return None, "audio_source_none"
        if source_type == "generated_placeholder":
            try:
                return self.create_placeholder_audio(work_dir, max(1.0, video_duration_seconds)), None
            except Exception as exc:
                if "ffmpeg_missing" in str(exc):
                    return None, "ffmpeg_missing"
                return None, "placeholder_audio_failed"
        if source_type == "local_file":
            local_path = (soundtrack_config.local_audio_path or "").strip()
            if local_path:
                candidate = Path(local_path)
                if candidate.exists() and candidate.is_file():
                    return candidate, None
                return None, "local_audio_missing"
            audio_url = (soundtrack_config.audio_url or "").strip()
            if audio_url:
                try:
                    target = work_dir / "external_audio_track"
                    with urllib.request.urlopen(audio_url, timeout=60, context=self._build_ssl_context()) as response:
                        target.write_bytes(response.read())
                    return target, None
                except Exception:
                    return None, "audio_url_unreachable"
            return None, "missing_audio_source"
        return None, "unsupported_audio_source_type"

    def mix_audio_into_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        soundtrack_config: SoundtrackConfig,
        video_duration_seconds: float,
    ) -> Dict[str, Any]:
        ffmpeg_bin = shutil_which("ffmpeg")
        if not ffmpeg_bin:
            return {"status": "failed", "blocker": "ffmpeg_missing"}
        output_path.parent.mkdir(parents=True, exist_ok=True)

        volume = self._normalize_volume(soundtrack_config.volume, 0.25)
        fade_in = self._normalize_fade_seconds(soundtrack_config.fade_in_seconds, 1.0)
        fade_out = self._normalize_fade_seconds(soundtrack_config.fade_out_seconds, 1.0)
        fade_out_start = max(0.0, float(video_duration_seconds or 0.0) - fade_out)
        afilter = f"volume={volume},afade=t=in:st=0:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}"

        cmd: List[str] = [ffmpeg_bin, "-y", "-i", str(video_path)]
        if soundtrack_config.loop_to_duration:
            cmd.extend(["-stream_loop", "-1"])
        has_existing_audio = self._probe_has_audio_stream(video_path)
        if has_existing_audio:
            filter_complex = (
                f"[1:a]{afilter}[bgm];"
                "[0:a:0][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )
            audio_map = "[aout]"
        else:
            filter_complex = f"[1:a]{afilter}[bgm]"
            audio_map = "[bgm]"
        cmd.extend(
            [
                "-i",
                str(audio_path),
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v:0",
                "-map",
                audio_map,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        )
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return {
                "status": "failed",
                "blocker": "audio_mix_failed",
                "error_message": (proc.stderr or proc.stdout or "audio mix failed").strip()[:500],
            }
        return {"status": "completed", "command": cmd}

    def validate_final_audio_video_output(self, output_path: Path) -> Dict[str, Any]:
        file_valid = self.validate_output_file(output_path)
        if not file_valid.get("valid"):
            return {"valid": False, "blocker": self._string(file_valid.get("blocker")) or "output_invalid"}
        if not self._probe_has_audio_stream(output_path):
            return {"valid": False, "blocker": "missing_audio_stream"}
        return {"valid": True}

    def build_stitch_result_payload(
        self,
        project_id: str,
        clip_count: int,
        output_path: Path,
        status: str,
        blocker: str | None = None,
        error_message: str | None = None,
    ) -> Dict[str, Any]:
        relative_path = output_path.relative_to(self.outputs_root).as_posix()
        payload: Dict[str, Any] = {
            "project_id": project_id,
            "clip_count": clip_count,
            "output_path": str(output_path),
            "output_url": f"/outputs/{relative_path}",
            "status": status,
        }
        duration = self._probe_duration_seconds(output_path) if status == "completed" and output_path.exists() else None
        if duration is not None:
            payload["duration_seconds"] = round(duration, 3)
        if blocker:
            payload["blocker"] = blocker
        if error_message:
            payload["error_message"] = error_message
        return payload

    def stitch_project(self, project_id: str, project: Dict[str, Any], overwrite: bool = False) -> Dict[str, Any]:
        return self.stitch_project_with_cards(
            project_id=project_id,
            project=project,
            overwrite=overwrite,
            title_card_config=TitleCardConfig(),
            end_card_config=EndCardConfig(),
            soundtrack_config=SoundtrackConfig(),
        )

    def stitch_scene(
        self,
        project_id: str,
        scene_id: str,
        project: Dict[str, Any],
        overwrite: bool = False,
        soundtrack_config: SoundtrackConfig | None = None,
    ) -> Dict[str, Any]:
        clean_scene_id = self._string(scene_id).strip()
        output_path = self.outputs_root / "scene_assemblies" / f"{project_id}_{clean_scene_id}.mp4"
        soundtrack_path = self.outputs_root / "scene_assemblies" / f"{project_id}_{clean_scene_id}_with_audio.mp4"
        clips = self.collect_completed_scene_outputs(project, clean_scene_id)
        if not clips:
            payload = self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=0,
                output_path=output_path,
                status="failed",
                blocker="no_completed_scene_outputs",
            )
            payload["scene_id"] = clean_scene_id
            return payload

        if output_path.exists() and not overwrite:
            existing_path = soundtrack_path if soundtrack_config and soundtrack_config.enabled and soundtrack_path.exists() else output_path
            payload = self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=len(clips),
                output_path=existing_path,
                status="existing",
            )
            payload["scene_id"] = clean_scene_id
            payload["shot_ids"] = [clip["shot_id"] for clip in clips]
            return payload

        with tempfile.TemporaryDirectory(prefix=f"stitch_{project_id}_{clean_scene_id}_") as temp_dir:
            work_dir = Path(temp_dir)
            try:
                clip_paths = self.download_or_stream_clips_safely(clips, work_dir)
            except Exception as exc:
                payload = self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(clips),
                    output_path=output_path,
                    status="failed",
                    blocker="clip_download_failed",
                    error_message=str(exc),
                )
                payload["scene_id"] = clean_scene_id
                return payload

            concat_list = self.build_ffmpeg_concat_list(clip_paths, work_dir)
            stitch_result = self.stitch_clips(concat_list, output_path, transcode=False)
            if stitch_result.get("status") != "completed":
                payload = self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(clips),
                    output_path=output_path,
                    status="failed",
                    blocker=self._string(stitch_result.get("blocker")) or "stitch_failed",
                    error_message=self._string(stitch_result.get("error_message")) or None,
                )
                payload["scene_id"] = clean_scene_id
                return payload

        validation = self.validate_output_file(output_path)
        if not validation.get("valid"):
            payload = self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=len(clips),
                output_path=output_path,
                status="failed",
                blocker=self._string(validation.get("blocker")) or "output_invalid",
            )
            payload["scene_id"] = clean_scene_id
            return payload

        final_path = output_path
        if soundtrack_config and soundtrack_config.enabled:
            with tempfile.TemporaryDirectory(prefix=f"mix_{project_id}_{clean_scene_id}_") as temp_dir:
                work_dir = Path(temp_dir)
                video_duration = self._probe_duration_seconds(output_path) or 0.0
                source_audio, audio_blocker = self.validate_audio_source(
                    work_dir=work_dir,
                    soundtrack_config=soundtrack_config,
                    video_duration_seconds=video_duration,
                )
                if not source_audio:
                    payload = self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=soundtrack_path,
                        status="failed",
                        blocker=audio_blocker or "missing_audio_source",
                    )
                    payload["scene_id"] = clean_scene_id
                    return payload
                mix_result = self.mix_audio_into_video(
                    video_path=output_path,
                    audio_path=source_audio,
                    output_path=soundtrack_path,
                    soundtrack_config=soundtrack_config,
                    video_duration_seconds=video_duration,
                )
                if mix_result.get("status") != "completed":
                    payload = self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=soundtrack_path,
                        status="failed",
                        blocker=self._string(mix_result.get("blocker")) or "audio_mix_failed",
                        error_message=self._string(mix_result.get("error_message")) or None,
                    )
                    payload["scene_id"] = clean_scene_id
                    return payload
            final_validation = self.validate_final_audio_video_output(soundtrack_path)
            if not final_validation.get("valid"):
                payload = self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(clips),
                    output_path=soundtrack_path,
                    status="failed",
                    blocker=self._string(final_validation.get("blocker")) or "final_audio_validation_failed",
                )
                payload["scene_id"] = clean_scene_id
                return payload
            final_path = soundtrack_path

        payload = self.build_stitch_result_payload(
            project_id=project_id,
            clip_count=len(clips),
            output_path=final_path,
            status="completed",
        )
        payload["scene_id"] = clean_scene_id
        payload["shot_ids"] = [clip["shot_id"] for clip in clips]
        return payload

    def stitch_project_with_cards(
        self,
        project_id: str,
        project: Dict[str, Any],
        overwrite: bool = False,
        title_card_config: TitleCardConfig | None = None,
        end_card_config: EndCardConfig | None = None,
        soundtrack_config: SoundtrackConfig | None = None,
    ) -> Dict[str, Any]:
        output_path = self.outputs_root / "final_films" / f"{project_id}_sandbox_short.mp4"
        soundtrack_path = self.outputs_root / "final_films" / f"{project_id}_sandbox_short_with_audio.mp4"
        clips = self.collect_completed_project_outputs(project)
        if not clips:
            return self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=0,
                output_path=output_path,
                status="failed",
                blocker="no_completed_outputs",
            )

        if output_path.exists() and not overwrite:
            if soundtrack_config and soundtrack_config.enabled:
                if soundtrack_path.exists():
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=soundtrack_path,
                        status="existing",
                    )
            else:
                return self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(clips),
                    output_path=output_path,
                    status="existing",
                )

        if not output_path.exists() or overwrite:
            with tempfile.TemporaryDirectory(prefix=f"stitch_{project_id}_") as temp_dir:
                work_dir = Path(temp_dir)
                try:
                    clip_paths = self.download_or_stream_clips_safely(clips, work_dir)
                except Exception as exc:
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=output_path,
                        status="failed",
                        blocker="clip_download_failed",
                        error_message=str(exc),
                    )

                pre_roll: List[Path] = []
                post_roll: List[Path] = []
                try:
                    if title_card_config and title_card_config.enabled:
                        pre_roll.append(self.generate_title_card_frame(work_dir, title_card_config))
                    if end_card_config and end_card_config.enabled:
                        post_roll.append(self.generate_end_card_frame(work_dir, end_card_config))
                except Exception as exc:
                    blocker = "ffmpeg_missing" if "ffmpeg_missing" in str(exc) else "card_generation_failed"
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=output_path,
                        status="failed",
                        blocker=blocker,
                        error_message=str(exc),
                    )

                ordered_paths = pre_roll + clip_paths + post_roll
                concat_list = self.build_ffmpeg_concat_list(ordered_paths, work_dir)
                has_cards = bool(pre_roll or post_roll)
                stitch_result = self.stitch_clips(concat_list, output_path, transcode=has_cards)
                if stitch_result.get("status") != "completed":
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=output_path,
                        status="failed",
                        blocker=self._string(stitch_result.get("blocker")) or "stitch_failed",
                        error_message=self._string(stitch_result.get("error_message")) or None,
                    )

        validation = self.validate_output_file(output_path)
        if not validation.get("valid"):
            return self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=len(clips),
                output_path=output_path,
                status="failed",
                blocker=self._string(validation.get("blocker")) or "output_invalid",
            )

        if soundtrack_config and soundtrack_config.enabled:
            with tempfile.TemporaryDirectory(prefix=f"mix_{project_id}_") as temp_dir:
                work_dir = Path(temp_dir)
                source_audio, audio_blocker = self.validate_audio_source(
                    work_dir=work_dir,
                    soundtrack_config=soundtrack_config,
                    video_duration_seconds=self._probe_duration_seconds(output_path) or 0.0,
                )
                if not source_audio:
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=soundtrack_path,
                        status="failed",
                        blocker=audio_blocker or "missing_audio_source",
                    )
                video_duration = self._probe_duration_seconds(output_path) or 0.0
                mix_result = self.mix_audio_into_video(
                    video_path=output_path,
                    audio_path=source_audio,
                    output_path=soundtrack_path,
                    soundtrack_config=soundtrack_config,
                    video_duration_seconds=video_duration,
                )
                if mix_result.get("status") != "completed":
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(clips),
                        output_path=soundtrack_path,
                        status="failed",
                        blocker=self._string(mix_result.get("blocker")) or "audio_mix_failed",
                        error_message=self._string(mix_result.get("error_message")) or None,
                    )
            final_validation = self.validate_final_audio_video_output(soundtrack_path)
            if not final_validation.get("valid"):
                return self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(clips),
                    output_path=soundtrack_path,
                    status="failed",
                    blocker=self._string(final_validation.get("blocker")) or "final_audio_validation_failed",
                )
            return self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=len(clips),
                output_path=soundtrack_path,
                status="completed",
            )

        return self.build_stitch_result_payload(
            project_id=project_id,
            clip_count=len(clips),
            output_path=output_path,
            status="completed",
        )

    def stitch_project_with_revisions(
        self,
        project_id: str,
        project: Dict[str, Any],
        revision_overrides: Dict[str, str],  # original_job_id -> new_output_url
        overwrite: bool = False,
        title_card_config: TitleCardConfig | None = None,
        end_card_config: EndCardConfig | None = None,
        soundtrack_config: SoundtrackConfig | None = None,
    ) -> Dict[str, Any]:
        """Stitch a project with revision overrides for specific clips"""
        output_path = self.outputs_root / "final_films" / f"{project_id}_sandbox_short_revised.mp4"
        soundtrack_path = self.outputs_root / "final_films" / f"{project_id}_sandbox_short_revised_with_audio.mp4"
        
        # Get completed clips and apply revision overrides
        clips = self.collect_completed_project_outputs(project)
        if not clips:
            return self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=0,
                output_path=output_path,
                status="failed",
                blocker="no_completed_outputs",
            )

        # Apply revision overrides - replace original clip URLs with revised ones
        revised_clips = []
        for clip in clips:
            original_job_id = clip.get("job_id", "")
            if original_job_id in revision_overrides:
                # Use the revised clip
                revised_clip = clip.copy()
                revised_clip["output_url"] = revision_overrides[original_job_id]
                revised_clips.append(revised_clip)
            else:
                # Use the original clip
                revised_clips.append(clip)

        if output_path.exists() and not overwrite:
            if soundtrack_config and soundtrack_config.enabled:
                if soundtrack_path.exists():
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(revised_clips),
                        output_path=soundtrack_path,
                        status="existing",
                    )
            else:
                return self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(revised_clips),
                    output_path=output_path,
                    status="existing",
                )

        if not output_path.exists() or overwrite:
            with tempfile.TemporaryDirectory(prefix=f"stitch_rev_{project_id}_") as temp_dir:
                work_dir = Path(temp_dir)
                try:
                    clip_paths = self.download_or_stream_clips_safely(revised_clips, work_dir)
                except Exception as exc:
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(revised_clips),
                        output_path=output_path,
                        status="failed",
                        blocker="clip_download_failed",
                        error_message=str(exc),
                    )

                pre_roll: List[Path] = []
                post_roll: List[Path] = []
                try:
                    if title_card_config and title_card_config.enabled:
                        pre_roll.append(self.generate_title_card_frame(work_dir, title_card_config))
                    if end_card_config and end_card_config.enabled:
                        post_roll.append(self.generate_end_card_frame(work_dir, end_card_config))
                except Exception as exc:
                    blocker = "ffmpeg_missing" if "ffmpeg_missing" in str(exc) else "card_generation_failed"
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(revised_clips),
                        output_path=output_path,
                        status="failed",
                        blocker=blocker,
                        error_message=str(exc),
                    )

                ordered_paths = pre_roll + clip_paths + post_roll
                concat_list = self.build_ffmpeg_concat_list(ordered_paths, work_dir)
                has_cards = bool(pre_roll or post_roll)
                stitch_result = self.stitch_clips(concat_list, output_path, transcode=has_cards)
                if stitch_result.get("status") != "completed":
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(revised_clips),
                        output_path=output_path,
                        status="failed",
                        blocker=self._string(stitch_result.get("blocker")) or "stitch_failed",
                        error_message=self._string(stitch_result.get("error_message")) or None,
                    )

        validation = self.validate_output_file(output_path)
        if not validation.get("valid"):
            return self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=len(revised_clips),
                output_path=output_path,
                status="failed",
                blocker=self._string(validation.get("blocker")) or "output_invalid",
            )

        if soundtrack_config and soundtrack_config.enabled:
            with tempfile.TemporaryDirectory(prefix=f"mix_rev_{project_id}_") as temp_dir:
                work_dir = Path(temp_dir)
                source_audio, audio_blocker = self.validate_audio_source(
                    work_dir=work_dir,
                    soundtrack_config=soundtrack_config,
                    video_duration_seconds=self._probe_duration_seconds(output_path) or 0.0,
                )
                if not source_audio:
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(revised_clips),
                        output_path=soundtrack_path,
                        status="failed",
                        blocker=audio_blocker or "missing_audio_source",
                    )
                video_duration = self._probe_duration_seconds(output_path) or 0.0
                mix_result = self.mix_audio_into_video(
                    video_path=output_path,
                    audio_path=source_audio,
                    output_path=soundtrack_path,
                    soundtrack_config=soundtrack_config,
                    video_duration_seconds=video_duration,
                )
                if mix_result.get("status") != "completed":
                    return self.build_stitch_result_payload(
                        project_id=project_id,
                        clip_count=len(revised_clips),
                        output_path=soundtrack_path,
                        status="failed",
                        blocker=self._string(mix_result.get("blocker")) or "audio_mix_failed",
                        error_message=self._string(mix_result.get("error_message")) or None,
                    )
            final_validation = self.validate_final_audio_video_output(soundtrack_path)
            if not final_validation.get("valid"):
                return self.build_stitch_result_payload(
                    project_id=project_id,
                    clip_count=len(revised_clips),
                    output_path=soundtrack_path,
                    status="failed",
                    blocker=self._string(final_validation.get("blocker")) or "final_audio_validation_failed",
                )
            return self.build_stitch_result_payload(
                project_id=project_id,
                clip_count=len(revised_clips),
                output_path=soundtrack_path,
                status="completed",
            )

        return self.build_stitch_result_payload(
            project_id=project_id,
            clip_count=len(revised_clips),
            output_path=output_path,
            status="completed",
        )


def shutil_which(binary: str) -> str | None:
    from shutil import which

    return which(binary)


short_film_stitching_service = ShortFilmStitchingService()
