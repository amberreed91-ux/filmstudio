from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.reference_assets import router
from app.services.reference_asset_service import ReferenceAssetService
from app.services.render import RenderService


@pytest.fixture
def storage(tmp_path: Path):
    return DatabaseStorage(str(tmp_path / "library"))


def asset(ref_id, target_type, target_id, kind, category, *, canonical=False, approval_state="approved", source_kind="uploaded"):
    return {
        "ref_id": ref_id,
        "project_id": "film-a",
        "target_type": target_type,
        "target_id": target_id,
        "kind": kind,
        "category": category,
        "image_url": f"https://cdn.example/{ref_id}.png",
        "canonical": canonical,
        "approval_state": approval_state,
        "source_kind": source_kind,
    }


def test_character_library_keeps_canonical_and_supporting_categories(storage):
    service = ReferenceAssetService(storage)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    storage.save_reference_asset(asset("maya-profile", "character", "maya", "character_full", "profile"))
    storage.save_reference_asset(asset("maya-night", "character", "maya", "character_full", "night"))

    library = service.list_library("film-a", "character", "maya")

    assert library["canonical"]["ref_id"] == "maya-canonical"
    assert {item["category"] for item in library["supporting"]} == {"profile", "night"}
    assert library["canonical"]["image_url"] != library["supporting"][0]["image_url"]


def test_generated_candidate_requires_approval_and_approval_does_not_change_canonical(storage):
    service = ReferenceAssetService(storage)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    storage.save_reference_asset(asset("maya-generated", "character", "maya", "character_full", "fear", approval_state="candidate", source_kind="generated"))

    before = service.list_library("film-a", "character", "maya")
    assert [item["ref_id"] for item in before["candidates"]] == ["maya-generated"]
    assert before["canonical"]["ref_id"] == "maya-canonical"

    approved = service.approve_supporting("film-a", "maya-generated")
    after = service.list_library("film-a", "character", "maya")
    assert approved["approval_state"] == "approved"
    assert after["canonical"]["ref_id"] == "maya-canonical"
    assert [item["ref_id"] for item in after["supporting"]] == ["maya-generated"]


def test_supporting_removal_does_not_delete_character_or_canonical(storage):
    service = ReferenceAssetService(storage)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    storage.save_reference_asset(asset("maya-profile", "character", "maya", "character_full", "profile"))

    assert service.remove_supporting("film-a", "maya-profile") is True
    assert storage.get_reference_asset("maya-canonical") is not None
    with pytest.raises(ValueError):
        service.remove_supporting("film-a", "maya-canonical")


def test_setting_library_supports_multiple_categories_and_isolates_targets(storage):
    service = ReferenceAssetService(storage)
    storage.save_reference_asset(asset("apt-canonical", "setting", "scene-1", "environment", "wide", canonical=True))
    storage.save_reference_asset(asset("apt-detail", "setting", "scene-1", "environment", "architecture"))
    storage.save_reference_asset(asset("other-detail", "setting", "scene-2", "environment", "architecture"))

    library = service.list_library("film-a", "setting", "scene-1")
    assert library["canonical"]["ref_id"] == "apt-canonical"
    assert [item["ref_id"] for item in library["supporting"]] == ["apt-detail"]
    assert "other-detail" not in {item["ref_id"] for item in library["supporting"]}


def test_render_consumes_approved_library_refs_but_not_candidates(monkeypatch):
    class ReferenceStorage:
        def list_reference_assets(self, **_kwargs):
            return [
                asset("canonical", "character", "maya", "character_face", "face", canonical=True),
                asset("supporting", "character", "maya", "character_full", "profile"),
                asset("candidate", "character", "maya", "character_full", "generated", approval_state="candidate", source_kind="generated"),
            ]

    import app.services.render as render_module
    monkeypatch.setattr(render_module, "_storage", ReferenceStorage())
    payload = RenderService._build_reference_consistency_payload(object(), "film-a")

    assert payload is not None
    assert {ref.ref_id for ref in payload.refs} == {"canonical", "supporting"}


def test_library_routes_enforce_scope_and_protect_canonical(storage, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    from app.routes import reference_assets as routes
    monkeypatch.setattr(routes, "reference_asset_service", ReferenceAssetService(storage))

    bad_scope = client.post("/api/f51/studio/projects/film-a/reference-library/character/maya", json=asset("bad", "setting", "scene-1", "environment", "wrong"))
    assert bad_scope.status_code == 400

    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    protected = client.delete("/api/f51/studio/projects/film-a/reference-library/character/maya/maya-canonical")
    assert protected.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# First-class reference image uploads — lifecycle and fail-closed behavior.
#
# Proves that a character or setting image entering through the upload endpoint
# travels the exact same reference_assets registry, approval gate, and
# generation pipeline as a URL-based reference. The only difference is
# ingestion:
#
#     upload bytes → validate → persist file → candidate row → approve →
#     supporting registry → selected scene → reference resolution → provider payload
#
# The upload path must never touch the canonical reference, never auto-approve,
# never submit anything to a provider, and leave no record behind on failure.
# ═══════════════════════════════════════════════════════════════════════════


def _png_bytes() -> bytes:
    """A genuinely valid 4x4 PNG, generated in-process (no fixture files)."""
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (4, 4), (120, 60, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _broken_bytes() -> bytes:
    return b"this is definitely not an image"


def _upload_client(storage, tmp_path: Path, monkeypatch) -> TestClient:
    from app.routes import reference_assets as routes
    from app.services import reference_asset_service as service_module

    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(routes, "reference_asset_service", ReferenceAssetService(storage))
    monkeypatch.setattr(service_module, "_backend_outputs_dir", lambda: tmp_path / "outputs")
    return TestClient(app)


def _upload(client: TestClient, target_type: str, target_id: str, data: bytes, category: str = "face"):
    return client.post(
        f"/api/f51/studio/projects/film-a/reference-library/{target_type}/{target_id}/upload",
        files={"file": ("anything.png", data, "image/png")},
        data={"category": category},
    )


def test_character_image_upload_enters_as_candidate(storage, tmp_path, monkeypatch):
    """Character image upload creates one candidate row, canonical untouched."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))

    response = _upload(client, "character", "maya", _png_bytes(), category="night")
    assert response.status_code == 200
    uploaded = response.json()["reference_asset"]
    assert uploaded["approval_state"] == "candidate"
    assert uploaded["source_kind"] == "uploaded"
    assert not uploaded["canonical"], "uploads never become canonical"
    assert uploaded["target_type"] == "character"
    assert uploaded["target_id"] == "maya"
    assert uploaded["kind"] == "character_full"
    assert uploaded["category"] == "night"
    assert uploaded["image_url"].startswith("/outputs/reference-assets/uploads/")

    library = ReferenceAssetService(storage).list_library("film-a", "character", "maya")
    assert [item["ref_id"] for item in library["candidates"]] == [uploaded["ref_id"]]
    assert library["canonical"]["ref_id"] == "maya-canonical"
    assert library["supporting"] == []


def test_setting_image_upload_enters_as_candidate(storage, tmp_path, monkeypatch):
    """Setting image upload is scoped to the setting target."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    response = _upload(client, "setting", "scene-1", _png_bytes(), category="wide")
    assert response.status_code == 200
    uploaded = response.json()["reference_asset"]
    assert uploaded["target_type"] == "setting"
    assert uploaded["target_id"] == "scene-1"
    assert uploaded["kind"] == "environment"
    assert uploaded["approval_state"] == "candidate"
    assert uploaded["source_kind"] == "uploaded"


def test_uploaded_file_is_persisted_inside_served_boundary(storage, tmp_path, monkeypatch):
    """Bytes are stored under the served reference-assets tree with a UUID name."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    response = _upload(client, "character", "maya", _png_bytes())
    uploaded = response.json()["reference_asset"]
    rel = uploaded["image_url"].removeprefix("/outputs/")
    stored = (tmp_path / "outputs" / rel).resolve()
    assert stored.is_file()
    assert stored.read_bytes() == _png_bytes()
    assert "maya" not in str(stored), "raw target id must not appear in the filesystem path"
    assert str(tmp_path) not in uploaded["image_url"], "no raw filesystem paths exposed to the frontend"


def test_uploaded_reference_can_be_approved_into_registry(storage, tmp_path, monkeypatch):
    """Upload → candidate → approve → approved supporting reference."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    uploaded = _upload(client, "character", "maya", _png_bytes(), category="profile").json()["reference_asset"]

    approved = ReferenceAssetService(storage).approve_supporting("film-a", uploaded["ref_id"])
    assert approved["approval_state"] == "approved"
    assert approved["ref_id"] == uploaded["ref_id"]
    assert approved["image_url"] == uploaded["image_url"]

    library = ReferenceAssetService(storage).list_library("film-a", "character", "maya")
    assert [item["ref_id"] for item in library["supporting"]] == [uploaded["ref_id"]]
    assert library["candidates"] == []


def test_uploaded_candidate_and_rejected_never_reach_generation(storage, tmp_path, monkeypatch):
    """The render payload builder skips uploaded candidates and rejected rows."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    candidate = _upload(client, "character", "maya", _png_bytes(), category="face").json()["reference_asset"]
    storage.save_reference_asset(asset("maya-rejected", "character", "maya", "character_full", "night", canonical=False, approval_state="rejected", source_kind="uploaded"))

    import app.services.render as render_module
    monkeypatch.setattr(render_module, "_storage", storage)
    payload = RenderService._build_reference_consistency_payload(object(), "film-a")
    # No approved asset exists in this project, so no payload is built at all.
    included = {ref.ref_id for ref in payload.refs} if payload else set()
    assert candidate["ref_id"] not in included
    assert "maya-rejected" not in included


def test_approved_upload_does_not_replace_canonical(storage, tmp_path, monkeypatch):
    """Approving an uploaded supporting reference leaves the canonical alone."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    uploaded = _upload(client, "character", "maya", _png_bytes()).json()["reference_asset"]

    ReferenceAssetService(storage).approve_supporting("film-a", uploaded["ref_id"])
    library = ReferenceAssetService(storage).list_library("film-a", "character", "maya")
    assert library["canonical"]["ref_id"] == "maya-canonical"
    assert library["canonical"]["image_url"] == "https://cdn.example/maya-canonical.png"
    assert uploaded["ref_id"] in {item["ref_id"] for item in library["supporting"]}
    stored_canonical = storage.get_reference_asset("maya-canonical")
    assert stored_canonical["canonical"]
    assert stored_canonical["approval_state"] == "approved"


def test_uploaded_reference_preserves_target_character_and_setting_ids(storage, tmp_path, monkeypatch):
    """Ownership survives the full storage round-trip."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    char_upload = _upload(client, "character", "maya", _png_bytes()).json()["reference_asset"]
    setting_upload = _upload(client, "setting", "scene-1", _png_bytes()).json()["reference_asset"]

    char_row = storage.get_reference_asset(char_upload["ref_id"])
    setting_row = storage.get_reference_asset(setting_upload["ref_id"])
    assert (char_row["target_type"], char_row["target_id"]) == ("character", "maya")
    assert (setting_row["target_type"], setting_row["target_id"]) == ("setting", "scene-1")
    assert char_row["project_id"] == "film-a"
    assert setting_row["project_id"] == "film-a"


def test_invalid_image_upload_is_rejected(storage, tmp_path, monkeypatch):
    """Unreadable bytes are rejected before anything is persisted."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    response = _upload(client, "character", "maya", _broken_bytes())
    assert response.status_code == 400
    assert "valid" in response.json()["detail"].lower()
    outputs = tmp_path / "outputs"
    assert not outputs.exists() or not any(outputs.rglob("*"))
    assert not storage.list_reference_assets(project_id="film-a", target_type="character", target_id="maya")


def test_oversized_upload_is_rejected_without_registering(storage, tmp_path, monkeypatch):
    """Files above the 10 MB contract are rejected with an actionable error."""
    from app.services.reference_asset_service import MAX_UPLOAD_BYTES

    client = _upload_client(storage, tmp_path, monkeypatch)
    response = _upload(client, "character", "maya", b"x" * (MAX_UPLOAD_BYTES + 1))
    assert response.status_code == 400
    assert "10 MB" in response.json()["detail"]
    assert storage.list_reference_assets(project_id="film-a") == []


def test_failed_upload_leaves_no_invalid_reference_record(storage, tmp_path, monkeypatch):
    """A storage failure after the file is written must not leave a broken row."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    original_save = storage.save_reference_asset

    def failing_save(asset):
        if asset.get("source_kind") == "uploaded":
            return False
        return original_save(asset)

    monkeypatch.setattr(storage, "save_reference_asset", failing_save)
    response = _upload(client, "character", "maya", _png_bytes())
    assert response.status_code == 400
    assert storage.list_reference_assets(project_id="film-a") == []
    outputs = tmp_path / "outputs"
    assert not outputs.exists() or not any(outputs.rglob("*.png")), "no orphaned upload file remains"


def test_upload_does_not_submit_to_provider(storage, tmp_path, monkeypatch):
    """The upload path is registry-only: no provider adapter or queue call."""
    import app.adapters as adapters_module

    def _no_submit(*args, **kwargs):
        raise AssertionError("upload must never reach a provider adapter")

    for name in dir(adapters_module):
        obj = getattr(adapters_module, name)
        if callable(obj) and hasattr(obj, "submit_job"):
            monkeypatch.setattr(obj, "submit_job", _no_submit)
    client = _upload_client(storage, tmp_path, monkeypatch)
    response = _upload(client, "character", "maya", _png_bytes())
    assert response.status_code == 200


def test_uploaded_and_url_references_share_registry_resolution(storage, tmp_path, monkeypatch):
    """Approved uploads and URL refs pass the same downstream validation;
    uploaded candidates are rejected by that same boundary."""
    from app.models import RenderJobInput, RenderJobModel
    from app.models.consistency import ConsistencyPayload, ReferenceAsset
    from app.services import reference_validation as validation
    from app.services.stability import ValidationError

    client = _upload_client(storage, tmp_path, monkeypatch)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    uploaded = _upload(client, "character", "maya", _png_bytes(), category="profile").json()["reference_asset"]
    ReferenceAssetService(storage).approve_supporting("film-a", uploaded["ref_id"])
    storage.save_reference_asset(asset("maya-url", "character", "maya", "character_full", "night", source_kind="confirmed"))
    storage.save_reference_asset(asset("set-canonical", "setting", "set-2", "environment", "wide", canonical=True))
    # Canonical-setting gate context: the scene resolves set-2 through exactly
    # one matching universe location node plus the approved canonical anchor.
    storage.save_universe_node({
        "node_id": "set-2", "project_id": "film-a", "node_type": "location",
        "name": "Set Two", "first_scene": "scene_002", "last_scene": "scene_002",
    })

    monkeypatch.setattr(
        validation.project_store,
        "get_project",
        lambda _: {"project_id": "film-a", "execution_summary": {"scenes": [{"scene_id": "scene_002", "character_ids": ["maya"], "setting_id": "set-2"}]}},
    )

    class StorageAdapter:
        def get_character(self, character_id, project_id):
            return {"id": "maya", "name": "Maya", "project_id": "film-a"} if character_id == "maya" else None

        def list_reference_assets(self, **kwargs):
            return storage.list_reference_assets(**kwargs)

        def get_universe_nodes(self, project_id):
            return storage.get_universe_nodes(project_id)

    def _job(refs):
        return RenderJobModel(
            id="job-shared",
            project_id="film-a",
            shot_id="scene_002_shot_1",
            provider="simulated",
            input_payload=RenderJobInput(consistency_payload=ConsistencyPayload(project_id="film-a", refs=refs, mode="identity_lock")),
        )

    approved_mix = [
        ReferenceAsset(**asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True)),
        ReferenceAsset(**{**asset("maya-url", "character", "maya", "character_full", "night"), "ref_id": "maya-url", "image_url": "https://cdn.example/maya-url.png"}),
        ReferenceAsset(**{**uploaded, "approval_state": "approved", "canonical": False}),
        ReferenceAsset(**{**asset("set-canonical", "setting", "set-2", "environment", "wide", canonical=True), "ref_id": "set-canonical", "image_url": "https://cdn.example/set-canonical.png"}),
    ]
    result = validation.validate_generation_payload(job=_job(approved_mix), storage=StorageAdapter())
    assert result["scene_id"] == "scene_002"
    assert result["setting_id"] == "set-2"

    candidate_mix = [
        ReferenceAsset(**asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True)),
        ReferenceAsset(**{**asset("set-canonical", "setting", "set-2", "environment", "wide", canonical=True), "ref_id": "set-canonical", "image_url": "https://cdn.example/set-canonical.png"}),
        ReferenceAsset(**{**uploaded, "approval_state": "candidate", "canonical": False}),
    ]
    with pytest.raises(ValidationError) as exc:
        validation.validate_generation_payload(job=_job(candidate_mix), storage=StorageAdapter())
    assert exc.value.metadata["failure_type"] == "unapproved_reference"


def test_candidate_only_and_rejected_only_project_fails_closed(storage, monkeypatch):
    """With only candidate/rejected uploads, generation is blocked."""
    from app.services import reference_validation as validation
    from app.services.stability import ValidationError

    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True, approval_state="candidate", source_kind="uploaded"))
    storage.save_reference_asset(asset("maya-rejected", "character", "maya", "character_full", "night", canonical=True, approval_state="rejected", source_kind="uploaded"))
    monkeypatch.setattr(
        validation.project_store,
        "get_project",
        lambda _: {"project_id": "film-a", "execution_summary": {"scenes": [{"scene_id": "scene_002", "character_ids": ["maya"], "setting_id": ""}]}},
    )

    class StorageAdapter:
        def get_character(self, character_id, project_id):
            return {"id": "maya", "name": "Maya", "project_id": "film-a"} if character_id == "maya" else None

        def list_reference_assets(self, **kwargs):
            return storage.list_reference_assets(**kwargs)

    with pytest.raises(ValidationError) as exc:
        validation.resolve_scene_reference_requirements(
            project_id="film-a", scene_id="scene_002", storage=StorageAdapter(),
        )
    assert exc.value.metadata["failure_type"] == "canonical_character_reference_missing"
    assert exc.value.metadata["target_id"] == "maya"


def test_deleted_supporting_upload_does_not_substitute_unrelated_references(storage, tmp_path, monkeypatch):
    """Removing an approved upload leaves no surrogate in the registry."""
    from app.services import reference_validation as validation

    client = _upload_client(storage, tmp_path, monkeypatch)
    storage.save_reference_asset(asset("maya-canonical", "character", "maya", "character_face", "face", canonical=True))
    uploaded = _upload(client, "character", "maya", _png_bytes()).json()["reference_asset"]
    ReferenceAssetService(storage).approve_supporting("film-a", uploaded["ref_id"])
    assert ReferenceAssetService(storage).remove_supporting("film-a", uploaded["ref_id"]) is True
    assert storage.get_reference_asset(uploaded["ref_id"]) is None
    # The canonical reference is still the only remaining anchor — no substitution.
    storage.save_reference_asset(asset("other-char-ref", "character", "char-other", "character_face", "face"))
    # Canonical-setting gate context for the requirements call below.
    storage.save_reference_asset(asset("set-canonical", "setting", "set-2", "environment", "wide", canonical=True))
    storage.save_universe_node({
        "node_id": "set-2", "project_id": "film-a", "node_type": "location",
        "name": "Set Two", "first_scene": "scene_002", "last_scene": "scene_002",
    })
    monkeypatch.setattr(
        validation.project_store,
        "get_project",
        lambda _: {"project_id": "film-a", "execution_summary": {"scenes": [{"scene_id": "scene_002", "character_ids": ["maya"], "setting_id": "set-2"}]}},
    )

    class StorageAdapter:
        def get_character(self, character_id, project_id):
            return {"id": "maya", "name": "Maya", "project_id": "film-a"} if character_id == "maya" else None

        def list_reference_assets(self, **kwargs):
            return storage.list_reference_assets(**kwargs)

        def get_universe_nodes(self, project_id):
            return storage.get_universe_nodes(project_id)

    requirements = validation.resolve_scene_reference_requirements(
        project_id="film-a", scene_id="scene_002", storage=StorageAdapter(),
    )
    # The canonical setting anchor is a legitimate allowed URL under the
    # setting gate; the deleted upload must still leave no surrogate behind.
    assert requirements["allowed_urls"] == ["https://cdn.example/maya-canonical.png", "https://cdn.example/set-canonical.png"]
    assert "https://cdn.example/other-char-ref.png" not in requirements["allowed_urls"]


def test_upload_is_project_scoped(storage, tmp_path, monkeypatch):
    """An upload registered in one project is invisible to another project."""
    client = _upload_client(storage, tmp_path, monkeypatch)
    response = client.post(
        "/api/f51/studio/projects/film-b/reference-library/character/maya/upload",
        files={"file": ("x.png", _png_bytes(), "image/png")},
        data={"category": "face"},
    )
    assert response.status_code == 200
    assert storage.list_reference_assets(project_id="film-a") == []
    assert len(storage.list_reference_assets(project_id="film-b")) == 1
    library = ReferenceAssetService(storage).list_library("film-b", "character", "maya")
    assert library["candidates"][0]["project_id"] == "film-b"


def test_upload_survives_complete_approval_and_generation_path(storage, tmp_path, monkeypatch):
    """Full contract: upload → candidate → approve → registry → payload builder."""
    service = ReferenceAssetService(storage)
    client = _upload_client(storage, tmp_path, monkeypatch)
    uploaded = _upload(client, "character", "maya", _png_bytes(), category="wardrobe").json()["reference_asset"]

    library = service.list_library("film-a", "character", "maya")
    assert library["candidates"][0]["ref_id"] == uploaded["ref_id"]

    service.approve_supporting("film-a", uploaded["ref_id"])
    library = service.list_library("film-a", "character", "maya")
    assert uploaded["ref_id"] in {item["ref_id"] for item in library["supporting"]}

    import app.services.render as render_module
    monkeypatch.setattr(render_module, "_storage", storage)
    payload = RenderService._build_reference_consistency_payload(object(), "film-a")
    ref_ids = {ref.ref_id for ref in payload.refs}
    assert uploaded["ref_id"] in ref_ids
    by_id = {ref.ref_id: ref for ref in payload.refs}
    upl = by_id[uploaded["ref_id"]]
    assert upl.approval_state == "approved"
    assert upl.source_kind == "uploaded"
    assert upl.target_type == "character"
    assert upl.target_id == "maya"
