from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_field(self, client: TestClient):
        body = client.get("/health").json()
        assert "status" in body
        assert body["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_has_version(self, client: TestClient):
        body = client.get("/health").json()
        assert "version" in body

    def test_health_has_uptime(self, client: TestClient):
        body = client.get("/health").json()
        assert "uptime_seconds" in body
        assert body["uptime_seconds"] >= 0

    def test_health_has_components(self, client: TestClient):
        body = client.get("/health").json()
        assert "components" in body
        components = body["components"]
        assert "database" in components
        assert "render_service" in components
        assert "production_queue" in components
        assert "circuit_breakers" in components
        assert "background_tasks" in components

    def test_health_database_component_has_status(self, client: TestClient):
        body = client.get("/health").json()
        db = body["components"]["database"]
        assert db["status"] == "ok"
        assert "latency_ms" in db
        assert db["latency_ms"] is not None
        assert db["latency_ms"] > 0


class TestReadinessEndpoint:
    def test_ready_returns_200_when_healthy(self, client: TestClient):
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_ready_has_ready_field(self, client: TestClient):
        body = client.get("/ready").json()
        assert "ready" in body
        assert isinstance(body["ready"], bool)

    def test_ready_has_components(self, client: TestClient):
        body = client.get("/ready").json()
        assert "components" in body
        assert "database" in body["components"]
        assert "schema" in body["components"]
        assert "background_tasks" in body["components"]

    def test_ready_has_timestamp(self, client: TestClient):
        body = client.get("/ready").json()
        assert "timestamp" in body
        assert body["timestamp"] > 0

    def test_ready_database_is_ready(self, client: TestClient):
        body = client.get("/ready").json()
        assert body["components"]["database"] == "ready"

    def test_ready_schema_reports_version(self, client: TestClient):
        body = client.get("/ready").json()
        schema = body["components"]["schema"]
        assert schema.startswith("ready (v")
