from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.data.storage import DatabaseStorage
from app.adapters import HappyHorseR2VAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.models.character_look import CharacterLookApprovalRequest
from app.routes.character_looks import router, get_character_look_service
from app.services.character_look_service import CharacterLookService, MAX_REFERENCE_BYTES
from app.services.character_profile_service import CharacterProfileService
from app.services.character_visual_reference_service import CharacterVisualReferenceService
from app.services.character_identity_memory_service import CharacterIdentityMemoryService
from app.services.character_staging_service import resolve_character_prompt
from app.services.shot_prompt_builder import build_shot_aware_prompt
from app.services.stability import StateError, ValidationError
from app.utils.character_appearance import appearance_approval


@pytest.fixture
def setup(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "database"))
    char = storage.save_character("film-a", "Maya", {"age": "30", "look": "brown skin, narrow face, short curls", "visual_prompt_summary": "slender build with short curls", "energy": "calm"})
    service = CharacterLookService(storage, tmp_path / "outputs")
    return storage, char, service


def picture(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (32, 48), "brown").save(output, format=format)
    return output.getvalue()


def approve(service, char, **overrides):
    url = service.upload(char["project_id"], char["id"], picture())
    view = service.get(char["project_id"], char["id"])
    request = CharacterLookApprovalRequest(expected_profile_revision=view.profile_revision, face_image_url=url, **overrides)
    return service.approve(char["project_id"], char["id"], request)


def test_upload_is_persisted_candidate_not_approval_and_media_is_scoped(setup):
    storage, char, service = setup
    url = service.upload("film-a", char["id"], picture())
    fresh = CharacterLookService(storage, service.outputs_dir).get("film-a", char["id"])
    assert fresh.status == "draft" and fresh.version == 0
    assert fresh.face_image_url is None
    assert url in [item.image_url for item in fresh.candidates]
    assert fresh.profile_revision != char["updated_at"]
    assert storage.access_media_projects(url) == {"film-a"}
    assert storage.access_media_projects(url + "-guessed") == set()


def test_approval_persists_and_rejects_appearance_edits_but_allows_personality(setup):
    storage, char, service = setup
    locked = approve(service, char)
    assert locked.status == "locked" and locked.version == 1 and locked.approved_at
    assert CharacterLookService(storage, service.outputs_dir).get("film-a", char["id"]).status == "locked"
    profiles = CharacterProfileService(storage)
    for updates in ({"look": "different face"}, {"name": "Another"}, {"age": "50"}, {"visual_prompt_summary": "new hair"}):
        with pytest.raises(StateError, match="locked"):
            profiles.update_character("film-a", char["id"], updates)
    changed = profiles.update_character("film-a", char["id"], {"energy": "restless"})
    assert changed["look"] == char["look"] and changed["age"] == "30"
    assert changed["visual_prompt_summary"] == char["visual_prompt_summary"]
    assert changed["energy"] == "restless"
    assert appearance_approval(changed)["status"] == "locked"
    with pytest.raises(ValidationError):
        profiles.update_character("film-a", char["id"], {"continuity_state_json": "{}"})


def test_partial_profile_update_and_rename_preserve_character_identity(setup):
    storage, char, _ = setup
    profile = CharacterProfileService(storage)
    saved = profile.update_character("film-a", char["id"], {"energy": "tired"})
    assert saved["look"] == char["look"] and saved["visual_prompt_summary"] == char["visual_prompt_summary"]
    renamed = profile.update_character("film-a", char["id"], {"name": "Maya Chen"})
    assert renamed["id"] == char["id"] and renamed["name"] == "Maya Chen"
    assert len(storage.get_characters("film-a")) == 1


def test_approval_rejects_stale_profile_foreign_reference_missing_description(setup):
    storage, char, service = setup
    url = service.upload("film-a", char["id"], picture())
    with pytest.raises(StateError):
        service.approve("film-a", char["id"], CharacterLookApprovalRequest(expected_profile_revision=char["updated_at"], face_image_url=url))
    view = service.get("film-a", char["id"])
    with pytest.raises(ValidationError):
        service.approve("film-a", char["id"], CharacterLookApprovalRequest(expected_profile_revision=view.profile_revision, face_image_url="https://unregistered.example/face.png"))
    other = storage.save_character("film-b", "Other", {"look": "short hair"})
    with pytest.raises(ValidationError):
        service.approve("film-b", other["id"], CharacterLookApprovalRequest(expected_profile_revision=other["updated_at"], face_image_url=url))
    with pytest.raises(LookupError):
        service.upload("film-b", char["id"], picture())
    blank = storage.save_character("film-a", "Blank", {})
    with pytest.raises(ValidationError, match="physical description"):
        approve(service, blank)


def test_revision_preserves_history_and_releases_old_reference_until_reapproved(setup):
    storage, char, service = setup
    first = approve(service, char)
    opened = service.revise("film-a", char["id"], first.profile_revision)
    assert opened.status == "draft" and opened.version == 1 and opened.approved_at is None
    assert CharacterVisualReferenceService().get_reference_locks_for_character(storage, "film-a", char["id"]) == []
    saved = CharacterProfileService(storage).update_character("film-a", char["id"], {"look": "brown skin, long curls"})
    second = service.approve("film-a", char["id"], CharacterLookApprovalRequest(expected_profile_revision=saved["updated_at"], face_image_url=first.face_image_url))
    assert second.version == 2 and "long curls" in second.description
    state = appearance_approval(storage.get_character(char["id"], "film-a"))
    assert state["history"][0]["profile"]["look"] == char["look"]
    assert state["history"][0]["face_image_url"] == first.face_image_url


def test_approved_snapshot_overrides_automatic_references_in_render_and_identity_context(setup):
    storage, char, service = setup
    visual = CharacterVisualReferenceService()
    auto = visual.relock_character_reference(project_id="film-a", character_id=char["id"], image_url="https://example.test/automatic.jpg", storage=storage, capture_method="representative_frame")
    locked = approve(service, char)
    refs = visual.get_reference_locks_for_character(storage, "film-a", char["id"], "look_costume_change")
    assert [ref["image_url"] for ref in refs] == [locked.face_image_url]
    assert refs[0]["capture_method"] == "director_override"
    identity = CharacterIdentityMemoryService().build_records_from_storage(project_id="film-a", storage=storage, character_ids=[char["id"]])[0]
    assert [ref.image_url for ref in identity.approved_visual_references] == [locked.face_image_url]
    assert auto.image_url not in [ref.image_url for ref in identity.approved_visual_references]
    service.revise("film-a", char["id"], locked.profile_revision)
    assert not CharacterIdentityMemoryService().build_records_from_storage(project_id="film-a", storage=storage, character_ids=[char["id"]])[0].approved_visual_references


def test_same_image_director_approval_promotes_automatic_lock(setup):
    storage, char, _ = setup
    visual = CharacterVisualReferenceService()
    args = dict(project_id="film-a", character_id=char["id"], image_url="https://example.test/same.png", storage=storage)
    auto = visual.relock_character_reference(**args, capture_method="representative_frame")
    director = visual.relock_character_reference(**args)
    assert auto.lock_id != director.lock_id
    assert director.capture_method == "director_override"
    replacement = visual.relock_character_reference(**{**args, "image_url": "https://example.test/new.png"}, capture_method="representative_frame")
    assert replacement.lock_id == director.lock_id


def test_new_storyboard_prompt_and_scene_staging_keep_approved_physical_description(setup):
    storage, char, service = setup
    approve(service, char)
    row = storage.get_character(char["id"], "film-a")
    prompt = build_shot_aware_prompt({"text": "Maya enters.", "characters": ["Maya"]}, 1, 1, [row], max_length=2000)
    assert "brown skin" in prompt and "narrow face" in prompt
    class Staging:
        def get_character_staging(self, *args):
            return {"appearance_override": "wearing a raincoat"}
    prompt = resolve_character_prompt(row, "scene_001", "scene_001_shot_001", Staging())
    assert "brown skin" in prompt and "wearing a raincoat" in prompt and "preserve approved face" in prompt


def test_approved_uploaded_portrait_reaches_supported_provider_payload(setup, monkeypatch):
    storage, char, service = setup
    locked = approve(service, char)
    consistency = CharacterVisualReferenceService().build_consistency_payload_for_shot(project_id="film-a", shot_id="scene_001_shot_001", storage=storage, prompt="Maya enters.")
    assert consistency is not None
    assert [ref.image_url for ref in consistency.refs] == [locked.face_image_url]
    monkeypatch.setattr(HappyHorseR2VAdapter, "_outputs_root", staticmethod(lambda: service.outputs_dir))
    adapter = HappyHorseR2VAdapter(ProviderConfig(provider_id="happyhorse-r2v", name="Reference video", enabled=True, is_simulated=False))
    job = RenderJobModel(id="test-job", project_id="film-a", shot_id="scene_001_shot_001", provider="happyhorse-r2v", status="pending", created_at="2026-09-05", updated_at="2026-09-05", input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="Maya enters.", consistency_payload=consistency))
    payload = adapter._build_submit_payload(job=job, resolution="720P", duration=5, ratio="16:9", seed=0, params={})
    media = payload["input"]["media"]
    assert media[0]["url"] == "data:image/png;base64," + base64.b64encode(picture()).decode()
    assert "preserve fixed identity" in payload["input"]["prompt"]


@pytest.mark.asyncio
async def test_descriptor_cannot_change_locked_character_or_race_approval(setup):
    storage, char, service = setup
    llm = AsyncMock(return_value='{"look":"different"}')
    profiles = CharacterProfileService(storage, llm)
    approve(service, char)
    with pytest.raises(StateError):
        await profiles.apply_descriptor("film-a", char["id"], "new character")
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_descriptor_completion_cannot_overwrite_an_approval_that_arrived_during_llm(setup):
    storage, char, service = setup
    async def completion(**kwargs):
        approve(service, char)
        return '{"core_wound":"unspoken grief"}'
    with pytest.raises(StateError):
        await CharacterProfileService(storage, completion).apply_descriptor("film-a", char["id"], "new description")
    assert service.get("film-a", char["id"]).status == "locked"
    assert storage.get_character(char["id"], "film-a")["core_wound"] is None


@pytest.mark.parametrize("data", [b"", b"not an image", b"x" * (MAX_REFERENCE_BYTES + 1)])
def test_invalid_upload_never_creates_candidate(setup, data):
    _, char, service = setup
    with pytest.raises(ValidationError):
        service.upload("film-a", char["id"], data)
    assert service.get("film-a", char["id"]).candidates == []


def test_conditional_write_prevents_concurrent_approval_overwrite(setup, monkeypatch):
    storage, char, service = setup
    image = service.upload("film-a", char["id"], picture())
    before = service.get("film-a", char["id"])
    patch = storage.patch_character_revision
    def raced(project, character, updates, revision):
        patch(project, character, {"look": "new draft"}, revision)
        return patch(project, character, updates, revision)
    monkeypatch.setattr(storage, "patch_character_revision", raced)
    with pytest.raises(StateError):
        service.approve("film-a", char["id"], CharacterLookApprovalRequest(expected_profile_revision=before.profile_revision, face_image_url=image))
    assert service.get("film-a", char["id"]).status == "draft"


def test_revised_editable_look_wins_over_older_migrated_identity(setup):
    storage, char, service = setup
    storage.patch_character_revision("film-a", char["id"], {"appearance_core": "old migrated face", "identity_core_json": '{"facial_identity":"old structured face","skin_tone":"old skin tone"}'}, char["updated_at"])
    locked = approve(service, char)
    assert locked.physical_description == char["look"]
    assert "old migrated" not in locked.description
    record = CharacterIdentityMemoryService().build_records_from_storage(project_id="film-a", storage=storage, character_ids=[char["id"]])[0]
    assert record.identity_core.facial_identity == char["look"]
    assert record.identity_core.skin_tone == ""


def test_api_contract_and_error_statuses(setup):
    _, char, service = setup
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_character_look_service] = lambda: service
    client = TestClient(api)
    path = f"/api/f51/studio/projects/film-a/characters/{char['id']}/look"
    assert client.get("/api/f51/studio/projects/film-a/character-looks").json()["looks"][0]["status"] == "draft"
    upload = client.post(path + "/reference", files={"file": ("face.png", picture(), "image/png")})
    assert upload.status_code == 200
    draft = client.get(path).json()
    payload = {"expected_profile_revision": draft["profile_revision"], "face_image_url": upload.json()["image_url"]}
    approved = client.post(path + "/approve", json=payload)
    assert approved.status_code == 200 and approved.json()["status"] == "locked"
    assert client.post(path + "/approve", json=payload).status_code == 409
    assert client.post(path + "/approve", json={**payload, "auto_approve": True}).status_code == 422
    assert client.get(path.replace("film-a", "film-b")).status_code == 404
    revised = client.post(path + "/revise", json={"expected_profile_revision": approved.json()["profile_revision"]})
    assert revised.status_code == 200 and revised.json()["status"] == "draft"
    bad = client.post(path + "/reference", files={"file": ("fake.png", b"fake", "image/png")})
    assert bad.status_code == 400 and bad.json()["detail"]["error_type"] == "validation_error"


def test_existing_profile_route_enforces_look_approval_and_preserves_partial_fields(setup, monkeypatch):
    from app.routes.projects import router as profiles_router
    from app.services.character_profile_service import character_profile_service

    storage, char, service = setup
    monkeypatch.setattr(character_profile_service, "_storage", storage)
    approve(service, char)
    api = FastAPI()
    api.include_router(profiles_router)
    client = TestClient(api)
    path = f"/api/f51/studio/projects/film-a/characters/{char['id']}"
    blocked = client.put(path, json={"look": "different physical identity"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["error_type"] == "state_error"
    saved = client.put(path, json={"energy": "determined"})
    assert saved.status_code == 200
    assert saved.json()["character"]["look"] == char["look"]
