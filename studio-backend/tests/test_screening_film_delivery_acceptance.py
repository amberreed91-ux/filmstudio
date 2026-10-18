from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.access_context import access_user_id
from app.data.storage import DatabaseStorage
from app.models import FinalShortFilmPackage, StudioProject
from app.models.production_acceptance import ProductionAcceptanceRunRequest
from app.services.production_acceptance_service import ProductionAcceptanceService
from app.services.screening_room_service import ScreeningRoomService
from app.services.stability import StateError
from app.services.video_asset_service import VideoAssetService


class Renderer:
    def list_jobs(self, project_id):
        return []


def make_service(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path / 'screening-integrity.sqlite'))
    storage.save_project(StudioProject(project_id='owned-project', title='Owned', execution_summary={'scenes': []}))
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    screening = ScreeningRoomService(storage=storage, renderer=Renderer())
    screening.outputs_root = outputs.resolve()
    screening.static_root = (tmp_path / 'static').resolve()
    screening.production_acceptance_service._outputs_root = outputs.resolve()
    screening.package_service._outputs_root = outputs.resolve()
    return storage, screening, outputs


def final_package(storage, screening, outputs, *, package_id='package-a', output_url='/outputs/final.mp4'):
    filename = output_url.rsplit('/', 1)[-1]
    path = outputs / filename
    path.write_bytes(b'accepted-candidate-media')
    package = FinalShortFilmPackage(
        package_id=package_id,
        project_id='owned-project',
        film_title='Final cut',
        final_output_url=output_url,
        final_output_path=str(path),
        render_job_ids=['render-a'],
        scene_count=0,
        review_id='review-a',
        review_decision='approved',
        package_status='ready_for_review',
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        metadata={},
    )
    storage.save_final_short_film_package(package)
    assets = VideoAssetService(storage)
    assets._outputs_root = outputs.resolve()
    assets.register_generated_output(
        project_id='owned-project',
        source_url=output_url,
        title='Final output',
        metadata={'package_id': package_id},
    )
    screening._register(
        project_id='owned-project',
        scene_id=None,
        shot_id=None,
        source_type='final_package',
        source_id=package_id,
        output_type='final',
        original_url=output_url,
        created_at=package.created_at,
        metadata={'film_title': package.film_title, 'package_status': package.package_status, 'review_id': package.review_id, 'review_decision': package.review_decision, 'render_job_ids': package.render_job_ids, 'revision_ids': package.revision_ids, 'has_soundtrack': package.has_soundtrack},
        warnings=[],
    )
    return package, storage.list_screening_outputs('owned-project')[0]


def test_film_delivery_final_without_package_scoped_acceptance_cannot_select_it(tmp_path):
    storage, screening, outputs = make_service(tmp_path)
    (outputs / 'delivery.mp4').write_bytes(b'delivered-film')
    storage.save_film('owned-project', 'http://localhost:8010/outputs/delivery.mp4', 1, 1.0, True)
    screening.sync_manifest('owned-project')
    output = next(row for row in storage.list_screening_outputs('owned-project') if row['source_type'] == 'film_delivery')
    with pytest.raises(StateError, match='current canonical cut, package, and exact manifest provenance'):
        screening.approve_output('owned-project', output['screening_output_id'], confirmed=True)
    assert storage.get_screening_project_state('owned-project')['current_final_output_id'] is None


def test_accepted_exact_package_output_can_be_selected(tmp_path):
    storage, screening, outputs = make_service(tmp_path)
    package, output = final_package(storage, screening, outputs)
    acceptance = ProductionAcceptanceService(storage=storage)
    acceptance._outputs_root = outputs.resolve()
    report = asyncio.run(acceptance.run_acceptance(
        'owned-project',
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    ))
    assert report.disposition == 'ready_for_creator_approval'
    selected = screening.approve_output('owned-project', output['screening_output_id'], confirmed=True)
    assert selected['approved'] is True
    assert storage.get_screening_project_state('owned-project')['current_final_output_id'] == output['screening_output_id']


def test_stale_report_does_not_replace_valid_current_final(tmp_path):
    storage, screening, outputs = make_service(tmp_path)
    package_a, output_a = final_package(storage, screening, outputs, package_id='package-a', output_url='/outputs/final.mp4')
    acceptance = ProductionAcceptanceService(storage=storage)
    acceptance._outputs_root = outputs.resolve()
    asyncio.run(acceptance.run_acceptance('owned-project', ProductionAcceptanceRunRequest(package_id=package_a.package_id, include_advisory_checks=False)))
    screening.approve_output('owned-project', output_a['screening_output_id'], confirmed=True)
    prior_current = storage.get_screening_project_state('owned-project')['current_final_output_id']

    package_b, output_b = final_package(storage, screening, outputs, package_id='package-b', output_url='/outputs/other.mp4')
    report = asyncio.run(acceptance.run_acceptance('owned-project', ProductionAcceptanceRunRequest(package_id=package_b.package_id, include_advisory_checks=False)))
    (outputs / 'other.mp4').write_bytes(b'output changed after acceptance')
    assert acceptance.get_latest_report('owned-project', package_id=package_b.package_id).stale is True
    with pytest.raises(StateError):
        screening.approve_output('owned-project', output_b['screening_output_id'], confirmed=True)
    assert storage.get_screening_project_state('owned-project')['current_final_output_id'] == prior_current


def test_output_from_another_project_is_never_approvable(tmp_path):
    storage, screening, _ = make_service(tmp_path)
    other = StudioProject(project_id='other-project', title='Other', execution_summary={'scenes': []})
    storage.save_project(other)
    storage.upsert_screening_output({
        'screening_output_id': 'foreign-output', 'project_id': 'other-project', 'source_type': 'final_package',
        'source_id': 'foreign-package', 'output_type': 'final', 'original_url': 'https://media.example.test/foreign.mp4',
        'playback_url': '/api/f51/studio/projects/other-project/screening/media/foreign-output', 'media_status': 'available',
    })
    with pytest.raises(StateError, match='not found'):
        screening.approve_output('owned-project', 'foreign-output', confirmed=True)
    assert storage.get_screening_project_state('owned-project')['current_final_output_id'] is None


def test_authenticated_non_owner_cannot_run_approval_guard_or_select_output(tmp_path):
    storage, screening, outputs = make_service(tmp_path)
    package, output = final_package(storage, screening, outputs)
    storage.access_save_user({'username': 'owner-user', 'user_id': 'owner-user'}, create=True)
    storage.access_save_user({'username': 'intruder-user', 'user_id': 'intruder-user'}, create=True)
    storage.access_claim_project('owned-project', 'owner-user')
    marker = access_user_id.set('intruder-user')
    try:
        guard = screening.production_acceptance_service.evaluate_package_approval_guard(package.package_id)
        assert guard.allowed is False
        with pytest.raises(StateError, match='project owner'):
            screening.approve_output('owned-project', output['screening_output_id'], confirmed=True)
    finally:
        access_user_id.reset(marker)


def test_cross_project_final_package_is_rejected_by_guard(tmp_path):
    storage, _, outputs = make_service(tmp_path)
    storage.save_project(StudioProject(project_id='other-project', title='Other', execution_summary={'scenes': []}))
    path = outputs / 'other.mp4'
    path.write_bytes(b'other')
    package = FinalShortFilmPackage(
        package_id='foreign-package', project_id='other-project', film_title='Other', final_output_url='/outputs/other.mp4',
        final_output_path=str(path), render_job_ids=[], scene_count=0, review_id='review', review_decision='approved',
        package_status='ready_for_review', created_at='2026-01-01', updated_at='2026-01-01', metadata={},
    )
    storage.save_final_short_film_package(package)
    acceptance = ProductionAcceptanceService(storage=storage)
    acceptance._project_store_service = type('ProjectLookup', (), {'get_project': lambda self, project_id: storage.get_project(project_id).model_dump(mode='json') if storage.get_project(project_id) else None})()
    report = asyncio.run(acceptance.run_acceptance(
        'other-project',
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    ))
    assert report.project_id == 'other-project'
    assert report.disposition in {'blocked', 'insufficient_data'}
    guard = acceptance.evaluate_package_approval_guard(package.package_id)
    assert guard.allowed is False
