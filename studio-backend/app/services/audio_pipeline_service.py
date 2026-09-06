"""
Audio Pipeline Service — CosyVoice/Qwen-TTS + optional score/ambient + FFmpeg

Full audio generation pipeline for Studio:
  1. Dialogue: CosyVoice/Qwen-TTS via DashScope
  2. Score/Ambient: skipped unless a provider is explicitly configured
  3. Mixing: FFmpeg (dialogue foreground, optional score background at -18dB)
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
import sys
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
# Dialogue TTS provider selection — mirrors AUDIO_SCORE_PROVIDER pattern
# ---------------------------------------------------------------------------

DIALOGUE_PROVIDER = (
    os.environ.get("AUDIO_DIALOGUE_PROVIDER")
    or os.environ.get("DIALOGUE_TTS_PROVIDER")
    or "cosyvoice"
).strip().lower() or "cosyvoice"

VALID_DIALOGUE_PROVIDERS = {"piper", "elevenlabs", "fish_audio", "cosyvoice", "auto"}

SCORE_AMBIENT_PROVIDER = (
    os.environ.get("AUDIO_SCORE_PROVIDER")
    or os.environ.get("AUDIO_SCORE_AMBIENT_PROVIDER")
    or "none"
).strip().lower() or "none"

VALID_SCORE_AMBIENT_PROVIDERS = {"none", "ace_step", "musicgen"}

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_DEFAULT_VOICE_ID = os.environ.get(
    "ELEVENLABS_DEFAULT_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"
).strip()
ELEVENLABS_MODEL_ID = os.environ.get(
    "ELEVENLABS_MODEL_ID", "eleven_flash_v2_5"
).strip()
ELEVENLABS_OUTPUT_FORMAT = os.environ.get(
    "ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32"
).strip()
ELEVENLABS_TIMEOUT_SECONDS = int(
    os.environ.get("ELEVENLABS_TIMEOUT_SECONDS", "30") or "30"
)
ELEVENLABS_MAX_RETRIES = int(
    os.environ.get("ELEVENLABS_MAX_RETRIES", "3") or "3"
)
ELEVENLABS_CHAR_LIMIT = int(
    os.environ.get("ELEVENLABS_CHAR_LIMIT", "2500") or "2500"
)
ELEVENLABS_FAILOVER_TO_PIPER = (
    os.environ.get("ELEVENLABS_FAILOVER_TO_PIPER", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
ELEVENLABS_CONFIGURED = bool(ELEVENLABS_API_KEY)


# ---------------------------------------------------------------------------
# Fish Audio TTS configuration
# ---------------------------------------------------------------------------

FISH_AUDIO_API_KEY = os.environ.get("FISH_AUDIO_API_KEY", "").strip()
FISH_AUDIO_API_BASE = "https://api.fish.audio/v1"

VALID_FISH_AUDIO_MODELS = {"s1", "s2-pro", "s2.1-pro", "s2.1-pro-free"}

_fish_audio_model_raw = os.environ.get("FISH_AUDIO_MODEL", "s2-pro").strip().lower() or "s2-pro"
if _fish_audio_model_raw not in VALID_FISH_AUDIO_MODELS:
    logger.error(
        "FISH_AUDIO_MODEL=%r is not a valid model (must be one of %s) — "
        "falling back to 's2-pro'. Emotion tag delimiters depend on the model: "
        "S2 uses [brackets], S1 uses (parentheses).",
        _fish_audio_model_raw, sorted(VALID_FISH_AUDIO_MODELS),
    )
    _fish_audio_model_raw = "s2-pro"
FISH_AUDIO_MODEL = _fish_audio_model_raw

FISH_AUDIO_TIMEOUT_SECONDS = int(
    os.environ.get("FISH_AUDIO_TIMEOUT_SECONDS", "30") or "30"
)
FISH_AUDIO_MAX_RETRIES = int(
    os.environ.get("FISH_AUDIO_MAX_RETRIES", "3") or "3"
)
FISH_AUDIO_OUTPUT_FORMAT = (
    os.environ.get("FISH_AUDIO_OUTPUT_FORMAT", "mp3").strip().lower() or "mp3"
)
FISH_AUDIO_FAILOVER_TO_PIPER = (
    os.environ.get("FISH_AUDIO_FAILOVER_TO_PIPER", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
FISH_AUDIO_CONFIGURED = bool(FISH_AUDIO_API_KEY)


# ---------------------------------------------------------------------------
# CosyVoice / Qwen-TTS configuration
# ---------------------------------------------------------------------------

COSYVOICE_CONFIGURED = bool(os.environ.get("DASHSCOPE_API_KEY", "").strip())
COSYVOICE_MODEL = (
    os.environ.get("COSYVOICE_MODEL")
    or os.environ.get("QWEN_TTS_MODEL")
    or "qwen3-tts-instruct-flash"
).strip() or "qwen3-tts-instruct-flash"
COSYVOICE_DEFAULT_VOICE = (
    os.environ.get("COSYVOICE_DEFAULT_VOICE")
    or os.environ.get("QWEN_TTS_DEFAULT_VOICE")
    or ("Cherry" if COSYVOICE_MODEL.startswith("qwen3-tts-instruct") else "longanwen_v3")
).strip()
COSYVOICE_OUTPUT_FORMAT = (
    os.environ.get("COSYVOICE_OUTPUT_FORMAT", "mp3").strip().lower()
    or "mp3"
)
COSYVOICE_FAILOVER_TO_PIPER = (
    os.environ.get("COSYVOICE_FAILOVER_TO_PIPER", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
COSYVOICE_SYSTEM_VOICES_WITHOUT_INSTRUCT = {
    "longanwen_v3",
    "longanwen",
    "longwanjun_v3",
}
COSYVOICE_V3_SYSTEM_VOICES_WITH_FIXED_INSTRUCT = {
    "longanyang",
}
COSYVOICE_FIXED_INSTRUCT_EMOTIONS = {
    "neutral",
    "fearful",
    "angry",
    "sad",
    "surprised",
    "happy",
    "disgusted",
}


# ---------------------------------------------------------------------------
# ACE Step score/ambient configuration
# ---------------------------------------------------------------------------

ACE_STEP_MODEL = "ACE-Step/ACE-Step-v1-3.5B"
ACE_STEP_RUNTIME_SITE = (
    Path(__file__).resolve().parents[2] / "outputs" / "ace_runtime_site"
)
ACE_STEP_CHECKPOINT_PATH = os.environ.get("ACE_STEP_CHECKPOINT_PATH", "").strip()
ACE_STEP_INFER_STEPS = int(os.environ.get("ACE_STEP_INFER_STEPS", "4") or "4")
ACE_STEP_GUIDANCE_SCALE = float(os.environ.get("ACE_STEP_GUIDANCE_SCALE", "15") or "15")
ACE_STEP_TIMEOUT_SECONDS = int(os.environ.get("ACE_STEP_TIMEOUT_SECONDS", "900") or "900")
ACE_STEP_DTYPE = os.environ.get("ACE_STEP_DTYPE", "float32").strip() or "float32"
ACE_STEP_CPU_OFFLOAD = (
    os.environ.get("ACE_STEP_CPU_OFFLOAD", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
ACE_STEP_AVAILABLE = shutil.which("ffmpeg") is not None


def _normalize_dialogue_provider(provider: str | None) -> str:
    """Validate and normalise a dialogue TTS provider string.

    Mirrors ``_normalize_score_provider`` in audio_generation_service.
    """
    normalized = (provider or DIALOGUE_PROVIDER or "piper").strip().lower()
    aliases = {
        "eleven": "elevenlabs",
        "eleven_labs": "elevenlabs",
        "eleven-labs": "elevenlabs",
        "piper-tts": "piper",
        "fish": "fish_audio",
        "fishaudio": "fish_audio",
        "fish-audio": "fish_audio",
        "cosy": "cosyvoice",
        "cosy_voice": "cosyvoice",
        "cosy-voice": "cosyvoice",
        "qwen": "cosyvoice",
        "qwen_tts": "cosyvoice",
        "qwen-tts": "cosyvoice",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in VALID_DIALOGUE_PROVIDERS:
        raise ValueError(
            f"AUDIO_DIALOGUE_PROVIDER must be one of {sorted(VALID_DIALOGUE_PROVIDERS)}, got {provider!r}"
        )
    return normalized


def _normalize_score_ambient_provider(provider: str | None) -> str:
    """Validate and normalize score/ambient provider selection."""
    normalized = (provider or SCORE_AMBIENT_PROVIDER or "none").strip().lower()
    aliases = {
        "": "none",
        "off": "none",
        "skip": "none",
        "disabled": "none",
        "no_provider": "none",
        "no-provider": "none",
        "ace": "ace_step",
        "ace-step": "ace_step",
        "acestep": "ace_step",
        "music_gen": "musicgen",
        "music-gen": "musicgen",
        "musicgen-small": "musicgen",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in VALID_SCORE_AMBIENT_PROVIDERS:
        raise ValueError(
            "AUDIO_SCORE_PROVIDER must be one of "
            f"{sorted(VALID_SCORE_AMBIENT_PROVIDERS)}, got {provider!r}"
        )
    return normalized


def _split_text_for_elevenlabs(text: str, char_limit: int = 2500) -> list[str]:
    """Split text into chunks at or below *char_limit* for ElevenLabs API calls.

    Prefers sentence boundaries (``. ``, ``! ``, ``? ``), then commas, then
    spaces.  Falls back to a hard split if no boundary is found within the
    limit.  Never truncates — all text is preserved across chunks.
    """
    if len(text) <= char_limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > char_limit:
        split_at = -1
        for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            pos = remaining.rfind(sep, 0, char_limit)
            if pos > split_at:
                split_at = pos + len(sep)
        if split_at <= 0:
            split_at = remaining.rfind(", ", 0, char_limit)
            if split_at > 0:
                split_at += 2
        if split_at <= 0:
            split_at = remaining.rfind("\n", 0, char_limit)
            if split_at > 0:
                split_at += 1
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, char_limit)
            if split_at > 0:
                split_at += 1
        if split_at <= 0:
            split_at = char_limit

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return [c for c in chunks if c]


def _resolve_elevenlabs_voice_id(
    character: str | None = None,
    project_id: str | None = None,
) -> str:
    """Resolve an ElevenLabs voice ID following the design-doc priority order.

    1. **Per-project DB assignment** — if *project_id* and *character* are
       provided, look up the character record's ``elevenlabs_voice_id``
       column in the SQLite ``characters`` table.  This is the UI-driven
       path that persists per-project.
    2. ``ELEVENLABS_VOICE_MAP_JSON`` exact character match (uppercase key).
       This is the global env-var fallback for quick bootstrapping.
    3. ``ELEVENLABS_VOICE_MAP_JSON`` ``"default"`` entry.
    4. ``ELEVENLABS_DEFAULT_VOICE_ID`` env var (defaults to the stock voice
       ``JBFqnCBsd6RMkjVDRZzb`` from the design doc).
    """
    voice_id = ""

    # 1. Per-project DB assignment (UI-driven, highest priority)
    if project_id and character:
        try:
            from app.data.storage import get_storage
            storage = get_storage("sqlite")
            db_voice_id = storage.get_character_voice_by_name(
                project_id, character.strip()
            )
            if db_voice_id:
                voice_id = db_voice_id
        except Exception as exc:
            logger.warning(
                "VOICE_RESOLUTION_DB_LOOKUP_FAILED | project=%s | character=%s | error=%s",
                project_id, character, exc,
            )

    # 2-3. ELEVENLABS_VOICE_MAP_JSON (global env-var fallback)
    if not voice_id:
        voice_map_json = os.environ.get("ELEVENLABS_VOICE_MAP_JSON", "").strip()
        if voice_map_json:
            try:
                voice_map: dict[str, str] = json.loads(voice_map_json)
                if character:
                    key = character.strip().upper()
                    if key in voice_map:
                        voice_id = voice_map[key]
                if not voice_id:
                    voice_id = voice_map.get("default", "")
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("ELEVENLABS_VOICE_MAP_JSON is set but could not be parsed")

    # 4. ELEVENLABS_DEFAULT_VOICE_ID env var
    if not voice_id:
        voice_id = os.environ.get(
            "ELEVENLABS_DEFAULT_VOICE_ID", ELEVENLABS_DEFAULT_VOICE_ID
        ).strip()

    if not voice_id:
        raise ValueError(
            "No ElevenLabs voice ID configured. Set ELEVENLABS_DEFAULT_VOICE_ID "
            "or ELEVENLABS_VOICE_MAP_JSON."
        )
    return voice_id


def _resolve_fish_audio_voice_id(
    character: str | None = None,
    project_id: str | None = None,
) -> str:
    """Resolve a Fish Audio voice model ID (reference_id).

    Mirrors ``_resolve_elevenlabs_voice_id`` but is env-var-only until the
    casting service is integrated (planned in a separate session):

    1. ``FISH_AUDIO_VOICE_MAP_JSON`` exact character match (uppercase key).
    2. ``FISH_AUDIO_VOICE_MAP_JSON`` ``"default"`` entry.
    3. ``FISH_AUDIO_DEFAULT_VOICE_ID`` env var.
    """
    voice_map_json = os.environ.get("FISH_AUDIO_VOICE_MAP_JSON", "").strip()
    if voice_map_json and character:
        try:
            voice_map: dict[str, str] = json.loads(voice_map_json)
            key = character.strip().upper()
            if key in voice_map:
                return voice_map[key]
            if "default" in voice_map:
                return voice_map["default"]
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("FISH_AUDIO_VOICE_MAP_JSON is set but could not be parsed")

    default_voice = os.environ.get("FISH_AUDIO_DEFAULT_VOICE_ID", "").strip()
    if default_voice:
        return default_voice

    raise ValueError(
        "No Fish Audio voice ID configured. Set FISH_AUDIO_DEFAULT_VOICE_ID "
        "or FISH_AUDIO_VOICE_MAP_JSON."
    )


def _resolve_cosyvoice_voice_id(
    character: str | None = None,
    project_id: str | None = None,
) -> str:
    """Resolve a CosyVoice stock voice name or cloned voice ID.

    Project-level Casting assignments take priority, then env maps/defaults.
    """
    if project_id and character:
        try:
            from app.data.storage import get_storage

            storage = get_storage("sqlite")
            if hasattr(storage, "get_character_voice_casting_by_name"):
                casting = storage.get_character_voice_casting_by_name(
                    project_id,
                    character.strip(),
                    provider="cosyvoice",
                )
                if isinstance(casting, dict):
                    voice_id = str(casting.get("voice_id") or "").strip()
                    if voice_id:
                        return voice_id
        except Exception as exc:
            logger.debug("CosyVoice casting lookup skipped for %s/%s: %s", project_id, character, exc)

    voice_map_json = os.environ.get("COSYVOICE_VOICE_MAP_JSON", "").strip()
    if voice_map_json and character:
        try:
            voice_map: dict[str, str] = json.loads(voice_map_json)
            key = character.strip().upper()
            if key in voice_map:
                return voice_map[key]
            if "default" in voice_map:
                return voice_map["default"]
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("COSYVOICE_VOICE_MAP_JSON is set but could not be parsed")

    return os.environ.get("COSYVOICE_DEFAULT_VOICE", COSYVOICE_DEFAULT_VOICE).strip() or COSYVOICE_DEFAULT_VOICE


def _cosyvoice_voice_instruction_mode(model: str, voice: str) -> str:
    """Return how instructions should be sent for the selected model/voice."""
    model_key = str(model or "").strip().lower()
    voice_key = str(voice or "").strip().lower()
    if model_key.startswith("qwen3-tts-instruct"):
        return "qwen_freeform"
    if model_key.startswith("cosyvoice-v3.5"):
        return "cosyvoice_freeform"
    if voice_key in COSYVOICE_SYSTEM_VOICES_WITHOUT_INSTRUCT:
        return "none"
    if model_key.startswith("cosyvoice-v3") and voice_key.startswith("cosyvoice-"):
        return "cosyvoice_freeform"
    if model_key.startswith("cosyvoice-v3") and voice_key in COSYVOICE_V3_SYSTEM_VOICES_WITH_FIXED_INSTRUCT:
        return "cosyvoice_fixed"
    if model_key.startswith("cosyvoice-v3"):
        return "none"
    return "none"


def _emotion_label_for_instruction(text: str) -> str:
    lowered = str(text or "").lower()
    if any(term in lowered for term in ("fear", "afraid", "dread", "unease", "anxious", "worry")):
        return "fearful"
    if any(term in lowered for term in ("angry", "anger", "furious", "rage")):
        return "angry"
    if any(term in lowered for term in ("sad", "grief", "regret", "mourn", "lost", "wounded", "hurt", "ashamed", "bitter", "betrayal", "dying", "disoriented")):
        return "sad"
    if any(term in lowered for term in ("surprise", "startled", "shock")):
        return "surprised"
    if any(term in lowered for term in ("happy", "relief", "warm", "hope")):
        return "happy"
    if any(term in lowered for term in ("disgust", "repuls")):
        return "disgusted"
    return "neutral"


def _cosyvoice_fixed_instruction(emotion: str) -> str:
    """Return the exact fixed-format v3 system-voice instruction DashScope accepts."""
    return f"你说话的情感是{emotion}。"


def _infer_dialogue_subtext_from_line(line: dict[str, Any]) -> str:
    """Infer a light delivery hint when extracted screenplay dialogue has no metadata."""
    text = str(line.get("text") or "").strip()
    lowered = text.lower()
    character = str(line.get("character") or line.get("character_name") or "").strip().upper()

    if "looking at me weird" in lowered or lowered.startswith("you good"):
        return "casual concern, testing whether something is wrong"
    if "i'm fine" in lowered or "just tired" in lowered:
        return "guarded deflection, trying to sound ordinary"
    if "you eat" in lowered:
        return "caretaking masked as routine"
    if lowered in {"yeah.", "yeah"}:
        return "quiet avoidance, keeping the answer small"
    if "something happened" in lowered or "something bad" in lowered or "would you come to me" in lowered:
        return "fear searching for reassurance without revealing why"
    if "what kind of something" in lowered:
        return "confusion with a protective edge"
    if "you're my people" in lowered or "always" in lowered:
        return "warm certainty that becomes painful in hindsight"
    if character == "MAYA" and "preparing" in lowered:
        return "controlled resolve under dread"
    return ""


def _build_dialogue_instruction(
    line: dict[str, Any],
    *,
    model: str,
    voice: str,
    scene_context: dict[str, Any] | None = None,
) -> tuple[str | None, str]:
    """Build provider-compatible delivery instructions for one dialogue line."""
    scene_context = scene_context if isinstance(scene_context, dict) else {}
    mode = _cosyvoice_voice_instruction_mode(model, voice)
    if mode == "none":
        return None, mode

    character = str(line.get("character") or line.get("character_name") or "").strip()
    emotional_subtext = str(line.get("emotional_subtext") or "").strip()
    if not emotional_subtext:
        emotional_subtext = _infer_dialogue_subtext_from_line(line)
    pacing_tag = str(line.get("pacing_tag") or "").strip()
    voice_hint = str(line.get("voice_style_hint") or "").strip()
    scene_tone = str(
        scene_context.get("emotional_tone")
        or scene_context.get("audio_tension")
        or scene_context.get("scene_mood")
        or ""
    ).strip()
    director_note = str(scene_context.get("director_note") or "").strip()

    evidence_parts = []
    if emotional_subtext:
        evidence_parts.append(f"subtext: {emotional_subtext}")
    if pacing_tag:
        evidence_parts.append(f"pace: {pacing_tag}")
    if scene_tone:
        evidence_parts.append(f"scene pressure: {scene_tone}")
    if voice_hint and voice_hint.upper() != character.upper():
        evidence_parts.append(f"voice: {voice_hint}")
    if director_note:
        evidence_parts.append(f"director note: {director_note}")

    if mode == "cosyvoice_fixed":
        emotion = _emotion_label_for_instruction(" ".join(evidence_parts))
        return _cosyvoice_fixed_instruction(emotion), mode

    if mode == "cosyvoice_freeform":
        # CosyVoice accepts free-form instructions for cloned/designed voices,
        # but the provider limit is 100 characters. Keep the complete creative
        # direction in performance_direction/instruction_sources and send a
        # compact provider payload carrying the same subtext and pacing.
        def _compact(value: str, limit: int) -> str:
            normalized = " ".join(value.split()).strip(" ,;.")
            if len(normalized) <= limit:
                return normalized
            clipped = normalized[: limit + 1].rsplit(" ", 1)[0].strip(" ,;.")
            return clipped or normalized[:limit].strip(" ,;.")

        compact_parts = []
        if emotional_subtext:
            compact_parts.append(_compact(emotional_subtext, 56))
        if pacing_tag:
            compact_parts.append(_compact(pacing_tag, 24))
        compact_parts.append("natural, restrained")
        return "; ".join(compact_parts)[:100], mode

    if not evidence_parts:
        evidence_parts.append("hold the line with restrained, natural film dialogue delivery")
    instruction = (
        f"Perform {character or 'the speaker'} with intimate, natural film dialogue. "
        f"Let the delivery carry {', '.join(evidence_parts)} without exaggeration."
    )
    return instruction[:480], mode


def _dialogue_instruction_sources(
    line: dict[str, Any],
    scene_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record which per-line/scene fields contributed to delivery instruction."""
    scene_context = scene_context if isinstance(scene_context, dict) else {}
    emotional_subtext = str(line.get("emotional_subtext") or "").strip()
    inferred_subtext = ""
    if not emotional_subtext:
        inferred_subtext = _infer_dialogue_subtext_from_line(line)
    scene_tone_key = ""
    scene_tone = ""
    for key in ("emotional_tone", "audio_tension", "scene_mood"):
        value = str(scene_context.get(key) or "").strip()
        if value:
            scene_tone_key = key
            scene_tone = value
            break
    return {
        "emotional_subtext": {
            "source": "line.emotional_subtext" if emotional_subtext else ("line_text_inference" if inferred_subtext else "missing"),
            "value": emotional_subtext or inferred_subtext or None,
        },
        "pacing_tag": {
            "source": "line.pacing_tag" if str(line.get("pacing_tag") or "").strip() else "missing",
            "value": str(line.get("pacing_tag") or "").strip() or None,
        },
        "voice_style_hint": {
            "source": "line.voice_style_hint" if str(line.get("voice_style_hint") or "").strip() else "missing",
            "value": str(line.get("voice_style_hint") or "").strip() or None,
        },
        "scene_pressure": {
            "source": f"scene_context.{scene_tone_key}" if scene_tone_key else "missing",
            "value": scene_tone or None,
        },
        "director_note": {
            "source": "scene_context.director_note" if str(scene_context.get("director_note") or "").strip() else "missing",
            "value": str(scene_context.get("director_note") or "").strip() or None,
        },
        "ssml_text": {
            "source": "line.ssml_text" if str(line.get("ssml_text") or "").strip() else "missing",
            "value": str(line.get("ssml_text") or "").strip() or None,
        },
    }


def _dialogue_tts_text(line: dict[str, Any]) -> str:
    """Return the exact text payload to send to the TTS provider for a line."""
    ssml_text = str(line.get("ssml_text") or "").strip()
    if ssml_text:
        return ssml_text
    return str(line.get("text") or "").strip()


def _dialogue_performance_direction(
    line: dict[str, Any],
    scene_context: dict[str, Any] | None = None,
) -> str:
    """Return the rich acting direction used to derive provider instructions."""
    scene_context = scene_context if isinstance(scene_context, dict) else {}
    parts: list[str] = []
    emotional_subtext = str(line.get("emotional_subtext") or "").strip()
    if not emotional_subtext:
        emotional_subtext = _infer_dialogue_subtext_from_line(line)
    pacing_tag = str(line.get("pacing_tag") or "").strip()
    scene_tone = str(
        scene_context.get("emotional_tone")
        or scene_context.get("audio_tension")
        or scene_context.get("scene_mood")
        or ""
    ).strip()
    if emotional_subtext:
        parts.append(emotional_subtext)
    if pacing_tag:
        parts.append(f"pace: {pacing_tag}")
    if scene_tone:
        parts.append(f"scene pressure: {scene_tone}")
    return "; ".join(parts)


def _fish_audio_emotion_delimiters(model: str) -> tuple[str, str]:
    """Return (open, close) delimiters for emotion tags based on model.

    S2 models (s2-pro, s2.1-pro, s2.1-pro-free) use [bracket] tags.
    S1 uses (parenthesis) tags.  See:
    https://docs.fish.audio/developer-guide/core-features/emotions
    """
    if model.startswith("s1"):
        return "(", ")"
    return "[", "]"


# ---------------------------------------------------------------------------
# Silence WAV helper
# ---------------------------------------------------------------------------

def _write_silence_wav(path: Path, duration_seconds: float = 1.0, sample_rate: int = 22050) -> None:
    """Write a minimal valid WAV file containing silence."""
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _estimate_dialogue_line_seconds(text: str) -> float:
    """Estimate spoken duration for one line using Studio's 150 wpm baseline."""
    words = max(1, len(str(text or "").split()))
    return (words / 150.0) * 60.0 + 0.2


def _select_dialogue_lines_for_video_duration(
    dialogue_lines: list[dict[str, str]],
    video_duration_seconds: float | None,
) -> tuple[list[dict[str, str]], str]:
    """Pick dialogue that can plausibly fit into a concrete rendered shot.

    Scene-level audio routes sometimes merge onto a single shot video. When no
    shot-level dialogue range is available, using the full scene dialogue creates
    a false audio overrun. Prefer the first contiguous cluster that fits the
    clip; if the opening line alone is too long, skip ahead to the first line
    that can fit so the shot still carries dialogue rather than forced silence.
    """
    if not dialogue_lines or not video_duration_seconds or video_duration_seconds <= 0:
        return dialogue_lines, "no video-duration dialogue clipping applied"

    target = max(1.0, video_duration_seconds - 0.35)
    selected: list[dict[str, str]] = []
    total = 0.0
    for line in dialogue_lines:
        estimated = _estimate_dialogue_line_seconds(line.get("text", ""))
        gap = 0.3 if selected else 0.0
        if selected and total + gap + estimated > target:
            break
        if not selected and estimated > target:
            continue
        selected.append(line)
        total += gap + estimated

    if selected:
        return (
            selected,
            f"selected {len(selected)} dialogue line(s) to fit {video_duration_seconds:.2f}s video",
        )

    return (
        [dialogue_lines[0]],
        "no line estimated to fit; kept first dialogue line so the shot remains voiced",
    )


# ---------------------------------------------------------------------------
# Dialogue extraction from screenplay format
# ---------------------------------------------------------------------------

_SCENE_HEADING_RE = re.compile(
    r"^(INT\.?|EXT\.?|INT\.\s*/\s*EXT\.?|EXT\.\s*/\s*INT\.?|CUT\s+TO:|FADE|SCENE|ACT|DISSOLVE|SMASH)",
    re.IGNORECASE,
)
_PARENTHETICAL_RE = re.compile(r"\(.*?\)")
_VOCATIVE_PUNCT = ".,!?:;"
_ACTION_PRONOUNS = ("HE ", "SHE ", "THEY ")

# Action-line openers that begin with "A (long )?<pause-noun>" — classic
# screenplay beat/pause directions ("A long beat.", "A long silence.",
# "A pause.", "A moment."). These are never spoken dialogue in this corpus.
# The noun set is deliberately curated so real dialogue like "A nightmare."
# (scene_013, DRE) is NOT flagged. A broad "The <noun> <verb>" rule is
# intentionally excluded: real dialogue starts that way in this corpus
# ("The nightmare showed me who we became.", "The kind you wake up from
# different.", "The first time the world ended, I lost everything.").
_ACTION_PAUSE_NOUNS = ("beat", "silence", "pause", "moment", "stillness", "breath")
_ACTION_PAUSE_OPENER_RE = re.compile(
    r"^A\s+(?:long\s+)?(" + "|".join(_ACTION_PAUSE_NOUNS) + r")\b",
    re.IGNORECASE,
)


def _is_scene_heading(line: str) -> bool:
    """Detect screenplay scene headings (INT./EXT./CUT TO:/FADE/SCENE/ACT/DISSOLVE/SMASH)."""
    return bool(_SCENE_HEADING_RE.match(line.strip()))


def _is_all_caps_section_header(line: str, known_characters: set[str] | None) -> bool:
    """Detect ALL-CAPS section headers that are NOT valid character cues.

    A real character cue reduces (after stripping V.O./CONT'D parentheticals) to
    a single token that matches a known character. A multi-word all-caps line with
    no parenthetical suffix is a section header (THE SECOND CHANCE, FINAL
    CONFRONTATION, MAYA AND HER MOM). A single-word all-caps line that is not a
    known character is also treated as a header (SUPPLIES, ENDING).
    """
    stripped = line.strip()
    without_parens = _PARENTHETICAL_RE.sub("", stripped).strip().rstrip(".")
    if not without_parens or not without_parens.replace(" ", "").replace("'", "").isalpha():
        return False
    if not without_parens.isupper():
        return False
    if known_characters and without_parens.upper() in known_characters:
        return False
    # Multi-word all-caps with no surviving parenthetical suffix = section header.
    if " " in without_parens:
        return True
    # Single-word all-caps not in the character list = likely a header (SUPPLIES).
    if known_characters:
        return True
    return False


def _is_action_line(line: str, known_characters: set[str] | None) -> bool:
    """Detect action/description lines that should end a dialogue block.

    Signals (high precision, designed not to clip vocative dialogue):
      * Starts with a known character name followed by a non-vocative word
        ("Maya is killed." -> action; "Maya. You're my people." -> vocative dialogue).
      * Starts with a third-person action pronoun (HE/SHE/THEY) followed by a word.
        (IT/WE/YOU/I are excluded because real dialogue starts with those in this
        corpus: "It remembers everything.", "We understand this is difficult.").
      * Opens with "A (long )?<pause-noun>" — a classic screenplay beat/pause
        direction ("A long beat.", "A long silence.", "A pause."). The noun set
        is curated (beat/silence/pause/moment/stillness/breath) so real dialogue
        like "A nightmare." (scene_013, DRE) is NOT flagged. A broad
        "The <noun> <verb>" rule is intentionally excluded because real dialogue
        starts that way in this corpus ("The nightmare showed me who we became.",
        "The kind you wake up from different.", "The first time the world
        ended, I lost everything.").
    """
    stripped = line.strip()
    if not stripped:
        return False
    first_word = stripped.split(None, 1)
    if not first_word:
        return False
    raw_first = first_word[0]
    rest = first_word[1] if len(first_word) > 1 else ""
    bare = raw_first.rstrip(_VOCATIVE_PUNCT)

    if known_characters:
        for name in known_characters:
            if bare.upper() == name.upper():
                if not rest:
                    return False
                # If the name had trailing vocative punctuation in the original
                # ("Maya." / "Maya,") it is a vocative address, not action.
                if len(raw_first) > len(bare):
                    return False
                # No trailing punct on the name: "Maya is killed." -> action.
                if rest[0] not in _VOCATIVE_PUNCT:
                    return True
                return False
    upper = stripped.upper()
    for pron in _ACTION_PRONOUNS:
        if upper.startswith(pron):
            tail = stripped[len(pron):].strip()
            if tail and not tail[0] in _VOCATIVE_PUNCT:
                return True
    # Screenplay beat/pause openers: "A long beat.", "A long silence.", "A pause."
    if _ACTION_PAUSE_OPENER_RE.match(stripped):
        return True
    return False


def _extract_dialogue_lines(
    scene_text: str,
    characters: List[str] | None = None,
) -> List[Dict[str, str]]:
    """
    Extract dialogue lines from screenplay-formatted text.

    Screenplay format:
        CHARACTER_NAME
        Dialogue line here.

        ANOTHER_CHARACTER
        Another line.

    Returns list of dicts with 'character' and 'text' keys.

    ``characters`` (optional) is the scene's known character list. When supplied,
    it is used to (a) reject false character cues that are actually ALL-CAPS
    section headers (SUPPLIES, FINAL CONFRONTATION) and (b) detect action/
    description lines that begin with a character name ("Maya is killed.") and
    should end the dialogue block rather than be absorbed as spoken text. Without
    it the parser falls back to structural terminators only (scene headings and
    multi-word ALL-CAPS headers), which is weaker but backward compatible.
    """
    if not scene_text:
        return []

    known: set[str] | None = (
        {re.sub(r"\s*\(.*?\)\s*", "", c).strip().upper() for c in characters if isinstance(c, str) and c.strip()}
        if characters
        else None
    )

    def _flush() -> None:
        nonlocal current_character, current_dialogue
        if current_character and current_dialogue:
            dialogue_lines.append({
                "character": current_character,
                "text": " ".join(current_dialogue).strip(),
            })
        current_character = None
        current_dialogue = []

    lines = scene_text.split("\n")
    dialogue_lines: List[Dict[str, str]] = []
    current_character: Optional[str] = None
    current_dialogue: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines (they end dialogue blocks)
        if not stripped:
            _flush()
            continue

        # Scene headings always terminate the current dialogue block.
        if _is_scene_heading(stripped):
            _flush()
            continue

        # ALL-CAPS section headers terminate the block and are never cues.
        if _is_all_caps_section_header(stripped, known):
            _flush()
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
        # When the character list is available, reject cues that are not known
        # characters (catches SUPPLIES, ENDING, IT RETURNS., etc.).
        if is_char_cue and known is not None:
            is_char_cue = clean.upper() in known

        if is_char_cue:
            # Save previous dialogue if any
            _flush()
            current_character = clean
            current_dialogue = []
        elif current_character:
            # Action/description line: ends the dialogue block, is NOT dialogue.
            if _is_action_line(stripped, known):
                _flush()
                continue
            # Skip parenthetical stage directions
            if stripped.startswith("(") and stripped.endswith(")"):
                continue
            # This is dialogue text
            current_dialogue.append(stripped)

    # Don't forget the last dialogue block
    _flush()

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
      1. Dialogue: CosyVoice/Qwen-TTS by default
      2. Score/Ambient/SFX: skipped unless explicitly configured
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

    @staticmethod
    def _skipped_score_ambient_result(track: str, provider: str = "none") -> Dict[str, Any]:
        return {
            "track": track,
            "status": TrackStatus.SKIPPED,
            "provider": provider,
            "file_path": None,
            "file_url": None,
            "advisory": "No score/ambient/SFX provider configured — stage skipped.",
        }

    def _dialogue_line_path(self, project_id: str, scene_id: str, line_idx: int) -> Path:
        return self._scene_dir(project_id, scene_id) / f"dialogue_line_{line_idx:03d}.wav"

    def _pre_supplied_shot_dialogue_path(
        self,
        project_id: str,
        scene_id: str,
        shot_id: str,
    ) -> Path | None:
        """Return a convention-based local dialogue file for *shot_id*, if present."""
        from app.services.scene_audio_source_service import SceneAudioSourceService
        return SceneAudioSourceService(self.output_base).supplied_path(project_id, scene_id, shot_id)

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
    # FFprobe media analysis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_media_duration(path: Path) -> float | None:
        """Probe media file duration in seconds via ffprobe. Returns None on failure."""
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return None
        cmd = [
            ffprobe_bin, "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            return None
        try:
            payload = json.loads(proc.stdout or "{}")
            duration = float((payload.get("format") or {}).get("duration") or 0.0)
            return duration if duration > 0 else None
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    @staticmethod
    def _probe_audio_info(path: Path) -> tuple[int, int] | None:
        """Probe audio sample_rate and channels via ffprobe.

        Returns (sample_rate, channels) or None if ffprobe fails.
        """
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return None
        cmd = [
            ffprobe_bin, "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "a:0",
            str(path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            return None
        try:
            payload = json.loads(proc.stdout or "{}")
            streams = payload.get("streams") or []
            if not streams:
                return None
            s = streams[0]
            return (int(s["sample_rate"]), int(s["channels"]))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    @staticmethod
    def _compute_aac_bitrate(sample_rate: int, channels: int) -> str:
        """Compute a sample-rate-aware AAC bitrate string (e.g. '48k').

        The previous code hardcoded 192k, which is impossible for mono 22050 Hz
        AAC — FFmpeg silently clamps it (observed: 94k actual for a 192k request
        on 22050 Hz mono).  We derive a bitrate proportional to the actual source
        bandwidth (~2 bits per Hz per channel), rounded to the nearest 32k and
        clamped to [48, 192]:

          mono 22050 Hz  →  48k   (was: 192k requested, 94k actual — clamped)
          mono 44100 Hz  →  96k
          stereo 44100   → 192k

        Bumping to stereo/44100 would be lossy upsampling with zero quality
        benefit since mix_audio_tracks already produces mono 22050 Hz.
        """
        raw_kbps = int(sample_rate * channels * 2 / 1000)
        rounded = max(48, min(192, ((raw_kbps + 16) // 32) * 32))
        return f"{rounded}k"

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

    # ------------------------------------------------------------------
    # ElevenLabs TTS dialogue generation (experimental, opt-in)
    # ------------------------------------------------------------------

    def _elevenlabs_api_call(self, text: str, voice_id: str) -> bytes:
        """Make a single ElevenLabs TTS API call and return raw audio bytes.

        Uses ``urllib.request`` to avoid adding a dependency.  Raises on
        any HTTP error so callers can implement their own fallback.
        """
        import urllib.request
        import urllib.error

        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            f"?output_format={ELEVENLABS_OUTPUT_FORMAT}"
        )
        body = json.dumps({
            "text": text,
            "model_id": ELEVENLABS_MODEL_ID,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        last_exc: Exception | None = None
        for attempt in range(ELEVENLABS_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=ELEVENLABS_TIMEOUT_SECONDS) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (401, 402, 403):
                    raise
                if exc.code == 429 and attempt < ELEVENLABS_MAX_RETRIES:
                    backoff = min(2 ** attempt, 10)
                    logger.warning(
                        "ELEVENLABS_RATE_LIMIT | attempt=%d | backoff=%ds", attempt + 1, backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < ELEVENLABS_MAX_RETRIES:
                    backoff = min(2 ** attempt, 10)
                    logger.warning(
                        "ELEVENLABS_NETWORK_ERROR | attempt=%d | backoff=%ds | error=%s",
                        attempt + 1, backoff, exc,
                    )
                    time.sleep(backoff)
                    continue
                raise
        raise RuntimeError(f"ElevenLabs API call exhausted retries: {last_exc}")

    def _fish_audio_api_call(
        self, text: str, voice_id: str, emotion_tag: str | None = None,
    ) -> bytes:
        """Make a single Fish Audio TTS API call and return raw audio bytes.

        Uses ``urllib.request`` to avoid adding a dependency, mirroring
        ``_elevenlabs_api_call``.  The model is set via the required
        ``model`` header.

        Emotion is expressed as inline tags in the text — not a structured
        API field.  The delimiter style depends on the model: S2 uses
        ``[brackets]``, S1 uses ``(parentheses)``.  When *emotion_tag* is
        provided it is prepended to the text with the correct delimiters.
        """
        import urllib.request
        import urllib.error

        open_delim, close_delim = _fish_audio_emotion_delimiters(FISH_AUDIO_MODEL)
        synthesized_text = (
            f"{open_delim}{emotion_tag}{close_delim} {text}"
            if emotion_tag
            else text
        )

        url = f"{FISH_AUDIO_API_BASE}/tts"
        body = json.dumps({
            "text": synthesized_text,
            "reference_id": voice_id,
            "format": FISH_AUDIO_OUTPUT_FORMAT,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {FISH_AUDIO_API_KEY}",
                "Content-Type": "application/json",
                "model": FISH_AUDIO_MODEL,
            },
            method="POST",
        )
        last_exc: Exception | None = None
        for attempt in range(FISH_AUDIO_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(
                    req, timeout=FISH_AUDIO_TIMEOUT_SECONDS,
                ) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (401, 402, 403):
                    raise
                if exc.code == 429 and attempt < FISH_AUDIO_MAX_RETRIES:
                    backoff = min(2 ** attempt, 10)
                    logger.warning(
                        "FISH_AUDIO_RATE_LIMIT | attempt=%d | backoff=%ds",
                        attempt + 1, backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < FISH_AUDIO_MAX_RETRIES:
                    backoff = min(2 ** attempt, 10)
                    logger.warning(
                        "FISH_AUDIO_NETWORK_ERROR | attempt=%d | backoff=%ds | error=%s",
                        attempt + 1, backoff, exc,
                    )
                    time.sleep(backoff)
                    continue
                raise
        raise RuntimeError(f"Fish Audio API call exhausted retries: {last_exc}")

    def _normalize_audio_to_wav(
        self,
        src: Path,
        dst: Path,
        trim_edge_silence: bool = False,
    ) -> None:
        """Normalise any audio file to PCM 16-bit mono 22050 Hz WAV via FFmpeg.

        This is the containment layer from the design doc — even if ElevenLabs
        returns MP3 or a higher-rate format, downstream sees the Piper-era
        WAV contract.
        """
        if not FFMPEG_AVAILABLE:
            raise RuntimeError("FFmpeg is required for ElevenLabs audio normalisation but is not available")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-ac", "1",
            "-ar", "22050",
            "-sample_fmt", "s16",
        ]
        if trim_edge_silence:
            cmd.extend(
                [
                    "-af",
                    (
                        "silenceremove="
                        "start_periods=1:start_duration=0.08:start_threshold=-45dB"
                    ),
                ]
            )
        cmd.append(str(dst))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg normalisation failed: {result.stderr[-500:]}"
            )

    def _generate_elevenlabs_tts_sync(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
        character: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Synchronous ElevenLabs TTS generation — runs in executor.

        Mirrors ``_generate_piper_tts_sync``: returns ``None``, leaves a valid
        WAV at *output_path* on success, raises on failure so callers can
        preserve their existing fallback behaviour.

        Respects the free-tier 2,500-character request cap: if *text* exceeds
        ``ELEVENLABS_CHAR_LIMIT``, it is split into multiple API calls and the
        resulting audio chunks are concatenated — never truncated.
        """
        if not ELEVENLABS_API_KEY:
            raise ValueError("ELEVENLABS_API_KEY is not set — cannot use ElevenLabs provider")

        voice_id = voice or _resolve_elevenlabs_voice_id(character, project_id=project_id)
        chunks = _split_text_for_elevenlabs(text, ELEVENLABS_CHAR_LIMIT)

        logger.info(
            "ELEVENLABS_TTS | voice=%s | model=%s | chars=%d | chunks=%d",
            voice_id, ELEVENLABS_MODEL_ID, len(text), len(chunks),
        )

        if len(chunks) == 1:
            audio_bytes = self._elevenlabs_api_call(chunks[0], voice_id)
            tmp_path = output_path.parent / f"{output_path.stem}_raw.mp3"
            try:
                tmp_path.write_bytes(audio_bytes)
                self._normalize_audio_to_wav(tmp_path, output_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            temp_wavs: list[Path] = []
            try:
                for idx, chunk in enumerate(chunks):
                    audio_bytes = self._elevenlabs_api_call(chunk, voice_id)
                    tmp_raw = output_path.parent / f"{output_path.stem}_chunk_{idx:03d}_raw.mp3"
                    tmp_wav = output_path.parent / f"{output_path.stem}_chunk_{idx:03d}.wav"
                    try:
                        tmp_raw.write_bytes(audio_bytes)
                        self._normalize_audio_to_wav(tmp_raw, tmp_wav)
                    finally:
                        tmp_raw.unlink(missing_ok=True)
                    temp_wavs.append(tmp_wav)

                self._concat_audio_files(temp_wavs, output_path)
            finally:
                for f in temp_wavs:
                    f.unlink(missing_ok=True)

        if not output_path.exists() or output_path.stat().st_size <= 44:
            raise ValueError(f"ElevenLabs TTS produced an empty or missing file: {output_path}")

    def _generate_fish_audio_tts_sync(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
        character: str | None = None,
        project_id: str | None = None,
        emotion_tag: str | None = None,
    ) -> None:
        """Synchronous Fish Audio TTS generation — runs in executor.

        Mirrors ``_generate_elevenlabs_tts_sync``: returns ``None``, leaves a
        valid WAV at *output_path* on success, raises on failure so callers
        can preserve their existing fallback behaviour.

        Fish Audio S2 models express emotion via inline ``[bracket]`` tags in
        the text (e.g. ``[angry] I told you not to come back here.``), not a
        structured API field.  When *emotion_tag* is provided it is prepended
        to the text.  Intensity is expressed via descriptive modifiers in the
        tag itself (``[very angry]``, ``[slightly sad]``) — there is no
        numeric intensity parameter in the API.
        """
        if not FISH_AUDIO_API_KEY:
            raise ValueError(
                "FISH_AUDIO_API_KEY is not set — cannot use Fish Audio provider"
            )

        voice_id = voice or _resolve_fish_audio_voice_id(
            character, project_id=project_id,
        )

        logger.info(
            "FISH_AUDIO_TTS | voice=%s | model=%s | chars=%d | emotion=%s",
            voice_id, FISH_AUDIO_MODEL, len(text), emotion_tag or "none",
        )

        audio_bytes = self._fish_audio_api_call(
            text, voice_id, emotion_tag=emotion_tag,
        )
        tmp_path = output_path.parent / f"{output_path.stem}_raw.{FISH_AUDIO_OUTPUT_FORMAT}"
        try:
            tmp_path.write_bytes(audio_bytes)
            self._normalize_audio_to_wav(tmp_path, output_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        if not output_path.exists() or output_path.stat().st_size <= 44:
            raise ValueError(
                f"Fish Audio TTS produced an empty or missing file: {output_path}"
            )

    def _generate_cosyvoice_tts_sync(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
        character: str | None = None,
        project_id: str | None = None,
        instruction: str | None = None,
    ) -> None:
        """Synchronous CosyVoice/Qwen-TTS dialogue generation."""
        if not COSYVOICE_CONFIGURED:
            raise ValueError(
                "DASHSCOPE_API_KEY is not set — cannot use CosyVoice provider"
            )

        from app.services.audio.cosyvoice_tts_service import CosyVoiceTTSService

        voice_id = voice or _resolve_cosyvoice_voice_id(
            character, project_id=project_id,
        )
        logger.info(
            "COSYVOICE_TTS | voice=%s | model=%s | chars=%d | instruction=%s",
            voice_id, COSYVOICE_MODEL, len(text), "yes" if instruction else "none",
        )

        service = CosyVoiceTTSService(model=COSYVOICE_MODEL)
        tmp_path = output_path.parent / f"{output_path.stem}_raw.{COSYVOICE_OUTPUT_FORMAT}"
        try:
            service.synthesize_dialogue(
                text=text,
                voice=voice_id,
                output_path=tmp_path,
                instruction=instruction,
            )
            self._normalize_audio_to_wav(tmp_path, output_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        if not output_path.exists() or output_path.stat().st_size <= 44:
            raise ValueError(
                f"CosyVoice TTS produced an empty or missing file: {output_path}"
            )

    def _generate_ace_step_sync(
        self,
        prompt: str,
        output_path: Path,
        duration_seconds: float = 10.0,
    ) -> None:
        """Generate a combined score/ambient bed through ACE Step.

        ACE Step's dependency set conflicts with portions of the backend ML
        stack, so generation runs in a child process with the isolated runtime
        site prepended to ``PYTHONPATH``.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        script = """
import os
import sys
from pathlib import Path

from acestep.pipeline_ace_step import ACEStepPipeline

prompt = sys.argv[1]
output_path = Path(sys.argv[2])
duration = float(sys.argv[3])
infer_steps = int(sys.argv[4])
guidance_scale = float(sys.argv[5])
checkpoint_path = sys.argv[6] or None
dtype = sys.argv[7]
cpu_offload = sys.argv[8].lower() == "true"

output_path.parent.mkdir(parents=True, exist_ok=True)
if output_path.exists():
    output_path.unlink()

pipeline = ACEStepPipeline(
    checkpoint_dir=checkpoint_path,
    dtype=dtype,
    cpu_offload=cpu_offload,
    overlapped_decode=False,
)
result = pipeline(
    format="wav",
    audio_duration=duration,
    prompt=prompt,
    lyrics="",
    infer_step=infer_steps,
    guidance_scale=guidance_scale,
    save_path=str(output_path),
    batch_size=1,
)
if not output_path.exists():
    for item in result:
        if isinstance(item, str) and item.endswith(".wav") and Path(item).exists():
            Path(item).replace(output_path)
            break
if not output_path.exists():
    raise RuntimeError(f"ACE Step did not create expected output: {output_path}")
if output_path.stat().st_size <= 44:
    raise RuntimeError(f"ACE Step created an empty output: {output_path}")
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
"""
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        pythonpath_parts = []
        if ACE_STEP_RUNTIME_SITE.exists():
            pythonpath_parts.append(str(ACE_STEP_RUNTIME_SITE))
        if existing_pythonpath:
            pythonpath_parts.append(existing_pythonpath)
        if pythonpath_parts:
            env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

        cmd = [
            sys.executable,
            "-c",
            script,
            prompt,
            str(output_path),
            f"{max(1.0, duration_seconds):.3f}",
            str(max(1, ACE_STEP_INFER_STEPS)),
            str(ACE_STEP_GUIDANCE_SCALE),
            ACE_STEP_CHECKPOINT_PATH,
            ACE_STEP_DTYPE,
            "true" if ACE_STEP_CPU_OFFLOAD else "false",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ACE_STEP_TIMEOUT_SECONDS,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "ACE Step generation failed: "
                f"{(result.stderr or result.stdout)[-1000:]}"
            )

        if not output_path.exists() or output_path.stat().st_size <= 44:
            raise ValueError(f"ACE Step produced an empty or missing file: {output_path}")

    def _concat_audio_files(self, input_files: list[Path], output_path: Path) -> None:
        """Concatenate multiple WAV files into one using FFmpeg."""
        if not FFMPEG_AVAILABLE:
            raise RuntimeError("FFmpeg is required for audio concatenation but is not available")
        concat_file = output_path.parent / f"{output_path.stem}_concat_list.txt"
        try:
            with open(concat_file, "w") as f:
                for path in input_files:
                    if path.exists():
                        f.write(f"file '{path}'\n")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-500:]}")
        finally:
            concat_file.unlink(missing_ok=True)

    def _generate_dialogue_tts_sync(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
        character: str | None = None,
        provider: str | None = None,
        project_id: str | None = None,
        emotion_tag: str | None = None,
        instruction: str | None = None,
    ) -> None:
        """Dispatch to the configured dialogue TTS provider.

        This is the single point of provider selection, mirroring the
        ``_generate_music_with_open_provider`` pattern in
        ``audio_generation_service``.  When ``elevenlabs`` is selected and
        fails, behaviour depends on ``ELEVENLABS_FAILOVER_TO_PIPER``:

        - ``True``  → silently fall back to Piper (dev/local mode).
        - ``False`` → re-raise so the caller writes silence (production/review).

        For ``auto``, ElevenLabs is used when configured (API key present),
        then CosyVoice when DashScope is configured, otherwise Piper.

        *emotion_tag* is forwarded to providers that support emotional
        expression (currently Fish Audio).  It is ``None`` by default —
        the existing call sites in ``generate_dialogue`` and
        ``generate_shot_dialogue`` do not pass it yet.  Upstream emotion
        resolution (from scene/character data) is wired by the casting
        service in a separate session.
        """
        resolved = _normalize_dialogue_provider(provider)

        if resolved == "auto":
            if ELEVENLABS_CONFIGURED:
                resolved = "elevenlabs"
            elif COSYVOICE_CONFIGURED:
                resolved = "cosyvoice"
            else:
                resolved = "piper"

        if resolved == "elevenlabs":
            try:
                self._generate_elevenlabs_tts_sync(
                    text, output_path,
                    voice=voice, character=character, project_id=project_id,
                )
                return
            except Exception as exc:
                if ELEVENLABS_FAILOVER_TO_PIPER and PIPER_AVAILABLE:
                    logger.warning(
                        "ELEVENLABS_FAILOVER | error=%s | falling back to Piper", exc,
                    )
                    self._generate_piper_tts_sync(text, output_path, voice=voice)
                    return
                raise

        if resolved == "cosyvoice":
            try:
                self._generate_cosyvoice_tts_sync(
                    text, output_path,
                    voice=voice, character=character, project_id=project_id,
                    instruction=instruction,
                )
                return
            except Exception as exc:
                if COSYVOICE_FAILOVER_TO_PIPER and PIPER_AVAILABLE:
                    logger.warning(
                        "COSYVOICE_FAILOVER | error=%s | falling back to Piper", exc,
                    )
                    self._generate_piper_tts_sync(text, output_path, voice=voice)
                    return
                raise

        if resolved == "fish_audio":
            try:
                self._generate_fish_audio_tts_sync(
                    text, output_path,
                    voice=voice, character=character, project_id=project_id,
                    emotion_tag=emotion_tag,
                )
                return
            except Exception as exc:
                if FISH_AUDIO_FAILOVER_TO_PIPER and PIPER_AVAILABLE:
                    logger.warning(
                        "FISH_AUDIO_FAILOVER | error=%s | falling back to Piper", exc,
                    )
                    self._generate_piper_tts_sync(text, output_path, voice=voice)
                    return
                raise

        self._generate_piper_tts_sync(text, output_path, voice=voice)

    async def generate_dialogue(
        self,
        scene_id: str,
        project_id: str,
        scene_text: str,
        provider: str | None = None,
        characters: list[str] | None = None,
        dialogue_lines: list[dict[str, str]] | None = None,
        max_duration_seconds: float | None = None,
        scene_context: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Generate dialogue track using the configured dialogue TTS provider.

        Provider selection follows the same pattern as ``AUDIO_SCORE_PROVIDER``:
        ``AUDIO_DIALOGUE_PROVIDER`` (or ``DIALOGUE_TTS_PROVIDER``) env var
        selects ``cosyvoice`` (default), ``piper``, ``elevenlabs``, ``fish_audio``,
        ``cosyvoice``, or ``auto``.  The *provider* parameter overrides the
        env var per-call.
        """
        out_path = self._track_path(project_id, scene_id, "dialogue")
        resolved_provider = _normalize_dialogue_provider(provider)

        if MOCK_MODE:
            _write_silence_wav(out_path, duration_seconds=3.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.MOCK,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Mock mode — Piper TTS not available. Install with: pip install piper-tts",
            }

        # Extract dialogue lines from scene text
        dialogue_lines = (
            [
                d
                for d in dialogue_lines
                if isinstance(d, dict)
                and isinstance(d.get("text"), str)
                and d.get("text", "").strip()
            ]
            if isinstance(dialogue_lines, list)
            else _extract_dialogue_lines(scene_text, characters=characters)
        )
        selection_reason = "all resolved scene dialogue lines used"
        if max_duration_seconds is not None:
            dialogue_lines, selection_reason = _select_dialogue_lines_for_video_duration(
                dialogue_lines, max_duration_seconds,
            )
        
        if not dialogue_lines:
            _write_silence_wav(out_path, duration_seconds=2.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.SKIPPED,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "No dialogue detected in scene — silence written.",
                "lines_found": 0,
                "selection_reason": selection_reason,
            }

        logger.info(
            "DIALOGUE_EXTRACTION | scene=%s | lines=%d | characters=%s",
            scene_id,
            len(dialogue_lines),
            list(set(d["character"] for d in dialogue_lines)),
        )

        # Generate each dialogue line
        line_files: List[Path] = []
        line_errors: list[dict[str, Any]] = []
        line_instructions: list[dict[str, Any]] = []
        for idx, line in enumerate(dialogue_lines):
            line_path = self._dialogue_line_path(project_id, scene_id, idx)
            voice_id = (
                _resolve_cosyvoice_voice_id(line.get("character"), project_id=project_id)
                if resolved_provider == "cosyvoice"
                else None
            )
            instruction, instruction_mode = (
                _build_dialogue_instruction(
                    line,
                    model=COSYVOICE_MODEL,
                    voice=voice_id or COSYVOICE_DEFAULT_VOICE,
                    scene_context=scene_context,
                )
                if resolved_provider == "cosyvoice"
                else (None, "none")
            )
            line_instructions.append({
                "line": idx,
                "character": line.get("character"),
                "text": line.get("text"),
                "tts_text": _dialogue_tts_text(line),
                "performance_direction": _dialogue_performance_direction(
                    line,
                    scene_context,
                ),
                "voice": voice_id,
                "model": COSYVOICE_MODEL if resolved_provider == "cosyvoice" else None,
                "instruction_mode": instruction_mode,
                "instruction": instruction,
                "instruction_sources": (
                    _dialogue_instruction_sources(line, scene_context)
                    if resolved_provider == "cosyvoice"
                    else {}
                ),
            })
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda t=_dialogue_tts_text(line), p=line_path, c=line.get("character"), v=voice_id, i=instruction: (
                        self._generate_dialogue_tts_sync(
                            t,
                            p,
                            voice=v,
                            character=c,
                            provider=provider,
                            project_id=project_id,
                            instruction=i,
                        )
                    ),
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
                line_errors.append({
                    "line": idx,
                    "character": line.get("character"),
                    "error": str(exc),
                })

        # Concatenate dialogue lines with silence gaps
        try:
            await self._concatenate_dialogue_lines(line_files, out_path, gap_seconds=0.3)
            status = (
                TrackStatus.FAILED
                if line_errors and resolved_provider != "piper"
                else TrackStatus.COMPLETE
            )
            return {
                "track": "dialogue",
                "status": status,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "lines_generated": len(line_files),
                "line_errors": line_errors,
                "line_instructions": line_instructions,
                "characters": list(set(d["character"] for d in dialogue_lines)),
                "selection_reason": selection_reason,
                "advisory": f"Dialogue rendered via {resolved_provider} ({len(line_files)} lines).",
            }
        except Exception as exc:
            logger.error("Dialogue concatenation failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=2.0)
            return {
                "track": "dialogue",
                "status": TrackStatus.FAILED,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "Dialogue concatenation failed — silence written as fallback.",
            }

    async def generate_shot_dialogue(
        self,
        project_id: str,
        scene_id: str,
        shot_id: str,
        scene_text: str = "",
        dialogue_lines: list[dict[str, str]] | None = None,
        dialogue_line_range: dict[str, int] | None = None,
        characters: list[str] | None = None,
        split_reason: str | None = None,
        provider: str | None = None,
        scene_context: dict[str, Any] | None = None,
        allow_generation: bool = True,
    ) -> Dict[str, Any]:
        """Resolve or generate a single shot's dialogue WAV.

        This is the per-shot analogue of :meth:`generate_dialogue`.  It reuses
        the same TTS primitives (``_generate_dialogue_tts_sync`` +
        ``_concatenate_dialogue_lines``) but operates on *one shot's* lines
        rather than re-extracting the whole scene.

        Audio source resolution order:

        1. A pre-supplied local file named ``<shot_id>.<ext>`` under
           ``outputs/audio/<project_id>/<scene_id>/pre_supplied/``. Supported
           extensions are WAV, MP3, M4A, FLAC, OGG, and AAC. The file is
           normalized to the pipeline's PCM WAV contract without calling a
           dialogue provider.

        2. Live provider synthesis from the resolved dialogue text below.

        Resolution order for the dialogue text (PER_SHOT_AUDIO_DESIGN §2.1):

        1. ``dialogue_lines`` — the shot's own ``[{character, text}, ...]``
           list persisted on the render job's ``input_payload.parameters``.
           This is the preferred, deterministic source (Tier 1 guarantees it
           for auto-split jobs) and disambiguates monologue-split sub-shots
           that share a line index.

        2. Fallback: re-extract the full scene's lines via
           ``_extract_dialogue_lines(scene_text, characters)`` and slice
           ``dialogue_line_range`` (inclusive ``end``).  This is ONLY safe for
           non-monologue shots — monologue sub-shots share a line index, so a
           range-slice would hand the full original line to every sub-shot
           (§1.2).  When ``split_reason == "vo_monologue_split"`` the fallback
           refuses and degrades to video-only.

        Edge cases (§7.1 / §7.2) — this method **never raises**:

        * Zero-dialogue / nothing resolvable → ``status=SKIPPED``,
          ``file_path=None``.  The orchestrator passes the raw video through
          unbaked (no merge, no silent audio track).
        * Malformed ``dialogue_line_range`` (non-int start/end, start > end)
          → ``SKIPPED``.
        * MOCK_MODE (no Piper/torch) → writes per-shot silence WAVs and
          returns ``status=MOCK`` with ``file_path`` set, so the orchestrator
          bakes it and the pipeline shape stays identical across modes (§7.7).

        Returns a dict shaped::

            {
                "track": "shot_dialogue",
                "status": COMPLETE | SKIPPED | MOCK | FAILED,
                "source": "pre_supplied" | "live_provider" | "mock" | "none",
                "file_path": str | None,
                "file_url": str | None,
                "lines_generated": int,
                "shot_id": shot_id,
                "advisory": str,
            }
        """
        scene_dir = self._scene_dir(project_id, scene_id)
        out_path = scene_dir / f"{shot_id}_dialogue.wav"
        resolved_provider = _normalize_dialogue_provider(provider)
        pre_supplied_path = self._pre_supplied_shot_dialogue_path(
            project_id,
            scene_id,
            shot_id,
        )

        if pre_supplied_path is not None:
            logger.info(
                "SHOT_DIALOGUE_SOURCE | project_id=%s | scene_id=%s | shot_id=%s "
                "| provider=%s | source=pre_supplied | source_path=%s",
                project_id,
                scene_id,
                shot_id,
                resolved_provider,
                pre_supplied_path,
            )
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self._normalize_audio_to_wav,
                    pre_supplied_path,
                    out_path,
                    True,
                )
                if not out_path.exists() or out_path.stat().st_size <= 44:
                    raise ValueError("normalized audio is empty")
            except Exception as exc:
                logger.error(
                    "SHOT_DIALOGUE_PRE_SUPPLIED_FAILED | project_id=%s | scene_id=%s "
                    "| shot_id=%s | source_path=%s | error=%s",
                    project_id,
                    scene_id,
                    shot_id,
                    pre_supplied_path,
                    exc,
                )
                return {
                    "track": "shot_dialogue",
                    "status": TrackStatus.FAILED,
                    "provider": resolved_provider,
                    "source": "pre_supplied",
                    "source_path": str(pre_supplied_path),
                    "file_path": None,
                    "file_url": None,
                    "lines_generated": 0,
                    "shot_id": shot_id,
                    "error": str(exc),
                    "advisory": (
                        f"Pre-supplied dialogue for {shot_id} could not be normalized; "
                        "the live provider was not called."
                    ),
                }
            return {
                "track": "shot_dialogue",
                "status": TrackStatus.COMPLETE,
                "provider": resolved_provider,
                "source": "pre_supplied",
                "source_path": str(pre_supplied_path),
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "lines_generated": len(dialogue_lines or []),
                "line_errors": [],
                "line_instructions": [],
                "shot_id": shot_id,
                "advisory": f"Pre-supplied local dialogue used for {shot_id}.",
            }

        if not allow_generation:
            return {
                "track": "shot_dialogue", "status": TrackStatus.SKIPPED,
                "provider": "none", "source": "none", "file_path": None,
                "file_url": None, "lines_generated": 0, "shot_id": shot_id,
                "advisory": "Existing-media assembly: no new dialogue generated. Audio already in the take is retained.",
            }

        generation_source = "mock" if MOCK_MODE else "live_provider"
        logger.info(
            "SHOT_DIALOGUE_SOURCE | project_id=%s | scene_id=%s | shot_id=%s "
            "| provider=%s | source=%s",
            project_id,
            scene_id,
            shot_id,
            resolved_provider,
            generation_source,
        )

        def _skipped(reason: str) -> Dict[str, Any]:
            logger.info("SHOT_DIALOGUE_SKIP | shot=%s | reason=%s", shot_id, reason)
            return {
                "track": "shot_dialogue",
                "status": TrackStatus.SKIPPED,
                "provider": resolved_provider,
                "source": "none",
                "file_path": None,
                "file_url": None,
                "lines_generated": 0,
                "shot_id": shot_id,
                "advisory": f"No dialogue baked for {shot_id} — {reason}.",
            }

        # ── 1. Resolve the dialogue lines for this shot ──────────────────
        lines: List[Dict[str, str]] = []

        # Preferred: the shot's own persisted dialogue_lines.
        if isinstance(dialogue_lines, list):
            lines = [
                d
                for d in dialogue_lines
                if isinstance(d, dict)
                and isinstance(d.get("text"), str)
                and d.get("text", "").strip()
            ]

        # Fallback: range-slice from re-extracted scene lines — only when the
        # preferred list is empty AND a range is available AND this is not a
        # monologue split (range is ambiguous for monologue sub-shots, §1.2).
        if dialogue_lines is None and scene_text and isinstance(dialogue_line_range, dict):
            if split_reason == "vo_monologue_split":
                return _skipped(
                    "monologue split without dialogue_lines — range-slice "
                    "ambiguous, degrading to video-only"
                )
            start = dialogue_line_range.get("start")
            end = dialogue_line_range.get("end")
            if not (isinstance(start, int) and isinstance(end, int) and 0 <= start <= end):
                return _skipped(f"malformed dialogue_line_range {dialogue_line_range!r}")
            all_lines = _extract_dialogue_lines(scene_text, characters=characters)
            sliced = all_lines[start : end + 1]  # end is inclusive
            lines = [
                d
                for d in sliced
                if isinstance(d, dict)
                and isinstance(d.get("text"), str)
                and d.get("text", "").strip()
            ]

        # Zero-dialogue / action-only shot → SKIPPED, pass video through.
        if not lines:
            return _skipped("no dialogue lines resolved for this shot")

        # ── 2. Generate one TTS WAV per line (reuses existing primitive) ──
        line_files: List[Path] = []
        line_errors: list[dict[str, Any]] = []
        line_instructions: list[dict[str, Any]] = []
        for idx, line in enumerate(lines):
            line_path = scene_dir / f"{shot_id}_line_{idx:03d}.wav"
            voice_id = (
                _resolve_cosyvoice_voice_id(line.get("character"), project_id=project_id)
                if resolved_provider == "cosyvoice"
                else None
            )
            instruction, instruction_mode = (
                _build_dialogue_instruction(
                    line,
                    model=COSYVOICE_MODEL,
                    voice=voice_id or COSYVOICE_DEFAULT_VOICE,
                    scene_context=scene_context,
                )
                if resolved_provider == "cosyvoice"
                else (None, "none")
            )
            line_instructions.append({
                "line": idx,
                "character": line.get("character"),
                "text": line.get("text"),
                "tts_text": _dialogue_tts_text(line),
                "performance_direction": _dialogue_performance_direction(
                    line,
                    scene_context,
                ),
                "voice": voice_id,
                "model": COSYVOICE_MODEL if resolved_provider == "cosyvoice" else None,
                "instruction_mode": instruction_mode,
                "instruction": instruction,
                "instruction_sources": (
                    _dialogue_instruction_sources(line, scene_context)
                    if resolved_provider == "cosyvoice"
                    else {}
                ),
            })
            try:
                if MOCK_MODE:
                    _write_silence_wav(line_path, duration_seconds=1.0)
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda t=_dialogue_tts_text(line), p=line_path, c=line.get("character"), v=voice_id, i=instruction: (
                            self._generate_dialogue_tts_sync(
                                t,
                                p,
                                voice=v,
                                character=c,
                                provider=provider,
                                project_id=project_id,
                                instruction=i,
                            )
                        ),
                    )
                line_files.append(line_path)
            except Exception as exc:
                logger.error(
                    "SHOT_DIALOGUE_LINE_FAILED | shot=%s | line=%d | error=%s",
                    shot_id, idx, exc,
                )
                # Match the scene-level behaviour: silence for a failed line,
                # keep going so one bad line never blocks the shot.
                _write_silence_wav(line_path, duration_seconds=1.0)
                line_files.append(line_path)
                line_errors.append({
                    "line": idx,
                    "character": line.get("character"),
                    "error": str(exc),
                })

        # ── 3. Concatenate the line WAVs into one shot-level dialogue WAV ──
        try:
            await self._concatenate_dialogue_lines(line_files, out_path, gap_seconds=0.3)
        except Exception as exc:
            logger.error("SHOT_DIALOGUE_CONCAT_FAILED | shot=%s | error=%s", shot_id, exc)
            # Silence fallback so the orchestrator can still bake (harmless).
            _write_silence_wav(out_path, duration_seconds=2.0)
            return {
                "track": "shot_dialogue",
                "status": TrackStatus.FAILED,
                "provider": resolved_provider,
                "source": generation_source,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "lines_generated": len(line_files),
                "shot_id": shot_id,
                "line_instructions": line_instructions,
                "advisory": "Shot dialogue concat failed — silence written as fallback.",
            }

        status = (
            TrackStatus.MOCK
            if MOCK_MODE
            else TrackStatus.FAILED if line_errors and resolved_provider != "piper"
            else TrackStatus.COMPLETE
        )
        advisory = (
            f"Mock mode — silence written for {len(line_files)} shot dialogue line(s)."
            if MOCK_MODE
            else f"Shot dialogue rendered via {resolved_provider} ({len(line_files)} line(s))."
        )
        logger.info(
            "SHOT_DIALOGUE_GENERATED | shot=%s | lines=%d | status=%s",
            shot_id, len(line_files), status,
        )
        return {
            "track": "shot_dialogue",
            "status": status,
            "provider": resolved_provider,
            "source": generation_source,
            "file_path": str(out_path),
            "file_url": self._file_url(out_path),
            "lines_generated": len(line_files),
            "line_errors": line_errors,
            "line_instructions": line_instructions,
            "shot_id": shot_id,
            "advisory": advisory,
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
    # Score/ambient generation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_score_ambient_prompt(
        mood: str = "",
        score_notes: str = "",
        ambient_notes: str = "",
        instrumentation: str = "",
        tempo: str = "",
    ) -> str:
        prompt_parts = []
        if mood:
            prompt_parts.append(mood)
        if score_notes:
            prompt_parts.append(score_notes)
        if ambient_notes:
            prompt_parts.append(ambient_notes)
        if instrumentation:
            prompt_parts.append(instrumentation)
        if tempo:
            prompt_parts.append(f"{tempo} tempo")
        prompt_parts.append(
            "instrumental cinematic score and subtle room-tone ambience, no vocals"
        )
        return ", ".join(p for p in prompt_parts if p)

    async def generate_score_ambient(
        self,
        scene_id: str,
        project_id: str,
        mood: str,
        score_notes: str,
        ambient_notes: str = "",
        instrumentation: str = "",
        tempo: str = "",
        silence_flag: bool = False,
        duration_seconds: float = 15.0,
        provider: str | None = None,
    ) -> Dict[str, Any]:
        """Generate one combined score/ambient bed when a provider is configured."""
        resolved_provider = _normalize_score_ambient_provider(provider)
        out_path = self._track_path(project_id, scene_id, "score")

        if resolved_provider == "none":
            return self._skipped_score_ambient_result("score_ambient", resolved_provider)

        if silence_flag:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "score_ambient",
                "status": TrackStatus.SKIPPED,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Silence flag set — intentional silence for this scene.",
            }

        if resolved_provider == "musicgen":
            return await self.generate_score(
                scene_id=scene_id,
                project_id=project_id,
                mood=mood,
                score_notes=score_notes,
                instrumentation=instrumentation,
                tempo=tempo,
                silence_flag=silence_flag,
                duration_seconds=duration_seconds,
                provider="musicgen",
            )

        prompt = self._build_score_ambient_prompt(
            mood=mood,
            score_notes=score_notes,
            ambient_notes=ambient_notes,
            instrumentation=instrumentation,
            tempo=tempo,
        )
        logger.info(
            "ACE_STEP_SCORE_AMBIENT | scene=%s | prompt=%s | duration=%ss",
            scene_id, prompt[:120], duration_seconds,
        )
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._generate_ace_step_sync(prompt, out_path, duration_seconds),
            )
            return {
                "track": "score_ambient",
                "status": TrackStatus.COMPLETE,
                "provider": "ace_step",
                "model": ACE_STEP_MODEL,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "prompt_used": prompt,
                "duration_seconds": duration_seconds,
                "advisory": f"Score/ambient rendered via ACE Step ({duration_seconds}s).",
            }
        except Exception as exc:
            logger.error("ACE Step score/ambient failed for scene %s: %s", scene_id, exc)
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "score_ambient",
                "status": TrackStatus.FAILED,
                "provider": "ace_step",
                "model": ACE_STEP_MODEL,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "error": str(exc),
                "advisory": "ACE Step score/ambient failed — silence written as fallback.",
            }

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
        provider: str | None = None,
    ) -> Dict[str, Any]:
        """Generate score track using the selected score/ambient provider."""
        resolved_provider = _normalize_score_ambient_provider(provider)
        if resolved_provider == "none":
            return self._skipped_score_ambient_result("score", resolved_provider)

        if resolved_provider == "ace_step":
            return await self.generate_score_ambient(
                scene_id=scene_id,
                project_id=project_id,
                mood=mood,
                score_notes=score_notes,
                ambient_notes="",
                instrumentation=instrumentation,
                tempo=tempo,
                silence_flag=silence_flag,
                duration_seconds=duration_seconds,
                provider="ace_step",
            )

        out_path = self._track_path(project_id, scene_id, "score")

        if silence_flag:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "score",
                "status": TrackStatus.SKIPPED,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Silence flag set — intentional silence for this scene.",
            }

        if MOCK_MODE or not MUSICGEN_AVAILABLE:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "score",
                "status": TrackStatus.MOCK,
                "provider": resolved_provider,
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
                "provider": resolved_provider,
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
                "provider": resolved_provider,
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
        provider: str | None = None,
    ) -> Dict[str, Any]:
        """Generate ambient track using the selected score/ambient provider."""
        resolved_provider = _normalize_score_ambient_provider(provider)
        if resolved_provider == "none":
            return self._skipped_score_ambient_result("ambient", resolved_provider)

        if resolved_provider == "ace_step":
            return await self.generate_score_ambient(
                scene_id=scene_id,
                project_id=project_id,
                mood="",
                score_notes="",
                ambient_notes=ambient_notes,
                silence_flag=silence_flag,
                duration_seconds=duration_seconds,
                provider="ace_step",
            )

        out_path = self._track_path(project_id, scene_id, "ambient")

        if silence_flag:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "ambient",
                "status": TrackStatus.SKIPPED,
                "provider": resolved_provider,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "advisory": "Silence flag set — intentional silence for this scene.",
            }

        if MOCK_MODE or not MUSICGEN_AVAILABLE:
            _write_silence_wav(out_path, duration_seconds=duration_seconds)
            return {
                "track": "ambient",
                "status": TrackStatus.MOCK,
                "provider": resolved_provider,
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
                "provider": resolved_provider,
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
                "provider": resolved_provider,
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
        score_path: Path | None = None,
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
        if score_path and score_path.exists():
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
        if score_path and score_path.exists():
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
        on_audio_overrun: str = "error",
    ) -> Dict[str, Any]:
        """
        Merge mixed audio onto rendered video clip using FFmpeg.

        If replace_original is True, overwrites the original video file.
        Otherwise, saves alongside with '_audio' suffix.

        on_audio_overrun controls behaviour when audio duration exceeds video
        duration (the normal case when dialogue is longer than the rendered
        clip):

          "error"           — Fail loudly. Report both durations. Do NOT
                              silently truncate or freeze.  (Default — safe
                              until a product decision is made.)

          "freeze_last_frame" — Extend the video by cloning the last frame for
                                the overrun duration using tpad, then merge the
                                full audio.  Re-encodes video (libx264) because
                                filters require re-encoding.

          "trim_audio"      — Not yet implemented.  Returns a clear error so
                              the config surface exists but the behaviour is
                              deferred until trim semantics are decided.
        """
        valid_modes = {"error", "freeze_last_frame", "trim_audio"}
        if on_audio_overrun not in valid_modes:
            raise ValueError(
                f"on_audio_overrun must be one of {sorted(valid_modes)}, "
                f"got '{on_audio_overrun}'"
            )

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

        # ------------------------------------------------------------------
        # Probe durations and audio info before building the command
        # ------------------------------------------------------------------
        video_dur = self._probe_media_duration(video_path)
        audio_dur = self._probe_media_duration(audio_path)
        audio_info = self._probe_audio_info(audio_path)

        # Compute sample-rate-aware AAC bitrate instead of hardcoded 192k.
        # 192k is impossible for mono 22050 Hz AAC — FFmpeg silently clamps it.
        if audio_info:
            sample_rate, channels = audio_info
        else:
            sample_rate, channels = 22050, 1
        bitrate = self._compute_aac_bitrate(sample_rate, channels)

        logger.info(
            "VIDEO_AUDIO_MERGE | scene=%s | video=%s | audio=%s | replace=%s | "
            "video_dur=%s | audio_dur=%s | audio_sr=%d | audio_ch=%d | "
            "bitrate=%s | on_audio_overrun=%s",
            scene_id, video_path.name, audio_path.name, replace_original,
            f"{video_dur:.3f}" if video_dur else "N/A",
            f"{audio_dur:.3f}" if audio_dur else "N/A",
            sample_rate, channels, bitrate, on_audio_overrun,
        )

        # ------------------------------------------------------------------
        # Detect audio overrun: audio longer than video
        # ------------------------------------------------------------------
        audio_overrun = (
            video_dur is not None
            and audio_dur is not None
            and audio_dur > video_dur
        )

        if audio_overrun:
            overrun_seconds = audio_dur - video_dur
            logger.warning(
                "AUDIO_OVERRUN_DETECTED | scene=%s | video_dur=%.3fs | "
                "audio_dur=%.3fs | overrun=%.3fs | mode=%s",
                scene_id, video_dur, audio_dur, overrun_seconds, on_audio_overrun,
            )

            if on_audio_overrun == "error":
                return {
                    "track": "final_video",
                    "status": TrackStatus.FAILED,
                    "file_path": str(video_path),
                    "error": (
                        f"Audio duration ({audio_dur:.2f}s) exceeds video "
                        f"duration ({video_dur:.2f}s) by {overrun_seconds:.2f}s. "
                        f"on_audio_overrun='error' — refusing to silently "
                        f"truncate dialogue. Use 'freeze_last_frame' to extend "
                        f"the video with a cloned last frame, or 'trim_audio' "
                        f"(not yet implemented)."
                    ),
                    "advisory": (
                        "Audio overrun detected — merge aborted to prevent "
                        "silent dialogue truncation."
                    ),
                    "video_duration": video_dur,
                    "audio_duration": audio_dur,
                    "overrun_seconds": overrun_seconds,
                    "on_audio_overrun": on_audio_overrun,
                }

            if on_audio_overrun == "trim_audio":
                return {
                    "track": "final_video",
                    "status": TrackStatus.FAILED,
                    "file_path": str(video_path),
                    "error": (
                        f"on_audio_overrun='trim_audio' is not yet implemented. "
                        f"Audio ({audio_dur:.2f}s) exceeds video "
                        f"({video_dur:.2f}s) by {overrun_seconds:.2f}s. "
                        f"Trimming dialogue is lossy — awaiting decision on "
                        f"trim semantics before implementation."
                    ),
                    "advisory": "trim_audio mode not implemented — merge aborted.",
                    "video_duration": video_dur,
                    "audio_duration": audio_dur,
                    "overrun_seconds": overrun_seconds,
                    "on_audio_overrun": on_audio_overrun,
                }

            # on_audio_overrun == "freeze_last_frame"
            # Extend video by cloning the last frame for the overrun duration
            # using tpad, then merge full audio.  This requires re-encoding
            # the video stream (libx264) because -c:v copy is incompatible
            # with filter_complex.  No -shortest: the tpad makes video match
            # audio duration, so both streams end together.
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-filter_complex",
                f"[0:v]tpad=stop_mode=clone:stop_duration={overrun_seconds:.6f}[vout]",
                "-map", "[vout]",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", bitrate,
                "-pix_fmt", "yuv420p",
                str(temp_path if temp_path else out_path),
            ]
        else:
            # Normal case: audio fits within video (or durations unknown).
            # Use -c:v copy (fast, lossless) and preserve the rendered video
            # duration; the audio stream may end before the picture.
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", bitrate,
                "-map", "0:v:0",
                "-map", "1:a:0",
                str(temp_path if temp_path else out_path),
            ]

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
                    "error": result.stderr[:500],
                    "advisory": "FFmpeg merge failed — original video returned.",
                }

            # If replacing original, swap files
            if temp_path and temp_path.exists():
                shutil.move(str(temp_path), str(out_path))

            # Probe output to confirm audio was preserved
            output_dur = self._probe_media_duration(out_path)
            audio_preserved = (
                output_dur is not None
                and audio_dur is not None
                and output_dur >= audio_dur - 0.1
            )

            return {
                "track": "final_video",
                "status": TrackStatus.COMPLETE,
                "file_path": str(out_path),
                "file_url": self._file_url(out_path),
                "replaced_original": replace_original,
                "video_duration": video_dur,
                "audio_duration": audio_dur,
                "output_duration": output_dur,
                "audio_overrun": audio_overrun,
                "audio_preserved": audio_preserved,
                "on_audio_overrun": on_audio_overrun,
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
        on_audio_overrun: str = "error",
        dialogue_provider: str | None = None,
        score_ambient_provider: str | None = None,
        characters: list[str] | None = None,
        dialogue_lines: list[dict[str, str]] | None = None,
        scene_context: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Run the full audio generation pipeline:
        1. Generate dialogue with CosyVoice/Qwen-TTS by default
        2. Skip score/ambient unless a provider is configured
        3. Mix audio tracks with FFmpeg
        4. Merge audio onto video with FFmpeg (if video_path provided)
        """
        job_id = f"audio_pipeline_{project_id}_{scene_id}_{uuid.uuid4().hex[:8]}"
        started_at = datetime.now().isoformat()
        resolved_dialogue_provider = _normalize_dialogue_provider(dialogue_provider)
        resolved_score_provider = _normalize_score_ambient_provider(score_ambient_provider)
        video_duration = (
            self._probe_media_duration(video_path)
            if video_path and video_path.exists()
            else None
        )
        target_duration_seconds = (
            video_duration
            if video_duration and video_duration > 0
            else estimated_duration_seconds
        )

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
            "AUDIO_PIPELINE_START | job=%s | project=%s | scene=%s | mock=%s | "
            "dialogue_provider=%s | score_provider=%s | target_duration=%s",
            job_id, project_id, scene_id, MOCK_MODE,
            resolved_dialogue_provider, resolved_score_provider,
            f"{target_duration_seconds:.3f}" if target_duration_seconds else "N/A",
        )

        try:
            # Step 1: Generate dialogue
            self._jobs[job_id]["steps"]["dialogue"]["status"] = TrackStatus.GENERATING
            dialogue_result = await self.generate_dialogue(
                scene_id,
                project_id,
                scene_text,
                provider=resolved_dialogue_provider,
                characters=characters,
                dialogue_lines=dialogue_lines,
                max_duration_seconds=video_duration,
                scene_context=scene_context,
            )
            self._jobs[job_id]["steps"]["dialogue"] = dialogue_result

            # Step 2 & 3: Generate score/ambient.
            self._jobs[job_id]["steps"]["score"]["status"] = TrackStatus.GENERATING
            self._jobs[job_id]["steps"]["ambient"]["status"] = TrackStatus.GENERATING

            if resolved_score_provider == "none":
                score_result = self._skipped_score_ambient_result(
                    "score", resolved_score_provider,
                )
                ambient_result = self._skipped_score_ambient_result(
                    "ambient", resolved_score_provider,
                )
            elif resolved_score_provider == "ace_step":
                score_result = await self.generate_score_ambient(
                    scene_id=scene_id,
                    project_id=project_id,
                    mood=mood,
                    score_notes=score_notes,
                    ambient_notes=ambient_notes,
                    instrumentation=instrumentation,
                    tempo=tempo,
                    silence_flag=silence_flag,
                    duration_seconds=target_duration_seconds,
                    provider=resolved_score_provider,
                )
                ambient_result = {
                    "track": "ambient",
                    "status": TrackStatus.SKIPPED,
                    "provider": resolved_score_provider,
                    "file_path": None,
                    "file_url": None,
                    "advisory": "Ambient included in combined ACE Step score/ambient bed.",
                }
            else:
                score_task = self.generate_score(
                    scene_id, project_id, mood, score_notes,
                    instrumentation, tempo, silence_flag, target_duration_seconds,
                    provider=resolved_score_provider,
                )
                ambient_task = self.generate_ambient(
                    scene_id, project_id, ambient_notes, silence_flag,
                    target_duration_seconds, provider=resolved_score_provider,
                )
                score_result, ambient_result = await asyncio.gather(score_task, ambient_task)
            self._jobs[job_id]["steps"]["score"] = score_result
            self._jobs[job_id]["steps"]["ambient"] = ambient_result

            # Step 4: Mix audio tracks
            self._jobs[job_id]["steps"]["mix"]["status"] = TrackStatus.GENERATING
            dialogue_path = Path(dialogue_result.get("file_path", ""))
            score_path = Path(score_result["file_path"]) if score_result.get("file_path") else None
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
                    project_id, scene_id, video_path, mixed_path,
                    replace_original=False,
                    on_audio_overrun=on_audio_overrun,
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
                "dialogue_provider": resolved_dialogue_provider,
                "score_ambient_provider": resolved_score_provider,
                "target_duration_seconds": target_duration_seconds,
                "video_duration_seconds": video_duration,
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
            "dialogue_tts_provider": _normalize_dialogue_provider(DIALOGUE_PROVIDER),
            "score_ambient_provider": _normalize_score_ambient_provider(SCORE_AMBIENT_PROVIDER),
            "ace_step_available": ACE_STEP_AVAILABLE,
            "ace_step_model": ACE_STEP_MODEL,
            "ace_step_runtime_site": str(ACE_STEP_RUNTIME_SITE) if ACE_STEP_RUNTIME_SITE.exists() else None,
            "valid_score_ambient_providers": sorted(VALID_SCORE_AMBIENT_PROVIDERS),
            "elevenlabs_configured": ELEVENLABS_CONFIGURED,
            "elevenlabs_model": ELEVENLABS_MODEL_ID if ELEVENLABS_CONFIGURED else None,
            "elevenlabs_failover_to_piper": ELEVENLABS_FAILOVER_TO_PIPER,
            "fish_audio_configured": FISH_AUDIO_CONFIGURED,
            "fish_audio_model": FISH_AUDIO_MODEL if FISH_AUDIO_CONFIGURED else None,
            "fish_audio_failover_to_piper": FISH_AUDIO_FAILOVER_TO_PIPER,
            "valid_fish_audio_models": sorted(VALID_FISH_AUDIO_MODELS),
            "cosyvoice_configured": COSYVOICE_CONFIGURED,
            "cosyvoice_model": COSYVOICE_MODEL if COSYVOICE_CONFIGURED else None,
            "cosyvoice_failover_to_piper": COSYVOICE_FAILOVER_TO_PIPER,
            "valid_dialogue_providers": sorted(VALID_DIALOGUE_PROVIDERS),
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
