from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.audio_pipeline_service import TrackStatus
from app.services.generation_contract import freeze_dialogue_handoff
from app.services.scene_assembly_service import SceneAssemblyService
from app.utils.helpers import derive_scene_id_from_shot_id
from conftest import run_async


def _video(path: Path, color: str) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c={color}:s=320x180:d=1:r=24",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _silence(path: Path, duration: float = 0.4) -> None:
    sample_rate = 22050
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * int(sample_rate * duration))


class FakeStorage:
    def __init__(self, jobs):
        self.jobs = jobs
        self.saved = None

    def list_take_choices(self, project_id, scene_id):
        return []

    def get_delivery_manifest(self, project_id, scope):
        return getattr(self, "manifest", None)

    def save_delivery_manifest(self, project_id, scope, payload):
        self.manifest = payload

    def list_jobs(self, project_id, limit=500):
        return self.jobs

    def save_scene_composition(self, **kwargs):
        self.saved = kwargs
        return kwargs


class FakeAudio:
    def __init__(self, root: Path):
        self.root = root
        self.dialogue_calls = []

    async def generate_shot_dialogue(self, **kwargs):
        self.dialogue_calls.append(kwargs)
        path = self.root / f"{kwargs['shot_id']}.wav"
        _silence(path)
        return {
            "status": TrackStatus.COMPLETE,
            "provider": "cosyvoice",
            "file_path": str(path),
            "lines_generated": len(kwargs.get("dialogue_lines") or []),
        }

    async def merge_audio_onto_video(self, **kwargs):
        source = Path(kwargs["video_path"])
        output = source.with_name(f"{source.stem}_audio.mp4")
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(source), "-i", str(kwargs["audio_path"]),
                "-filter:a", "apad", "-t", "1", "-c:v", "copy", "-c:a", "aac",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return {"status": TrackStatus.COMPLETE, "file_path": str(output)}


def _job(
    tmp_path: Path,
    shot_id: str,
    color: str,
    created_at: str,
    *,
    create_video: bool = False,
) -> RenderJobModel:
    video = tmp_path / f"{shot_id}.mp4"
    if create_video:
        _video(video, color)
    return RenderJobModel(
        id=f"job-{shot_id}-{created_at}",
        project_id="project_real",
        shot_id=shot_id,
        provider="runway",
        status="complete",
        input_payload=RenderJobInput(
            shot_id=shot_id,
            prompt="real scene shot",
            parameters={
                "dialogue_lines": [{"character": "MAYA", "text": f"Line for {shot_id}"}],
            },
        ),
        metadata={
            "creative_dialogue_handoff": freeze_dialogue_handoff(
                scene_id=derive_scene_id_from_shot_id(shot_id),
                shot_id=shot_id,
                lines=[{"character": "MAYA", "text": f"Line for {shot_id}"}],
            )
        },
        output_payload=RenderJobOutput(asset_url=str(video)),
        created_at=created_at,
    )


def test_collect_scene_jobs_supports_auto_split_ids_and_dedupes_latest(tmp_path: Path):
    jobs = [
        _job(tmp_path, "shot_scene_002_003", "blue", "2026-01-01T00:00:03"),
        _job(tmp_path, "shot_scene_002_001", "red", "2026-01-01T00:00:01"),
        _job(tmp_path, "shot_scene_002_002", "green", "2026-01-01T00:00:02"),
        _job(tmp_path, "shot_scene_002_002", "yellow", "2026-01-02T00:00:02"),
        _job(tmp_path, "shot_scene_003_001", "black", "2026-01-01T00:00:04"),
    ]
    service = SceneAssemblyService(storage=FakeStorage(jobs), backend_root=tmp_path)

    found = service.collect_scene_jobs("project_real", "scene_002")

    assert [number for number, _ in found] == [1, 2, 3]
    assert [job.shot_id for _, job in found] == [
        "shot_scene_002_001",
        "shot_scene_002_002",
        "shot_scene_002_003",
    ]
    assert found[1][1].created_at == "2026-01-02T00:00:02"


def test_assemble_three_shot_scene_bakes_cosyvoice_and_keeps_audio_continuous(tmp_path: Path):
    jobs = [
        _job(tmp_path, "shot_scene_002_001", "red", "2026-01-01T00:00:01", create_video=True),
        _job(tmp_path, "shot_scene_002_002", "green", "2026-01-01T00:00:02", create_video=True),
        _job(tmp_path, "shot_scene_002_003", "blue", "2026-01-01T00:00:03", create_video=True),
    ]
    storage = FakeStorage(jobs)
    audio = FakeAudio(tmp_path)
    service = SceneAssemblyService(
        storage=storage,
        audio_service=audio,
        backend_root=tmp_path,
        composed_root=tmp_path / "composed",
    )

    result = run_async(service.assemble_completed_scene(
        project_id="project_real",
        scene_id="scene_002",
        score_ambient_provider="none",
    ))

    output = Path(result["output_path"])
    assert output.exists()
    assert result["shot_count"] == 3
    assert result["has_audio"] is True
    assert result["audio_continuity"]["valid"] is True
    assert result["audio_continuity"]["duration_delta_seconds"] <= 0.15
    assert result["audio_continuity"]["audio_packet_timeline"]["packet_count"] > 0
    assert result["audio_continuity"]["audio_packet_timeline"]["max_gap_seconds"] <= 0.05
    assert result["audio_continuity"]["audio_packet_timeline"]["max_overlap_seconds"] <= 0.05
    assert result["audio_continuity"]["dialogue_complete_per_shot"] is True
    assert result["dialogue_provider_requested"] == "cosyvoice"
    assert len(result["audio_continuity"]["shot_boundaries_seconds"]) == 2
    assert [call["provider"] for call in audio.dialogue_calls] == [
        "cosyvoice",
        "cosyvoice",
        "cosyvoice",
    ]
    assert storage.saved["shot_count"] == 3


def test_chosen_older_take_is_the_actual_assembled_picture(tmp_path: Path):
    import numpy as np
    old = _job(tmp_path, 'scene_001_shot_001', 'red', '2026-01-01')
    new = _job(tmp_path, 'scene_001_shot_001', 'blue', '2026-02-01')
    old.output_payload.asset_url = str(tmp_path / 'old.mp4')
    new.output_payload.asset_url = str(tmp_path / 'new.mp4')
    _video(Path(old.output_payload.asset_url), 'red')
    _video(Path(new.output_payload.asset_url), 'blue')
    store = FakeStorage([new, old])
    store.list_take_choices = lambda *args: [{'shot_number': 1, 'job_id': old.id}]
    store.get_job = lambda id: old if id == old.id else new
    service = SceneAssemblyService(storage=store, audio_service=FakeAudio(tmp_path), backend_root=tmp_path, composed_root=tmp_path / 'composed')
    result = run_async(service.assemble_completed_scene(project_id='project_real', scene_id='scene_001', score_ambient_provider='none'))
    pixels = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '0.3', '-i', result['output_path'], '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    mean = np.frombuffer(pixels, dtype=np.uint8).reshape(-1, 3).mean(axis=0)
    assert mean[0] > 200 and mean[2] < 30
    assert store.manifest['job_ids'] == [old.id]


def test_dialogue_overrun_stops_without_saving_or_freezing(tmp_path: Path):
    import pytest
    from app.services.stability import StateError
    jobs = [_job(tmp_path, 'scene_001_shot_001', 'red', '2026-01-01', create_video=True)]
    store = FakeStorage(jobs)
    audio = FakeAudio(tmp_path)
    async def overrun(**kwargs):
        assert kwargs['on_audio_overrun'] == 'error'
        return {'status': TrackStatus.FAILED, 'advisory': 'Audio longer than video'}
    audio.merge_audio_onto_video = overrun
    service = SceneAssemblyService(storage=store, audio_service=audio, backend_root=tmp_path)
    with pytest.raises(StateError) as error:
        run_async(service.assemble_completed_scene(project_id='project_real', scene_id='scene_001', score_ambient_provider='none'))
    assert error.value.stage == 'scene_assembly_audio_timing'
    assert store.saved is None


def test_changed_local_render_bytes_invalidate_scene_manifest_without_job_change(tmp_path: Path):
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    source_video = outputs_root / "scene_001_shot_001.mp4"
    job = _job(tmp_path, "scene_001_shot_001", "red", "2026-01-01", create_video=True)
    Path(job.output_payload.asset_url).replace(source_video)
    job.output_payload.asset_url = f"file://{source_video}"
    storage = FakeStorage([job])
    service = SceneAssemblyService(
        storage=storage,
        audio_service=FakeAudio(tmp_path),
        backend_root=tmp_path,
        composed_root=tmp_path / "composed",
    )
    first = run_async(service.assemble_completed_scene(
        project_id="project_real", scene_id="scene_001", score_ambient_provider="none"
    ))
    manifest_before = dict(storage.manifest)
    previous_stat = source_video.stat()
    _video(source_video, "blue")
    import os

    os.utime(source_video, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns))

    second = run_async(service.assemble_completed_scene(
        project_id="project_real", scene_id="scene_001", score_ambient_provider="none", overwrite=False
    ))

    assert second["status"] == "complete"
    assert second["output_path"] != first["output_path"]
    assert storage.manifest["source_media"] != manifest_before["source_media"]
    assert storage.manifest["job_ids"] == [job.id]


def test_source_media_change_during_assembly_preserves_previous_manifest(tmp_path: Path, monkeypatch):
    import pytest
    from app.services.stability import StateError

    job = _job(tmp_path, "scene_001_shot_001", "red", "2026-01-01", create_video=True)
    storage = FakeStorage([job])
    previous = {"composed_url": "/static/previous.mp4"}
    storage.manifest = previous
    service = SceneAssemblyService(storage=storage, audio_service=FakeAudio(tmp_path), backend_root=tmp_path)
    snapshots = iter([service.source_media_snapshot([(1, job)]), {"changed": {"sha256": "different"}}])
    monkeypatch.setattr(service, "source_media_snapshot", lambda _jobs: next(snapshots))

    with pytest.raises(StateError, match="rendered shot changed") as error:
        run_async(service.assemble_completed_scene(
            project_id="project_real", scene_id="scene_001", score_ambient_provider="none"
        ))
    assert error.value.stage == "scene_assembly_video_inputs"
    assert storage.manifest == previous


def test_recording_changed_during_assembly_keeps_previous_composition(tmp_path, monkeypatch):
    import pytest
    from app.services.stability import StateError

    job = _job(tmp_path, 'shot_scene_002_001', 'red', '2026-01-01', create_video=True)
    storage = FakeStorage([job])
    previous = {'composed_url': '/static/previous.mp4'}
    storage.saved = previous
    service = SceneAssemblyService(storage=storage, audio_service=FakeAudio(tmp_path), backend_root=tmp_path)
    snapshots = iter([{'shot_scene_002_001': None}, {'shot_scene_002_001': {'sha256': 'changed'}}])
    monkeypatch.setattr(service.audio_sources, 'snapshot', lambda *args: next(snapshots))
    with pytest.raises(StateError, match='recording changed'):
        run_async(service.assemble_completed_scene(project_id='project_real', scene_id='scene_002', score_ambient_provider='none'))
    assert storage.saved == previous
