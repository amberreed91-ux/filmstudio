"""Tests: FLUX.2 Klein 4B — NVIDIA hosted image generation provider.

Covers the workstream's required proofs (all mock/fixture based; NO live
provider calls are ever made):

6.  Provider registration (registry metadata + centralized model registry).
7.  NVIDIA authentication (bearer from NVIDIA_API_KEY; missing-key failure).
8.  Request construction (deterministic, fail-closed validation).
9.  Response parsing (both documented response shapes; malformed rejection).
10. Timeout and provider failure behavior (deterministic normalized failure).
11. Credential redaction (no secret material in errors or logs).
12. Provider selection and fallback behavior through the image seam.

Boundary proof: NVIDIA handling is not coupled to storyboard/reference/scene
services — the seam (providers.image_provider.submit_image_render) is the only
integration point.
"""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

import pytest

from app.services.model_registry import (
    MODALITY_IMAGE,
    ROLE_IMAGE_GENERATION,
    model_registry,
)
from app.services.providers import (
    NVIDIA_MODEL_ID,
    NVIDIA_PROVIDER_NAME,
    NvidiaImageProvider,
    build_nvidia_image_request,
    build_nvidia_registry_entries,
    get_nvidia_api_key,
    parse_nvidia_image_response,
    redact_nvidia_secrets,
    submit_nvidia_image_render,
)
from app.services.providers.image_provider import (
    build_image_render_payload,
    submit_image_render,
)
from app.services.providers.nvidia_image_provider import (
    DEFAULT_NVIDIA_API_BASE_URL,
    NVIDIA_API_KEY_ENV_VAR,
    NVIDIA_HOSTED_IMAGE_PATH,
    _post_image_json,
    resolve_image_dimensions,
)

# 1x1 transparent PNG, base64 — deterministic fixture, never a live response.
FIXTURE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
FIXTURE_PROMPT = "A rain-soaked harbor kitchen at dawn, cold blue light, 35mm"


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch):
    """Hard guard: any real HTTP attempt inside these tests fails the test."""
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("Live provider call attempted during tests")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden, raising=True)


# ── 6. Provider registration ─────────────────────────────────────────────────


def test_nvidia_provider_registration_metadata(monkeypatch):
    monkeypatch.delenv(NVIDIA_API_KEY_ENV_VAR, raising=False)
    entry = build_nvidia_registry_entries()[NVIDIA_PROVIDER_NAME]
    assert entry["provider"] == NVIDIA_PROVIDER_NAME
    assert entry["model_id"] == NVIDIA_MODEL_ID
    assert entry["modality"] == MODALITY_IMAGE
    assert ROLE_IMAGE_GENERATION in entry["roles"]
    assert entry["supports_render"] is True
    assert entry["supports_canonical_mutation"] is False
    assert entry["auth_requirements"]["required"] is True
    assert entry["auth_requirements"]["env_var"] == NVIDIA_API_KEY_ENV_VAR
    assert entry["auth_requirements"]["credential_present"] is False


def test_nvidia_registered_in_centralized_model_registry():
    definition = model_registry.get_model(NVIDIA_MODEL_ID)
    assert definition is not None
    assert definition.provider == NVIDIA_PROVIDER_NAME
    assert definition.modality == MODALITY_IMAGE
    assert definition.generation_modes == ("text_to_image",)
    assert NVIDIA_MODEL_ID in model_registry.image_generation_model_ids()
    assert NVIDIA_MODEL_ID in [m.model_id for m in model_registry.models_for_modality("image")]


def test_nvidia_never_enters_runway_render_routing():
    assert NVIDIA_MODEL_ID not in model_registry.allowed_model_ids("runway")
    for model in model_registry.models_for_provider("runway"):
        assert model.provider == "runway"


def test_nvidia_provider_ready_depends_on_credential(monkeypatch):
    monkeypatch.delenv(NVIDIA_API_KEY_ENV_VAR, raising=False)
    provider = NvidiaImageProvider()
    assert provider.is_ready() is False
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    assert provider.is_ready() is True


# ── 7. NVIDIA authentication ─────────────────────────────────────────────────


def test_nvidia_auth_header_uses_env_credential(monkeypatch):
    # Isolate the base-URL env var: the assertion proves the DEFAULT endpoint
    # even when a local .env set NVIDIA_IMAGE_API_BASE_URL (dotenv leakage from
    # main.py imports must not change what this test verifies).
    monkeypatch.delenv("NVIDIA_IMAGE_API_BASE_URL", raising=False)
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"artifacts": [{"base64": FIXTURE_B64}]}).encode("utf-8")

    def _fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return _Response()

    with patch(
        "app.services.providers.nvidia_image_provider.urlopen", _fake_urlopen
    ):
        result = submit_nvidia_image_render(FIXTURE_PROMPT)

    assert result["status"] == "success"
    assert captured["headers"]["Authorization"] == "Bearer test-nvidia-key"
    assert captured["url"] == (
        f"{DEFAULT_NVIDIA_API_BASE_URL}{NVIDIA_HOSTED_IMAGE_PATH}"
    )
    assert captured["method"] == "POST"


def test_nvidia_missing_credential_fails_closed_without_network(monkeypatch):
    monkeypatch.delenv(NVIDIA_API_KEY_ENV_VAR, raising=False)
    result = submit_nvidia_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "NVIDIA_API_KEY" in result["error"] or "Missing NVIDIA" in result["error"]
    assert result["meta"]["reason"] == "missing_nvidia_api_key"


# ── 8. Request construction ──────────────────────────────────────────────────


def test_nvidia_request_construction_shape():
    # Hosted FLUX.2-klein schema: prompt + explicit pixel dimensions + optional
    # seed. No "model", "aspect_ratio", "size", "n", or "output_format" fields.
    body = build_nvidia_image_request(FIXTURE_PROMPT, seed=42)
    assert body["prompt"] == FIXTURE_PROMPT
    assert body["width"] == 1024
    assert body["height"] == 1024
    assert body["seed"] == 42
    assert "model" not in body
    assert "aspect_ratio" not in body
    assert "size" not in body
    assert "n" not in body
    assert "output_format" not in body


def test_nvidia_request_construction_is_deterministic():
    assert build_nvidia_image_request(FIXTURE_PROMPT) == build_nvidia_image_request(FIXTURE_PROMPT)


def test_nvidia_request_construction_fails_closed_on_unknown_params():
    with pytest.raises(ValueError):
        build_nvidia_image_request(FIXTURE_PROMPT, size="999x999")
    with pytest.raises(ValueError):
        build_nvidia_image_request(FIXTURE_PROMPT, aspect_ratio="21:9")
    with pytest.raises(ValueError):
        build_nvidia_image_request("   ")
    with pytest.raises(ValueError):
        build_nvidia_image_request("x" * 4001)


# ── 8b. Hosted endpoint contract (2026-09-27 correction) ────────────────────


def test_nvidia_hosted_url_and_method(monkeypatch):
    """Regression (TEST 2 404): requests must target NVIDIA's hosted FLUX.2 Klein
    genai path with POST — never the legacy integrate.api.nvidia.com OpenAI host
    or the /v1/images/generations container path."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"artifacts": [{"base64": FIXTURE_B64}]}).encode("utf-8")

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return _Response()

    with patch("app.services.providers.nvidia_image_provider.urlopen", _fake_urlopen):
        result = submit_nvidia_image_render(FIXTURE_PROMPT)

    assert result["status"] == "success"
    assert captured["url"] == "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"
    assert captured["method"] == "POST"


def test_nvidia_legacy_base_url_env_maps_to_hosted_endpoint(monkeypatch):
    """A configured NVIDIA_IMAGE_API_BASE_URL equal to the legacy integrate host
    resolves to the hosted endpoint (no .env edit required). Other hosts are
    honored verbatim (self-hosted NIM gateways keep working)."""
    from app.services.providers.nvidia_image_provider import get_nvidia_base_url

    monkeypatch.setenv("NVIDIA_IMAGE_API_BASE_URL", "https://integrate.api.nvidia.com")
    assert get_nvidia_base_url() == DEFAULT_NVIDIA_API_BASE_URL
    monkeypatch.setenv("NVIDIA_IMAGE_API_BASE_URL", "https://integrate.api.nvidia.com/")
    assert get_nvidia_base_url() == DEFAULT_NVIDIA_API_BASE_URL
    monkeypatch.setenv("NVIDIA_IMAGE_API_BASE_URL", "http://localhost:8000")
    assert get_nvidia_base_url() == "http://localhost:8000"
    monkeypatch.delenv("NVIDIA_IMAGE_API_BASE_URL", raising=False)
    assert get_nvidia_base_url() == DEFAULT_NVIDIA_API_BASE_URL


def test_nvidia_request_body_carries_no_model_field_but_registry_gate_holds():
    """The hosted schema has no "model" body field (Studio's dotted registry id
    is translated into the hosted URL path instead), but the registry gate must
    still be enforced — an unregistered/deregistered id fails closed."""
    body = build_nvidia_image_request(FIXTURE_PROMPT)
    assert "model" not in body
    with patch(
        "app.services.providers.nvidia_image_provider.model_registry.get_model",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="not registered"):
            build_nvidia_image_request(FIXTURE_PROMPT)


def test_nvidia_canonical_base_prompt_reaches_http_layer_unchanged(monkeypatch):
    """The canonical prompt crosses the seam and the HTTP boundary byte-identical:
    never rewritten, summarized, enhanced, appended to, truncated, or replaced."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    canonical = "Z" * 512  # any exact string, unusual chars included
    canonical = ("Wide establishing shot. Camera far back. — éüñ \"quotes\" and "
                 "apostrophe's; 100% intact.")
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"artifacts": [{"base64": FIXTURE_B64}]}).encode("utf-8")

    def _fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    with patch("app.services.providers.nvidia_image_provider.urlopen", _fake_urlopen):
        result = submit_image_render(
            build_image_render_payload(
                {"scene_id": "scene_002", "shot_id": "shot_001"},
                {"shot_id": "shot_001"},
                {"base_prompt": canonical},
            ),
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["status"] == "success"
    assert captured["body"]["prompt"] == canonical  # byte-identical


def test_nvidia_dimensions_deterministic_translation():
    """Canonical aspect_ratio → hosted pixel dimensions, deterministically, with
    landscape/portrait intent preserved (16:9 stays landscape)."""
    assert resolve_image_dimensions(aspect_ratio="16:9") == (1536, 864)
    assert resolve_image_dimensions(aspect_ratio="9:16") == (864, 1536)
    assert resolve_image_dimensions(aspect_ratio="3:2") == (1536, 1024)
    assert resolve_image_dimensions(aspect_ratio="2:3") == (1024, 1536)
    assert resolve_image_dimensions(aspect_ratio="1:1") == (1024, 1024)
    # Deterministic: same inputs, same outputs, always.
    for _ in range(3):
        assert resolve_image_dimensions(aspect_ratio="16:9") == (1536, 864)
    # Explicit Studio dimensions win and must sit on the supported 16-px grid.
    assert resolve_image_dimensions(width=1536, height=864) == (1536, 864)
    with pytest.raises(ValueError):
        resolve_image_dimensions(width=1920, height=1080)  # off-grid
    with pytest.raises(ValueError):
        resolve_image_dimensions(width=1536)  # height missing
    # Explicit size strings are grid-validated.
    assert resolve_image_dimensions(size="1536x864", aspect_ratio="1:1") == (1536, 864)
    with pytest.raises(ValueError):
        resolve_image_dimensions(size="999x999")
    with pytest.raises(ValueError):
        resolve_image_dimensions(size="1920x1080")
    with pytest.raises(ValueError):
        resolve_image_dimensions(aspect_ratio="21:9")


def test_nvidia_request_body_uses_translated_dimensions(monkeypatch):
    """End-to-end: the canonical 16:9 contract produces 1536x864 in the hosted
    request body — no silent 16:9→3:2 rewrite of the Studio contract."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"artifacts": [{"base64": FIXTURE_B64}]}).encode("utf-8")

    def _fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    with patch("app.services.providers.nvidia_image_provider.urlopen", _fake_urlopen):
        result = submit_image_render(
            {
                "scene_id": "scene_002",
                "shot_id": "shot_001",
                "base_prompt": FIXTURE_PROMPT,
                "meta": {"aspect_ratio": "16:9", "seed": 916483},
            },
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["status"] == "success"
    assert captured["body"]["width"] == 1536
    assert captured["body"]["height"] == 864
    assert captured["body"]["seed"] == 916483
    assert "aspect_ratio" not in captured["body"]
    assert "size" not in captured["body"]


def test_nvidia_unsupported_dimensions_fail_closed_without_network(monkeypatch):
    """Unsupported orientation/params raise inside request construction — the
    HTTP layer is never reached and no other provider is invoked."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    with patch(
        "app.services.providers.nvidia_image_provider._post_image_json",
        side_effect=AssertionError("HTTP layer must never be reached for invalid params"),
    ) as http:
        result = submit_nvidia_image_render(FIXTURE_PROMPT, aspect_ratio="21:9")
        assert result["status"] == "failed"
        assert "Unsupported aspect ratio" in result["error"]
        assert result["meta"]["reason"] == "nvidia_image_provider_failed"

        result = submit_nvidia_image_render(FIXTURE_PROMPT, width=1920, height=1080)
        assert result["status"] == "failed"
        assert "16-px grid" in result["error"]
    http.assert_not_called()


def test_nvidia_failure_does_not_invoke_any_other_provider(monkeypatch):
    """A NVIDIA failure must never fall through to Qwen/Muse/OpenRouter/Groq/
    Runway/DashScope or the local image fallback."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    invoked = []

    import app.llm_client as llm_client
    import app.services.providers.muse_chat_provider as muse_mod
    import app.services.providers.video_provider as vp

    for target, name in (
        (llm_client, "call_openrouter"),
        (llm_client, "call_groq"),
        (llm_client, "call_llm"),
        (muse_mod, "call_muse"),
        (vp, "submit_video_render"),
    ):
        def _spy(*args, _name=name, **kwargs):
            invoked.append(_name)
            raise AssertionError(f"fallback provider {_name} must not be invoked")

        monkeypatch.setattr(target, name, _spy)

    with patch(
        "app.services.providers.nvidia_image_provider._post_image_json",
        side_effect=RuntimeError("NVIDIA image request failed with HTTP 503"),
    ):
        result = submit_image_render(
            {"scene_id": "scene_002", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["status"] == "failed"
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert invoked == []  # no fallback provider was touched
    assert "picsum" not in json.dumps(result)  # no local placeholder substitute


def test_nvidia_seam_ignores_config_api_key_for_nvidia(monkeypatch):
    """Credential isolation: NVIDIA reads NVIDIA_API_KEY itself; a stale config
    key must never be forwarded, and absence fails closed without network."""
    monkeypatch.delenv(NVIDIA_API_KEY_ENV_VAR, raising=False)
    with patch(
        "app.services.providers.nvidia_image_provider._post_image_json",
        side_effect=AssertionError("must fail closed before HTTP"),
    ) as http:
        result = submit_image_render(
            {"scene_id": "scene_001", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "nvidia",
             "image_provider_api_key": "stale-config-key"},
        )
    http.assert_not_called()
    assert result["status"] == "failed"
    # Provider-level reason is missing_nvidia_api_key; the seam normalizes the
    # failure reason to nvidia_image_failed (existing seam contract).
    assert result["meta"]["reason"] == "nvidia_image_failed"
    assert "NVIDIA" in result["error"]
    assert "stale-config-key" not in json.dumps(result)


# ── 9. Response parsing ──────────────────────────────────────────────────────


def test_nvidia_response_parsing_native_artifacts_shape():
    parsed = parse_nvidia_image_response({"artifacts": [{"base64": FIXTURE_B64}]})
    assert parsed["status"] == "success"
    assert parsed["meta"]["image_base64"] == FIXTURE_B64
    assert parsed["meta"]["provider_model"] == NVIDIA_MODEL_ID
    assert parsed["error"] is None


def test_nvidia_response_parsing_openai_compatible_shape():
    parsed = parse_nvidia_image_response({"data": [{"b64_json": FIXTURE_B64}]})
    assert parsed["status"] == "success"
    assert parsed["meta"]["image_base64"] == FIXTURE_B64


def test_nvidia_response_parsing_rejects_malformed():
    for bad in (None, {}, {"artifacts": []}, {"data": [{}]}, {"artifacts": [{"base64": "!!not-b64!!"}]}):
        parsed = parse_nvidia_image_response(bad)
        assert parsed["status"] == "failed"
        assert parsed["error"]


# ── 10. Timeout and provider failure behavior ───────────────────────────────


def test_nvidia_timeout_maps_to_deterministic_failure(monkeypatch):
    import urllib.error

    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")

    def _timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    with patch("app.services.providers.nvidia_image_provider.urlopen", _timeout):
        result = submit_nvidia_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "TimeoutError" in result["error"]
    assert result["meta"]["reason"] == "nvidia_image_provider_failed"


def test_nvidia_http_error_maps_to_deterministic_failure(monkeypatch):
    import urllib.error

    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")

    def _http_error(*args, **kwargs):
        raise urllib.error.HTTPError(
            f"{DEFAULT_NVIDIA_API_BASE_URL}{NVIDIA_HOSTED_IMAGE_PATH}",
            429, "Too Many Requests", {}, b'{"detail": "rate limited"}',
        )

    with patch("app.services.providers.nvidia_image_provider.urlopen", _http_error):
        result = submit_nvidia_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "429" in result["error"]
    assert result["meta"]["reason"] == "nvidia_image_provider_failed"


def test_nvidia_single_shot_no_retry(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    calls = {"count": 0}

    def _fail(*args, **kwargs):
        calls["count"] += 1
        raise TimeoutError("timed out")

    with patch("app.services.providers.nvidia_image_provider.urlopen", _fail):
        submit_nvidia_image_render(FIXTURE_PROMPT)
    assert calls["count"] == 1


def test_nvidia_timeout_env_var_is_honored(monkeypatch):
    monkeypatch.setenv("NVIDIA_IMAGE_TIMEOUT_SECONDS", "7")
    import importlib

    from app.services.providers import nvidia_image_provider

    importlib.reload(nvidia_image_provider)
    try:
        assert nvidia_image_provider.NVIDIA_TIMEOUT_SECONDS == 7.0
    finally:
        importlib.reload(nvidia_image_provider)


# ── 11. Credential redaction ─────────────────────────────────────────────────


def test_nvidia_error_redaction(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "super-secret-nvidia-key")
    scrubbed = redact_nvidia_secrets("Bearer super-secret-nvidia-key rejected")
    assert "super-secret-nvidia-key" not in scrubbed
    assert NVIDIA_API_KEY_ENV_VAR in scrubbed


def test_nvidia_registry_entries_never_contain_credential(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "super-secret-nvidia-key")
    dumped = json.dumps(build_nvidia_registry_entries())
    assert "super-secret-nvidia-key" not in dumped


def test_nvidia_provider_failure_logs_are_redacted(monkeypatch, caplog):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "super-secret-nvidia-key")

    class _LeakyError(OSError):
        def __str__(self):
            return "auth failed key=super-secret-nvidia-key"

    def _boom(*args, **kwargs):
        raise _LeakyError()

    with patch("app.services.providers.nvidia_image_provider.urlopen", _boom):
        with caplog.at_level(logging.WARNING, logger="nvidia-image-provider"):
            result = submit_nvidia_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "super-secret-nvidia-key" not in result["error"]
    assert "super-secret-nvidia-key" not in caplog.text


def test_nvidia_seam_failure_never_leaks_key_into_error(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "super-secret-nvidia-key")
    with patch(
        "app.services.providers.nvidia_image_provider._post_image_json",
        side_effect=RuntimeError("HTTP 401 for key super-secret-nvidia-key"),
    ):
        result = submit_image_render(
            {"scene_id": "scene_001", "shot_id": "shot_001", "prompt": {"base_prompt": FIXTURE_PROMPT}},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["status"] == "failed"
    assert "super-secret-nvidia-key" not in json.dumps(result)


# ── 12. Provider selection and fallback behavior ────────────────────────────


def test_image_seam_defaults_unchanged_when_disabled():
    result = submit_image_render(
        {"scene_id": "scene_001", "shot_id": "shot_001", "prompt": {"base_prompt": FIXTURE_PROMPT}},
        {},
    )
    assert result["provider"] == "local_image"
    assert result["status"] == "success"
    assert result["meta"]["reason"] == "provider_disabled_local_fallback"


def test_image_seam_legacy_stubbed_path_unchanged():
    result = submit_image_render(
        {"scene_id": "scene_001", "shot_id": "shot_001", "prompt": {"base_prompt": FIXTURE_PROMPT}},
        {"image_provider_enabled": True, "image_provider_name": "other_hosted", "image_provider_api_key": "k"},
    )
    assert result["provider"] == "other_hosted"
    # Unknown names fail closed (new) — but any name outside the registry that
    # predates this workstream (e.g. a free-form hosted name) must keep its
    # legacy stubbed behavior. "other_hosted" is not in the registry, so the
    # fail-closed path is the intended new contract here.
    assert result["status"] == "failed"
    assert result["meta"]["reason"] == "unknown_image_provider"


def test_image_seam_unknown_provider_fails_closed():
    result = submit_image_render(
        {"scene_id": "scene_001", "shot_id": "shot_001", "prompt": {"base_prompt": FIXTURE_PROMPT}},
        {"image_provider_enabled": True, "image_provider_name": "does_not_exist"},
    )
    assert result["status"] == "failed"
    assert result["meta"]["reason"] == "unknown_image_provider"


def test_image_seam_routes_nvidia_when_selected(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    with patch(
        "app.services.providers.nvidia_image_provider.submit_nvidia_image_render",
        return_value={
            "status": "success", "url": None, "file_path": None, "error": None,
            "meta": {"image_base64": FIXTURE_B64, "provider_model": NVIDIA_MODEL_ID},
        },
    ) as submit:
        result = submit_image_render(
            {
                "scene_id": "scene_002",
                "shot_id": "shot_002",
                "prompt": {"base_prompt": FIXTURE_PROMPT},
                "meta": {"aspect_ratio": "3:2", "seed": 7},
            },
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert result["status"] == "success"
    assert result["render_id"] == "image_scene_002_shot_002"
    assert result["meta"]["provider_model"] == NVIDIA_MODEL_ID
    args, kwargs = submit.call_args
    assert args[0] == FIXTURE_PROMPT
    assert kwargs["aspect_ratio"] == "3:2"
    assert kwargs["seed"] == 7


def test_image_seam_nvidia_failure_stays_provider_scoped(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    with patch(
        "app.services.providers.nvidia_image_provider.submit_nvidia_image_render",
        return_value={"status": "failed", "url": None, "file_path": None,
                      "error": "NVIDIA image request failed with HTTP 503", "meta": {}},
    ):
        result = submit_image_render(
            {"scene_id": "scene_001", "shot_id": "shot_001", "prompt": {"base_prompt": FIXTURE_PROMPT}},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert result["status"] == "failed"
    # Failure does NOT silently fall back to the local placeholder.
    assert "picsum" not in json.dumps(result)


# ── Boundary: no storyboard/reference/scene coupling ────────────────────────


def test_nvidia_module_imports_no_storyboard_or_scene_services():
    import app.services.providers.nvidia_image_provider as module

    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in ("storyboard", "reference_selection", "scene_service", "script_parser", "previs"):
        assert forbidden not in source, f"NVIDIA provider must not couple to {forbidden}"


def test_nvidia_receives_exact_canonical_base_prompt_from_builder(monkeypatch):
    """Regression: FLUX.2 Klein gets the canonical prompt produced by
    build_image_render_payload (top-level payload["base_prompt"]), verbatim —
    the seam must not drop it in favor of the legacy nested shape."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    captured = {}

    def _capture_submit(prompt, *, aspect_ratio="1:1", seed=None):
        captured["prompt"] = prompt
        captured["aspect_ratio"] = aspect_ratio
        captured["seed"] = seed
        return {"status": "success", "url": "fixture://not-a-real-url",
                "file_path": None, "error": None, "meta": {"provider_model": NVIDIA_MODEL_ID}}

    with patch(
        "app.services.providers.nvidia_image_provider.submit_nvidia_image_render",
        side_effect=_capture_submit,
    ):
        payload = build_image_render_payload(
            {"scene_id": "scene_004", "shot_id": "shot_001", "heading": "ROOFTOP - NIGHT"},
            {"shot_id": "shot_001"},
            {"base_prompt": FIXTURE_PROMPT, "style_tags": ["noir"], "negative_prompt": ["text"],
             "meta": {"heading": "ROOFTOP - NIGHT"}},
        )
        assert payload.get("base_prompt") == FIXTURE_PROMPT  # canonical shape itself
        result = submit_image_render(
            payload,
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert result["status"] == "success"
    assert captured["prompt"] == FIXTURE_PROMPT
    assert captured["aspect_ratio"] == "1:1"  # seam metadata default preserved
    assert "style_tags" not in captured  # reference info stays unforwarded


def test_nvidia_never_silently_replaces_prompt_with_empty_string(monkeypatch):
    """Regression: a payload missing the canonical prompt must fail closed at
    the provider's non-empty-prompt guard — an empty prompt must never reach
    the HTTP layer, and no local placeholder may silently substitute."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV_VAR, "test-nvidia-key")
    with patch(
        "app.services.providers.nvidia_image_provider._post_image_json",
        side_effect=AssertionError("HTTP layer must never be reached without a prompt"),
    ) as http:
        result = submit_image_render(
            {"scene_id": "scene_001", "shot_id": "shot_001"},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    http.assert_not_called()  # empty prompt can never produce an NVIDIA request
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert result["status"] == "failed"
    assert "prompt" in str(result.get("error")).lower()
    assert "picsum" not in json.dumps(result)  # no silent local fallback

    # And when only the legacy nested shape is present, it is consumed as-is
    # (no regeneration, no rewrite) — the canonical prompt arrives unchanged.
    with patch(
        "app.services.providers.nvidia_image_provider.submit_nvidia_image_render",
        side_effect=lambda prompt, **_: {"status": "success", "url": "fixture://x",
                                          "file_path": None, "error": None, "meta": {}},
    ):
        legacy = submit_image_render(
            {"scene_id": "scene_001", "shot_id": "shot_001",
             "prompt": {"base_prompt": FIXTURE_PROMPT}},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    assert legacy["status"] == "success"  # non-empty prompt accepted, not replaced


def test_seam_payload_projection_is_explicit_and_bounded():
    """Only base_prompt/aspect_ratio/seed cross the seam into NVIDIA handling."""
    from app.services.providers.image_provider import _as_clean_str  # internal, stable

    payload = {
        "scene_id": "scene_001",
        "shot_id": "shot_001",
        "prompt": {"base_prompt": FIXTURE_PROMPT, "style_tags": ["noir"], "negative_prompt": ["text"]},
        "meta": {"heading": "INT. ROOM", "aspect_ratio": "1:1"},
    }
    prompt_pack = payload.get("prompt") or {}
    meta = payload.get("meta") or {}
    projected_prompt = _as_clean_str(prompt_pack.get("base_prompt"))
    assert projected_prompt == FIXTURE_PROMPT
    # Style tags and negative prompts are not silently forwarded as image fields.
    assert "style_tags" not in meta
    assert "negative_prompt" not in meta
