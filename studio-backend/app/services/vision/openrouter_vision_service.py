"""
Adherence scoring through OpenRouter's OpenAI-compatible endpoint.

Why this subclasses QwenVisionService rather than copying it: the scoring
prompt, the JSON-fence stripping and the validator together *are* the definition
of what an adherence score means. A second copy of them would drift, and two
scores produced by drifted prompts are not comparable even when the numbers look
alike. Only the client construction and the model id differ, so only those are
overridden here.

There is deliberately no default model id. Twice in this project a constant
lifted from prose has pointed at something that did not exist — a project id
copied from a design document that was absent from the database, and a DashScope
embedding model copied from documentation that answered "Model not exist." The
id must come from the live /models endpoint:

    curl -s https://openrouter.ai/api/v1/models \
      -H "Authorization: Bearer $OPENROUTER_API_KEY"

and be set in ADHERENCE_VISION_MODEL.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.vision.qwen_vision_service import QwenVisionService

logger = logging.getLogger(__name__)

FALLBACK_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterVisionService(QwenVisionService):
    """Vision adherence scoring via OpenRouter.

    Note on temporary models: OpenRouter periodically hosts free preview models
    from undisclosed providers. Scores taken from such a model are not
    interchangeable with scores from a permanent one, which is why
    AdherenceScore records scored_by_model. A threshold tuned against a model
    that has since been withdrawn otherwise looks exactly like one tuned against
    the scorer still in use.
    """

    def __init__(self, model: str | None = None) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for OpenRouterVisionService. "
                "Install backend requirements before using OpenRouter vision."
            ) from exc

        from app.config import get_settings

        settings = get_settings()
        api_key = (getattr(settings, "openrouter_api_key", "") or "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to studio-backend/.env "
                "before selecting ADHERENCE_VISION_PROVIDER=openrouter."
            )

        resolved_model = (model or "").strip()
        if not resolved_model:
            raise RuntimeError(
                "ADHERENCE_VISION_MODEL must name an OpenRouter model id when "
                "ADHERENCE_VISION_PROVIDER=openrouter. Discover valid ids from "
                "GET https://openrouter.ai/api/v1/models rather than copying one "
                "from documentation."
            )

        base_url = (
            getattr(settings, "openrouter_base_url", "") or FALLBACK_BASE_URL
        ).strip()

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = resolved_model
        self._base_url = base_url
        # Set by score_adherence when a model rejects response_format and the
        # call has to be retried without it. Surfaced so a silent downgrade in
        # output-format guarantees is visible rather than assumed away.
        self.json_mode_supported: bool | None = None

    async def _create_completion(self, content: list[dict[str, Any]]) -> str:
        """Request a completion, degrading gracefully if json_object is refused.

        Not every OpenRouter-hosted model accepts response_format. Asking for it
        and falling back is better than omitting it for everyone, but a fallback
        that happens silently would hide that this model is only being asked
        nicely for JSON rather than constrained to it.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "Return strict JSON only. Do not include markdown. "
                    "Be specific and do not inflate scores when visible evidence is weak."
                ),
            },
            {"role": "user", "content": content},
        ]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        try:
            response = await self._client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs
            )
            self.json_mode_supported = True
        except Exception as exc:
            logger.warning(
                "OPENROUTER_VISION_JSON_MODE_REJECTED | model=%s | error=%s | "
                "retrying without response_format",
                self._model,
                exc,
            )
            response = await self._client.chat.completions.create(**kwargs)
            self.json_mode_supported = False

        return response.choices[0].message.content or "{}"

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
        """Score three frames. Same contract and same prompt as the Qwen path."""
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
            "OPENROUTER_VISION_API_CALL | model=%s | frames=%d",
            self._model,
            len(frames),
        )
        response_text = await self._create_completion(content)

        try:
            result = json.loads(self._strip_json_fence(response_text))
        except json.JSONDecodeError as exc:
            logger.error("OPENROUTER_VISION_INVALID_JSON | model=%s | error=%s", self._model, exc)
            logger.error("OPENROUTER_VISION_RAW_RESPONSE | first_500=%s", response_text[:500])
            raise ValueError(
                f"OpenRouter model {self._model!r} returned invalid JSON: {exc}"
            ) from exc

        validated = self._validate_result(result)
        logger.info(
            "OPENROUTER_VISION_API_SUCCESS | model=%s | json_mode=%s | response_length=%d",
            self._model,
            self.json_mode_supported,
            len(response_text),
        )
        return validated
