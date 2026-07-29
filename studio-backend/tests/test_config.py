from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings


class TestConfigDefaults:
    def test_admin_token_defaults_to_empty(self):
        s = Settings()
        assert s.admin_token == ""

    def test_rate_limit_default(self):
        s = Settings()
        assert s.rate_limit_per_minute == 120

    def test_demo_mode_defaults_to_false(self):
        s = Settings()
        assert s.demo_mode is False

    def test_backup_enabled_default(self):
        s = Settings()
        assert s.backup_enabled is True

    def test_cors_origins_default_empty(self):
        s = Settings()
        assert s.cors_origins == ""


class TestConfigFromEnv:
    def test_admin_token_reads_env(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "my-secret")
        s = Settings()
        assert s.admin_token == "my-secret"

    def test_rate_limit_reads_env(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "60")
        s = Settings()
        assert s.rate_limit_per_minute == 60

    def test_cors_origins_reads_env(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://example.com,https://app.example.com")
        s = Settings()
        assert "https://example.com" in s.cors_origins

    def test_demo_mode_reads_env(self, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        s = Settings()
        assert s.demo_mode is True
