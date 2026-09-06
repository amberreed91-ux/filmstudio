"""No provider calls: actual local audio/video, service handoffs and persistence."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import subprocess

import numpy as np
import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobModel, RenderJobInput, RenderJobOutput, StudioProject
from app.services.audio_pipeline_service import AudioPipelineService, TrackStatus
from app.services.scene_assembly_service import SceneAssemblyService
from app.services.film_delivery_service import FilmDeliveryService
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.screening_room_service import ScreeningRoomService
from conftest import run_async


def _audio(tmp_path):
    service = AudioPipelineService()
    service.output_base = tmp_path / 'audio'
    service._generate_dialogue_tts_sync = lambda *args, **kwargs: pytest.fail('Voice generation is forbidden in offline delivery')
    service.generate_score_ambient = AsyncMock(side_effect=AssertionError('Music generation is forbidden in offline delivery'))
    return service


def test_existing_media_mode_never_calls_voice_provider(tmp_path):
    service = _audio(tmp_path)
    result = run_async(service.generate_shot_dialogue(project_id='p', scene_id='scene_001', shot_id='scene_001_shot_001', dialogue_lines=[{'character':'Maya','text':'Keep the door closed.'}], allow_generation=False))
    assert result['status'] == TrackStatus.SKIPPED
    assert result['provider'] == 'none' and result['source'] == 'none'
    assert result['file_path'] is None


def test_explicit_empty_dialogue_does_not_restore_scene_dialogue(tmp_path):
    service = _audio(tmp_path)
    result = run_async(service.generate_shot_dialogue(project_id='p', scene_id='scene_001', shot_id='scene_001_shot_001', scene_text='MAYA\nKeep the door closed.', dialogue_lines=[], dialogue_line_range={'start':0,'end':0}))
    assert result['status'] == TrackStatus.SKIPPED


def test_unassigned_scene_dialogue_is_not_repeated_on_every_shot():
    service = SceneProductionPipelineService()
    project = {'execution_summary': {'dialogue_lines': [
        {'scene_id':'scene_001','text':'Unassigned scene line','character':'Maya'},
        {'scene_id':'scene_001','shot_id':'scene_001_shot_002','text':'Assigned line','character':'Jules'},
    ]}}
    assert service._dialogue_lines_for_shot(project,'scene_001','scene_001_shot_001') == []
    assert [line['text'] for line in service._dialogue_lines_for_shot(project,'scene_001','scene_001_shot_002')] == ['Assigned line']
    assert service._dialogue_lines_for_shot({'execution_summary':{}},'scene_001','scene_001_shot_001') == []
    assert service._dialogue_lines_for_shot({'execution_summary':{}},'scene_001','scene_001_shot_001',allow_scene_fallback=True) is None


def _run(command):
    result = subprocess.run(command, capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    return result.stdout


def test_local_audio_mixed_shot_sizes_export_approval_and_reopen(tmp_path):
    store = DatabaseStorage(str(tmp_path / 'db'))
    project_id = 'offline_film'
    project = {'project_id':project_id,'title':'Offline delivery fixture','execution_summary':{'scenes':[{'scene_id':'scene_001'}]}}
    store.save_project(StudioProject(**project))
    audio = _audio(tmp_path)
    supplied = audio.output_base / project_id / 'scene_001' / 'pre_supplied'
    supplied.mkdir(parents=True)
    _run(['ffmpeg','-y','-f','lavfi','-i','sine=frequency=440:duration=0.7:sample_rate=48000',str(supplied/'scene_001_shot_001.wav')])
    output_root = tmp_path / 'outputs';output_root.mkdir()
    for number,color,size,fps in [(1,'red','320x180',24),(2,'blue','180x320',30)]:
        path = output_root / f'shot_{number}.mp4'
        command=['ffmpeg','-y','-f','lavfi','-i',f'color=c={color}:s={size}:d=1:r={fps}']
        if number==2:command+=['-f','lavfi','-i','sine=frequency=880:duration=1:sample_rate=48000']
        command+=['-c:v','libx264','-pix_fmt','yuv420p']
        command+=['-c:a','aac','-shortest'] if number==2 else ['-an']
        _run(command+[str(path)])
        shot=f'scene_001_shot_{number:03d}'
        store.save_job(RenderJobModel(id=f'job-{number}',project_id=project_id,shot_id=shot,provider='simulated',status='complete',created_at=f'2026-01-01T00:00:0{number}',input_payload=RenderJobInput(shot_id=shot,prompt='Local verification fixture',parameters={'dialogue_lines':[{'character':'Maya','text':'Must never invoke a voice provider'}]}),output_payload=RenderJobOutput(asset_url=str(path))))
    assembly = SceneAssemblyService(storage=store,audio_service=audio,backend_root=tmp_path)
    service = FilmDeliveryService(storage=store,projects=SimpleNamespace(load=lambda _:project),scenes=assembly,backend_root=tmp_path)
    result=run_async(service.assemble(project_id))
    audio.generate_score_ambient.assert_not_awaited()
    final=tmp_path / result.film_url.split('8010/')[1]
    streams=SceneAssemblyService._probe_streams(final)
    video=next(row for row in streams if row['codec_type']=='video')
    assert (video['width'],video['height']) == (320,180)
    assert abs(result.total_duration_seconds-2)<.2
    samples=np.frombuffer(_run(['ffmpeg','-v','error','-i',str(final),'-f','f32le','-ac','1','-ar','48000','-']),dtype=np.float32)
    for start,frequency in [(.1,440),(1.2,880)]:
        segment=samples[int(start*48000):int((start+.3)*48000)]
        peak=np.fft.rfftfreq(len(segment),1/48000)[np.abs(np.fft.rfft(segment)).argmax()]
        assert abs(peak-frequency)<10
    for start,channel in [(.3,0),(1.3,2)]:
        frame=np.frombuffer(_run(['ffmpeg','-v','error','-ss',str(start),'-i',str(final),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']),dtype=np.uint8).reshape(180,320,3)
        assert frame[90,160,channel]>200
    screening=ScreeningRoomService(store,SimpleNamespace(list_jobs=lambda _:store.list_jobs(project_id=project_id)), delivery_service=service)
    screening.outputs_root=output_root;screening.static_root=tmp_path/'static'
    manifest=screening.sync_manifest(project_id)
    delivered=next(row for row in manifest['outputs'] if row['source_type']=='film_delivery')
    screening.approve_output(project_id,delivered['screening_output_id'],confirmed=True)
    reopened=DatabaseStorage(str(tmp_path/'db'))
    assert reopened.get_screening_output(delivered['screening_output_id'])['approved']
    assert reopened.get_delivery_manifest(project_id,'scene_001')['job_ids']==['job-1','job-2']
    assert FilmDeliveryService(storage=reopened,projects=SimpleNamespace(load=lambda _:project),scenes=assembly,backend_root=tmp_path).status(project_id).film_assembled

    assert screening.get_manifest(project_id)['current_final_output']['cut_freshness']['status'] == 'current'
    recording = supplied/'scene_001_shot_001.wav'
    previous = recording.stat()
    data = bytearray(recording.read_bytes()); data[-100] ^= 1; recording.write_bytes(data)
    import os
    os.utime(recording, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    stale = screening.get_manifest(project_id)
    assert stale['current_final_output']['approved']
    assert stale['current_final_output']['cut_freshness']['status'] == 'outdated'
    assert stale['completion_status'] == 'in_progress'
    assert service.status(project_id).scenes_needing_assembly == ['scene_001']
    rebuilt = run_async(service.assemble(project_id))
    assert rebuilt.film_url != result.film_url
    outputs = screening.sync_manifest(project_id)['outputs']
    old = next(row for row in outputs if row['screening_output_id'] == delivered['screening_output_id'])
    new = next(row for row in outputs if row.get('metadata',{}).get('film_url') == rebuilt.film_url)
    assert old['cut_freshness']['status'] == 'outdated'
    assert new['cut_freshness']['status'] == 'current'
    assert not new['approved']
    screening.approve_output(project_id,new['screening_output_id'],confirmed=True)
    assert screening.get_manifest(project_id)['completion_status'] == 'complete'
    recording.unlink()
    assert service.status(project_id).film_outdated
