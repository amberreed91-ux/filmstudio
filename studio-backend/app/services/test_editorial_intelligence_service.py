from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.data.storage import DatabaseStorage
from app.models.editorial_intelligence import EditorialAnalysisRequest, EditorialApplyRequest, EditorialDecision
from app.services.editorial_intelligence_service import EditorialIntelligenceService
from app.services.editorial_timeline_context_service import EditorialTimelineContextService


class _FakeStorage:
    def __init__(self):
        self.jobs = []
        self.scene_compositions = []
        self.packages = []
        self.video_assets = []
        self.video_keyframes = []
        self.shot_boundaries_by_asset = {}
        self.continuity_issues = []
        self.style_drift_issues = []
        self.memories = []
        self.frame_analyses = []
        self.analyses = {}
        self.applications = {}

    def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, title="Test Film")

    def list_jobs(self, project_id=None, limit=1000):  # noqa: ARG002
        return self.jobs

    def list_scene_compositions_for_project(self, project_id):  # noqa: ARG002
        return self.scene_compositions

    def list_final_short_film_packages_for_project(self, project_id):  # noqa: ARG002
        return self.packages

    def list_video_assets_for_project(self, project_id):  # noqa: ARG002
        return self.video_assets

    def list_video_keyframes_for_project(self, project_id):  # noqa: ARG002
        return self.video_keyframes

    def list_shot_boundaries_for_asset(self, asset_id):
        return self.shot_boundaries_by_asset.get(asset_id, [])

    def list_continuity_issues_for_project(self, project_id):  # noqa: ARG002
        return self.continuity_issues

    def list_style_drift_issues_for_project(self, project_id):  # noqa: ARG002
        return self.style_drift_issues

    def list_cinematic_memory_for_project(self, project_id):  # noqa: ARG002
        return self.memories

    def list_video_frame_analyses_for_project(self, project_id):  # noqa: ARG002
        return self.frame_analyses

    def save_editorial_analysis_record(self, record):
        self.analyses[record.analysis_id] = record
        return record

    def get_editorial_analysis_record(self, analysis_id):
        return self.analyses.get(analysis_id)

    def get_latest_editorial_analysis_record(self, project_id):
        rows = [row for row in self.analyses.values() if row.project_id == project_id]
        return rows[-1] if rows else None

    def list_editorial_analysis_records_for_project(self, project_id, limit=20):
        return [row for row in self.analyses.values() if row.project_id == project_id][-limit:]

    def save_editorial_decision_application(self, application):
        self.applications[application.application_id] = application
        return application

    def list_editorial_decision_applications_for_project(self, project_id, limit=20):
        return [row for row in self.applications.values() if row.project_id == project_id][-limit:]


class _FakeProjectStore:
    def __init__(self):
        self.project = {
            "project_id": "project-x",
            "title": "Test Film",
            "film_cut": {
                "cut_id": "cut-a",
                "scene_order": ["scene_001", "scene_002"],
                "included_scenes": ["scene_001", "scene_002"],
                "excluded_scenes": [],
                "created_at": "2026-07-27T00:00:00Z",
            },
        }

    def get_project(self, project_id):
        if project_id == self.project["project_id"]:
            return dict(self.project)
        return None

    def save_project(self, project):
        self.project = dict(project)
        return self.project


def _service(storage=None, project_store=None):
    storage = storage or _FakeStorage()
    project_store = project_store or _FakeProjectStore()
    context = EditorialTimelineContextService(storage=storage, project_store_service=project_store)
    return EditorialIntelligenceService(storage=storage, context_service=context, project_store_service=project_store)


def test_low_data_analysis_is_advisory_and_persisted():
    storage = _FakeStorage()
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    assert analysis.analysis_status == "low_data"
    assert analysis.advisory_only is True
    assert analysis.low_data_reasons
    assert analysis.analysis_id in storage.analyses


def test_continuity_pressure_generates_transition_decision():
    storage = _FakeStorage()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    storage.continuity_issues = [SimpleNamespace(issue_id="continuity-1")]
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    assert analysis.transition_advisories
    assert analysis.transition_advisories[0].recommended_transition_type == "hold_then_cut"
    assert any(decision.decision_type == "replace_transition" for decision in analysis.edit_decisions)


def test_apply_to_next_stitch_persists_application_metadata():
    storage = _FakeStorage()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    storage.style_drift_issues = [SimpleNamespace(issue_id="style-1")]
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    decision_ids = [row.decision_id for row in analysis.edit_decisions if row.decision_type == "replace_transition"]
    result = svc.apply_decisions(
        "project-x",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=decision_ids,
            apply_mode="next_stitch",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    assert result.application_status == "applied"
    assert result.metadata["transition_advisories"]
    assert svc.latest_transition_advisories_for_stitch("project-x")


def test_apply_to_next_stitch_persists_timing_adjustments_for_hold_decision():
    storage = _FakeStorage()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    decision_ids = [row.decision_id for row in analysis.edit_decisions if row.decision_type == "hold"]
    assert decision_ids
    result = svc.apply_decisions(
        "project-x",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=decision_ids,
            apply_mode="next_stitch",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    assert result.skipped_decisions == []
    adjustments = result.metadata["timing_adjustments"]
    assert adjustments[0]["adjustment_type"] == "tail_hold"
    assert svc.latest_stitch_plan("project-x")["timing_adjustments"]


def test_style_drift_generates_executable_trim_decision_for_next_stitch():
    storage = _FakeStorage()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    storage.style_drift_issues = [SimpleNamespace(issue_id="style-1")]
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    decision_ids = [row.decision_id for row in analysis.edit_decisions if row.decision_type == "trim"]
    assert decision_ids
    result = svc.apply_decisions(
        "project-x",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=decision_ids,
            apply_mode="next_stitch",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    adjustments = result.metadata["timing_adjustments"]
    assert adjustments[0]["adjustment_type"] == "tail_trim"
    assert "bounded trim" in result.applied_effects[0]


def test_apply_rejects_stale_context():
    storage = _FakeStorage()
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    with pytest.raises(RuntimeError):
        svc.apply_decisions(
            "project-x",
            analysis.analysis_id,
            EditorialApplyRequest(
                decision_ids=[analysis.edit_decisions[0].decision_id],
                apply_mode="metadata_only",
                expected_context_hash="stale",
                creator_confirmation=True,
            ),
        )


def test_update_cut_applies_valid_reorder_to_canonical_film_cut():
    storage = _FakeStorage()
    project_store = _FakeProjectStore()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    svc = _service(storage=storage, project_store=project_store)
    analysis = svc.analyze_project("project-x")
    reorder = EditorialDecision(
        decision_id="decision-reorder-final-first",
        decision_type="reorder_scene",
        target_type="sequence",
        target_id="timeline",
        recommendation="Move the second scene before the first only for this structural clarity pass.",
        rationale="This reorder tests whether the reveal carries more tension before the setup.",
        metadata={"proposed_scene_order": ["scene_002", "scene_001"]},
    )
    analysis.edit_decisions.append(reorder)
    storage.save_editorial_analysis_record(analysis)
    result = svc.apply_decisions(
        "project-x",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=[reorder.decision_id],
            apply_mode="update_cut",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    assert result.result_cut_id
    assert result.skipped_decisions == []
    assert project_store.project["film_cut"]["scene_order"] == ["scene_002", "scene_001"]
    assert project_store.project["film_cut"]["included_scenes"] == ["scene_002", "scene_001"]
    assert project_store.project["film_cut"]["editorial_source_analysis_id"] == analysis.analysis_id
    assert project_store.project["film_cut"]["editorial_application_decision_ids"] == [reorder.decision_id]


def test_update_cut_skips_invalid_reorder_without_mutating_film_cut():
    storage = _FakeStorage()
    project_store = _FakeProjectStore()
    svc = _service(storage=storage, project_store=project_store)
    analysis = svc.analyze_project("project-x")
    reorder = EditorialDecision(
        decision_id="decision-reorder-missing-scene",
        decision_type="reorder_scene",
        target_type="sequence",
        target_id="timeline",
        recommendation="Test an invalid reorder.",
        rationale="Invalid proposals must not alter canonical scene order.",
        metadata={"proposed_scene_order": ["scene_002"]},
    )
    analysis.edit_decisions.append(reorder)
    storage.save_editorial_analysis_record(analysis)
    before = list(project_store.project["film_cut"]["scene_order"])
    result = svc.apply_decisions(
        "project-x",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=[reorder.decision_id],
            apply_mode="update_cut",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    assert result.result_cut_id == ""
    assert result.application_status == "applied_with_skips"
    assert result.skipped_decisions == [reorder.decision_id]
    assert project_store.project["film_cut"]["scene_order"] == before


def test_guardrails_reject_scoring_language():
    svc = _service()
    analysis = svc.analyze_project("project-x", persist=False)
    analysis.overall_read = "Score: 8/10"
    with pytest.raises(ValueError):
        svc._enforce_guardrails(analysis)


def test_revision_emphasis_changes_final_decision_type():
    storage = _FakeStorage()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    svc = _service(storage=storage)
    analysis = svc.analyze_project(
        "project-x",
        EditorialAnalysisRequest(revision_emphasis="structural_clarity"),
    )
    assert any(decision.decision_type == "compress_escalation" for decision in analysis.edit_decisions)


def test_analysis_generates_full_advisory_editorial_decision_vocabulary():
    storage = _FakeStorage()
    project_store = _FakeProjectStore()
    project_store.project["film_cut"]["scene_order"] = ["scene_001", "scene_002", "scene_003"]
    project_store.project["film_cut"]["included_scenes"] = ["scene_001", "scene_002", "scene_003"]
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
        {"scene_id": "scene_003", "composed_url": "/outputs/scene_003.mp4", "shot_count": 1},
    ]
    storage.continuity_issues = [SimpleNamespace(issue_id="continuity-1")]
    storage.style_drift_issues = [SimpleNamespace(issue_id="style-1")]
    storage.memories = [SimpleNamespace(memory_id="memory-1", summary="A stillness motif returns near the end.")]
    svc = _service(storage=storage, project_store=project_store)

    analysis = svc.analyze_project(
        "project-x",
        EditorialAnalysisRequest(revision_emphasis="emotional_residue"),
    )

    decision_types = {decision.decision_type for decision in analysis.edit_decisions}
    assert {
        "replace_transition",
        "trim",
        "hold",
        "extend_reaction",
        "protect_silence",
        "delay_reveal",
        "restore_motif_callback",
        "reorder_scene",
    }.issubset(decision_types)
    reorder = next(decision for decision in analysis.edit_decisions if decision.decision_type == "reorder_scene")
    assert reorder.metadata["proposed_scene_order"] == ["scene_001", "scene_003", "scene_002"]


def test_context_reads_keyframe_and_shot_boundary_evidence():
    storage = _FakeStorage()
    storage.scene_compositions = [
        {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
        {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
    ]
    storage.video_assets = [SimpleNamespace(asset_id="asset-cut-1")]
    storage.video_keyframes = [
        SimpleNamespace(
            keyframe_id="kf-001",
            asset_id="asset-cut-1",
            timestamp_seconds=1.2,
            frame_index=12,
        )
    ]
    storage.shot_boundaries_by_asset = {
        "asset-cut-1": [
            SimpleNamespace(
                boundary_id="boundary-001",
                asset_id="asset-cut-1",
                start_time=1.0,
                end_time=2.0,
                transition_type="hard_cut",
            )
        ]
    }
    svc = _service(storage=storage)
    analysis = svc.analyze_project("project-x")
    assert analysis.metadata["evidence_counts"]["video_keyframes"] == 1
    assert analysis.metadata["evidence_counts"]["shot_boundaries"] == 1
    pacing_sources = {
        evidence.source_type
        for diagnostic in analysis.pacing_diagnostics
        for evidence in diagnostic.evidence_refs
    }
    transition_sources = {
        evidence.source_type
        for advisory in analysis.transition_advisories
        for evidence in advisory.evidence_refs
    }
    assert "video_keyframe" in pacing_sources
    assert "shot_boundary" in pacing_sources
    assert "shot_boundary" in transition_sources


def test_sqlite_round_trip_preserves_editorial_decision_metadata(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "storage"))
    analysis = _service(storage=_FakeStorage()).analyze_project("project-x", persist=False)
    reorder = EditorialDecision(
        decision_id="decision-reorder-round-trip",
        decision_type="reorder_scene",
        target_type="sequence",
        target_id="timeline",
        recommendation="Test the alternate scene order as an explicit cut update.",
        rationale="The proposal must remain inspectable after persistence.",
        metadata={"proposed_scene_order": ["scene_002", "scene_001"]},
    )
    analysis.edit_decisions.append(reorder)
    storage.save_editorial_analysis_record(analysis)

    loaded = storage.get_editorial_analysis_record(analysis.analysis_id)

    assert loaded is not None
    loaded_reorder = next(row for row in loaded.edit_decisions if row.decision_id == reorder.decision_id)
    assert loaded_reorder.metadata["proposed_scene_order"] == ["scene_002", "scene_001"]


def test_sqlite_round_trip_preserves_editorial_application_metadata(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "storage"))
    fake_storage = _FakeStorage()
    svc = _service(storage=fake_storage)
    analysis = svc.analyze_project("project-x")
    decision_id = analysis.edit_decisions[0].decision_id
    result = svc.apply_decisions(
        "project-x",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=[decision_id],
            apply_mode="metadata_only",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
            metadata={"operator_note": "approved in screening"},
        ),
    )
    storage.save_editorial_decision_application(result)

    loaded = storage.get_editorial_decision_application(result.application_id)

    assert loaded is not None
    assert loaded.metadata["operator_note"] == "approved in screening"
    assert loaded.decision_ids == [decision_id]
