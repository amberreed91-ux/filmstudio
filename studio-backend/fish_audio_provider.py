"""
Fish Audio (S2 Pro) TTS provider.

Assumptions about your existing codebase (adjust import paths/interface to match
your actual TTSProvider base class in studio-backend):
  - There's a base class / protocol like `TTSProvider` that Chatterbox and Kokoro
    already implement, with a method along the lines of:
        async def synthesize(self, text: str, voice_id: str, **kwargs) -> AudioResult
  - `ProviderPicker` selects a provider by name/config, per-shot or globally.
  - Emotion is expressed as a tag string (Fish Audio supports 50+ open-domain
    emotion/tone tags — e.g. "angry", "whispering", "sobbing", "sarcastic").

This file is a drop-in candidate for wherever Chatterbox/Kokoro providers live,
e.g. `studio-backend/services/audio/providers/`.
"""

from __future__ import annotations

import os
import httpx
from dataclasses import dataclass
from typing import Optional


FISH_AUDIO_API_BASE = "https://api.fish.audio"


@dataclass
class AudioResult:
    audio_bytes: bytes
    format: str  # e.g. "mp3", "wav"
    duration_seconds: Optional[float] = None
    provider: str = "fish_audio"


class FishAudioProvider:
    """
    TTS provider for Fish Audio S2 Pro.

    Implements the same shape as your Chatterbox/Kokoro providers so it can be
    registered in ProviderPicker as a third dialogue option, selectable per-shot
    or per-character.
    """

    name = "fish_audio"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("FISH_AUDIO_API_KEY")
        if not self.api_key:
            raise ValueError("FISH_AUDIO_API_KEY not set")
        self._client = httpx.AsyncClient(
            base_url=FISH_AUDIO_API_BASE,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
        )

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        emotion_tag: Optional[str] = None,
        emotion_intensity: Optional[float] = None,  # 0.0-1.0, if supported
        format: str = "mp3",
    ) -> AudioResult:
        """
        Generate dialogue audio for one line.

        `voice_id` is the Fish Audio voice/model reference (from a cloned voice
        or their voice library — this is what the casting service resolves
        per-character, see casting_service.py).

        `emotion_tag` is the single biggest lever for the "not emotional enough"
        problem — pull this from whatever already tags scene emotion in your
        pipeline (Emotional Audience Simulator output, Director's Memory, or a
        per-line annotation from the Co-Director Brain) rather than leaving it
        null. Fish Audio's tags are inline/open-domain, e.g.:
            "[whispering] I told you not to come back here."
        or passed as a separate emotion parameter depending on their current
        API shape — check their docs at generation time, this has been known
        to shift between inline tags and a structured field across versions.
        """
        payload = {
            "text": text,
            "reference_id": voice_id,
            "format": format,
        }
        if emotion_tag:
            # NOTE: verify current Fish Audio API field name before wiring this
            # in for real — inline-tag vs structured-emotion-field has varied.
            payload["text"] = f"[{emotion_tag}] {text}"
        if emotion_intensity is not None:
            payload["emotion_intensity"] = emotion_intensity

        resp = await self._client.post("/v1/tts", json=payload)
        resp.raise_for_status()

        return AudioResult(
            audio_bytes=resp.content,
            format=format,
            provider=self.name,
        )

    async def clone_voice(self, reference_audio_path: str, label: str) -> str:
        """
        Clone a voice from a short reference clip (Fish Audio supports cloning
        from ~10-second samples). Returns a voice_id to store against a
        character in the casting service.

        Useful if a filmmaker uploads a reference voice for a character on
        The Page rather than picking from a stock library.
        """
        filename = os.path.basename(reference_audio_path)
        with open(reference_audio_path, "rb") as f:
            files = {"voices": (filename, f, "audio/wav")}
            data = {
                "type": "tts",
                "title": label,
                "train_mode": "fast",
                "visibility": "private",
                "enhance_audio_quality": "true",
                "generate_sample": "false",
            }
            resp = await self._client.post(
                "/model", files=files, data=data
            )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("_id") or payload["voice_id"]

    async def close(self):
        await self._client.aclose()
