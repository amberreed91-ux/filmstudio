from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.adapters.casting_image_adapter import CastingImageAdapter
from app.data.storage import DatabaseStorage
from app.models.character_look import CharacterCastingRequest, CharacterLookApprovalRequest
from app.routes.character_looks import router, get_character_casting_service, get_character_look_service
from app.services.character_casting_service import CharacterCastingService
from app.services.character_look_service import CharacterLookService
from app.services.character_profile_service import CharacterProfileService
from app.services.character_visual_reference_service import CharacterVisualReferenceService
from app.services.stability import PersistenceError, ProviderError, StateError, ValidationError
from app.utils.character_appearance import continuity_document
from app.utils.character_casting import CASTING_KEY


def portrait():
    stream = BytesIO()
    Image.new("RGB", (48, 64), "tan").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def cast(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "database"))
    character = storage.save_character("film", "Maya", {"age": "32", "look": "brown skin, short black curls, narrow face", "visual_prompt_summary": "slender frame", "energy": "calm"})
    looks = CharacterLookService(storage, tmp_path / "outputs")
    adapter = Mock(provider="dashscope", model="qwen-image-max")
    adapter.generate.return_value = portrait()
    service = CharacterCastingService(looks, adapter)
    return storage, character, looks, adapter, service


def request(looks, character, **kwargs):
    return CharacterCastingRequest(expected_profile_revision=looks.get("film", character["id"]).profile_revision, request_id=uuid4(), direction="", **kwargs)


def complete(cast):
    _, char, looks, _, service = cast
    payload = request(looks, char)
    service.start("film", char["id"], payload)
    service.run("film", char["id"], str(payload.request_id))
    return looks.get("film", char["id"]), payload


def test_generates_persistent_scoped_candidates_without_approving_or_changing_profile(cast):
    storage, char, looks, adapter, service = cast
    queued = service.start("film", char["id"], payload := request(looks, char))
    assert queued.casting_generations[0].status == "queued"
    assert queued.face_image_url is None and not queued.candidates
    adapter.generate.assert_not_called()
    service.run("film", char["id"], str(payload.request_id))
    result = CharacterLookService(storage, looks.outputs_dir).get("film", char["id"])
    assert result.status == "draft" and result.face_image_url is None
    assert len(result.candidates) == 3 and len({row.image_url for row in result.candidates}) == 3
    assert result.casting_generations[0].status == "complete"
    assert all(row.matches_current_profile for row in result.candidates)
    assert all(storage.access_media_projects(row.image_url) == {"film"} for row in result.candidates)
    assert storage.get_character(char["id"], "film")["look"] == char["look"]
    assert adapter.generate.call_count == 3
    prompt = adapter.generate.call_args_list[0].args[0]
    assert char["look"] in prompt and "32" in prompt and "slender frame" in prompt
    assert len({call.args[1] for call in adapter.generate.call_args_list}) == 3


def test_only_explicit_approval_feeds_generated_face_into_render_references(cast):
    storage, char, looks, _, _ = cast
    result, _ = complete(cast)
    refs = CharacterVisualReferenceService()
    assert not refs.get_reference_locks_for_character(storage, "film", char["id"])
    locked = looks.approve("film", char["id"], CharacterLookApprovalRequest(expected_profile_revision=result.profile_revision, face_image_url=result.candidates[1].image_url))
    assert locked.face_image_url == result.candidates[1].image_url
    assert [row["image_url"] for row in refs.get_reference_locks_for_character(storage, "film", char["id"])] == [locked.face_image_url]


def test_duplicate_submission_and_workers_never_repeat_paid_calls(cast):
    _, char, looks, adapter, service = cast
    payload = request(looks, char)
    service.start("film", char["id"], payload)
    service.start("film", char["id"], payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: service.run("film", char["id"], str(payload.request_id)), range(2)))
    service.start("film", char["id"], payload)
    service.run("film", char["id"], str(payload.request_id))
    assert adapter.generate.call_count == 3
    assert len(looks.get("film", char["id"]).casting_generations) == 1
    with pytest.raises(StateError, match="different direction"):
        service.start("film", char["id"], payload.model_copy(update={"direction": "different"}))


def test_no_parallel_set_or_locked_or_stale_or_foreign_generation(cast):
    _, char, looks, adapter, service = cast
    payload = request(looks, char)
    service.start("film", char["id"], payload)
    with pytest.raises(StateError, match="already"):
        service.start("film", char["id"], request(looks, char))
    with pytest.raises(StateError, match="changed"):
        service.start("film", char["id"], payload.model_copy(update={"request_id": uuid4()}))
    with pytest.raises(LookupError):
        service.start("foreign", char["id"], payload)
    adapter.generate.assert_not_called()
    service.run("film", char["id"], str(payload.request_id))
    result = looks.get("film", char["id"])
    looks.approve("film", char["id"], CharacterLookApprovalRequest(expected_profile_revision=result.profile_revision, face_image_url=result.candidates[0].image_url))
    with pytest.raises(StateError, match="Revise"):
        service.start("film", char["id"], request(looks, char))


def test_missing_description_configuration_and_oversized_prompt_fail_before_job_creation(cast):
    storage, char, looks, adapter, service = cast
    blank = storage.save_character("film", "Blank", {})
    with pytest.raises(ValidationError, match="physical description"):
        service.start("film", blank["id"], request(looks, blank))
    CharacterProfileService(storage).update_character("film", char["id"], {"look": "curly hair " * 1000})
    with pytest.raises(ValidationError, match="too long"):
        service.start("film", char["id"], request(looks, char))
    CharacterProfileService(storage).update_character("film", char["id"], {"look": "short hair"})
    adapter.check_configured.side_effect = ProviderError("Connection missing")
    with pytest.raises(ProviderError):
        service.start("film", char["id"], request(looks, char))
    assert not looks.get("film", char["id"]).casting_generations
    adapter.generate.assert_not_called()


def test_partial_failure_saves_success_and_new_set_requires_new_id(cast):
    _, char, looks, adapter, service = cast
    adapter.generate.side_effect = [portrait(), ProviderError("Provider timed out")]
    result, payload = complete(cast)
    assert len(result.candidates) == 1 and result.casting_generations[0].status == "partial"
    assert result.casting_generations[0].error == "Provider timed out"
    service.start("film", char["id"], payload)
    service.run("film", char["id"], str(payload.request_id))
    assert adapter.generate.call_count == 2
    adapter.generate.side_effect = None
    next_set, _ = complete(cast)
    assert len(next_set.candidates) == 4 and len(next_set.casting_generations) == 2


def test_profile_change_during_generation_preserves_metadata_and_marks_old_candidates(cast):
    storage, char, looks, adapter, _ = cast
    def generate(*_args):
        CharacterProfileService(storage).update_character("film", char["id"], {"look": "long auburn hair", "energy": "curious"})
        return portrait()
    adapter.generate.side_effect = generate
    result, _ = complete(cast)
    assert result.physical_description == "long auburn hair"
    assert all(not row.matches_current_profile for row in result.candidates)
    assert not result.casting_generations[0].matches_current_profile
    assert storage.get_character(char["id"], "film")["energy"] == "curious"


def test_profile_locked_during_generation_is_never_overwritten(cast):
    _, char, looks, adapter, _ = cast
    chosen = looks.upload("film", char["id"], portrait())
    calls = 0
    def generate(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            view = looks.get("film", char["id"])
            looks.approve("film", char["id"], CharacterLookApprovalRequest(expected_profile_revision=view.profile_revision, face_image_url=chosen))
        return portrait()
    adapter.generate.side_effect = generate
    result, _ = complete(cast)
    assert result.status == "locked" and result.face_image_url == chosen and len(result.candidates) == 4


def test_invalid_provider_image_is_failed_without_candidate_files(cast):
    _, char, looks, adapter, _ = cast
    adapter.generate.return_value = b"invalid image bytes"
    result, _ = complete(cast)
    assert result.casting_generations[0].status == "failed"
    assert not result.candidates and result.face_image_url is None
    assert not list(looks.outputs_dir.rglob("*.png"))
    assert adapter.generate.call_count == 1


def test_registration_failure_cleans_only_unregistered_image(cast, monkeypatch):
    storage, char, looks, adapter, service = cast
    service.start("film", char["id"], payload := request(looks, char))
    original = storage.patch_character_revision
    def patch(project, character, values, revision):
        state = json.loads(values["continuity_state_json"])
        if state[CASTING_KEY][0]["images"]:
            raise RuntimeError("disk unavailable")
        return original(project, character, values, revision)
    monkeypatch.setattr(storage, "patch_character_revision", patch)
    service.run("film", char["id"], str(payload.request_id))
    result = looks.get("film", char["id"])
    assert result.casting_generations[0].status == "failed" and not result.candidates
    assert not list(looks.outputs_dir.rglob("*.png"))
    assert adapter.generate.call_count == 1


def test_interrupted_jobs_expire_without_automatic_provider_replay(cast):
    storage, char, looks, adapter, service = cast
    service.start("film", char["id"], payload := request(looks, char))
    current = storage.get_character(char["id"], "film")
    document = continuity_document(current)
    document[CASTING_KEY][0].update(status="running", deadline=time.time() - 1, worker_id="old-process")
    storage.patch_character_revision("film", char["id"], {"continuity_state_json": json.dumps(document)}, current["updated_at"])
    assert looks.get("film", char["id"]).casting_generations[0].status == "failed"
    service.run("film", char["id"], str(payload.request_id))
    adapter.generate.assert_not_called()
    fresh = service.start("film", char["id"], request(looks, char))
    assert fresh.casting_generations[0].status == "queued"


def test_generation_route_is_typed_and_background_service_owned(cast):
    _, char, looks, adapter, service = cast
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_character_casting_service] = lambda: service
    app.dependency_overrides[get_character_look_service] = lambda: looks
    client = TestClient(app)
    path = f"/api/f51/studio/projects/film/characters/{char['id']}/look"
    payload = request(looks, char).model_dump(mode="json")
    response = client.post(path + "/casting", json=payload)
    assert response.status_code == 202 and response.json()["casting_generations"][0]["status"] == "queued"
    assert client.get(path).json()["casting_generations"][0]["status"] == "complete"
    assert client.post(path + "/casting", json=payload).status_code == 202
    assert adapter.generate.call_count == 3
    assert client.post(path + "/casting", json={**payload, "request_id": "bad"}).status_code == 422
    assert client.post(path + "/casting", json={**payload, "count": 30}).status_code == 422
    assert client.post(path.replace("/film/", "/other/") + "/casting", json=payload).status_code == 404
    assert client.post(path + "/casting", json={**payload, "request_id": str(uuid4())}).status_code == 409


def test_adapter_sends_explicit_traits_without_rewriting_and_persists_download_bytes(monkeypatch):
    import app.adapters.casting_image_adapter as module
    monkeypatch.setattr(module, "get_dashscope_config", lambda: Mock(api_key="test-key", native_api_base_url="https://configured.example/api/v1"))
    post = Mock(return_value=Mock(status_code=200, json=lambda: {"output": {"choices": [{"message": {"content": [{"image": "https://dashscope-result.oss-cn-shanghai.aliyuncs.com/portrait.png"}]}}]}}))
    download = Mock(status_code=200)
    download.iter_content.return_value = [portrait()]
    context = Mock()
    context.__enter__ = Mock(return_value=download)
    context.__exit__ = Mock(return_value=False)
    get = Mock(return_value=context)
    monkeypatch.setattr(module.requests, "post", post)
    monkeypatch.setattr(module.requests, "get", get)
    assert CastingImageAdapter().generate("precise saved physical traits", 19) == portrait()
    parameters = post.call_args.kwargs["json"]["parameters"]
    assert parameters["prompt_extend"] is False and parameters["seed"] == 19 and parameters["n"] == 1
    assert parameters["size"] == "1104*1472"
    assert post.call_args.kwargs["timeout"] == (10, 150)
    assert get.call_args.kwargs["allow_redirects"] is False
    assert "Authorization" not in get.call_args.kwargs


@pytest.mark.parametrize("failure", ["timeout", "403", "missing", "foreign-url"])
def test_adapter_failures_are_structured_and_never_retried(monkeypatch, failure):
    import app.adapters.casting_image_adapter as module
    monkeypatch.setattr(module, "get_dashscope_config", lambda: Mock(api_key="secret", native_api_base_url="https://configured.example"))
    post = Mock()
    if failure == "timeout":
        post.side_effect = module.requests.Timeout("credential-bearing raw error")
    else:
        url = "http://127.0.0.1/private" if failure == "foreign-url" else None
        post.return_value = Mock(status_code=403 if failure == "403" else 200, json=lambda: {"output": {"choices": [{"message": {"content": [{"image": url}]}}]}})
    monkeypatch.setattr(module.requests, "post", post)
    with pytest.raises(ProviderError) as error:
        CastingImageAdapter().generate("portrait", 1)
    assert post.call_count == 1
    assert "secret" not in error.value.message and "credential-bearing" not in error.value.message
