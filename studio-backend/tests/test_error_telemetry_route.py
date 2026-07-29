from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.errors import router


def _client():
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


class TestErrorTelemetryRoute:
    def test_accepts_valid_error_batch(self):
        client = _client()
        payload = {
            "errors": [
                {
                    "error_id": "test-123",
                    "timestamp": 1700000000000,
                    "message": "Something broke",
                    "url": "http://localhost:5000/studio/dashboard",
                    "user_agent": "Mozilla/5.0",
                    "build_version": "dev",
                    "level": "error",
                }
            ]
        }
        resp = client.post("/api/f51/studio/errors", json=payload)
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1

    def test_accepts_empty_batch(self):
        client = _client()
        resp = client.post("/api/f51/studio/errors", json={"errors": []})
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 0

    def test_accepts_multiple_errors(self):
        client = _client()
        payload = {
            "errors": [
                {
                    "error_id": f"err-{i}",
                    "timestamp": 1700000000000 + i,
                    "message": f"Error {i}",
                    "url": "http://localhost:5000",
                    "user_agent": "test",
                    "build_version": "dev",
                    "level": "error",
                }
                for i in range(10)
            ]
        }
        resp = client.post("/api/f51/studio/errors", json=payload)
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 10

    def test_accepts_fatal_level(self):
        client = _client()
        payload = {
            "errors": [
                {
                    "error_id": "fatal-1",
                    "timestamp": 1700000000000,
                    "message": "Fatal crash",
                    "url": "http://localhost:5000",
                    "user_agent": "test",
                    "build_version": "dev",
                    "level": "fatal",
                }
            ]
        }
        resp = client.post("/api/f51/studio/errors", json=payload)
        assert resp.status_code == 200

    def test_accepts_optional_fields(self):
        client = _client()
        payload = {
            "errors": [
                {
                    "error_id": "opt-1",
                    "timestamp": 1700000000000,
                    "message": "Minimal error",
                    "stack": "Error: ...\n  at line 1",
                    "component_stack": "at Dashboard",
                    "context": {"scene_id": "scene_001"},
                }
            ]
        }
        resp = client.post("/api/f51/studio/errors", json=payload)
        assert resp.status_code == 200

    def test_rejects_invalid_payload(self):
        client = _client()
        resp = client.post("/api/f51/studio/errors", json={"bad": "data"})
        assert resp.status_code == 422

    def test_rejects_missing_required_fields(self):
        client = _client()
        payload = {"errors": [{"error_id": "x"}]}
        resp = client.post("/api/f51/studio/errors", json=payload)
        assert resp.status_code == 422
