"""Repeatable screenplay-to-provider-to-storage trace; no paid calls or downloads."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.adapters import HappyHorseAdapter
from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services import render as render_module
from app.services.script_parser import ScriptParser


@pytest.mark.asyncio
async def test_screenplay_facts_reach_provider_and_completed_job_is_persisted(tmp_path, monkeypatch):
    script = 'INT. WORKSHOP - NIGHT\n\nMAYA\nKeep the door closed.\n\nMaya holds a brass key.'
    summary = ScriptParser().build_script_breakdown_bundle(script)
    assert summary['scenes']
    project_id = 'audit-screenplay-trace'
    project = {'project_id': project_id, 'title': 'The Key', 'script_text': script, 'execution_summary': summary}
    render_module.project_store.save_project(project)
    storage = DatabaseStorage(str(tmp_path / 'db'))
    storage.save_project(StudioProject(**project))
    character = storage.save_character(project_id, 'MAYA', {'visual_prompt_summary': 'Black woman with natural locs and a red coat.'})
    # S2 canonical-stack fixture, reused from test_shot_reference_binding._seed /
    # test_render_scene_reference_transition.py: universe location node +
    # approved environment anchor + approved canonical character ref. Adds only
    # authority the reference gates demand; existing assertions are untouched.
    scene_id_for_setting = summary['scenes'][0]['scene_id']
    setting_id = 'audit-screenplay-trace-setting'
    storage.save_universe_node({
        'node_id': setting_id,
        'project_id': project_id,
        'node_type': 'location',
        'name': 'WORKSHOP',
        'first_scene': scene_id_for_setting,
        'last_scene': scene_id_for_setting,
    })
    storage.save_reference_asset({
        'ref_id': 'audit-screenplay-trace-setting-anchor',
        'project_id': project_id,
        'target_type': 'setting',
        'target_id': setting_id,
        'kind': 'environment',
        'image_url': 'https://cdn.example.test/audit-screenplay-trace-setting.png',
        'canonical': True,
        'approval_state': 'approved',
        'source_kind': 'confirmed',
    })
    storage.save_reference_asset({
        'ref_id': 'audit-screenplay-trace-maya-face',
        'project_id': project_id,
        'target_type': 'character',
        'target_id': character['id'],
        'kind': 'character_face',
        'image_url': 'https://cdn.example.test/audit-screenplay-trace-maya-face.png',
        'canonical': True,
        'approval_state': 'approved',
        'source_kind': 'confirmed',
    })
    monkeypatch.setattr(render_module, '_storage', storage)
    monkeypatch.setattr('app.data.storage.get_storage', lambda *args, **kwargs: storage)
    for name in ('_run_continuity_review', '_run_render_quality_check', '_run_character_reference_lock', '_notify_update'):
        monkeypatch.setattr(render_module, name, AsyncMock())
    captured = []
    async def request(self, method, path, payload=None):
        if method == 'POST':
            captured.append(deepcopy(payload))
            return {'output': {'task_id': 'test-hosted-task'}}
        return {'output': {'task_status': 'SUCCEEDED', 'video_url': 'https://example.test/generated.mp4'}}
    async def download(self, **kwargs):
        return '/outputs/test-generated.mp4', {'test_double': True}
    monkeypatch.setattr(HappyHorseAdapter, '_happyhorse_request', request)
    monkeypatch.setattr(HappyHorseAdapter, '_download_and_strip_audio', download)
    service = render_module.RenderService()
    # Retired DashScope provider: explicitly re-enabled here only so this
    # historical screenplay-trace test keeps covering the adapter unit.
    # Production defaults keep happyhorse disabled (Runway canonical).
    service._provider_configs['happyhorse'].enabled = True
    service._provider_configs['happyhorse'].api_key = 'test-only-credential'
    # Character-reference routing promotes happyhorse to happyhorse-r2v
    # at submit time; enable the sibling for the same historical coverage.
    service._provider_configs['happyhorse-r2v'].enabled = True
    service._provider_configs['happyhorse-r2v'].api_key = 'test-only-credential'
    scene_id = summary['scenes'][0]['scene_id']
    job = service.create_job(project_id=project_id, shot_id=f'{scene_id}_shot_001', provider='happyhorse', prompt='')
    # Gate 2 authority: attach the server-resolved canonical binding (character +
    # setting) so the final payload carries the approved environment anchor.
    # Reuses ReferenceAssetService.resolve_shot_binding like
    # test_confirmed_reference_binding_handoff.py; no assertions relaxed.
    from app.services.reference_asset_service import ReferenceAssetService
    from app.services.reference_validation import frozen_reference_payload
    resolved = ReferenceAssetService(storage).resolve_shot_binding(project_id, f'{scene_id}_shot_001')
    binding = resolved['binding']
    job.input_payload.referenceAssets = [row['uri'] for row in binding]
    job.input_payload.consistency_payload = frozen_reference_payload(binding, project_id=project_id)
    assert job.input_payload.prompt.strip()
    result = await service.submit_job(job.id)
    assert len(captured) == 1
    prompt = captured[0]['input']['prompt']
    assert 'MAYA' in prompt.upper()
    assert 'key' in prompt.lower()
    assert 'Black woman' in prompt
    assert captured[0]['parameters']['seed'] is not None
    persisted = storage.get_job(job.id)
    assert persisted.status == result.status == 'complete'
    assert persisted.provider_job_id == 'test-hosted-task'
    assert persisted.output_payload.asset_url == '/outputs/test-generated.mp4'
    assert persisted.input_payload.prompt == result.input_payload.prompt
    storage.close()
