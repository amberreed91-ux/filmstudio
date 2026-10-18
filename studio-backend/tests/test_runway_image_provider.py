"""Tests: Runway Gen-4 Image (gen4_image) — hosted image generation provider.

Covers the Runway integration workstream's required proofs (all mock/fixture
based; NO live provider calls are ever made — the module-level live-network
guard makes any accidental real HTTP attempt fail the test immediately):

1.  IMAGE_PROVIDER_NAME=runway selects Runway.
2.  IMAGE_PROVIDER_NAME=nvidia still selects NVIDIA.
3.  Unknown provider fails closed.
4.  Runway receives the canonical base_prompt unchanged (hash-proven).
5.  Runway receives the correct 16:9 representation.
6.  Runway request uses the documented gen4_image model.
7.  Runway task creation response is parsed correctly.
8.  Runway task polling is bounded.
9.  Successful task output is parsed correctly.
10. Missing task ID fails closed.
11. Failed task fails closed.
12. Poll timeout fails closed.
13. Missing image output fails closed.
14. Runway failure does not invoke NVIDIA.
15. NVIDIA failure does not invoke Runway.
16. No fallback provider is silently invoked.
17. Existing NVIDIA tests continue passing unchanged (separate file; here we
    re-prove the seam still routes NVIDIA with its own contract intact).
18. Existing image seam tests continue passing (seam defaults unchanged).
19. Existing provider registry tests continue passing (registry slice intact).
20. Existing render prompt tests continue passing (canonical prompt handling
    through build_image_render_payload unchanged).

Mock tests never contact Runway: the autouse _no_live_network guard fails any
attempt to use urllib.request.urlopen for real, and every HTTP interaction in
these tests is a patched fake.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
from unittest.mock import patch

import pytest

from app.services.model_registry import (
    MODALITY_IMAGE,
    ROLE_IMAGE_GENERATION,
    model_registry,
)
from app.services.providers import (
    NVIDIA_PROVIDER_NAME,
    RUNWAY_IMAGE_MODEL_ID,
    RUNWAY_IMAGE_PROVIDER_NAME,
    RunwayImageProvider,
    build_runway_image_request,
    build_runway_image_registry_entries,
    get_runway_image_api_key,
    parse_runway_task_result,
    parse_runway_task_submission,
    redact_runway_image_secrets,
    resolve_runway_ratio,
    submit_runway_image_render,
)
from app.services.providers.image_provider import (
    build_image_render_payload,
    submit_image_render,
)
from app.services.providers.runway_image_provider import (
    DEFAULT_RUNWAY_IMAGE_API_BASE_URL,
    RUNWAY_API_KEY_ENV_VAR,
    RUNWAY_IMAGE_PATH,
    RUNWAY_IMAGE_POLL_INTERVAL_SECONDS,
    RUNWAY_TASK_PATH_TEMPLATE,
)

FIXTURE_PROMPT = "A rain-soaked harbor kitchen at dawn, cold blue light, 35mm"
TASK_ID = "8f14e45f-ceea-467f-a3d0-2c3a5f5d1c01"
# Deterministic HTTPS fixture URL for the generated image output (never live).
FIXTURE_OUTPUT_URL = "https://fixtures.invalid/runway-image/1.png"


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch):
    """Hard guard: any real HTTP attempt inside these tests fails the test.

    This is the required test guard so accidental live Runway (or NVIDIA)
    network calls fail immediately. Every HTTP interaction below is a patched
    fake; a live call can never be made by these tests.
    """
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("Live provider call attempted during tests")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden, raising=True)


def _runway_env(monkeypatch, key: str = "test-runway-key") -> str:
    monkeypatch.setenv(RUNWAY_API_KEY_ENV_VAR, key)
    return key


def _fake_urlopen_factory(responses, captured=None):
    """Build a urlopen stub serving a queued list of JSON responses.

    responses: list of dicts (or an exception instance) served in order.
    """
    queue = list(responses)

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(queue[0] if not isinstance(queue[0], Exception) else {}).encode("utf-8")

    def _fake_urlopen(request, timeout=None):
        if captured is not None:
            captured.setdefault("requests", []).append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "headers": dict(request.headers),
                    "body": json.loads(request.data.decode("utf-8"))
                    if request.data is not None
                    else None,
                }
            )
        current = queue.pop(0) if len(queue) > 1 or not isinstance(queue[0], Exception) else queue[0]
        if isinstance(current, Exception):
            raise current
        if len(queue) == 0:
            pass  # last response stays in place for repeated polling
        return _Response()

    return _fake_urlopen


# ── 1-3. Provider selection through the seam ─────────────────────────────────


def test_image_seam_selects_runway_when_configured(monkeypatch):
    """IMAGE_PROVIDER_NAME=runway selects Runway (mocked; no network)."""
    _runway_env(monkeypatch)
    with patch(
        "app.services.providers.runway_image_provider.submit_runway_image_render",
        return_value={"status": "success", "url": FIXTURE_OUTPUT_URL, "file_path": None,
                      "error": None, "meta": {"provider_model": RUNWAY_IMAGE_MODEL_ID}},
    ) as submit:
        result = submit_image_render(
            {"scene_id": "scene_002", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "runway"},
        )
    submit.assert_called_once()
    assert result["provider"] == RUNWAY_IMAGE_PROVIDER_NAME
    assert result["status"] == "success"
    assert result["url"] == FIXTURE_OUTPUT_URL
    assert result["meta"]["reason"] == "runway_image_generated"


def test_image_seam_still_selects_nvidia_when_configured(monkeypatch):
    """IMAGE_PROVIDER_NAME=nvidia still selects NVIDIA exactly as before."""
    monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key")
    with patch(
        "app.services.providers.nvidia_image_provider.submit_nvidia_image_render",
        return_value={"status": "success", "url": None, "file_path": None,
                      "error": None, "meta": {"image_base64": "x"}},
    ) as submit:
        result = submit_image_render(
            {"scene_id": "scene_002", "shot_id": "shot_002", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    submit.assert_called_once()
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert result["status"] == "success"
    assert result["meta"]["reason"] == "nvidia_image_generated"


def test_image_seam_unknown_provider_fails_closed(monkeypatch):
    """Unknown provider names continue to fail closed (existing contract)."""
    result = submit_image_render(
        {"scene_id": "scene_001", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
        {"image_provider_enabled": True, "image_provider_name": "does_not_exist"},
    )
    assert result["status"] == "failed"
    assert result["meta"]["reason"] == "unknown_image_provider"


# ── 4. Canonical prompt integrity (hash-proven) ──────────────────────────────


def test_runway_receives_canonical_base_prompt_unchanged(monkeypatch):
    """The canonical prompt crosses the seam and the HTTP boundary byte-identical.

    Proven two ways: direct equality and a SHA-256 hash match, so no rewrite,
    summary, enhancement, cinematic addition, truncation, removal, substitution,
    or regeneration occurred anywhere between build_image_render_payload and
    the serialized Runway request body.
    """
    _runway_env(monkeypatch)
    canonical = (
        "Wide establishing shot. Camera far back. — éüñ \"quotes\" and "
        "apostrophe's; 100% intact. No added cinematic language."
    )
    expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    captured = {}

    def _fake_urlopen(request, timeout=None):
        if request.data is not None:  # submission POST
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "SUCCEEDED", "output": [FIXTURE_OUTPUT_URL]}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_image_render(
            build_image_render_payload(
                {"scene_id": "scene_002", "shot_id": "shot_001"},
                {"shot_id": "shot_001"},
                {"base_prompt": canonical},
            ),
            {"image_provider_enabled": True, "image_provider_name": "runway"},
        )
    assert result["status"] == "success"
    assert captured["body"] is not None  # submission is POSTed with a JSON body
    assert captured["body"]["promptText"] == canonical  # byte-identical
    assert (
        hashlib.sha256(captured["body"]["promptText"].encode("utf-8")).hexdigest()
        == expected_hash
    )


def test_runway_prompt_integrity_is_hash_proven_in_request_builder():
    body = build_runway_image_request(FIXTURE_PROMPT, aspect_ratio="16:9")
    assert body["promptText"] == FIXTURE_PROMPT
    assert (
        hashlib.sha256(body["promptText"].encode("utf-8")).hexdigest()
        == hashlib.sha256(FIXTURE_PROMPT.encode("utf-8")).hexdigest()
    )


# ── 5. 16:9 translation ──────────────────────────────────────────────────────


def test_runway_receives_documented_16_9_representation(monkeypatch):
    """Studio's canonical 16:9 maps to Runway's documented 1280:720 ratio.

    The translation happens only inside the adapter; the ratio is 16:9 in
    Runway's <width>:<height> form. No NVIDIA-style width/height pixels, no
    aspect_ratio string, and no size field are sent.
    """
    _runway_env(monkeypatch)
    captured = {}

    def _fake_urlopen(request, timeout=None):
        if request.data is not None:  # submission POST
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "SUCCEEDED", "output": [FIXTURE_OUTPUT_URL]}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_image_render(
            {
                "scene_id": "scene_002",
                "shot_id": "shot_001",
                "base_prompt": FIXTURE_PROMPT,
                "meta": {"aspect_ratio": "16:9", "seed": 916483},
            },
            {"image_provider_enabled": True, "image_provider_name": "runway"},
        )
    assert result["status"] == "success"
    assert captured["body"]["ratio"] == "1280:720"  # documented gen4_image 16:9 value
    assert "width" not in captured["body"]         # NVIDIA semantics stay with NVIDIA
    assert "height" not in captured["body"]
    assert "aspect_ratio" not in captured["body"]
    assert "size" not in captured["body"]
    assert captured["body"]["seed"] == 916483


def test_runway_ratio_translation_is_deterministic_and_fail_closed():
    assert resolve_runway_ratio(aspect_ratio="16:9") == "1280:720"
    assert resolve_runway_ratio(aspect_ratio="9:16") == "720:1280"
    assert resolve_runway_ratio(aspect_ratio="1:1") == "1024:1024"
    assert resolve_runway_ratio(aspect_ratio="3:2") == "1920:1080"
    assert resolve_runway_ratio(aspect_ratio="2:3") == "1080:1920"
    # Deterministic: same inputs, same outputs, always.
    for _ in range(3):
        assert resolve_runway_ratio(aspect_ratio="16:9") == "1280:720"
    # Already-documented Runway ratios pass through verbatim.
    assert resolve_runway_ratio(aspect_ratio="1920:1080") == "1920:1080"
    # Unknown orientations fail closed (never silently swapped).
    with pytest.raises(ValueError):
        resolve_runway_ratio(aspect_ratio="21:9")


# ── 6. Documented gen4_image model ───────────────────────────────────────────


def test_runway_request_uses_documented_gen4_image_model(monkeypatch):
    _runway_env(monkeypatch)
    captured = {}

    def _fake_urlopen(request, timeout=None):
        if request.data is not None:  # submission POST
            captured.setdefault("requests", []).append(
                {"url": request.full_url, "headers": dict(request.headers),
                 "body": json.loads(request.data.decode("utf-8"))}
            )
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        captured.setdefault("requests", []).append(
            {"url": request.full_url, "headers": dict(request.headers), "body": None,
             "method": request.get_method()}
        )
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "SUCCEEDED", "output": [FIXTURE_OUTPUT_URL]}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_runway_image_render(FIXTURE_PROMPT, aspect_ratio="16:9")

    assert result["status"] == "success"
    submission = captured["requests"][0]
    assert submission["body"]["model"] == "gen4_image"  # documented model id, not Model Router
    assert submission["url"] == f"{DEFAULT_RUNWAY_IMAGE_API_BASE_URL}{RUNWAY_IMAGE_PATH}"
    assert submission["headers"]["Authorization"] == "Bearer test-runway-key"
    # urllib normalizes multi-word header casing in Request.headers; assert on
    # the sent value case-insensitively (the wire header is X-Runway-Version).
    assert submission["headers"]["X-runway-version"] == "2024-11-06"
    # Second request is the documented task poll, never a resubmission.
    poll = captured["requests"][1]
    assert poll["url"] == (
        f"{DEFAULT_RUNWAY_IMAGE_API_BASE_URL}{RUNWAY_TASK_PATH_TEMPLATE.format(task_id=TASK_ID)}"
    )
    assert poll["method"] == "GET"


# ── 7. Task creation parsing ─────────────────────────────────────────────────


def test_runway_task_creation_response_is_parsed_correctly():
    assert parse_runway_task_submission({"id": TASK_ID}) == TASK_ID
    with pytest.raises(ValueError):
        parse_runway_task_submission(None)
    with pytest.raises(ValueError):
        parse_runway_task_submission({})
    with pytest.raises(ValueError):
        parse_runway_task_submission({"nope": True})


# ── 8. Bounded polling ───────────────────────────────────────────────────────


def test_runway_polling_is_bounded_by_attempt_ceiling(monkeypatch):
    """Polling never exceeds the attempt budget and sleeps between polls."""
    _runway_env(monkeypatch)
    monkeypatch.setenv("RUNWAY_IMAGE_MAX_POLL_ATTEMPTS", "4")
    monkeypatch.setenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "60")
    import app.services.providers.runway_image_provider as mod

    polls = {"count": 0}
    sleeps = {"count": 0}

    def _fake_urlopen(request, timeout=None):
        if "text_to_image" in request.full_url:
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        polls["count"] += 1
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "RUNNING"}
                              ).encode()})()

    def _fake_sleep(_seconds):
        sleeps["count"] += 1

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep", _fake_sleep
    ):
        result = submit_runway_image_render(FIXTURE_PROMPT)

    assert result["status"] == "failed"
    assert "attempt budget" in result["error"]
    assert polls["count"] == 4  # exactly the bounded ceiling, never more
    assert sleeps["count"] == 3  # polls are spaced, not a tight loop


def test_runway_poll_interval_defaults_respect_runway_update_guidance():
    """Runway docs: task updates arrive at most every 5s — default honors that."""
    assert RUNWAY_IMAGE_POLL_INTERVAL_SECONDS == 5.0


# ── 9. Successful task output parsing ────────────────────────────────────────


def test_runway_successful_task_output_is_parsed_correctly():
    parsed = parse_runway_task_result(
        {"id": TASK_ID, "status": "SUCCEEDED", "output": [FIXTURE_OUTPUT_URL, "https://fixtures.invalid/2.png"]}
    )
    assert parsed["status"] == "success"
    assert parsed["url"] == FIXTURE_OUTPUT_URL  # first documented output URL
    assert parsed["file_path"] is None
    assert parsed["error"] is None
    assert parsed["meta"]["task_id"] == TASK_ID
    assert parsed["meta"]["provider_model"] == RUNWAY_IMAGE_MODEL_ID


# ── 10. Missing task ID fails closed ─────────────────────────────────────────


def test_runway_missing_task_id_fails_closed(monkeypatch):
    _runway_env(monkeypatch)

    def _fake_urlopen(request, timeout=None):
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps({"unexpected": True}).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen):
        result = submit_runway_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "task id" in result["error"].lower()
    assert result["meta"]["reason"] == "runway_image_provider_failed"


# ── 11. Failed task fails closed ─────────────────────────────────────────────


def test_runway_failed_task_fails_closed(monkeypatch):
    _runway_env(monkeypatch)

    def _fake_urlopen(request, timeout=None):
        if request.data is not None:  # submission POST
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "FAILED",
                                   "failure": "moderated content", "failureCode": "moderation_blocked"}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_runway_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "moderation_blocked" in result["error"]
    assert result["meta"]["reason"] == "runway_image_provider_failed"


def test_runway_cancelled_task_fails_closed():
    parsed = parse_runway_task_result({"id": TASK_ID, "status": "CANCELLED"})
    assert parsed["status"] == "failed"


# ── 12. Poll timeout fails closed ────────────────────────────────────────────


def test_runway_poll_timeout_fails_closed(monkeypatch):
    _runway_env(monkeypatch)
    monkeypatch.setenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setenv("RUNWAY_IMAGE_MAX_POLL_ATTEMPTS", "100")

    def _fake_urlopen(request, timeout=None):
        if "text_to_image" in request.full_url:
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "RUNNING"}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen):
        result = submit_runway_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "timed out" in result["error"]
    assert result["meta"]["reason"] == "runway_image_provider_failed"


# ── 13. Missing image output fails closed ────────────────────────────────────


def test_runway_missing_image_output_fails_closed(monkeypatch):
    _runway_env(monkeypatch)

    def _fake_urlopen(request, timeout=None):
        if "text_to_image" in request.full_url:
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "SUCCEEDED", "output": []}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_runway_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "no image output" in result["error"].lower()


def test_runway_malformed_task_response_fails_closed():
    for bad in (None, "not-an-object", 42, {"id": TASK_ID, "status": "WEIRD"}):
        parsed = parse_runway_task_result(bad)
        assert parsed["status"] == "failed"
        assert parsed["error"]


# ── 14. Runway failure never invokes NVIDIA ──────────────────────────────────


def test_runway_failure_does_not_invoke_nvidia(monkeypatch):
    _runway_env(monkeypatch)
    with patch(
        "app.services.providers.nvidia_image_provider.submit_nvidia_image_render",
        side_effect=AssertionError("NVIDIA must never be invoked from a Runway failure"),
    ) as nvidia_submit, patch(
        "app.services.providers.runway_image_provider.urlopen",
        side_effect=RuntimeError("Runway image request failed with HTTP 503"),
    ):
        result = submit_image_render(
            {"scene_id": "scene_002", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "runway"},
        )
    nvidia_submit.assert_not_called()
    assert result["provider"] == RUNWAY_IMAGE_PROVIDER_NAME
    assert result["status"] == "failed"
    assert "picsum" not in json.dumps(result)  # no silent local fallback either


def test_runway_missing_key_fails_closed_without_network(monkeypatch):
    monkeypatch.delenv(RUNWAY_API_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    with patch(
        "app.services.providers.runway_image_provider.urlopen",
        side_effect=AssertionError("must fail closed before HTTP"),
    ) as http:
        result = submit_runway_image_render(FIXTURE_PROMPT)
    http.assert_not_called()
    assert result["status"] == "failed"
    assert result["meta"]["reason"] == "missing_runway_api_key"


# ── 15. NVIDIA failure never invokes Runway ──────────────────────────────────


def test_nvidia_failure_does_not_invoke_runway(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key")
    with patch(
        "app.services.providers.runway_image_provider.submit_runway_image_render",
        side_effect=AssertionError("Runway must never be invoked from an NVIDIA failure"),
    ) as runway_submit, patch(
        "app.services.providers.nvidia_image_provider._post_image_json",
        side_effect=RuntimeError("NVIDIA image request failed with HTTP 503"),
    ):
        result = submit_image_render(
            {"scene_id": "scene_002", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "nvidia"},
        )
    runway_submit.assert_not_called()
    assert result["provider"] == NVIDIA_PROVIDER_NAME
    assert result["status"] == "failed"


# ── 16. No fallback provider is silently invoked ─────────────────────────────


def test_runway_failure_invokes_no_fallback_provider(monkeypatch):
    _runway_env(monkeypatch)
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

    def _fake_urlopen(request, timeout=None):
        if "text_to_image" in request.full_url:
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "FAILED", "failureCode": "server_error"}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_image_render(
            {"scene_id": "scene_002", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "runway"},
        )
    assert invoked == []  # Qwen/Muse/OpenRouter/Groq/Runway-video/DashScope untouched
    assert result["status"] == "failed"
    assert "picsum" not in json.dumps(result)


# ── 17-20. Existing contracts stay intact ────────────────────────────────────


def test_seam_defaults_unchanged_when_disabled():
    """Existing seam fallback behavior unchanged (test 18 companion)."""
    result = submit_image_render(
        {"scene_id": "scene_001", "shot_id": "shot_001", "prompt": {"base_prompt": FIXTURE_PROMPT}},
        {},
    )
    assert result["provider"] == "local_image"
    assert result["status"] == "success"
    assert result["meta"]["reason"] == "provider_disabled_local_fallback"


def test_runway_seam_ignores_config_api_key_uses_env_only(monkeypatch):
    """Credential isolation mirrors NVIDIA: env-only, config key never forwarded."""
    _runway_env(monkeypatch, "env-runway-key")
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["auth"] = dict(request.headers).get("Authorization")
        if "text_to_image" in request.full_url:
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "SUCCEEDED", "output": [FIXTURE_OUTPUT_URL]}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        result = submit_image_render(
            {"scene_id": "scene_001", "shot_id": "shot_001", "base_prompt": FIXTURE_PROMPT},
            {"image_provider_enabled": True, "image_provider_name": "runway",
             "image_provider_api_key": "stale-config-key"},
        )
    assert result["status"] == "success"
    assert captured["auth"] == "Bearer env-runway-key"
    assert "stale-config-key" not in json.dumps(result)


def test_runway_ml_api_secret_fallback_credential(monkeypatch):
    """RUNWAYML_API_SECRET (Studio's established Runway credential) is honored."""
    monkeypatch.delenv(RUNWAY_API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv("RUNWAYML_API_SECRET", "key_from_secret_env")
    assert get_runway_image_api_key() == "key_from_secret_env"


def test_runway_registered_in_centralized_model_registry():
    definition = model_registry.get_model(RUNWAY_IMAGE_MODEL_ID)
    assert definition is not None
    assert definition.provider == RUNWAY_IMAGE_PROVIDER_NAME
    assert definition.modality == MODALITY_IMAGE
    assert definition.generation_modes == ("text_to_image",)
    assert ROLE_IMAGE_GENERATION in definition.roles
    assert RUNWAY_IMAGE_MODEL_ID in model_registry.image_generation_model_ids()


def test_runway_image_model_never_enters_runway_video_routing():
    """gen4_image is an image model: video routing must never select it."""
    from app.services.model_registry import MODALITY_VIDEO

    # Video-model override allowlist is video-modality scoped.
    assert RUNWAY_IMAGE_MODEL_ID not in model_registry.allowed_model_ids("runway")
    # Video candidates the router can pick from are video-modality only.
    video_candidates = [
        m for m in model_registry.models_for_provider("runway")
        if m.modality == MODALITY_VIDEO
    ]
    assert RUNWAY_IMAGE_MODEL_ID not in {m.model_id for m in video_candidates}
    assert len(video_candidates) >= 10  # the existing video catalog is intact
    # The centralized registry still knows it for the image seam/modality.
    assert RUNWAY_IMAGE_MODEL_ID in model_registry.image_generation_model_ids()
    assert RUNWAY_IMAGE_MODEL_ID in [m.model_id for m in model_registry.models_for_modality("image")]


def test_generation_models_route_never_offers_image_model_for_video():
    """The /models catalog feeding the video model picker stays video-scoped."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import render as render_routes

    app = FastAPI()
    app.include_router(render_routes.router, prefix="/api/f51/studio/render")
    response = TestClient(app).get("/api/f51/studio/render/models?provider=runway")
    assert response.status_code == 200
    model_ids = [m["model_id"] for m in response.json()["models"]]
    assert RUNWAY_IMAGE_MODEL_ID not in model_ids
    assert "gen4.5" in model_ids  # existing video catalog unchanged


def test_runway_registry_entries_never_contain_credential(monkeypatch):
    _runway_env(monkeypatch, "super-secret-runway-key")
    entry = build_runway_image_registry_entries()[RUNWAY_IMAGE_PROVIDER_NAME]
    assert entry["provider"] == RUNWAY_IMAGE_PROVIDER_NAME
    assert entry["model_id"] == RUNWAY_IMAGE_MODEL_ID
    assert entry["supports_canonical_mutation"] is False
    assert entry["auth_requirements"]["env_var"] == RUNWAY_API_KEY_ENV_VAR
    assert "super-secret-runway-key" not in json.dumps(entry)


def test_runway_error_redaction(monkeypatch):
    _runway_env(monkeypatch, "super-secret-runway-key")
    scrubbed = redact_runway_image_secrets("Bearer super-secret-runway-key rejected")
    assert "super-secret-runway-key" not in scrubbed
    assert RUNWAY_API_KEY_ENV_VAR in scrubbed


def test_runway_failure_logs_are_redacted(monkeypatch, caplog):
    _runway_env(monkeypatch, "super-secret-runway-key")

    def _leaky(*args, **kwargs):
        raise OSError("auth failed key=super-secret-runway-key")

    with patch("app.services.providers.runway_image_provider.urlopen", _leaky):
        with caplog.at_level(logging.WARNING, logger="runway-image-provider"):
            result = submit_runway_image_render(FIXTURE_PROMPT)
    assert result["status"] == "failed"
    assert "super-secret-runway-key" not in result["error"]
    assert "super-secret-runway-key" not in caplog.text


def test_runway_complete_prompt_is_never_logged(monkeypatch, caplog):
    """The private canonical prompt must not reach logs in full."""
    _runway_env(monkeypatch)
    private_prompt = "PRIVATE-CANONICAL-" + "x" * 400

    def _fake_urlopen(request, timeout=None):
        if "text_to_image" in request.full_url:
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps({"id": TASK_ID}).encode()})()
        return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                              "read": lambda s: json.dumps(
                                  {"id": TASK_ID, "status": "SUCCEEDED", "output": [FIXTURE_OUTPUT_URL]}
                              ).encode()})()

    with patch("app.services.providers.runway_image_provider.urlopen", _fake_urlopen), patch(
        "app.services.providers.runway_image_provider.time.sleep"
    ):
        with caplog.at_level(logging.INFO, logger="runway-image-provider"):
            submit_runway_image_render(private_prompt)
    assert "PRIVATE-CANONICAL-" not in caplog.text


# ── Request construction (fail-closed validation) ────────────────────────────


def test_runway_request_construction_shape_and_fail_closed_validation():
    body = build_runway_image_request(FIXTURE_PROMPT, aspect_ratio="16:9", seed=7)
    assert body["model"] == "gen4_image"
    assert body["promptText"] == FIXTURE_PROMPT
    assert body["ratio"] == "1280:720"
    assert body["seed"] == 7
    assert build_runway_image_request(FIXTURE_PROMPT) == build_runway_image_request(FIXTURE_PROMPT)

    with pytest.raises(ValueError):
        build_runway_image_request("   ")
    with pytest.raises(ValueError):  # prompt over Runway's documented 1000-char limit
        build_runway_image_request("x" * 1001)
    with pytest.raises(ValueError):  # seed outside Runway's documented range
        build_runway_image_request(FIXTURE_PROMPT, seed=4294967296)
    with pytest.raises(ValueError):  # unknown orientation
        build_runway_image_request(FIXTURE_PROMPT, aspect_ratio="21:9")


def test_runway_references_forwarded_in_documented_form_and_reported():
    report = {"forwarded": 0, "skipped": [], "tags_dropped": []}
    body = build_runway_image_request(
        FIXTURE_PROMPT,
        aspect_ratio="16:9",
        references=[
            {"url": "https://refs.invalid/hero.png", "tag": "Hero Face"},
            {"url": "https://refs.invalid/setting.jpg"},           # untagged is documented
            {"tag": "no-uri"},                                      # reported, not sent
            {"url": "ftp://refs.invalid/legacy.png", "tag": "old"}, # unsupported scheme reported
        ],
        reference_report=report,
    )
    assert body["referenceImages"] == [
        {"uri": "https://refs.invalid/hero.png", "tag": "Hero_Face"},
        {"uri": "https://refs.invalid/setting.jpg"},
    ]
    assert report["forwarded"] == 2
    assert {"index": 2, "reason": "missing_uri"} in report["skipped"]
    assert {"index": 3, "reason": "unsupported_uri_scheme", "scheme": "ftp"} in report["skipped"]


def test_runway_reference_limit_fail_closed_reporting():
    report = {"forwarded": 0, "skipped": [], "tags_dropped": []}
    refs = [{"url": f"https://refs.invalid/{i}.png"} for i in range(5)]
    body = build_runway_image_request(
        FIXTURE_PROMPT, aspect_ratio="16:9", references=refs, reference_report=report
    )
    assert len(body["referenceImages"]) == 3  # Runway documents a max of 3
    assert report["forwarded"] == 3
    assert [s["reason"] for s in report["skipped"]] == [
        "exceeds_runway_reference_limit", "exceeds_runway_reference_limit"
    ]


# ── Boundary: no storyboard/reference/scene coupling ────────────────────────


def test_runway_module_imports_no_storyboard_or_scene_services():
    import app.services.providers.runway_image_provider as module

    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in ("storyboard", "reference_selection", "scene_service", "script_parser", "previs"):
        assert forbidden not in source, f"Runway provider must not couple to {forbidden}"


def test_runway_timeout_env_var_is_honored(monkeypatch):
    monkeypatch.setenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "7")
    from app.services.providers import runway_image_provider as mod

    importlib.reload(mod)
    try:
        assert mod.get_runway_image_timeout_seconds() == 7.0
    finally:
        importlib.reload(mod)
