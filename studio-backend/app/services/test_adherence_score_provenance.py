"""An adherence score must carry the identity of the model that produced it."""
from __future__ import annotations

from dataclasses import fields

from app.services.adherence_service import AdherenceScore, AdherenceService


def test_adherence_score_has_provenance_fields():
    names = {f.name for f in fields(AdherenceScore)}
    assert "scored_by_provider" in names
    assert "scored_by_model" in names


def test_openrouter_provider_has_no_default_model(monkeypatch):
    """A default id would silently point at a preview that may not exist."""
    monkeypatch.setenv("ADHERENCE_VISION_PROVIDER", "openrouter")
    monkeypatch.delenv("ADHERENCE_VISION_MODEL", raising=False)
    service = AdherenceService(storage=None)
    assert service._vision_provider == "openrouter"
    assert service._vision_model == ""


def test_qwen_provider_keeps_its_default(monkeypatch):
    monkeypatch.setenv("ADHERENCE_VISION_PROVIDER", "qwen")
    monkeypatch.delenv("ADHERENCE_VISION_MODEL", raising=False)
    service = AdherenceService(storage=None)
    assert service._vision_model == "qwen-vl-max"
