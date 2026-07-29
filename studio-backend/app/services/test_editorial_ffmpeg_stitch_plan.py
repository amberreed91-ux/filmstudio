from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.editorial_intelligence import EditorialApplyRequest
from app.services.editorial_intelligence_service import EditorialIntelligenceService
from app.services.editorial_timeline_context_service import EditorialTimelineContextService
from app.services.ffmpeg_stitching_service import FFmpegStitchingService, _get_video_duration


class _EditorialStorage:
    def __init__(self):
        self.scene_compositions = [
            {"scene_id": "scene_001", "composed_url": "/outputs/scene_001.mp4", "shot_count": 1},
            {"scene_id": "scene_002", "composed_url": "/outputs/scene_002.mp4", "shot_count": 1},
        ]
        self.style_drift_issues = [SimpleNamespace(issue_id="style-1")]
        self.analyses = {}
        self.applications = {}

    def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, title="Editorial Stitch Test")

    def list_jobs(self, project_id=None, limit=1000):  # noqa: ARG002
        return []

    def list_scene_compositions_for_project(self, project_id):  # noqa: ARG002
        return self.scene_compositions

    def list_final_short_film_packages_for_project(self, project_id):  # noqa: ARG002
        return []

    def list_video_assets_for_project(self, project_id):  # noqa: ARG002
        return []

    def list_video_keyframes_for_project(self, project_id):  # noqa: ARG002
        return []

    def list_shot_boundaries_for_asset(self, asset_id):  # noqa: ARG002
        return []

    def list_continuity_issues_for_project(self, project_id):  # noqa: ARG002
        return []

    def list_style_drift_issues_for_project(self, project_id):  # noqa: ARG002
        return self.style_drift_issues

    def list_cinematic_memory_for_project(self, project_id):  # noqa: ARG002
        return []

    def list_video_frame_analyses_for_project(self, project_id):  # noqa: ARG002
        return []

    def save_editorial_analysis_record(self, record):
        self.analyses[record.analysis_id] = record
        return record

    def get_editorial_analysis_record(self, analysis_id):
        return self.analyses.get(analysis_id)

    def list_editorial_analysis_records_for_project(self, project_id, limit=20):
        return [row for row in self.analyses.values() if row.project_id == project_id][-limit:]

    def get_latest_editorial_analysis_record(self, project_id):
        rows = self.list_editorial_analysis_records_for_project(project_id, limit=1)
        return rows[0] if rows else None

    def save_editorial_decision_application(self, application):
        self.applications[application.application_id] = application
        return application

    def list_editorial_decision_applications_for_project(self, project_id, limit=20):
        return [row for row in self.applications.values() if row.project_id == project_id][-limit:]


class _EditorialProjectStore:
    def __init__(self):
        self.project = {
            "project_id": "project-editorial-stitch",
            "title": "Editorial Stitch Test",
            "approved_scenes": ["scene_001", "scene_002"],
            "film_cut": {
                "cut_id": "cut-a",
                "scene_order": ["scene_001", "scene_002"],
                "included_scenes": ["scene_001", "scene_002"],
            },
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "duration_estimate": 1.2},
                    {"scene_id": "scene_002", "duration_estimate": 1.2},
                ]
            },
        }

    def get_project(self, project_id):
        return self.project if project_id == self.project["project_id"] else None

    def save_project(self, project):
        self.project = dict(project)
        return self.project


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _make_test_clip(path: Path, duration: float = 1.2) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration}:size=160x90:rate=24",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={duration}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(path),
        ],
        check=True,
    )


def _make_test_audio(path: Path, duration: float = 1.2) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:sample_rate=44100:duration={duration}",
            str(path),
        ],
        check=True,
    )


def test_editorial_timing_map_accepts_executable_adjustments(monkeypatch):
    service = FFmpegStitchingService()

    monkeypatch.setattr(
        service,
        "_approved_editorial_stitch_plan",
        lambda _project_id: {
            "transition_advisories": [],
            "timing_adjustments": [
                {
                    "target_scene_id": "scene_001",
                    "adjustment_type": "tail_hold",
                    "seconds": 1.25,
                },
                {
                    "target_scene_id": "scene_002",
                    "adjustment_type": "compress_duration",
                    "seconds": 0.75,
                },
                {
                    "target_scene_id": "scene_004",
                    "adjustment_type": "tail_trim",
                    "seconds": 0.5,
                },
                {
                    "target_scene_id": "scene_003",
                    "adjustment_type": "unsupported",
                    "seconds": 4.0,
                },
            ],
        },
    )

    timing = service._approved_editorial_timing_map("project-x")
    assert set(timing) == {"scene_001", "scene_002", "scene_004"}
    assert timing["scene_001"]["adjustment_type"] == "tail_hold"
    assert timing["scene_002"]["adjustment_type"] == "compress_duration"
    assert timing["scene_004"]["adjustment_type"] == "tail_trim"


def test_editorial_transition_map_uses_scene_pairs(monkeypatch):
    service = FFmpegStitchingService()

    monkeypatch.setattr(
        service,
        "_approved_editorial_stitch_plan",
        lambda _project_id: {
            "transition_advisories": [
                {
                    "from_scene_id": "scene_001",
                    "to_scene_id": "scene_002",
                    "recommended_transition_type": "cross_dissolve",
                }
            ],
            "timing_adjustments": [],
        },
    )

    transitions = service._approved_editorial_transition_map("project-x")
    assert transitions[("scene_001", "scene_002")]["recommended_transition_type"] == "cross_dissolve"


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe required for media-level editorial timing verification")
def test_tail_hold_extends_real_segment_duration(tmp_path):
    service = FFmpegStitchingService()
    source = tmp_path / "source.mp4"
    held = tmp_path / "held.mp4"
    _make_test_clip(source, duration=1.2)

    before = _get_video_duration(str(source))
    service._apply_tail_hold(str(source), str(held), hold_seconds=0.4)
    after = _get_video_duration(str(held))

    assert held.exists()
    assert after >= before + 0.25


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe required for media-level editorial timing verification")
def test_trimmed_segment_build_shortens_real_media_duration(tmp_path):
    service = FFmpegStitchingService()
    source = tmp_path / "source.mp4"
    audio = tmp_path / "audio.wav"
    trimmed = tmp_path / "trimmed.mp4"
    _make_test_clip(source, duration=1.2)
    _make_test_audio(audio, duration=1.2)

    service._build_segment(
        video_path=str(source),
        audio_path=str(audio),
        duration=0.7,
        output=str(trimmed),
        tmp=tmp_path,
        idx=0,
    )
    after = _get_video_duration(str(trimmed))

    assert trimmed.exists()
    assert 0.45 <= after <= 0.9


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe required for media-level editorial stitch verification")
def test_approved_editorial_application_is_consumed_by_real_stitch_core(tmp_path, monkeypatch):
    storage = _EditorialStorage()
    project_store = _EditorialProjectStore()
    context = EditorialTimelineContextService(storage=storage, project_store_service=project_store)
    editorial_service = EditorialIntelligenceService(
        storage=storage,
        context_service=context,
        project_store_service=project_store,
    )
    analysis = editorial_service.analyze_project(project_store.project["project_id"])
    decision_ids = [
        decision.decision_id
        for decision in analysis.edit_decisions
        if decision.decision_type in {"replace_transition", "hold"}
    ]
    assert decision_ids
    result = editorial_service.apply_decisions(
        project_store.project["project_id"],
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=decision_ids,
            apply_mode="next_stitch",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    assert result.metadata["transition_advisories"]
    assert result.metadata["timing_adjustments"]

    import app.services.editorial_intelligence_service as editorial_module
    import app.services.ffmpeg_stitching_service as stitch_module
    import app.services.project_store as project_store_module

    monkeypatch.setattr(editorial_module, "editorial_intelligence_service", editorial_service)
    monkeypatch.setattr(project_store_module, "project_store", project_store)
    monkeypatch.setattr(stitch_module, "_FINAL_FILMS_DIR", tmp_path)

    stitcher = FFmpegStitchingService()
    scenes = project_store.project["execution_summary"]["scenes"]
    job = {
        "project_id": project_store.project["project_id"],
        "transitions_used": [],
        "progress": 0,
        "scenes_done": 0,
    }
    output = tmp_path / "editorial_stitch.mp4"

    stitcher._stitch_sync(project_store.project["project_id"], scenes, str(output), job)

    assert output.exists()
    assert job["editorial_transition_source"] == "editorial_intelligence"
    assert job["editorial_timing_source"] == "editorial_intelligence"
    assert job["editorial_timing_adjustments"]
    assert "cross_dissolve" in job["transitions_used"]
    assert _get_video_duration(str(output)) > 0
