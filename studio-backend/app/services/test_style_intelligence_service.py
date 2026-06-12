"""Tests for Style Drift + Director Signature v1.0."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import DirectorSignature, FrameAnalysisRecord, StyleDriftIssue, VideoAsset
from app.services.style_intelligence_service import StyleIntelligenceService


def _analysis(
    kid: str,
    aid: str,
    pid: str,
    *,
    mood=None,
    lighting=None,
    composition=None,
    palette=None,
    caption="",
    visual="",
):
    return FrameAnalysisRecord(
        analysis_id=f"analysis-{kid}",
        keyframe_id=kid,
        asset_id=aid,
        project_id=pid,
        mood_tags=mood or [],
        lighting_tags=lighting or [],
        composition_tags=composition or [],
        color_palette=palette or [],
        caption=caption,
        visual_summary=visual,
        confidence=0.85,
        provider="test",
        model="test",
        status="available",
        created_at="2026-01-01T00:00:00Z",
    )


class _MemStorage:
    def __init__(self) -> None:
        self.signatures: list[DirectorSignature] = []
        self.drifts: list[StyleDriftIssue] = []
        self.save_project_called = False

    def save_project(self, *_a, **_k):
        self.save_project_called = True

    def save_director_signature(self, sig: DirectorSignature) -> DirectorSignature:
        self.signatures.append(sig)
        return sig

    def list_director_signatures_for_project(self, project_id: str):
        return [s for s in self.signatures if s.project_id == project_id]

    def get_latest_director_signature(self, project_id: str):
        rows = [s for s in self.signatures if s.project_id == project_id]
        return sorted(rows, key=lambda s: s.created_at, reverse=True)[0] if rows else None

    def delete_style_drift_issues_for_project(self, project_id: str) -> int:
        before = len(self.drifts)
        self.drifts = [d for d in self.drifts if d.project_id != project_id]
        return before - len(self.drifts)

    def save_style_drift_issue(self, issue: StyleDriftIssue) -> StyleDriftIssue:
        self.drifts.append(issue)
        return issue

    def list_style_drift_issues_for_project(self, project_id: str):
        return [d for d in self.drifts if d.project_id == project_id]


class _FA:
    def __init__(self, by_project: dict[str, list[FrameAnalysisRecord]]):
        self._by = by_project

    def list_analyses_for_project(self, project_id: str):
        return list(self._by.get(project_id, []))


class _Mem:
    def __init__(self, rows=None):
        self._rows = rows or []

    def list_memory_for_project(self, project_id: str):
        return [m for m in self._rows if m.project_id == project_id]


class _VA:
    def __init__(self, assets: list[VideoAsset]):
        self._assets = assets

    def list_assets_for_project(self, project_id: str):
        return [a for a in self._assets if a.project_id == project_id]

    def get_asset(self, asset_id: str):
        for a in self._assets:
            if a.asset_id == asset_id:
                return a
        return None


def test_builds_director_signature_from_frame_analyses():
    storage = _MemStorage()
    pid = "proj-sig"
    analyses = [
        _analysis("kf1", "a1", pid, mood=["somber", "tense"], lighting=["low-key"]),
        _analysis("kf2", "a1", pid, mood=["somber", "melancholic"], lighting=["low-key"]),
        _analysis("kf3", "a2", pid, mood=["somber"], lighting=["low-key", "moonlit"]),
    ]
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    sig = svc.build_director_signature(pid)
    assert sig.metadata.get("insufficient_data") is False
    assert "somber" in sig.dominant_mood_tags
    assert "low-key" in sig.dominant_lighting_tags
    assert len(storage.signatures) == 1


def test_detects_lighting_drift():
    storage = _MemStorage()
    pid = "proj-light"
    analyses = []
    for i in range(5):
        analyses.append(
            _analysis(f"kf{i}", f"a{i}", pid, lighting=["moonlit", "underexposed"]),
        )
    analyses.append(_analysis("kf-out", "a-out", pid, lighting=["high-key", "bright"]))
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    sig = svc.build_director_signature(pid)
    assert sig.metadata.get("insufficient_data") is False
    res = svc.detect_style_drift(pid)
    assert res.get("insufficient_data") is False
    types = {i["drift_type"] for i in res.get("issues", [])}
    assert "lighting_drift" in types


def test_detects_mood_drift():
    storage = _MemStorage()
    pid = "proj-mood"
    analyses = []
    for i in range(5):
        analyses.append(_analysis(f"k{i}", f"a{i}", pid, mood=["anxious", "claustrophobic"]))
    analyses.append(_analysis("k-out", "a-x", pid, mood=["euphoric", "celebratory"]))
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    svc.build_director_signature(pid)
    res = svc.detect_style_drift(pid)
    assert any(i["drift_type"] == "mood_drift" for i in res.get("issues", []))


def test_detects_composition_drift():
    storage = _MemStorage()
    pid = "proj-comp"
    analyses = []
    for i in range(5):
        analyses.append(_analysis(f"k{i}", f"a{i}", pid, composition=["symmetry", "centered"]))
    analyses.append(_analysis("k-out", "a-x", pid, composition=["handheld", "chaotic"]))
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    svc.build_director_signature(pid)
    res = svc.detect_style_drift(pid)
    assert any(i["drift_type"] == "composition_drift" for i in res.get("issues", []))


def test_detects_palette_drift():
    storage = _MemStorage()
    pid = "proj-pal"
    analyses = []
    for i in range(5):
        analyses.append(_analysis(f"k{i}", f"a{i}", pid, palette=["#0a0a12", "#1a1030"]))
    analyses.append(_analysis("k-out", "a-x", pid, palette=["#fffaf0", "#ffe4c4"]))
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    svc.build_director_signature(pid)
    res = svc.detect_style_drift(pid)
    assert any(i["drift_type"] == "palette_drift" for i in res.get("issues", []))


def test_no_fake_drift_when_data_insufficient():
    storage = _MemStorage()
    pid = "proj-thin"
    analyses = [_analysis("k1", "a1", pid, lighting=["low-key"]), _analysis("k2", "a2", pid, lighting=["high-key"])]
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    sig = svc.build_director_signature(pid)
    assert sig.metadata.get("insufficient_data") is True
    res = svc.detect_style_drift(pid)
    assert res.get("issues") == []


def test_project_isolation():
    storage = _MemStorage()
    p_a = "proj-a"
    p_b = "proj-b"
    a_analyses = []
    for i in range(5):
        a_analyses.append(_analysis(f"a{i}", f"ax{i}", p_a, lighting=["cool"]))
    a_analyses.append(_analysis("a-out", "axz", p_a, lighting=["warm", "golden-hour"]))
    b_analyses = [_analysis("b1", "b1", p_b, lighting=["flat"])]
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({p_a: a_analyses, p_b: b_analyses}),
        cinematic_memory_service=_Mem([]),
    )
    svc.build_director_signature(p_a)
    svc.detect_style_drift(p_a)
    drifts_b = svc.list_style_drift_issues(p_b)
    assert drifts_b == []


def test_advisory_only_no_canonical_project_mutation():
    storage = _MemStorage()
    pid = "proj-safe"
    analyses = [_analysis(f"k{i}", f"a{i}", pid, mood=["x"]) for i in range(5)]
    svc = StyleIntelligenceService(
        storage=storage,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    svc.build_director_signature(pid)
    svc.detect_style_drift(pid)
    assert storage.save_project_called is False


def test_sqlite_migration_and_roundtrip(tmp_path: Path):
    from app.data.storage import DatabaseStorage
    from app.models import StudioProject

    db = DatabaseStorage(str(tmp_path / "db"))
    pid = "proj-db-style"
    db.save_project(StudioProject(project_id=pid, title="Style Test"))
    analyses = []
    for i in range(5):
        analyses.append(
            _analysis(f"kf{i}", f"asset{i}", pid, lighting=["tungsten", "practical"]),
        )
    analyses.append(_analysis("kf5", "asset5", pid, lighting=["daylight", "overexposed"]))
    svc = StyleIntelligenceService(
        storage=db,
        frame_analysis_service=_FA({pid: analyses}),
        cinematic_memory_service=_Mem([]),
    )
    sig = svc.build_director_signature(pid)
    assert sig.signature_id
    svc.detect_style_drift(pid)
    loaded = db.list_style_drift_issues_for_project(pid)
    assert isinstance(loaded, list)
