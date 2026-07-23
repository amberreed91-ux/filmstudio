"""Tests for ElevenLabs voice casting routes — proxy, get, set.

All ElevenLabs API calls are mocked — these tests never spend real credits.
Uses a temporary SQLite database for persistence tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.projects import router
from app.data.storage import DatabaseStorage


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch) -> DatabaseStorage:
    """Create a temp SQLite DB and patch get_storage to return it."""
    db_dir = tmp_path / "route_test_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    storage = DatabaseStorage(str(db_dir))
    monkeypatch.setattr("app.routes.projects.get_storage", lambda *a, **kw: storage)
    # Also patch _project_exists to return True for our test project
    monkeypatch.setattr("app.routes.projects._project_exists", lambda pid: True)
    return storage


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client with the projects router.

    The projects router already carries its own prefix ``/api/f51/studio``,
    so we include it without an additional prefix.
    """
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


class TestListElevenLabsVoices:
    """Proxy endpoint for ElevenLabs List Voices API."""

    def test_returns_voices_list(self, temp_db, client, monkeypatch):
        """Valid API response is normalized and returned."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-123")
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "voices": [
                {
                    "voice_id": "v1",
                    "name": "Rachel",
                    "category": "premade",
                    "preview_url": "https://example.test/preview1.mp3",
                    "labels": {"gender": "female", "age": "young", "accent": "american"},
                },
                {
                    "voice_id": "v2",
                    "name": "Adam",
                    "category": "premade",
                    "preview_url": "https://example.test/preview2.mp3",
                    "labels": {"gender": "male", "age": "middle aged", "accent": "british"},
                },
            ]
        }).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            response = client.get(
                "/api/f51/studio/projects/proj-1/elevenlabs/voices"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 2
        assert len(body["voices"]) == 2
        v1 = body["voices"][0]
        assert v1["voice_id"] == "v1"
        assert v1["name"] == "Rachel"
        assert v1["preview_url"] == "https://example.test/preview1.mp3"
        assert v1["labels"]["gender"] == "female"
        assert v1["labels"]["accent"] == "american"

    def test_category_filter(self, temp_db, client, monkeypatch):
        """Category query param filters the returned voices."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-123")
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "voices": [
                {
                    "voice_id": "v1",
                    "name": "Rachel",
                    "category": "premade",
                    "preview_url": "https://example.test/p1.mp3",
                    "labels": {"gender": "female", "age": "young", "accent": "american"},
                },
                {
                    "voice_id": "v2",
                    "name": "Cloned Voice",
                    "category": "cloned",
                    "preview_url": "https://example.test/p2.mp3",
                    "labels": {"gender": "male", "age": "old", "accent": "indian"},
                },
            ]
        }).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            response = client.get(
                "/api/f51/studio/projects/proj-1/elevenlabs/voices?category=premade"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["voices"][0]["voice_id"] == "v1"
        assert body["voices"][0]["category"] == "premade"

    def test_no_api_key_returns_503(self, temp_db, client, monkeypatch):
        """Missing ELEVENLABS_API_KEY returns 503."""
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        response = client.get(
            "/api/f51/studio/projects/proj-1/elevenlabs/voices"
        )
        assert response.status_code == 503
        assert "API key not configured" in response.json()["detail"]

    def test_api_error_returns_502(self, temp_db, client, monkeypatch):
        """ElevenLabs API HTTP error returns 502."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-123")
        import urllib.error
        mock_error = urllib.error.HTTPError(
            url="https://api.elevenlabs.io/v1/voices",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=mock_error):
            response = client.get(
                "/api/f51/studio/projects/proj-1/elevenlabs/voices"
            )
        assert response.status_code == 502

    def test_project_not_found(self, temp_db, client, monkeypatch):
        """Nonexistent project returns 404."""
        monkeypatch.setattr("app.routes.projects._project_exists", lambda pid: False)
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-123")
        response = client.get(
            "/api/f51/studio/projects/nonexistent/elevenlabs/voices"
        )
        assert response.status_code == 404


class TestGetCharacterVoice:
    """GET voice assignment route."""

    def test_get_voice_with_assignment(self, temp_db, client):
        """Returns the assigned voice for a character that has one."""
        created = temp_db.save_character("proj-1", "MARA", {})
        temp_db.set_character_voice(created["id"], "proj-1", "v123", "Rachel")
        response = client.get(
            f"/api/f51/studio/projects/proj-1/characters/{created['id']}/voice"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["character_id"] == created["id"]
        assert body["elevenlabs_voice_id"] == "v123"
        assert body["elevenlabs_voice_name"] == "Rachel"

    def test_get_voice_without_assignment(self, temp_db, client):
        """Returns null voice fields for a character with no assignment."""
        created = temp_db.save_character("proj-1", "ELI", {})
        response = client.get(
            f"/api/f51/studio/projects/proj-1/characters/{created['id']}/voice"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["elevenlabs_voice_id"] is None
        assert body["elevenlabs_voice_name"] is None

    def test_get_voice_nonexistent_character(self, temp_db, client):
        """Nonexistent character returns 404."""
        response = client.get(
            "/api/f51/studio/projects/proj-1/characters/fake-id/voice"
        )
        assert response.status_code == 404


class TestSetCharacterVoice:
    """PUT voice assignment route."""

    def test_set_voice_assignment(self, temp_db, client):
        """Setting a voice assignment persists and returns the updated values."""
        created = temp_db.save_character("proj-1", "MARA", {})
        response = client.put(
            f"/api/f51/studio/projects/proj-1/characters/{created['id']}/voice",
            json={"voice_id": "v789", "voice_name": "Adam"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["elevenlabs_voice_id"] == "v789"
        assert body["elevenlabs_voice_name"] == "Adam"
        # Verify persistence
        retrieved = temp_db.get_character_voice_by_name("proj-1", "MARA")
        assert retrieved == "v789"
        casting = temp_db.get_character_voice_casting_by_name("proj-1", "MARA", "elevenlabs")
        assert casting["voice_id"] == "v789"
        assert casting["voice_provider"] == "elevenlabs"

    def test_set_cosyvoice_casting_assignment(self, temp_db, client):
        """Setting a CosyVoice casting assignment persists provider-aware fields."""
        created = temp_db.save_character("proj-1", "DRE", {})
        response = client.put(
            f"/api/f51/studio/projects/proj-1/characters/{created['id']}/voice",
            json={
                "provider": "cosyvoice",
                "voice_id": "cosyvoice-dre-clone-001",
                "voice_name": "Dre clone",
                "source_type": "clone",
                "style_prompt": "warm, guarded Chicago cadence",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["voice_provider"] == "cosyvoice"
        assert body["voice_id"] == "cosyvoice-dre-clone-001"
        assert body["voice_source_type"] == "clone"
        assert body["voice_style_prompt"] == "warm, guarded Chicago cadence"
        assert body["elevenlabs_voice_id"] is None

    def test_rejects_unknown_casting_provider(self, temp_db, client):
        """Unknown voice provider is rejected before persistence."""
        created = temp_db.save_character("proj-1", "DRE", {})
        response = client.put(
            f"/api/f51/studio/projects/proj-1/characters/{created['id']}/voice",
            json={"provider": "unknown", "voice_id": "v1"},
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error_type"] == "validation_error"

    def test_update_voice_assignment(self, temp_db, client):
        """Updating an existing voice assignment replaces the old value."""
        created = temp_db.save_character("proj-1", "MARA", {})
        char_id = created["id"]
        client.put(
            f"/api/f51/studio/projects/proj-1/characters/{char_id}/voice",
            json={"voice_id": "v1", "voice_name": "First"},
        )
        response = client.put(
            f"/api/f51/studio/projects/proj-1/characters/{char_id}/voice",
            json={"voice_id": "v2", "voice_name": "Second"},
        )
        assert response.status_code == 200
        assert response.json()["elevenlabs_voice_id"] == "v2"
        assert response.json()["elevenlabs_voice_name"] == "Second"

    def test_clear_voice_assignment(self, temp_db, client):
        """Setting voice_id to empty string clears the assignment."""
        created = temp_db.save_character("proj-1", "ELI", {})
        char_id = created["id"]
        client.put(
            f"/api/f51/studio/projects/proj-1/characters/{char_id}/voice",
            json={"voice_id": "v1", "voice_name": "Test"},
        )
        response = client.put(
            f"/api/f51/studio/projects/proj-1/characters/{char_id}/voice",
            json={"voice_id": "", "voice_name": ""},
        )
        assert response.status_code == 200
        assert response.json()["elevenlabs_voice_id"] is None
        assert response.json()["elevenlabs_voice_name"] is None

    def test_set_voice_nonexistent_character(self, temp_db, client):
        """Setting voice on a nonexistent character returns 404."""
        response = client.put(
            "/api/f51/studio/projects/proj-1/characters/fake-id/voice",
            json={"voice_id": "v1", "voice_name": "Test"},
        )
        assert response.status_code == 404
