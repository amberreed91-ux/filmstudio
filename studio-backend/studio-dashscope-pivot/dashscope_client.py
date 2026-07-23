"""
Shared DashScope (Alibaba Cloud Model Studio) client config.

One API key now covers what used to be three separate providers:
Groq (LLM), Gemini (vision), Runway (video) -- plus dialogue TTS.

Env vars expected:
  DASHSCOPE_API_KEY       - required
  DASHSCOPE_REGION        - "intl" (Singapore, default) or "beijing"
                             NOTE: API keys are region-specific. A Singapore
                             key will not work against the Beijing endpoint
                             and vice versa -- this bit people in the docs
                             threads. Pick one region and stay on it.
  DASHSCOPE_WORKSPACE_ID  - optional, only needed for the workspace-scoped
                             *.maas.aliyuncs.com hosts (some newer models,
                             e.g. certain TTS voice-clone endpoints, require
                             this instead of the shared dashscope-intl host)

Drop this file at: studio-backend/app/services/shared/dashscope_client.py
(or wherever your other provider clients currently live -- adjust the
imports in the four service files to match).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


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
        if self.region == "beijing":
            return "https://dashscope.aliyuncs.com/api/v1"
        return "https://dashscope-intl.aliyuncs.com/api/v1"

    @property
    def workspace_base_url(self) -> str | None:
        """Workspace-scoped host, required by a few newer endpoints."""
        if not self.workspace_id:
            return None
        subdomain = "cn-beijing" if self.region == "beijing" else "ap-southeast-1"
        return f"https://{self.workspace_id}.{subdomain}.maas.aliyuncs.com/api/v1"


@lru_cache(maxsize=1)
def get_dashscope_config() -> DashScopeConfig:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise DashScopeConfigError(
            "DASHSCOPE_API_KEY is not set. Get one at "
            "https://www.alibabacloud.com/help/en/model-studio/get-api-key "
            "-- remember the key is tied to a region (intl vs beijing)."
        )
    region = os.environ.get("DASHSCOPE_REGION", "intl").lower()
    if region not in ("intl", "beijing"):
        raise DashScopeConfigError(
            f"DASHSCOPE_REGION must be 'intl' or 'beijing', got {region!r}"
        )
    workspace_id = os.environ.get("DASHSCOPE_WORKSPACE_ID")
    return DashScopeConfig(api_key=api_key, region=region, workspace_id=workspace_id)
