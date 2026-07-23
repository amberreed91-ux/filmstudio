"""
Vision provider swap: Gemini 2.5 Flash -> Qwen-VL

Used by Loop 1 (vision-based adherence scoring) in the render pipeline --
takes a rendered frame + the original shot prompt, returns a structured
critique. Also usable for the Casting feature later if you want vision-based
face/likeness checks against reference images.

Same OpenAI-compatible endpoint as the LLM service, just with an image
content block in the message.

Drop at: studio-backend/app/services/vision/qwen_vision_service.py
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI

from ..shared.dashscope_client import get_dashscope_config

logger = logging.getLogger(__name__)

# qwen-vl-max is the flagship vision model on DashScope. There's also
# qwen-vl-plus for a cheaper/faster pass -- worth benchmarking both against
# your Loop 1 scoring rubric before picking one, since adherence scoring is
# sensitive to a model's willingness to actually flag mismatches rather than
# being agreeable about "close enough" compositions.
DEFAULT_MODEL = "qwen-vl-max"


@dataclass
class AdherenceScore:
    """Matches the shape Loop 1 / Loop 3's retry logic expects to consume."""
    matches_prompt: bool
    mismatches: list[str]
    raw_critique: str


class QwenVisionService:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        config = get_dashscope_config()
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.openai_compatible_base_url,
        )
        self._model = model

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        data = image_path.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        suffix = image_path.suffix.lstrip(".") or "jpeg"
        return f"data:image/{suffix};base64,{b64}"

    async def score_adherence(
        self,
        *,
        frame_path: Path,
        shot_prompt: str,
        slot_summary: str | None = None,
    ) -> AdherenceScore:
        """
        Scores whether a rendered frame matches the shot prompt.

        `slot_summary` is optional structured context (e.g. from Loop 4's
        slot assembly) to give the vision model the same decomposed prompt
        your render pipeline used, rather than just the raw prompt string --
        this generally produces sharper critiques than the raw prompt alone.
        """
        image_url = self._encode_image(frame_path)

        system_prompt = (
            "You are a strict continuity and prompt-adherence reviewer for "
            "an AI film production pipeline. Compare the rendered frame "
            "against the intended shot description. Do not be lenient -- "
            "flag composition, subject count, setting, lighting, and action "
            "mismatches even if the overall vibe is close. "
            'Respond ONLY with JSON: {"matches_prompt": bool, '
            '"mismatches": [strings]}'
        )

        user_text = f"Shot prompt: {shot_prompt}"
        if slot_summary:
            user_text += f"\n\nStructured slots: {slot_summary}"

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw = resp.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Qwen-VL returned non-JSON critique, wrapping raw text")
            parsed = {"matches_prompt": False, "mismatches": ["unparseable critique"]}

        return AdherenceScore(
            matches_prompt=bool(parsed.get("matches_prompt", False)),
            mismatches=list(parsed.get("mismatches", [])),
            raw_critique=raw,
        )
