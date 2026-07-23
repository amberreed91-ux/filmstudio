"""
Dialogue TTS swap: Chatterbox/Kokoro -> CosyVoice / Qwen3-TTS

Covers dialogue synthesis only. Score/ambient/SFX (currently ACE Step)
has no equivalent on DashScope -- Fun-Music is limited-preview,
Beijing-region-only, and built for full songs with vocals, not
instrumental score/ambient beds. Leave ACE Step wired in for that.

This also overlaps with the planned Fish Audio S2 Pro integration for
the Casting feature -- Qwen3-TTS-VD (voice design) and the voice-cloning
endpoints below may let you drop that second provider entirely if the
voice quality holds up for emotional dialogue casting. Worth an A/B
before committing either way.

Drop at: studio-backend/app/services/audio/cosyvoice_tts_service.py

Note: the DashScope Python SDK (not the OpenAI-compatible client) is used
here since TTS isn't exposed on the OpenAI-compatible endpoint. Requires
`pip install dashscope`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, VoiceEnrollmentService

from ..shared.dashscope_client import get_dashscope_config

logger = logging.getLogger(__name__)

# cosyvoice-v3-flash: fast, good default for most dialogue lines.
# qwen3-tts-vd-*: use for Voice Design (generate a voice from a text
#   description) when casting a character who doesn't have a reference clip.
DEFAULT_MODEL = "cosyvoice-v3-flash"


@dataclass
class ClonedVoice:
    voice_id: str
    preferred_name: str


class CosyVoiceTTSService:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        config = get_dashscope_config()
        dashscope.api_key = config.api_key
        if config.region == "intl":
            dashscope.base_http_api_url = f"{config.native_api_base_url}"
        self._model = model
        self._enrollment = VoiceEnrollmentService()

    def clone_voice_from_sample(
        self,
        *,
        audio_url: str,
        preferred_name: str,
        target_model: str = "cosyvoice-v3",
    ) -> ClonedVoice:
        """
        Clones a character voice from a reference audio sample for the
        Casting feature. `audio_url` must be a publicly reachable URL
        (upload the sample to your own storage first if it's local).
        """
        voice_id = self._enrollment.create_voice(
            target_model=target_model,
            prefix=preferred_name,
            url=audio_url,
        )
        logger.info("Cloned voice %s -> voice_id=%s", preferred_name, voice_id)
        return ClonedVoice(voice_id=voice_id, preferred_name=preferred_name)

    def synthesize_dialogue(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        speech_rate: float = 1.0,
        pitch_rate: float = 1.0,
    ) -> Path:
        """
        Synthesizes a single dialogue line. `voice` is either a stock
        CosyVoice voice name (e.g. "longxiaochun") or a cloned voice_id
        from `clone_voice_from_sample`.

        This is a blocking call by design (matches SpeechSynthesizer's
        `.call()` semantics) -- wrap in `asyncio.to_thread(...)` when
        calling from the per-shot audio orchestrator's async pipeline.
        """
        synthesizer = SpeechSynthesizer(
            model=self._model,
            voice=voice,
            speech_rate=speech_rate,
            pitch_rate=pitch_rate,
        )
        audio_bytes = synthesizer.call(text)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        logger.info("Synthesized dialogue line -> %s", output_path)
        return output_path
