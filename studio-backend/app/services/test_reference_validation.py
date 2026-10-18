from __future__ import annotations

import asyncio

import pytest

from app.models import RenderJobInput, RenderJobModel
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services import render as render_module
from app.services.generation_contract import freeze_generation_contract
from app.services.reference_validation import (
    frozen_reference_payload,
    reference_binding_digest,
    reference_binding_for_requirements,
    resolve_scene_reference_requirements,
    validate_frozen_reference_binding_current,
    validate_generation_payload,
    verify_frozen_reference_payload,
)
from app.services.stability import ValidationError


class ReferenceStorage:
    def __init__(self, *, characters=None, assets=None):
        self.characters = characters or {}
        self.assets = assets or []
        self.universe_nodes = []

    def get_universe_nodes(self, project_id):
        return [row for row in self.universe_nodes if row.get("project_id") == project_id]

    def get_character(self, character_id, project_id):
        row = self.characters.get(character_id)
        return row if row and row.get("project_id") == project_id else None

    def list_reference_assets(self, **kwargs):
        rows = [row for row in self.assets if row.get("project_id") == kwargs.get("project_id")]
        if kwargs.get("target_type"):
            rows = [row for row in rows if row.get("target_type") == kwargs["target_type"]]
        if kwargs.get("target_id"):
            rows = [row for row in rows if row.get("target_id") == kwargs["target_id"]]
        return rows


def _project(scene):
    return {"project_id": "film-a", "execution_summary": {"scenes": [scene]}}


def _asset(ref_id, target_type, target_id, kind, *, canonical=True, approval_state="approved"):
    return {
        "ref_id": ref_id,
        "project_id": "film-a",
        "target_type": target_type,
        "target_id": target_id,
        "kind": kind,
        "image_url": f"https://cdn.example/{ref_id}.png",
        "canonical": canonical,
        "approval_state": approval_state,
    }


def _job(refs, *, scene_id="scene_002"):
    payload = ConsistencyPayload(project_id="film-a", refs=refs, mode="identity_lock")
    return RenderJobModel(
        id="job-1",
        project_id="film-a",
        shot_id=f"{scene_id}_shot_1",
        provider="simulated",
        input_payload=RenderJobInput(consistency_payload=payload),
    )


def _scene(*, character_id="char-1", setting_id="set-2", scene_id="scene_002", character_ids=None):
    return {"scene_id": scene_id, "character_ids": character_ids or [character_id], "setting_id": setting_id}


def _character(character_id="char-1", *, name=None):
    return {"id": character_id, "name": name or character_id, "project_id": "film-a"}


def _setting_node(setting_id="set-2", project_id="film-a", *, first_scene="scene_002", last_scene="scene_002"):
    return {
        "node_id": setting_id, "project_id": project_id, "node_type": "location",
        "name": "Fixture location", "first_scene": first_scene, "last_scene": last_scene,
    }


def _frozen_binding():
    return [
        {
            "ref_id": "char-ref", "uri": "https://cdn.example/char-ref.png",
            "target_type": "character", "target_id": "char-1", "role": "face",
            "category": "face", "canonical": True, "approval_state": "approved",
            "source_kind": "uploaded", "kind": "character_face",
        },
        {
            "ref_id": "setting-ref", "uri": "https://cdn.example/setting-ref.png",
            "target_type": "setting", "target_id": "set-2", "role": "wide",
            "category": "wide", "canonical": True, "approval_state": "approved",
            "source_kind": "confirmed", "kind": "environment",
        },
    ]


def _frozen_job(binding):
    job = _job([])
    job.input_payload.consistency_payload = frozen_reference_payload(binding, project_id="film-a")
    job.input_payload.referenceAssets = [row["uri"] for row in binding]
    contract = freeze_generation_contract(
        shot_id=job.shot_id,
        prompt="Approved test reference binding.",
        reference_assets=[
            {**row, "studio_role": row["role"], "source": "canonical_reference_binding"}
            for row in binding
        ],
        parameters={"reference_roles": [row["role"] for row in binding]},
    )
    job.metadata = {
        "frozen_reference_binding": binding,
        "frozen_reference_binding_sha256": reference_binding_digest(binding),
        "creative_generation_contract": contract.to_record(),
    }
    return job


def test_shot_reference_resolution_narrows_approved_scene_cast_without_uri_substitution():
    scene = _scene(character_ids=["char-1", "char-2"])
    storage = ReferenceStorage(
        characters={
            "char-1": _character("char-1", name="Character A"),
            "char-2": _character("char-2", name="Character B"),
        },
        assets=[
            _asset("char-a", "character", "char-1", "character_face"),
            _asset("char-b", "character", "char-2", "character_face"),
            _asset("setting-ref", "setting", "set-2", "environment"),
        ],
    )
    storage.universe_nodes = [_setting_node()]
    requirements = resolve_scene_reference_requirements(
        project_id="film-a", scene_id="scene_002", storage=storage,
        scene=scene, character_focus=["Character A"],
    )
    assert requirements["scene_character_ids"] == ["char-1", "char-2"]
    assert requirements["character_ids"] == ["char-1"]
    binding = reference_binding_for_requirements(
        requirements, required_character_ids=requirements["character_ids"],
    )
    assert [row["ref_id"] for row in binding] == ["char-a", "setting-ref"]
    assert [row["target_id"] for row in binding if row["target_type"] == "character"] == ["char-1"]
    with pytest.raises(ValueError, match="required character IDs"):
        reference_binding_for_requirements(requirements, required_character_ids=["char-2"])
    with pytest.raises(ValueError, match="required character IDs"):
        reference_binding_for_requirements(requirements, required_character_ids=["char-1", "char-2"])
    with pytest.raises(ValidationError) as exc:
        resolve_scene_reference_requirements(
            project_id="film-a", scene_id="scene_002", storage=storage,
            scene=scene, character_focus=["Unrelated character"],
        )
    assert exc.value.metadata["failure_type"] == "shot_character_focus_unresolved"


def test_duplicate_character_uris_keep_distinct_reference_ids():
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[
            {**_asset("char-a", "character", "char-1", "character_face"), "image_url": "https://cdn.example/shared.png"},
            {**_asset("char-b", "character", "char-1", "character_full"), "image_url": "https://cdn.example/shared.png"},
            _asset("setting-ref", "setting", "set-2", "environment"),
        ],
    )
    storage.universe_nodes = [_setting_node()]
    requirements = resolve_scene_reference_requirements(
        project_id="film-a", scene_id="scene_002", storage=storage, scene=_scene(),
    )
    binding = reference_binding_for_requirements(requirements)
    assert [row["ref_id"] for row in binding] == ["char-a", "char-b", "setting-ref"]
    assert [row["uri"] for row in binding[:2]] == ["https://cdn.example/shared.png"] * 2


def test_coverage_projection_preserves_empty_category_separately_from_kind():
    from app.services.reference_validation import reference_binding_coverage_projection

    projected = reference_binding_coverage_projection([{
        "ref_id": "setting-ref",
        "uri": "https://cdn.example/setting.png",
        "target_type": "setting",
        "target_id": "set-2",
        "role": "reference",
        "category": "",
        "kind": "environment",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    }])

    assert projected[0]["category"] == ""
    assert projected[0]["kind"] == "environment"


def test_coverage_projection_preserves_missing_optional_reference_metadata():
    from app.services.reference_validation import reference_binding_coverage_projection

    projected = reference_binding_coverage_projection([{
        "ref_id": "setting-ref",
        "uri": "https://cdn.example/setting.png",
        "target_type": "setting",
        "target_id": "set-2",
        "role": "environment",
    }])

    assert projected[0]["category"] == ""
    assert projected[0]["approval_state"] is None
    assert projected[0]["source_kind"] is None
    assert projected[0]["kind"] is None


def test_coverage_verifier_normalizes_absent_optional_fields_without_uri_substitution():
    from app.services.reference_validation import verify_shot_reference_coverage_binding

    coverage_row = {
        "ref_id": "setting-ref",
        "uri": "https://cdn.example/setting.png",
        "target_type": "setting",
        "target_id": "set-2",
        "role": "environment",
        "category": None,
        "canonical": True,
        "approval_state": None,
        "source_kind": None,
        "kind": None,
    }
    frozen_row = {
        **coverage_row,
        "category": "",
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "",
    }

    verify_shot_reference_coverage_binding(
        actual_binding=[frozen_row],
        coverage_shot={
            "approved_reference_bindings": [coverage_row],
            "approved_reference_ids": ["setting-ref"],
        },
    )

    with pytest.raises(ValueError, match="approved coverage IDs"):
        verify_shot_reference_coverage_binding(
            actual_binding=[{**frozen_row, "ref_id": "replacement-ref"}],
            coverage_shot={
                "approved_reference_bindings": [coverage_row],
                "approved_reference_ids": ["setting-ref"],
            },
        )

    with pytest.raises(ValueError, match="approved coverage IDs"):
        verify_shot_reference_coverage_binding(
            actual_binding=[{**frozen_row, "uri": "https://cdn.example/substitute.png"}],
            coverage_shot={
                "approved_reference_bindings": [coverage_row],
                "approved_reference_ids": ["setting-ref"],
            },
        )


def test_coverage_verifier_is_reference_id_sensitive_even_when_uri_is_identical():
    from app.services.reference_validation import verify_shot_reference_coverage_binding

    first = {**_frozen_binding()[0], "ref_id": "ref-one"}
    second = {**first, "ref_id": "ref-two"}
    setting = _frozen_binding()[1]
    coverage_binding = [first, setting]
    coverage = {
        "approved_reference_bindings": coverage_binding,
        "approved_reference_ids": ["ref-one", setting["ref_id"]],
    }
    with pytest.raises(ValueError, match="approved coverage IDs"):
        verify_shot_reference_coverage_binding(
            actual_binding=[second, setting],
            coverage_shot=coverage,
        )


def test_coverage_verifier_normalizes_absent_optional_fields_without_uri_substitution():
    from app.services.reference_validation import verify_shot_reference_coverage_binding

    coverage_row = {
        "ref_id": "setting-ref",
        "uri": "https://cdn.example/setting.png",
        "target_type": "setting",
        "target_id": "set-2",
        "role": "environment",
        "category": None,
        "canonical": True,
        "approval_state": None,
        "source_kind": None,
        "kind": None,
    }
    frozen_row = {
        **coverage_row,
        "category": "",
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "",
    }

    verify_shot_reference_coverage_binding(
        actual_binding=[frozen_row],
        coverage_shot={
            "approved_reference_bindings": [coverage_row],
            "approved_reference_ids": ["setting-ref"],
        },
    )


def test_coverage_verifier_is_reference_id_sensitive_even_when_uri_is_identical():
    from app.services.reference_validation import verify_shot_reference_coverage_binding

    first = {**_frozen_binding()[0], "ref_id": "ref-one"}
    second = {**first, "ref_id": "ref-two"}
    setting = _frozen_binding()[1]
    coverage_binding = [first, setting]
    coverage = {
        "approved_reference_bindings": coverage_binding,
        "approved_reference_ids": ["ref-one", setting["ref_id"]],
    }
    with pytest.raises(ValueError, match="approved coverage IDs"):
        verify_shot_reference_coverage_binding(
            actual_binding=[second, setting],
            coverage_shot=coverage,
        )


def test_frozen_coverage_rejects_character_outside_focus_before_payload_validation(monkeypatch):
    binding = [
        {**_frozen_binding()[0], "target_id": "char-1"},
        {**_frozen_binding()[0], "ref_id": "foreign-character", "uri": "https://cdn.example/foreign.png", "target_id": "char-2"},
        _frozen_binding()[1],
    ]
    job = _frozen_job(binding)
    job.shot_id = "scene_002_shot_1"
    coverage = {
        "shot_id": job.shot_id,
        "required_character_ids": ["char-1"],
        "required_setting_id": "set-2",
        "approved_reference_bindings": [
            {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind")}
            for row in [binding[0], binding[2]]
        ],
        "approved_reference_ids": [binding[0]["ref_id"], binding[2]["ref_id"]],
        "covered_content_ids": [], "covered_dialogue_ids": [],
    }
    payload = job.metadata["creative_generation_contract"]["payload"]
    payload["scene_coverage"] = {"scene_id": "scene_002", "shots": [coverage]}
    payload["scene_coverage_shot"] = coverage
    from app.services.generation_contract import _canonical_json
    import hashlib
    record = job.metadata["creative_generation_contract"]
    record["sha256"] = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    job.metadata["creative_generation_contract"] = record
    with pytest.raises(ValidationError) as exc:
        validate_generation_payload(job=job, storage=ReferenceStorage())
    assert exc.value.metadata["failure_type"] == "frozen_reference_contract_mismatch"


def test_missing_focused_reference_does_not_select_other_scene_character():
    scene = _scene(character_ids=["char-1", "char-2"])
    storage = ReferenceStorage(
        characters={"char-1": _character("char-1", name="Character A"), "char-2": _character("char-2", name="Character B")},
        assets=[
            _asset("char-b", "character", "char-2", "character_face"),
            _asset("setting-ref", "setting", "set-2", "environment"),
        ],
    )
    storage.universe_nodes = [_setting_node()]
    with pytest.raises(ValidationError) as exc:
        resolve_scene_reference_requirements(
            project_id="film-a", scene_id="scene_002", storage=storage,
            scene=scene, character_focus=["Character A"],
        )
    assert exc.value.metadata["failure_type"] == "canonical_character_reference_missing"


def test_missing_canonical_character_blocks_before_provider(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    with pytest.raises(ValidationError) as exc:
        validate_generation_payload(job=_job([]), storage=ReferenceStorage(characters={"char-1": _character()}))
    assert exc.value.metadata["failure_type"] == "canonical_character_reference_missing"
    assert "character char-1" in str(exc.value)


@pytest.mark.parametrize("approval_state", ["candidate", "rejected"])
def test_unapproved_character_only_never_satisfies_canonical_requirement(monkeypatch, approval_state):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene(setting_id="")))
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[_asset("char-ref", "character", "char-1", "character_face", approval_state=approval_state)],
    )
    with pytest.raises(ValidationError) as exc:
        validate_generation_payload(job=_job([]), storage=storage)
    assert exc.value.metadata["failure_type"] == "canonical_character_reference_missing"


def test_missing_canonical_setting_blocks_and_identifies_setting(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[_asset("char-ref", "character", "char-1", "character_face")],
    )
    refs = [ReferenceAsset(**_asset("char-ref", "character", "char-1", "character_face"))]
    with pytest.raises(ValidationError) as exc:
        validate_generation_payload(job=_job(refs), storage=storage)
    assert exc.value.metadata["failure_type"] == "setting_identity_unproven"
    assert exc.value.metadata["target_id"] == "set-2"


def test_project_scoped_setting_node_resolves_and_rejects_unknown_or_cross_project():
    from app.services.reference_validation import resolve_scene_reference_requirements
    from app.services import reference_validation as validation
    from unittest.mock import patch

    scene = _scene()
    project = _project(scene)
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[
            _asset("char-ref", "character", "char-1", "character_face"),
            _asset("set-ref", "setting", "set-2", "environment"),
        ],
    )
    storage.universe_nodes = [_setting_node()]
    with patch.object(validation.project_store, "get_project", return_value=project):
        requirements = resolve_scene_reference_requirements(
            project_id="film-a", scene_id="scene_002", storage=storage, scene=scene,
        )
    assert requirements["setting_id"] == "set-2"

    with patch.object(validation.project_store, "get_project", return_value=project):
        for nodes in (
            [],
            [_setting_node(project_id="film-b")],
        ):
            storage.universe_nodes = nodes
            with pytest.raises(ValidationError) as exc:
                resolve_scene_reference_requirements(
                    project_id="film-a", scene_id="scene_002", storage=storage, scene=scene,
                )
            assert exc.value.metadata["failure_type"] == "setting_identity_unproven"


def test_unapproved_setting_reference_does_not_resolve_location_node():
    from app.services.reference_validation import resolve_scene_reference_requirements
    from app.services import reference_validation as validation
    from unittest.mock import patch

    scene = _scene()
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[_asset("char-ref", "character", "char-1", "character_face"),
                _asset("set-ref", "setting", "set-2", "environment", approval_state="candidate")],
    )
    storage.universe_nodes = [_setting_node()]
    with patch.object(validation.project_store, "get_project", return_value=_project(scene)):
        with pytest.raises(ValidationError) as exc:
            resolve_scene_reference_requirements(
                project_id="film-a", scene_id="scene_002", storage=storage, scene=scene,
            )
    assert exc.value.metadata["failure_type"] == "canonical_setting_reference_missing"


def test_unknown_scene_and_character_are_blocking(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    storage = ReferenceStorage(characters={})
    with pytest.raises(ValidationError) as scene_error:
        validate_generation_payload(job=_job([], scene_id="scene_404"), storage=storage)
    assert scene_error.value.metadata["failure_type"] == "unknown_scene"
    with pytest.raises(ValidationError) as character_error:
        validate_generation_payload(job=_job([]), storage=storage)
    assert character_error.value.metadata["failure_type"] == "unknown_character"


def test_wrong_character_and_setting_ownership_blocks(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[_asset("char-ref", "character", "char-1", "character_face"), _asset("set-ref", "setting", "set-2", "environment")],
    )
    storage.universe_nodes = [_setting_node()]
    wrong_character = [
        ReferenceAsset(**_asset("other-ref", "character", "char-other", "character_face")),
        ReferenceAsset(**_asset("set-ref", "setting", "set-2", "environment")),
    ]
    with pytest.raises(ValidationError) as char_error:
        validate_generation_payload(job=_job(wrong_character), storage=storage)
    assert char_error.value.metadata["failure_type"] == "reference_ownership_mismatch"
    wrong_setting = [
        ReferenceAsset(**_asset("char-ref", "character", "char-1", "character_face")),
        ReferenceAsset(**_asset("other-set", "setting", "set-other", "environment")),
    ]
    with pytest.raises(ValidationError) as setting_error:
        validate_generation_payload(job=_job(wrong_setting), storage=storage)
    assert setting_error.value.metadata["failure_type"] == "reference_ownership_mismatch"


def test_valid_canonical_payload_passes_and_optional_supporting_gap_is_not_substituted(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    storage = ReferenceStorage(
        characters={"char-1": _character()},
        assets=[_asset("char-ref", "character", "char-1", "character_face"), _asset("set-ref", "setting", "set-2", "environment")],
    )
    storage.universe_nodes = [_setting_node()]
    refs = [
        ReferenceAsset(**_asset("char-ref", "character", "char-1", "character_face")),
        ReferenceAsset(**_asset("set-ref", "setting", "set-2", "environment")),
    ]
    result = validate_generation_payload(job=_job(refs), storage=storage)
    assert result["scene_id"] == "scene_002"
    assert result["allowed_urls"] == ["https://cdn.example/char-ref.png", "https://cdn.example/set-ref.png"]


def test_invalid_payload_never_invokes_provider(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene(setting_id="")))
    monkeypatch.setattr(render_module, "_storage", ReferenceStorage(characters={"char-1": _character()}))
    calls = []

    class Provider:
        async def submit_job(self, job):
            calls.append(job.id)
            return job

    monkeypatch.setattr(render_module, "get_adapter", lambda *_args: Provider())
    service = render_module.RenderService()
    job = service.create_job(
        project_id="film-a", shot_id="scene_002_shot_1", provider="simulated",
        prompt="A valid cinematic shot.", parameters={"require_canonical_references": True},
    )
    with pytest.raises(ValidationError):
        asyncio.run(service.submit_job(job.id))
    assert calls == []
    assert service.get_job(job.id).status == "failed"


def test_bootstrap_without_reference_set_remains_allowed_for_existing_post_render_lock_flow(monkeypatch):
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene(setting_id="")))
    result = validate_generation_payload(
        job=RenderJobModel(id="job-bootstrap", project_id="film-a", shot_id="scene_002_shot_1", provider="simulated", input_payload=RenderJobInput()),
        storage=ReferenceStorage(characters={"char-1": _character()}),
        require_setting_reference=False,
        require_canonical_references=False,
    )
    assert result["scene_id"] == "scene_002"


def test_final_validation_uses_coverage_focus_and_compares_exact_ids_and_records(monkeypatch):
    binding = [
        {**_frozen_binding()[0], "ref_id": "character-a", "target_id": "char-1"},
        {**_frozen_binding()[1], "ref_id": "setting-ref"},
    ]
    job = _frozen_job(binding)
    job.shot_id = "scene_002_shot_1"
    coverage_binding = [
        {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind")}
        for row in binding
    ]
    shot_coverage = {
        "shot_id": job.shot_id,
        "required_character_ids": ["char-1"],
        "required_setting_id": "set-2",
        "approved_reference_bindings": coverage_binding,
        "approved_reference_ids": [row["ref_id"] for row in coverage_binding],
        "covered_dialogue_ids": [],
    }
    content_unit = {
        "content_id": "content-a", "text": "Character A waits beside the door.",
        "source_order": 1, "disposition": "ASSIGNED", "shot_ids": [job.shot_id],
    }
    shot_coverage.update({
        "scene_id": "scene_002", "source_scene_id": "scene_002", "shot_order": 1,
        "covered_content_ids": ["content-a"], "covered_dialogue_ids": [],
        "content_coverage_state": "ASSIGNED", "content_coverage_reason": "",
        "dialogue_disposition": "INTENTIONAL_SILENCE",
        "dialogue_disposition_reason": "This shot is intentionally silent.",
        "camera_plan": {"camera": "Locked off"}, "camera_provenance": "USER_SPECIFIED",
        "camera_source_digest": "camera-digest", "camera_source_project_id": "film-a",
        "camera_source_scene_id": "scene_002", "camera_source_shot_id": job.shot_id,
        "camera_source_storyboard_shot_id": "", "camera_target_project_id": "film-a",
        "camera_target_scene_id": "scene_002", "camera_target_shot_id": job.shot_id,
    })
    scene_coverage = {
        "scene_id": "scene_002", "project_id": "film-a", "shots": [shot_coverage],
        "content_units": [{**content_unit, "source_start": 0, "source_end": 40}],
        "dialogue": [], "canonical_script_sha256": "", "scene_content_sha256": "",
        "scene_source_identity": "", "scene_source_start": 0, "scene_source_end": 40,
        "script_version_id": "",
    }
    coverage_binding = [
        {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind")}
        for row in binding
    ]
    from app.services.generation_contract import _canonical_json
    import hashlib
    contract_record = job.metadata["creative_generation_contract"]
    payload = contract_record["payload"]
    payload["scene_coverage"] = scene_coverage
    payload["scene_coverage_shot"] = shot_coverage
    payload["dialogue_handoff"] = {
        "payload": {"version": 1, "scene_id": "scene_002", "shot_id": job.shot_id, "lines": [], "silence": True},
        "sha256": "unused-by-validator-test",
    }
    contract_record["sha256"] = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    job.metadata["creative_generation_contract"] = contract_record
    job.metadata["frozen_reference_binding"] = binding
    job.metadata["frozen_reference_binding_sha256"] = reference_binding_digest(binding)
    job.input_payload.referenceAssets = [row["uri"] for row in binding]
    job.input_payload.consistency_payload = frozen_reference_payload(binding, project_id="film-a")

    scene = _scene(character_ids=["char-1", "char-2"])
    storage = _current_reference_storage(binding)
    storage.characters["char-2"] = _character("char-2", name="Character B")
    storage.assets.append({**_asset("character-b", "character", "char-2", "character_face"), "image_url": "https://cdn.example/char-b.png"})
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _project_id: _project(scene))
    # New scene cast anchors do not widen a frozen shot whose approved focus is A.
    requirements = validate_frozen_reference_binding_current(job=job, storage=storage)
    assert requirements["character_ids"] == ["char-1"]
    assert requirements["scene_character_ids"] == ["char-1", "char-2"]
    assert [row["ref_id"] for row in reference_binding_for_requirements(requirements)] == ["character-a", "setting-ref"]


def test_frozen_binding_preserves_character_setting_order_and_roles_without_reselection(monkeypatch):
    binding = _frozen_binding()
    job = _frozen_job(binding)
    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    requirements = validate_generation_payload(job=job, storage=ReferenceStorage())
    verify_frozen_reference_payload(job=job, binding=binding)
    assert [ref.ref_id for ref in job.input_payload.consistency_payload.refs] == ["char-ref", "setting-ref"]
    assert [ref.reference_role for ref in job.input_payload.consistency_payload.refs] == ["face", "wide"]
    assert requirements["allowed_urls"] == [row["uri"] for row in binding]
    assert requirements["setting_id"] == "set-2"


def test_frozen_binding_rejects_role_or_uri_drift():
    binding = _frozen_binding()
    job = _frozen_job(binding)
    job.input_payload.consistency_payload.refs[0].reference_role = "wardrobe"
    with pytest.raises(ValidationError) as role_error:
        verify_frozen_reference_payload(job=job, binding=binding)
    assert role_error.value.metadata["failure_type"] == "frozen_reference_payload_mismatch"
    job = _frozen_job(binding)
    job.input_payload.referenceAssets.reverse()
    with pytest.raises(ValidationError) as uri_error:
        verify_frozen_reference_payload(job=job, binding=binding)
    assert uri_error.value.metadata["failure_type"] == "frozen_reference_payload_mismatch"


def test_frozen_binding_requires_persisted_integrity_digest():
    job = _frozen_job(_frozen_binding())
    job.metadata.pop("frozen_reference_binding_sha256")
    with pytest.raises(ValidationError) as exc:
        verify_frozen_reference_payload(job=job, binding=job.metadata["frozen_reference_binding"])
    assert exc.value.metadata["failure_type"] == "frozen_reference_binding_integrity_mismatch"


def _current_reference_storage(binding, *, project_id="film-a", scene_id="scene_002"):
    character_ids = list(dict.fromkeys(
        str(row["target_id"]) for row in binding if row.get("target_type") == "character"
    ))
    storage = ReferenceStorage(
        characters={character_id: _character(character_id) for character_id in character_ids},
        assets=[{
            "ref_id": row["ref_id"],
            "project_id": project_id,
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "kind": row["kind"],
            "category": row["category"],
            "image_url": row["uri"],
            "canonical": row["canonical"],
            "approval_state": row["approval_state"],
            "source_kind": row["source_kind"],
        } for row in binding]
    )
    storage.universe_nodes = [_setting_node(
        setting_id=next(row["target_id"] for row in binding if row.get("target_type") == "setting"),
        project_id=project_id,
        first_scene=scene_id,
        last_scene=scene_id,
    )]
    return storage


def test_unchanged_frozen_binding_passes_final_current_validation(monkeypatch):
    binding = _frozen_binding()
    job = _frozen_job(binding)
    storage = _current_reference_storage(binding)
    from app.services import reference_validation as validation

    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: _project_for_scene())
    requirements = validate_frozen_reference_binding_current(job=job, storage=storage)
    assert requirements["scene_id"] == "scene_002"
    assert requirements["setting_id"] == "set-2"


def test_final_current_validation_uses_only_frozen_shot_focus_not_new_scene_cast(monkeypatch):
    binding = [
        {**_frozen_binding()[0], "ref_id": "character-a", "target_id": "char-1"},
        {**_frozen_binding()[1], "ref_id": "setting-ref"},
    ]
    job = _frozen_job(binding)
    job.shot_id = "scene_002_shot_1"
    coverage_binding = [
        {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind")}
        for row in binding
    ]
    shot_coverage = {
        "shot_id": job.shot_id,
        "required_character_ids": ["char-1"],
        "required_setting_id": "set-2",
        "approved_reference_bindings": coverage_binding,
        "approved_reference_ids": [row["ref_id"] for row in coverage_binding],
        "covered_content_ids": [], "covered_dialogue_ids": [],
        "content_coverage_state": "ASSIGNED", "content_coverage_reason": "",
        "dialogue_disposition": "INTENTIONAL_SILENCE",
        "dialogue_disposition_reason": "Approved silent shot.",
        "camera_plan": {"camera": "Locked off"}, "camera_provenance": "USER_SPECIFIED",
        "camera_source_digest": "camera-digest", "camera_source_project_id": "film-a",
        "camera_source_scene_id": "scene_002", "camera_source_shot_id": job.shot_id,
        "camera_source_storyboard_shot_id": "", "camera_target_project_id": "film-a",
        "camera_target_scene_id": "scene_002", "camera_target_shot_id": job.shot_id,
        "scene_id": "scene_002", "source_scene_id": "scene_002", "shot_order": 1,
        "shot_kind": "coverage", "covered_content_ids": [], "covered_dialogue_ids": [],
    }
    from app.services.generation_contract import _canonical_json
    import hashlib
    record = job.metadata["creative_generation_contract"]
    payload = record["payload"]
    payload["scene_coverage_shot"] = shot_coverage
    payload["scene_coverage"] = {"scene_id": "scene_002", "shots": [shot_coverage]}
    record["sha256"] = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    job.metadata["creative_generation_contract"] = record
    from app.services import reference_validation as validation
    storage = _current_reference_storage(binding)
    scene = _scene(character_ids=["char-1", "char-2"])
    storage.characters["char-2"] = _character("char-2", name="Character B")
    storage.assets.append({**_asset("character-b", "character", "char-2", "character_face"), "image_url": "https://cdn.example/char-b.png"})
    monkeypatch.setattr(validation.project_store, "get_project", lambda project_id: _project(scene))

    requirements = validate_frozen_reference_binding_current(job=job, storage=storage)

    assert requirements["character_ids"] == ["char-1"]
    assert requirements["scene_character_ids"] == ["char-1", "char-2"]
    assert [row["ref_id"] for row in reference_binding_for_requirements(requirements)] == ["character-a", "setting-ref"]


def test_final_current_validation_rejects_reference_id_substitution_with_same_uri(monkeypatch):
    original = _frozen_binding()
    binding = [
        {**original[0], "ref_id": "character-original"},
        {**original[1], "ref_id": "setting-ref"},
    ]
    job = _frozen_job(binding)
    storage = _current_reference_storage(binding)
    storage.assets[0]["ref_id"] = "character-substitute"
    monkeypatch.setattr(
        "app.services.reference_validation.project_store.get_project",
        lambda _project: _project_for_scene(),
    )

    with pytest.raises(ValidationError) as exc:
        validate_frozen_reference_binding_current(job=job, storage=storage)

    assert exc.value.metadata["failure_type"] == "frozen_reference_binding_stale"


def _project_for_scene():
    return _project(_scene())


@pytest.mark.parametrize("change", ["revoked", "deleted", "uri_changed", "role_changed", "wrong_project"])
def test_changed_current_reference_rejected_at_final_validation(monkeypatch, change):
    binding = _frozen_binding()
    job = _frozen_job(binding)
    storage = _current_reference_storage(binding)
    if change == "revoked":
        storage.assets[0]["approval_state"] = "rejected"
    elif change == "deleted":
        storage.assets.pop(0)
    elif change == "uri_changed":
        storage.assets[0]["image_url"] = "https://cdn.example/replaced-character.png"
    elif change == "role_changed":
        storage.assets[0]["category"] = "wardrobe"
    else:
        storage.assets[0]["project_id"] = "film-b"
    from app.services import reference_validation as validation

    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: _project_for_scene())
    with pytest.raises(ValidationError):
        validate_frozen_reference_binding_current(job=job, storage=storage)


def test_current_reference_binding_rejects_project_and_role_mismatch(monkeypatch):
    binding = _frozen_binding()
    job = _frozen_job(binding)
    wrong_project_binding = [dict(row) for row in binding]
    wrong_project_binding[0]["project_id"] = "film-b"
    wrong_project_job = _frozen_job(wrong_project_binding)
    storage = _current_reference_storage(binding)
    from app.services import reference_validation as validation

    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: _project_for_scene())
    with pytest.raises(ValidationError) as project_error:
        validate_frozen_reference_binding_current(job=wrong_project_job, storage=storage)
    assert project_error.value.metadata["failure_type"] == "reference_project_mismatch"

    wrong_role_binding = [dict(row) for row in binding]
    wrong_role_binding[0]["role"] = "wardrobe"
    wrong_role_job = _frozen_job(wrong_role_binding)
    with pytest.raises(ValidationError):
        validate_frozen_reference_binding_current(job=wrong_role_job, storage=storage)


def test_scene002_setting_decision_remains_current_at_final_reference_validation(monkeypatch):
    from types import SimpleNamespace
    from app.services.reference_asset_service import SCENE002_PROJECT_ID, SCENE002_SETTING_ID
    from app.services import reference_validation as validation

    reference_id = "ref_set_final-boundary"
    binding = [{
        "ref_id": reference_id,
        "project_id": SCENE002_PROJECT_ID,
        "uri": "https://cdn.example/scene002-setting.png",
        "target_type": "setting",
        "target_id": SCENE002_SETTING_ID,
        "role": "environment",
        "category": "environment",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "environment",
    }]
    job = RenderJobModel(
        id="scene002-final-reference-job",
        project_id=SCENE002_PROJECT_ID,
        shot_id="scene_002_shot_001",
        provider="runway_router",
        input_payload=RenderJobInput(
            referenceAssets=[binding[0]["uri"]],
            consistency_payload=frozen_reference_payload(binding, project_id=SCENE002_PROJECT_ID),
        ),
    )
    contract = freeze_generation_contract(
        shot_id=job.shot_id,
        prompt="Approved Scene 002 setting selection.",
        reference_assets=[{**binding[0], "studio_role": "environment", "source": "canonical_reference_binding"}],
    )
    job.metadata = {
        "frozen_reference_binding": binding,
        "frozen_reference_binding_sha256": reference_binding_digest(binding),
        "creative_generation_contract": contract.to_record(),
    }
    row = {**binding[0], "image_url": binding[0]["uri"]}
    storage = ReferenceStorage(assets=[row])
    storage.universe_nodes = [_setting_node(
        setting_id=SCENE002_SETTING_ID,
        project_id=SCENE002_PROJECT_ID,
        first_scene="scene_002",
        last_scene="scene_002",
    )]
    storage.get_reference_asset = lambda ref_id: row if ref_id == reference_id else None
    storage.get_storyboard_blueprint = lambda project_id, scene_id: SimpleNamespace(
        project_id=project_id, scene_id=scene_id,
        current_version_id="board-v1", approved_version_id="board-v1", status="approved",
    )
    storyboard_shot = SimpleNamespace(
        storyboard_shot_id="board-shot-scene002",
        project_id=SCENE002_PROJECT_ID,
        scene_id="scene_002",
        shot_id=job.shot_id,
        version_id="board-v1",
        status="approved",
        visual_plan={"reference_asset_ids": [reference_id]},
        render_contract={"reference_assets": [binding[0]["uri"]]},
        intent={"character_focus": []},
    )
    storage.get_storyboard_shot = lambda storyboard_shot_id: (
        storyboard_shot if storyboard_shot_id == storyboard_shot.storyboard_shot_id else None
    )
    storage.get_storyboard_blueprint_version = lambda version_id: SimpleNamespace(
        version_id=version_id, project_id=SCENE002_PROJECT_ID, scene_id="scene_002",
        status="approved",
        metadata={"scene_direction": {"setting_reference_decision": {
            "canonical_setting_id": SCENE002_SETTING_ID, "reference_id": reference_id,
        }}},
    )
    monkeypatch.setattr(validation.project_store, "get_project", lambda _project: {
        "project_id": SCENE002_PROJECT_ID,
        "execution_summary": {"scenes": [{
            "scene_id": "scene_002", "setting_id": SCENE002_SETTING_ID, "character_ids": [],
        }]},
    })

    requirements = validate_frozen_reference_binding_current(job=job, storage=storage)

    assert requirements["setting_reference_decision"] == {
        "canonical_setting_id": SCENE002_SETTING_ID, "reference_id": reference_id,
    }
    assert requirements["setting_references"][0]["ref_id"] == reference_id


def test_frozen_payload_drift_never_invokes_provider(monkeypatch):
    binding = _frozen_binding()
    job = _frozen_job(binding)
    job.input_payload.consistency_payload.refs[1].target_id = "another-setting"
    calls = []

    class Provider:
        async def submit_job(self, job):
            calls.append(job.id)
            return job

    from app.services import reference_validation as validation
    monkeypatch.setattr(validation.project_store, "get_project", lambda _: _project(_scene()))
    monkeypatch.setattr(validation, "_approved_character_references", lambda *_args, **_kwargs: [dict(binding[0])])
    monkeypatch.setattr(validation, "_approved_setting_references", lambda *_args, **_kwargs: [dict(binding[1])])
    monkeypatch.setattr(render_module, "get_adapter", lambda *_args: Provider())
    service = render_module.RenderService()
    service._jobs[job.id] = job
    monkeypatch.setattr(render_module, "_storage", None)
    with pytest.raises(ValidationError):
        asyncio.run(service.submit_job(job.id))
    assert calls == []
