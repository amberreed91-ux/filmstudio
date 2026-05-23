from __future__ import annotations

import types

import scripts.verify_runway_hosted_generation as verify


def test_extract_output_fields_prefers_normalized_and_payload_urls() -> None:
    payload = {
        "provider_job_id": "rw-123",
        "output_payload": {
            "asset_url": "https://cdn.example.com/final.mp4",
            "thumbnail_url": "https://cdn.example.com/preview.jpg",
            "metadata": {
                "provider_response_normalized": {
                    "output": {
                        "video_url": "https://cdn.example.com/final-from-normalized.mp4",
                        "preview_url": "https://cdn.example.com/preview-from-normalized.jpg",
                    },
                    "metadata": {"task_id": "rw-123", "provider_mode": "hosted_api"},
                }
            },
        },
    }

    output_url, preview_url, provider_job_id, provider_mode = verify._extract_output_fields(payload)

    assert output_url == "https://cdn.example.com/final.mp4"
    assert preview_url == "https://cdn.example.com/preview.jpg"
    assert provider_job_id == "rw-123"
    assert provider_mode == "hosted_api"


def test_main_fails_fast_when_mock_mode_enabled(monkeypatch):
    monkeypatch.setattr(verify, "load_env", lambda _path: None)
    monkeypatch.setattr(verify, "resolve_runway_key", lambda: ("RUNWAY_API_KEY", "rk_live_1234"))
    monkeypatch.setenv("RENDER_PROVIDER_TEST_MODE", "mock_success")
    monkeypatch.setattr(verify, "parse_args", lambda: types.SimpleNamespace(prompt="x", timeout_seconds=60))

    rc = verify.main()
    assert rc == 1


def test_main_succeeds_in_hosted_ready_mode_without_live_calls(monkeypatch):
    monkeypatch.setattr(verify, "load_env", lambda _path: None)
    monkeypatch.setattr(verify, "resolve_runway_key", lambda: ("RUNWAY_API_KEY", "rk_live_1234"))
    monkeypatch.delenv("RENDER_PROVIDER_TEST_MODE", raising=False)
    monkeypatch.setattr(verify, "parse_args", lambda: types.SimpleNamespace(prompt="x", timeout_seconds=60))

    monkeypatch.setattr(verify, "detect_backend_base", lambda: "http://127.0.0.1:8010")
    monkeypatch.setattr(
        verify,
        "get_runway_provider_status",
        lambda _base: {
            "provider_id": "runway",
            "provider_mode": "hosted_api",
            "ready_for_hosted_generation": True,
            "missing_requirements": [],
        },
    )
    monkeypatch.setattr(verify, "create_render_job", lambda _base, _prompt: {"id": "job-1"})
    monkeypatch.setattr(
        verify,
        "submit_and_poll_job",
        lambda _base, _job_id, _timeout: {
            "status": "complete",
            "provider_job_id": "rw-123",
            "output_payload": {
                "asset_url": "https://cdn.example.com/final.mp4",
                "thumbnail_url": "https://cdn.example.com/preview.jpg",
                "metadata": {
                    "provider_response_normalized": {
                        "metadata": {"provider_mode": "hosted_api", "task_id": "rw-123"}
                    }
                },
            },
        },
    )

    rc = verify.main()
    assert rc == 0


def test_provider_status_requires_hosted_readiness():
    with __import__("pytest").raises(RuntimeError) as exc:
        verify.assert_hosted_ready(
            {
                "provider_id": "runway",
                "provider_mode": "unavailable",
                "ready_for_hosted_generation": False,
                "missing_requirements": ["api_key"],
            }
        )
    assert "provider_mode" in str(exc.value)


def test_parse_args_uses_300_second_default_timeout(monkeypatch):
    monkeypatch.delenv("RUNWAY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr("sys.argv", ["verify"])
    args = verify.parse_args()
    assert args.timeout_seconds == 300


def test_submit_and_poll_timeout_preserves_provider_job_id(monkeypatch):
    calls = {"status_gets": 0}

    def _fake_curl(method: str, url: str, *, payload=None, timeout=20):
        if method == "POST":
            return {"ok": True}
        calls["status_gets"] += 1
        return {
            "id": "job-1",
            "status": "rendering",
            "provider_job_id": "rw-xyz",
        }

    monkeypatch.setattr(verify, "curl_json", _fake_curl)
    monkeypatch.setattr(verify.time, "sleep", lambda _s: None)
    monkeypatch.setattr(verify.time, "time", lambda: 1000.0 + (calls["status_gets"] * 10.0))

    with __import__("pytest").raises(RuntimeError) as exc:
        verify.submit_and_poll_job("http://127.0.0.1:8010", "job-1", 5)

    msg = str(exc.value)
    assert "provider_job_id=rw-xyz" in msg
    assert "last_status=rendering" in msg
