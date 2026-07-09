from __future__ import annotations

from types import SimpleNamespace

from app.services.cinematic_timeline_intelligence_service import CinematicTimelineIntelligenceService


class _FakeStorage:
    def __init__(self):
        self.packages = []
        self.jobs = []
        self.continuity_issues = []
        self.style_drift_issues = []
        self.memories = []

    def list_final_short_film_packages_for_project(self, _project_id):
        return self.packages

    def list_jobs(self, project_id=None, limit=1000):  # noqa: ARG002
        return self.jobs

    def list_continuity_issues_for_project(self, _project_id):
        return self.continuity_issues

    def list_style_drift_issues_for_project(self, _project_id):
        return self.style_drift_issues

    def list_cinematic_memory_for_project(self, _project_id):
        return self.memories


def _job(*, shot_id: str, status: str = "complete", asset_url: str = "https://cdn.example.com/clip.mp4"):
    return SimpleNamespace(
        shot_id=shot_id,
        status=status,
        output_payload=SimpleNamespace(asset_url=asset_url),
    )


def _package(*, assembly_kind: str, final_output_url: str = "/outputs/final_films/test.mp4"):
    return SimpleNamespace(
        metadata={"assembly_kind": assembly_kind},
        final_output_url=final_output_url,
    )


def test_low_data_analysis_when_no_package_and_no_clips():
    storage = _FakeStorage()
    service = CinematicTimelineIntelligenceService(storage=storage)

    result = service.analyze_project_timeline("proj-a")

    assert result["assembly_kind"] == "none"
    assert result["clip_count"] == 0
    assert result["low_data_reason"]
    assert "No completed clips yet" in " ".join(result["advisory_notes"])


def test_single_clip_returns_preview_level_pacing_read():
    storage = _FakeStorage()
    storage.jobs = [_job(shot_id="scene_001_shot_001")]
    service = CinematicTimelineIntelligenceService(storage=storage)

    result = service.analyze_project_timeline("proj-a")

    assert result["clip_count"] == 1
    assert result["assembly_kind"] == "single_scene_preview"
    assert "preview" in result["pacing_read"].lower()


def test_manifest_package_returns_manifest_pacing_read():
    storage = _FakeStorage()
    storage.packages = [_package(assembly_kind="assembled_manifest", final_output_url="manifest://project")]
    storage.jobs = [
        _job(shot_id="scene_001_shot_001", asset_url="https://cdn.example.com/a.mp4"),
        _job(shot_id="scene_001_shot_002", asset_url="https://cdn.example.com/b.mp4"),
    ]
    service = CinematicTimelineIntelligenceService(storage=storage)

    result = service.analyze_project_timeline("proj-a")

    assert result["assembly_kind"] == "assembled_manifest"
    assert "manifest" in result["pacing_read"].lower()


def test_stitched_film_returns_final_film_read():
    storage = _FakeStorage()
    storage.packages = [_package(assembly_kind="stitched_film", final_output_url="/outputs/final_films/proj.mp4")]
    storage.jobs = [
        _job(shot_id="scene_001_shot_001", asset_url="https://cdn.example.com/a.mp4"),
        _job(shot_id="scene_001_shot_002", asset_url="https://cdn.example.com/b.mp4"),
        _job(shot_id="scene_001_shot_003", asset_url="https://cdn.example.com/c.mp4"),
    ]
    service = CinematicTimelineIntelligenceService(storage=storage)

    result = service.analyze_project_timeline("proj-a")

    assert result["assembly_kind"] == "stitched_film"
    assert "assembled movement" in " ".join(result["advisory_notes"]).lower()
    assert result["clip_count"] == 3


def test_result_has_no_numeric_scoring_fields():
    storage = _FakeStorage()
    storage.jobs = [_job(shot_id="scene_001_shot_001")]
    service = CinematicTimelineIntelligenceService(storage=storage)

    result = service.analyze_project_timeline("proj-a")
    serialized = str(result).lower()

    assert "confidence_score" not in result
    assert "pace_score" not in result
    assert "score:" not in serialized
    assert "percent" not in serialized


def test_continuity_style_memory_signals_influence_advisory_text():
    storage = _FakeStorage()
    storage.jobs = [
        _job(shot_id="scene_001_shot_001", asset_url="https://cdn.example.com/a.mp4"),
        _job(shot_id="scene_001_shot_002", asset_url="https://cdn.example.com/b.mp4"),
    ]
    storage.continuity_issues = [SimpleNamespace(issue_id="c1"), SimpleNamespace(issue_id="c2")]
    storage.style_drift_issues = [SimpleNamespace(issue_id="s1")]
    storage.memories = [SimpleNamespace(record_id="m1")]
    service = CinematicTimelineIntelligenceService(storage=storage)

    result = service.analyze_project_timeline("proj-a")
    flattened = " ".join(
        [result["pacing_read"], result["tension_curve"], result["tonal_consistency_read"], *result["advisory_notes"], *result["abrupt_transition_flags"], *result["emotional_residue_points"]]
    ).lower()

    assert "continuity" in flattened
    assert "style drift" in flattened
    assert "memory" in flattened
