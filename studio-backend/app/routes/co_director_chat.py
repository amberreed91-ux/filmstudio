"""
Co-Director Chat — shared LLM client + router re-export.

The actual HTTP routes live in `app.routes.proactive`.
This module:
  1. Re-exports the proactive router as `router` for backwards-compat
  2. Re-exports the LLM client so tests can patch it via
     `app.routes.co_director_chat._call_llm`
"""

from __future__ import annotations

# Re-export the router from proactive so existing imports keep working.
from app.routes.proactive import router as co_director_chat_router  # noqa: E402
router = co_director_chat_router  # backwards-compat alias

# Re-export the LLM client so tests and proactive can both reference it here.
from app.llm_client import call_llm  # noqa: E402

# backwards-compat alias used by existing tests
_call_llm = call_llm
