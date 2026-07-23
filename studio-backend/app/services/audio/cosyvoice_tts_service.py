"""
DashScope CosyVoice / Qwen-TTS dialogue synthesis.

This service is for dialogue generation only. Voice cloning/design endpoints
belong to casting workflows and are intentionally not wired into the dialogue
pipeline here.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import ResultCallback, SpeechSynthesizer, VoiceEnrollmentService

from app.services.shared.dashscope_client import get_dashscope_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3-tts-instruct-flash"
DEFAULT_VOICE = "Cherry"
DEFAULT_TIMEOUT_MILLIS = int(os.environ.get("COSYVOICE_TIMEOUT_MILLIS", "60000") or "60000")
DEFAULT_MAX_RETRIES = int(os.environ.get("COSYVOICE_MAX_RETRIES", "2") or "2")
DASHSCOPE_VOICE_PREFIX_MAX_LENGTH = 10


@dataclass
class ClonedVoice:
    voice_id: str
    preferred_name: str


class _CollectingTTSCallback(ResultCallback):
    """Collect DashScope streaming TTS bytes and preserve callback errors."""

    def __init__(self) -> None:
        self.audio_chunks: list[bytes] = []
        self.errors: list[str] = []
        self.events: list[str] = []
        self.completed = False
        self.closed = False
        self.done = threading.Event()

    def on_data(self, data: bytes) -> None:
        if data:
            self.audio_chunks.append(data)

    def on_error(self, message: str) -> None:
        if message:
            self.errors.append(str(message))
        self.done.set()

    def on_event(self, message: str) -> None:
        if message:
            self.events.append(str(message))

    def on_complete(self) -> None:
        self.completed = True
        self.done.set()

    def on_close(self) -> None:
        self.closed = True
        self.done.set()

    @property
    def audio_bytes(self) -> bytes | None:
        if not self.audio_chunks:
            return None
        return b"".join(self.audio_chunks)


class CosyVoiceTTSService:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        config = get_dashscope_config()
        dashscope.api_key = config.api_key
        if config.region == "intl":
            dashscope.base_http_api_url = config.native_api_base_url
            dashscope.base_websocket_api_url = config.native_websocket_api_url
        self._model = model
        self._enrollment = VoiceEnrollmentService()

    def clone_voice_from_sample(
        self,
        *,
        audio_url: str,
        preferred_name: str,
        target_model: str = "cosyvoice-v3",
    ) -> ClonedVoice:
        """Clone a voice from a public reference URL for future casting use."""
        enrollment_prefix = self._voice_enrollment_prefix(preferred_name)
        voice_id = self._enrollment.create_voice(
            target_model=target_model,
            prefix=enrollment_prefix,
            url=audio_url,
        )
        logger.info("Cloned CosyVoice sample %s -> voice_id=%s", enrollment_prefix, voice_id)
        return ClonedVoice(voice_id=voice_id, preferred_name=preferred_name)

    @staticmethod
    def _voice_enrollment_prefix(preferred_name: str) -> str:
        """DashScope voice enrollment prefixes must be short identifier strings."""
        normalized = re.sub(r"[^a-zA-Z0-9]", "", preferred_name or "").lower()
        return (normalized or "casting")[:DASHSCOPE_VOICE_PREFIX_MAX_LENGTH]

    def synthesize_dialogue(
        self,
        *,
        text: str,
        voice: str = DEFAULT_VOICE,
        output_path: Path,
        instruction: str | None = None,
        speech_rate: float = 1.0,
        pitch_rate: float = 1.0,
    ) -> Path:
        """Synthesize one dialogue line and write provider audio bytes."""
        last_error: Exception | None = None
        audio_bytes: bytes | None = None
        for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
            try:
                if self._model.startswith("qwen3-tts-instruct"):
                    response = dashscope.MultiModalConversation.call(
                        model=self._model,
                        api_key=dashscope.api_key,
                        workspace=get_dashscope_config().workspace_id,
                        text=text,
                        voice=voice,
                        instructions=instruction,
                        optimize_instructions=bool(instruction),
                        stream=False,
                    )
                    audio_bytes = self._download_qwen_audio(response)
                else:
                    callback = _CollectingTTSCallback()
                    synthesizer = SpeechSynthesizer(
                        model=self._model,
                        voice=voice,
                        speech_rate=speech_rate,
                        pitch_rate=pitch_rate,
                        instruction=instruction,
                        callback=callback,
                    )
                    returned_audio = synthesizer.call(
                        text,
                        timeout_millis=DEFAULT_TIMEOUT_MILLIS,
                    )
                    if returned_audio is None and callback.audio_bytes is None:
                        callback.done.wait(DEFAULT_TIMEOUT_MILLIS / 1000)
                    audio_bytes = returned_audio or callback.audio_bytes
                    if audio_bytes is None:
                        response = self._safe_synthesizer_response(synthesizer)
                        request_id = self._safe_synthesizer_request_id(synthesizer)
                        callback_error = "; ".join(callback.errors)
                        raise RuntimeError(
                            "CosyVoice returned no audio"
                            f"{f' (request_id={request_id})' if request_id else ''}"
                            f"{f': {callback_error}' if callback_error else ''}"
                            f"{f' | response={response}' if response else ''}"
                        )
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "CosyVoice synthesis attempt %d/%d failed: %s",
                    attempt, DEFAULT_MAX_RETRIES, exc,
                )
                if attempt < DEFAULT_MAX_RETRIES:
                    time.sleep(min(2.0 * attempt, 5.0))
        if audio_bytes is None:
            raise RuntimeError(f"CosyVoice synthesis failed: {last_error}") from last_error

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        logger.info("Synthesized CosyVoice dialogue line -> %s", output_path)
        return output_path

    @staticmethod
    def _safe_synthesizer_response(synthesizer: object) -> str:
        try:
            response = synthesizer.get_response()
        except Exception:
            return ""
        return str(response or "")

    @staticmethod
    def _safe_synthesizer_request_id(synthesizer: object) -> str:
        try:
            request_id = synthesizer.get_last_request_id()
        except Exception:
            return ""
        return str(request_id or "")

    @staticmethod
    def _download_qwen_audio(response: object) -> bytes:
        """Extract and download audio from a Qwen-TTS MultiModalConversation response."""
        status_code = getattr(response, "status_code", None)
        if status_code and int(status_code) >= 400:
            raise RuntimeError(f"Qwen-TTS synthesis failed: {getattr(response, 'message', response)}")

        output = getattr(response, "output", None)
        if isinstance(output, dict):
            audio = output.get("audio") or {}
        else:
            audio = getattr(output, "audio", None) or {}

        if not isinstance(audio, dict):
            audio = dict(audio) if audio else {}

        data = audio.get("data")
        if data:
            import base64

            return base64.b64decode(data)

        url = audio.get("url")
        if not url:
            raise RuntimeError(f"Qwen-TTS response missing audio URL: {response}")

        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT_MILLIS / 1000) as resp:
            return resp.read()
