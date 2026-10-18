"""Regression tests for ScriptParser's opt-in Runway Router image path.

All provider HTTP is mocked; these tests never contact Runway or generate assets.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.consistency import ReferenceAsset
from app.models.storyboard_blueprint import (
    StoryboardBlueprint,
    StoryboardBlueprintStatus,
    StoryboardBlueprintVersion,
    StoryboardShot,
    StoryboardShotStatus,
)
from app.services.providers.image_provider import submit_image_render
from app.services.stability import PersistenceError, ValidationError
from app.services.video_asset_service import VideoAssetService
from app.services.providers.runway_router_provider import (
    get_router_config_id,
    submit_runway_router_image_render,
)
from app.services.script_parser import ScriptParser


def _scene():
    return {
        "scene_id": "scene_router_test",
        "shots": [],
        "multi_shot_execution_ledger": [
            {
                "shot_id": "scene_router_test_shot_001",
                "storyboard_shot_id": "board-shot-image-1",
                "status": "not_executed",
                "generation_context_id": "generation-context-42",
                "prompt_pack": {"base_prompt": "Creator-approved image prompt."},
                "reference_assets": [
                    "https://cdn.example.test/character.png",
                    "https://cdn.example.test/setting.png",
                ],
            }
        ],
    }


def _selected_router_config():
    return {"image_provider_enabled": True, "image_provider_name": "runway_router"}


def _image_authority_storage(
    *,
    storage_path,
    project_id="image-registration-project",
    scene_id="scene_router_test",
    shot_id="scene_router_test_shot_001",
    character_project_id=None,
    character_approval="approved",
    setting_approval="approved",
    include_character=True,
    include_setting=True,
    setting_id="set-image-1",
    shot_references=None,
    shot_reference_ids=None,
):
    from app.models import StudioProject
    from app.services.project_store import ProjectStore

    storage = DatabaseStorage(str(storage_path))
    if character_project_id is None:
        character_project_id = project_id
    project_store = ProjectStore(str(storage_path / "project-state.json"))
    project = {
        "project_id": project_id,
        "title": "Image authorization",
        "script_text": "",
        "execution_summary": {"scenes": [{
            "scene_id": scene_id,
            "character_ids": ["char-image-1"] if include_character else [],
            "setting_id": setting_id,
            "characters": ["Character One"] if include_character else [],
        }]},
    }

    project_store.save_project(project)
    storage.save_project(StudioProject(**project))
    storage.save_universe_node({
        "node_id": setting_id, "project_id": project_id,
        "node_type": "location", "name": "Set", "first_scene": scene_id,
        "last_scene": scene_id,
    })
    character = {
        "id": "char-image-1", "project_id": character_project_id,
        "name": "Character One", "appearance_core": "A distinctive silhouette",
        "description_status": "verified",
    }
    storage.save_character(project_id, "Character One", character)
    references = []
    if include_character:
        references.append({
            "ref_id": "char-approved", "project_id": character_project_id,
            "kind": "character_face", "image_url": "https://cdn.example.test/character.png",
            "target_type": "character", "target_id": "char-image-1", "category": "face",
            "approval_state": character_approval, "canonical": True, "source_kind": "confirmed",
        })
    if include_setting:
        references.append({
            "ref_id": "setting-approved", "project_id": project_id,
            "kind": "environment", "image_url": "https://cdn.example.test/setting.png",
            "target_type": "setting", "target_id": setting_id, "category": "wide",
            "approval_state": setting_approval, "canonical": True, "source_kind": "confirmed",
        })
    for reference in references:
        storage.save_reference_asset(reference)
    version_id = "image-board-v1"
    blueprint_id = "image-board-1"
    version_metadata = {}
    if project_id == "project_5907c60cddbc" and scene_id == "scene_002":
        version_metadata = {"scene_direction": {"setting_reference_decision": {
            "canonical_setting_id": setting_id,
            "reference_id": (shot_reference_ids or ["scene002-approved-setting-ref"])[-1],
        }}}
    storage.save_storyboard_blueprint(StoryboardBlueprint(
        blueprint_id=blueprint_id, project_id=project_id, scene_id=scene_id,
        current_version_id=version_id, approved_version_id=version_id,
        status=StoryboardBlueprintStatus.APPROVED,
    ))
    storage.save_storyboard_blueprint_version(StoryboardBlueprintVersion(
        version_id=version_id, blueprint_id=blueprint_id, project_id=project_id,
        scene_id=scene_id, status=StoryboardBlueprintStatus.APPROVED,
        approved_at="2026-10-11T10:00:00Z", approved_by="creator-1",
        metadata=version_metadata,
    ))
    selected_uris = shot_references if shot_references is not None else [
        "https://cdn.example.test/character.png",
        "https://cdn.example.test/setting.png",
    ]
    selected_ids = shot_reference_ids if shot_reference_ids is not None else [
        "char-approved",
        "setting-approved",
    ]
    shot = StoryboardShot(
        storyboard_shot_id="board-shot-image-1", blueprint_id=blueprint_id,
        version_id=version_id, project_id=project_id, scene_id=scene_id,
        shot_id=shot_id, shot_number=1, status=StoryboardShotStatus.APPROVED,
        intent={"character_focus": ["Character One"] if include_character else []},
        visual_plan={"reference_asset_ids": selected_ids},
        render_contract={"reference_assets": selected_uris},
    )
    storage.save_storyboard_shot(shot)
    return storage, project_store


def _authorized_image_payload(scene=None, shot=None, references=None):
    scene = scene or _scene()
    shot = shot or scene["multi_shot_execution_ledger"][0]
    return {
        "project_id": "image-registration-project",
        "scene_id": scene["scene_id"],
        "shot_id": shot["shot_id"],
        "storyboard_shot_id": "board-shot-image-1",
        "references": references if references is not None else [
            "https://cdn.example.test/character.png",
            "https://cdn.example.test/setting.png",
        ],
    }


def test_router_image_path_never_uses_comfyui_or_synthesizes_preview_fallback():
    with (
        patch("app.services.script_parser.get_render_provider_config", return_value=_selected_router_config()),
        patch("app.services.script_parser.render_with_comfyui", side_effect=AssertionError("ComfyUI fallback forbidden")),
        patch(
            "app.services.reference_validation.authorize_runway_router_image_references",
            return_value={
                "project_id": "image-registration-project",
                "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001",
                "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1",
                "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "references": _scene()["multi_shot_execution_ledger"][0]["reference_assets"],
                "binding": [],
            },
        ),
        patch(
            "app.services.providers.image_provider.authorize_runway_router_image_references",
            return_value={
                "project_id": "image-registration-project",
                "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001",
                "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1",
                "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "binding": [],
                "references": _scene()["multi_shot_execution_ledger"][0]["reference_assets"],
            },
        ),
        patch(
            "app.services.providers.runway_router_provider.submit_runway_router_image_render",
            return_value={
                "status": "failed",
                "url": None,
                "file_path": None,
                "error": "router_config_not_found",
                "meta": {"reason": "router_config_not_found", "router_config_id": "studio-production-router"},
            },
        ) as submit,
    ):
        result = ScriptParser().build_image_render_assets([_scene()])["image_render_assets"][0]

    assert submit.call_args.args[0] == "Creator-approved image prompt."
    assert submit.call_args.kwargs["references"] == [
        "https://cdn.example.test/character.png",
        "https://cdn.example.test/setting.png",
    ]
    assert result["provider"] == "runway_router"
    assert result["status"] == "failed"
    assert result["url"] is None
    assert result["meta"]["router_execution"]["reason"] == "router_config_not_found"
    assert result["meta"]["router_execution"]["error"] == "router_config_not_found"
    assert result["meta"]["router_execution"]["router_config_id"] == "studio-production-router"


@pytest.mark.parametrize(
    ("task_id", "url", "identity", "expected_status", "expected_reason"),
    [
        ("image-task-42", "https://cdn.example.test/generated.png", None, "failed", "provider_output_identity_missing"),
        (
            "image-task-42",
            "https://cdn.example.test/generated.png",
            {"provider_task_id": "foreign-task", "output_url": "https://cdn.example.test/generated.png", "association_source": "runway_router_polled_task"},
            "failed",
            "provider_output_identity_mismatch",
        ),
        (
            "image-task-42",
            "https://cdn.example.test/generated.png",
            {"provider_task_id": "image-task-42", "output_url": "https://cdn.example.test/foreign.png", "association_source": "runway_router_polled_task"},
            "failed",
            "provider_output_identity_mismatch",
        ),
        (
            "image-task-42",
            "https://cdn.example.test/generated.png",
            {"provider_task_id": "image-task-42", "output_url": "https://cdn.example.test/generated.png", "association_source": "foreign_source"},
            "failed",
            "provider_output_identity_mismatch",
        ),
        (
            "image-task-42",
            "https://cdn.example.test/generated.png",
            {"provider_task_id": "image-task-42", "output_url": "https://cdn.example.test/generated.png", "association_source": "runway_router_polled_task"},
            "success",
            "runway_router_image_generated",
        ),
    ],
)
def test_router_image_seam_requires_a_matching_task_output_association(
    task_id, url, identity, expected_status, expected_reason,
):
    with (
        patch(
            "app.services.providers.image_provider.authorize_runway_router_image_references",
            return_value={
                "project_id": "image-registration-project", "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001", "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1",                "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "references": [],

            },
        ),
        patch(
            "app.services.providers.runway_router_provider.submit_runway_router_image_render",
            return_value={
            "status": "success",
            "url": url,
            "file_path": None,
            "error": None,
            "meta": {"runway_task_id": task_id, "output_identity": identity},
            },
        ),
    ):
        result = submit_image_render(
            {"project_id": "image-registration-project", "scene_id": "scene_router_test", "shot_id": "scene_router_test_shot_001", "base_prompt": "Approved prompt."},
            _selected_router_config(),
        )

    assert result["status"] == expected_status
    assert result["meta"]["reason"] == expected_reason
    if expected_status == "failed":
        assert result["url"] is None


def test_image_reference_authorization_uses_current_project_storyboard_and_registry(tmp_path, monkeypatch):
    from app.services import reference_validation
    from app.services.reference_validation import authorize_runway_router_image_references

    storage, source = _image_authority_storage(storage_path=tmp_path / "valid-image-authority")
    try:
        monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
        authorization = authorize_runway_router_image_references(
            payload=_authorized_image_payload(), storage=storage,
        )
        assert authorization["project_id"] == "image-registration-project"
        assert authorization["scene_id"] == "scene_router_test"
        assert authorization["shot_id"] == "scene_router_test_shot_001"
        assert [row["ref_id"] for row in authorization["references"]] == ["char-approved", "setting-approved"]
        assert all(row["project_id"] == "image-registration-project" for row in authorization["references"])
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("kwargs", "failure_type"),
    [
        ({"character_project_id": "foreign-project"}, "canonical_character_reference_missing"),
        ({"character_approval": "candidate"}, "canonical_character_reference_missing"),
        ({"character_approval": "rejected"}, "canonical_character_reference_missing"),
        ({"setting_approval": "rejected"}, "canonical_setting_reference_missing"),
        ({"include_setting": False}, "canonical_setting_reference_missing"),
        ({"shot_references": ["https://cdn.example.test/foreign.png"]}, "shot_reference_binding_mismatch"),
        ({"shot_reference_ids": ["foreign-reference", "setting-approved"]}, "reference_identity_unproven"),
        ({"shot_reference_ids": ["setting-approved", "char-approved"], "shot_references": ["https://cdn.example.test/setting.png", "https://cdn.example.test/character.png"]}, "shot_reference_binding_mismatch"),
    ],
)
def test_image_reference_authorization_rejects_unprovable_or_changed_bindings(kwargs, failure_type, tmp_path, monkeypatch):
    from app.services import reference_validation
    from app.services.reference_validation import authorize_runway_router_image_references

    storage, source = _image_authority_storage(storage_path=tmp_path / "rejected-image-authority", **kwargs)
    try:
        monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
        with pytest.raises(ValidationError) as exc:
            authorize_runway_router_image_references(
                payload=_authorized_image_payload(), storage=storage,
            )
        assert exc.value.metadata["failure_type"] == failure_type
    finally:
        storage.close()


def test_image_reference_authorization_rejects_same_uri_under_substituted_requested_id(tmp_path, monkeypatch):
    from app.services import reference_validation
    from app.services.reference_validation import authorize_runway_router_image_references

    storage, source = _image_authority_storage(storage_path=tmp_path / "substituted-request-id")
    monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
    payload = _authorized_image_payload(references=[
        {"ref_id": "substitute-id", "uri": "https://cdn.example.test/character.png"},
        {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
    ])

    try:
        with pytest.raises(ValidationError) as exc:
            authorize_runway_router_image_references(payload=payload, storage=storage)
        assert exc.value.metadata["failure_type"] == "shot_reference_binding_mismatch"
    finally:
        storage.close()


def test_image_reference_authorization_keeps_authorized_reference_id_and_uri_order(tmp_path, monkeypatch):
    from app.services import reference_validation
    from app.services.reference_validation import authorize_runway_router_image_references

    storage, source = _image_authority_storage(storage_path=tmp_path / "ordered-image-authority")
    monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
    payload = _authorized_image_payload(references=[
        {"ref_id": "char-approved", "uri": "https://cdn.example.test/character.png"},
        {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
    ])

    try:
        authorization = authorize_runway_router_image_references(payload=payload, storage=storage)
        assert [(row["ref_id"], row["uri"]) for row in authorization["references"]] == [
            ("char-approved", "https://cdn.example.test/character.png"),
            ("setting-approved", "https://cdn.example.test/setting.png"),
        ]
    finally:
        storage.close()


def test_image_provider_direct_call_cannot_bypass_reference_authorization(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.providers.runway_router_provider.submit_runway_router_image_render",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    result = submit_image_render({
        "project_id": "image-registration-project",
        "scene_id": "scene_router_test",
        "shot_id": "scene_router_test_shot_001",
        "base_prompt": "Approved prompt.",
        "references": ["https://cdn.example.test/foreign.png"],
    }, _selected_router_config())

    assert result["status"] == "failed"
    assert result["meta"]["reason"] == "image_reference_authorization_failed"
    assert calls == []


def test_script_parser_router_failure_is_not_success_and_never_registers_asset(tmp_path, monkeypatch):
    from app.services import reference_validation

    storage_path = tmp_path / "image-auth-failure"
    storage, source = _image_authority_storage(
        storage_path=storage_path, include_setting=False,
    )
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_args, **_kwargs: storage)
    monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
    with (
        patch("app.services.script_parser.get_render_provider_config", return_value=_selected_router_config()),
        patch("app.services.script_parser.render_with_comfyui", side_effect=AssertionError("fallback forbidden")),
        patch("app.services.providers.image_provider.authorize_runway_router_image_references") as authorize,
        patch("app.services.providers.runway_router_provider.submit_runway_router_image_render") as submit,
        patch.object(VideoAssetService, "register_generated_image_for_execution") as register,
    ):
        result = _build_router_image_asset(project_id="image-registration-project", execution_id="test-execution")

    assert result["status"] == "failed"
    assert result["url"] is None
    assert result["meta"]["router_execution"]["reason"] == "image_reference_authorization_failed"
    authorize.assert_not_called()
    submit.assert_not_called()
    register.assert_not_called()
    storage.close()


def test_router_image_submission_preserves_reference_order_and_binds_polled_task(monkeypatch):
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    references = [
        {"ref_id": "char-approved", "uri": "https://cdn.example.test/character.png"},
        {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
    ]
    calls = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, url, payload))
        if method == "POST":
            return {
                "dryRun": False,
                "id": "image-task-42",
                "routing": {
                    "model": "gpt_image_2",
                    "provider": "runway",
                    "configId": get_router_config_id(),
                },
            }
        return {
            "id": "image-task-42",
            "status": "SUCCEEDED",
            "output": ["https://cdn.example.test/generated.png"],
        }

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)

    result = submit_runway_router_image_render(
        "Creator-approved image prompt.",
        references=references,
        _sleep=lambda _seconds: None,
    )

    assert [call[0] for call in calls] == ["POST", "GET"]
    assert calls[0][2]["input"]["referenceImages"] == [
        {"uri": "https://cdn.example.test/character.png"},
        {"uri": "https://cdn.example.test/setting.png"},
    ]
    assert calls[1][1].endswith("/v1/tasks/image-task-42")
    assert result["status"] == "success"
    assert result["url"] == "https://cdn.example.test/generated.png"
    assert result["meta"]["output_identity"] == {
        "provider_task_id": "image-task-42",
        "output_url": "https://cdn.example.test/generated.png",
        "association_source": "runway_router_polled_task",
    }


def _successful_router_image_result(**extra_meta):
    return {
        "status": "success",
        "url": "https://cdn.example.test/generated.png",
        "file_path": None,
        "error": None,
        "meta": {
            "reason": "runway_router_generated",
            "routing_mode": "model_router",
            "router_config_id": "studio-production-router",
            "resolved_model": "gpt_image_2",
            "estimated_cost_credits": 18.5,
            "resolved_settings": {"optimizeFor": "quality"},
            "resolved_input": {"aspectRatio": "16:9"},
            "runway_task_id": "image-task-42",
            "generation_context_id": "generation-context-42",
            "output_identity": {
                "provider_task_id": "image-task-42",
                "output_url": "https://cdn.example.test/generated.png",
                "association_source": "runway_router_polled_task",
            },
            **extra_meta,
        },
    }


def _build_router_image_asset(*, project_id=None, execution_id=None):
    return ScriptParser().build_image_render_assets(
        [_scene()], project_id=project_id, execution_id=execution_id
    )["image_render_assets"][0]


def test_router_image_success_uses_router_output_and_registers_durable_asset(tmp_path, monkeypatch):
    project_id = "image-registration-project"
    execution_id = "image-registration-execution"
    storage, source = _image_authority_storage(storage_path=tmp_path / "image-registration")
    monkeypatch.setattr("app.services.reference_validation.project_store.get_project", source.get_project)
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_args, **_kwargs: storage)
    with (
        patch("app.services.script_parser.get_render_provider_config", return_value=_selected_router_config()),
        patch("app.services.script_parser.render_with_comfyui", side_effect=AssertionError("ComfyUI fallback forbidden")),
        patch(
            "app.services.providers.image_provider.authorize_runway_router_image_references",
            return_value={
                "project_id": project_id, "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001", "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1", "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "references": [
                    {"ref_id": "char-approved", "uri": "https://cdn.example.test/character.png"},
                    {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
                ],
            },
        ),
        patch(
            "app.services.providers.runway_router_provider.submit_runway_router_image_render",
            return_value=_successful_router_image_result(),
        ),
    ):
        result = _build_router_image_asset(project_id=project_id, execution_id=execution_id)

    assert result["provider"] == "runway_router"
    assert result["status"] == "success"
    assert result["url"] == "https://cdn.example.test/generated.png"
    router_execution = result["meta"]["router_execution"]
    assert router_execution["runway_task_id"] == "image-task-42"
    assert router_execution["routing_mode"] == "model_router"
    assert router_execution["reason"] == "runway_router_image_generated"
    assert router_execution["execution_id"] == execution_id
    assert router_execution["project_id"] == project_id
    assert router_execution["output_identity"] == {
        "provider_task_id": "image-task-42",
        "output_url": "https://cdn.example.test/generated.png",
        "association_source": "runway_router_polled_task",
    }
    durable = result["meta"]["durable_asset"]
    assert durable["project_id"] == project_id
    assert durable["execution_id"] == execution_id
    assert durable["provider_task_id"] == "image-task-42"
    assert durable["status"] == "available"

    stored = storage.get_video_asset(durable["asset_id"])
    assert stored is not None
    assert stored.project_id == project_id
    assert stored.source_type == "generated_output"
    assert stored.status == "available"
    assert stored.source_url == "https://cdn.example.test/generated.png"
    assert stored.metadata["media_type"] == "image"
    assert stored.metadata["provider"] == "runway_router"
    assert stored.metadata["execution_id"] == execution_id
    assert stored.metadata["provider_task_id"] == "image-task-42"
    assert stored.metadata["output_identity"] == router_execution["output_identity"]
    assert stored.metadata["scene_id"] == "scene_router_test"
    assert stored.metadata["shot_id"] == "scene_router_test_shot_001"
    assert stored.metadata["image_render_id"] == "image_scene_router_test_scene_router_test_shot_001"
    assert stored.metadata["generation_context_id"] == "generation-context-42"
    assert [row["ref_id"] for row in stored.metadata["reference_assets"]] == [
        "char-approved",
        "setting-approved",
    ]
    storage.close()


@pytest.mark.parametrize("missing_identity", ["project_id", "execution_id"])
def test_router_image_success_without_project_or_execution_provenance_fails_closed(
    missing_identity, tmp_path, monkeypatch
):
    project_id = "image-registration-project"
    execution_id = "image-registration-execution"
    storage, source = _image_authority_storage(storage_path=tmp_path / f"missing-{missing_identity}")
    monkeypatch.setattr("app.services.reference_validation.project_store.get_project", source.get_project)
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_args, **_kwargs: storage)
    with (
        patch("app.services.script_parser.get_render_provider_config", return_value=_selected_router_config()),
        patch(
            "app.services.providers.image_provider.authorize_runway_router_image_references",
            return_value={
                "project_id": project_id, "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001", "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1", "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "references": [
                    {"ref_id": "char-approved", "uri": "https://cdn.example.test/character.png"},
                    {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
                ],
            },
        ),
        patch(
            "app.services.providers.runway_router_provider.submit_runway_router_image_render",
            return_value=_successful_router_image_result(),
        ),
        patch.object(VideoAssetService, "register_generated_image_for_execution") as register,
    ):
        result = _build_router_image_asset(
            project_id=None if missing_identity == "project_id" else project_id,
            execution_id=None if missing_identity == "execution_id" else execution_id,
        )

    assert result["status"] == "failed"
    assert result["url"] is None
    if missing_identity == "project_id":
        assert result["meta"]["router_execution"]["reason"] == "image_reference_authorization_failed"
    else:
        assert result["meta"]["router_execution"]["reason"] == "durable_asset_registration_failed"
        assert result["meta"]["router_execution"]["registration_error"]["error_type"] == "persistence_error"
    register.assert_not_called()
    storage.close()


def test_router_image_registration_failure_is_reported_as_failed_output(tmp_path, monkeypatch):
    project_id = "image-registration-project"
    execution_id = "image-registration-execution"
    storage, source = _image_authority_storage(storage_path=tmp_path / "registration-failure")
    monkeypatch.setattr("app.services.reference_validation.project_store.get_project", source.get_project)
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_args, **_kwargs: storage)
    with (
        patch("app.services.script_parser.get_render_provider_config", return_value=_selected_router_config()),
        patch(
            "app.services.providers.runway_router_provider.submit_runway_router_image_render",
            return_value=_successful_router_image_result(),
        ),
        patch(
            "app.services.providers.image_provider.authorize_runway_router_image_references",
            return_value={
                "project_id": project_id, "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001", "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1", "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "references": [
                    {"ref_id": "char-approved", "uri": "https://cdn.example.test/character.png"},
                    {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
                ],
            },
        ),
        patch.object(
            VideoAssetService,
            "register_generated_image_for_execution",
            side_effect=PersistenceError("storage write failed", stage="image_asset_registration"),
        ) as register,
    ):
        result = _build_router_image_asset(project_id=project_id, execution_id=execution_id)

    assert result["status"] == "failed"
    assert result["url"] is None
    assert result["file_path"] is None
    assert result["error"] == "storage write failed"
    assert result["meta"]["router_execution"]["reason"] == "durable_asset_registration_failed"
    assert result["meta"]["router_execution"]["registration_error"]["error_type"] == "persistence_error"
    register.assert_called_once()
    storage.close()


@pytest.mark.parametrize(
    ("reported_key", "reported_value"),
    [("project_id", "foreign-project"), ("execution_id", "foreign-execution")],
)
def test_router_image_registration_rejects_mismatched_reported_context(
    reported_key, reported_value, tmp_path, monkeypatch
):
    project_id = "image-registration-project"
    execution_id = "image-registration-execution"
    storage, source = _image_authority_storage(storage_path=tmp_path / f"mismatch-{reported_key}")
    monkeypatch.setattr("app.services.reference_validation.project_store.get_project", source.get_project)
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_args, **_kwargs: storage)
    with (
        patch("app.services.script_parser.get_render_provider_config", return_value=_selected_router_config()),
        patch(
            "app.services.providers.image_provider.authorize_runway_router_image_references",
            return_value={
                "project_id": project_id, "scene_id": "scene_router_test",
                "shot_id": "scene_router_test_shot_001", "storyboard_version_id": "image-board-v1",
                "storyboard_shot_id": "board-shot-image-1", "binding_sha256": "test-binding",
                "generation_context_id": "test-context",
                "references": [
                    {"ref_id": "char-approved", "uri": "https://cdn.example.test/character.png"},
                    {"ref_id": "setting-approved", "uri": "https://cdn.example.test/setting.png"},
                ],
            },
        ),
        patch(
            "app.services.providers.runway_router_provider.submit_runway_router_image_render",
            return_value=_successful_router_image_result(**{reported_key: reported_value}),
        ),
        patch.object(VideoAssetService, "register_generated_image_for_execution") as register,
    ):
        result = _build_router_image_asset(project_id=project_id, execution_id=execution_id)

    assert result["status"] == "failed"
    assert result["url"] is None
    assert result["meta"]["router_execution"]["reason"] == "durable_asset_registration_failed"
    assert result["meta"]["router_execution"]["registration_error"]["error_type"] == "persistence_error"
    register.assert_not_called()
    storage.close()


def test_scene002_image_authorization_preserves_explicit_setting_identity_without_frame_substitution(tmp_path, monkeypatch):
    from app.services import reference_validation
    from app.services.reference_asset_service import SCENE002_PROJECT_ID, SCENE002_SETTING_ID
    from app.services.reference_validation import authorize_runway_router_image_references

    reference_id = "scene002-approved-setting-ref"
    uri = "https://assets.example.test/scene002-setting-authority.png"
    storage, source = _image_authority_storage(
        storage_path=tmp_path / "scene002-image-authority",
        project_id=SCENE002_PROJECT_ID,
        scene_id="scene_002",
        shot_id="scene_002_shot_001",
        include_character=False,
        setting_id=SCENE002_SETTING_ID,
        shot_references=[uri],
        shot_reference_ids=[reference_id],
    )
    reference_row = {
        "ref_id": reference_id,
        "project_id": SCENE002_PROJECT_ID,
        "kind": "environment",
        "image_url": uri,
        "target_type": "setting",
        "target_id": SCENE002_SETTING_ID,
        "category": "environment",
        "approval_state": "approved",
        "canonical": True,
        "source_kind": "confirmed",
    }
    storage.save_reference_asset(reference_row)
    monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
    payload = {
        "project_id": SCENE002_PROJECT_ID,
        "scene_id": "scene_002",
        "shot_id": "scene_002_shot_001",
        "storyboard_shot_id": "board-shot-image-1",
        "generation_context_id": "generation-context-42",
        "references": [{"ref_id": reference_id, "uri": uri}],
        "reference_binding": [{
            "ref_id": reference_id,
            "project_id": SCENE002_PROJECT_ID,
            "uri": uri,
            "target_type": "setting",
            "target_id": SCENE002_SETTING_ID,
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "environment",
        }],
        "storyboard_frame_url": "https://cdn.example.test/scene002-composition-only.png",
    }

    try:
        authorization = authorize_runway_router_image_references(payload=payload, storage=storage)
        assert [(row["ref_id"], row["uri"], row["target_type"], row["target_id"]) for row in authorization["references"]] == [
            (reference_id, uri, "setting", SCENE002_SETTING_ID),
        ]
        assert payload["storyboard_frame_url"] != authorization["references"][0]["uri"]
    finally:
        storage.close()


def test_scene002_image_authorization_rejects_composition_frame_as_identity_substitution(tmp_path, monkeypatch):
    from app.services import reference_validation
    from app.services.reference_asset_service import SCENE002_PROJECT_ID, SCENE002_SETTING_ID
    from app.services.reference_validation import authorize_runway_router_image_references

    canonical_uri = "https://assets.example.test/scene002-setting-authority.png"
    composition_uri = "https://cdn.example.test/scene002-composition-only.png"
    storage, source = _image_authority_storage(
        storage_path=tmp_path / "scene002-frame-substitution",
        project_id=SCENE002_PROJECT_ID,
        scene_id="scene_002",
        shot_id="scene_002_shot_001",
        include_character=False,
        setting_id=SCENE002_SETTING_ID,
        shot_references=[composition_uri],
        shot_reference_ids=["scene002-approved-setting-ref"],
    )
    storage.save_reference_asset({
        "ref_id": "scene002-approved-setting-ref",
        "project_id": SCENE002_PROJECT_ID,
        "kind": "environment",
        "image_url": canonical_uri,
        "target_type": "setting",
        "target_id": SCENE002_SETTING_ID,
        "category": "environment",
        "approval_state": "approved",
        "canonical": True,
        "source_kind": "confirmed",
    })
    monkeypatch.setattr(reference_validation.project_store, "get_project", source.get_project)
    payload = {
        "project_id": SCENE002_PROJECT_ID,
        "scene_id": "scene_002",
        "shot_id": "scene_002_shot_001",
        "storyboard_shot_id": "board-shot-image-1",
        "generation_context_id": "generation-context-42",
        "references": [{"ref_id": "scene002-approved-setting-ref", "uri": composition_uri}],
        "reference_binding": [{
            "ref_id": "scene002-approved-setting-ref",
            "project_id": SCENE002_PROJECT_ID,
            "uri": composition_uri,
            "target_type": "setting",
            "target_id": SCENE002_SETTING_ID,
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "environment",
        }],
    }

    try:
        with pytest.raises(ValidationError) as exc:
            authorize_runway_router_image_references(payload=payload, storage=storage)
        assert exc.value.metadata["failure_type"] == "shot_reference_binding_mismatch"
    finally:
        storage.close()


def test_video_asset_registration_rejects_mismatched_provider_output_identity(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "mismatched-output-identity"))
    project_id = "image-registration-project"
    storage.save_project(StudioProject(project_id=project_id, title="Image registration"))
    service = VideoAssetService(storage)

    with pytest.raises(ValidationError, match="provenance does not match"):
        service.register_generated_image_for_execution(
            project_id=project_id,
            image_render_id="image-render-42",
            scene_id="scene_router_test",
            shot_id="scene_router_test_shot_001",
            execution_id="image-registration-execution",
            provider_task_id="image-task-42",
            source_url="https://cdn.example.test/generated.png",
            output_identity={
                "provider_task_id": "image-task-42",
                "output_url": "https://cdn.example.test/foreign.png",
                "association_source": "runway_router_polled_task",
            },
        )

    assert storage.list_video_assets_for_project(project_id) == []
    storage.close()


def test_video_asset_registration_rejects_task_already_bound_to_another_project_or_execution(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "task-binding"))
    project_id = "image-registration-project"
    other_project_id = "other-image-registration-project"
    storage.save_project(StudioProject(project_id=project_id, title="Image registration"))
    storage.save_project(StudioProject(project_id=other_project_id, title="Other image registration"))
    service = VideoAssetService(storage)
    identity = {
        "provider_task_id": "image-task-42",
        "output_url": "https://cdn.example.test/generated.png",
        "association_source": "runway_router_polled_task",
    }
    service.register_generated_image_for_execution(
        project_id=project_id,
        image_render_id="image-render-42",
        scene_id="scene_router_test",
        shot_id="scene_router_test_shot_001",
        execution_id="original-execution",
        provider_task_id="image-task-42",
        source_url="https://cdn.example.test/generated.png",
        output_identity=identity,
    )

    with pytest.raises(ValidationError, match="already registered to different"):
        service.register_generated_image_for_execution(
            project_id=other_project_id,
            image_render_id="image-render-42",
            scene_id="scene_router_test",
            shot_id="scene_router_test_shot_001",
            execution_id="foreign-execution",
            provider_task_id="image-task-42",
            source_url="https://cdn.example.test/generated.png",
            output_identity=identity,
        )

    assets = storage.list_video_assets(source_type="generated_output")
    assert len(assets) == 1
    assert assets[0].project_id == project_id
    assert assets[0].metadata["execution_id"] == "original-execution"
    storage.close()


def test_video_asset_registration_rejects_changed_reference_or_context_provenance(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "changed-provenance"))
    project_id = "image-registration-project"
    storage.save_project(StudioProject(project_id=project_id, title="Image registration"))
    service = VideoAssetService(storage)
    identity = {
        "provider_task_id": "image-task-42",
        "output_url": "https://cdn.example.test/generated.png",
        "association_source": "runway_router_polled_task",
    }
    service.register_generated_image_for_execution(
        project_id=project_id,
        image_render_id="image-render-42",
        scene_id="scene_router_test",
        shot_id="scene_router_test_shot_001",
        execution_id="original-execution",
        provider_task_id="image-task-42",
        source_url="https://cdn.example.test/generated.png",
        output_identity=identity,
        reference_assets=["https://cdn.example.test/character.png"],
        generation_context_id="original-context",
    )

    with pytest.raises(ValidationError, match="different reference or generation-context provenance"):
        service.register_generated_image_for_execution(
            project_id=project_id,
            image_render_id="image-render-42",
            scene_id="scene_router_test",
            shot_id="scene_router_test_shot_001",
            execution_id="original-execution",
            provider_task_id="image-task-42",
            source_url="https://cdn.example.test/generated.png",
            output_identity=identity,
            reference_assets=["https://cdn.example.test/foreign-reference.png"],
            generation_context_id="foreign-context",
        )

    assets = storage.list_video_assets(source_type="generated_output")
    assert len(assets) == 1
    assert assets[0].metadata["reference_assets"] == ["https://cdn.example.test/character.png"]
    assert assets[0].metadata["generation_context_id"] == "original-context"
    storage.close()
