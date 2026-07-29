from __future__ import annotations

import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageStat

from app.models import VideoKeyframe
from app.services.video_asset_service import VideoAssetService


VALID_EXTRACTION_REASONS = {"interval", "shot_boundary", "manual", "representative"}


class KeyframeExtractionService:
    def __init__(self, storage=None, video_asset_service: Optional[VideoAssetService] = None):
        self._storage = storage
        self._video_asset_service = video_asset_service
        self._outputs_root = Path(__file__).resolve().parents[2] / "outputs"
        self._keyframes_root = self._outputs_root / "keyframes"
        self._fallback_keyframes: Dict[str, VideoKeyframe] = {}

    def _storage_supports(self, method_name: str) -> bool:
        return bool(self._storage) and hasattr(self._storage, method_name)

    def _save_keyframe(self, keyframe: VideoKeyframe) -> VideoKeyframe:
        if self._storage_supports("save_video_keyframe"):
            return self._storage.save_video_keyframe(keyframe)
        self._fallback_keyframes[keyframe.keyframe_id] = keyframe
        return keyframe

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_keyframe_id(self) -> str:
        return f"keyframe-{uuid.uuid4().hex[:12]}"

    def _resolve_asset_file_path(self, asset) -> Optional[Path]:
        if asset.local_path:
            local = Path(asset.local_path).expanduser()
            if local.exists() and local.is_file():
                return local
        if asset.source_url and asset.source_url.startswith("/outputs/"):
            candidate = self._outputs_root / asset.source_url.removeprefix("/outputs/")
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def validate_frame_exists(self, frame_path: str) -> bool:
        return Path(frame_path).expanduser().exists()

    def build_frame_url(self, *, asset_id: str, filename: str) -> str:
        return f"/outputs/keyframes/{asset_id}/{filename}"

    def get_keyframe(self, keyframe_id: str) -> Optional[VideoKeyframe]:
        if not self._storage:
            return self._fallback_keyframes.get(keyframe_id)
        if self._storage_supports("get_video_keyframe"):
            return self._storage.get_video_keyframe(keyframe_id)
        return self._fallback_keyframes.get(keyframe_id)

    def list_keyframes_for_asset(self, asset_id: str) -> List[VideoKeyframe]:
        if not self._storage:
            return [row for row in self._fallback_keyframes.values() if row.asset_id == asset_id]
        if self._storage_supports("list_video_keyframes_for_asset"):
            return self._storage.list_video_keyframes_for_asset(asset_id)
        return [row for row in self._fallback_keyframes.values() if row.asset_id == asset_id]

    def list_keyframes_for_project(self, project_id: str) -> List[VideoKeyframe]:
        if not self._storage:
            return [row for row in self._fallback_keyframes.values() if row.project_id == project_id]
        if hasattr(self._storage, "list_video_keyframes_for_project"):
            return self._storage.list_video_keyframes_for_project(project_id)
        return [row for row in self._fallback_keyframes.values() if row.project_id == project_id]

    def delete_keyframes_for_asset(self, asset_id: str) -> int:
        removed = 0
        asset_dir = self._keyframes_root / asset_id
        if asset_dir.exists() and asset_dir.is_dir():
            shutil.rmtree(asset_dir)
        fallback_keys = [k for k, row in self._fallback_keyframes.items() if row.asset_id == asset_id]
        for key in fallback_keys:
            self._fallback_keyframes.pop(key, None)
            removed += 1
        if self._storage_supports("delete_video_keyframes_for_asset"):
            return self._storage.delete_video_keyframes_for_asset(asset_id)
        return removed

    async def analyze_keyframe_variance(
        self,
        *,
        frame_paths: List[str],
        shot_id: str,
    ) -> Dict[str, Any]:
        """Measure normalized visual change between consecutive extracted frames."""
        paths = [Path(path).expanduser() for path in frame_paths]
        missing = [str(path) for path in paths if not path.exists() or not path.is_file()]
        if missing:
            raise ValueError(f"Keyframe files are not accessible: {missing}")

        frame_details: List[Dict[str, Any]] = []
        variances: List[float] = []
        previous: Image.Image | None = None

        for index, path in enumerate(paths):
            with Image.open(path) as source:
                current = source.convert("RGB")
                if previous is not None:
                    if current.size != previous.size:
                        current = current.resize(previous.size)
                    difference = ImageChops.difference(previous, current)
                    channel_means = ImageStat.Stat(difference).mean
                    variance = round(sum(channel_means) / (len(channel_means) * 255.0), 6)
                    variances.append(variance)
                    frame_details.append(
                        {
                            "from_frame": index - 1,
                            "to_frame": index,
                            "variance": variance,
                        }
                    )
                previous = current.copy()

        average = round(sum(variances) / len(variances), 6) if variances else 0.0
        maximum = max(variances, default=0.0)
        rating = "stable" if average < 0.08 else "moderate" if average < 0.2 else "high_change"
        return {
            "shot_id": shot_id,
            "frames_analyzed": len(paths),
            "avg_variance": average,
            "max_variance": maximum,
            "stability_rating": rating,
            "frame_details": frame_details,
        }

    def _assert_ready_for_extraction(self, asset_id: str):
        if not self._video_asset_service:
            raise ValueError("Video asset service is not configured")
        if shutil.which("ffmpeg") is None:
            raise ValueError("FFmpeg is not installed or not available in PATH")

        asset = self._video_asset_service.get_asset(asset_id)
        if asset is None:
            raise ValueError("Video asset not found")

        input_path = self._resolve_asset_file_path(asset)
        if input_path is None:
            raise ValueError("Video asset is not accessible for keyframe extraction")

        try:
            asset_dir = self._keyframes_root / asset.asset_id
            asset_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise ValueError(f"Unable to create keyframe output directory: {exc}") from exc

        return asset, input_path, asset_dir

    def _probe_video(self, input_path: Path) -> Tuple[float, Optional[int], Optional[int]]:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=0",
            str(input_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown ffprobe error"
            raise ValueError(f"FFmpeg probe failed: {message}")
        duration = 0.0
        width: Optional[int] = None
        height: Optional[int] = None
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key == "duration":
                try:
                    duration = max(float(value), 0.0)
                except ValueError:
                    duration = 0.0
            elif key == "width":
                try:
                    width = int(value)
                except ValueError:
                    width = None
            elif key == "height":
                try:
                    height = int(value)
                except ValueError:
                    height = None
        return duration, width, height

    def _extract_frame_at_timestamp(self, *, input_path: Path, output_file: Path, timestamp_seconds: float) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-strict",
            "unofficial",
            "-ss",
            f"{max(timestamp_seconds, 0.0):.3f}",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-pix_fmt",
            "yuvj420p",
            str(output_file),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown ffmpeg error"
            raise ValueError(f"FFmpeg keyframe extraction failed: {message}")

    @staticmethod
    def _build_timestamps(*, duration_seconds: float, interval_seconds: int, max_frames: int) -> List[float]:
        if duration_seconds <= 0.0:
            return [0.0]
        # Avoid sampling the exact trailing boundary; some inputs report duration
        # slightly beyond the last decodable frame timestamp.
        end_ts = max(duration_seconds - 0.25, 0.0)
        timestamps = [0.0, duration_seconds / 2.0, end_ts]
        # Optional interval frames for longer videos.
        if duration_seconds > (interval_seconds * 3):
            t = float(interval_seconds)
            while t < end_ts and len(timestamps) < max_frames:
                timestamps.append(t)
                t += float(interval_seconds)
        deduped = sorted({round(max(ts, 0.0), 3) for ts in timestamps})
        return deduped[:max_frames]

    def extract_keyframes_from_video(
        self,
        *,
        input_path: Path,
        output_dir: Path,
        asset_id: str,
        project_id: str,
        source_type: str,
        interval_seconds: int,
        max_frames: int,
        extraction_method: str,
    ) -> List[VideoKeyframe]:
        for existing in output_dir.glob("frame_*.jpg"):
            existing.unlink(missing_ok=True)
        duration, width, height = self._probe_video(input_path)
        timestamps = self._build_timestamps(
            duration_seconds=duration,
            interval_seconds=interval_seconds,
            max_frames=max_frames,
        )
        now = self._now_iso()
        keyframes: List[VideoKeyframe] = []
        for index, ts in enumerate(timestamps):
            filename = f"frame_{index:04d}.jpg"
            output_file = output_dir / filename
            self._extract_frame_at_timestamp(input_path=input_path, output_file=output_file, timestamp_seconds=ts)
            keyframe = VideoKeyframe(
                keyframe_id=self._generate_keyframe_id(),
                asset_id=asset_id,
                project_id=project_id,
                source_type=source_type,
                timestamp_seconds=ts,
                frame_index=index,
                image_path=str(output_file),
                image_url=self.build_frame_url(asset_id=asset_id, filename=filename),
                width=width,
                height=height,
                extraction_method=extraction_method,
                frame_path=str(output_file),
                frame_url=self.build_frame_url(asset_id=asset_id, filename=filename),
                extraction_reason=extraction_method,
                created_at=now,
                metadata={
                    "duration_seconds": duration,
                    "interval_seconds": interval_seconds,
                    "max_frames": max_frames,
                },
            )
            keyframes.append(self._save_keyframe(keyframe))
        return keyframes

    def extract_keyframes_for_asset(
        self,
        *,
        asset_id: str,
        interval_seconds: int = 5,
        max_frames: int = 20,
        overwrite: bool = False,
        extraction_method: str = "representative",
    ) -> List[VideoKeyframe]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if max_frames <= 0:
            raise ValueError("max_frames must be > 0")
        if extraction_method not in VALID_EXTRACTION_REASONS:
            raise ValueError(f"Invalid extraction_method: {extraction_method}")
        existing = self.list_keyframes_for_asset(asset_id)
        if existing and not overwrite:
            return existing
        asset, input_path, output_dir = self._assert_ready_for_extraction(asset_id)
        if overwrite:
            self.delete_keyframes_for_asset(asset_id)
            output_dir.mkdir(parents=True, exist_ok=True)
        return self.extract_keyframes_from_video(
            input_path=input_path,
            output_dir=output_dir,
            asset_id=asset.asset_id,
            project_id=asset.project_id,
            source_type=asset.source_type,
            interval_seconds=interval_seconds,
            max_frames=max_frames,
            extraction_method=extraction_method,
        )

    def extract_keyframes_interval(
        self,
        *,
        asset_id: str,
        interval_seconds: int = 5,
        max_frames: int = 20,
        overwrite: bool = False,
        extraction_reason: str = "interval",
    ) -> List[VideoKeyframe]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if max_frames <= 0:
            raise ValueError("max_frames must be > 0")
        if extraction_reason not in VALID_EXTRACTION_REASONS:
            raise ValueError(f"Invalid extraction_reason: {extraction_reason}")

        return self.extract_keyframes_for_asset(
            asset_id=asset_id,
            interval_seconds=interval_seconds,
            max_frames=max_frames,
            overwrite=overwrite,
            extraction_method=extraction_reason,
        )

    def extract_keyframes_representative(
        self,
        *,
        asset_id: str,
        interval_seconds: int = 5,
        max_frames: int = 20,
        overwrite: bool = False,
    ) -> List[VideoKeyframe]:
        return self.extract_keyframes_interval(
            asset_id=asset_id,
            interval_seconds=interval_seconds,
            max_frames=max_frames,
            overwrite=overwrite,
            extraction_reason="representative",
        )


# Alias required by v1.0 naming while preserving existing imports.
VideoKeyframeService = KeyframeExtractionService


keyframe_extraction_service = KeyframeExtractionService()
