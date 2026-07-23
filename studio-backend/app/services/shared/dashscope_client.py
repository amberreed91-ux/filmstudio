"""
Shared DashScope (Alibaba Cloud Model Studio) client config.

One API key covers the planned Qwen LLM, Qwen-VL, HappyHorse video, and
CosyVoice dialogue TTS providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings


class DashScopeConfigError(RuntimeError):
    """Raised when required DashScope config is missing."""


@dataclass(frozen=True)
class DashScopeConfig:
    api_key: str
    region: str
    workspace_id: str | None

    @property
    def openai_compatible_base_url(self) -> str:
        """Base URL for the OpenAI-compatible endpoint (chat + vision)."""
        if self.region == "beijing":
            return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    @property
    def native_api_base_url(self) -> str:
        """Base URL for native DashScope REST calls (video synthesis, TTS)."""
        if self.workspace_id:
            subdomain = "cn-beijing" if self.region == "beijing" else "ap-southeast-1"
            return f"https://{self.workspace_id}.{subdomain}.maas.aliyuncs.com/api/v1"
        if self.region == "beijing":
            return "https://dashscope.aliyuncs.com/api/v1"
        return "https://dashscope-intl.aliyuncs.com/api/v1"

    @property
    def native_websocket_api_url(self) -> str:
        """WebSocket URL for native streaming DashScope calls such as TTS."""
        if self.workspace_id:
            subdomain = "cn-beijing" if self.region == "beijing" else "ap-southeast-1"
            return f"wss://{self.workspace_id}.{subdomain}.maas.aliyuncs.com/api-ws/v1/inference"
        if self.region == "beijing":
            return "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        return "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"

    @property
    def workspace_base_url(self) -> str | None:
        """Workspace-scoped host, required by a few newer endpoints."""
        if not self.workspace_id:
            return None
        subdomain = "cn-beijing" if self.region == "beijing" else "ap-southeast-1"
        return f"https://{self.workspace_id}.{subdomain}.maas.aliyuncs.com/api/v1"


@lru_cache(maxsize=1)
def get_dashscope_config() -> DashScopeConfig:
    settings = get_settings()
    api_key = (settings.dashscope_api_key or "").strip()
    if not api_key:
        raise DashScopeConfigError(
            "DASHSCOPE_API_KEY is not set. Get one at "
            "https://www.alibabacloud.com/help/en/model-studio/get-api-key "
            "-- remember the key is tied to a region (intl vs beijing)."
        )
    region = (settings.dashscope_region or "intl").strip().lower()
    if region not in ("intl", "beijing"):
        raise DashScopeConfigError(
            f"DASHSCOPE_REGION must be 'intl' or 'beijing', got {region!r}"
        )
    workspace_id = (settings.dashscope_workspace_id or "").strip() or None
    return DashScopeConfig(api_key=api_key, region=region, workspace_id=workspace_id)
