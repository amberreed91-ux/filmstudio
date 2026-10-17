from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Awaitable, Callable, Optional

from openai import AsyncOpenAI, AuthenticationError

from app.config import get_settings
from app.services.shared.dashscope_client import get_dashscope_config
from app.services.stability import ProviderError


logger = logging.getLogger("qwen-llm-client")
DEFAULT_OPENROUTER_MODEL = "google/gemma-4-26b-a4b-it:free"


# ---------------------------------------------------------------------------
# Provider-fallback helper for LLM calls carrying screenplay content
# ---------------------------------------------------------------------------
# Live DashScope/Qwen calls carrying screenplay content can be silently
# blocked by the platform's own content reviewer — the same wall that blocked
# live CosyVoice dialogue export. The block manifests either as a hung
# request (no response, no error) or as an empty completion. Both leave the
# frontend's 30s AbortController to abort, which surfaces as a misleading
# "Render timed out" message for non-render calls.
#
# This module races the primary Qwen call against an internal timeout well
# under the frontend's 30s, and falls back to OpenRouter on timeout or a
# policy-block.
# A distinct ``QwenPolicyBlockedError`` makes a policy block diagnosable
# later instead of indistinguishable from ordinary network slowness.


class QwenPolicyBlockedError(RuntimeError):
    """Raised when Qwen/DashScope returns a content-policy-blocked response.

    DashScope's reviewer typically returns an empty completion (or a generic
    error) when screenplay content trips the policy. This is distinct from a
    slow/hung request (handled via the internal timeout) so callers can fall
    back to OpenRouter and operators can diagnose the block later.
    """


async def call_llm(
    system_prompt: str,
    message: str,
    max_tokens: int = 1024,
) -> str:
    """Call Qwen through DashScope's OpenAI-compatible chat endpoint.

    Raises ``QwenPolicyBlockedError`` when Qwen returns an empty response — a
    common content-policy-block symptom — so the fallback helper can route to
    OpenRouter instead of surfacing a misleading timeout.
    """
    config = get_dashscope_config()
    model = get_settings().qwen_llm_model.strip() or "qwen3.7-max"
    client = AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.openai_compatible_base_url,
    )

    started = perf_counter()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise QwenPolicyBlockedError(
                "Qwen returned an empty response (possible content-policy block)"
            )
        return content.strip()
    finally:
        logger.info(
            "project_id=- job_id=- provider=qwen stage=llm_chat "
            "duration_ms=%d model=%s",
            int((perf_counter() - started) * 1000),
            model,
        )


async def call_openrouter(
    system_prompt: str,
    message: str,
    max_tokens: int = 1024,
) -> str:
    """Call OpenRouter's OpenAI-compatible chat endpoint as the fallback provider.

    Uses a ``:free`` model by default. OpenRouter free-tier capacity has lower
    burst limits than paid providers, which is acceptable for these interactive
    previs intelligence calls but may rate-limit large fan-outs.
    """
    settings = get_settings()
    api_key = (settings.openrouter_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set — cannot fall back to OpenRouter"
        )
    model = settings.openrouter_llm_model.strip() or DEFAULT_OPENROUTER_MODEL
    backup_models = [
        item.strip()
        for item in str(getattr(settings, "openrouter_backup_llm_models", "") or "").split(",")
        if item.strip()
    ]
    models = list(dict.fromkeys([model, *backup_models]))
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.openrouter_base_url.strip() or "https://openrouter.ai/api/v1",
    )

    started = perf_counter()
    last_exc: Exception | None = None
    attempted_model = model
    try:
        for attempted_model in models:
            try:
                response = await client.chat.completions.create(
                    model=attempted_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
                content = response.choices[0].message.content
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("OpenRouter returned an empty response")
                return content.strip()
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "project_id=- job_id=- provider=openrouter stage=llm_chat_fallback_attempt "
                    "duration_ms=%d model=%s error=%s",
                    int((perf_counter() - started) * 1000),
                    attempted_model,
                    type(exc).__name__,
                )
        raise RuntimeError(
            "OpenRouter fallback failed for all configured free models: "
            + ", ".join(models)
        ) from last_exc
    finally:
        logger.info(
            "project_id=- job_id=- provider=openrouter stage=llm_chat_fallback "
            "duration_ms=%d model=%s",
            int((perf_counter() - started) * 1000),
            attempted_model,
        )


async def call_groq(
    system_prompt: str,
    message: str,
    max_tokens: int = 1024,
) -> str:
    """Call Groq's OpenAI-compatible chat endpoint as a local configured fallback."""
    settings = get_settings()
    api_key = (settings.groq_api_key or "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set — cannot fall back to Groq")
    model = str(getattr(settings, "groq_llm_model", "") or "").strip() or "llama-3.3-70b-versatile"
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    started = perf_counter()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq returned an empty response")
        return content.strip()
    finally:
        logger.info(
            "project_id=- job_id=- provider=groq stage=llm_chat_fallback "
            "duration_ms=%d model=%s",
            int((perf_counter() - started) * 1000),
            model,
        )


# Shape of the tuple-returning fallback helper used by routes that want to
# surface/log which provider actually answered.
FallbackLLM = Callable[..., Awaitable[tuple[str, str]]]


async def get_llm_completion_with_fallback(
    system_prompt: str,
    message: str,
    *,
    max_tokens: int = 1024,
    context: Optional[dict] = None,
) -> tuple[str, str]:
    """Race the primary Qwen call against an internal timeout, fall back to OpenRouter.

    Returns ``(completion_text, provider_used)`` where ``provider_used`` is
    either ``"qwen"`` or ``"openrouter"``. Falls back to OpenRouter on
    ``asyncio.TimeoutError`` (hung request) or ``QwenPolicyBlockedError``
    (content-policy block) so callers get a result within a few seconds even
    when Qwen is blocked or slow.
    """
    settings = get_settings()
    timeout = float(settings.qwen_internal_timeout_seconds or 12.0)
    try:
        result = await asyncio.wait_for(
            call_llm(system_prompt, message, max_tokens=max_tokens),
            timeout=timeout,
        )
        return result, "qwen"
    except (asyncio.TimeoutError, QwenPolicyBlockedError, AuthenticationError) as exc:
        logger.warning(
            "Qwen unavailable (%s), trying configured fallback LLM providers",
            type(exc).__name__,
        )
        fallback_errors: dict[str, str] = {}
        try:
            if (settings.openrouter_api_key or "").strip():
                result = await call_openrouter(system_prompt, message, max_tokens=max_tokens)
                return result, "openrouter"
            fallback_errors["openrouter"] = "OPENROUTER_API_KEY missing"
        except Exception as openrouter_exc:
            fallback_errors["openrouter"] = f"{type(openrouter_exc).__name__}: {str(openrouter_exc)[:200]}"

        try:
            if (settings.groq_api_key or "").strip():
                result = await call_groq(system_prompt, message, max_tokens=max_tokens)
                return result, "groq"
            fallback_errors["groq"] = "GROQ_API_KEY missing"
        except Exception as groq_exc:
            fallback_errors["groq"] = f"{type(groq_exc).__name__}: {str(groq_exc)[:200]}"

        raise ProviderError(
            "All configured LLM providers failed",
            stage="llm_fallback",
            metadata={
                "qwen_error": type(exc).__name__,
                "openrouter_error": fallback_errors.get("openrouter", ""),
                "groq_error": fallback_errors.get("groq", ""),
                "fallback_errors": fallback_errors,
            },
        )


async def get_llm_completion_qwenless_fallback(
    system_prompt: str,
    message: str,
    *,
    max_tokens: int = 1024,
) -> tuple[str, str]:
    """Fallback chain WITHOUT the Qwen/DashScope primary leg.

    The Co-Director chat path uses this: Qwen has been removed from that
    chain's provider selection, so fallback flows OpenRouter → Groq exactly as
    ``get_llm_completion_with_fallback`` does after its primary leg fails.
    Unrelated Studio systems (prompt enhancement, character profiling, emotion
    analysis, adherence) keep the original Qwen-primary helper unchanged.

    Returns ``(completion_text, provider_used)`` where ``provider_used`` is
    ``"openrouter"`` or ``"groq"``. Raises ``ProviderError`` when every
    configured fallback is missing or fails.
    """
    settings = get_settings()
    fallback_errors: dict[str, str] = {}
    try:
        if (settings.openrouter_api_key or "").strip():
            result = await call_openrouter(system_prompt, message, max_tokens=max_tokens)
            return result, "openrouter"
        fallback_errors["openrouter"] = "OPENROUTER_API_KEY missing"
    except Exception as openrouter_exc:
        fallback_errors["openrouter"] = (
            f"{type(openrouter_exc).__name__}: {str(openrouter_exc)[:200]}"
        )

    try:
        if (settings.groq_api_key or "").strip():
            result = await call_groq(system_prompt, message, max_tokens=max_tokens)
            return result, "groq"
        fallback_errors["groq"] = "GROQ_API_KEY missing"
    except Exception as groq_exc:
        fallback_errors["groq"] = f"{type(groq_exc).__name__}: {str(groq_exc)[:200]}"

    raise ProviderError(
        "All configured LLM providers failed",
        stage="llm_fallback",
        metadata={
            "qwen_error": "disabled_for_co_director",
            "openrouter_error": fallback_errors.get("openrouter", ""),
            "groq_error": fallback_errors.get("groq", ""),
            "fallback_errors": fallback_errors,
        },
    )


async def call_llm_with_fallback(
    system_prompt: str,
    message: str,
    max_tokens: int = 1024,
) -> str:
    """str-returning adapter around the fallback helper.

    Matches the ``LLMCallable`` contract (``Callable[..., Awaitable[str]]``)
    used by services that take an injected LLM, e.g. the prompt-enhancement
    service. The provider that actually answered is logged inside the helper.
    """
    text, _provider = await get_llm_completion_with_fallback(
        system_prompt, message, max_tokens=max_tokens
    )
    return text
