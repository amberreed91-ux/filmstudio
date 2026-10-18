from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.services.take_selection_service import TakeSelectionService
from app.services.film_delivery_service import FilmDeliveryService
from app.services.screening_room_service import ScreeningRoomService
from app.services.stability import ValidationError, StateError, PlaybackError
from app.routes.take_selection import router, get_take_selection_service
from conftest import run_async
from test_canonical_film_delivery_handoff import seed_cut


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

    def get_current_film_cut(self, project_id): return getattr(self, 'current_cut', None)
    def get_film_cut_state(self, project_id): return getattr(self, 'cut_state', None)
    def get_film_cut_version(self, cut_id):
        cut = getattr(self, 'current_cut', None)
        return cut if cut and cut['cut_id'] == cut_id else None


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
    project_id = 'p'
    if isinstance(store, DatabaseStorage):
        from app.models import StudioProject

        store.save_project(StudioProject(
            project_id=project_id,
            title='Take selection delivery test',
            execution_summary={'scenes': [{'scene_id': sid} for sid in order]},
        ))
        seed_cut(store, project_id, order)
        project_loader = lambda requested: store.get_project(requested).model_dump(mode='json') if store.get_project(requested) else None
    else:
        store.current_cut = {'cut_id': 'p-cut-v1', 'project_id': project_id, 'version_number': 1, 'status': 'approved', 'scene_order': list(order), 'updated_at': '2026-01-01T00:00:00Z'}
        store.cut_state = {'current_cut_id': 'p-cut-v1', 'approved_cut_id': 'p-cut-v1'}
        project_loader = lambda requested: {'project_id': requested, 'execution_summary': {'scenes': [{'scene_id': sid} for sid in order]}} if requested == project_id else None
    return FilmDeliveryService(storage=store, project_loader=project_loader, scenes=scenes, backend_root=tmp_path)


def test_changed_take_marks_scene_and_film_outdated(tmp_path):
    store = Store([job('old'), job('new', created='2026-02-01')])
    store.compositions = [{'scene_id': 'scene_001', 'project_id': 'p', 'composed_url': '/static/edit.mp4'}]
    from app.services.scene_assembly_service import SceneAssemblyService
    source_snapshot = SceneAssemblyService.source_media_snapshot(
        SceneAssemblyService(storage=store, backend_root=tmp_path),
        [(1, store.jobs['new'])],
    )
    store.save_delivery_manifest('p', 'scene_001', {'job_ids': ['new'], 'composed_url': '/static/edit.mp4', 'audio_inputs': {'scene_001_shot_001': None}, 'source_media': source_snapshot})
    store.film = {'film_url': '/static/film.mp4', 'has_audio': True, 'scene_count': 1, 'total_duration_seconds': 1.0}
    store.save_delivery_manifest('p', '__film__', {'scene_ids': ['scene_001'], 'scene_urls': ['/static/edit.mp4'], 'film_url': '/static/film.mp4', 'source_cut_id': 'p-cut-v1', 'scene_provenance': []})
    service = delivery(store, ['scene_001'], tmp_path)
    assert service.status('p').film_assembled
    TakeSelectionService(store).choose('p', 'scene_001', 1, 'old')
    status = service.status('p')
    assert status.film_outdated and not status.film_assembled
    assert status.scenes_needing_assembly == ['scene_001']


def test_incomplete_scene_aborts_without_replacing_old_film(tmp_path):
    store = Store()
    store.film = {'film_url': '/static/old.mp4', 'scene_count': 2, 'total_duration_seconds': 2.0, 'has_audio': True}
    store.save_delivery_manifest('p', '__film__', {'film_url': '/static/old.mp4', 'scene_ids': ['scene_002','scene_001'], 'scene_urls': [], 'source_cut_id': 'p-cut-v1', 'scene_provenance': []})
    scenes = SimpleNamespace(assemble_completed_scene=AsyncMock(side_effect=StateError('missing shots')))
    service = delivery(store, ['scene_002', 'scene_001'], tmp_path, scenes)
    with pytest.raises(StateError) as error:
        run_async(service.assemble('p'))
    assert error.value.stage == 'film_delivery_coverage'
    assert store.film['film_url'] == '/static/old.mp4'
    # Full-film delivery is fail-closed: stale scene media must be assembled
    # explicitly before the handoff, not auto-substituted here.
    scenes.assemble_completed_scene.assert_not_awaited()


def test_changed_render_source_marks_scene_and_film_outdated(tmp_path):
    from app.services.scene_assembly_service import SceneAssemblyService

    source = tmp_path / "take.mp4"
    source.write_bytes(b"original-take")
    selected = job("same-job")
    selected.output_payload.asset_url = str(source)
    store = Store([selected])
    composition = {"scene_id": "scene_001", "project_id": "p", "composed_url": "/static/edit.mp4"}
    store.compositions = [composition]
    audio_inputs = {"scene_001_shot_001": None}
    assembly = SceneAssemblyService(storage=store, backend_root=tmp_path)
    source_media = assembly.source_media_snapshot([(1, selected)])
    store.save_delivery_manifest("p", "scene_001", {
        "job_ids": [selected.id],
        "composed_url": composition["composed_url"],
        "audio_inputs": audio_inputs,
        "source_media": source_media,
    })
    store.film = {"film_url": "/static/film.mp4", "has_audio": True, "scene_count": 1, "total_duration_seconds": 1.0}
    store.save_delivery_manifest("p", "__film__", {
        "scene_ids": ["scene_001"], "scene_urls": [composition["composed_url"]],
        "film_url": "/static/film.mp4", "source_cut_id": "p-cut-v1", "scene_provenance": [],
    })
    service = delivery(store, ["scene_001"], tmp_path, scenes=assembly)
    assert service.status("p").film_assembled

    source.write_bytes(b"revised-take")
    status = service.status("p")
    assert status.film_outdated and not status.film_assembled
    assert status.scenes_needing_assembly == ["scene_001"]


def test_unreadable_scene_is_not_silently_omitted(tmp_path):
    store = Store()
    from app.services.scene_assembly_service import SceneAssemblyService
    store.jobs['job'] = job('job')
    store.compositions = [{'scene_id': 'scene_001', 'project_id': 'p', 'composed_url': '/outputs/missing.mp4'}]
    assembly = SceneAssemblyService(storage=store, backend_root=tmp_path)
    store.save_delivery_manifest('p', 'scene_001', {
        'composed_url': '/outputs/missing.mp4', 'job_ids': ['job'],
        'audio_inputs': {'scene_001_shot_001': None},
        'source_media': assembly.source_media_snapshot([(1, store.jobs['job'])]),
    })
    with pytest.raises(PlaybackError): run_async(delivery(store, ['scene_001'], tmp_path).assemble('p'))
    assert store.film is None


def test_real_media_delivery_preserves_scene_order_sound_and_reopens(tmp_path):
    import subprocess
    import numpy as np
    from app.services.scene_assembly_service import SceneAssemblyService

    store = DatabaseStorage(str(tmp_path / 'media.db'))
    project_id = 'p'
    from app.models import StudioProject
    store.save_project(StudioProject(project_id=project_id, title='Take selection delivery', execution_summary={'scenes': [{'scene_id': 'scene_010'}, {'scene_id': 'scene_002'}]}))
    source_dir = tmp_path / 'outputs'; source_dir.mkdir()
    # Known tones verify that both scenes' sound survives, in screenplay order.
    for sid, color, tone in [('scene_010', 'red', 440), ('scene_002', 'blue', 880)]:
        source = source_dir / f'{sid}.mp4'
        result = subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c={color}:s=320x180:d=1:r=24', '-f', 'lavfi', '-i', f'sine=frequency={tone}:duration=1:sample_rate=48000', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(source)], capture_output=True)
        assert result.returncode == 0
        shot_id = f'{sid}_shot_001'
        job_id = f'job-{sid}'
        store.save_job(__import__('app.models', fromlist=['RenderJobModel']).RenderJobModel(
            id=job_id, project_id=project_id, shot_id=shot_id, provider='fixture', status='complete',
            input_payload=__import__('app.models', fromlist=['RenderJobInput']).RenderJobInput(shot_id=shot_id, prompt='fixture', parameters={}),
            output_payload=__import__('app.models', fromlist=['RenderJobOutput']).RenderJobOutput(asset_url=str(source)),
            created_at='2026-01-01T00:00:00Z',
        ))
        composition_service = SceneAssemblyService(storage=store, backend_root=tmp_path)
        source_media = composition_service.source_media_snapshot([(1, store.get_job(job_id))])
        run_async(composition_service.assemble_completed_scene(project_id=project_id, scene_id=sid, allow_audio_generation=False))
        composition = next(row for row in store.list_scene_compositions_for_project(project_id) if row['scene_id'] == sid)
        assert store.get_delivery_manifest(project_id, sid)['source_media'] == source_media
    service = delivery(store, ['scene_010', 'scene_002'], tmp_path, scenes=composition_service)
    result = run_async(service.assemble('p'))
    output = tmp_path / result.film_url.lstrip('/')
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
    # The handoff was not yet accepted at export time, so no film pointer
    # persists; scene provenance and the package must survive a reopen instead.
    assert store.get_film('p') is None
    assert store.get_delivery_manifest('p', '__film__') is None
    reopened_store = DatabaseStorage(str(tmp_path / 'media.db'))
    reopened = FilmDeliveryService(storage=reopened_store, project_loader=lambda requested: reopened_store.get_project(requested).model_dump(mode='json') if reopened_store.get_project(requested) else None, backend_root=tmp_path)
    assert not reopened.status('p').film_assembled
    assert reopened.status('p').scenes_needing_assembly == []
    assert reopened_store.get_final_short_film_package(result.package_id).final_output_url == result.film_url
    assert reopened_store.get_delivery_manifest('p', 'scene_010')['job_ids'] == ['job-scene_010']
    assert reopened_store.get_delivery_manifest('p', 'scene_002')['job_ids'] == ['job-scene_002']
    from app.models.production_acceptance import ProductionAcceptanceRunRequest
    from app.services.production_acceptance_service import ProductionAcceptanceService
    from app.services.short_film_review_service import ShortFilmReviewService
    review = ShortFilmReviewService(storage=store).create_review('p', result.film_url, reviewer='Creator')
    ShortFilmReviewService(storage=store).update_review_decision(review.review_id, 'approved', reviewer='Creator')
    # The creator decision binds to this exact output only. A fresh acceptance
    # run is required before Screening can select it; reassembling would mint a
    # new output URL that this review does not cover.
    package = store.get_final_short_film_package(result.package_id)
    assert package.project_id == 'p' and package.review_id == review.review_id and package.review_decision == 'approved'
    acceptance = ProductionAcceptanceService(storage=store)
    acceptance._outputs_root = tmp_path / 'outputs'
    report = run_async(acceptance.run_acceptance('p', ProductionAcceptanceRunRequest(package_id=result.package_id, include_advisory_checks=False)))
    assert report.disposition == 'ready_for_creator_approval'
    assert report.package_id == result.package_id
    assert acceptance.evaluate_package_approval_guard(result.package_id, desired_status='approved').allowed
    screening = ScreeningRoomService(storage=store, backend_root=tmp_path)
    synced = screening.sync_manifest('p')
    entry = next(row for row in synced['outputs'] if row['source_type'] == 'final_package' and row['source_id'] == result.package_id)
    assert store.get_screening_output(entry['screening_output_id'])['original_url'] == result.film_url
    selected = screening.approve_output('p', entry['screening_output_id'], confirmed=True)
    assert selected['approved'] is True
    assert store.get_screening_project_state('p')['current_final_output_id'] == entry['screening_output_id']
    provenance = package.metadata['canonical_delivery_manifest']
    cut = store.get_current_film_cut('p')
    assert provenance['source_cut_id'] == cut['cut_id'] and provenance['scene_ids'] == ['scene_010', 'scene_002']
    assert [row['scene_id'] for row in provenance['scene_provenance']] == ['scene_010', 'scene_002']
    assert provenance['film_url'] == result.film_url == package.final_output_url
    # The export file is retained on disk.
    assert output.is_file()


def test_unfinished_shot_prevents_partial_scene_delivery():
    store = Store([job('ready', number=1), job('failed', number=2, status='failed')])
    with pytest.raises(StateError) as error:
        TakeSelectionService(store).resolve('p', 'scene_001')
    assert error.value.metadata['shot_numbers'] == [2]
