from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.editorial_intelligence import (
    EditorialAnalysisRecord,
    EditorialApplyResult,
    EditorialEmotionalFlowDiagnostic,
)
from app.routes import editorial_intelligence as route_module


class _FakeEditorialService:
    def __init__(self):
        self.apply_error = None
        self.analysis_missing = False
        self.analysis = EditorialAnalysisRecord(
            analysis_id="analysis-1",
            project_id="project-x",
            source_cut_id="cut-a",
            context_hash="hash-a",
            overall_read="The cut has a readable editorial pulse.",
            emotional_flow=EditorialEmotionalFlowDiagnostic(
                read="Emotion carries across the available beats.",
                tension_curve="Draft escalation is legible.",
                emotional_residue="The ending leaves room for feeling to settle.",
            ),
        )

    def analyze_project(self, project_id, request=None):  # noqa: ARG002
        return self.analysis

    def latest_analysis(self, project_id):  # noqa: ARG002
        return self.analysis

    def list_analyses(self, project_id, limit=20):  # noqa: ARG002
        return [self.analysis]

    def get_analysis(self, analysis_id):  # noqa: ARG002
        return self.analysis

    def list_applications(self, project_id, limit=20):  # noqa: ARG002
        return [
            EditorialApplyResult(
                application_id="application-1",
                project_id=project_id,
                analysis_id="analysis-1",
                decision_ids=["decision-1"],
                source_cut_id="cut-a",
                application_status="applied",
                applied_effects=["Recorded selected editorial decisions as advisory metadata."],
            )
        ]

    def apply_decisions(self, project_id, analysis_id, request):  # noqa: ARG002
        if self.apply_error:
            raise self.apply_error
        return EditorialApplyResult(
            application_id="application-1",
            project_id=project_id,
            analysis_id=analysis_id,
            decision_ids=request.decision_ids,
            source_cut_id="cut-a",
            application_status="applied",
            applied_effects=["Recorded selected editorial decisions as advisory metadata."],
        )


def _client(monkeypatch, service=None):
    service = service or _FakeEditorialService()
    monkeypatch.setattr(route_module, "editorial_intelligence_service", service)
    app = FastAPI()
    app.include_router(route_module.router)
    return TestClient(app), service


def test_analyze_editorial_intelligence_route(monkeypatch):
    client, _service = _client(monkeypatch)
    response = client.post("/api/f51/studio/projects/project-x/editorial-intelligence/analyze", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["analysis_id"] == "analysis-1"
    assert payload["analysis"]["advisory_only"] is True


def test_latest_editorial_intelligence_route(monkeypatch):
    client, _service = _client(monkeypatch)
    response = client.get("/api/f51/studio/projects/project-x/editorial-intelligence/latest")
    assert response.status_code == 200
    assert response.json()["analysis"]["overall_read"]


def test_list_and_get_editorial_intelligence_routes(monkeypatch):
    client, _service = _client(monkeypatch)
    listed = client.get("/api/f51/studio/projects/project-x/editorial-intelligence")
    fetched = client.get("/api/f51/studio/projects/project-x/editorial-intelligence/analysis-1")
    applications = client.get("/api/f51/studio/projects/project-x/editorial-intelligence/applications")
    assert listed.status_code == 200
    assert listed.json()["analyses"][0]["analysis_id"] == "analysis-1"
    assert fetched.status_code == 200
    assert fetched.json()["analysis"]["analysis_id"] == "analysis-1"
    assert applications.status_code == 200
    assert applications.json()["applications"][0]["application_id"] == "application-1"


def test_apply_editorial_decisions_route(monkeypatch):
    client, _service = _client(monkeypatch)
    response = client.post(
        "/api/f51/studio/projects/project-x/editorial-intelligence/analysis-1/apply",
        json={
            "decision_ids": ["decision-1"],
            "apply_mode": "metadata_only",
            "expected_context_hash": "hash-a",
            "creator_confirmation": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["application_status"] == "applied"


def test_apply_editorial_decisions_route_requires_confirmation(monkeypatch):
    service = _FakeEditorialService()
    service.apply_error = ValueError("creator_confirmation is required before applying editorial decisions")
    client, _service = _client(monkeypatch, service)
    response = client.post(
        "/api/f51/studio/projects/project-x/editorial-intelligence/analysis-1/apply",
        json={
            "decision_ids": ["decision-1"],
            "apply_mode": "metadata_only",
            "expected_context_hash": "hash-a",
            "creator_confirmation": False,
        },
    )
    assert response.status_code == 400
    assert "creator_confirmation" in response.json()["detail"]


def test_apply_editorial_decisions_route_returns_conflict_for_stale_context(monkeypatch):
    service = _FakeEditorialService()
    service.apply_error = RuntimeError("stale_editorial_analysis")
    client, _service = _client(monkeypatch, service)
    response = client.post(
        "/api/f51/studio/projects/project-x/editorial-intelligence/analysis-1/apply",
        json={
            "decision_ids": ["decision-1"],
            "apply_mode": "metadata_only",
            "expected_context_hash": "stale",
            "creator_confirmation": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "stale_editorial_analysis"


def test_apply_editorial_decisions_route_returns_not_found(monkeypatch):
    service = _FakeEditorialService()
    service.apply_error = LookupError("Editorial analysis not found")
    client, _service = _client(monkeypatch, service)
    response = client.post(
        "/api/f51/studio/projects/project-x/editorial-intelligence/missing/apply",
        json={
            "decision_ids": ["decision-1"],
            "apply_mode": "metadata_only",
            "expected_context_hash": "hash-a",
            "creator_confirmation": True,
        },
    )
    assert response.status_code == 404
