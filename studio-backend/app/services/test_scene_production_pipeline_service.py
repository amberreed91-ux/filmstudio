from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, SoundtrackConfig
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.stability import ValidationError
from conftest import run_async


class FakeRenderService:
    def __init__(self, outputs_dir: Path):
        self.outputs_dir = outputs_dir
        self.created: list[dict[str, Any]] = []
        self.jobs: dict[str, RenderJobModel] = {}
        self.consistency_payload: ConsistencyPayload | None = None

    def create_job(self, **kwargs):
        index = len(self.created) + 1
        job_id = f"job-{index}"
        shot_id = kwargs["shot_id"]
        video = self.outputs_dir / f"{shot_id}.mp4"
        video.write_bytes(b"fake-video")
        job = RenderJobModel(
            id=job_id,
            project_id=kwargs["project_id"],
            shot_id=shot_id,
            provider=kwargs.get("provider") or "happyhorse",
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=kwargs["prompt"],
                referenceAssets=kwargs.get("reference_assets") or [],
                parameters=kwargs.get("parameters") or {},
                consistency_payload=self.consistency_payload,
            ),
            output_payload=RenderJobOutput(asset_url=f"/outputs/renders/{video.name}"),
        )
        self.created.append(kwargs)
        self.jobs[job_id] = job
        return job

    async def submit_job(self, job_id: str):
        self.jobs[job_id].status = "complete"
        return self.jobs[job_id]

    async def get_job_status(self, job_id: str):
        return self.jobs[job_id]


class FakeAudioService:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def generate_full_pipeline(self, **kwargs):
        self.calls.append(kwargs)
        video_path = Path(kwargs["video_path"])
        final = video_path.with_name(f"{video_path.stem}_audio.mp4")
        final.write_bytes(b"fake-video-with-audio")
        return {
            "job_id": f"audio-{kwargs['scene_id']}",
            "dialogue_provider": "cosyvoice",
            "score_ambient_provider": kwargs.get("score_ambient_provider") or "none",
            "final_video_path": str(final),
            "final_video_url": f"/outputs/renders/{final.name}",
        }


class FakeStitchingService:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.status = "complete"

    def stitch_scene(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": self.status,
            "clip_count": 2,
            "duration_seconds": 5.5,
            "shot_ids": ["scene_001_shot_001", "scene_001_shot_002"],
            "output_url": f"/outputs/scene_assemblies/{kwargs['project_id']}_{kwargs['scene_id']}.mp4",
            "output_path": f"/tmp/{kwargs['project_id']}_{kwargs['scene_id']}.mp4",
        }


def _project() -> dict[str, Any]:
    return {
        "project_id": "project_test",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "description": "Dre listens before answering.",
                    "emotional_tone": "restrained concern",
                    "characters": ["Dre"],
                    "shots": [
                        {"shot_id": "scene_001_shot_002", "description": "Reverse on Dre."},
                        {"shot_id": "scene_001_shot_001", "description": "Wide two-shot."},
                    ],
                }
            ],
            "dialogue_lines": [
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_001",
                    "character": "Dre",
                    "text": "You heard that too, right?",
                    "emotional_subtext": "casual concern",
                }
            ],
        },
    }


def test_scene_pipeline_renders_shots_in_order_adds_audio_and_stitches(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    render = FakeRenderService(outputs_dir)
    audio = FakeAudioService()
    stitch = FakeStitchingService()
    service = SceneProductionPipelineService(
        render_svc=render,
        audio_svc=audio,
        stitching_svc=stitch,
        backend_root=tmp_path,
    )
    saved_projects: list[dict[str, Any]] = []

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        save_project=lambda updated: saved_projects.append(updated) or updated,
    ))

    assert result["status"] == "complete"
    assert [call["shot_id"] for call in render.created] == ["scene_001_shot_001", "scene_001_shot_002"]
    assert [call["scene_id"] for call in audio.calls] == ["scene_001_shot_001", "scene_001_shot_002"]
    assert audio.calls[0]["dialogue_lines"][0]["emotional_subtext"] == "casual concern"
    assert audio.calls[0]["score_ambient_provider"] == "none"
    render_rows = saved_projects[0]["execution_summary"]["one_button_render_jobs"]
    assert [row["output_url"] for row in render_rows] == [
        "/outputs/renders/scene_001_shot_001_audio.mp4",
        "/outputs/renders/scene_001_shot_002_audio.mp4",
    ]
    assert stitch.calls[0]["project"]["execution_summary"]["one_button_render_jobs"] == render_rows
    assemblies = saved_projects[0]["execution_summary"]["scene_pipeline_assemblies"]
    assert len(assemblies) == 1
    assert assemblies[0]["scene_id"] == "scene_001"
    assert assemblies[0]["status"] == "complete"
    assert assemblies[0]["output_url"] == "/outputs/scene_assemblies/project_test_scene_001.mp4"
    assert assemblies[0]["duration_seconds"] == 5.5
    assert assemblies[0]["score_ambient_provider"] == "none"
    assert result["assembly"] == assemblies[0]


def test_scene_pipeline_accepts_stitcher_completed_status(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    stitch = FakeStitchingService()
    stitch.status = "completed"
    service = SceneProductionPipelineService(
        render_svc=FakeRenderService(outputs_dir),
        audio_svc=FakeAudioService(),
        stitching_svc=stitch,
        backend_root=tmp_path,
    )

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
    ))

    assert result["status"] == "complete"


def test_scene_pipeline_resolves_all_auto_split_candidates_in_numeric_order(tmp_path: Path):
    service = SceneProductionPipelineService(backend_root=tmp_path)
    scene = {"scene_id": "scene_002", "description": "Maya faces Dre."}
    project = {
        "execution_summary": {
            "shot_candidates": [
                {"shot_id": "shot_scene_002_003", "scene_id": "scene_002"},
                {"shot_id": "shot_scene_003_001", "scene_id": "scene_003"},
                {"shot_id": "shot_scene_002_001", "scene_id": "scene_002"},
                {"shot_id": "shot_scene_002_002", "scene_id": "scene_002"},
            ]
        }
    }

    shots = service._resolve_ordered_shots(project, scene)

    assert [shot["shot_id"] for shot in shots] == [
        "shot_scene_002_001",
        "shot_scene_002_002",
        "shot_scene_002_003",
    ]


def test_scene_pipeline_normalizes_legacy_multi_shot_ledger_ids(tmp_path: Path):
    service = SceneProductionPipelineService(backend_root=tmp_path)
    scene = {
        "scene_id": "scene_002",
        "description": "Maya faces Dre.",
        "multi_shot_execution_ledger": [
            {"shot_id": "shot_002", "prompt_pack": {"base_prompt": "Reverse on Maya."}},
            {"shot_id": "shot_001", "prompt_pack": {"base_prompt": "Wide on both."}},
        ],
    }

    shots = service._resolve_ordered_shots({"execution_summary": {}}, scene)

    assert [shot["shot_id"] for shot in shots] == [
        "shot_scene_002_001",
        "shot_scene_002_002",
    ]
    assert [shot["description"] for shot in shots] == [
        "Wide on both.",
        "Reverse on Maya.",
    ]


def test_scene_pipeline_persists_reference_lock_evidence(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    render = FakeRenderService(outputs_dir)
    render.consistency_payload = ConsistencyPayload(
        project_id="project_test",
        mode="identity_lock",
        refs=[
            ReferenceAsset(
                ref_id="dre-full",
                kind="character_full",
                image_url="/outputs/refs/dre-full.png",
                project_id="project_test",
            ),
            ReferenceAsset(
                ref_id="dre-face",
                kind="character_face",
                image_url="/outputs/refs/dre-face.png",
                project_id="project_test",
            ),
        ],
        weights={"dre-full": 1.0, "dre-face": 0.55},
    )
    service = SceneProductionPipelineService(
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        backend_root=tmp_path,
    )
    saved_projects: list[dict[str, Any]] = []

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        save_project=lambda updated: saved_projects.append(updated) or updated,
    ))

    first_consistency = result["shots"][0]["consistency"]
    assert first_consistency == {
        "mode": "identity_lock",
        "attached": True,
        "reference_count": 2,
        "reference_kinds": ["character_full", "character_face"],
        "primary_reference_url": "/outputs/refs/dre-full.png",
    }
    render_rows = saved_projects[0]["execution_summary"]["one_button_render_jobs"]
    assert render_rows[0]["consistency"] == first_consistency


def test_scene_pipeline_reports_manual_post_render_soundtrack(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    service = SceneProductionPipelineService(
        render_svc=FakeRenderService(outputs_dir),
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        backend_root=tmp_path,
    )

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        score_ambient_provider="manual_post_render",
        soundtrack_config=SoundtrackConfig(
            enabled=True,
            audio_source_type="local_file",
            local_audio_path=str(tmp_path / "score.wav"),
        ),
    ))

    assert result["score_ambient_provider"] == "manual_post_render"
    assert result["soundtrack_status"] == "manual_post_render"


def test_scene_pipeline_manual_post_render_skips_per_shot_score_generation(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    audio = FakeAudioService()
    service = SceneProductionPipelineService(
        render_svc=FakeRenderService(outputs_dir),
        audio_svc=audio,
        stitching_svc=FakeStitchingService(),
        backend_root=tmp_path,
    )

    run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        score_ambient_provider="manual",
        soundtrack_config=SoundtrackConfig(
            enabled=True,
            audio_source_type="local_file",
            local_audio_path=str(tmp_path / "score.wav"),
        ),
    ))

    assert {call["score_ambient_provider"] for call in audio.calls} == {"none"}


def test_scene_pipeline_manual_post_render_requires_soundtrack_source(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    service = SceneProductionPipelineService(
        render_svc=FakeRenderService(outputs_dir),
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        backend_root=tmp_path,
    )

    try:
        run_async(service.generate_scene(
            project_id="project_test",
            scene_id="scene_001",
            project=_project(),
            score_ambient_provider="manual_post_render",
            soundtrack_config=SoundtrackConfig(enabled=True, audio_source_type="local_file"),
        ))
    except ValidationError as exc:
        assert exc.error_type == "validation_error"
        assert exc.stage == "scene_soundtrack"
    else:
        raise AssertionError("manual_post_render without source should fail")
