from __future__ import annotations

from types import SimpleNamespace

from app.services.editorial_revision_intelligence_service import EditorialRevisionIntelligenceService


class _FakeStorage:
    def __init__(self):
        self.jobs = []
        self.continuity_issues = []
        self.style_drift_issues = []
        self.memories = []
        self.packages = []
        self.scene_compositions = []

    def list_jobs(self, project_id=None, limit=1000):  # noqa: ARG002
        return self.jobs

    def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, title="Revision Test Film")

    def list_scene_compositions_for_project(self, _project_id):
        return self.scene_compositions

    def list_video_frame_analyses_for_project(self, _project_id):
        return []

    def list_continuity_issues_for_project(self, _project_id):
        return self.continuity_issues

    def list_style_drift_issues_for_project(self, _project_id):
        return self.style_drift_issues

    def list_cinematic_memory_for_project(self, _project_id):
        return self.memories

    def list_final_short_film_packages_for_project(self, _project_id):
        return self.packages


def _job(revision_id: str, shot_id: str, created_at: str, status: str = "complete", url: str = "https://cdn.example.com/x.mp4"):
    return SimpleNamespace(
        id=revision_id,
        shot_id=shot_id,
        created_at=created_at,
        status=status,
        output_payload=SimpleNamespace(asset_url=url, metadata={}),
    )


def test_low_data_fallback():
    svc = EditorialRevisionIntelligenceService(storage=_FakeStorage())
    out = svc.compare_revisions("proj-x")
    assert out["baseline_revision_id"] == ""
    assert out["uncertainty_note"]
    assert "low-data" in out["uncertainty_note"].lower()


def test_stitched_revisions_compare_successfully():
    store = _FakeStorage()
    store.jobs = [
        _job("rev-a", "scene_001_shot_001", "2026-05-20T00:00:00Z"),
        _job("rev-b", "scene_001_shot_002", "2026-05-20T00:01:00Z"),
    ]
    store.packages = [SimpleNamespace(metadata={"assembly_kind": "stitched_film"})]
    svc = EditorialRevisionIntelligenceService(storage=store)
    out = svc.compare_revisions("proj-x", baseline_revision_id="rev-a", comparison_revision_id="rev-b")
    assert out["baseline_revision_id"] == "rev-a"
    assert out["comparison_revision_id"] == "rev-b"
    assert out["strongest_difference"]


def test_no_numeric_scoring_fields():
    store = _FakeStorage()
    store.jobs = [
        _job("rev-a", "scene_001_shot_001", "2026-05-20T00:00:00Z"),
        _job("rev-b", "scene_001_shot_002", "2026-05-20T00:01:00Z"),
    ]
    svc = EditorialRevisionIntelligenceService(storage=store)
    out = svc.compare_revisions("proj-x")
    blob = str(out).lower()
    assert "score" not in blob
    assert "%" not in blob


def test_advisory_language_only():
    store = _FakeStorage()
    store.jobs = [
        _job("rev-a", "scene_001_shot_001", "2026-05-20T00:00:00Z"),
        _job("rev-b", "scene_001_shot_002", "2026-05-20T00:01:00Z"),
    ]
    svc = EditorialRevisionIntelligenceService(storage=store)
    out = svc.compare_revisions("proj-x")
    joined = " ".join(out["advisory_notes"]).lower()
    assert "must" not in joined
    assert "objective" not in joined


def test_revision_emphasis_influences_wording():
    store = _FakeStorage()
    store.jobs = [
        _job("rev-a", "scene_001_shot_001", "2026-05-20T00:00:00Z"),
        _job("rev-b", "scene_001_shot_002", "2026-05-20T00:01:00Z"),
    ]
    svc = EditorialRevisionIntelligenceService(storage=store)
    emo = svc.compare_revisions("proj-x", revision_emphasis="emotional_residue")
    struct = svc.compare_revisions("proj-x", revision_emphasis="structural_clarity")
    assert emo["strongest_difference"] != struct["strongest_difference"]
    assert "emotion" in emo["strongest_difference"].lower()
    assert "readability" in struct["strongest_difference"].lower() or "structural" in struct["structural_clarity_tradeoff"].lower()


def test_uncertainty_note_present_when_signals_thin():
    store = _FakeStorage()
    store.jobs = [
        _job("rev-a", "scene_001_shot_001", "2026-05-20T00:00:00Z"),
        _job("rev-b", "scene_001_shot_001", "2026-05-20T00:01:00Z"),
    ]
    svc = EditorialRevisionIntelligenceService(storage=store)
    out = svc.compare_revisions("proj-x")
    assert out["uncertainty_note"]


def test_revision_comparison_includes_canonical_editorial_analysis_when_available():
    store = _FakeStorage()
    store.jobs = [
        _job("rev-a", "scene_001_shot_001", "2026-05-20T00:00:00Z"),
        _job("rev-b", "scene_002_shot_001", "2026-05-20T00:01:00Z"),
    ]
    store.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    store.continuity_issues = [SimpleNamespace(issue_id="continuity-1")]
    svc = EditorialRevisionIntelligenceService(storage=store)
    out = svc.compare_revisions("proj-x", baseline_revision_id="rev-a", comparison_revision_id="rev-b")
    canonical = out["canonical_editorial_analysis"]
    assert canonical["analysis_id"].startswith("editorial-analysis-")
    assert canonical["primary_pacing_read"]
    assert any("Canonical editorial analysis" in note for note in out["advisory_notes"])
