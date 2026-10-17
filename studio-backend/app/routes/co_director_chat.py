"""
Co-Director Chat — shared LLM client + router re-export.

The actual HTTP routes live in `app.routes.proactive`.
This module:
  1. Re-exports the proactive router as `router` for backwards-compat
  2. Re-exports the LLM client so tests can patch it via
     `app.routes.co_director_chat._call_llm`
  3. Exposes the Co-Director LLM chain through the existing chat provider
     abstraction. Muse Glimmer 30B (registered in the centralized model
     registry as an advisory chat/intelligence model) is prepended when its
     credential is configured. Qwen/DashScope has been REMOVED from this
     chain's provider selection: the fallback is the Qwen-less configured
     chain (OpenRouter → Groq). Advisory only — no canonical mutation, and
     every session/context/approval boundary in co_director_chat_service is
     kept.
"""

from __future__ import annotations

# Re-export the router from proactive so existing imports keep working.
from app.routes.proactive import router as co_director_chat_router  # noqa: E402
router = co_director_chat_router  # backwards-compat alias

# Re-export the LLM client so tests and proactive can both reference it here.
from app.llm_client import call_llm  # noqa: E402,F401
from app.llm_client import get_llm_completion_qwenless_fallback  # noqa: E402

# backwards-compat alias used by existing tests
_call_llm = call_llm


async def call_co_director_llm(system_prompt: str, message: str) -> str:
    """Route one Co-Director chat call through the configured provider chain.

    Muse Glimmer 30B (advisory intelligence model) answers when MUSE_API_KEY is
    set; otherwise — and on any Muse failure — the Qwen-less configured
    fallback chain (OpenRouter → Groq) applies. Qwen/DashScope is not in the
    Co-Director provider chain. Returns only an advisory reply string: no
    session, context, or approval state is read or written here.
    """
    from app.services.providers.muse_chat_provider import call_muse

    try:
        return await call_muse(system_prompt, message)
    except Exception:
        # Muse unavailable/misconfigured → Qwen-less configured chain.
        return await get_llm_completion_qwenless_fallback(system_prompt, message)


# The Co-Director chat seam. The route wires this so Muse is the primary
# intelligence model; the seam stays a drop-in LLMCallable so tests and
# services keep their existing patch points. Qwen is never selected here: the
# chain's internal fallback is the Qwen-less configured chain (OpenRouter →
# Groq), never the Qwen-primary LLM client.
def _get_co_director_llm_callable():
    return call_co_director_llm
