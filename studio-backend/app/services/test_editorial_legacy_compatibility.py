from __future__ import annotations

from types import SimpleNamespace

from app.services.cinematic_timeline_intelligence_service import CinematicTimelineIntelligenceService
from app.services.editing_intelligence_service import EditingIntelligenceService


class _FakeStorage:
    def __init__(self):
        self.scene_compositions = [
            {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
            {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
        ]
        self.jobs = []
        self.packages = []
        self.continuity_issues = [SimpleNamespace(issue_id="continuity-1")]
        self.style_drift_issues = []
        self.memories = [SimpleNamespace(memory_id="memory-1", summary="A recurring stillness motif.")]
        self.frame_analyses = []

    def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, title="Test Film")

    def list_scene_compositions_for_project(self, project_id):  # noqa: ARG002
        return self.scene_compositions

    def list_jobs(self, project_id=None, limit=1000):  # noqa: ARG002
        return self.jobs

    def list_final_short_film_packages_for_project(self, project_id):  # noqa: ARG002
        return self.packages

    def list_continuity_issues_for_project(self, project_id):  # noqa: ARG002
        return self.continuity_issues

    def list_style_drift_issues_for_project(self, project_id):  # noqa: ARG002
        return self.style_drift_issues

    def list_cinematic_memory_for_project(self, project_id):  # noqa: ARG002
        return self.memories

    def list_video_frame_analyses_for_project(self, project_id):  # noqa: ARG002
        return self.frame_analyses


def test_timeline_intelligence_uses_canonical_editorial_read():
    service = CinematicTimelineIntelligenceService(storage=_FakeStorage())
    out = service.analyze_project_timeline("project-x")
    assert out["clip_count"] == 2
    assert out["pacing_read"]
    assert out["abrupt_transition_flags"]
    assert any("Generated advisory edit decisions" in note for note in out["advisory_notes"])


def test_legacy_editing_suggestions_do_not_emit_scores_or_percentages():
    service = EditingIntelligenceService()
    out = service.build_editing_intelligence(
        screening_playlist=[{"scene_id": "scene_001"}, {"scene_id": "scene_002"}, {"scene_id": "scene_003"}],
        scene_transitions=[{"transition": "hold"}, {"transition": "hold"}],
        emotional_continuity={"score": 0.1},
        sequence_flow={"issues": ["middle handoff drags"]},
    )
    blob = str(out).lower()
    assert "%" not in blob
    assert "8/10" not in blob
    assert "rating" not in blob
