from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, StudioProject
from app.services.film_delivery_service import FilmDeliveryService
from app.services.scene_assembly_service import SceneAssemblyService
from app.services.stability import StateError
from app.services.screening_room_service import ScreeningRoomService


def create_clip(path: Path, color: str) -> None:
    result = subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c={color}:s=320x180:d=0.4:r=24', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors='replace')


def seed_cut(storage: DatabaseStorage, project_id: str, order: list[str], *, approved: bool = True):
    cut_id = f'{project_id}-cut-v1'
    storage.commit_film_cut_version({
        'cut_id': cut_id,
        'project_id': project_id,
        'version_number': 1,
        'status': 'draft',
        'source_cut_id': None,
        'source_analysis_id': None,
        'source_application_id': None,
        'scene_order': order,
        'timeline': [{'scene_id': scene_id, 'order_index': index} for index, scene_id in enumerate(order)],
        'metadata': {},
        'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-01T00:00:00Z',
    })
    if approved:
        storage.approve_film_cut(project_id, cut_id, 'creator')
    return cut_id


def setup_project(tmp_path: Path, order: list[str], *, approved: bool = True):
    storage = DatabaseStorage(str(tmp_path / 'film-delivery.sqlite'))
    project_id = 'project-delivery'
    scenes = [{'scene_id': scene_id} for scene_id in sorted(order)]
    project = {
        'project_id': project_id,
        'title': 'Delivery test',
        'execution_summary': {'scenes': scenes},
    }
    storage.save_project(StudioProject(**project))
    seed_cut(storage, project_id, order, approved=approved)
    output_root = tmp_path / 'outputs'
    output_root.mkdir()
    for index, scene_id in enumerate(order):
        source = output_root / f'{scene_id}.mp4'
        create_clip(source, 'red' if index % 2 == 0 else 'blue')
        shot_id = f'{scene_id}_shot_001'
        job_id = f'job-{scene_id}'
        storage.save_job(RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider='fixture',
            status='complete',
            input_payload=RenderJobInput(shot_id=shot_id, prompt='fixture', parameters={}),
            output_payload=RenderJobOutput(asset_url=f'/outputs/{scene_id}.mp4'),
            created_at='2026-01-01T00:00:00Z',
            updated_at='2026-01-01T00:00:00Z',
            completed_at='2026-01-01T00:00:00Z',
        ))
        storage.save_scene_composition(project_id, scene_id, f'/outputs/composed-{scene_id}.mp4', 1, 0.4)
        composed_path = output_root / f'composed-{scene_id}.mp4'
        create_clip(composed_path, 'red')
        storage.save_delivery_manifest(project_id, scene_id, {
            'composed_url': f'/outputs/composed-{scene_id}.mp4',
            'job_ids': [job_id],
            'audio_inputs': {shot_id: None},
            'source_media': {shot_id: {
                'job_id': job_id,
                'asset_url': f'/outputs/{scene_id}.mp4',
                'source_kind': 'local_sha256',
                'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            }},
        })
    loader = lambda _project_id: project if _project_id == project_id else None
    assembly = SceneAssemblyService(storage=storage, backend_root=tmp_path)
    async def use_saved_scene_output(*, project_id: str, scene_id: str, **_kwargs):
        manifest = storage.get_delivery_manifest(project_id, scene_id) or {}
        composition = next((row for row in storage.list_scene_compositions_for_project(project_id) if row['scene_id'] == scene_id), None)
        return {'composed_url': composition['composed_url'] if composition else '', 'status': 'existing', 'manifest': manifest}
    assembly.assemble_completed_scene = use_saved_scene_output
    assembly._concat = staticmethod(lambda clips, target: subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', _write_concat_list(clips, target.parent), '-c', 'copy', str(target)],
        capture_output=True, check=True,
    ))
    service = FilmDeliveryService(storage=storage, scenes=assembly, backend_root=tmp_path, project_loader=loader)
    service.scenes._local_path = lambda value: (tmp_path / value.removeprefix('/')) if value.startswith('/outputs/') and (tmp_path / value.removeprefix('/')).is_file() else None
    service._materialize = fake_materialize(tmp_path)
    return storage, service, project_id


def _write_concat_list(clips, directory: Path) -> str:
    path = directory / 'fixture-concat.txt'
    path.write_text(''.join(f"file '{clip.as_posix()}'\n" for clip in clips))
    return str(path)


def fake_materialize(root: Path):
    async def materialize(_client, value: str, target: Path):
        source = root / 'outputs' / value.removeprefix('/outputs/')
        if not source.is_file():
            from app.services.stability import PlaybackError
            raise PlaybackError('fixture scene file is missing', stage='film_delivery_media')
        target.write_bytes(source.read_bytes())
    return materialize


def test_assembly_requires_explicit_approved_cut(tmp_path):
    storage, service, project_id = setup_project(tmp_path, ['scene_001'], approved=False)
    with pytest.raises(StateError, match='Approve the current Film Cut'):
        asyncio.run(service.assemble(project_id))
    assert storage.get_film(project_id) is None


def test_cut_order_manifest_provenance_and_registration_are_exact(tmp_path, monkeypatch):
    order = ['scene_010', 'scene_002']
    storage, service, project_id = setup_project(tmp_path, order)
    candidate_manifests = []
    create_handoff = service._create_package_acceptance_handoff

    def capture_handoff(project_id, result, output, manifest):
        candidate_manifests.append(manifest)
        return create_handoff(project_id, result, output, manifest)

    monkeypatch.setattr(service, '_create_package_acceptance_handoff', capture_handoff)
    result = asyncio.run(service.assemble(project_id))
    manifest = candidate_manifests[0]
    assert result.scene_count == 2
    assert manifest['scene_ids'] == order
    assert manifest['source_cut_id'] == f'{project_id}-cut-v1'
    assert [row['scene_id'] for row in manifest['scene_provenance']] == order
    assert [row['order_index'] for row in manifest['scene_provenance']] == [0, 1]
    assert manifest['scene_ids'] == order
    assert all(row['job_ids'] and row['source_media'] for row in manifest['scene_provenance'])
    assert result.package_id
    package = storage.get_final_short_film_package(result.package_id)
    assert package.project_id == project_id
    assert package.final_output_url == result.film_url
    assert package.metadata['source_cut_id'] == manifest['source_cut_id']
    assert package.metadata['delivery_manifest_hash'] == __import__('hashlib').sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert result.acceptance_report_id
    assert result.acceptance_status in {'blocked', 'needs_attention', 'ready_for_creator_approval', 'insufficient_data'}
    assert result.acceptance_status == 'needs_attention'
    assert next(check for check in storage.get_production_acceptance_report(result.acceptance_report_id).checks if check.check_id == 'review_decision_consistent').severity == 'warning'
    assert ScreeningRoomService(storage=storage, backend_root=tmp_path).sync_manifest(project_id)['current_final_output'] is None
    screening = service.storage.list_screening_outputs(project_id)
    assert result.screening_output_id == ''
    assert not any(row['source_type'] == 'final_package' and row['source_id'] == package.package_id for row in screening)
    assert result.acceptance_status == 'needs_attention'
    assert storage.get_film(project_id) is None
    assert storage.get_delivery_manifest(project_id, '__film__') is None
    screening_service = ScreeningRoomService(storage=storage, backend_root=tmp_path)
    screening = screening_service.sync_manifest(project_id)
    assert not any(
        row['source_type'] == 'final_package' and row['source_id'] == package.package_id
        for row in screening['outputs']
    )
    assert screening['current_final_output'] is None
    assert storage.get_screening_project_state(project_id)['current_final_output_id'] is None


def test_handoff_failure_restores_previous_delivery_or_clears_new_pointer(tmp_path, monkeypatch):
    storage, service, project_id = setup_project(tmp_path, ['scene_001'])
    prior = tmp_path / 'outputs' / 'prior-film.mp4'
    create_clip(prior, 'green')
    storage.save_film(project_id, '/outputs/prior-film.mp4', 1, 0.4, True)
    old_manifest = {'film_url': '/outputs/prior-film.mp4', 'scene_ids': ['scene_001'], 'scene_urls': ['/outputs/composed-scene_001.mp4'], 'source_cut_id': f'{project_id}-cut-v1', 'scene_provenance': []}
    storage.save_delivery_manifest(project_id, '__film__', old_manifest)

    def fail_handoff(*_args):
        raise RuntimeError('acceptance unavailable')

    monkeypatch.setattr(service, '_create_package_acceptance_handoff', fail_handoff)
    with pytest.raises(Exception, match='Film delivery failed'):
        asyncio.run(service.assemble(project_id))
    assert storage.get_film(project_id)['film_url'] == '/outputs/prior-film.mp4'
    assert storage.get_delivery_manifest(project_id, '__film__') == old_manifest


def test_missing_scene_media_provenance_blocks_before_replacing_old_delivery(tmp_path):
    storage, service, project_id = setup_project(tmp_path, ['scene_001', 'scene_002'])
    storage.save_film(project_id, '/outputs/prior-film.mp4', 2, 4.0, True)
    old_manifest = {'film_url': '/outputs/prior-film.mp4', 'scene_ids': ['old']}
    storage.save_delivery_manifest(project_id, '__film__', old_manifest)
    storage.save_delivery_manifest(project_id, 'scene_001', {'composed_url': '/outputs/composed-scene_001.mp4'})
    with pytest.raises(StateError, match='missing or stale'):
        asyncio.run(service.assemble(project_id))
    assert storage.get_film(project_id)['film_url'] == '/outputs/prior-film.mp4'
    assert storage.get_delivery_manifest(project_id, '__film__') == old_manifest


def test_scene_output_from_another_project_cannot_be_used(tmp_path):
    storage, service, project_id = setup_project(tmp_path, ['scene_001'])
    storage.save_scene_composition('foreign-project', 'scene_001', '/outputs/foreign.mp4', 1, 1.0)
    storage.save_delivery_manifest(project_id, 'scene_001', {'composed_url': '/outputs/foreign.mp4', 'job_ids': ['foreign-job'], 'source_media': {'shot': {'sha256': 'foreign'}}})
    with pytest.raises(StateError, match='Scene scene_001'):
        asyncio.run(service.assemble(project_id))
    assert storage.get_film(project_id) is None


def test_rejected_creator_review_preserves_previous_current_screening_final(tmp_path):
    from app.models.production_acceptance import ProductionAcceptanceRunRequest
    from app.services.production_acceptance_service import ProductionAcceptanceService
    from app.services.short_film_review_service import ShortFilmReviewService

    storage, service, project_id = setup_project(tmp_path, ['scene_001'])
    first = asyncio.run(service.assemble(project_id))
    review_service = ShortFilmReviewService(storage=storage)
    review = review_service.create_review(project_id, first.film_url, reviewer='Creator')
    review_service.update_review_decision(review.review_id, 'approved', reviewer='Creator')
    # The creator decision binds to this exact output only; a fresh acceptance
    # run is required before Screening can select it.
    acceptance = ProductionAcceptanceService(storage=storage)
    acceptance._outputs_root = tmp_path / 'outputs'
    report = asyncio.run(acceptance.run_acceptance(
        project_id, ProductionAcceptanceRunRequest(package_id=first.package_id, include_advisory_checks=False)))
    assert report.disposition == 'ready_for_creator_approval'
    assert acceptance.evaluate_package_approval_guard(first.package_id, desired_status='approved').allowed
    screening_service = ScreeningRoomService(storage=storage, backend_root=service.root)
    synced = screening_service.sync_manifest(project_id)
    accepted_output = next(row for row in synced['outputs']
        if row['source_type'] == 'final_package' and row['source_id'] == first.package_id)
    screening_service.approve_output(project_id, accepted_output['screening_output_id'], confirmed=True)
    previous_current = storage.get_screening_project_state(project_id)['current_final_output_id']
    assert previous_current == accepted_output['screening_output_id']

    # A newer export is not yet accepted, so no film pointer persists and no
    # screening output is registered for it.
    next_delivery = asyncio.run(service.assemble(project_id))
    assert next_delivery.screening_output_id == ''
    assert storage.get_film(project_id) is None
    assert storage.get_delivery_manifest(project_id, '__film__') is None
    rejected_review = review_service.create_review(project_id, next_delivery.film_url, reviewer='Creator')
    review_service.update_review_decision(rejected_review.review_id, 'rejected', reviewer='Creator')
    rejected_report = asyncio.run(acceptance.run_acceptance(
        project_id, ProductionAcceptanceRunRequest(package_id=next_delivery.package_id, include_advisory_checks=False)))
    assert rejected_report.disposition != 'ready_for_creator_approval'
    assert not acceptance.evaluate_package_approval_guard(next_delivery.package_id, desired_status='approved').allowed
    resynced = screening_service.sync_manifest(project_id)
    assert not any(row['source_type'] == 'final_package' and row['source_id'] == next_delivery.package_id
        for row in resynced['outputs'])
    assert storage.get_screening_project_state(project_id)['current_final_output_id'] == previous_current


def test_invalid_project_request_does_not_create_delivery(tmp_path):
    storage, service, _project_id = setup_project(tmp_path, ['scene_001'])
    with pytest.raises(StateError, match='Project not found'):
        asyncio.run(service.assemble('missing-project'))
    assert storage.get_film('missing-project') is None


def test_cut_scene_order_change_blocks_prior_delivery_selection(tmp_path):
    storage, service, project_id = setup_project(tmp_path, ['scene_001', 'scene_002'])
    manifest = {'film_url': '/outputs/old.mp4', 'scene_ids': ['scene_001', 'scene_002'], 'scene_urls': ['/outputs/a', '/outputs/b'], 'source_cut_id': f'{project_id}-cut-v1', 'scene_provenance': []}
    storage.save_film(project_id, '/outputs/old.mp4', 2, 2.0, True)
    storage.save_delivery_manifest(project_id, '__film__', manifest)
    # A newly approved current cut makes the prior delivery stale, rather than selecting it.
    cut = storage.get_current_film_cut(project_id)
    new_cut = {**cut, 'cut_id': f'{project_id}-cut-v2', 'version_number': 2, 'status': 'draft', 'scene_order': ['scene_002', 'scene_001'], 'timeline': [], 'source_cut_id': cut['cut_id'], 'approved_at': None, 'approved_by': None}
    storage.commit_film_cut_version(new_cut, supersede_cut_id=cut['cut_id'])
    storage.approve_film_cut(project_id, new_cut['cut_id'], 'creator')
    assert service.status(project_id).film_outdated is True
    assert storage.get_film(project_id)['film_url'] == '/outputs/old.mp4'
    assert storage.get_delivery_manifest(project_id, '__film__') == manifest
