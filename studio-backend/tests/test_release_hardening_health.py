"""Release hardening: staleness visibility in /health + startup tripwire.

The stale-backend failure (AUDIT_2026-10-17 H1) was invisible: nothing in
the health response said which commit the process runs. These tests pin the
additive fields (git_commit, process_start_time, image_provider) and the
fail-closed startup check that refuses to boot DashScope-resolving code.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import main
from main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestHealthStalenessVisibility:
    def test_health_reports_git_commit(self, client: TestClient):
        body = client.get("/health").json()
        assert "git_commit" in body
        commit = body["git_commit"]
        assert commit, "health must show the commit the backend runs"
        assert re.fullmatch(r"[0-9a-f]{40}", commit), f"not a git SHA: {commit!r}"

    def test_health_reports_process_start_time(self, client: TestClient):
        from datetime import datetime

        body = client.get("/health").json()
        assert "process_start_time" in body
        datetime.fromisoformat(body["process_start_time"])

    def test_health_reports_image_provider(self, client: TestClient):
        body = client.get("/health").json()
        assert "image_provider" in body
        assert body["image_provider"] == main._resolve_image_provider()

    def test_existing_health_behavior_unchanged(self, client: TestClient):
        body = client.get("/health").json()
        for field in ("status", "version", "uptime_seconds", "timestamp", "components"):
            assert field in body


class TestImageProviderResolution:
    def test_defaults_to_runway(self, monkeypatch):
        monkeypatch.delenv("DEFAULT_IMAGE_PROVIDER", raising=False)
        assert main._resolve_image_provider() == "runway"

    @pytest.mark.parametrize("alias", ["qwen", "qwen-image-max", "dashscope", "wanx"])
    def test_legacy_aliases_normalize_to_runway(self, monkeypatch, alias):
        monkeypatch.setenv("DEFAULT_IMAGE_PROVIDER", alias)
        assert main._resolve_image_provider() == "runway"


class TestStoryboardStartupTripwire:
    def test_current_tree_passes(self):
        assert main._assert_storyboard_runway_only() == "runway"

    def test_non_runway_canonical_refuses_to_boot(self, monkeypatch):
        import app.services.storyboard_image_service as service_module

        # The tripwire reads the constant via `from ... import`, so patch
        # the attribute on the defining module.
        monkeypatch.setattr(service_module, "CANONICAL_IMAGE_PROVIDER", "dashscope")
        with pytest.raises(RuntimeError, match="refusing to boot"):
            main._assert_storyboard_runway_only()
