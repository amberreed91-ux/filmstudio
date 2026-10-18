from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.scene_direction import CoverageDecision, SaveSceneDirection
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.scene_direction_service import SceneDirectionService
from app.services.project_store import ProjectStore
from app.services.stability import StateError, PersistenceError
from pydantic import ValidationError as PydanticValidationError
from app.services.stability import ValidationError as ServiceValidationError


@pytest.fixture
def scene(tmp_path):
    scene_text = 'INT. ROOM - NIGHT\nMaya stands by the door.\nMAYA\nKeep it.\nJULES\nI will.'
    project = StudioProject(project_id='direction-film', title='The key', script_text=scene_text, execution_summary={
        'scenes': [{'scene_id': 'scene_001', 'description': 'Maya passes a key to Jules.', 'text': scene_text, 'characters':['Maya','Jules']}],
        'dialogue_lines': [
            {'line_id':'a','scene_id':'scene_001','character_name':'MAYA','text':'Keep it.','voice_style_hint':'quiet and deliberate'},
            {'line_id':'b','scene_id':'scene_001','character_name':'JULES','text':'I will.'},
            {'line_id':'other','scene_id':'scene_002','character_name':'Jules','text':'Other scene.'},
        ],
    })
    storage = DatabaseStorage(str(tmp_path / 'db'))
    storage.save_project(project)
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path/'state.json'))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(project_id=project.project_id, scene_id='scene_001', shot_count=2)
    for shot in detail['shots']:
        shot.render_contract.structured_parameters.update({
            'prompt': f'UNCHANGED PROMPT {shot.shot_number}',
            'shot_kind': 'dialogue' if shot.shot_number == 1 else 'close_up',
            'camera_plan': {'camera': 'fixed', 'framing': 'medium'},
            'approved_references': ['ref-unchanged'],
        })
        shot.render_contract.reference_assets = ['ref-unchanged']
        storage.save_storyboard_shot(shot)
    detail['shots'] = storage.list_storyboard_shots(detail['blueprint'].blueprint_id, detail['version'].version_id)
    detail['version'] = storage.get_storyboard_blueprint_version(detail['version'].version_id)
    detail['version'].status = StoryboardBlueprintStatus.APPROVED
    detail['version'].approved_at = '2026-09-30T00:00:00+00:00'
    detail['version'].approved_by = 'temporary-test-creator'
    detail['blueprint'].status = StoryboardBlueprintStatus.APPROVED
    detail['blueprint'].approved_version_id = detail['version'].version_id
    storage.save_storyboard_blueprint_version(detail['version'])
    storage.save_storyboard_blueprint(detail['blueprint'])
    detail['version'] = storage.get_storyboard_blueprint_version(detail['version'].version_id)
    detail['blueprint'] = storage.get_storyboard_blueprint_by_id(detail['blueprint'].blueprint_id)
    return service, storage, detail


def payload_for(data):
    return SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[shot.model_dump(include={'shot_id','opening_state','action_change','ending_state'}) for shot in data.shots],
    )


def test_phase6_load_defaults_unassigned_and_save_without_decisions(scene):
    service, storage, detail = scene
    data = service.get('direction-film','scene_001')
    assert [line.text for line in data.dialogue] == ['Keep it.', 'I will.']
    assert [line.shot_id for line in data.dialogue] == [None, None]
    assert all(row.status == 'UNASSIGNED' for row in data.coverage_decisions)
    assert data.coverage_blocked
    assert all(row.status == 'UNASSIGNED' for row in data.coverage_obligations)
    assert len(storage.list_jobs(project_id='direction-film')) == 0
    source_version = storage.get_storyboard_blueprint_version(data.version_id)
    source_snapshot = source_version.model_dump(mode='json')
    source_shots = {shot.shot_id: shot.model_dump(mode='json') for shot in detail['shots']}
    source_project = storage.get_project('direction-film').model_dump(mode='json')
    saved = service.save('direction-film','scene_001',payload_for(data))
    assert [row.status for row in saved.coverage_decisions if row.obligation_type == 'dialogue'] == ['UNASSIGNED', 'UNASSIGNED']
    assert saved.coverage_blocked
    assert all(row.status == 'UNASSIGNED' for row in saved.coverage_obligations)
    assert saved.version_id != data.version_id and saved.version_status == 'draft'
    assert len(storage.list_storyboard_blueprint_versions(detail['blueprint'].blueprint_id)) == 2
    assert storage.get_storyboard_blueprint_version(data.version_id).model_dump(mode='json') == source_snapshot
    assert storage.get_storyboard_blueprint_version(data.version_id).status == StoryboardBlueprintStatus.APPROVED
    assert {shot.shot_id: shot.model_dump(mode='json') for shot in storage.list_storyboard_shots(detail['blueprint'].blueprint_id, data.version_id)} == source_shots
    assert storage.get_project('direction-film').model_dump(mode='json') == source_project
    assert len(storage.list_jobs(project_id='direction-film')) == 0


def test_assignment_and_omission_persist_without_mutating_source_shots(scene):
    service, storage, detail = scene
    source = service.get('direction-film','scene_001')
    source_snapshot = storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode='json')
    before = {shot.shot_id: shot.model_dump(mode='json') for shot in detail['shots']}
    source_project = storage.get_project('direction-film').model_dump(mode='json')
    payload = payload_for(source)
    decisions = []
    for decision in payload.coverage_decisions:
        if decision.obligation_type == 'content':
            decisions.append(decision.model_copy(update={'status': 'ASSIGNED', 'shot_id': source.shots[0].shot_id}))
        elif decision.obligation_type == 'dialogue' and decision.obligation_id == source.dialogue[0].line_id:
            decisions.append(decision.model_copy(update={'status': 'ASSIGNED', 'shot_id': source.shots[0].shot_id}))
        elif decision.obligation_type == 'dialogue':
            decisions.append(decision.model_copy(update={'status': 'EXPLICITLY_OMITTED', 'reason': 'Creator chose to omit this line.'}))
        else:
            decisions.append(decision)
    payload.coverage_decisions = decisions
    payload.dialogue[0].shot_id = source.shots[0].shot_id
    saved = service.save('direction-film','scene_001',payload)
    by_id = {row.obligation_id: row for row in saved.coverage_decisions if row.obligation_type == 'dialogue'}
    assigned_line = by_id[source.dialogue[0].line_id]
    omitted_line = by_id[source.dialogue[1].line_id]
    assert assigned_line.status == 'ASSIGNED' and assigned_line.shot_id == source.shots[0].shot_id
    assert omitted_line.status == 'EXPLICITLY_OMITTED' and omitted_line.reason == 'Creator chose to omit this line.'
    assert saved.coverage_blocked
    assert storage.get_storyboard_blueprint_version(source.version_id).status == StoryboardBlueprintStatus.APPROVED
    after = storage.list_storyboard_shots(detail['blueprint'].blueprint_id, source.version_id)
    assert {shot.shot_id: shot.model_dump(mode='json') for shot in after} == before
    successor = storage.list_storyboard_shots(detail['blueprint'].blueprint_id, saved.version_id)
    for original, clone in zip(detail['shots'], successor):
        assert clone.render_contract.provider_neutral_prompt == original.render_contract.provider_neutral_prompt
        assert clone.render_contract.structured_parameters['camera_plan'] == original.render_contract.structured_parameters['camera_plan']
        assert clone.render_contract.structured_parameters['approved_references'] == original.render_contract.structured_parameters['approved_references']
        assert clone.render_contract.reference_assets == original.render_contract.reference_assets
        assert {key: value for key, value in clone.render_contract.structured_parameters.items() if key not in {'creator_coverage_decisions', 'covered_content_ids', 'dialogue_disposition', 'dialogue_disposition_reason', 'content_coverage_disposition', 'content_coverage_reason'}} == {key: value for key, value in original.render_contract.structured_parameters.items() if key not in {'creator_coverage_decisions', 'covered_content_ids', 'dialogue_disposition', 'dialogue_disposition_reason', 'content_coverage_disposition', 'content_coverage_reason'}}
    assert storage.get_storyboard_blueprint_version(source.version_id).model_dump(mode='json') == source_snapshot
    assert storage.get_storyboard_blueprint_version(source.version_id).status == StoryboardBlueprintStatus.APPROVED
    assert storage.get_project('direction-film').model_dump(mode='json') == source_project
    assert len(storage.list_jobs(project_id='direction-film')) == 0


def test_rejects_invalid_duplicate_omission_silence_and_stale_choices(scene):
    service, _, _ = scene
    data = service.get('direction-film','scene_001')
    payload = payload_for(data)
    dialogue = next(row for row in payload.coverage_decisions if row.obligation_type == 'dialogue')
    with pytest.raises(PydanticValidationError):
        CoverageDecision(obligation_type='dialogue', obligation_id=dialogue.obligation_id, status='INTENTIONAL_SILENCE', reason='Not allowed')
    payload.coverage_decisions.append(dialogue)
    with pytest.raises(ServiceValidationError):
        service.save('direction-film','scene_001',payload)
    payload = payload_for(data)
    index = next(i for i, row in enumerate(payload.coverage_decisions) if row.obligation_type == 'dialogue')
    payload.coverage_decisions[index] = payload.coverage_decisions[index].model_copy(update={'status': 'EXPLICITLY_OMITTED'})
    with pytest.raises(ServiceValidationError):
        service.save('direction-film','scene_001',payload)
    payload = payload_for(data)
    payload.coverage_decisions.append(CoverageDecision(obligation_type='dialogue', obligation_id='unknown-dialogue', status='UNASSIGNED'))
    with pytest.raises(ServiceValidationError):
        service.save('direction-film','scene_001',payload)
    payload = payload_for(data)
    index = next(i for i, row in enumerate(payload.coverage_decisions) if row.obligation_type == 'content')
    payload.coverage_decisions[index] = payload.coverage_decisions[index].model_copy(update={'status': 'ASSIGNED', 'shot_id': 'foreign-shot'})
    with pytest.raises(ServiceValidationError):
        service.save('direction-film','scene_001',payload)
    payload = payload_for(data)
    payload.expected_version_id = 'stale-version'
    with pytest.raises(StateError):
        service.save('direction-film','scene_001',payload)
    payload = payload_for(data)
    payload.dialogue[0].shot_id = data.shots[0].shot_id
    with pytest.raises(ServiceValidationError):
        service.save('direction-film','scene_001',payload)


def test_prompt_and_narrative_function_cannot_create_dialogue_assignment(scene):
    service, storage, detail = scene
    shot = detail['shots'][0]
    shot.render_contract.structured_parameters['dialogue_lines'] = [{'line_id':'a','character':'MAYA','text':'Keep it.'}]
    storage.save_storyboard_shot(shot)
    shot.intent.narrative_function = 'Maya gives Jules the key.'
    shot.render_contract.provider_neutral_prompt = 'MAYA: Keep it.'
    storage.save_storyboard_shot(shot)
    data = service.get('direction-film','scene_001')
    assert data.dialogue[0].shot_id is None
    assert next(row for row in data.coverage_decisions if row.obligation_type == 'dialogue' and row.obligation_id == 'a').status == 'UNASSIGNED'


def test_route_saves_expected_version_decisions_only(scene):
    from app.routes.scene_direction import router, get_service
    service, _, _ = scene
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_service]=lambda:service
    client=TestClient(app);url='/api/f51/studio/projects/direction-film/scenes/scene_001/direction'
    response=client.get(url);assert response.status_code==200
    data=service.get('direction-film','scene_001');payload=payload_for(data).model_dump()
    result=client.put(url,json=payload);assert result.status_code==200,result.text
    assert result.json()['coverage_blocked'] is True
    assert client.put(url,json=payload).status_code==409
