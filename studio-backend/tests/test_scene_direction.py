from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.scene_direction import SaveSceneDirection
from app.services.scene_direction_service import SceneDirectionService
from app.services.project_store import ProjectStore
from app.services.stability import StateError, ValidationError, PersistenceError
from app.services.storyboard_render_inputs import storyboard_render_inputs


@pytest.fixture
def scene(tmp_path):
    storage = DatabaseStorage(str(tmp_path / 'db'))
    project = StudioProject(project_id='direction-film', title='The key', execution_summary={
        'scenes': [{'scene_id': 'scene_001', 'description': 'Maya passes a key to Jules.', 'characters':['Maya','Jules']}],
        'dialogue_lines': [
            {'line_id':'a','scene_id':'scene_001','character_name':'Maya','text':'Keep it.','voice_style_hint':'quiet and deliberate'},
            {'line_id':'b','scene_id':'scene_001','character_name':'Jules','text':'I will.'},
            {'line_id':'other','scene_id':'scene_002','character_name':'Jules','text':'Other scene.'},
        ],
    })
    storage.save_project(project)
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path/'state.json'))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(project_id=project.project_id, scene_id='scene_001', shot_count=2)
    shot=detail['shots'][0];shot.storyboard_image_url='/static/approved-frame.png';storage.save_storyboard_shot(shot)
    return service, storage, detail


def payload_for(data):
    return SaveSceneDirection(expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        handoffs=[shot.model_dump(include={'shot_id','opening_state','action_change','ending_state'}) for shot in data.shots])


def test_explicit_assignment_handoff_snapshot_and_reopen(scene, tmp_path):
    service, storage, detail = scene
    data = service.get('direction-film','scene_001')
    assert data.unassigned_line_ids == ['a','b']
    assert not data.saved
    # Reading does not save creative decisions.
    assert len(storage.list_storyboard_blueprint_versions(detail['blueprint'].blueprint_id)) == 1
    service.blueprints.run_continuity_review(blueprint_id=detail['blueprint'].blueprint_id, version_id=data.version_id)
    service.blueprints.approve_version(blueprint_id=detail['blueprint'].blueprint_id, version_id=data.version_id)
    payload = payload_for(data)
    payload.dialogue[0].shot_id=data.shots[0].shot_id
    payload.handoffs[0].opening_state='Maya holds the key in her right hand.'
    payload.handoffs[0].action_change='Maya places the key in Jules’s left palm.'
    payload.handoffs[0].ending_state='Jules holds the key. Maya’s hands are empty.'
    payload.handoffs[1].opening_state=payload.handoffs[0].ending_state
    saved = service.save('direction-film','scene_001',payload)
    assert saved.version_id != data.version_id and saved.version_status == 'draft'
    assert saved.unassigned_line_ids == ['b']
    assert saved.shots[1].previous_ending_state == payload.handoffs[0].ending_state
    assert saved.shots[0].saved_frame_url == '/static/approved-frame.png'
    original=storage.get_storyboard_blueprint_version(data.version_id)
    assert original.status == 'approved'
    assert storage.list_storyboard_shots(detail['blueprint'].blueprint_id,data.version_id)[0].continuity_plan.opening_state == ''
    with pytest.raises(StateError,match='Approve'):
        service.blueprints.scene_render_inputs('direction-film','scene_001')
    shots=storage.list_storyboard_shots(detail['blueprint'].blueprint_id,saved.version_id)
    inputs=storyboard_render_inputs(shots[0])
    assert inputs['parameters']['dialogue_lines'][0]['text']=='Keep it.'
    assert inputs['parameters']['dialogue_lines'][0]['voice_style_hint']=='quiet and deliberate'
    assert 'Maya holds the key in her right hand.' in inputs['prompt']
    assert inputs['parameters']['continuity_handoff']['reference_frame_url']=='/static/approved-frame.png'
    assert storyboard_render_inputs(shots[1])['parameters']['dialogue_lines']==[]
    reopened=SceneDirectionService(DatabaseStorage(str(tmp_path/'db')))
    assert reopened.get('direction-film','scene_001').model_dump() == saved.model_dump()
    shots[0].storyboard_image_url='/static/replacement.png';storage.save_storyboard_shot(shots[0])
    assert service.get('direction-film','scene_001').shots[0].frame_changed
    # Explicit editing/removal are reversible and do not alter old approvals.
    revision=payload_for(service.get('direction-film','scene_001'))
    revision.dialogue=[]
    for shot in revision.handoffs:
        shot.opening_state=shot.action_change=shot.ending_state=''
    cleared=service.save('direction-film','scene_001',revision)
    assert cleared.dialogue==[] and cleared.shots[0].opening_state==''


def test_stale_foreign_duplicate_locked_and_failed_save_preserve_version(scene, monkeypatch):
    service, storage, detail=scene
    data=service.get('direction-film','scene_001');payload=payload_for(data)
    payload.dialogue[0].shot_id='shot_scene_999_001'
    with pytest.raises(ValidationError):service.save('direction-film','scene_001',payload)
    payload=payload_for(data);payload.dialogue.append(payload.dialogue[0])
    with pytest.raises(ValidationError):service.save('direction-film','scene_001',payload)
    payload=payload_for(data);payload.expected_version_id='stale'
    with pytest.raises(StateError):service.save('direction-film','scene_001',payload)
    shot=detail['shots'][0];shot.locked=True;storage.save_storyboard_shot(shot)
    payload=payload_for(data);payload.handoffs[0].opening_state='Changed'
    with pytest.raises(StateError,match='Unlock'):service.save('direction-film','scene_001',payload)
    shot.locked=False;storage.save_storyboard_shot(shot)
    def fail(**kwargs):raise RuntimeError('disk failure')
    monkeypatch.setattr(storage,'commit_storyboard_blueprint_version',fail)
    with pytest.raises(PersistenceError):service.save('direction-film','scene_001',payload_for(data))
    assert storage.get_storyboard_blueprint('direction-film','scene_001').current_version_id==data.version_id


def test_atomic_version_compare_and_revision_carry_forward(scene):
    service, storage, detail=scene
    data=service.get('direction-film','scene_001');payload=payload_for(data)
    payload.dialogue[0].shot_id=data.shots[0].shot_id
    saved=service.save('direction-film','scene_001',payload)
    with pytest.raises(StateError):service.save('direction-film','scene_001',payload)
    with pytest.raises(ValueError):
        storage.commit_storyboard_blueprint_version(blueprint=detail['blueprint'],version=detail['version'],shots=detail['shots'],expected_version_id=data.version_id)
    assert storage.get_storyboard_blueprint('direction-film','scene_001').current_version_id==saved.version_id
    revised=service.blueprints.create_version(blueprint_id=detail['blueprint'].blueprint_id)
    current=service.get('direction-film','scene_001')
    assert current.dialogue[0].shot_id==data.shots[0].shot_id
    assert revised['shots'][0].render_contract.structured_parameters['dialogue_lines'][0]['line_id']=='a'
    service.blueprints.delete_shot(blueprint_id=detail['blueprint'].blueprint_id,storyboard_shot_id=revised['shots'][0].storyboard_shot_id)
    assert service.get('direction-film','scene_001').dialogue[0].shot_id is None


def test_route_contract_validates_scene_and_preserves_unassigned(scene):
    from app.routes.scene_direction import router, get_service
    service, storage, detail=scene
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_service]=lambda:service
    client=TestClient(app);url='/api/f51/studio/projects/direction-film/scenes/scene_001/direction'
    response=client.get(url);assert response.status_code==200
    data=service.get('direction-film','scene_001');payload=payload_for(data).model_dump()
    payload['dialogue'][0]['shot_id']=data.shots[0].shot_id
    result=client.put(url,json=payload);assert result.status_code==200,result.text
    assert result.json()['unassigned_line_ids']==['b']
    assert client.put(url,json=payload).status_code==409
    payload['dialogue'][0]['text']=' '
    assert client.put(url,json=payload).status_code==422
    assert client.get(url.replace('direction-film','another-film')).status_code==404


def test_previs_override_keeps_saved_handoff_and_dialogue(scene, tmp_path):
    from types import SimpleNamespace
    from app.services.previs_service import PrevisService
    from app.models.previs_render import PrevisRenderSettings
    class FakeRenderer:
        def __init__(self):
            self.jobs = {}
        def create_job(self, **kwargs):
            job = SimpleNamespace(id='direction-previs', status='pending', output_payload=None, error_message=None, **kwargs)
            self.jobs[job.id] = job
            return job
        async def submit_job(self, job_id):
            return self.jobs[job_id]
    from conftest import run_async

    service, storage, detail=scene
    data=service.get('direction-film','scene_001');payload=payload_for(data)
    payload.handoffs[0].opening_state='Jules holds the key.'
    payload.dialogue[0].shot_id=data.shots[0].shot_id
    saved=service.save('direction-film','scene_001',payload)
    service.blueprints.run_continuity_review(blueprint_id=detail['blueprint'].blueprint_id, version_id=saved.version_id)
    approved=service.blueprints.approve_version(blueprint_id=detail['blueprint'].blueprint_id, version_id=saved.version_id)
    renderer=FakeRenderer()
    previs=PrevisService(storage=storage,renderer=renderer)
    run_async(previs.generate_scene('direction-film','scene_001',storyboard_shot_id=approved['shots'][0].storyboard_shot_id,render_settings=PrevisRenderSettings(prompt='A close-up of Jules.')))
    job=next(iter(renderer.jobs.values()))
    assert 'A close-up of Jules.' in job.prompt
    assert 'Opening state: Jules holds the key.' in job.prompt
    assert job.parameters['dialogue_lines'][0]['text']=='Keep it.'


def test_scene_pipeline_uses_assigned_lines_and_explicit_silence(tmp_path, monkeypatch):
    from app.services.test_scene_production_pipeline_service import FakeRenderService, FakeAudioService, FakeStitchingService, _project
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService
    from conftest import run_async
    outputs=tmp_path/'outputs'/'renders';outputs.mkdir(parents=True)
    audio=FakeAudioService();render=FakeRenderService(outputs)
    service=SceneProductionPipelineService(render_svc=render,audio_svc=audio,stitching_svc=FakeStitchingService(),backend_root=tmp_path)
    shots=[{'shot_id':'scene_001_shot_001','prompt':'Wide','parameters':{'dialogue_lines':[]}}, {'shot_id':'scene_001_shot_002','prompt':'Close','parameters':{'dialogue_lines':[{'character':'Dre','text':'Assigned only here.'}]}}]
    monkeypatch.setattr(service,'_resolve_ordered_shots',lambda *args:shots)
    run_async(service.generate_scene(project_id='project_test',scene_id='scene_001',project=_project(),save_project=lambda project:project))
    assert audio.calls[0]['dialogue_lines']==[]
    assert audio.calls[1]['dialogue_lines']==[{'character':'Dre','text':'Assigned only here.'}]


def test_existing_contract_dialogue_and_unchanged_locked_shots_survive(scene):
    service, storage, detail=scene
    shot=detail['shots'][0]
    shot.render_contract.structured_parameters['dialogue_lines']=[{'line_id':'a','character':'Maya','text':'Keep it.'}]
    shot.locked=True
    storage.save_storyboard_shot(shot)
    data=service.get('direction-film','scene_001')
    assert data.dialogue[0].shot_id==shot.shot_id
    payload=payload_for(data)
    payload.handoffs[1].ending_state='Jules steps through the doorway.'
    saved=service.save('direction-film','scene_001',payload)
    copied=storage.list_storyboard_shots(detail['blueprint'].blueprint_id,saved.version_id)[0]
    assert copied.locked
    assert copied.render_contract.structured_parameters == shot.render_contract.structured_parameters
