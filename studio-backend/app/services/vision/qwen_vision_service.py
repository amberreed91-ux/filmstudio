"""
Qwen-VL adherence scoring via DashScope's OpenAI-compatible endpoint.

This service returns the raw vision-result shape consumed by
AdherenceService.score_render_attempt: dimensions plus temporal_drift.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from app.services.shared.dashscope_client import get_dashscope_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen-vl-max"
REQUIRED_DIMENSIONS = [
    "character_state",
    "action",
    "camera",
    "lighting",
    "environment_persistence",
]


class QwenVisionService:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for QwenVisionService. "
                "Install backend requirements before using DashScope vision."
            ) from exc

        config = get_dashscope_config()
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.openai_compatible_base_url,
        )
        self._model = model

    @staticmethod
    def _encode_image(image_path: str | Path) -> str:
        path = Path(image_path)
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        suffix = path.suffix.lstrip(".").lower() or "jpeg"
        if suffix == "jpg":
            suffix = "jpeg"
        return f"data:image/{suffix};base64,{b64}"

    @staticmethod
    def _strip_json_fence(response_text: str) -> str:
        text = response_text.strip()
        if "```json" in text:
            json_start = text.find("```json") + 7
            json_end = text.find("```", json_start)
            if json_end != -1:
                return text[json_start:json_end].strip()
        if "```" in text:
            json_start = text.find("```") + 3
            json_end = text.find("```", json_start)
            if json_end != -1:
                return text[json_start:json_end].strip()
        return text

    @staticmethod
    def _validate_result(result: dict[str, Any]) -> dict[str, Any]:
        if "dimensions" not in result or "temporal_drift" not in result:
            raise ValueError("Qwen-VL response missing dimensions or temporal_drift")

        dimensions = result.get("dimensions")
        if not isinstance(dimensions, dict):
            raise ValueError("Qwen-VL response dimensions must be an object")

        missing = [dim for dim in REQUIRED_DIMENSIONS if dim not in dimensions]
        if missing:
            raise ValueError(f"Qwen-VL response missing dimensions: {missing}")

        for dim in REQUIRED_DIMENSIONS:
            item = dimensions[dim]
            if not isinstance(item, dict):
                raise ValueError(f"Qwen-VL dimension {dim!r} must be an object")
            for key in ("score", "evidence", "observed"):
                if key not in item:
                    raise ValueError(f"Qwen-VL dimension {dim!r} missing {key!r}")
            item["score"] = max(0.0, min(100.0, float(item["score"])))
            item["evidence"] = str(item.get("evidence", ""))
            item["observed"] = str(item.get("observed", ""))
            item["expected"] = str(item.get("expected", ""))

        drift = result.get("temporal_drift")
        if not isinstance(drift, dict):
            raise ValueError("Qwen-VL temporal_drift must be an object")
        for key in ("start_score", "end_score"):
            drift[key] = max(0.0, min(100.0, float(drift.get(key, 0))))

        return result

    @staticmethod
    def _build_scoring_prompt(
        *,
        expected_character: str,
        expected_action: str,
        expected_camera: str,
        expected_lighting: str,
        expected_environment: str,
    ) -> str:
        """The scoring prompt, shared by every provider that scores adherence.

        Extracted so the OpenRouter path cannot drift from this one. The prompt
        is part of what a score MEANS: two scores produced by differently-worded
        prompts are not comparable even when the numbers look alike, and a
        threshold calibrated under one wording does not transfer to the other.
        """
        return f"""You are a strict film continuity and prompt-adherence reviewer.

Expected Character State: {expected_character}
Expected Action: {expected_action}
Expected Camera: {expected_camera}
Expected Lighting: {expected_lighting}
Expected Environment: {expected_environment}

Analyze the 3 provided frames (10%, 50%, 90% of shot duration) and score each dimension 0-100.
Detect temporal drift across the shot.

Respond ONLY with valid JSON matching this exact schema:
{{
  "dimensions": {{
    "character_state": {{"score": 0-100, "evidence": "str", "expected": "{expected_character}", "observed": "str"}},
    "action": {{"score": 0-100, "evidence": "str", "expected": "{expected_action}", "observed": "str"}},
    "camera": {{"score": 0-100, "evidence": "str", "expected": "{expected_camera}", "observed": "str"}},
    "lighting": {{"score": 0-100, "evidence": "str", "expected": "{expected_lighting}", "observed": "str"}},
    "environment_persistence": {{"score": 0-100, "evidence": "str", "expected": "{expected_environment}", "observed": "str"}}
  }},
  "temporal_drift": {{"start_score": 0-100, "end_score": 0-100}}
}}"""

    async def score_adherence(
        self,
        *,
        frames: list[str],
        expected_character: str,
        expected_action: str,
        expected_camera: str,
        expected_lighting: str,
        expected_environment: str,
    ) -> dict[str, Any]:
        """
        Score three extracted frames against Loop 1's five adherence slots.

        Returns the raw dict shape expected by AdherenceService:
        {"dimensions": {...}, "temporal_drift": {...}}.
        """
        if len(frames) != 3:
            raise ValueError(f"Expected 3 frames, got {len(frames)}")

        prompt = self._build_scoring_prompt(
            expected_character=expected_character,
            expected_action=expected_action,
            expected_camera=expected_camera,
            expected_lighting=expected_lighting,
            expected_environment=expected_environment,
        )

        content: list[dict[str, Any]] = []
        for idx, frame in enumerate(frames):
            content.append(
                {
                    "type": "text",
                    "text": f"Frame {idx + 1} ({['10%', '50%', '90%'][idx]} of shot):",
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._encode_image(frame)},
                }
            )
        content.append({"type": "text", "text": prompt})

        logger.info(
            "QWEN_VISION_API_CALL | model=%s | frames=%d",
            self._model,
            len(frames),
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON only. Do not include markdown. "
                        "Be specific and do not inflate scores when visible evidence is weak."
                    ),
                },
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        response_text = response.choices[0].message.content or "{}"
        try:
            result = json.loads(self._strip_json_fence(response_text))
        except json.JSONDecodeError as exc:
            logger.error("QWEN_VISION_INVALID_JSON | error=%s", exc)
            logger.error("QWEN_VISION_RAW_RESPONSE | first_500=%s", response_text[:500])
            raise ValueError(f"Qwen-VL returned invalid JSON: {exc}") from exc

        validated = self._validate_result(result)
        logger.info("QWEN_VISION_API_SUCCESS | response_length=%d", len(response_text))
        return validated
