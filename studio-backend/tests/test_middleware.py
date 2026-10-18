from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_id import RequestIDMiddleware
from app.middleware.structured_logging import StructuredLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware


class TestRequestIDMiddleware:
    def test_adds_request_id_header_to_response(self):
        api = FastAPI()
        api.add_middleware(RequestIDMiddleware)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    def test_preserves_provided_request_id(self):
        api = FastAPI()
        api.add_middleware(RequestIDMiddleware)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        resp = client.get("/test", headers={"X-Request-ID": "my-custom-id"})
        assert resp.headers["X-Request-ID"] == "my-custom-id"

    def test_generates_unique_ids_per_request(self):
        api = FastAPI()
        api.add_middleware(RequestIDMiddleware)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        ids = set()
        for _ in range(20):
            resp = client.get("/test")
            ids.add(resp.headers["X-Request-ID"])
        assert len(ids) == 20


class TestStructuredLoggingMiddleware:
    def test_requests_complete_without_error(self):
        api = FastAPI()
        api.add_middleware(RequestIDMiddleware)
        api.add_middleware(StructuredLoggingMiddleware)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_404_still_logged(self):
        api = FastAPI()
        api.add_middleware(RequestIDMiddleware)
        api.add_middleware(StructuredLoggingMiddleware)

        @api.get("/exists")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        resp = client.get("/not-exists")
        assert resp.status_code == 404


class TestRateLimitMiddleware:
    def test_allows_requests_under_limit(self):
        api = FastAPI()
        api.add_middleware(RateLimitMiddleware, requests_per_minute=10)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        for _ in range(5):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_blocks_requests_over_limit(self):
        api = FastAPI()
        api.add_middleware(RateLimitMiddleware, requests_per_minute=5)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        for _ in range(5):
            resp = client.get("/test")
            assert resp.status_code == 200

        resp = client.get("/test")
        assert resp.status_code == 429
        assert resp.json()["error"] == "rate_limit_exceeded"
        assert "retry_after_seconds" in resp.json()
        assert "Retry-After" in resp.headers

    def test_rate_limit_resets_after_window(self, monkeypatch):
        api = FastAPI()
        api.add_middleware(RateLimitMiddleware, requests_per_minute=3)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        fake_time = [1000.0]
        monkeypatch.setattr(time, "time", lambda: fake_time[0])

        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200

        resp = client.get("/test")
        assert resp.status_code == 429

        fake_time[0] += 61.0
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_health_and_ready_bypass_rate_limit(self):
        api = FastAPI()
        api.add_middleware(RateLimitMiddleware, requests_per_minute=2)

        @api.get("/health")
        async def health():
            return {"status": "ok"}

        @api.get("/ready")
        async def ready():
            return {"ready": True}

        client = TestClient(api)
        for _ in range(10):
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200

    def test_options_requests_bypass_rate_limit(self):
        api = FastAPI()
        api.add_middleware(RateLimitMiddleware, requests_per_minute=2)

        @api.options("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        for _ in range(10):
            resp = client.options("/test")
            assert resp.status_code == 200

    def test_rate_limit_headers_present(self):
        api = FastAPI()
        api.add_middleware(RateLimitMiddleware, requests_per_minute=10)

        @api.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(api)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert "X-RateLimit-Remaining" in resp.headers


def test_polling_and_creator_actions_have_independent_budgets():
    api = FastAPI()
    api.add_middleware(RateLimitMiddleware, requests_per_minute=1, read_requests_per_minute=3)

    @api.get('/room')
    async def read_room():
        return {'ok': True}

    @api.post('/save')
    async def save():
        return {'ok': True}

    client = TestClient(api)
    for _ in range(3):
        assert client.get('/room').status_code == 200
    assert client.get('/room').status_code == 429
    assert client.post('/save').status_code == 200
    assert client.post('/save').status_code == 429
