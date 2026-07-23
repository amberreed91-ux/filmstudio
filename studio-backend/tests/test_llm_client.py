from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm_client import QwenPolicyBlockedError, call_llm, call_openrouter, get_llm_completion_with_fallback
from app.services.stability import ProviderError
from app.services.shared.dashscope_client import DashScopeConfig


@pytest.mark.asyncio
async def test_call_llm_uses_qwen_through_dashscope() -> None:
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="  Scene-grounded Qwen response.  ")
            )
        ]
    )
    create = AsyncMock(return_value=completion)
    client = MagicMock()
    client.chat.completions.create = create
    config = DashScopeConfig(
        api_key="test-dashscope-key",
        region="intl",
        workspace_id=None,
    )

    with (
        patch("app.llm_client.get_dashscope_config", return_value=config),
        patch("app.llm_client.AsyncOpenAI", return_value=client) as openai_client,
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.qwen_llm_model = "qwen-plus"
        result = await call_llm("system prompt", "user message", max_tokens=777)

    assert result == "Scene-grounded Qwen response."
    openai_client.assert_called_once_with(
        api_key="test-dashscope-key",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    create.assert_awaited_once_with(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user message"},
        ],
        max_tokens=777,
        temperature=0.7,
    )


@pytest.mark.asyncio
async def test_call_llm_rejects_empty_qwen_response() -> None:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    config = DashScopeConfig(
        api_key="test-dashscope-key",
        region="beijing",
        workspace_id=None,
    )

    with (
        patch("app.llm_client.get_dashscope_config", return_value=config),
        patch("app.llm_client.AsyncOpenAI", return_value=client),
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.qwen_llm_model = "qwen-plus"
        with pytest.raises(RuntimeError, match="empty response"):
            await call_llm("system", "message")


@pytest.mark.asyncio
async def test_call_openrouter_uses_free_model_and_openai_compatible_endpoint() -> None:
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="  OpenRouter fallback response.  ")
            )
        ]
    )
    create = AsyncMock(return_value=completion)
    client = MagicMock()
    client.chat.completions.create = create

    with (
        patch("app.llm_client.AsyncOpenAI", return_value=client) as openai_client,
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.openrouter_api_key = "test-openrouter-key"
        settings.return_value.openrouter_llm_model = (
            "google/gemma-4-26b-a4b-it:free"
        )
        settings.return_value.openrouter_backup_llm_models = ""
        settings.return_value.openrouter_base_url = "https://openrouter.ai/api/v1"
        result = await call_openrouter("system prompt", "user message", max_tokens=333)

    assert result == "OpenRouter fallback response."
    openai_client.assert_called_once_with(
        api_key="test-openrouter-key",
        base_url="https://openrouter.ai/api/v1",
    )
    create.assert_awaited_once_with(
        model="google/gemma-4-26b-a4b-it:free",
        messages=[
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user message"},
        ],
        max_tokens=333,
        temperature=0.7,
    )


@pytest.mark.asyncio
async def test_call_openrouter_retries_configured_free_backup_model() -> None:
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="  Backup model response.  ")
            )
        ]
    )
    create = AsyncMock(side_effect=[RuntimeError("rate limited"), completion])
    client = MagicMock()
    client.chat.completions.create = create

    with (
        patch("app.llm_client.AsyncOpenAI", return_value=client),
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.openrouter_api_key = "test-openrouter-key"
        settings.return_value.openrouter_llm_model = "google/gemma-4-26b-a4b-it:free"
        settings.return_value.openrouter_backup_llm_models = "poolside/laguna-s-2.1:free"
        settings.return_value.openrouter_base_url = "https://openrouter.ai/api/v1"
        result = await call_openrouter("system prompt", "user message", max_tokens=222)

    assert result == "Backup model response."
    assert create.await_args_list[0].kwargs["model"] == "google/gemma-4-26b-a4b-it:free"
    assert create.await_args_list[1].kwargs["model"] == "poolside/laguna-s-2.1:free"


@pytest.mark.asyncio
async def test_qwen_policy_block_falls_back_to_openrouter() -> None:
    with (
        patch("app.llm_client.call_llm", AsyncMock(side_effect=QwenPolicyBlockedError("blocked"))),
        patch("app.llm_client.call_openrouter", AsyncMock(return_value="fallback text")) as openrouter,
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.qwen_internal_timeout_seconds = 12.0
        result, provider = await get_llm_completion_with_fallback("system", "message")

    assert result == "fallback text"
    assert provider == "openrouter"
    openrouter.assert_awaited_once_with("system", "message", max_tokens=1024)


@pytest.mark.asyncio
async def test_both_provider_failure_raises_provider_error_with_openrouter_metadata() -> None:
    with (
        patch("app.llm_client.call_llm", AsyncMock(side_effect=QwenPolicyBlockedError("blocked"))),
        patch("app.llm_client.call_openrouter", AsyncMock(side_effect=RuntimeError("router down"))),
        patch("app.llm_client.get_settings") as settings,
    ):
        settings.return_value.qwen_internal_timeout_seconds = 12.0
        with pytest.raises(ProviderError) as exc_info:
            await get_llm_completion_with_fallback("system", "message")

    error = exc_info.value
    assert error.stage == "llm_fallback"
    assert error.metadata["qwen_error"] == "QwenPolicyBlockedError"
    assert error.metadata["openrouter_error"] == "RuntimeError"
    assert "router down" in error.metadata["openrouter_detail"]
