"""
LLM provider swap: Groq (Llama 3.3 70B) -> Qwen Plus 3.7

DashScope's OpenAI-compatible endpoint means this is a near drop-in --
same `chat.completions.create` shape your Co-Director agents already call
against Groq. The main things that change are base_url, model name, and
error handling around DashScope's rate-limit response shape.

If your existing LLM service wraps calls in a `LLMProvider` protocol
(matching the ProviderPicker pattern from the render side), implement
that same protocol here rather than the standalone class below --
this is written standalone so you can see the whole shape at once.

Drop at: studio-backend/app/services/llm/qwen_llm_service.py
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from openai import AsyncOpenAI, RateLimitError

from ..shared.dashscope_client import get_dashscope_config

logger = logging.getLogger(__name__)

# Qwen Plus 3.7 is the current flagship "Plus" tier model string on DashScope
# as of writing. Confirm the exact model string in your Model Studio console
# before deploying -- Alibaba ships frequent dated snapshots (e.g.
# qwen-plus-2026-xx-xx) alongside the rolling alias.
DEFAULT_MODEL = "qwen-plus"

# Co-Director's five specialist agents + Character Mind Simulator etc. were
# tuned against Llama 3.3 70B's instruction-following quirks. Expect to
# re-tune system prompts lightly after the swap -- Qwen's instruction
# adherence differs enough on multi-constraint prompts (your standing
# corrections / Taste Memory constraints) that it's worth a validation pass,
# not just a model-string change.


class QwenLLMService:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        config = get_dashscope_config()
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.openai_compatible_base_url,
        )
        self._model = model

    async def chat(
        self,
        messages: Iterable[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """
        Mirrors the shape of a typical Groq chat-completion call.
        Returns the assistant text content directly.
        """
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        except RateLimitError:
            # DashScope's shared endpoint is 600 RPM / 1M TPM for most
            # models -- Co-Director's five-agent fan-out could burst past
            # this under concurrent scene processing. Consider a
            # semaphore/backoff wrapper around calls that touch multiple
            # agents in parallel, same as you'd want for any provider.
            logger.warning("DashScope rate limit hit on qwen_llm_service.chat")
            raise

        choice = resp.choices[0]
        return choice.message.content or ""

    async def chat_json(
        self,
        messages: Iterable[dict[str, str]],
        *,
        temperature: float = 0.3,
    ) -> str:
        """For structured outputs (e.g. slot assembly, standing corrections
        parsing) -- forces JSON mode where the render pipeline expects it."""
        return await self.chat(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
