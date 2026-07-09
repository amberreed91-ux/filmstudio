"""
Audio Generation Service — Coqui TTS + Stable Audio Open (diffusers)

Three tracks per scene:
  - dialogue: Coqui TTS (tts_models/en/ljspeech/tacotron2-DDC)
  - score:    Stable Audio Open (stabilityai/stable-audio-open-1.0)
  - ambient:  Stable Audio Open (stabilityai/stable-audio-open-1.0)

Models are lazy-loaded on first use. If libraries are not installed,
the service operates in mock mode and returns placeholder status.

Apple Silicon (M1/M2/M3) is supported via MPS backend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import struct
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import scipy.io.wavfile as wavfile

logger = logging.getLogger("audio-generation")

# ---------------------------------------------------------------------------
# Availability probes — checked once at import time
# ---------------------------------------------------------------------------

def _probe_tts() -> bool:
    try:
        import TTS  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_diffusers() -> bool:
    try:
        from diffusers import StableAudioPipeline  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


TTS_AVAILABLE = _probe_tts()
DIFFUSERS_AVAILABLE = _probe_diffusers()
TORCH_AVAILABLE = _probe_torch()
MOCK_MODE = not (TTS_AVAILABLE and DIFFUSERS_AVAILABLE and TORCH_AVAILABLE)

if MOCK_MODE:
    missing = []
    if not TORCH_AVAILABLE:
        missing.append("torch")
    if not TTS_AVAILABLE:
        missing.append("TTS")
    if not DIFFUSERS_AVAILABLE:
        missing.append("diffusers + StableAudioPipeline")
    logger.warning(
        "AudioGenerationService running in MOCK MODE — missing: %s. "
        "Install with: pip install torch torchaudio TTS diffusers scipy soundfile",
        ", ".join(missing),
    )
else:
    logger.info("AudioGenerationService: all libraries available — real generation enabled")


# ---------------------------------------------------------------------------
# Silence WAV helper
# ---------------------------------------------------------------------------

def _write_silence_wav(path: Path, duration_seconds: float = 1.0, sample_rate: int = 22050) -> None:
    """Write a minimal valid WAV file containing silence."""
    num_samples = int(sample_rate * duration_seconds)
    data_size = num_samples * 2  # 16-bit mono
    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))       # chunk size
        f.write(struct.pack("<H", 1))        # PCM
        f.write(struct.pack("<H", 1))        # mono
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * 2))  # byte rate
        f.write(struct.pack("<H", 2))        # block align
        f.write(struct.pack("<H", 16))       # bits per sample
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)


# ---------------------------------------------------------------------------
# Dialogue extraction
# ---------------------------------------------------------------------------

_DIALOGUE_PATTERNS = [
    re.compile(r'"([^"]{10,})"'),           # "quoted text"
    re.compile(r"'([^']{10,})'"),           # 'quoted text'
    re.compile(r"says[,:]?\s+(.+?)[\.\!\?]", re.IGNORECASE),
    re.compile(r"(?:whispers?|shouts?|asks?|replies?|says?)[,:]?\s+(.+?)[\.\!\?]", re.IGNORECASE),
]


def _extract_dialogue(scene_description: str) -> Optional[str]:
    """Extract the first plausible dialogue line from a scene description."""
    if not scene_description:
        return None
    for pattern in _DIALOGUE_PATTERNS:
        match = pattern.search(scene_description)
        if match:
            text = match.group(1).strip()
            if len(text) > 8:
                return text
    return None


# ---------------------------------------------------------------------------
# Track status model
# ---------------------------------------------------------------------------

class TrackStatus:
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"
    MOCK = "mock"


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class AudioGenerationService:
    """
    Generates three audio tracks per scene:
      - dialogue  (Coqui TTS)
      - score     (Stable Audio Open)
      - ambient   (Stable Audio Open)

    Models are lazy-loaded on first use. Operates in mock mode when
    libraries are not installed.
    """

    def __init__(self) -> None:
        self.output_base = Path(__file__).resolve().parents[3] / "outputs" / "audio"
        self.output_base.mkdir(parents=True, exist_ok=True)

        self._tts: Any = None
        self._stable_audio: Any = None
        self._tts_lock = asyncio.Lock()
        self._stable_audio_lock = asyncio.Lock()

        # In-memory job tracking: job_id -> dict
        self._jobs: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _get_device(self) -> str:
        """Return best available torch device (mps > cuda > cpu)."""
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    async def _load_tts(self) -> None:
        """Lazy-load Coqui TTS model (thread-safe)."""
        async with self._tts_lock:
            if self._tts is not None:
                return
            logger.info("Loading Coqui TTS model (tacotron2-DDC)…")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_tts_sync)

    def _load_tts_sync(self) -> None:
        from TTS.api import TTS
        # gpu=False works on all platforms; MPS is used automatically by PyTorch
        self._tts = TTS("tts_models/en/ljspeech/tacotron2-DDC", gpu=False)
        logger.info("Coqui TTS model loaded")

    async def _load_stable_audio(self) -> None:
        """Lazy-load Stable Audio Open model (thread-safe)."""
        async with self._stable_audio_lock:
            if self._stable_audio is not None:
                return
            logger.info("Loading Stable Audio Open model…")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_stable_audio_sync)

    def _load_stable_audio_sync(self) -> None:
        from diffusers import StableAudioPipeline
        import torch
        device = self._get_device()
        hf_token = os.environ.get("HF_TOKEN", "")
        if not hf_token:
            logger.warning("HF_TOKEN not set — Stable Audio Open will fail for gated access")
        self._stable_audio = StableAudioPipeline.from_pretrained(
            "stabilityai/stable-audio-open-1.0",
            torch_dtype=torch.float32,
            token=hf_token,
        )
        self._stable_audio = self._stable_audio.to(device)
        logger.info("Stable Audio Open model loaded on %s", device)

    # ------------------------------------------------------------------
    # Output directory helpers
    # ------------------------------------------------------------------

    def _scene_dir(self, project_id: str, scene_id: str) -> Path:
        d = self.output_base / project_id / scene_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _track_path(self, project_id: str, scene_id: str, track: str) -> Path:
        return self._scene_dir(project_id, scene_id) / f"{track}_{scene_id}.wav"

    # ------------------------------------------------------------------
    # Static file URL helper
    # ------------------------------------------------------------------

    @staticmethod
    def _file_url(path: Path) -> str:
        """Convert absolute path to a URL served by the /outputs static mount."""
        try:
            rel = path.relative_to(Path(__file__).resolve().parents[3] / "outputs")
            return f"/outputs/{rel.as_posix()}"
        except ValueError:
            return str(path)

    # ------------------------------------------------------------------
    # Track generators
    # ------------------------------------------------------------------

    async def generate_dialogue(
        self,
        scene_id: str,
        project_id: str,
        scene_description: str,
    ) -> Dict[str, Any]:
        """Generate dialogue track using Coqui TTS."""
        out_path = self._track_path(project_id, scene_id, "dialogue")

        if MOCK_MODE:
            _write_silence_wav(out_path, duration_seconds=2.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — TTS library not installed. Install with: pip install TTS",
            }

        dialogue_text = _extract_dialogue(scene_description)
        if not dialogue_text:
            _write_silence_wav(out_path, duration_seconds=1.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.SKIPPED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "No dialogue detected in scene description — silence written.",
            }

        try:
            await self._load_tts()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._tts.tts_to_file(text=dialogue_text, file_path=str(out_path)),
            )
            return {
                "track": "dialogue",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "text_used": dialogue_text,
                "advisory": "Dialogue rendered via Coqui TTS (tacotron2-DDC).",
            }
        except Exception as exc:
            logger.error("Dialogue generation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=1.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.FAILED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Dialogue generation failed — silence written as fallback.",
            }

    async def generate_score(
        self,
        scene_id: str,
        project_id: str,
        mood: str,
        score_notes: str,
        prompt: str | None = None,
    ) -> Dict[str, Any]:
        """Generate score track using Stable Audio Open."""
        out_path = self._track_path(project_id, scene_id, "score")

        if MOCK_MODE:
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "score",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — diffusers/StableAudioPipeline not installed. Install with: pip install diffusers scipy soundfile",
            }

        # Build prompt from mood + score_notes, or use provided prompt
        if prompt:
            prompt_to_use = prompt
        else:
            parts = [p.strip() for p in [mood, score_notes] if p and p.strip()]
            prompt_to_use = ", ".join(parts) if parts else "cinematic orchestral score, emotional, atmospheric"
            prompt_to_use += ", cinematic, film score"

        try:
            await self._load_stable_audio()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._generate_stable_audio_track(prompt_to_use, out_path, duration_s=30),
            )
            return {
                "track": "score",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "prompt_used": prompt_to_use,
                "advisory": "Score rendered via Stable Audio Open (30s).",
            }
        except Exception as exc:
            logger.error("Score generation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "score",
                "status": TrackStatus.FAILED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Score generation failed — silence written as fallback.",
            }

    async def generate_ambient(
        self,
        scene_id: str,
        project_id: str,
        ambient_notes: str,
        silence_flag: bool,
    ) -> Dict[str, Any]:
        """Generate ambient track using Stable Audio Open."""
        out_path = self._track_path(project_id, scene_id, "ambient")

        if silence_flag:
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "ambient",
                "status": TrackStatus.SKIPPED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Silence flag set — intentional silence for this scene.",
            }

        if MOCK_MODE:
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "ambient",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — diffusers/StableAudioPipeline not installed. Install with: pip install diffusers scipy soundfile",
            }

        prompt = ambient_notes.strip() if ambient_notes and ambient_notes.strip() else \
            "ambient environmental sound, natural atmosphere, subtle background"
        prompt += ", ambient, atmospheric, background"

        try:
            await self._load_stable_audio()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._generate_stable_audio_track(prompt, out_path, duration_s=30),
            )
            return {
                "track": "ambient",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "prompt_used": prompt,
                "advisory": "Ambient rendered via Stable Audio Open (30s).",
            }
        except Exception as exc:
            logger.error("Ambient generation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "ambient",
                "status": TrackStatus.FAILED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Ambient generation failed — silence written as fallback.",
            }

    def _generate_stable_audio_track(self, prompt: str, out_path: Path, duration_s: int = 30) -> None:
        """Synchronous Stable Audio Open generation — runs in executor."""
        import torch

        with torch.no_grad():
            audio = self._stable_audio(
                prompt=prompt,
                num_inference_steps=100,
                audio_end_in_s=duration_s,
                num_waveforms=1,
            )

        audio_data = audio.audios[0]
        sample_rate = self._stable_audio.vae.sampling_rate

        # Normalize to int16
        audio_int16 = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        wavfile.write(str(out_path), sample_rate, audio_int16)

    # ------------------------------------------------------------------
    # Full mix
    # ------------------------------------------------------------------

    async def generate_full_mix(
        self,
        scene_id: str,
        project_id: str,
        scene_description: str = "",
        mood: str = "",
        score_notes: str = "",
        ambient_notes: str = "",
        silence_flag: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate all three tracks concurrently.
        Returns a dict with per-track results and overall status.
        """
        job_id = f"audio_{project_id}_{scene_id}_{uuid.uuid4().hex[:8]}"
        started_at = datetime.now().isoformat()

        # Record job as generating
        self._jobs[job_id] = {
            "job_id": job_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "status": "generating",
            "started_at": started_at,
            "tracks": {
                "dialogue": {"status": TrackStatus.PENDING},
                "score": {"status": TrackStatus.PENDING},
                "ambient": {"status": TrackStatus.PENDING},
            },
        }

        try:
            dialogue_task = self.generate_dialogue(scene_id, project_id, scene_description)
            score_task = self.generate_score(scene_id, project_id, mood, score_notes)
            ambient_task = self.generate_ambient(scene_id, project_id, ambient_notes, silence_flag)

            dialogue_result, score_result, ambient_result = await asyncio.gather(
                dialogue_task, score_task, ambient_task
            )

            completed_at = datetime.now().isoformat()
            result = {
                "job_id": job_id,
                "project_id": project_id,
                "scene_id": scene_id,
                "status": "complete",
                "mock_mode": MOCK_MODE,
                "started_at": started_at,
                "completed_at": completed_at,
                "tracks": {
                    "dialogue": dialogue_result,
                    "score": score_result,
                    "ambient": ambient_result,
                },
            }
            self._jobs[job_id] = result
            return result

        except Exception as exc:
            logger.error("Full mix generation failed for scene %s: %s", scene_id, exc)
            error_result = {
                "job_id": job_id,
                "project_id": project_id,
                "scene_id": scene_id,
                "status": "failed",
                "mock_mode": MOCK_MODE,
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "error": str(exc),
                "tracks": {
                    "dialogue": {"status": TrackStatus.FAILED},
                    "score": {"status": TrackStatus.FAILED},
                    "ambient": {"status": TrackStatus.FAILED},
                },
            }
            self._jobs[job_id] = error_result
            return error_result

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_scene_status(self, project_id: str, scene_id: str) -> Dict[str, Any]:
        """Return the latest job status for a scene."""
        # Find most recent job for this scene
        matching = [
            job for job in self._jobs.values()
            if job.get("project_id") == project_id and job.get("scene_id") == scene_id
        ]
        if not matching:
            # Check if files exist on disk
            return self._status_from_disk(project_id, scene_id)

        # Return most recent
        matching.sort(key=lambda j: j.get("started_at", ""), reverse=True)
        return matching[0]

    def get_project_status(self, project_id: str) -> Dict[str, Any]:
        """Return status for all scenes in a project."""
        scene_ids: set = set()
        for job in self._jobs.values():
            if job.get("project_id") == project_id:
                scene_ids.add(job.get("scene_id", ""))

        scenes_status = {}
        for scene_id in scene_ids:
            if scene_id:
                scenes_status[scene_id] = self.get_scene_status(project_id, scene_id)

        return {
            "project_id": project_id,
            "mock_mode": MOCK_MODE,
            "scenes": scenes_status,
            "total_scenes": len(scenes_status),
        }

    def _status_from_disk(self, project_id: str, scene_id: str) -> Dict[str, Any]:
        """Build status from files that exist on disk (no in-memory job)."""
        scene_dir = self.output_base / project_id / scene_id
        tracks: Dict[str, Any] = {}
        for track in ("dialogue", "score", "ambient"):
            path = scene_dir / f"{track}_{scene_id}.wav"
            if path.exists():
                tracks[track] = {
                    "status": TrackStatus.COMPLETE,
                    "file_path": str(path),
                    "file_url": self._file_url(path),
                }
            else:
                tracks[track] = {"status": TrackStatus.PENDING}

        overall = "complete" if all(
            t.get("status") == TrackStatus.COMPLETE for t in tracks.values()
        ) else "pending"

        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "status": overall,
            "mock_mode": MOCK_MODE,
            "tracks": tracks,
        }

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    @staticmethod
    def capabilities() -> Dict[str, Any]:
        return {
            "mock_mode": MOCK_MODE,
            "tts_available": TTS_AVAILABLE,
            "diffusers_available": DIFFUSERS_AVAILABLE,
            "torch_available": TORCH_AVAILABLE,
            "tts_model": "tts_models/en/ljspeech/tacotron2-DDC",
            "stable_audio_model": "stabilityai/stable-audio-open-1.0",
            "apple_silicon_supported": True,
            "install_hint": (
                "pip install torch torchaudio TTS diffusers scipy soundfile"
                if MOCK_MODE else None
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

audio_generation_service = AudioGenerationService()