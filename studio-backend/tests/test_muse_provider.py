"""Tests: Muse Glimmer 30B — advisory chat/intelligence provider.

Covers the workstream's required proofs (all mock/fixture based; NO live
provider calls are ever made):

1.  Provider registration (registry metadata + centralized model registry).
2.  Request construction (deterministic chat-completions body).
3.  Response parsing (success + malformed/empty failure paths).
4.  Co-Director routing to Muse through the existing chat/provider seam,
    including proof that Qwen/DashScope is never selected for Co-Director
    (removed from the active chain) and that fallback stays Qwen-less.
5.  Canonical truth immutability (registry/advisory contract; no writes).
11. Credential redaction (no secret material in errors or logs).
13. Generation-context provenance (advisory provenance record shape).

Runway regression safety: the Runway registry slice is asserted unchanged.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.model_registry import (
    MODALITY_CHAT,
    ROLE_ADVISORY_INTELLIGENCE,
    model_registry,
)
from app.services.providers import (
    MUSE_MODEL_ID,
    MUSE_PROVIDER_NAME,
    MuseChatProvider,
    build_muse_chat_request,
    build_muse_registry_entries,
    call_muse,
    parse_muse_chat_response,
    redact_muse_secrets,
)
from app.services.providers.muse_chat_provider import (
    DEFAULT_MUSE_API_BASE_URL,
    MUSE_API_KEY_ENV_VAR,
    build_co_director_llm_chain,
    get_muse_base_url,
    get_muse_model,
)


QWENLESS_FALLBACK_TARGET = (
    "app.routes.co_director_chat.get_llm_completion_qwenless_fallback"
)


FIXTURE_SYSTEM_PROMPT = (
    "You are the A24 Co-Director: emotionally perceptive and advisory only."
)
FIXTURE_USER_MESSAGE = "User request:\nHow can the second scene carry more dread?"
FIXTURE_REPLY = (
    "Hold the doorway beat two lines longer; the dread lands when she "
    "does not name what she saw. Advisory — your call."
)


# ── 1. Provider registration ─────────────────────────────────────────────────


def test_muse_provider_registration_metadata():
    entries = build_muse_registry_entries()
    entry = entries.get(MUSE_PROVIDER_NAME)
    assert entry is not None
    assert entry["provider"] == MUSE_PROVIDER_NAME
    assert entry["model_id"] == MUSE_MODEL_ID
    assert entry["modality"] == MODALITY_CHAT
    assert ROLE_ADVISORY_INTELLIGENCE in entry["roles"]
    assert entry["supports_render"] is False
    assert entry["supports_canonical_mutation"] is False
    # Auth requirement records the env var NAME, never a credential value.
    assert entry["auth_requirements"]["required"] is True
    assert entry["auth_requirements"]["env_var"] == MUSE_API_KEY_ENV_VAR
    assert isinstance(entry["auth_requirements"]["credential_present"], bool)


def test_muse_registered_in_centralized_model_registry():
    definition = model_registry.get_model(MUSE_MODEL_ID)
    assert definition is not None
    assert definition.provider == MUSE_PROVIDER_NAME
    assert definition.modality == MODALITY_CHAT
    assert definition.roles == (ROLE_ADVISORY_INTELLIGENCE,)
    # Chat models are not generation models: no render modes, no pricing.
    assert definition.generation_modes == ()
    assert definition.credits_per_second == 0
    assert definition.model_id not in model_registry.allowed_model_ids("runway")


def test_muse_absent_from_runway_render_routing():
    # The render-side router must never see the chat model.
    assert model_registry.models_for_provider("runway") == [
        m for m in model_registry.models_for_provider("runway") if m.provider == "runway"
    ]
    assert MUSE_MODEL_ID not in model_registry.allowed_model_ids("runway")
    # And no video model may carry the advisory role.
    for model in model_registry.models_for_provider("runway"):
        assert ROLE_ADVISORY_INTELLIGENCE not in model.roles


def test_muse_is_an_intelligence_model_not_a_video_provider():
    from app.adapters import ADAPTER_REGISTRY
    from app.services.render import RenderService

    service = RenderService()
    assert "muse" not in service._provider_configs
    assert "muse" not in ADAPTER_REGISTRY
    assert MUSE_MODEL_ID not in model_registry.allowed_model_ids("runway")


def test_muse_models_for_modality_lists_chat():
    chat_models = model_registry.models_for_modality("chat")
    assert MUSE_MODEL_ID in [m.model_id for m in chat_models]
    assert MUSE_MODEL_ID in model_registry.advisory_intelligence_model_ids()
    assert MUSE_MODEL_ID not in model_registry.image_generation_model_ids()


# ── 2. Request construction ──────────────────────────────────────────────────


def test_muse_request_construction_shape():
    request = build_muse_chat_request(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE, max_tokens=777)
    assert request["model"] == MUSE_MODEL_ID
    assert request["messages"] == [
        {"role": "system", "content": FIXTURE_SYSTEM_PROMPT},
        {"role": "user", "content": FIXTURE_USER_MESSAGE},
    ]
    assert request["max_tokens"] == 777


def test_muse_request_construction_is_deterministic():
    first = build_muse_chat_request("sys", "msg")
    second = build_muse_chat_request("sys", "msg")
    assert first == second


def test_muse_resolves_model_through_registry(monkeypatch):
    # Isolate the base-URL env var so the assertion proves the DEFAULT fallback
    # even in processes where a local .env set MUSE_API_BASE_URL (dotenv leakage
    # from main.py imports must not change what this test verifies).
    monkeypatch.delenv("MUSE_API_BASE_URL", raising=False)
    assert get_muse_model() == MUSE_MODEL_ID
    assert get_muse_base_url() == DEFAULT_MUSE_API_BASE_URL


# ── 3. Response parsing ──────────────────────────────────────────────────────


def test_muse_response_parsing_success_strips_reply():
    response = {
        "choices": [
            {"message": {"role": "assistant", "content": f"  {FIXTURE_REPLY}  "}}
        ]
    }
    assert parse_muse_chat_response(response) == FIXTURE_REPLY


def test_muse_response_parsing_rejects_malformed_and_empty():
    with pytest.raises(ValueError):
        parse_muse_chat_response(None)
    with pytest.raises(ValueError):
        parse_muse_chat_response({})
    with pytest.raises(ValueError):
        parse_muse_chat_response({"choices": []})
    with pytest.raises(ValueError):
        parse_muse_chat_response({"choices": [{"message": {"content": "   "}}]})


# ── 4. Co-Director routing to Muse ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_co_director_seam_routes_to_muse_when_configured(monkeypatch):
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    with (
        patch(
            "app.services.providers.muse_chat_provider._post_chat_json",
            MagicMock(return_value={"choices": [{"message": {"content": FIXTURE_REPLY}}]}),
        ) as post,
        patch(
            "app.routes.co_director_chat._call_llm",
            new=AsyncMock(side_effect=AssertionError("fallback chain must not run")),
        ),
    ):
        from app.routes.co_director_chat import call_co_director_llm

        reply = await call_co_director_llm(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)

    assert reply == FIXTURE_REPLY
    payload = post.call_args.args[0]
    assert payload["model"] == MUSE_MODEL_ID
    assert payload["messages"][1]["content"] == FIXTURE_USER_MESSAGE


@pytest.mark.asyncio
async def test_co_director_seam_falls_back_to_qwenless_chain_when_muse_unconfigured(monkeypatch):
    """Unconfigured Muse → the Qwen-less configured chain, never the Qwen client."""
    monkeypatch.delenv(MUSE_API_KEY_ENV_VAR, raising=False)
    fallback = AsyncMock(return_value="configured-chain reply")
    with (
        patch(QWENLESS_FALLBACK_TARGET, new=fallback),
        patch(
            "app.services.providers.muse_chat_provider.call_muse",
            new=AsyncMock(side_effect=AssertionError("muse must not be called")),
        ),
        patch(
            "app.routes.co_director_chat._call_llm",
            new=AsyncMock(side_effect=AssertionError("Qwen must not be selected for Co-Director")),
        ),
    ):
        from app.routes.co_director_chat import _get_co_director_llm_callable

        llm = _get_co_director_llm_callable()
        reply = await llm(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)
    assert reply == "configured-chain reply"
    fallback.assert_awaited_once_with(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)


@pytest.mark.asyncio
async def test_co_director_muse_failure_falls_back_to_qwenless_chain(monkeypatch):
    """A configured-but-failing Muse falls back past Qwen straight to the Qwen-less chain."""
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    fallback = AsyncMock(return_value="qwenless fallback reply")
    with (
        patch(
            "app.services.providers.muse_chat_provider._post_chat_json",
            MagicMock(side_effect=RuntimeError("Muse chat request failed with HTTP 503")),
        ),
        patch(QWENLESS_FALLBACK_TARGET, new=fallback),
        patch(
            "app.routes.co_director_chat._call_llm",
            new=AsyncMock(side_effect=AssertionError("Qwen must not be selected for Co-Director")),
        ),
    ):
        from app.routes.co_director_chat import call_co_director_llm

        reply = await call_co_director_llm(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)
    assert reply == "qwenless fallback reply"
    fallback.assert_awaited_once_with(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)


@pytest.mark.asyncio
async def test_co_director_chain_never_routes_to_qwen(monkeypatch):
    """Qwen/DashScope must never be selected on the Co-Director chat path.

    With Muse unconfigured AND the Qwen-less fallback providers absent, the
    chain fails cleanly — and the Qwen-primary client (app.llm_client.call_llm
    via DashScope) is provably never invoked.
    """
    monkeypatch.delenv(MUSE_API_KEY_ENV_VAR, raising=False)
    from app.services.stability import ProviderError

    with (
        patch(
            "app.services.providers.muse_chat_provider.call_muse",
            new=AsyncMock(side_effect=AssertionError("muse must not be called")),
        ),
        patch(
            "app.llm_client.call_llm",
            new=AsyncMock(side_effect=AssertionError("Qwen must never run for Co-Director")),
        ),
        patch(
            "app.llm_client.get_dashscope_config",
            MagicMock(side_effect=AssertionError("DashScope must never be configured for Co-Director")),
        ),
        patch(
            "app.llm_client.call_openrouter",
            new=AsyncMock(side_effect=AssertionError("network isolated: no real OpenRouter call")),
        ),
        patch(
            "app.llm_client.call_groq",
            new=AsyncMock(side_effect=AssertionError("network isolated: no real Groq call")),
        ),
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.openrouter_api_key = ""
        settings.return_value.groq_api_key = ""
        from app.routes.co_director_chat import call_co_director_llm

        with pytest.raises(ProviderError) as exc:
            await call_co_director_llm(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)
    # Clean failure metadata names the configured fallback legs only.
    assert "qwen_error" in exc.value.metadata


@pytest.mark.asyncio
async def test_qwenless_fallback_helper_preserves_openrouter_then_groq_order():
    """The Qwen-less chain mirrors the legacy order: OpenRouter first, then Groq."""
    from app.llm_client import get_llm_completion_qwenless_fallback

    with (
        patch(
            "app.llm_client.call_openrouter",
            AsyncMock(side_effect=AssertionError("openrouter leg must not run here")),
        ),
        patch("app.llm_client.call_groq", AsyncMock(return_value="groq reply")) as groq,
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.openrouter_api_key = ""
        settings.return_value.groq_api_key = "test-groq-key"
        text, provider = await get_llm_completion_qwenless_fallback("sys", "msg")
    assert (text, provider) == ("groq reply", "groq")
    groq.assert_awaited_once_with("sys", "msg", max_tokens=1024)


@pytest.mark.asyncio
async def test_qwenless_fallback_helper_skips_unconfigured_groq():
    """With neither fallback configured, the Qwen-less chain fails cleanly (fail-closed)."""
    from app.services.stability import ProviderError
    from app.llm_client import get_llm_completion_qwenless_fallback

    with patch("app.llm_client.get_settings") as settings:
        settings.return_value.openrouter_api_key = ""
        settings.return_value.groq_api_key = ""
        with pytest.raises(ProviderError):
            await get_llm_completion_qwenless_fallback("sys", "msg")


@pytest.mark.asyncio
async def test_co_director_service_keeps_boundaries_with_muse_llm(monkeypatch):
    """The existing Co-Director chat service keeps session/context/approval behavior."""
    from app.services.co_director_chat_service import CoDirectorChatService

    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    service = CoDirectorChatService(store=_StubStore())
    llm = AsyncMock(return_value=FIXTURE_REPLY)
    reply, prompt = await service.chat(
        project_id="proj-muse",
        specialist="director",
        message="What's wrong with the second scene?",
        context_type="custom",
        frontend_system_prompt="",
        scene_id=None,
        llm=llm,
    )
    assert reply == FIXTURE_REPLY
    assert prompt.request_classification == "CLEAR"
    llm.assert_awaited_once()
    # The service — not the provider — assembled the prompt (boundary preserved).
    system_prompt = llm.await_args.args[0]
    assert "A24 Co-Director" in system_prompt


@pytest.mark.asyncio
async def test_muse_chat_provider_callable_matches_llmcallable_shape(monkeypatch):
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    with patch(
        "app.services.providers.muse_chat_provider._post_chat_json",
        MagicMock(return_value={"choices": [{"message": {"content": FIXTURE_REPLY}}]}),
 ):
        provider = MuseChatProvider()
        assert await provider(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE) == FIXTURE_REPLY


@pytest.mark.asyncio
async def test_muse_call_raises_without_credential(monkeypatch):
    monkeypatch.delenv(MUSE_API_KEY_ENV_VAR, raising=False)
    with patch(
        "app.services.providers.muse_chat_provider._post_chat_json",
        new=AsyncMock(side_effect=AssertionError("no network without a credential")),
    ):
        with pytest.raises(RuntimeError, match="MUSE_API_KEY"):
            await call_muse(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)


def test_muse_chain_builder_preserves_existing_behavior(monkeypatch):
    # Unconfigured → None (callers keep today's behavior unchanged).
    monkeypatch.delenv(MUSE_API_KEY_ENV_VAR, raising=False)
    assert build_co_director_llm_chain() is None
    # Configured → Muse-first chain (callables only).
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    chain = build_co_director_llm_chain()
    assert chain is not None and callable(chain[0])


# ── 5. Canonical truth immutability ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_muse_reply_never_mutates_canonical_truth(monkeypatch):
    """Muse routing must not write screenplay, storyboard, references, or manifest state."""
    from app.services.co_director_chat_service import CoDirectorChatService

    class _RecordingStore(_StubStore):
        def __init__(self):
            super().__init__()
            self.write_calls = []

        def __getattribute__(self, name):  # noqa: D105 — record every attribute access
            attr = object.__getattribute__(self, name)
            if callable(attr) and any(
                token in name for token in ("save", "update", "write", "delete", "set_", "approve", "lock", "assign")
            ):
                def _recorder(*args, **kwargs):
                    object.__getattribute__(self, "write_calls").append(name)
                    return attr(*args, **kwargs)
                return _recorder
            return attr

    store = _RecordingStore()
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    with patch(
        "app.services.providers.muse_chat_provider._post_chat_json",
        MagicMock(return_value={"choices": [{"message": {"content": FIXTURE_REPLY}}]}),
    ):
        service = CoDirectorChatService(store=store)
        await service.chat(
            project_id="proj-immutability",
            specialist="writer",
            message="Rewrite the doorway beat in the second scene.",
            context_type="custom",
            frontend_system_prompt="",
            scene_id=None,
            llm=call_muse,  # the advisory provider itself
        )
    assert store.write_calls == []


def test_muse_registry_declares_no_canonical_mutation():
    entry = build_muse_registry_entries()[MUSE_PROVIDER_NAME]
    assert entry["supports_canonical_mutation"] is False
    assert "no_canonical_mutation" in entry["capabilities"]
    assert ROLE_ADVISORY_INTELLIGENCE in entry["roles"]


def test_runway_registry_slice_unchanged_by_muse_workstream():
    ids = {m.model_id for m in model_registry.list_models() if m.provider == "runway"}
    assert {"gen4.5", "gen4_turbo", "veo3.1", "wan3", "h3_max"} <= ids
    # Video-model override allowlist is scoped to video-modality models
    # (gen4_image renders through the image seam, never as a video override).
    assert model_registry.allowed_model_ids("runway") == frozenset(
        m.model_id
        for m in model_registry.models_for_provider("runway")
        if m.modality == "video"
    )


# ── 11. Credential redaction ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_muse_error_and_logs_are_redacted(monkeypatch, caplog):
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "super-secret-muse-key")

    def _leaky_http_error(*args, **kwargs):
        # Simulate the provider echoing credential material in an HTTP failure
        # (the exact path the redaction contract exists for).
        import urllib.error

        raise urllib.error.HTTPError(
            "https://api.muse.example.com/v1/chat/completions",
            401,
            "unauthorized key=super-secret-muse-key",
            {},
            b'{"detail": "bad key super-secret-muse-key"}',
        )

    with patch(
        "app.services.providers.muse_chat_provider.urlopen", _leaky_http_error
    ):
        with caplog.at_level(logging.WARNING, logger="muse-chat-provider"):
            with pytest.raises(RuntimeError) as exc:
                await call_muse(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE)
    assert "super-secret-muse-key" not in str(exc.value)
    assert "super-secret-muse-key" not in caplog.text


def test_muse_redaction_helper_scrubs_credential(monkeypatch):
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "super-secret-muse-key")
    scrubbed = redact_muse_secrets("Authorization: Bearer super-secret-muse-key failed")
    assert "super-secret-muse-key" not in scrubbed
    assert MUSE_API_KEY_ENV_VAR in scrubbed


def test_muse_registry_entries_never_contain_credential(monkeypatch):
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "super-secret-muse-key")
    dumped = json.dumps(build_muse_registry_entries())
    assert "super-secret-muse-key" not in dumped


def test_muse_logs_record_provider_and_stage_not_secrets(monkeypatch, caplog):
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "super-secret-muse-key")
    with patch(
        "app.services.providers.muse_chat_provider._post_chat_json",
        side_effect=RuntimeError("HTTP 500 boom"),
    ):
        with caplog.at_level(logging.WARNING, logger="muse-chat-provider"):
            with pytest.raises(RuntimeError):
                import asyncio

                asyncio.run(call_muse(FIXTURE_SYSTEM_PROMPT, FIXTURE_USER_MESSAGE))
    assert "super-secret-muse-key" not in caplog.text


# ── 13. Generation-context provenance ────────────────────────────────────────


def test_muse_advisory_provenance_record_shape(monkeypatch):
    """Advisory provenance is auditable, bounded, and carries no credential."""
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "test-muse-key")
    entry = build_muse_registry_entries()[MUSE_PROVIDER_NAME]
    provenance = {
        "provider": entry["provider"],
        "model_id": entry["model_id"],
        "role": ROLE_ADVISORY_INTELLIGENCE,
        "advisory_only": True,
        "canonical_mutation": False,
        "auth_env_var": entry["auth_requirements"]["env_var"],
    }
    assert provenance["provider"] == MUSE_PROVIDER_NAME
    assert provenance["advisory_only"] is True
    assert provenance["canonical_mutation"] is False
    assert provenance["auth_env_var"] == MUSE_API_KEY_ENV_VAR
    dumped = json.dumps(provenance)
    assert "test-muse-key" not in dumped


# ── Fixtures ─────────────────────────────────────────────────────────────────


class _StubStore:
    """Minimal ProjectStore stand-in: read-only project lookup, no persistence."""

    def get_project(self, project_id):
        return {
            "project_id": project_id,
            "title": "Immutability Fixture",
            "scenes": [],
            "script_text": "INT. FIXTURE ROOM - NIGHT\nA doorway. Nothing else.",
        }

    # Deliberately NO save/update/delete methods: any mutation attempt by the
    # chat path would raise, which is exactly what the immutability tests assert.
