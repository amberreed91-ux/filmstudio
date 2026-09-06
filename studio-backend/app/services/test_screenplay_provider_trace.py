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
    storage.save_character(project_id, 'MAYA', {'visual_prompt_summary': 'Black woman with natural locs and a red coat.'})
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
    service._provider_configs['happyhorse'].api_key = 'test-only-credential'
    scene_id = summary['scenes'][0]['scene_id']
    job = service.create_job(project_id=project_id, shot_id=f'{scene_id}_shot_001', provider='happyhorse', prompt='')
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
