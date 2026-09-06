from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.services.take_selection_service import TakeSelectionService
from app.services.film_delivery_service import FilmDeliveryService
from app.services.stability import ValidationError, StateError, PlaybackError
from app.routes.take_selection import router, get_take_selection_service
from conftest import run_async


def job(id, number=1, project='p', status='complete', created='2026-01-01'):
    return SimpleNamespace(id=id, project_id=project, shot_id=f'scene_001_shot_{number:03d}', status=status, created_at=created, output_payload=SimpleNamespace(asset_url=f'/outputs/{id}.mp4'))


class Store:
    def __init__(self, jobs=()):
        self.jobs = {j.id: j for j in jobs}
        self.choices = {}
        self.manifests = {}
        self.compositions = []
        self.film = None

    def get_job(self, id): return self.jobs.get(id)
    def list_jobs(self, **kwargs): return list(self.jobs.values())
    def list_take_choices(self, project_id, scene_id):
        return [{'shot_number': number, 'job_id': value} for (p, s, number), value in self.choices.items() if (p, s) == (project_id, scene_id)]
    def save_take_choice(self, p, s, n, id): self.choices[p, s, n] = id
    def get_delivery_manifest(self, p, scope): return self.manifests.get((p, scope))
    def save_delivery_manifest(self, p, scope, value): self.manifests[p, scope] = value
    def list_scene_compositions_for_project(self, p): return self.compositions
    def get_film(self, p): return self.film
    def save_film(self, **kwargs): self.film = kwargs


def test_older_choice_survives_new_render_and_clear_restores_latest():
    store = Store([job('old'), job('new', created='2026-02-01')])
    service = TakeSelectionService(store)
    service.choose('p', 'scene_001', 1, 'old')
    assert service.resolve('p', 'scene_001')[0][1].id == 'old'
    store.jobs['newer'] = job('newer', created='2026-03-01')
    assert service.resolve('p', 'scene_001')[0][1].id == 'old'
    service.choose('p', 'scene_001', 1, None)
    assert service.resolve('p', 'scene_001')[0][1].id == 'newer'


@pytest.mark.parametrize('candidate', [job('foreign', project='other'), job('wrong-shot', number=2)])
def test_rejects_foreign_or_wrong_shot(candidate):
    store = Store([candidate])
    with pytest.raises(ValidationError): TakeSelectionService(store).choose('p', 'scene_001', 1, candidate.id)
    assert not store.choices


def test_missing_or_failed_selected_take_never_falls_back():
    store = Store([job('chosen'), job('new', created='2026-02-01')])
    service = TakeSelectionService(store)
    service.choose('p', 'scene_001', 1, 'chosen')
    store.jobs['chosen'].status = 'failed'
    with pytest.raises(StateError): service.resolve('p', 'scene_001')
    del store.jobs['chosen']
    with pytest.raises(ValidationError): service.resolve('p', 'scene_001')


def test_choices_and_manifests_survive_database_reopen(tmp_path):
    store = DatabaseStorage(str(tmp_path / 'edit.db'))
    store.save_take_choice('p', 'scene_001', 1, 'old')
    store.save_delivery_manifest('p', 'scene_001', {'job_ids': ['old'], 'composed_url': '/static/old.mp4'})
    reopened = DatabaseStorage(str(tmp_path / 'edit.db'))
    assert reopened.list_take_choices('p', 'scene_001')[0]['job_id'] == 'old'
    assert reopened.get_delivery_manifest('p', 'scene_001')['job_ids'] == ['old']
    assert reopened.list_take_choices('other', 'scene_001') == []


def test_take_route_contract_and_validation():
    service = TakeSelectionService(Store([job('old')]))
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_take_selection_service] = lambda: service
    client = TestClient(app)
    url = '/api/f51/studio/projects/p/scenes/scene_001/take-choices'
    assert client.put(url + '/1', json={'job_id': 'old'}).json()['choices'] == [{'shot_number': 1, 'job_id': 'old'}]
    assert client.get(url).status_code == 200
    assert client.put(url + '/0', json={'job_id': 'old'}).status_code == 422
    assert client.put(url + '/1', json={'job_id': 'unknown'}).status_code == 400
    assert client.put(url + '/1', json={'job_id': None}).json()['choices'][0]['job_id'] is None


def delivery(store, order, tmp_path, scenes=None):
    projects = SimpleNamespace(load=lambda _: {'execution_summary': {'scenes': [{'scene_id': sid} for sid in order]}})
    return FilmDeliveryService(storage=store, projects=projects, scenes=scenes, backend_root=tmp_path)


def test_changed_take_marks_scene_and_film_outdated(tmp_path):
    store = Store([job('old'), job('new', created='2026-02-01')])
    store.compositions = [{'scene_id': 'scene_001', 'composed_url': '/static/edit.mp4'}]
    store.save_delivery_manifest('p', 'scene_001', {'job_ids': ['new'], 'composed_url': '/static/edit.mp4', 'audio_inputs': {'scene_001_shot_001': None}})
    store.film = {'film_url': '/static/film.mp4', 'has_audio': True}
    store.save_delivery_manifest('p', '__film__', {'scene_ids': ['scene_001'], 'scene_urls': ['/static/edit.mp4'], 'film_url': '/static/film.mp4'})
    service = delivery(store, ['scene_001'], tmp_path)
    assert service.status('p').film_assembled
    TakeSelectionService(store).choose('p', 'scene_001', 1, 'old')
    status = service.status('p')
    assert status.film_outdated and not status.film_assembled
    assert status.scenes_needing_assembly == ['scene_001']


def test_incomplete_scene_aborts_without_replacing_old_film(tmp_path):
    store = Store()
    store.film = {'film_url': '/static/old.mp4'}
    scenes = SimpleNamespace(assemble_completed_scene=AsyncMock(side_effect=StateError('missing shots')))
    service = delivery(store, ['scene_002', 'scene_001'], tmp_path, scenes)
    with pytest.raises(StateError): run_async(service.assemble('p'))
    assert store.film['film_url'] == '/static/old.mp4'
    assert scenes.assemble_completed_scene.call_args.kwargs['scene_id'] == 'scene_002'


def test_unreadable_scene_is_not_silently_omitted(tmp_path):
    store = Store()
    store.compositions = [{'scene_id': 'scene_001', 'composed_url': '/outputs/missing.mp4'}]
    with pytest.raises(PlaybackError): run_async(delivery(store, ['scene_001'], tmp_path).assemble('p'))
    assert store.film is None


def test_real_media_delivery_preserves_scene_order_sound_and_reopens(tmp_path):
    import subprocess
    import numpy as np
    from app.services.scene_assembly_service import SceneAssemblyService

    store = DatabaseStorage(str(tmp_path / 'media.db'))
    source_dir = tmp_path / 'outputs'; source_dir.mkdir()
    # Known tones verify that both scenes' sound survives, in screenplay order.
    for sid, color, tone in [('scene_010', 'red', 440), ('scene_002', 'blue', 880)]:
        source = source_dir / f'{sid}.mp4'
        result = subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c={color}:s=320x180:d=1:r=24', '-f', 'lavfi', '-i', f'sine=frequency={tone}:duration=1:sample_rate=48000', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(source)], capture_output=True)
        assert result.returncode == 0
        store.save_scene_composition('p', sid, f'/outputs/{sid}.mp4', 1, 1.0)
    service = delivery(store, ['scene_010', 'scene_002'], tmp_path)
    result = run_async(service.assemble('p'))
    output = tmp_path / result.film_url.split('8010/')[1]
    assert output.is_file() and result.scene_count == 2 and result.has_audio
    assert abs(result.total_duration_seconds - 2) < .2
    samples = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], capture_output=True, check=True).stdout
    audio = np.frombuffer(samples, dtype=np.float32)
    for second, expected in [(.2, 440), (1.2, 880)]:
        window = audio[int(second*48000):int((second+.4)*48000)]
        peak = np.fft.rfftfreq(len(window), 1/48000)[np.abs(np.fft.rfft(window)).argmax()]
        assert abs(peak - expected) < 10
    # Decode actual frames to verify the picture order independently of manifests.
    for second, channel in [(.3, 0), (1.3, 2)]:
        pixels = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(second), '-i', str(output), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
        mean = np.frombuffer(pixels, dtype=np.uint8).reshape(-1, 3).mean(axis=0)
        assert mean[channel] > 200
    reopened = delivery(DatabaseStorage(str(tmp_path / 'media.db')), ['scene_010', 'scene_002'], tmp_path)
    assert reopened.status('p').film_assembled
    assert reopened.status('p').film_url == result.film_url
    assert store.get_delivery_manifest('p', '__film__')['scene_ids'] == ['scene_010', 'scene_002']
    # A second export retains the first file and receives a distinct URL.
    newer = run_async(service.assemble('p'))
    assert newer.film_url != result.film_url and output.is_file()


def test_unfinished_shot_prevents_partial_scene_delivery():
    store = Store([job('ready', number=1), job('failed', number=2, status='failed')])
    with pytest.raises(StateError) as error:
        TakeSelectionService(store).resolve('p', 'scene_001')
    assert error.value.metadata['shot_numbers'] == [2]
