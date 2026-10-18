from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routes.camera_presets import router, get_service
from app.services.camera_preset_service import CameraPresetService
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.storyboard_render_inputs import storyboard_render_inputs
from app.services.project_store import ProjectStore
from app.data.storage import DatabaseStorage
from app.models import StudioProject


def test_catalog_values_and_injected_route():
    service = CameraPresetService()
    catalog = service.catalog()
    assert len({p.id for p in catalog.presets}) == len(catalog.presets)
    assert {'rack-focus', 'orbit-360', 'dolly-zoom', 'reaction', 'through-shot', 'cosmic-pullback'} <= {p.id for p in catalog.presets}
    catalog.presets[0].camera = 'changed'
    assert service.catalog().presets[0].camera != 'changed'
    assert all(p.camera and p.description and p.category for p in catalog.presets)
    # New optics columns — small, curated, distinct ids
    assert len(catalog.lenses) >= 5 and len(catalog.lenses) == len({l.id for l in catalog.lenses})
    assert {'wide-cinema', 'compact-anamorphic', 'vintage-prime', 'clinical-sharp', 'creative-tilt', 'macro'} <= {l.id for l in catalog.lenses}
    focal_ids = [f.id for f in catalog.focal_lengths]
    assert {'14mm', '24mm', '35mm', '50mm', '85mm', '135mm'} <= set(focal_ids)
    assert all(f.mm > 0 for f in catalog.focal_lengths)
    aperture_ids = [a.id for a in catalog.apertures]
    assert {'f1.4', 'f2.8', 'f4', 'f5.6', 'f11'} <= set(aperture_ids)
    app = FastAPI()
    app.include_router(router)
    fake = Mock()
    fake.catalog.return_value = service.catalog()
    app.dependency_overrides[get_service] = lambda: fake
    response = TestClient(app).get('/api/camera-presets')
    assert response.status_code == 200
    payload = response.json()
    assert payload['views'][0]['id'] == 'eye-level'
    assert len(payload['lenses']) >= 5
    assert any(f['mm'] == 50 for f in payload['focal_lengths'])
    assert any(a['f_stop'] == 'f/2.8' for a in payload['apertures'])
    fake.catalog.assert_called_once_with()


def test_shot_recommendation_ids_are_catalog_valid_and_deterministic():
    service = CameraPresetService()
    catalog = service.catalog()
    scene = {'scene_id': 's1', 'text': 'Maya waits by the doorway.\nMAYA\nWe stay.', 'characters': ['Maya'], 'location': 'Doorway'}
    first = service.recommend_for_shot(scene, 1)
    assert service.recommend_for_shot(scene, 1) == first
    valid = (
        {p.id for p in catalog.presets}, {v.id for v in catalog.views},
        {f.id for f in catalog.framings}, {l.id for l in catalog.lenses},
        {f.id for f in catalog.focal_lengths}, {a.id for a in catalog.apertures},
    )
    for shot_number in (1, 2, 3, 5):
        rec = service.recommend_for_shot(scene, shot_number)
        assert rec['preset_id'] in valid[0] and rec['view_id'] in valid[1]
        assert rec['framing_id'] in valid[2] and rec['lens_id'] in valid[3]
        assert rec['focal_length_id'] in valid[4] and rec['aperture_id'] in valid[5]
        assert rec['camera'].strip() and rec['framing'].strip() and rec['why'].strip()
        assert '%' not in rec['why'] and '/10' not in rec['why']
        assert 'Maya' in rec['why']


def test_shot_recommendation_follows_beat_not_position_alone():
    service = CameraPresetService()
    dialogue_scene = {'text': 'Maya faces Dre.\nMAYA\nYou knew.\nDRE\nI know.', 'characters': ['Maya', 'Dre']}
    assert service.recommend_for_shot(dialogue_scene, 2)['preset_id'] == 'two-shot'
    action_scene = {'text': 'Maya enters the market.\nShe scans the stalls.\nMaya runs through the market, weaving past stalls.\nVendors shout and scatter.\nShe vaults a crate.\nShe disappears into the crowd.', 'characters': ['Maya']}
    assert service.recommend_for_shot(action_scene, 2)['preset_id'] == 'side-tracking'
    assert service.recommend_for_shot(dialogue_scene, 1)['preset_id'] == 'pull-back'
    assert service.recommend_for_shot({}, 0)['shot_label'] == 'WIDE'


def test_recommend_route_contract():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post('/api/camera-presets/recommend', json={'scene': {'text': 'Maya waits.'}, 'shot_number': 1})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['preset_id'] == 'pull-back' and payload['focal_length'] == '24mm'
    assert client.post('/api/camera-presets/recommend', json={'scene': {}, 'shot_number': 0}).status_code == 422


def test_recommend_all_plans_every_shot_from_its_own_beat():
    service = CameraPresetService()
    scene = {
        'text': 'Maya enters the market.\nShe scans the stalls.\nMAYA\nYou knew.\nDRE\nI know.\nShe runs into the crowd.',
        'characters': ['Maya', 'Dre'],
    }
    result = service.recommend_for_scene(scene, 3)
    assert result['total_shots'] == 3
    assert [rec['shot_label'] for rec in result['recommendations']] == ['WIDE', 'MEDIUM', 'CLOSE']
    assert result['recommendations'][0]['preset_id'] == 'pull-back'
    assert len({rec['preset_id'] for rec in result['recommendations']}) >= 2
    assert all(rec['why'].strip() for rec in result['recommendations'])
    assert service.recommend_for_scene(scene, 99)['total_shots'] == 12


def test_recommend_all_route_contract():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post('/api/camera-presets/recommend-all', json={'scene': {'text': 'Maya waits.'}, 'total_shots': 3})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['total_shots'] == 3 and len(payload['recommendations']) == 3
    assert client.post('/api/camera-presets/recommend-all', json={'scene': {}, 'total_shots': 0}).status_code == 422


@pytest.fixture
def blueprint(tmp_path):
    storage = DatabaseStorage(str(tmp_path / 'db'))
    project = StudioProject(project_id='camera-film', title='The doorway', execution_summary={
        'scenes': [{'scene_id': 'scene_001', 'description': 'Maya waits by the doorway.', 'characters': ['Maya']}]})
    storage.save_project(project)
    service = StoryboardBlueprintService(storage=storage)
    service.project_store = ProjectStore(str(tmp_path / 'state.json'))
    service.project_store.save_project(project.model_dump())
    detail = service.get_or_create_blueprint(project_id=project.project_id, scene_id='scene_001', shot_count=2)
    return service, detail


def test_plan_persists_per_shot_and_replaces_old_direction(blueprint):
    service, detail = blueprint
    result = service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001', provider='pollinations', shot_number=2,
        camera_plan={'camera': 'Track backward at ground level.', 'framing': 'Close-up'})
    shot = service.get_storyboard_shot(result['storyboard_shot_id'])
    assert shot.visual_plan.camera_movement == 'Track backward at ground level.'
    assert shot.visual_plan.framing == 'Close-up'
    assert storyboard_render_inputs(shot)['parameters']['shot_planning']['camera'] == 'Track backward at ground level.'
    assert 'Track backward at ground level.' in storyboard_render_inputs(shot)['prompt']
    untouched = service.get_storyboard_shot(detail['shots'][0].storyboard_shot_id)
    assert untouched.visual_plan.camera_movement != shot.visual_plan.camera_movement
    service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001', provider='pollinations', shot_number=2,
        camera_plan={'camera': 'Hold stationary.'})
    updated = service.get_storyboard_shot(result['storyboard_shot_id'])
    assert 'Track backward at ground level.' not in updated.render_contract.provider_neutral_prompt
    assert updated.render_contract.provider_neutral_prompt.count('[CREATOR CAMERA PLAN') == 1
    assert updated.visual_plan.framing == 'Close-up'


def test_lens_focal_aperture_are_persisted_and_prompted(blueprint):
    service, detail = blueprint
    result = service.generate_storyboard_image_for_scene_shot(
        project_id='camera-film', scene_id='scene_001', provider='pollinations', shot_number=1,
        camera_plan={
            'camera': 'Hold a wide lock-off.',
            'framing': 'Wide shot',
            'lens': 'Use a compact anamorphic prime — oval bokeh.',
            'focal_length': '35mm',
            'aperture': 'f/2.8',
        },
    )
    shot = service.get_storyboard_shot(result['storyboard_shot_id'])
    assert shot.visual_plan.camera_movement == 'Hold a wide lock-off.'
    assert shot.visual_plan.framing == 'Wide shot'
    assert shot.visual_plan.lens_language == 'Use a compact anamorphic prime — oval bokeh.'
    assert shot.visual_plan.focal_length_mm == 35
    assert shot.visual_plan.aperture == 'f/2.8'
    rendered = storyboard_render_inputs(shot)
    assert rendered['parameters']['shot_planning']['lens'] == 'Use a compact anamorphic prime — oval bokeh.'
    assert rendered['parameters']['shot_planning']['focal_length'] == '35mm'
    assert rendered['parameters']['shot_planning']['aperture'] == 'f/2.8'
    prompt = rendered['prompt']
    assert 'lens: Use a compact anamorphic prime' in prompt
    assert 'focal_length: 35mm' in prompt
    assert 'aperture: f/2.8' in prompt


def test_provider_failure_keeps_saved_plan(blueprint, monkeypatch):
    service, detail = blueprint
    from app.services.storyboard_image_service import storyboard_image_service
    # D4 workflow: save the camera plan via the legacy path (persists without
    # gating), then derive+approve the image prompt against the new canonical
    # text so the Runway path is render-ready.
    service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001', provider='pollinations',
        camera_plan={'camera': 'Orbit.'})
    service.derive_and_approve_image_prompts_for_version(version_id=detail['version'].version_id)
    def fail(**kwargs):
        raise RuntimeError('test provider failure')
    monkeypatch.setattr(storyboard_image_service, 'generate_runway_image', fail)
    before = service.get_storyboard_shot(detail['shots'][0].storyboard_shot_id).model_dump()
    with pytest.raises(RuntimeError):
        service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001')
    assert service.get_storyboard_shot(detail['shots'][0].storyboard_shot_id).model_dump() == before


def test_storyboard_camera_body_contract():
    from app.routes import projects_router, _storyboard_image_service
    app = FastAPI()
    app.include_router(projects_router, prefix="/api/f51/studio")
    fake = Mock()
    fake.generate_storyboard_image_for_scene_shot.return_value = {'status': 'complete'}
    app.dependency_overrides[_storyboard_image_service] = lambda: fake
    client = TestClient(app)
    url = '/api/f51/studio/projects/camera-film/scenes/scene_001/storyboard?shot_number=2'
    response = client.post(url, json={'camera': 'Rack focus.', 'framing': 'Close-up'})
    assert response.status_code == 200, response.text
    assert fake.generate_storyboard_image_for_scene_shot.call_args.kwargs['camera_plan'] == {'camera': 'Rack focus.', 'framing': 'Close-up'}
    assert client.post(url, json={'camera': 'x' * 4001}).status_code == 422
    assert client.post(url, json={'unknown': 'Orbit'}).status_code == 422


def test_invalid_camera_does_not_create_draft(blueprint):
    from app.services.stability import ValidationError
    service, detail = blueprint
    version_id = detail['version'].version_id
    with pytest.raises(ValidationError):
        service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001', camera_plan={'camera': 'x' * 4001}, create_revision=True)
    assert service.get_blueprint_detail(project_id='camera-film', scene_id='scene_001')['version'].version_id == version_id


def test_camera_revision_preserves_approved_shot_and_locked_shot(blueprint):
    from app.services.stability import StateError
    service, detail = blueprint
    bid = detail['blueprint'].blueprint_id
    vid = detail['version'].version_id
    service.run_continuity_review(blueprint_id=bid, version_id=vid)
    service.derive_and_approve_image_prompts_for_version(version_id=vid)
    service.approve_version(blueprint_id=bid, version_id=vid)
    original = service.get_storyboard_shot(detail['shots'][0].storyboard_shot_id).model_dump()
    result = service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001', provider='pollinations', create_revision=True,
        camera_plan={'camera': 'Hold a patient reaction.'})
    assert result['version_id'] != vid
    assert service.get_storyboard_shot(detail['shots'][0].storyboard_shot_id).model_dump() == original
    current = service.get_storyboard_shot(result['storyboard_shot_id'])
    current.locked = True
    service.storage.save_storyboard_shot(current)
    with pytest.raises(StateError):
        service.generate_storyboard_image_for_scene_shot(project_id='camera-film', scene_id='scene_001', provider='pollinations', camera_plan={'camera': 'Orbit.'})
    assert service.get_storyboard_shot(current.storyboard_shot_id).visual_plan.camera_movement == 'Hold a patient reaction.'
