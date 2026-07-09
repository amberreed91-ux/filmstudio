from __future__ import annotations

from types import SimpleNamespace

from app.services.studio_decision_gate_service import StudioDecisionGateService


class StubStorage:
    def __init__(self):
        self.project_state_mutated = False
        self.assets = []
        self.keyframes = []
        self.analyses = []
        self.embeddings = []
        self.memories = []
        self.continuity = []
        self.style_drift = []
        self.signatures = []
        self.jobs = []
        self.reviews = []
        self.revisions = []
        self.packages = []

    def list_video_assets_for_project(self, _project_id):
        return self.assets

    def list_video_keyframes_for_project(self, _project_id):
        return self.keyframes

    def list_frame_analyses_for_project(self, _project_id):
        return self.analyses

    def list_visual_embeddings_for_project(self, _project_id):
        return self.embeddings

    def list_cinematic_memory_for_project(self, _project_id):
        return self.memories

    def list_continuity_issues_for_project(self, _project_id):
        return self.continuity

    def list_style_drift_issues_for_project(self, _project_id):
        return self.style_drift

    def list_director_signatures_for_project(self, _project_id):
        return self.signatures

    def list_jobs(self, project_id=None, limit=1000):
        assert project_id is not None
        assert limit == 1000
        return self.jobs

    def list_reviews_for_project(self, _project_id):
        return self.reviews

    def list_clip_revisions_for_project(self, _project_id):
        return self.revisions

    def list_final_short_film_packages_for_project(self, _project_id):
        return self.packages

    # Explicitly fail if service tries to mutate canonical project state.
    def save_project(self, *_args, **_kwargs):
        self.project_state_mutated = True
        raise AssertionError("Decision gate must not mutate project state")


JOB = lambda status, url=None: SimpleNamespace(status=status, output_payload=SimpleNamespace(asset_url=url) if url else None)
REVIEW = lambda decision: SimpleNamespace(decision=decision)
REVISION = lambda status: SimpleNamespace(status=status)
PACKAGE = lambda status: SimpleNamespace(package_status=status)


def test_insufficient_data_project():
    storage = StubStorage()
    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.gate_status == "insufficient_data"
    assert gate.current_stage == "intake"
    assert "Not enough project data yet" in gate.recommended_next_action


def test_failed_render_blocks_project():
    storage = StubStorage()
    storage.jobs = [JOB("failed")]

    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.gate_status == "blocked"
    assert any("failed render" in msg.lower() for msg in gate.blockers)


def test_completed_renders_without_review_needs_review():
    storage = StubStorage()
    storage.assets = [SimpleNamespace(asset_id="a1")]
    storage.jobs = [JOB("complete", "https://example.com/clip.mp4")]

    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.gate_status == "needs_review"
    assert "ready for approval" in gate.recommended_next_action.lower()


def test_approved_review_plus_package_ready():
    storage = StubStorage()
    storage.assets = [SimpleNamespace(asset_id="a1")]
    storage.jobs = [JOB("complete", "https://example.com/clip.mp4")]
    storage.reviews = [REVIEW("approved")]
    storage.packages = [PACKAGE("approved")]

    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.gate_status == "ready"
    assert "approved cut can be packaged" in gate.recommended_next_action.lower()


def test_rejected_review_blocks_project():
    storage = StubStorage()
    storage.assets = [SimpleNamespace(asset_id="a1")]
    storage.jobs = [JOB("complete", "https://example.com/clip.mp4")]
    storage.reviews = [REVIEW("rejected")]

    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.gate_status == "blocked"
    assert any("rejected" in msg.lower() for msg in gate.blockers)


def test_continuity_and_style_drift_create_warnings_not_automatic_block():
    storage = StubStorage()
    storage.assets = [SimpleNamespace(asset_id="a1")]
    storage.jobs = [JOB("complete", "https://example.com/clip.mp4")]
    storage.continuity = [SimpleNamespace(issue_id="c1")]
    storage.style_drift = [SimpleNamespace(drift_id="s1")]

    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.gate_status == "needs_review"
    assert len(gate.warnings) >= 2
    assert not gate.blockers


def test_no_canonical_project_mutation():
    storage = StubStorage()
    storage.assets = [SimpleNamespace(asset_id="a1")]

    gate = StudioDecisionGateService(storage=storage).evaluate_project_gate("proj-1")

    assert gate.metadata.get("canonical_state_mutated") is False
    assert storage.project_state_mutated is False
