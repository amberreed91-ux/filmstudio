"""Muse Glimmer 30B — advisory chat/intelligence chat provider.

This module adds Muse Glimmer 30B as the primary chat/intelligence model
**through the existing chat/provider abstraction** — it is consumed wherever an
``LLMCallable`` (``Callable[[str, str], Awaitable[str]]``) is already injected
(e.g. the Co-Director chat service and the Co-Director chat routes). It is NOT
a parallel Co-Director implementation: session handling, context assembly,
grounding validation, provenance, and human approval boundaries live in
``co_director_chat_service`` and are unchanged. Muse only receives the fully
assembled prompts those boundaries already produce and returns an advisory
reply string.

Canonical truth immutability (contract, enforced by tests):
- Muse is an ADVISORY model. Its replies never mutate canonical screenplay,
  FilmStructure, CreativeSpine, storyboard approval state, references, camera
  approval, dialogue assignments, locks, or generation manifests.
- The model is registered in the centralized model registry as a chat-modality
  model with the ``advisory_intelligence`` role and NO generation role, so
  render routing, adapters, and cost gates can never select or execute it.

Credentials:
- The API key is read ONLY from the ``MUSE_API_KEY`` environment variable.
- It is never hardcoded and never logged; error paths carry a redaction helper
  (``redact_muse_secrets``) so exception text is scrubbed before storage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.model_registry import (
    ROLE_ADVISORY_INTELLIGENCE,
    model_registry,
)

logger = logging.getLogger("muse-chat-provider")

MUSE_PROVIDER_NAME = "muse"
# Served id must match NVIDIA's namespaced NIM model name (verified against
# NVIDIA's published reference, 2026-09-27); keep in sync with the registry.
MUSE_MODEL_ID = "meta/muse-glimmer-30b"
MUSE_CHAT_ROLE = ROLE_ADVISORY_INTELLIGENCE

DEFAULT_MUSE_API_BASE_URL = "https://api.muse.example.com/v1"
MUSE_API_KEY_ENV_VAR = "MUSE_API_KEY"
MUSE_TIMEOUT_SECONDS = float(os.getenv("MUSE_TIMEOUT_SECONDS", "20") or 20)

_SECRET_ENV_VARS = (MUSE_API_KEY_ENV_VAR,)


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def redact_muse_secrets(text: Any) -> str:
    """Scrub credential material out of any string destined for logs or errors."""
    redacted = str(text or "")
    for env_var in _SECRET_ENV_VARS:
        secret = os.getenv(env_var, "").strip()
        if secret and secret in redacted:
            redacted = redacted.replace(secret, f"[REDACTED:{env_var}]")
    return redacted


def get_muse_api_key() -> str:
    """Return the Muse credential from the environment (name only; never logged)."""
    return os.getenv(MUSE_API_KEY_ENV_VAR, "").strip()


def get_muse_base_url() -> str:
    """Return the Muse API base URL from the environment, else the default."""
    return (
        os.getenv("MUSE_API_BASE_URL", "").strip()
        or DEFAULT_MUSE_API_BASE_URL
    )


def get_muse_model() -> str:
    """Resolve the served model id through the centralized model registry."""
    definition = model_registry.get_model(MUSE_MODEL_ID)
    if definition is None or definition.provider != MUSE_PROVIDER_NAME:
        raise ValueError(
            f"Model '{MUSE_MODEL_ID}' is not registered for provider "
            f"'{MUSE_PROVIDER_NAME}' in the centralized model registry."
        )
    if definition.modality != "chat" or definition.roles != (ROLE_ADVISORY_INTELLIGENCE,):
        raise ValueError(
            f"Model '{MUSE_MODEL_ID}' must remain an advisory chat model; "
            "registry configuration is invalid."
        )
    return definition.model_id


def build_provider_registry_entries() -> Dict[str, Dict[str, Any]]:
    """Registry metadata for Muse (capabilities, modality, endpoint, auth, availability).

    Deterministic and credential-free: the API key is never included, only the
    NAME of the environment variable that holds it.
    """
    definition = model_registry.get_model(MUSE_MODEL_ID)
    if definition is None:
        return {}
    return {
        MUSE_PROVIDER_NAME: {
            "provider": MUSE_PROVIDER_NAME,
            "model_id": definition.model_id,
            "label": definition.label,
            "modality": definition.modality,
            "modality_detail": definition.modality_detail,
            "roles": list(definition.roles),
            "capabilities": list(definition.capabilities) or [
                "advisory_only",
                "chat_completion",
                "no_render",
                "no_canonical_mutation",
            ],
            "endpoint_config": definition.endpoint_config,
            "auth_requirements": {
                "required": True,
                "env_var": definition.auth_env_var,
                "credential_present": bool(get_muse_api_key()),
            },
            "availability_status": definition.availability_status,
            "supports_render": False,
            "supports_canonical_mutation": False,
        }
    }


def build_muse_chat_request(
    system_prompt: str,
    message: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Build the deterministic chat-completions request body for Muse.

    Mirrors the shape every other chat provider in Studio sends (system +
    user messages), so the Co-Director's prompt assembly is preserved exactly.
    """
    return {
        "model": get_muse_model(),
        "messages": [
            {"role": "system", "content": str(system_prompt or "")},
            {"role": "user", "content": str(message or "")},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }


def parse_muse_chat_response(response: Any) -> str:
    """Parse a Muse chat-completions response into the advisory reply string.

    Raises ``ValueError`` on empty/malformed completions so callers fall back
    through the existing configured chain (never silently degrading).
    """
    if not isinstance(response, dict):
        raise ValueError("Muse returned a malformed (non-object) response")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Muse returned no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("Muse returned a malformed choice")
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Muse returned an empty response")
    return content.strip()


def _post_chat_json(payload: Dict[str, Any], api_key: str, base_url: str) -> Dict[str, Any]:
    """Blocking chat-completions POST; executed off-thread by ``call_muse``."""
    url = base_url.rstrip("/") + "/chat/completions"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=MUSE_TIMEOUT_SECONDS) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        # Never surface or log credential material from error bodies.
        logger.warning(
            "Muse chat request failed status=%s reason=%s",
            exc.code,
            redact_muse_secrets(exc.reason),
        )
        raise RuntimeError(
            redact_muse_secrets(f"Muse chat request failed with HTTP {exc.code}")
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Muse chat request failed error_type=%s", type(exc).__name__)
        raise RuntimeError(
            redact_muse_secrets(f"Muse chat request failed: {type(exc).__name__}")
        ) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Muse returned a non-JSON response") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Muse returned a non-object response")
    return parsed


async def call_muse(
    system_prompt: str,
    message: str,
    *,
    max_tokens: int = 1024,
) -> str:
    """LLMCallable-compatible Muse call (``Callable[[str, str], Awaitable[str]]``).

    Advisory-only chat completion. Raises ``RuntimeError`` when the credential
    is missing so the caller's existing fallback chain applies unchanged.
    """
    api_key = get_muse_api_key()
    if not api_key:
        raise RuntimeError("MUSE_API_KEY is not set — cannot call Muse")

    payload = build_muse_chat_request(system_prompt, message, max_tokens=max_tokens)
    response = await asyncio.to_thread(
        _post_chat_json, payload, api_key, get_muse_base_url()
    )
    return parse_muse_chat_response(response)


class MuseChatProvider:
    """Advisory chat provider bound to the existing chat/provider abstraction.

    Exposes the ``LLMCallable``-shaped adapter plus a readiness check. This
    class performs no routing itself — the Co-Director chat service selects
    the provider through ``build_co_director_llm_chain`` and keeps every
    session/approval boundary.
    """

    name = MUSE_PROVIDER_NAME

    def is_ready(self) -> bool:
        return bool(get_muse_api_key())

    def registry_entries(self) -> Dict[str, Dict[str, Any]]:
        return build_provider_registry_entries()

    async def __call__(self, system_prompt: str, message: str) -> str:
        return await call_muse(system_prompt, message)


def build_co_director_llm_chain() -> Optional[List[Any]]:
    """Prepend Muse to the Co-Director's LLM chain when it is configured.

    Returns a provider-ordered chain (Muse first when its credential is
    present) for callers that route through the configured chain; ``None``
    preserves today's behavior unchanged when Muse is not configured. The
    chain carries callables only — no canonical state, no session state.
    """
    if not get_muse_api_key():
        return None
    return [call_muse]


muse_chat_provider = MuseChatProvider()
