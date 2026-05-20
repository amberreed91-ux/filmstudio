from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from app.models import ShotBoundary, VideoKeyframe
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService


class ShotDetectionService:
    def __init__(
        self,
        storage=None,
        video_asset_service: Optional[VideoAssetService] = None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
    ):
        self._storage = storage
        self._video_asset_service = video_asset_service
        self._keyframe_service = keyframe_service
        self._outputs_root = Path(__file__).resolve().parents[2] / "outputs"

    def _generate_boundary_id(self) -> str:
        return f"boundary-{uuid.uuid4().hex[:12]}"

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

    def _assert_ready(self, asset_id: str) -> Tuple[object, Path]:
        if not self._video_asset_service:
            raise ValueError("Video asset service is not configured")
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise ValueError("FFmpeg/FFprobe are required for shot detection")

        asset = self._video_asset_service.get_asset(asset_id)
        if asset is None:
            raise ValueError("Video asset not found")

        input_path = self._resolve_asset_file_path(asset)
        if input_path is None:
            raise ValueError("Video asset is not accessible for shot detection")
        return asset, input_path

    def _probe_duration(self, input_path: Path) -> float:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError("Failed to probe video duration")
        try:
            return max(0.0, float((result.stdout or "0").strip()))
        except ValueError as exc:
            raise ValueError("Invalid video duration from ffprobe") from exc

    def _run_scene_detection(self, input_path: Path, threshold: float = 0.30) -> List[Tuple[float, float]]:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(input_path),
            "-filter:v",
            f"select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        output = (result.stderr or "") + "\n" + (result.stdout or "")

        cuts: List[Tuple[float, float]] = []
        for line in output.splitlines():
            if "showinfo" not in line or "pts_time:" not in line:
                continue
            try:
                pts_chunk = line.split("pts_time:", 1)[1]
                pts_text = pts_chunk.split(" ", 1)[0].strip()
                pts_time = float(pts_text)
                score = 0.5
                if "scene:" in line:
                    scene_text = line.split("scene:", 1)[1].split(" ", 1)[0].strip()
                    score = float(scene_text)
                cuts.append((pts_time, max(0.0, min(1.0, score))))
            except Exception:
                continue
        return cuts

    def _detect_fade_windows(self, input_path: Path) -> List[Tuple[float, float]]:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(input_path),
            "-vf",
            "blackdetect=d=0.05:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        output = (result.stderr or "") + "\n" + (result.stdout or "")

        windows: List[Tuple[float, float]] = []
        for line in output.splitlines():
            if "black_start:" not in line or "black_end:" not in line:
                continue
            try:
                start_text = line.split("black_start:", 1)[1].split(" ", 1)[0].strip()
                end_text = line.split("black_end:", 1)[1].split(" ", 1)[0].strip()
                windows.append((float(start_text), float(end_text)))
            except Exception:
                continue
        return windows

    def _infer_transition_type(self, boundary_time: float, confidence: float, fade_windows: List[Tuple[float, float]]) -> str:
        for start, end in fade_windows:
            if start - 0.2 <= boundary_time <= end + 0.2:
                return "fade"
        if confidence < 0.45:
            return "dissolve"
        return "hard_cut"

    def detect_shots(self, *, asset_id: str, threshold: float = 0.30, overwrite: bool = True) -> List[ShotBoundary]:
        if threshold <= 0 or threshold >= 1:
            raise ValueError("threshold must be between 0 and 1")
        if not self._storage:
            raise ValueError("Shot boundary storage is not configured")

        existing = self.list_shots(asset_id)
        if existing and not overwrite:
            return existing

        asset, input_path = self._assert_ready(asset_id)
        if overwrite:
            self._storage.delete_shot_boundaries_for_asset(asset_id)

        duration = self._probe_duration(input_path)
        cuts = self._run_scene_detection(input_path, threshold=threshold)
        fade_windows = self._detect_fade_windows(input_path)

        cut_times = sorted([time for time, _score in cuts if 0.0 < time < duration])
        cut_scores = {time: score for time, score in cuts}

        boundaries: List[ShotBoundary] = []
        start = 0.0
        for cut_time in cut_times + [duration]:
            if cut_time <= start:
                continue
            confidence = float(cut_scores.get(cut_time, 0.99 if cut_time == duration else 0.5))
            transition = self._infer_transition_type(cut_time, confidence, fade_windows)
            boundary = ShotBoundary(
                boundary_id=self._generate_boundary_id(),
                asset_id=asset.asset_id,
                start_time=round(start, 4),
                end_time=round(cut_time, 4),
                confidence=round(confidence, 4),
                transition_type=transition,
                metadata={"threshold": threshold, "duration": duration},
            )
            self._storage.save_shot_boundary(boundary)
            boundaries.append(boundary)
            start = cut_time

        return boundaries

    def list_shots(self, asset_id: str) -> List[ShotBoundary]:
        if not self._storage:
            return []
        return self._storage.list_shot_boundaries_for_asset(asset_id)

    def generate_representative_frames(self, *, asset_id: str, max_frames: int = 20) -> List[VideoKeyframe]:
        if not self._keyframe_service:
            raise ValueError("Keyframe extraction service is not configured")
        shots = self.list_shots(asset_id)
        if not shots:
            shots = self.detect_shots(asset_id=asset_id)

        # One representative frame per shot via keyframe pipeline; limited by max_frames.
        interval = 1
        if shots:
            avg_duration = sum(max(0.1, s.end_time - s.start_time) for s in shots) / len(shots)
            interval = max(1, int(round(avg_duration)))

        return self._keyframe_service.extract_keyframes_representative(
            asset_id=asset_id,
            interval_seconds=interval,
            max_frames=max_frames,
            overwrite=True,
        )


shot_detection_service = ShotDetectionService()
