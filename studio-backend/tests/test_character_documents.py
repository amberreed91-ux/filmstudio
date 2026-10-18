import json
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import AsyncMock
import pytest
from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.project_store import ProjectStore
from app.services.character_profile_service import CharacterProfileService
from app.services.character_document_parser import parse_character_document, match_document_name


def bible_bytes():
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        z.writestr('word/document.xml', '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>Keep timeline versions separate.</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Elena Cruz</w:t></w:r></w:p>
        <w:p><w:r><w:t>Appearance / visual lock: Proposed: silver curls.</w:t></w:r></w:p>
        <w:p><w:r><w:t>Wardrobe: Navy coat.</w:t></w:r></w:p>
        <w:p><w:r><w:t>Voice / dialogue: Measured and low.</w:t></w:r></w:p>
        <w:p><w:r><w:t>Continuity locks: No injury before scene three.</w:t></w:r></w:p>
        <w:p><w:r><w:t>Image generation prompt: Portrait of Elena.</w:t></w:r></w:p>
        </w:body></w:document>''')
    return out.getvalue()


def test_parser_preserves_all_bible_fields_without_llm():
    parsed = parse_character_document('bible.docx', bible_bytes())
    assert parsed['profiles'][0]['wardrobe'] == 'Navy coat.'
    assert parsed['profiles'][0]['continuity_notes'] == 'No injury before scene three.'
    assert parsed['context']['general_notes'] == 'Keep timeline versions separate.'


def test_mothers_and_children_are_never_matched_as_one_person():
    assert match_document_name("Lena's Mother", [{'name': 'Lena', 'id': '1'}]) is None
    assert match_document_name("Little Boy's Mother", [{'name': 'Little Boy', 'id': '1'}, {'name': 'Mother', 'id': '2'}])['id'] == '2'


@pytest.mark.asyncio
async def test_manifest_and_bible_are_repeatable_project_scoped_and_keep_source_details(tmp_path):
    storage = DatabaseStorage(str(tmp_path / 'db'))
    storage.save_project(StudioProject(project_id='harbor', title='Harbor'))
    state = ProjectStore(str(tmp_path / 'projects.json'))
    state.create_project(title='Harbor', project_id='harbor')
    llm = AsyncMock(side_effect=AssertionError('Structured documents must not use the LLM'))
    service = CharacterProfileService(storage, llm, state_store=state, document_root=tmp_path / 'documents')
    manifest = {'project': 'Harbor', 'principal': [{'script_name': 'Elena Cruz', 'age_timeline': '40 in 2024', 'function': 'Harbor pilot', 'asset': 'Persistent locked character'}], 'background_groups': [{'group': 'Dockworkers', 'includes': 'Loaders'}], 'referenced_or_archival_only': [{'name': 'Anne Cruz', 'status': 'Photograph only'}]}
    first = await service.import_profile_file('harbor', 'cast.json', json.dumps(manifest).encode(), multiple=True)
    await service.import_profile_file('harbor', 'bible.docx', bible_bytes(), multiple=True)
    await service.import_profile_file('harbor', 'bible.docx', bible_bytes(), multiple=True)
    rows = service.list_characters('harbor')
    assert len(rows) == 1 and rows[0]['id'] == first[0]['id']
    assert rows[0]['look'] == 'Proposed: silver curls.'
    assert rows[0]['bible']['wardrobe'] == 'Navy coat.'
    assert rows[0]['bible']['category'] == 'principal'
    assert rows[0]['voice_style_prompt'] == 'Measured and low.'
    assert not rows[0]['voice_id']
    assert not rows[0]['continuity_state_json']
    assert len(service.character_documents('harbor')['sources']) == 2
    assert service.character_documents('other-film') == {}
    llm.assert_not_called()


def test_referenced_sections_are_distinct_from_cast_profiles():
    parsed = parse_character_document('cast.json', json.dumps({'principal': [], 'background_groups': [{'group': 'Crowd', 'includes': 'Commuters'}], 'referenced_or_archival_only': [{'name': 'Ancestor', 'status': 'Photo only'}]}).encode())
    assert parsed['profiles'] == []
    assert parsed['context']['background_groups'][0]['group'] == 'Crowd'


@pytest.mark.asyncio
async def test_documents_route_and_original_download_are_project_scoped(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import projects
    storage = DatabaseStorage(str(tmp_path / 'db'))
    storage.save_project(StudioProject(project_id='harbor', title='Harbor'))
    state = ProjectStore(str(tmp_path / 'state.json'))
    state.create_project(title='Harbor', project_id='harbor')
    service = CharacterProfileService(storage, state_store=state, document_root=tmp_path / 'documents')
    monkeypatch.setattr(projects, 'character_profile_service', service)
    api = FastAPI(); api.include_router(projects.router)
    client = TestClient(api)
    data = json.dumps({'project': 'Harbor', 'principal': [{'script_name': 'Elena Cruz', 'function': 'Pilot'}]}).encode()
    response = client.post('/api/f51/studio/projects/harbor/characters/import-profile', files={'file': ('cast.json', data, 'application/json')})
    assert response.status_code == 200, response.text
    library = client.get('/api/f51/studio/projects/harbor/character-documents').json()
    source = library['sources'][0]
    assert 'path' not in source
    url = f"/api/f51/studio/projects/harbor/character-documents/{source['sha256']}/source"
    assert client.get(url).content == data
    assert client.get(url.replace('/harbor/', '/other-project/')).status_code == 404
