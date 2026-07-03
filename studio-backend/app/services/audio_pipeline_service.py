"""
Audio Pipeline Service — Piper TTS + MusicGen-small + FFmpeg

Full audio generation pipeline for Studio:
  1. Dialogue: Piper TTS (en_US-lessac-medium)
  2. Score/Ambient: MusicGen-small (facebook/musicgen-small)
  3. Mixing: FFmpeg (dialogue foreground + score background at -18dB)
  4. Merge onto video: FFmpeg

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
import shutil
import subprocess
import struct
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("audio-pipeline")

# ---------------------------------------------------------------------------
# Availability probes — checked once at import time
# ---------------------------------------------------------------------------

def _probe_piper() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_musicgen() -> bool:
    try:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


PIPER_AVAILABLE = _probe_piper()
MUSICGEN_AVAILABLE = _probe_musicgen()
TORCH_AVAILABLE = _probe_torch()
FFMPEG_AVAILABLE = _probe_ffmpeg()

MOCK_MODE = not (PIPER_AVAILABLE and TORCH_AVAILABLE and FFMPEG_AVAILABLE)

if MOCK_MODE:
    missing = []
    if not PIPER_AVAILABLE:
        missing.append("piper-tts")
    if not TORCH_AVAILABLE:
        missing.append("torch")
    if not FFMPEG_AVAILABLE:
        missing.append("ffmpeg")
    logger.warning(
        "AudioPipelineService running in MOCK MODE — missing: %s. "
        "Install with: pip install piper-tts torch transformers scipy",
        ", ".join(missing),
    )
else:
    logger.info("AudioPipelineService: all libraries available — real generation enabled")


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
# Dialogue extraction from screenplay format
# ---------------------------------------------------------------------------

def _extract_dialogue_lines(scene_text: str) -> List[Dict[str, str]]:
    """
    Extract dialogue lines from screenplay-formatted text.
    
    Screenplay format:
        CHARACTER_NAME
        Dialogue line here.
        
        ANOTHER_CHARACTER
        Another line.
    
    Returns list of dicts with 'character' and 'text' keys.
    """
    if not scene_text:
        return []
    
    lines = scene_text.split("\n")
    dialogue_lines: List[Dict[str, str]] = []
    current_character: Optional[str] = None
    current_dialogue: List[str] = []
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines (they end dialogue blocks)
        if not stripped:
            if current_character and current_dialogue:
                dialogue_lines.append({
                    "character": current_character,
                    "text": " ".join(current_dialogue).strip(),
                })
                current_character = None
                current_dialogue = []
            continue
        
        # Check if this is a character cue (ALL CAPS, short line, not a section header)
        # Character cues are typically < 35 chars and don't start with common headers
        clean = re.sub(r"\(.*?\)", "", stripped).strip().rstrip(".")
        is_char_cue = (
            len(stripped) < 35
            and len(clean) >= 2
            and clean.replace(" ", "").replace("'", "").isalpha()
            and clean.isupper()
            and not clean.startswith(("THE ", "ACT ", "INT ", "EXT ", "CUT ", "FADE", "SCENE"))
        )
        
        if is_char_cue:
            # Save previous dialogue if any
            if current_character and current_dialogue:
                dialogue_lines.append({
                    "character": current_character,
                    "text": " ".join(current_dialogue).strip(),
                })
            current_character = clean
            current_dialogue = []
        elif current_character:
            # Skip parenthetical stage directions
            if stripped.startswith("(") and stripped.endswith(")"):
                continue
            # This is dialogue text
            current_dialogue.append(stripped)
    
    # Don't forget the last dialogue block
    if current_character and current_dialogue:
        dialogue_lines.append({
            "character": current_character,
            "text": " ".join(current_dialogue).strip(),
        })
    
    return dialogue_lines


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

class AudioPipelineService:
    """
    Full audio generation pipeline:
      1. Dialogue: Piper TTS
      2. Score/Ambient: MusicGen-small
      3. Mixing: FFmpeg
      4. Merge onto video: FFmpeg
    """

    def __init__(self) -> None:
        self.output_base = Path(__file__).resolve().parents[2] / "outputs" / "audio"
        self.output_base.mkdir(parents=True, exist_ok=True)
        
        # Piper voice model path
        self.piper_model_dir = Path(__file__).resolve().parents[2] / "models" / "piper"
        self.piper_voice = "en_US-lessac-medium"
        
        # Secondary voice for different characters
        self.piper_voices = {
            "default": "en_US-lessac-medium",
            "male": "en_US-lessac-medium",
            "female": "en_US-lessac-medium",  # Could add a female voice later
        }

        self._musicgen_model: Any = None
        self._musicgen_processor: Any = None
        self._musicgen_lock = asyncio.Lock()

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

    def _get_piper_model_path(self) -> Path:
        """Return path to the Piper voice model."""
        return self.piper_model_dir / f"{self.piper_voice}.onnx"

    async def _load_musicgen(self) -> None:
        """Lazy-load MusicGen-small model (thread-safe)."""
        async with self._musicgen_lock:
            if self._musicgen_model is not None:
                return
            logger.info("Loading MusicGen-small model…")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_musicgen_sync)

    def _load_musicgen_sync(self) -> None:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        import torch
        
        device = self._get_device()
        logger.info("Loading MusicGen-small on %s", device)
        
        self._musicgen_processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
        self._musicgen_model = MusicgenForConditionalGeneration.from_pretrained(
            "facebook/musicgen-small",
            torch_dtype=torch.float32 if device == "cpu" else torch.float16,
        )
        self._musicgen_model = self._musicgen_model.to(device)
        logger.info("MusicGen-small model loaded on %s", device)

    # ------------------------------------------------------------------
    # Output directory helpers
    # ------------------------------------------------------------------

    def _scene_dir(self, project_id: str, scene_id: str) -> Path:
        d = self.output_base / project_id / scene_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _track_path(self, project_id: str, scene_id: str, track: str) -> Path:
        return self._scene_dir(project_id, scene_id) / f"{track}_{scene_id}.wav"

    def _dialogue_line_path(self, project_id: str, scene_id: str, line_idx: int) -> Path:
        return self._scene_dir(project_id, scene_id) / f"dialogue_line_{line_idx:03d}.wav"

    # ------------------------------------------------------------------
    # Static file URL helper
    # ------------------------------------------------------------------

    @staticmethod
    def _file_url(path: Path) -> str:
        """Convert absolute path to a URL served by the /outputs static mount."""
        try:
            rel = path.relative_to(Path(__file__).resolve().parents[2] / "outputs")
            return f"/outputs/{rel.as_posix()}"
        except ValueError:
            return str(path)

    # ------------------------------------------------------------------
    # Piper TTS dialogue generation
    # ------------------------------------------------------------------

    def _generate_piper_tts_sync(self, text: str, output_path: Path, voice: str | None = None) -> None:
        """Synchronous Piper TTS generation — runs in executor."""
        import piper
        
        voice_name = voice or self.piper_voice
        model_path = self.piper_model_dir / f"{voice_name}.onnx"
        
        if not model_path.exists():
            raise FileNotFoundError(f"Piper voice model not found: {model_path}")
        
        # Load the Piper voice model
        voice_instance = piper.PiperVoice.load(model_path)
        
        # synthesize_wav handles WAV header setup automatically (set_wav_format=True)
        with wave.open(str(output_path), "wb") as wav_file:
            voice_instance.synthesize_wav(text, wav_file, set_wav_format=True)

    async def generate_dialogue(
        self,
        scene_id: str,
        project_id: str,
        scene_text: str,
    ) -> Dict[str, Any]:
        """Generate dialogue track using Piper TTS."""
        out_path = self._track_path(project_id, scene_id, "dialogue")

        if MOCK_MODE:
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — Piper TTS not available. Install with: pip install piper-tts",
            }

        # Extract dialogue lines from scene text
        dialogue_lines = _extract_dialogue_lines(scene_text)
        
        if not dialogue_lines:
            _write_silence_wav(out_path, duration_seconds=2.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.SKIPPED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "No dialogue detected in scene — silence written.",
                "lines_found": 0,
            }

        logger.info(
            "DIALOGUE_EXTRACTION | scene=%s | lines=%d | characters=%s",
            scene_id,
            len(dialogue_lines),
            list(set(d["character"] for d in dialogue_lines)),
        )

        # Generate each dialogue line
        line_files: List[Path] = []
        for idx, line in enumerate(dialogue_lines):
            line_path = self._dialogue_line_path(project_id, scene_id, idx)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda t=line["text"], p=line_path: self._generate_piper_tts_sync(t, p),
                )
                line_files.append(line_path)
                logger.info(
                    "DIALOGUE_LINE_GENERATED | scene=%s | line=%d | character=%s | text=%s",
                    scene_id, idx, line["character"], line["text"][:50],
                )
            except Exception as exc:
                logger.error(
                    "DIALOGUE_LINE_FAILED | scene=%s | line=%d | character=%s | error=%s",
                    scene_id, idx, line["character"], exc,
                )
                # Write silence for failed line
                _write_silence_wav(line_path, duration_seconds=1.0)
                line_files.append(line_path)

        # Concatenate dialogue lines with silence gaps
        try:
            await self._concatenate_dialogue_lines(line_files, out_path, gap_seconds=0.3)
            return {
                "track": "dialogue",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "lines_generated": len(line_files),
                "characters": list(set(d["character"] for d in dialogue_lines)),
                "advisory": f"Dialogue rendered via Piper TTS ({len(line_files)} lines).",
            }
        except Exception as exc:
            logger.error("Dialogue concatenation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=2.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.FAILED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Dialogue concatenation failed — silence written as fallback.",
            }

    async def _concatenate_dialogue_lines(
        self,
        line_files: List[Path],
        output_path: Path,
        gap_seconds: float = 0.3,
    ) -> None:
        """Concatenate dialogue line WAV files with silence gaps using FFmpeg."""
        if not line_files:
            _write_silence_wav(output_path, duration_seconds=1.0)
            return

        # Create a concat file for FFmpeg
        concat_file = output_path.parent / "dialogue_concat.txt"
        silence_file = output_path.parent / "silence_gap.wav"
        
        # Create silence gap file
        _write_silence_wav(silence_file, duration_seconds=gap_seconds, sample_rate=22050)
        
        with open(concat_file, "w") as f:
            for i, line_file in enumerate(line_files):
                if line_file.exists():
                    f.write(f"file '{line_file}'\n")
                    if i < len(line_files) - 1:
                        f.write(f"file '{silence_file}'\n")

        # Use FFmpeg to concatenate
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, check=True))
        
        # Cleanup temp files
        concat_file.unlink(missing_ok=True)
        silence_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # MusicGen score/ambient generation
    # ------------------------------------------------------------------

    def _generate_musicgen_sync(
        self,
        prompt: str,
        output_path: Path,
        duration_seconds: float = 10.0,
    ) -> None:
        """Synchronous MusicGen generation — runs in executor."""
        import torch
        import scipy.io.wavfile as wavfile
        
        device = self._get_device()
        
        # Prepare inputs
        inputs = self._musicgen_processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Calculate max_new_tokens based on duration
        # MusicGen generates at ~50 tokens per second
        max_tokens = int(duration_seconds * 50)
        
        with torch.no_grad():
            audio_values = self._musicgen_model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                guidance_scale=3.0,
            )
        
        # Convert to numpy: shape is (batch=1, channels=1, samples) → squeeze to (samples,)
        audio_data = audio_values[0].cpu().float().numpy().squeeze()
        
        # Normalize to int16 safely
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val
        audio_data = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        
        # MusicGen outputs at 32kHz; ensure sample_rate is a plain int for WAV header
        sample_rate = int(self._musicgen_model.config.audio_encoder.sampling_rate)
        wavfile.write(str(output_path), sample_rate, audio_data)

    async def generate_score(
        self,
        scene_id: str,
        project_id: str,
        mood: str,
        score_notes: str,
        instrumentation: str = "",
        tempo: str = "",
        silence_flag: bool = False,
        duration_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """Generate score track using MusicGen-small."""
        out_path = self._track_path(project_id, scene_id, "score")

        if silence_flag:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "score",
                "status": TrackStatus.SKIPPED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Silence flag set — intentional silence for this scene.",
            }

        if MOCK_MODE or not MUSICGEN_AVAILABLE:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "score",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — MusicGen not available. Install with: pip install transformers",
            }

        # Build prompt from audio brief
        prompt_parts = []
        if mood:
            prompt_parts.append(mood)
        if score_notes:
            prompt_parts.append(score_notes)
        if instrumentation:
            prompt_parts.append(instrumentation)
        if tempo:
            prompt_parts.append(f"{tempo} tempo")
        
        # Add cinematic context
        prompt_parts.append("cinematic film score, atmospheric")
        
        prompt = ", ".join(p for p in prompt_parts if p)
        if not prompt:
            prompt = "cinematic orchestral score, emotional, atmospheric"

        logger.info(
            "SCORE_GENERATION | scene=%s | prompt=%s | duration=%ss",
            scene_id, prompt[:80], duration_seconds,
        )

        try:
            await self._load_musicgen()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._generate_musicgen_sync(prompt, out_path, duration_seconds),
            )
            return {
                "track": "score",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "prompt_used": prompt,
                "duration_seconds": duration_seconds,
                "advisory": f"Score rendered via MusicGen-small ({duration_seconds}s).",
            }
        except Exception as exc:
            logger.error("Score generation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
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
        duration_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """Generate ambient track using MusicGen-small."""
        out_path = self._track_path(project_id, scene_id, "ambient")

        if silence_flag:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "ambient",
                "status": TrackStatus.SKIPPED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Silence flag set — intentional silence for this scene.",
            }

        if MOCK_MODE or not MUSICGEN_AVAILABLE:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "ambient",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — MusicGen not available. Install with: pip install transformers",
            }

        prompt = ambient_notes.strip() if ambient_notes and ambient_notes.strip() else \
            "ambient environmental sound, natural atmosphere, subtle background"
        prompt += ", ambient, atmospheric, background, diegetic sound"

        logger.info(
            "AMBIENT_GENERATION | scene=%s | prompt=%s | duration=%ss",
            scene_id, prompt[:80], duration_seconds,
        )

        try:
            await self._load_musicgen()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._generate_musicgen_sync(prompt, out_path, duration_seconds),
            )
            return {
                "track": "ambient",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "prompt_used": prompt,
                "duration_seconds": duration_seconds,
                "advisory": f"Ambient rendered via MusicGen-small ({duration_seconds}s).",
            }
        except Exception as exc:
            logger.error("Ambient generation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "ambient",
                "status": TrackStatus.FAILED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Ambient generation failed — silence written as fallback.",
            }

    # ------------------------------------------------------------------
    # FFmpeg audio mixing
    # ------------------------------------------------------------------

    async def mix_audio_tracks(
        self,
        project_id: str,
        scene_id: str,
        dialogue_path: Path,
        score_path: Path,
        ambient_path: Path | None = None,
        score_volume_db: float = -18.0,
    ) -> Dict[str, Any]:
        """
        Mix dialogue (foreground, full volume) with score/ambient (background, lower volume).
        Uses FFmpeg amix filter.
        """
        out_path = self._scene_dir(project_id, scene_id) / f"mixed_{scene_id}.wav"

        if not FFMPEG_AVAILABLE:
            # Fallback: just copy dialogue track
            if dialogue_path.exists():
                shutil.copy(dialogue_path, out_path)
            else:
                _write_silence_wav(out_path, duration_seconds=5.0)
            return {
                "track": "mixed",
                "status": TrackStatus.MOCK,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "FFmpeg not available — dialogue track copied as-is.",
            }

        # Build FFmpeg command for mixing
        inputs = []
        filter_parts = []
        
        # Dialogue track (full volume)
        if dialogue_path.exists():
            inputs.extend(["-i", str(dialogue_path)])
            filter_parts.append(f"[{len(inputs)//2 - 1}:a]volume=1.0[dialogue]")
        
        # Score track (reduced volume)
        if score_path.exists():
            inputs.extend(["-i", str(score_path)])
            filter_parts.append(f"[{len(inputs)//2 - 1}:a]volume={score_volume_db}dB[score]")
        
        # Ambient track (reduced volume, if provided)
        if ambient_path and ambient_path.exists():
            inputs.extend(["-i", str(ambient_path)])
            filter_parts.append(f"[{len(inputs)//2 - 1}:a]volume={score_volume_db}dB[ambient]")

        if not filter_parts:
            _write_silence_wav(out_path, duration_seconds=5.0)
            return {
                "track": "mixed",
                "status": TrackStatus.SKIPPED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "No audio tracks to mix — silence written.",
            }

        # Build amix filter
        track_labels = []
        if dialogue_path.exists():
            track_labels.append("[dialogue]")
        if score_path.exists():
            track_labels.append("[score]")
        if ambient_path and ambient_path.exists():
            track_labels.append("[ambient]")
        
        if len(track_labels) == 1:
            # Only one track, just copy it
            filter_complex = f"{track_labels[0]}acopy[out]"
            maps = ["-map", "[out]"]
        else:
            # Mix all tracks - use semicolons between chains
            filter_complex = ";".join(filter_parts) + ";" + "".join(track_labels) + f"amix=inputs={len(track_labels)}:duration=longest:normalize=0[out]"
            maps = ["-map", "[out]"]

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            *maps,
            "-ac", "1",  # Mono output
            "-ar", "22050",  # Standard sample rate
            str(out_path),
        ]

        logger.info(
            "AUDIO_MIX | scene=%s | tracks=%d | score_volume=%sdB",
            scene_id, len(track_labels), score_volume_db,
        )

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True),
            )
            
            if result.returncode != 0:
                logger.error("FFmpeg mix failed: %s", result.stderr)
                # Fallback to dialogue only
                if dialogue_path.exists():
                    shutil.copy(dialogue_path, out_path)
                else:
                    _write_silence_wav(out_path, duration_seconds=5.0)
                return {
                    "track": "mixed",
                    "status": TrackStatus.FAILED,
                    "file_path": str(out_path),
                    "file_url": self._file_url(out_path),
                    "error": result.stderr[:200],
                    "advisory": "FFmpeg mix failed — fallback audio used.",
                }

            return {
                "track": "mixed",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "tracks_mixed": len(track_labels),
                "advisory": f"Audio mixed via FFmpeg ({len(track_labels)} tracks).",
            }
        except Exception as exc:
            logger.error("Audio mixing failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=5.0)
            return {
                "track": "mixed",
                "status": TrackStatus.FAILED,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Audio mixing failed — silence written as fallback.",
            }

    # ------------------------------------------------------------------
    # FFmpeg video+audio merge
    # ------------------------------------------------------------------

    async def merge_audio_onto_video(
        self,
        project_id: str,
        scene_id: str,
        video_path: Path,
        audio_path: Path,
        replace_original: bool = False,
    ) -> Dict[str, Any]:
        """
        Merge mixed audio onto rendered video clip using FFmpeg.
        
        If replace_original is True, overwrites the original video file.
        Otherwise, saves alongside with '_audio' suffix.
        """
        if not video_path.exists():
            return {
                "track": "final_video",
                "status": TrackStatus.FAILED,
                "error": f"Video file not found: {video_path}",
                "advisory": "Cannot merge audio — rendered video not found.",
            }

        if not audio_path.exists():
            return {
                "track": "final_video",
                "status": TrackStatus.FAILED,
                "error": f"Audio file not found: {audio_path}",
                "advisory": "Cannot merge — mixed audio not found.",
            }

        if not FFMPEG_AVAILABLE:
            return {
                "track": "final_video",
                "status": TrackStatus.MOCK,
                "file_path": str(video_path),
                "file_url": self._file_url(video_path),
                "advisory": "FFmpeg not available — returning original video without audio.",
            }

        # Determine output path
        if replace_original:
            out_path = video_path
            temp_path = video_path.parent / f"{video_path.stem}_temp{video_path.suffix}"
        else:
            out_path = video_path.parent / f"{video_path.stem}_audio{video_path.suffix}"
            temp_path = None

        # FFmpeg command to merge audio onto video
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",  # Copy video stream without re-encoding
            "-c:a", "aac",   # Encode audio as AAC
            "-b:a", "192k",  # Audio bitrate
            "-map", "0:v:0",  # Take video from first input
            "-map", "1:a:0",  # Take audio from second input
            "-shortest",      # End when shortest stream ends
            str(temp_path if temp_path else out_path),
        ]

        logger.info(
            "VIDEO_AUDIO_MERGE | scene=%s | video=%s | audio=%s | replace=%s",
            scene_id, video_path.name, audio_path.name, replace_original,
        )

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True),
            )
            
            if result.returncode != 0:
                logger.error("FFmpeg merge failed: %s", result.stderr)
                return {
                    "track": "final_video",
                    "status": TrackStatus.FAILED,
                    "file_path": str(video_path),
                    "error": result.stderr[:200],
                    "advisory": "FFmpeg merge failed — original video returned.",
                }

            # If replacing original, swap files
            if temp_path and temp_path.exists():
                shutil.move(str(temp_path), str(out_path))

            return {
                "track": "final_video",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "replaced_original": replace_original,
                "advisory": f"Audio merged onto video via FFmpeg. Output: {out_path.name}",
            }
        except Exception as exc:
            logger.error("Video/audio merge failed for scene %s: %s", scene_id, exc)
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return {
                "track": "final_video",
                "status": TrackStatus.FAILED,
                "file_path": str(video_path),
                "error": str(exc),
                "advisory": "Video/audio merge failed — original video returned.",
            }

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def generate_full_pipeline(
        self,
        scene_id: str,
        project_id: str,
        scene_text: str = "",
        mood: str = "",
        score_notes: str = "",
        ambient_notes: str = "",
        instrumentation: str = "",
        tempo: str = "",
        silence_flag: bool = False,
        video_path: Path | None = None,
        estimated_duration_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Run the full audio generation pipeline:
        1. Generate dialogue with Piper TTS
        2. Generate score with MusicGen-small
        3. Generate ambient with MusicGen-small
        4. Mix audio tracks with FFmpeg
        5. Merge audio onto video with FFmpeg (if video_path provided)
        """
        job_id = f"audio_pipeline_{project_id}_{scene_id}_{uuid.uuid4().hex[:8]}"
        started_at = datetime.now().isoformat()

        # Record job as generating
        self._jobs[job_id] = {
            "job_id": job_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "status": "generating",
            "started_at": started_at,
            "steps": {
                "dialogue": {"status": TrackStatus.PENDING},
                "score": {"status": TrackStatus.PENDING},
                "ambient": {"status": TrackStatus.PENDING},
                "mix": {"status": TrackStatus.PENDING},
                "merge": {"status": TrackStatus.PENDING},
            },
        }

        logger.info(
            "AUDIO_PIPELINE_START | job=%s | project=%s | scene=%s | mock=%s",
            job_id, project_id, scene_id, MOCK_MODE,
        )

        try:
            # Step 1: Generate dialogue
            self._jobs[job_id]["steps"]["dialogue"]["status"] = TrackStatus.GENERATING
            dialogue_result = await self.generate_dialogue(scene_id, project_id, scene_text)
            self._jobs[job_id]["steps"]["dialogue"] = dialogue_result

            # Step 2 & 3: Generate score and ambient concurrently
            self._jobs[job_id]["steps"]["score"]["status"] = TrackStatus.GENERATING
            self._jobs[job_id]["steps"]["ambient"]["status"] = TrackStatus.GENERATING
            
            score_task = self.generate_score(
                scene_id, project_id, mood, score_notes,
                instrumentation, tempo, silence_flag, estimated_duration_seconds,
            )
            ambient_task = self.generate_ambient(
                scene_id, project_id, ambient_notes, silence_flag, estimated_duration_seconds,
            )
            
            score_result, ambient_result = await asyncio.gather(score_task, ambient_task)
            self._jobs[job_id]["steps"]["score"] = score_result
            self._jobs[job_id]["steps"]["ambient"] = ambient_result

            # Step 4: Mix audio tracks
            self._jobs[job_id]["steps"]["mix"]["status"] = TrackStatus.GENERATING
            dialogue_path = Path(dialogue_result.get("file_path", ""))
            score_path = Path(score_result.get("file_path", ""))
            ambient_path = Path(ambient_result.get("file_path", "")) if ambient_result.get("file_path") else None
            
            mix_result = await self.mix_audio_tracks(
                project_id, scene_id, dialogue_path, score_path, ambient_path,
            )
            self._jobs[job_id]["steps"]["mix"] = mix_result

            # Step 5: Merge audio onto video (if video path provided)
            merge_result = {"status": TrackStatus.SKIPPED, "advisory": "No video path provided."}
            if video_path and video_path.exists():
                self._jobs[job_id]["steps"]["merge"]["status"] = TrackStatus.GENERATING
                mixed_path = Path(mix_result.get("file_path", ""))
                merge_result = await self.merge_audio_onto_video(
                    project_id, scene_id, video_path, mixed_path, replace_original=False,
                )
            self._jobs[job_id]["steps"]["merge"] = merge_result

            # Final result
            completed_at = datetime.now().isoformat()
            result = {
                "job_id": job_id,
                "project_id": project_id,
                "scene_id": scene_id,
                "status": "complete",
                "mock_mode": MOCK_MODE,
                "started_at": started_at,
                "completed_at": completed_at,
                "steps": {
                    "dialogue": dialogue_result,
                    "score": score_result,
                    "ambient": ambient_result,
                    "mix": mix_result,
                    "merge": merge_result,
                },
                "final_video_path": merge_result.get("file_path") if merge_result.get("status") == TrackStatus.COMPLETE else None,
                "final_video_url": merge_result.get("file_url") if merge_result.get("status") == TrackStatus.COMPLETE else None,
                "mixed_audio_path": mix_result.get("file_path"),
                "mixed_audio_url": mix_result.get("file_url"),
            }
            self._jobs[job_id] = result
            
            logger.info(
                "AUDIO_PIPELINE_COMPLETE | job=%s | scene=%s | duration=%s",
                job_id, scene_id,
                f"{(datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)).total_seconds():.1f}s",
            )
            
            return result

        except Exception as exc:
            logger.error("Audio pipeline failed for scene %s: %s", scene_id, exc)
            error_result = {
                "job_id": job_id,
                "project_id": project_id,
                "scene_id": scene_id,
                "status": "failed",
                "mock_mode": MOCK_MODE,
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "error": str(exc),
                "steps": self._jobs.get(job_id, {}).get("steps", {}),
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
        for track in ("dialogue", "score", "ambient", "mixed"):
            path = scene_dir / f"{track}_{scene_id}.wav"
            if path.exists():
                tracks[track] = {
                    "status": TrackStatus.COMPLETE,
                    "file_path": str(path),
                    "file_url": self._file_url(path),
                }
            else:
                tracks[track] = {"status": TrackStatus.PENDING}

        # Check for final video with audio
        final_video = None
        if scene_dir.exists():
            for f in scene_dir.iterdir():
                if f.suffix in (".mp4", ".mov", ".webm") and "_audio" in f.stem:
                    final_video = {
                        "status": TrackStatus.COMPLETE,
                        "file_path": str(f),
                        "file_url": self._file_url(f),
                    }
                    break

        overall = "complete" if all(
            t.get("status") == TrackStatus.COMPLETE for t in tracks.values()
        ) else "pending"

        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "status": overall,
            "mock_mode": MOCK_MODE,
            "tracks": tracks,
            "final_video": final_video,
        }

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    @staticmethod
    def capabilities() -> Dict[str, Any]:
        return {
            "mock_mode": MOCK_MODE,
            "piper_available": PIPER_AVAILABLE,
            "musicgen_available": MUSICGEN_AVAILABLE,
            "torch_available": TORCH_AVAILABLE,
            "ffmpeg_available": FFMPEG_AVAILABLE,
            "piper_voice": "en_US-lessac-medium",
            "musicgen_model": "facebook/musicgen-small",
            "apple_silicon_supported": True,
            "install_hint": (
                "pip install piper-tts torch transformers scipy && brew install ffmpeg"
                if MOCK_MODE else None
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

audio_pipeline_service = AudioPipelineService()