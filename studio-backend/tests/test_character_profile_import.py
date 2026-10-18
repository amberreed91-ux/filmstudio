from io import BytesIO
from unittest.mock import AsyncMock, Mock
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.character_profile_service import CharacterProfileService, CharacterDescriptorProviderError
from app.services.stability import StateError, ValidationError


@pytest.fixture
def profiles(tmp_path):
    storage = DatabaseStorage(str(tmp_path / 'database'))
    storage.save_project(StudioProject(project_id='new-film', title='New film'))
    storage.save_project(StudioProject(project_id='other-film', title='Other film'))
    llm = AsyncMock(return_value='{"name":"Maya","look":"Short curls","energy":"Watchful"}')
    return CharacterProfileService(storage, llm), storage, llm


def test_empty_cast_read_never_seeds_other_films(profiles, monkeypatch):
    service, storage, _ = profiles
    seed = Mock(side_effect=AssertionError('GET must not seed'))
    monkeypatch.setattr(storage, 'seed_demo_characters', seed)
    storage.save_character('other-film', 'Mara', {'look': 'Coastal jacket'})
    assert service.list_characters('new-film') == []
    assert service.list_characters('new-film') == []
    assert len(service.list_characters('other-film')) == 1
    seed.assert_not_called()


@pytest.mark.asyncio
async def test_import_json_is_project_scoped_and_preserves_existing_profiles(profiles):
    service, storage, llm = profiles
    other = storage.save_character('other-film', 'Maya', {'look': 'Other film look'})
    saved = await service.import_profile_file('new-film', 'Maya.JSON', b'{"name":"Maya","age":32,"look":"Short curls"}')
    assert saved['project_id'] == 'new-film'
    assert saved['look'] == 'Short curls' and saved['age'] == '32'
    assert storage.get_character(other['id'], 'other-film') == other
    with pytest.raises(StateError, match='already has a profile'):
        await service.import_profile_file('new-film', 'maya.json', b'{"name":"maya","look":"Changed"}')
    assert storage.get_character(saved['id'], 'new-film')['look'] == 'Short curls'
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_text_and_word_import_use_document_text(profiles):
    service, storage, llm = profiles
    await service.import_profile_file('new-film', 'Maya.md', b'# Maya\nShort curls, watchful.')
    assert llm.call_args.kwargs['message'] == '# Maya\nShort curls, watchful.'
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Maya, watchful.</w:t></w:r></w:p></w:body></w:document>')
    await service.import_profile_file('other-film', 'Maya.docx', output.getvalue())
    assert llm.call_args.kwargs['message'] == 'Maya, watchful.'


@pytest.mark.asyncio
@pytest.mark.parametrize('filename,data', [('empty.txt', b''), ('bad.json', b'[]'), ('bad.json', b'{"name":" "}'), ('bad.json', b'{"name":"Maya","look":[]}'), ('bad.docx', b'not zip'), ('bad.exe', b'text')])
async def test_invalid_files_create_nothing(profiles, filename, data):
    service, storage, _ = profiles
    with pytest.raises(ValidationError):
        await service.import_profile_file('new-film', filename, data)
    assert storage.get_characters('new-film') == []


@pytest.mark.asyncio
async def test_missing_film_and_failed_analysis_create_nothing(profiles):
    service, storage, llm = profiles
    with pytest.raises(StateError, match='Film not found'):
        await service.import_profile_file('missing', 'maya.txt', b'Maya')
    llm.side_effect = RuntimeError('offline')
    with pytest.raises(CharacterDescriptorProviderError):
        await service.import_profile_file('new-film', 'maya.txt', b'Maya')
    assert storage.get_characters('new-film') == []


def test_import_route_and_empty_cast_contract(profiles, monkeypatch):
    from app.routes import projects
    service, _, _ = profiles
    monkeypatch.setattr(projects, 'character_profile_service', service)
    api = FastAPI()
    api.include_router(projects.router)
    client = TestClient(api)
    assert client.get('/api/f51/studio/projects/new-film/characters').json() == {'characters': []}
    response = client.post('/api/f51/studio/projects/new-film/characters/import-profile', files={'file': ('maya.json', b'{"name":"Maya","look":"Short curls"}', 'application/json')})
    assert response.status_code == 200, response.text
    assert response.json()['character']['project_id'] == 'new-film'
    assert len(client.get('/api/f51/studio/projects/new-film/characters').json()['characters']) == 1
    assert client.get('/api/f51/studio/projects/other-film/characters').json() == {'characters': []}


@pytest.mark.asyncio
async def test_bible_imports_every_sibling_and_fills_only_empty_fields(profiles):
    service, storage, llm = profiles
    saved = storage.save_character('new-film', 'Maya', {'look': 'Creator look'})
    llm.return_value = '{"characters":[{"name":"Maya","look":"Other look","energy":"Watchful"},{"name":"Terrence Cole","age":18},{"name":"Kendrick Cole","age":15}]}'
    result = await service.import_profile_file('new-film', 'family.md', b'Three siblings: Maya, Terrence Cole, Kendrick Cole.', multiple=True)
    assert len(result) == 3
    assert result[0]['id'] == saved['id']
    assert result[0]['look'] == 'Creator look'
    assert result[0]['energy'] == 'Watchful'
    assert result[2]['age'] == '15'
    assert 'every named character' in llm.call_args.kwargs['system_prompt']


@pytest.mark.asyncio
async def test_invalid_later_bible_entry_does_not_save_first(profiles):
    service, storage, _ = profiles
    with pytest.raises(ValidationError):
        await service.import_profile_file('new-film', 'family.json', b'[{"name":"Maya"},{"name":""}]', multiple=True)
    assert storage.get_characters('new-film') == []


def test_bible_route_returns_all_characters(profiles, monkeypatch):
    from app.routes import projects
    service, _, _ = profiles
    monkeypatch.setattr(projects, 'character_profile_service', service)
    api = FastAPI()
    api.include_router(projects.router)
    response = TestClient(api).post('/api/f51/studio/projects/new-film/characters/import-profile', files={'file': ('family.json', b'[{"name":"Terrence Cole"},{"name":"Kendrick Cole"}]', 'application/json')})
    assert response.status_code == 200, response.text
    assert [c['name'] for c in response.json()['characters']] == ['Terrence Cole', 'Kendrick Cole']


@pytest.mark.asyncio
async def test_bible_aliases_keep_one_profile_per_brother(profiles):
    import json
    service, storage, _ = profiles
    rows = [{'name': 'MALCOLM "MAK" COLE'}, {'name': 'MAK', 'energy': 'Watchful'}, {'name': 'TERRENCE "T" COLE'}, {'name': 'T'}]
    result = await service.import_profile_file('new-film', 'bible.json', json.dumps(rows).encode(), multiple=True)
    assert len(result) == 2
    assert result[0]['energy'] == 'Watchful'


def test_skeleton_matches_script_nickname_without_creating_duplicate(profiles):
    service, storage, _ = profiles
    storage.save_project(StudioProject(project_id='new-film', title='New film', script_text='MALCOLM "MAK" COLE, 29.'))
    saved = storage.save_character('new-film', 'MAK', {'look': 'Creator look'})
    result = service.create_skeleton('new-film', 'MALCOLM "MAK" COLE')
    assert result['id'] == saved['id']
    assert len(storage.get_characters('new-film')) == 1


def test_discovery_reads_full_saved_script_and_matches_existing_aliases(profiles):
    service, storage, _ = profiles
    storage.save_project(StudioProject(project_id='new-film', title='New film', script_text='INT. HOME - DAY\nDEON HOLLIS, 25, waits.\nDEON\nHello.\nARIELLE COLE, 9, watches silently.'))
    storage.save_character('new-film', 'Deon', {'look': 'Creator look'})
    result = service.discover_characters('new-film')
    assert result['missing_characters'] == ['ARIELLE COLE']
    assert set(result['characters']) == {'DEON HOLLIS', 'ARIELLE COLE'}
    assert len(storage.get_characters('new-film')) == 1
    saved = service.create_skeleton('new-film', 'DEON HOLLIS')
    assert saved['name'] == 'Deon'


def test_discovery_route_contract(profiles, monkeypatch):
    from app.routes import projects
    service, _, _ = profiles
    monkeypatch.setattr(projects, 'character_profile_service', service)
    api = FastAPI()
    api.include_router(projects.router)
    response = TestClient(api).get('/api/f51/studio/projects/new-film/character-discovery')
    assert response.status_code == 200
    assert response.json() == {'characters': [], 'missing_characters': []}


def test_reconciliation_preserves_imported_details_removes_only_empty_duplicate(profiles):
    service, storage, _ = profiles
    storage.save_project(StudioProject(project_id='new-film', title='Film', script_text='INT. HOME - DAY\nJAMAL "MAL" HINES, 19, waits.\nMAL\nHello.\nARIELLE COLE, 9, watches silently.'))
    empty = storage.save_character('new-film', 'MAL', {})
    saved = storage.save_character('new-film', 'Jamal Mal Hines', {'look': 'Creator portrait description'})
    result = service.reconcile_script_cast('new-film')
    assert result == {'created': 1, 'renamed': 1, 'duplicates_removed': 1, 'needs_review': []}
    assert storage.get_character(empty['id'], 'new-film') is None
    kept = storage.get_character(saved['id'], 'new-film')
    assert kept['look'] == 'Creator portrait description'
    assert kept['name'] == 'JAMAL "MAL" HINES'
    assert service.reconcile_script_cast('new-film') == {'created': 0, 'renamed': 0, 'duplicates_removed': 0, 'needs_review': []}


def test_unused_skeleton_deletion_protects_edits_and_embedded_references(profiles):
    _, storage, _ = profiles
    saved = storage.save_character('new-film', 'MAL', {})
    with storage._get_connection() as conn:
        conn.execute('CREATE TABLE cast_test_references (payload TEXT)')
        conn.execute('INSERT INTO cast_test_references VALUES (?)', ('{"id":"' + saved['id'] + '"}',))
        conn.commit()
    assert not storage.delete_unused_character_skeleton('new-film', saved['id'], saved['updated_at'])
    assert storage.get_character(saved['id'], 'new-film') is not None
    other = storage.save_character('new-film', 'JAMAL', {'look': 'Creator look'})
    assert not storage.delete_unused_character_skeleton('new-film', other['id'], other['updated_at'])
    assert not storage.delete_unused_character_skeleton('other-film', other['id'], other['updated_at'])


def test_reconciliation_route(profiles, monkeypatch):
    from app.routes import projects
    service, storage, _ = profiles
    storage.save_project(StudioProject(project_id='new-film', title='Film', script_text='INT. HOME - DAY\nNURSE\nHello.'))
    monkeypatch.setattr(projects, 'character_profile_service', service)
    api = FastAPI()
    api.include_router(projects.router)
    response = TestClient(api).post('/api/f51/studio/projects/new-film/character-reconciliation')
    assert response.status_code == 200, response.text
    assert response.json()['created'] == 1


def test_collective_cues_are_not_saved_as_an_extra_person(profiles):
    service, storage, _ = profiles
    storage.save_project(StudioProject(project_id='new-film', title='Film', script_text='INT. HOME - DAY\nNURSE\nHello.'))
    old = storage.save_character('new-film', 'ALL FIVE BROTHERS', {})
    result = service.reconcile_script_cast('new-film')
    assert result['duplicates_removed'] == 1
    assert storage.get_character(old['id'], 'new-film') is None
