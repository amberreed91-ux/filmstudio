from __future__ import annotations

import copy
import hashlib

import pytest

from app.models import RenderJobInput, RenderJobModel
from app.services.scene002_contract_only import (
    MODE,
    RETRY_POLICY,
    Scene002ContractError,
    assert_no_protected_project_mutation,
    assert_protected_seed_unchanged,
    assert_ordinary_retry_matches,
    digest,
    project_revision_guard,
    reject_altered_retry,
    validate_result_only_metadata,
    verify_execution_contract,
)


def _authority(*, script: str = "INT. TEST - DAY\nAction.", scene: str = "INT. TEST - DAY\nAction.") -> dict:
    start = script.index(scene)
    scene_hash = hashlib.sha256(scene.encode()).hexdigest()
    script_hash = hashlib.sha256(script.encode()).hexdigest()
    return {
        "authority_id": "auth-1", "authority_decision_id": "decision-1",
        "authority_signature": "not-valid-without-configured-key", "approved_by": "fixture-creator",
        "approved_at": "fixture-time", "decision_status": "approved", "project_id": "project-1",
        "scene_id": "scene_002", "screenplay_representation_id": "screenplay-fixture-1",
        "screenplay_text": script, "screenplay_sha256": script_hash, "scene_content": scene,
        "scene_heading": "INT. TEST - DAY", "scene_sha256": scene_hash,
        "scene_span": {"convention": "python_unicode_codepoint_offsets_v1", "start": start,
                        "end": start + len(scene), "sha256": scene_hash},
        "storyboard_version_id": "storyboard-v1", "storyboard_relationship": {"relationship": "fixture"},
        "provider_policy": {"provider": "runway_router", "routing_policy_id": "route-policy-1",
                            "router_config_id": "router-config-1"},
        "model_policy": {"policy_id": "router-selected-model-policy"},
        "seed_policy": {"mode": "fixed", "seed": 17}, "retry_policy": RETRY_POLICY,
        "reference_content_sha256": {"ref-setting": "a" * 64},
        "authorized_creative_fingerprint": "b" * 64,
        "coverage_decision_ids": ["coverage-1"],
        "coverage_decisions": [{"decision_version_id": "coverage-1", "status": "approved"}],
        "execution_parameters_by_shot": {"scene_002_shot_001": {
            "aspect_ratio": "16:9", "duration": 5, "resolution": "720p", "seed": 17,
            "audio": False, "negative_prompt": "", "reference_videos": [], "reference_audio": [],
            "keyframes": [], "content_moderation": "standard", "creative_parameters": {},
        }},
        "ordered_shot_ids": ["scene_002_shot_001"],
        "reference_bindings": [{"ref_id": "ref-setting", "uri": "/tmp/reference.png",
            "target_type": "setting", "target_id": "setting-1", "role": "reference",
            "category": "environment", "canonical": True, "approval_state": "approved",
            "source_kind": "confirmed", "kind": "environment"}],
        "setting_identity": {"setting_id": "setting-1"},
        "approved_setting_anchor": {"anchor_id": "anchor-1", "setting_id": "setting-1", "reference_id": "ref-setting"},
    }


def _unsigned_execution_record() -> dict:
    authority = _authority()
    payload = {
        "mode": MODE, "contract_version": 1, "project_id": authority["project_id"],
        "scene_id": authority["scene_id"], "shot_id": "scene_002_shot_001",
        "source_authority": authority, "authority_decision_id": authority["authority_decision_id"],
        "creative_fingerprint": authority["authorized_creative_fingerprint"],
        "creative_identity_sha256": "c" * 64, "provider": "runway_router",
        "routing_policy_id": "route-policy-1", "router_config_id": "router-config-1",
        "model_policy": authority["model_policy"],
        "execution_parameters": authority["execution_parameters_by_shot"]["scene_002_shot_001"],
        "seed_policy": authority["seed_policy"], "retry_policy": RETRY_POLICY,
        "reference_content_sha256": authority["reference_content_sha256"],
        "reference_bindings": authority["reference_bindings"],
        "setting_identity": authority["setting_identity"],
        "approved_setting_anchor": authority["approved_setting_anchor"],
        "ordered_shot_ids": authority["ordered_shot_ids"], "creative_manifest": {},
        "generation_contract": {}, "provider_input_parameters": {},
        "storyboard_version_id": "storyboard-v1",
    }
    return {"payload": payload, "execution_fingerprint": digest(payload)}


def _protected_metadata() -> dict:
    return {
        "execution_mode": MODE,
        "scene002_execution_contract": {"payload": {}, "execution_fingerprint": ""},
        "source_authority_id": "auth-1", "creative_generation_contract": {},
        "creative_generation_manifest": {}, "creative_manifest_fingerprint": "f" * 64,
        "creative_contract_digest": "e" * 64,
        "creative_generation_identity": {"job_id": "job-1", "project_id": "project-1",
                                     "shot_id": "scene_002_shot_001", "provider": "runway_router"},
        "frozen_reference_binding": [], "frozen_reference_binding_sha256": "d" * 64,
        "creative_dialogue_handoff": {}, "pipeline_reliability": {"phase_timing": {}},
    }


def _authorized_components() -> tuple[dict, dict]:
    reference = {"ref_id": "ref-setting", "uri": "file:///immutable.png", "role": "reference",
                 "target_type": "setting", "target_id": "setting-1", "category": "environment",
                 "canonical": True, "approval_state": "approved", "source_kind": "confirmed", "kind": "environment",
                 "content_sha256": "1" * 64}
    dialogue = {"payload": {"scene_id": "scene_002", "shot_id": "scene_002_shot_001", "lines": [], "silence": True}, "sha256": "d" * 64}
    script = "FROZEN SCREENPLAY"
    authority = {
        "project_id": "project-1", "scene_id": "scene_002", "screenplay_representation_id": "script-v1",
        "screenplay_text": script, "screenplay_sha256": "a" * 64, "scene_content": "FROZEN SCENE",
        "scene_sha256": "b" * 64, "scene_span": {"start": 0, "end": 1},
        "storyboard_version_id": "board-v1", "authorized_creative_fingerprint": "c" * 64,
        "ordered_shot_ids": ["scene_002_shot_001"], "reference_bindings": [reference],
        "reference_content_sha256": {"ref-setting": "1" * 64}, "provider_policy": {
            "provider": "runway_router", "routing_policy_id": "route-v1", "router_config_id": "config-v1"},
        "model_policy": {"policy_id": "model-route-v1"}, "seed_policy": {"mode": "fixed", "seed": 17},
        "retry_policy": RETRY_POLICY,
        "execution_parameters_by_shot": {"scene_002_shot_001": {"seed": 17, "duration": 5}},
    }
    scene = {"project_id": "project-1", "scene_id": "scene_002", "canonical_script_sha256": "a" * 64,
             "scene_content_sha256": "b" * 64, "scene_source_start": 0, "scene_source_end": 1}
    shot = {"shot_id": "scene_002_shot_001", "shot_prompt": "frozen prompt", "dialogue_handoff": dialogue}
    payload = {
        "project_id": "project-1", "scene_id": "scene_002", "shot_id": shot["shot_id"],
        "creative_manifest": {"scene": scene, "storyboard": {"storyboard_version": "board-v1"}, "shots": [shot]},
        "creative_fingerprint": "c" * 64, "ordered_shot_ids": [shot["shot_id"]],
        "ordered_prompts": [shot["shot_prompt"]], "storyboard_version_id": "board-v1",
        "generation_contract": {"payload": {"prompt": "frozen prompt", "dialogue_handoff": dialogue,
            "scene_coverage": {"canonical_script_sha256": "a" * 64, "canonical_script_text": script,
                              "script_version_id": "script-v1", "scene_content_sha256": "b" * 64,
                              "scene_content": "FROZEN SCENE"},
            "references": [{**reference, "studio_role": "reference"}]}},
        "dialogue_handoff": dialogue, "coverage_contract": {"canonical_script_sha256": "a" * 64,
            "canonical_script_text": script, "script_version_id": "script-v1", "scene_content_sha256": "b" * 64,
            "scene_content": "FROZEN SCENE"},
        "reference_bindings": [reference], "reference_content_sha256": {"ref-setting": "1" * 64},
        "provider": "runway_router", "model_policy": {"policy_id": "model-route-v1"},
        "routing_policy_id": "route-v1", "router_config_id": "config-v1",
        "seed_policy": {"mode": "fixed", "seed": 17}, "retry_policy": RETRY_POLICY,
        "execution_parameters": {"seed": 17, "duration": 5},
        "provider_input_parameters": {},
    }
    authority["reference_bindings"] = [reference]
    authority["creative_manifest"] = payload["creative_manifest"]
    authority["coverage_contract"] = payload["coverage_contract"]
    authority["generation_contracts_by_shot"] = {shot["shot_id"]: payload["generation_contract"]}
    from app.services.scene002_contract_only import execution_envelope
    payload["execution_identity_sha256"] = digest(execution_envelope(payload))
    return payload, authority


def test_missing_execution_contract_fails_closed():
    with pytest.raises(Scene002ContractError, match="execution contract is missing"):
        verify_execution_contract(None)


@pytest.mark.parametrize("mutation", [
    "screenplay", "scene", "storyboard", "prompt", "dialogue", "reference", "execution",
])
def test_each_authorized_execution_identity_mismatch_fails_closed(mutation):
    from app.services.scene002_contract_only import verify_authorized_execution_components

    payload, authority = _authorized_components()
    if mutation == "screenplay":
        payload["coverage_contract"]["canonical_script_text"] = "mutable project screenplay"
    elif mutation == "scene":
        payload["creative_manifest"]["scene"]["scene_id"] = "scene_003"
    elif mutation == "storyboard":
        payload["creative_manifest"]["storyboard"]["storyboard_version"] = "board-mutated"
    elif mutation == "prompt":
        payload["generation_contract"]["payload"]["prompt"] = "altered prompt"
    elif mutation == "dialogue":
        payload["dialogue_handoff"]["sha256"] = "e" * 64
    elif mutation == "reference":
        payload["reference_bindings"][0]["uri"] = "file:///different.png"
    else:
        payload["execution_parameters"]["seed"] = 18
    with pytest.raises(Scene002ContractError):
        verify_authorized_execution_components(payload, authority)


def test_mutable_project_script_cannot_replace_authorized_screenplay():
    from app.services.scene002_contract_only import verify_authorized_execution_components

    payload, authority = _authorized_components()
    project = {"project_id": "project-1", "script_text": "MUTABLE PROJECT SCREENPLAY"}
    assert project["script_text"] != authority["screenplay_text"]
    payload["coverage_contract"]["canonical_script_text"] = project["script_text"]
    with pytest.raises(Scene002ContractError):
        verify_authorized_execution_components(payload, authority)


def test_changed_execution_fingerprint_fails_closed():
    record = _unsigned_execution_record()
    record["payload"]["router_config_id"] = "changed-config"
    with pytest.raises(Scene002ContractError, match="fingerprint"):
        verify_execution_contract(record)


def test_expired_prepared_snapshot_is_not_reconstructed():
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    service = SceneProductionPipelineService()
    with pytest.raises(Exception, match="unavailable or expired"):
        service._consume_prepared_scene_batch("missing-or-expired-token", project_id="project-1",
            scene_id="scene_002", provider="runway_router", project={"project_id": "project-1"},
            execution_mode=MODE, source_authority_id="auth-1")


def test_protected_project_save_rejects_screenplay_ownership_approval_and_storyboard_writes():
    before = {"project_id": "project-1", "script_text": "frozen", "ownership": {"owner": "creator"},
              "creative_approvals": {"board": True}, "execution_summary": {"one_button_render_jobs": []}}
    for field, changed in (("script_text", "rewritten"), ("ownership", {"owner": "other"}),
                           ("creative_approvals", {"board": False}), ("storyboard_narrative", "new story")):
        after = copy.deepcopy(before)
        after[field] = changed
        with pytest.raises(Scene002ContractError, match="creative-state changes"):
            assert_no_protected_project_mutation(before, after)


def test_protected_project_save_allows_render_bookkeeping_only():
    before = {"project_id": "project-1", "script_text": "frozen", "execution_summary": {"one_button_render_jobs": []}}
    after = copy.deepcopy(before)
    after["execution_summary"]["one_button_render_jobs"].append({"job_id": "job-result"})
    assert_no_protected_project_mutation(before, after)


def test_protected_seed_mutation_is_blocked():
    job = RenderJobModel(id="seed-job", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", metadata={"execution_mode": MODE})
    class Storage:
        def list_jobs(self, **kwargs):
            return [job]
    with pytest.raises(Scene002ContractError, match="seed and lock are frozen"):
        assert_protected_seed_unchanged(Storage(), "project-1", "scene_002_shot_001")


def test_current_project_screenplay_change_invalidates_revision_guard():
    assert project_revision_guard({"project_id": "project-1", "script_text": "A"}) != project_revision_guard(
        {"project_id": "project-1", "script_text": "Different"})


@pytest.mark.parametrize("field,value", [
    ("script_text", "mutated screenplay"), ("ownership", {"owner": "changed"}),
    ("creative_approvals", {"approved": False}), ("storyboard_narrative", "rewritten"),
    ("standing_corrections", ["new instruction"]), ("reference_authority", {"approved": True}),
])
def test_result_only_persistence_rejects_creative_metadata(field, value):
    metadata = _protected_metadata()
    metadata[field] = value
    with pytest.raises(Scene002ContractError, match="non-result metadata"):
        validate_result_only_metadata(metadata)


def test_result_only_persistence_allows_runtime_bookkeeping():
    metadata = _protected_metadata()
    metadata["router_execution"] = {"router_config_id": "router-config-1", "resolved_model": "router-selected"}
    metadata["pipeline_reliability"]["phase_timing"]["render"] = {"duration_ms": 12}
    validate_result_only_metadata(metadata)


def test_result_only_persistence_requires_immutable_proof():
    metadata = _protected_metadata()
    metadata.pop("scene002_execution_contract")
    with pytest.raises(Scene002ContractError, match="complete immutable creative proof"):
        validate_result_only_metadata(metadata)


def test_protected_job_contractless_and_altered_retries_reject():
    job = RenderJobModel(id="job-1", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", metadata={"execution_mode": MODE}, input_payload=RenderJobInput(prompt="frozen"))
    with pytest.raises(Scene002ContractError, match="Altered retries"):
        reject_altered_retry(job)
    with pytest.raises(Scene002ContractError, match="execution contract is missing"):
        assert_ordinary_retry_matches(job, copy.deepcopy(job))


def test_contractless_recovery_fails_closed():
    job = RenderJobModel(id="job-restart", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", status="pending", metadata={"execution_mode": MODE},
        input_payload=RenderJobInput(prompt="mutable"))
    with pytest.raises(Scene002ContractError, match="execution contract is missing"):
        from app.services.scene002_contract_only import verify_job_contract
        verify_job_contract(job)


def test_ordinary_retry_preserves_exact_contract_identity():
    from app.services.scene002_contract_only import protected_input_payload_identity

    first = RenderJobModel(id="same-job", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", metadata={"execution_mode": MODE}, input_payload=RenderJobInput(prompt="frozen"))
    retry = copy.deepcopy(first)
    retry.retry_count = 1
    assert first.metadata["execution_mode"] == retry.metadata["execution_mode"] == MODE
    assert protected_input_payload_identity(first.input_payload) == protected_input_payload_identity(retry.input_payload)
    altered = copy.deepcopy(retry)
    altered.input_payload.prompt = "altered"
    assert protected_input_payload_identity(first.input_payload) != protected_input_payload_identity(altered.input_payload)


def test_project_revision_guard_ignores_only_result_summary_bookkeeping():
    project = {"project_id": "project-1", "script_text": "frozen", "execution_summary": {"one_button_render_jobs": []}}
    result = copy.deepcopy(project)
    result["execution_summary"]["one_button_render_jobs"].append({"job_id": "j1"})
    assert project_revision_guard(project) == project_revision_guard(result)


def test_execution_fingerprint_binds_config_policy_and_retry():
    record = _unsigned_execution_record()
    for key, value in (("router_config_id", "other"), ("retry_policy", "altered")):
        changed = copy.deepcopy(record)
        changed["payload"][key] = value
        assert record["execution_fingerprint"] != digest(changed["payload"])


def test_protected_lifecycle_bookkeeping_does_not_mutate_contract_inputs(monkeypatch):
    from app.services import render as render_module

    job = RenderJobModel(id="job-protected", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", metadata=_protected_metadata(),
        input_payload=RenderJobInput(prompt="frozen", parameters={"seed": 17}))
    before_input, before_metadata = job.input_payload.model_dump(mode="json"), copy.deepcopy(job.metadata)
    monkeypatch.setattr(render_module, "_now_iso", lambda: "2026-10-05T00:00:00")
    render_module._set_zero_touch_phase(job, "render", "failed", error="poll failed")
    render_module._record_failure_location(job, phase="render", reason="poll failed")
    render_module._ensure_reliability_metadata(job)
    assert job.input_payload.model_dump(mode="json") == before_input
    assert job.metadata == before_metadata


def test_result_only_metadata_cannot_change_frozen_proof():
    before = _protected_metadata()
    after = copy.deepcopy(before)
    after["router_execution"] = {"status": "complete"}
    validate_result_only_metadata(after, previous=before)
    after["creative_contract_digest"] = "x" * 64
    with pytest.raises(Scene002ContractError, match="immutable metadata"):
        validate_result_only_metadata(after, previous=before)


def test_storage_persists_protected_results_but_rejects_input_mutation(tmp_path, monkeypatch):
    from app.data.storage import DatabaseStorage
    from app.models import RenderJobOutput, StudioProject
    from app.services import scene002_contract_only

    monkeypatch.setattr(scene002_contract_only, "verify_job_contract", lambda *args, **kwargs: {})
    storage = DatabaseStorage(str(tmp_path / "storage"))
    storage.save_project(StudioProject(project_id="project-1", title="fixture"))
    job = RenderJobModel(id="job-result-only", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", status="pending", metadata=_protected_metadata(),
        input_payload=RenderJobInput(prompt="frozen", parameters={"seed": 17}))
    storage.save_job(job)
    result = copy.deepcopy(job)
    result.status = "complete"
    result.output_payload = RenderJobOutput(asset_url="file:///result.mp4")
    result.metadata["router_execution"] = {"status": "complete", "provider_job_id": "task-1"}
    storage.save_job(result)
    recovered = storage.get_job(job.id)
    assert recovered.status == "complete"
    assert recovered.output_payload.asset_url == "file:///result.mp4"
    assert recovered.input_payload.model_dump(mode="json") == job.input_payload.model_dump(mode="json")
    assert recovered.metadata["scene002_execution_contract"] == job.metadata["scene002_execution_contract"]
    altered = copy.deepcopy(recovered)
    altered.input_payload.parameters["seed"] = 18
    with pytest.raises(ValueError, match="immutable creative input"):
        storage.save_job(altered)
    assert storage.get_job(job.id).input_payload.parameters["seed"] == 17
    storage.close()


def test_storage_rejects_protected_job_downgrade(tmp_path, monkeypatch):
    from app.data.storage import DatabaseStorage
    from app.models import StudioProject
    from app.services import scene002_contract_only

    monkeypatch.setattr(scene002_contract_only, "verify_job_contract", lambda *args, **kwargs: {})
    storage = DatabaseStorage(str(tmp_path / "storage"))
    storage.save_project(StudioProject(project_id="project-1", title="fixture"))
    protected = RenderJobModel(id="job-no-downgrade", project_id="project-1", shot_id="scene_002_shot_001",
        provider="runway_router", metadata=_protected_metadata(), input_payload=RenderJobInput(prompt="frozen"))
    storage.save_job(protected)
    ordinary = copy.deepcopy(protected)
    ordinary.metadata = {"router_execution": {"status": "complete"}}
    with pytest.raises(ValueError, match="cannot be downgraded"):
        storage.save_job(ordinary)
    assert storage.get_job(protected.id).metadata["execution_mode"] == MODE
    storage.close()


def test_authority_validation_fails_closed_when_key_is_unconfigured(monkeypatch):
    from app.services.scene002_contract_only import validate_authority_record

    monkeypatch.delenv("SCENE002_AUTHORITY_HMAC_KEY", raising=False)
    with pytest.raises(Scene002ContractError, match="verification key is not configured"):
        validate_authority_record(_authority())
