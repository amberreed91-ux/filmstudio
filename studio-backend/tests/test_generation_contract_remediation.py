from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services.generation_contract import (
    FrozenGenerationContract,
    GenerationContractError,
    freeze_generation_contract,
)
from app.services.generation_cost_gate import GenerationCostGate
from app.services.shot_manifest import build_shot_manifest, recompute_manifest_fingerprint
from app.services.stability import ValidationError
from app.data.storage import DatabaseStorage
from app.services.providers.runway_router_provider import (
    DEFAULT_ROUTER_CONFIG_ID,
    build_runway_router_video_request,
    get_router_config_id,
    project_frozen_camera_plan_prompt,
    reconstruct_runway_router_video_request,
)


def _job_with_frozen_contract(params: dict | None = None) -> RenderJobModel:
    """Build a valid synthetic Router job without reading/writing project state."""
    params = dict(params or {})
    shot_id = "scene_001_shot_001"
    prompt = "  Approved prompt bytes: keep the exact punctuation!  "
    camera_parameters = {
        "camera_plan": {"camera": "Slow dolly in", "framing": "Wide"},
        **params,
    }
    if "camera_instructions" not in camera_parameters:
        from app.services.camera_provenance import canonical_camera_instructions

        camera_parameters["camera_instructions"] = canonical_camera_instructions(
            camera_parameters["camera_plan"], camera_parameters.get("camera_provenance", "USER_SPECIFIED")
        )
    camera_parameters.setdefault(
        "camera_provenance",
        "USER_SPECIFIED" if camera_parameters.get("camera_plan") else "UNSPECIFIED",
    )
    camera_parameters.update(
        camera_source_project_id="project-contract-test",
        camera_source_scene_id="scene_001",
        camera_source_shot_id=shot_id,
        camera_target_project_id="project-contract-test",
        camera_target_scene_id="scene_001",
        camera_target_shot_id=shot_id,
    )
    from app.services.scene_coverage_contract import build_scene_coverage_contract

    scene_text = "INT. TEST ROOM - DAY\nA single lamp glows beside a closed book."
    project = {
        "project_id": "project-contract-test",
        "script_text": scene_text,
        "execution_summary": {"scenes": [], "dialogue_lines": []},
    }
    scene = {"scene_id": "scene_001", "heading": "INT. TEST ROOM - DAY", "text": scene_text, "setting_id": "setting-contract-test"}
    setting_refs = [
        {"ref_id": "ref-story", "project_id": "project-contract-test", "uri": "https://cdn.example.test/story.png", "target_type": "setting", "target_id": "setting-contract-test", "role": "environment", "category": "", "canonical": True, "approval_state": "approved", "source_kind": "confirmed", "kind": "environment"},
        {"ref_id": "ref-context", "project_id": "project-contract-test", "uri": "https://cdn.example.test/context.png", "target_type": "setting", "target_id": "setting-contract-test", "role": "environment", "category": "", "canonical": True, "approval_state": "approved", "source_kind": "confirmed", "kind": "environment"},
    ]
    from app.services.camera_provenance import camera_plan_digest

    camera_parameters["camera_source_digest"] = camera_plan_digest(
        camera_parameters["camera_plan"], camera_parameters["camera_provenance"],
        source_project_id="project-contract-test", source_scene_id="scene_001", source_shot_id=shot_id,
    )
    if not camera_parameters["camera_plan"]:
        camera_parameters["camera_source_digest"] = camera_plan_digest(
            {}, "UNSPECIFIED", source_project_id="project-contract-test",
            source_scene_id="scene_001", source_shot_id=shot_id,
        )
    shot = {
        "shot_id": shot_id,
        "scene_id": "scene_001",
        "shot_number": 1,
        "parameters": {
            **camera_parameters,
            "dialogue_disposition": "INTENTIONAL_SILENCE",
            "dialogue_disposition_reason": "The approved shot contains no spoken dialogue.",
        },
        "dialogue_disposition": "INTENTIONAL_SILENCE",
        "dialogue_disposition_reason": "The approved shot contains no spoken dialogue.",
    }
    requirements = {
        "setting_id": "setting-contract-test",
        "characters": {},
        "reference_binding": setting_refs,
    }
    coverage_probe, _, _ = build_scene_coverage_contract(
        project_id="project-contract-test", project=project, scene=scene,
        shots=[shot], reference_requirements=requirements,
    )
    creator_decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"],
         "status": "ASSIGNED", "shot_id": shot_id, "reason": ""}
        for row in coverage_probe["content_units"]
    ]
    creator_decisions.extend([
        {"obligation_type": "shot_content", "obligation_id": shot_id,
         "status": "UNRESOLVED", "shot_id": None, "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shot_id,
         "status": "INTENTIONAL_SILENCE",
         "reason": "The approved shot contains no spoken dialogue."},
    ])
    coverage, coverage_blockers, _ = build_scene_coverage_contract(
        project_id="project-contract-test", project=project, scene=scene,
        shots=[shot], reference_requirements=requirements,
        creator_decisions=creator_decisions,
    )
    assert not coverage_blockers, coverage_blockers
    shot_coverage = coverage["shots"][0]
    references = [
        {
            **row,
            "role": row.get("role") or "reference",
            "studio_role": row.get("role") or "reference",
            "source": "canonical_reference_binding",
        }
        for row in shot_coverage["approved_reference_bindings"]
    ]
    from app.services.generation_contract import freeze_dialogue_handoff
    dialogue_handoff = freeze_dialogue_handoff(scene_id="scene_001", shot_id=shot_id, lines=[])
    contract = freeze_generation_contract(
        shot_id=shot_id,
        prompt=prompt,
        negative_prompt="No extra people.",
        reference_assets=references,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
        dialogue_handoff=dialogue_handoff,
        parameters={
            "duration": 6,
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "seed": 43,
            "audio_intent": "generate",
            "content_moderation": "standard",
            **camera_parameters,
        },
    )
    manifest = build_shot_manifest(
        project_id="project-contract-test",
        scene_id="scene_001",
        scene=None,
        scene_version="test-scene-v1",
        storyboard_version="test-board-v1",
        scene_lineage=coverage,
        entries=[{
            "shot_id": shot_id,
            "shot_order": 1,
            "duration_seconds": contract.duration or 0,
            "prompt": contract.prompt,
            "negative_prompt": contract.negative_prompt,
            "audio_intent": contract.audio,
            "reference_roles": [ref.studio_role for ref in contract.references],
            "reference_binding": [
                {
                    "ref_id": ref.ref_id,
                    "uri": ref.uri,
                    "target_type": ref.target_type,
                    "target_id": ref.target_id,
                    "role": ref.studio_role,
                    "category": ref.category,
                    "canonical": ref.canonical,
                    "approval_state": ref.approval_state,
                    "source_kind": ref.source_kind,
                    **({"kind": ref.kind} if ref.kind else {}),
                    **({"project_id": "project-contract-test"} if ref.target_type == "setting" else {}),
                }
                for ref in contract.references
            ],
            "generation_contract_digest": contract.creative_digest(),
            "aspect_ratio": contract.aspect_ratio,
            "resolution": contract.resolution,
            "seed": contract.seed,
            "references": [ref.uri for ref in contract.references],
            "camera_plan": __import__("json").loads(contract.camera_plan_json),
            "camera_provenance": contract.camera_provenance,
            "camera_instructions": __import__("json").loads(contract.camera_instructions_json),
            "camera_source_digest": contract.camera_source_digest,
            "camera_source_project_id": contract.camera_source_project_id,
            "camera_source_scene_id": contract.camera_source_scene_id,
            "camera_source_shot_id": contract.camera_source_shot_id,
            "camera_source_storyboard_shot_id": contract.camera_source_storyboard_shot_id,
            "camera_target_project_id": contract.camera_target_project_id,
            "camera_target_scene_id": contract.camera_target_scene_id,
            "camera_target_shot_id": contract.camera_target_shot_id,
            "parameters": __import__("json").loads(contract.creative_parameters_json),
            "scene_coverage": coverage,
            "shot_coverage": shot_coverage,
            "dialogue_handoff": contract.payload().get("dialogue_handoff", {}),
        }],
    )
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
    manifest["shots"][0]["scene_coverage"] = coverage
    manifest["shots"][0]["scene_coverage_shot"] = shot_coverage
    manifest["shots"][0]["reference_binding"] = [
        {key: ref.get(key) for key in ("ref_id", "project_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind") if key in ref}
        for ref in manifest["shots"][0]["reference_binding"]
    ]
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
    record = contract.to_record()
    return RenderJobModel(
        id="job-contract-test",
        project_id="project-contract-test",
        shot_id=shot_id,
        provider="runway_router",
        status="pending",
        input_payload=RenderJobInput(
            shot_id=shot_id,
            prompt=contract.prompt,
            negative_prompt=contract.negative_prompt,
            referenceAssets=[ref.uri for ref in contract.references],
            parameters={
                **contract.payload()["creative_parameters"],
                "duration": contract.duration,
                "aspect_ratio": contract.aspect_ratio,
                "resolution": contract.resolution,
                "seed": contract.seed,
                "audio_intent": contract.audio,
                "negative_prompt": contract.negative_prompt,
                "camera_plan": contract.payload()["camera_plan"],
                "camera_provenance": contract.camera_provenance,
                "camera_source_digest": contract.camera_source_digest,
                "camera_instructions": contract.payload()["camera_instructions"],
                "camera_source_project_id": contract.camera_source_project_id,
                "camera_source_scene_id": contract.camera_source_scene_id,
                "camera_source_shot_id": contract.camera_source_shot_id,
                "camera_target_project_id": contract.camera_target_project_id,
                "camera_target_scene_id": contract.camera_target_scene_id,
                "camera_target_shot_id": contract.camera_target_shot_id,
                "reference_roles": [ref.studio_role for ref in contract.references],
                "frozen_reference_binding": [
                    {"ref_id": ref.ref_id, "uri": ref.uri, "target_type": ref.target_type,
                     "target_id": ref.target_id, "role": ref.studio_role, "category": ref.category,
                     "canonical": ref.canonical, "approval_state": ref.approval_state,
                     "source_kind": ref.source_kind, "kind": ref.kind,
                     "studio_role": ref.studio_role, "source": ref.source,
                     **({"project_id": "project-contract-test"} if ref.target_type == "setting" else {})}
                    for ref in contract.references
                ],
                "scene_coverage": coverage,
            "scene_coverage_shot": shot_coverage,
            "dialogue_lines": contract.payload().get("dialogue_handoff", {}).get("payload", {}).get("lines", []),
            "dialogue_handoff": contract.payload().get("dialogue_handoff", {}),
            },
        ),
        metadata={
            "creative_generation_contract": record,
            "creative_generation_manifest": manifest,
            "creative_manifest_fingerprint": manifest["manifest_fingerprint"],
            "creative_contract_digest": contract.creative_digest(),
        "creative_generation_identity": {
            "job_id": "job-contract-test",
            "project_id": "project-contract-test",
            "shot_id": shot_id,
            "provider": "runway_router",
        },
        },
    )


def _provider_config() -> ProviderConfig:
    return ProviderConfig(
        provider_id="runway_router",
        name="Runway Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "model_routing"],
    )


_ROUTER_AUTHORITY_OWNER = "router-authority-owner"
_ROUTER_AUTHORITY_BOARD_SHOT = "board-shot-authority"


def _bind_router_execution_authority(job):
    """Bind a frozen-contract job to owner-approved storyboard authority.

    Direct calls to ``_submit_job_after_authorization`` must satisfy the same
    durable authority as the adapter entry gate. This binds the exact approved
    storyboard version/scope already frozen in the job to an in-memory
    authority store and returns that store; callers patch
    ``app.data.storage.get_storage`` with it. Must run after the test's own
    job mutations so the durable row matches the submitted job.
    """
    from types import SimpleNamespace

    owner = _ROUTER_AUTHORITY_OWNER
    manifest = job.metadata["creative_generation_manifest"]
    scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
    scene_id = str(scene.get("scene_id") or "").strip()
    storyboard = manifest.get("storyboard") if isinstance(manifest.get("storyboard"), dict) else {}
    version_id = str(storyboard.get("storyboard_version") or "").strip() or "test-board-v1"
    try:
        contract = FrozenGenerationContract.from_record(job.metadata["creative_generation_contract"])
    except (GenerationContractError, TypeError, ValueError, KeyError):
        contract = None
    if contract is not None:
        manifest.setdefault("storyboard", {})["storyboard_version"] = version_id
        for row in manifest.get("shots", []):
            if isinstance(row, dict) and row.get("shot_id") == job.shot_id:
                row["storyboard_shot_id"] = _ROUTER_AUTHORITY_BOARD_SHOT
        for _ in range(3):
            manifest["manifest_fingerprint"] = ""
            fingerprint = recompute_manifest_fingerprint(manifest)
            manifest["manifest_fingerprint"] = fingerprint
            contract = replace(contract, manifest_fingerprint=fingerprint)
            for row in manifest.get("shots", []):
                if isinstance(row, dict) and row.get("shot_id") == job.shot_id:
                    row["generation_contract_digest"] = contract.creative_digest()
        job.metadata.update(
            creative_generation_contract=contract.to_record(),
            creative_generation_manifest=manifest,
            creative_manifest_fingerprint=manifest["manifest_fingerprint"],
            creative_contract_digest=contract.creative_digest(),
        )
    job.metadata["production_request_actor_id"] = owner
    job.input_payload.parameters["storyboard"] = {
        "storyboard_shot_id": _ROUTER_AUTHORITY_BOARD_SHOT,
        "version_id": version_id,
    }
    blueprint = SimpleNamespace(
        blueprint_id="board-authority",
        project_id=job.project_id,
        scene_id=scene_id,
        current_version_id=version_id,
        approved_version_id=version_id,
        status="approved",
    )
    version = SimpleNamespace(
        version_id=version_id,
        blueprint_id="board-authority",
        project_id=job.project_id,
        scene_id=scene_id,
        status="approved",
        approved_at="2026-10-10T12:00:00Z",
        approved_by=owner,
        metadata={"production_approval": {"actor_id": owner, "actor_authenticated": True}},
    )
    shot = SimpleNamespace(
        storyboard_shot_id=_ROUTER_AUTHORITY_BOARD_SHOT,
        blueprint_id="board-authority",
        version_id=version_id,
        project_id=job.project_id,
        scene_id=scene_id,
        shot_id=job.shot_id,
        status="approved",
    )
    durable = job.model_copy(deep=True)
    return SimpleNamespace(
        get_job=lambda job_id: durable.model_copy(deep=True) if job_id == job.id else None,
        access_project_owner=lambda project_id: owner if project_id == job.project_id else None,
        get_project=lambda project_id: {} if project_id == job.project_id else None,
        get_storyboard_blueprint=lambda project_id, scene_id: blueprint,
        get_storyboard_blueprint_version=lambda version_id_: version if version_id_ == version_id else None,
        get_storyboard_shot=lambda shot_id: shot if shot_id == _ROUTER_AUTHORITY_BOARD_SHOT else None,
    )


def _submit_authorized(monkeypatch, job):
    """Run the provider execution boundary with authority provisioned."""
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    return asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(job))


def test_router_projection_is_identical_for_dry_run_and_live_submission(monkeypatch):
    calls = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if method == "POST" and payload and payload.get("dryRun"):
            return {"dryRun": True, "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": "studio-production-router", "estimatedCost": {"credits": 20},
            }}
        if method == "POST":
            return {"dryRun": False, "id": "task-id", "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": "studio-production-router", "estimatedCost": {"credits": 20},
            }}
        return {"id": "task-id", "status": "SUCCEEDED", "output": ["https://cdn.test/out.mp4"]}

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    monkeypatch.setattr("app.services.providers.runway_router_provider.time.sleep", lambda *_: None)
    job = _job_with_frozen_contract()
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "complete", result.error_message

    dry_payload = next(payload for method, payload in calls if method == "POST" and payload.get("dryRun"))
    live_payload = next(payload for method, payload in calls if method == "POST" and not payload.get("dryRun"))
    contract = FrozenGenerationContract.from_record(job.metadata["creative_generation_contract"])
    expected = project_frozen_camera_plan_prompt(contract.prompt, contract.payload()["camera_plan"])
    assert dry_payload["input"]["promptText"] == live_payload["input"]["promptText"] == expected


def test_offline_router_reconstruction_matches_live_body_and_stale_script_fails_closed(monkeypatch):
    calls = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, copy.deepcopy(payload)))
        if method == "POST" and payload and payload.get("dryRun"):
            return {"dryRun": True, "routing": {
                "model": "router-selected", "provider": "runway",
                "configId": "phase6-test-router", "estimatedCost": {"credits": 1},
            }}
        if method == "POST":
            return {"dryRun": False, "id": "offline-proof-task", "routing": {
                "model": "router-selected", "provider": "runway",
                "configId": "phase6-test-router", "estimatedCost": {"credits": 1},
            }}
        return {"id": "offline-proof-task", "status": "SUCCEEDED", "output": ["https://cdn.test/offline.mp4"]}

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("RUNWAY_ROUTER_CONFIG_ID", "phase6-test-router")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    monkeypatch.setattr("app.services.providers.runway_router_provider.time.sleep", lambda *_: None)
    job = _job_with_frozen_contract()
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    contract_record = copy.deepcopy(job.metadata["creative_generation_contract"])
    manifest = copy.deepcopy(job.metadata["creative_generation_manifest"])
    offline = reconstruct_runway_router_video_request(
        contract_record, manifest, config_id="phase6-test-router"
    )

    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(job))
    assert result.status == "complete", result.error_message
    dry_payload = next(payload for method, payload in calls if method == "POST" and payload.get("dryRun"))
    live_payload = next(payload for method, payload in calls if method == "POST" and not payload.get("dryRun"))
    assert dry_payload == {**offline, "dryRun": True}
    assert live_payload == offline

    # Canonical source freshness is enforced at the scene pipeline handoff,
    # while Router reconstruction is a pure projection of the frozen proof.
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    script = "INT. TEST ROOM - DAY\\nA single lamp glows beside a closed book."
    scene = {"scene_id": "scene_001", "heading": "INT. TEST ROOM - DAY", "text": script}
    project = {
        "project_id": "project-contract-test",
        "script_text": script,
        "execution_summary": {"scenes": [scene]},
    }
    pipeline = SceneProductionPipelineService(backend_root=__import__("pathlib").Path("."))
    batch = {
        "project_id": "project-contract-test",
        "canonical_script_sha256": __import__("hashlib").sha256(script.encode("utf-8")).hexdigest(),
        "scene_snapshot_fingerprint": pipeline._snapshot_fingerprint(scene),
        "source_kind": "single_shot_fallback",
        "shots": [],
    }
    project["script_text"] = script.replace("single lamp", "broken lantern")
    with pytest.raises(ValidationError, match="canonical screenplay changed after preflight") as exc_info:
        pipeline._assert_prepared_scene_batch_current(batch, project=project, scene_id="scene_001")
    assert exc_info.value.stage == "scene_pipeline_lineage"
    assert exc_info.value.metadata["failure_type"] == "stale_canonical_script"
    assert reconstruct_runway_router_video_request(
        contract_record, manifest, config_id="phase6-test-router"
    ) == offline
    assert len([1 for method, _ in calls if method == "POST"]) == 2


def test_frozen_camera_projection_is_deterministic_and_does_not_duplicate_existing_language():
    prompt = "An intimate portrait. camera: Slow dolly in\nframing: Wide"
    plan = {"framing": "Wide", "camera": "Slow dolly in"}
    projected = project_frozen_camera_plan_prompt(prompt, plan)
    assert projected == prompt
    assert project_frozen_camera_plan_prompt(prompt, plan) == projected
    partially_present = project_frozen_camera_plan_prompt(
        "An intimate portrait. Slow dolly in camera movement.", plan
    )
    assert partially_present.count("Slow dolly in") == 1
    assert "framing: Wide" in partially_present
    assert project_frozen_camera_plan_prompt("An intimate portrait.", plan) == (
        "An intimate portrait.\n\n[CREATOR CAMERA PLAN — use for this shot]\n"
        "camera: Slow dolly in\nframing: Wide"
    )
    assert project_frozen_camera_plan_prompt("An intimate portrait.", {**plan, "camera": "Crane up"}) != projected


def test_generation_contract_freezes_exact_prompt_audio_and_reference_semantics():
    approved_prompt = "Exact bytes: café — retain spaces. "
    source_refs = [
        {"uri": "https://cdn.test/first.png", "studio_role": "storyboard"},
        {"uri": "https://cdn.test/wardrobe.png", "studio_role": "wardrobe"},
    ]
    frozen = freeze_generation_contract(
        shot_id="s1",
        prompt=approved_prompt,
        reference_assets=source_refs,
        parameters={"audio_intent": "generate", "duration": 7, "aspect_ratio": "4:3", "resolution": "1080p", "seed": 11},
    )
    source_refs.reverse()
    record = frozen.to_record()
    restored = FrozenGenerationContract.from_record(record)
    assert restored.prompt == approved_prompt
    assert [ref.uri for ref in restored.references] == ["https://cdn.test/first.png", "https://cdn.test/wardrobe.png"]
    assert [ref.studio_role for ref in restored.references] == ["storyboard", "wardrobe"]
    assert restored.audio is True
    assert (restored.aspect_ratio, restored.duration, restored.resolution, restored.seed) == ("4:3", 7, "1080p", 11)


def test_contract_record_tampering_fails_digest_verification():
    record = freeze_generation_contract(shot_id="s1", prompt="approved").to_record()
    record["payload"]["prompt"] = "silently changed"
    with pytest.raises(GenerationContractError, match="integrity"):
        FrozenGenerationContract.from_record(record)


def test_unsupported_audio_language_fails_closed():
    with pytest.raises(GenerationContractError, match="audio_intent"):
        freeze_generation_contract(shot_id="s1", prompt="x", parameters={"audio_intent": "dialogue plus score mix"})


def _create_router_contract_for_integrity_test(storage, source, *, manifest, contract_record, frozen_binding):
    from app.access_context import access_user_id
    from app.services.render import RenderService

    storage.save_project(__import__("app.models", fromlist=["StudioProject"]).StudioProject(
        project_id=source.project_id,
        title="Frozen-contract test",
    ))
    storage.access_save_user({"username": "owner-test", "user_id": "owner-test"}, create=True)
    storage.access_claim_project(source.project_id, "owner-test")
    from app.models.storyboard_blueprint import (
        StoryboardBlueprint,
        StoryboardBlueprintStatus,
        StoryboardBlueprintVersion,
        StoryboardShot,
        StoryboardShotStatus,
    )
    from app.services.shot_manifest import recompute_manifest_fingerprint

    manifest["storyboard"] = {"storyboard_version": "test-board-v1"}
    manifest["shots"][0]["storyboard_shot_id"] = "board-shot-test"
    frozen = FrozenGenerationContract.from_record(contract_record)
    manifest["shots"][0]["generation_contract_digest"] = frozen.creative_digest()
    manifest["manifest_fingerprint"] = ""
    fingerprint = recompute_manifest_fingerprint(manifest)
    manifest["manifest_fingerprint"] = fingerprint
    frozen = replace(frozen, manifest_fingerprint=fingerprint)
    contract_record = frozen.to_record()
    manifest["shots"][0]["generation_contract_digest"] = frozen.creative_digest()
    manifest["manifest_fingerprint"] = ""
    fingerprint = recompute_manifest_fingerprint(manifest)
    manifest["manifest_fingerprint"] = fingerprint
    frozen = replace(frozen, manifest_fingerprint=fingerprint)
    contract_record = frozen.to_record()
    manifest["shots"][0]["generation_contract_digest"] = frozen.creative_digest()
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    fingerprint = manifest["manifest_fingerprint"]
    frozen = replace(frozen, manifest_fingerprint=fingerprint)
    contract_record = frozen.to_record()
    actor_token = access_user_id.set("owner-test")
    try:
        return RenderService().create_job(
            project_id=source.project_id,
            shot_id=source.shot_id,
            provider="runway_router",
            prompt=frozen.prompt,
            parameters={
                **source.input_payload.parameters,
                "storyboard": {"storyboard_shot_id": "board-shot-test", "version_id": "test-board-v1"},
            },
            reference_assets=source.input_payload.referenceAssets,
            generation_contract=contract_record,
            creative_manifest=manifest,
            creative_manifest_fingerprint=fingerprint,
            frozen_reference_binding=frozen_binding,
            dialogue_handoff=contract_record["payload"]["dialogue_handoff"],
            prepared_generation_contract=contract_record,
        )
    finally:
        access_user_id.reset(actor_token)


def test_render_service_persists_and_reloads_router_contract_exactly(tmp_path, monkeypatch):
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / "router-contract-storage"))
    monkeypatch.setattr("app.services.render._storage", storage)
    source = _job_with_frozen_contract()
    source.metadata["creative_generation_identity"]["job_id"] = "job-contract-test"
    source.input_payload.parameters["dialogue_handoff"] = source.metadata["creative_generation_contract"]["payload"].get("dialogue_handoff", {})
    source.input_payload.parameters["dialogue_lines"] = source.metadata["creative_generation_contract"]["payload"]["dialogue_handoff"]["payload"]["lines"]
    source.input_payload.parameters["scene_coverage"] = source.metadata["creative_generation_contract"]["payload"]["scene_coverage"]
    source.input_payload.parameters["scene_coverage_shot"] = source.metadata["creative_generation_contract"]["payload"]["scene_coverage_shot"]
    contract_record = source.metadata["creative_generation_contract"]
    source_contract = FrozenGenerationContract.from_record(contract_record)
    # Pipeline-realistic scope: setting rows always carry their owning
    # project_id (cf. _approved_setting_references; R4.5 session A,
    # owner-authorized fixture shape).
    frozen_binding = [
        {
            "ref_id": ref.ref_id, "uri": ref.uri, "target_type": ref.target_type,
            "target_id": ref.target_id, "role": ref.studio_role, "category": ref.category,
            "canonical": ref.canonical, "approval_state": ref.approval_state,
            "source_kind": ref.source_kind, "kind": ref.kind,
            **({"project_id": source.project_id} if ref.target_type == "setting" else {}),
        }
        for ref in source_contract.references
    ]
    source.input_payload.parameters["frozen_reference_binding"] = frozen_binding
    manifest = copy.deepcopy(source.metadata["creative_generation_manifest"])
    from app.services.shot_manifest import recompute_manifest_fingerprint
    frozen_contract = FrozenGenerationContract.from_record(contract_record)
    manifest_shot = manifest["shots"][0]
    manifest_shot["generation_contract_digest"] = frozen_contract.creative_digest()
    manifest_shot["scene_coverage"] = contract_record["payload"]["scene_coverage"]
    manifest_shot["scene_coverage_shot"] = contract_record["payload"]["scene_coverage_shot"]
    manifest_shot["reference_binding"] = [
        {key: row.get(key) for key in ("ref_id", "project_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind") if key in row}
        for row in frozen_binding
    ]
    source.input_payload.parameters["frozen_reference_binding"] = frozen_binding
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract_record = replace(frozen_contract, manifest_fingerprint=manifest["manifest_fingerprint"]).to_record()
    manifest_shot["generation_contract_digest"] = FrozenGenerationContract.from_record(contract_record).creative_digest()
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract_record = replace(FrozenGenerationContract.from_record(contract_record), manifest_fingerprint=manifest["manifest_fingerprint"]).to_record()
    manifest_shot["generation_contract_digest"] = FrozenGenerationContract.from_record(contract_record).creative_digest()
    service = RenderService()
    from app.access_context import access_user_id
    from app.models import StudioProject
    from app.models.storyboard_blueprint import (
        StoryboardBlueprint,
        StoryboardBlueprintStatus,
        StoryboardBlueprintVersion,
        StoryboardShot,
        StoryboardShotStatus,
    )
    storage.save_project(StudioProject(project_id=source.project_id, title="Frozen-contract test"))
    storage.access_save_user({"username": "owner-test", "user_id": "owner-test"}, create=True)
    storage.access_claim_project(source.project_id, "owner-test")
    manifest["storyboard"] = {"storyboard_version": "test-board-v1"}
    manifest_shot["storyboard_shot_id"] = "board-shot-test"
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract_record = replace(FrozenGenerationContract.from_record(contract_record), manifest_fingerprint=manifest["manifest_fingerprint"]).to_record()
    manifest_shot["generation_contract_digest"] = FrozenGenerationContract.from_record(contract_record).creative_digest()
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract_record = replace(FrozenGenerationContract.from_record(contract_record), manifest_fingerprint=manifest["manifest_fingerprint"]).to_record()
    manifest_shot["generation_contract_digest"] = FrozenGenerationContract.from_record(contract_record).creative_digest()
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    fingerprint = manifest["manifest_fingerprint"]
    contract_record = replace(FrozenGenerationContract.from_record(contract_record), manifest_fingerprint=fingerprint).to_record()
    storage.save_storyboard_blueprint(StoryboardBlueprint(
        blueprint_id="board-test", project_id=source.project_id, scene_id="scene_001",
        current_version_id="test-board-v1", approved_version_id="test-board-v1", status=StoryboardBlueprintStatus.APPROVED,
    ))
    storage.save_storyboard_blueprint_version(StoryboardBlueprintVersion(
        version_id="test-board-v1", blueprint_id="board-test", project_id=source.project_id, scene_id="scene_001",
        status=StoryboardBlueprintStatus.APPROVED, approved_at="2026-10-10T12:00:00Z", approved_by="owner-test",
        metadata={"production_approval": {"actor_id": "owner-test", "actor_authenticated": True}},
    ))
    storage.save_storyboard_shot(StoryboardShot(
        storyboard_shot_id="board-shot-test", blueprint_id="board-test", version_id="test-board-v1",
        project_id=source.project_id, scene_id="scene_001", shot_id=source.shot_id, shot_number=1,
        status=StoryboardShotStatus.APPROVED,
    ))
    token = access_user_id.set("owner-test")
    try:
        created = service.create_job(
            project_id=source.project_id,
            shot_id=source.shot_id,
            provider="runway_router",
            prompt=source.input_payload.prompt,
            parameters={
                **source.input_payload.parameters,
                "storyboard": {"storyboard_shot_id": "board-shot-test", "version_id": "test-board-v1"},
            },
            reference_assets=source.input_payload.referenceAssets,
            generation_contract=contract_record,
            creative_manifest=manifest,
            creative_manifest_fingerprint=fingerprint,
            frozen_reference_binding=frozen_binding,
            dialogue_handoff=contract_record["payload"]["dialogue_handoff"],
            prepared_generation_contract=contract_record,
        )
    finally:
        access_user_id.reset(token)
    reloaded = storage.get_job(created.id)
    service_reloaded = service.get_job(created.id)
    assert reloaded is not None and service_reloaded is not None
    assert service_reloaded.metadata == reloaded.metadata
    for key in (
        "creative_generation_contract",
        "creative_generation_manifest",
        "creative_manifest_fingerprint",
        "creative_contract_digest",
        "creative_generation_identity",
    ):
        assert reloaded.metadata[key] == created.metadata[key]
    assert recompute_manifest_fingerprint(reloaded.metadata["creative_generation_manifest"]) == reloaded.metadata["creative_manifest_fingerprint"]


def test_storage_rejects_router_job_with_incomplete_frozen_metadata(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "incomplete-router-storage"))
    job = RenderJobModel(
        id="job-incomplete-router",
        project_id="project-contract-test",
        shot_id="scene_001_shot_001",
        provider="runway_router",
        input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="mutable"),
        metadata={},
    )
    with pytest.raises(RuntimeError, match="complete frozen contract metadata"):
        storage.save_job(job)


def test_router_adapter_uses_frozen_values_not_mutable_render_input(monkeypatch):
    calls = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if method == "POST" and payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "resolvedSettings": {"priceCeiling": 250},
                    "resolvedInput": {},
                    "estimatedCost": {"credits": 20},
                },
            }
        if method == "POST":
            return {
                "dryRun": False,
                "id": "task-id",
                "routing": {
                    "model": "seedance2_5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "resolvedSettings": {"priceCeiling": 250},
                    "resolvedInput": {},
                    "estimatedCost": {"credits": 20},
                },
            }
        return {"id": "task-id", "status": "SUCCEEDED", "output": ["https://cdn.test/out.mp4"], "cost": {"credits": 18}}

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    job = _job_with_frozen_contract()
    job.metadata["creative_generation_identity"]["job_id"] = job.id
    job.input_payload.parameters["dialogue_handoff"] = job.metadata["creative_generation_contract"]["payload"].get("dialogue_handoff", {})
    job.input_payload.parameters["scene_coverage"] = job.metadata["creative_generation_contract"]["payload"]["scene_coverage"]
    job.input_payload.parameters["scene_coverage_shot"] = job.metadata["creative_generation_contract"]["payload"]["scene_coverage_shot"]
    job.input_payload.parameters["camera_plan"] = {"camera": "mutated mutable-job camera value"}
    job.input_payload.parameters["camera_instructions"] = [
        {"dimension": "camera", "value": "mutated mutable-job camera value", "instruction_source": "USER_SPECIFIED", "source_version": ""}
    ]
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    original_manifest = copy.deepcopy(job.metadata["creative_generation_manifest"])
    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    monkeypatch.setattr("app.services.providers.runway_router_provider.time.sleep", lambda *_: None)
    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(job))
    assert result.status == "complete", result.error_message
    assert result.metadata["router_execution"]["estimated_cost_semantics"] == "ADVISORY_ESTIMATE"
    assert result.metadata["router_execution"]["quote_authorization_supported"] is False
    assert result.metadata["router_execution"]["provider_cost_capabilities"] == {
        "ADVISORY_ESTIMATE": True,
        "PROVIDER_ENFORCED_MAXIMUM": True,
        "QUOTE_AUTHORIZATION": False,
    }
    assert result.metadata["router_execution"]["decision_semantics"] == (
        "Runway dry-run estimated this request at approximately 20 credits; "
        "Studio policy permits submission under configured local controls; "
        "Runway independently applies its provider-side limits."
    )
    assert result.metadata["router_execution"]["resolved_model"] == "seedance2_5"
    assert result.metadata["router_execution"]["resolved_model"] != "gen4.5"
    dry_payload = next(payload for method, payload in calls if method == "POST" and payload.get("dryRun"))
    video_input = dry_payload["input"]
    assert video_input["promptText"] == (
        "  Approved prompt bytes: keep the exact punctuation!  "
        "\n\n[CREATOR CAMERA PLAN — use for this shot]\n"
        "camera: Slow dolly in\nframing: Wide"
    )
    assert video_input["promptText"] != job.metadata["creative_generation_contract"]["payload"]["prompt"]
    assert video_input["promptText"].endswith("camera: Slow dolly in\nframing: Wide")
    assert "camera" not in video_input and "cameraPlan" not in video_input
    assert set(video_input) <= {
        "promptText", "aspectRatio", "duration", "resolution", "negativePrompt",
        "audio", "seed", "contentModeration", "referenceImages",
        "referenceVideos", "referenceAudio", "keyframes",
    }
    assert job.metadata["creative_generation_contract"]["payload"]["prompt"] == "  Approved prompt bytes: keep the exact punctuation!  "
    assert job.metadata["creative_generation_contract"]["payload"]["camera_plan"] == {
        "camera": "Slow dolly in", "framing": "Wide"
    }
    assert job.metadata["creative_generation_manifest"] == original_manifest
    frozen_payload = job.metadata["creative_generation_contract"]["payload"]
    assert frozen_payload["camera_provenance"] == "USER_SPECIFIED"
    assert {row["dimension"]: row["value"] for row in frozen_payload["camera_instructions"] if row["value"]} == frozen_payload["camera_plan"]
    live_payload = next(payload for method, payload in calls if method == "POST" and not payload.get("dryRun"))
    assert live_payload["input"]["promptText"] == video_input["promptText"]
    assert video_input["negativePrompt"] == "No extra people."
    assert [row["uri"] for row in video_input["referenceImages"]] == [
        "https://cdn.example.test/story.png", "https://cdn.example.test/context.png"
    ]
    assert [row["role"] for row in video_input["referenceImages"]] == ["reference", "reference"]
    assert video_input["audio"] is True
    assert video_input["duration"] == 6
    assert video_input["aspectRatio"] == "16:9"
    assert video_input["resolution"] == "720p"
    assert video_input["seed"] == 43
    assert video_input["contentModeration"] == "standard"
    assert job.input_payload.prompt == job.metadata["creative_generation_contract"]["payload"]["prompt"]
    assert job.input_payload.parameters["camera_plan"] == {"camera": "mutated mutable-job camera value"}
    assert job.input_payload.parameters["camera_instructions"][0]["value"] == "mutated mutable-job camera value"
    assert len([1 for method, payload in calls if method == "POST" and payload.get("dryRun")]) == 1
    assert len([1 for method, payload in calls if method == "POST" and not payload.get("dryRun")]) == 1


@pytest.mark.parametrize("missing_representation", ["absent", "empty"])
def test_router_missing_frozen_camera_plan_fails_closed_before_http(monkeypatch, missing_representation):
    calls = []
    job = _job_with_frozen_contract()
    payload = job.metadata["creative_generation_contract"]["payload"]
    if missing_representation == "empty":
        payload["camera_plan"] = {}
        payload["camera_provenance"] = "UNSPECIFIED"
        from app.services.camera_provenance import camera_plan_digest, canonical_camera_instructions
        payload["camera_source_digest"] = camera_plan_digest(
            {}, "UNSPECIFIED", source_project_id=payload["camera_source_project_id"],
            source_scene_id=payload["camera_source_scene_id"], source_shot_id=payload["camera_source_shot_id"],
        )
        payload["camera_instructions"] = canonical_camera_instructions({}, "UNSPECIFIED")
    else:
        payload.pop("camera_plan")
    import hashlib
    import json

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    job.metadata["creative_generation_contract"]["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("missing required frozen camera plan must fail before Router HTTP")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    # An absent camera plan breaks contract integrity and is denied at the
    # authority gate; an explicitly empty plan stays structurally valid and
    # is denied by the Router camera-plan check. Either way zero HTTP calls.
    auth = result.metadata.get("production_authorization") or {}
    if auth.get("allowed") is False:
        assert auth["reason"] in {
            "frozen_generation_contract_integrity_failed", "production_authority_lookup_failed",
        }
    else:
        assert result.metadata["router_execution"]["reason"] in {
            "frozen_camera_plan_missing", "frozen_contract_digest_mismatch",
            "frozen_contract_manifest_creative_mismatch",
        }
    assert calls == []


def test_router_camera_plan_isolated_between_frozen_shots(monkeypatch):
    calls = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if method == "POST" and payload and payload.get("dryRun"):
            return {"dryRun": True, "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": "studio-production-router", "estimatedCost": {"credits": 20},
            }}
        if method == "POST":
            return {"dryRun": False, "id": "task-id", "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": "studio-production-router", "estimatedCost": {"credits": 20},
            }}
        return {"id": "task-id", "status": "SUCCEEDED", "output": ["https://cdn.test/out.mp4"]}

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    monkeypatch.setattr("app.services.providers.runway_router_provider.time.sleep", lambda *_: None)
    plans = [
        {"camera": "Pan left", "framing": "Wide"},
        {"camera": "Tilt down", "framing": "Close-up"},
    ]
    for plan in plans:
        job = _job_with_frozen_contract({"camera_plan": plan})
        result = _submit_authorized(monkeypatch, job)
        assert result.status == "complete", result.error_message
    dry_prompts = [payload["input"]["promptText"] for method, payload in calls if method == "POST" and payload.get("dryRun")]
    assert len(dry_prompts) == 2
    assert "camera: Pan left" in dry_prompts[0] and "camera: Tilt down" not in dry_prompts[0]
    assert "camera: Tilt down" in dry_prompts[1] and "camera: Pan left" not in dry_prompts[1]


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_contract", "bad_record_hash", "bad_identity",
        "bad_manifest_fingerprint", "bad_contract_digest", "bad_camera_source_digest",
        "bad_manifest_camera_plan", "bad_contract_camera_instructions",
        "bad_manifest_camera_instructions",
    ],
)
def test_router_contract_failures_make_zero_provider_calls(monkeypatch, corruption):
    calls = []
    job = _job_with_frozen_contract()
    # Provision valid authority first: the durable row captures the approved
    # request, then each corruption mutates only the submitted job so the
    # execution boundary must deny it before any provider call.
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    if corruption == "missing_contract":
        job.metadata.pop("creative_generation_contract")
    elif corruption == "bad_record_hash":
        job.metadata["creative_generation_contract"]["sha256"] = "0" * 64
    elif corruption == "bad_identity":
        job.metadata["creative_generation_identity"]["job_id"] = "wrong-job"
    elif corruption == "bad_manifest_fingerprint":
        job.metadata["creative_generation_manifest"]["shots"][0]["shot_prompt"] = "tampered"
    elif corruption == "bad_contract_digest":
        job.metadata["creative_generation_manifest"]["shots"][0]["generation_contract_digest"] = "0" * 64
    elif corruption == "bad_camera_source_digest":
        import hashlib
        import json

        record = job.metadata["creative_generation_contract"]
        record["payload"]["camera_plan"]["camera"] = "tampered after preparation"
        encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    elif corruption == "bad_contract_camera_instructions":
        import hashlib
        import json

        record = job.metadata["creative_generation_contract"]
        record["payload"]["camera_instructions"][0]["value"] = "tampered structured projection"
        encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    elif corruption == "bad_manifest_camera_instructions":
        manifest = job.metadata["creative_generation_manifest"]
        manifest["shots"][0]["camera_instructions"][0]["value"] = "tampered structured projection"
        manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
        job.metadata["creative_manifest_fingerprint"] = manifest["manifest_fingerprint"]
        record = job.metadata["creative_generation_contract"]
        record["payload"]["manifest_fingerprint"] = manifest["manifest_fingerprint"]
        import hashlib
        import json

        encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
        job.metadata["creative_contract_digest"] = FrozenGenerationContract.from_record(record).creative_digest()
    elif corruption == "bad_manifest_camera_plan":
        manifest = job.metadata["creative_generation_manifest"]
        manifest["shots"][0]["camera_plan"] = {"camera": "tampered after preparation"}
        manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
        job.metadata["creative_manifest_fingerprint"] = manifest["manifest_fingerprint"]
        record = job.metadata["creative_generation_contract"]
        record["payload"]["manifest_fingerprint"] = manifest["manifest_fingerprint"]
        import hashlib
        import json

        encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
        job.metadata["creative_contract_digest"] = FrozenGenerationContract.from_record(record).creative_digest()

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid persisted contract must fail before Router request")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(job))
    assert result.status == "failed"
    assert calls == []


@pytest.mark.parametrize(
    ("identity_field", "replacement"),
    [
        ("camera_target_project_id", "project-other"),
        ("camera_target_scene_id", "scene_other"),
        ("camera_target_shot_id", "scene_001_shot_009"),
    ],
)
def test_router_rejects_cross_project_scene_or_shot_camera_before_provider(
    monkeypatch, identity_field, replacement
):
    import hashlib
    import json

    calls = []
    job = _job_with_frozen_contract()
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    record = job.metadata["creative_generation_contract"]
    record["payload"][identity_field] = replacement
    encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("cross-identity camera must fail before provider HTTP")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)

    assert result.status == "failed"
    assert calls == []


@pytest.mark.parametrize("manifest_field", ["references", "reference_roles"])
def test_render_service_rejects_manifest_reference_mismatch(tmp_path, monkeypatch, manifest_field):
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / f"reference-mismatch-{manifest_field}"))
    monkeypatch.setattr("app.services.render._storage", storage)
    source = _job_with_frozen_contract()
    manifest = copy.deepcopy(source.metadata["creative_generation_manifest"])
    if manifest_field == "references":
        manifest["shots"][0]["references"][0] = "https://cdn.example.test/tampered.png"
    else:
        manifest["shots"][0]["reference_roles"][0] = "wardrobe"
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract = FrozenGenerationContract.from_record(source.metadata["creative_generation_contract"])
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])

    frozen_binding = [
        {
            "ref_id": ref.ref_id,
            "uri": ref.uri,
            "target_type": ref.target_type,
            "target_id": ref.target_id,
            "role": ref.studio_role,
            "category": ref.category,
            "canonical": ref.canonical,
            "approval_state": ref.approval_state,
            "source_kind": ref.source_kind,
            "kind": ref.kind,
        }
        for ref in contract.references
    ]
    with pytest.raises(ValueError, match="do not match the creative manifest"):
        _create_router_contract_for_integrity_test(
            storage,
            source,
            manifest=manifest,
            contract_record=contract.to_record(),
            frozen_binding=frozen_binding,
        )


def test_render_service_refuses_to_synthesize_missing_router_contract(monkeypatch):
    from app.services.render import RenderService

    monkeypatch.setattr("app.services.render._storage", None)
    service = RenderService()
    with pytest.raises(ValueError, match="require a frozen contract"):
        service.create_job(
            project_id="project-contract-test",
            shot_id="scene_001_shot_001",
            provider="runway_router",
            prompt="Mutable prompt must never be frozen here",
            reference_assets=["https://cdn.example.test/mutable.png"],
            parameters={"duration": 5},
        )


@pytest.mark.parametrize("execution_field", ["provider", "model", "cost", "generation_context_id", "execution_metadata"])
def test_manifest_fingerprint_excludes_execution_fields(execution_field):
    job = _job_with_frozen_contract()
    manifest = copy.deepcopy(job.metadata["creative_generation_manifest"])
    original_fingerprint = recompute_manifest_fingerprint(manifest)
    manifest["shots"][0][execution_field] = {"value": "execution-only"}
    manifest["manifest_fingerprint"] = original_fingerprint
    assert recompute_manifest_fingerprint(manifest) == original_fingerprint


def test_manifest_contract_digest_is_fingerprinted_and_reproducible():
    job = _job_with_frozen_contract()
    manifest = job.metadata["creative_generation_manifest"]
    assert recompute_manifest_fingerprint(manifest) == manifest["manifest_fingerprint"]
    assert manifest["shots"][0]["generation_contract_digest"] == job.metadata["creative_contract_digest"]


def test_router_fails_closed_on_unsupported_studio_reference_role(monkeypatch):
    calls = []
    job = _job_with_frozen_contract()
    contract = freeze_generation_contract(
        shot_id=job.shot_id,
        prompt="approved",
        reference_assets=[{"uri": "https://cdn.test/wardrobe.png", "studio_role": "wardrobe"}],
        parameters={
            "camera_plan": {"camera": "Hold"},
            "camera_provenance": "USER_SPECIFIED",
            "camera_source_project_id": job.project_id,
            "camera_source_scene_id": "scene_001",
            "camera_source_shot_id": job.shot_id,
            "camera_target_project_id": job.project_id,
            "camera_target_scene_id": "scene_001",
            "camera_target_shot_id": job.shot_id,
        },
    )
    manifest = build_shot_manifest(
        project_id=job.project_id,
        scene_id="scene_001",
        scene=None,
        scene_version="test-scene-v1",
        storyboard_version="test-board-v1",
        entries=[{
            "shot_id": job.shot_id,
            "prompt": contract.prompt,                "negative_prompt": contract.negative_prompt,
                "shot_duration_seconds": contract.duration or 0,
                "audio_intent": contract.audio,
                "aspect_ratio": contract.aspect_ratio,
                "resolution": contract.resolution,
                "seed": contract.seed,
                "camera_plan": {"camera": "Hold"},
                "camera_provenance": contract.camera_provenance,
                "camera_instructions": __import__("json").loads(contract.camera_instructions_json),
                "camera_source_digest": contract.camera_source_digest,
                "camera_source_project_id": contract.camera_source_project_id,
                "camera_source_scene_id": contract.camera_source_scene_id,
                "camera_source_shot_id": contract.camera_source_shot_id,
                "camera_source_storyboard_shot_id": contract.camera_source_storyboard_shot_id,
                "camera_target_project_id": contract.camera_target_project_id,
                "camera_target_scene_id": contract.camera_target_scene_id,
                "camera_target_shot_id": contract.camera_target_shot_id,
                "parameters": {},
                "generation_contract_digest": contract.creative_digest(),
                "references": [reference.uri for reference in contract.references],
                "reference_roles": [reference.studio_role for reference in contract.references],

        }],
    )
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    record = contract.to_record()
    job.metadata.update(
        creative_generation_contract=record,
        creative_manifest_fingerprint=manifest["manifest_fingerprint"],
        creative_contract_digest=contract.creative_digest(),
        creative_generation_manifest=manifest,
        creative_generation_identity={
            "job_id": job.id,
            "project_id": job.project_id,
            "shot_id": job.shot_id,
            "provider": "runway_router",
        },
    )

    def capture(*args, **kwargs):
        calls.append(args)
        raise AssertionError("unsupported creative role must fail before provider call")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    assert result.metadata["router_execution"]["reason"] == "frozen_scene_coverage_invalid"
    assert calls == []


def test_config_slug_is_not_router_resource_uuid(monkeypatch):
    monkeypatch.delenv("RUNWAY_ROUTER_CONFIG_ID", raising=False)
    assert get_router_config_id() == DEFAULT_ROUTER_CONFIG_ID == "studio-production-router"
    request = build_runway_router_video_request("approved")
    assert request["configId"] == "studio-production-router"
    assert "138f4c50-3411-4aee-88a9-91dd56b90987" not in repr(request)


@pytest.mark.parametrize("quote", [None, -1, float("nan"), float("inf"), True, "20"])
def test_router_invalid_or_unknown_quotes_make_zero_live_calls(monkeypatch, quote):
    calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "0")
    job = _job_with_frozen_contract()

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        return {
            "dryRun": True,
            "routing": {
                "model": "gen4.5",
                "provider": "runway",
                "configId": "studio-production-router",
                "estimatedCost": {"credits": quote} if quote is not None else {},
            },
        }

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    assert len(calls) == 1
    assert calls[0][0] == "POST" and calls[0][1]["dryRun"] is True
    assert not any(method == "POST" and not payload.get("dryRun") for method, payload in calls)


def test_router_live_submission_occurs_once_after_advisory_estimate_and_local_gate(monkeypatch):
    calls = []
    gate_calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "50")
    job = _job_with_frozen_contract()

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 20},
                },
            }
        if method == "POST":
            return {
                "dryRun": False,
                "id": "task-id",
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 20},
                },
            }
        return {"id": "task-id", "status": "SUCCEEDED", "output": ["https://cdn.test/out.mp4"]}

    from app.services.generation_cost_gate import generation_cost_gate
    original_enforce = generation_cost_gate.enforce_shot_limit

    def record_gate(*args, **kwargs):
        gate_calls.append(kwargs.get("router_estimated_cost"))
        assert kwargs["router_provider_ceiling_configured"] is False
        return original_enforce(*args, **kwargs)

    monkeypatch.setattr(generation_cost_gate, "enforce_shot_limit", record_gate)
    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    monkeypatch.setattr("app.services.providers.runway_router_provider.time.sleep", lambda *_: None)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "complete", result.error_message
    assert result.metadata["router_execution"]["estimated_cost_semantics"] == "ADVISORY_ESTIMATE"
    assert result.metadata["router_execution"]["quote_authorization_supported"] is False
    assert result.metadata["router_execution"]["provider_cost_capabilities"] == {
        "ADVISORY_ESTIMATE": True,
        "PROVIDER_ENFORCED_MAXIMUM": False,
        "QUOTE_AUTHORIZATION": False,
    }
    assert result.metadata["router_execution"]["decision_semantics"] == (
        "Runway dry-run estimated this request at approximately 20 credits; "
        "Studio policy permits submission under configured local controls; "
        "Runway independently applies its provider-side limits."
    )
    assert gate_calls == [20.0]
    assert len([call for call in calls if call[0] == "POST" and call[1].get("dryRun")]) == 1
    assert len([call for call in calls if call[0] == "POST" and not call[1].get("dryRun")]) == 1


def test_router_over_cap_quote_makes_zero_live_calls(monkeypatch):
    calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "10")
    job = _job_with_frozen_contract()

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 20},
                },
            }
        raise AssertionError("over-cap quote must not result in a live request")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    assert len(calls) == 1 and calls[0][1]["dryRun"] is True


def test_cost_gate_distinguishes_known_under_over_and_unknown(monkeypatch):
    from app.services.generation_cost_gate import runway_router_cost_capabilities

    assert runway_router_cost_capabilities(provider_ceiling_configured=False) == {
        "ADVISORY_ESTIMATE": True,
        "PROVIDER_ENFORCED_MAXIMUM": False,
        "QUOTE_AUTHORIZATION": False,
    }
    assert runway_router_cost_capabilities(
        provider_ceiling_configured=False, provider_ceiling_supported=False
    ) == {
        "ADVISORY_ESTIMATE": True,
        "PROVIDER_ENFORCED_MAXIMUM": False,
        "QUOTE_AUTHORIZATION": False,
    }
    assert runway_router_cost_capabilities(provider_ceiling_configured=True) == {
        "ADVISORY_ESTIMATE": True,
        "PROVIDER_ENFORCED_MAXIMUM": True,
        "QUOTE_AUTHORIZATION": False,
    }
    gate = GenerationCostGate()
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "50")
    result = gate.enforce_shot_limit(
        "p", "runway_router", {}, router_estimated_cost=49, router_cost_known=True,
        router_provider_ceiling_configured=True, router_provider_ceiling_supported=True,
    )
    assert result["estimated_credits"] == 49
    assert result["estimated_cost_semantics"] == "ADVISORY_ESTIMATE"
    assert result["model"] is None
    assert result["quote_authorization_supported"] is False
    assert result["provider_cost_capabilities"] == {
        "ADVISORY_ESTIMATE": True,
        "PROVIDER_ENFORCED_MAXIMUM": True,
        "QUOTE_AUTHORIZATION": False,
    }
    with pytest.raises(ValidationError, match="exceeds the per-generation limit"):
        gate.enforce_shot_limit("p", "runway_router", {}, router_estimated_cost=51, router_cost_known=True)
    with pytest.raises(ValidationError, match="no estimated cost"):
        gate.enforce_shot_limit("p", "runway_router", {}, router_cost_known=False)


def test_router_cost_gate_enforces_daily_budget_against_persisted_spend(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / "daily-budget-gate"))
    monkeypatch.setattr("app.services.render._storage", storage)
    storage.save_job(RenderJobModel(
        id="existing-spend-job",
        project_id="project-daily-cap",
        shot_id="scene_001_shot_001",
        provider="simulated",
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={"estimated_cost_credits": 40},
    ))
    gate = GenerationCostGate(renderer=RenderService())
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "50")
    assert gate.enforce_shot_limit(
        "project-daily-cap", "runway_router", {}, router_estimated_cost=10, router_cost_known=True,
    )["estimated_credits"] == 10
    with pytest.raises(ValidationError, match="exceeds the daily budget") as exc:
        gate.enforce_shot_limit(
            "project-daily-cap", "runway_router", {}, router_estimated_cost=11, router_cost_known=True,
            router_provider_ceiling_configured=True,
            router_provider_ceiling_supported=True,
        )
    assert exc.value.metadata["provider_cost_capabilities"]["PROVIDER_ENFORCED_MAXIMUM"] is True
    assert "daily_spent_credits" not in exc.value.metadata["provider_cost_capabilities"]
    assert exc.value.metadata["daily_spent_credits"] == 40
    assert exc.value.metadata["projected_daily_credits"] == 51


def test_router_cost_gate_distinguishes_successful_zero_spend_from_unavailable_history(tmp_path, monkeypatch):
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / "empty-daily-history"))
    monkeypatch.setattr("app.services.render._storage", storage)
    gate = GenerationCostGate(renderer=RenderService())
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "50")
    quote = gate.enforce_shot_limit(
        "project-daily-cap", "runway_router", {},
        router_estimated_cost=10, router_cost_known=True,
    )
    assert quote["estimated_credits"] == 10
    assert quote["estimated_cost_semantics"] == "ADVISORY_ESTIMATE"
    assert quote["model"] is None


def test_daily_cap_blocks_when_persisted_history_reader_fails_before_live_request(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "50")
    job = _job_with_frozen_contract()

    storage = DatabaseStorage(str(tmp_path / "daily-history-read-failure"))
    monkeypatch.setattr("app.services.render._storage", storage)
    monkeypatch.setattr(
        storage,
        "list_jobs_page",
        lambda **kwargs: (_ for _ in ()).throw(OSError("isolated storage read failure")),
    )
    from app.services.generation_cost_gate import generation_cost_gate
    from app.services.render import RenderService
    monkeypatch.setattr(generation_cost_gate, "_renderer", RenderService())

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 10},
                },
            }
        raise AssertionError("history read failure must prevent a live Router request")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    assert result.metadata["router_execution"]["cost_gate"]["cost_status"] == "history_unavailable"
    assert result.metadata["router_execution"]["cost_gate"]["history_error"] == "storage_read_failed"
    assert len(calls) == 1 and calls[0][1]["dryRun"] is True
    assert not any(method == "POST" and not payload.get("dryRun") for method, payload in calls)


def test_daily_cap_blocks_when_persisted_history_reader_is_missing(monkeypatch):
    gate = GenerationCostGate()
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "50")
    with pytest.raises(ValidationError, match="persisted render-history reader is unavailable") as exc:
        gate.enforce_shot_limit(
            "project-daily-cap", "runway_router", {},
            router_estimated_cost=10, router_cost_known=True,
        )
    assert exc.value.metadata["cost_status"] == "history_unavailable"
    assert exc.value.metadata["history_error"] == "reader_unavailable"


def test_router_adapter_daily_over_cap_quote_makes_zero_live_calls(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "50")
    job = _job_with_frozen_contract()

    storage = DatabaseStorage(str(tmp_path / "daily-budget-adapter"))
    monkeypatch.setattr("app.services.render._storage", storage)
    storage.save_job(RenderJobModel(
        id="existing-spend-job",
        project_id=job.project_id,
        shot_id="scene_001_shot_001",
        provider="simulated",
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={"estimated_cost_credits": 40},
    ))

    from app.services.generation_cost_gate import generation_cost_gate
    from app.services.render import RenderService
    monkeypatch.setattr(generation_cost_gate, "_renderer", RenderService())

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 11},
                },
            }
        raise AssertionError("daily over-cap quote must not result in a live request")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    assert len(calls) == 1 and calls[0][1]["dryRun"] is True
    assert result.metadata["router_execution"]["cost_gate"]["daily_spent_credits"] == 40


def _save_cost_history_job(storage, *, job_id: str, project_id: str, metadata: dict) -> None:
    from datetime import datetime, timezone

    storage.save_job(RenderJobModel(
        id=job_id,
        project_id=project_id,
        shot_id=f"{job_id}-shot",
        provider="simulated",
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata=metadata,
    ))


def test_persisted_fractional_router_estimate_is_preserved_in_daily_history(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from app.services.generation_cost_gate import generation_cost_gate
    from app.services.render import RenderService

    calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "10")
    storage = DatabaseStorage(str(tmp_path / "fractional-history"))
    monkeypatch.setattr("app.services.render._storage", storage)
    monkeypatch.setattr(generation_cost_gate, "_renderer", RenderService())
    job = _job_with_frozen_contract()
    job.created_at = datetime.now(timezone.utc).isoformat()

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if method == "POST" and payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 0.5},
                },
            }
        if method == "POST":
            return {
                "dryRun": False,
                "id": "fractional-task-id",
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 0.5},
                },
            }
        return {
            "id": "fractional-task-id",
            "status": "SUCCEEDED",
            "output": ["https://cdn.test/fractional.mp4"],
        }

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    monkeypatch.setattr("app.services.providers.runway_router_provider.time.sleep", lambda *_: None)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "complete", result.error_message
    assert result.metadata["router_execution"]["estimated_cost_credits"] == 0.5
    storage.save_job(result)

    reloaded = storage.get_job(result.id)
    assert reloaded is not None
    assert reloaded.metadata["router_execution"]["estimated_cost_credits"] == 0.5
    spent = GenerationCostGate(renderer=RenderService())._daily_spent_credits(job.project_id)
    assert spent == Decimal("0.5")
    assert len([1 for method, payload in calls if method == "POST" and payload.get("dryRun")]) == 1
    assert len([1 for method, payload in calls if method == "POST" and not payload.get("dryRun")]) == 1


def test_fractional_history_accumulates_exactly_at_and_above_daily_cap(tmp_path, monkeypatch):
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / "fractional-accumulation"))
    monkeypatch.setattr("app.services.render._storage", storage)
    _save_cost_history_job(
        storage, job_id="fractional-history-a", project_id="fractional-project",
        metadata={"estimated_cost_credits": 0.1},
    )
    _save_cost_history_job(
        storage, job_id="fractional-history-b", project_id="fractional-project",
        metadata={"estimated_cost_credits": 0.2},
    )
    gate = GenerationCostGate(renderer=RenderService())
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "1")

    assert gate._daily_spent_credits("fractional-project") == Decimal("0.3")
    allowed = gate.enforce_shot_limit(
        "fractional-project", "runway_router", {}, router_estimated_cost=0.7, router_cost_known=True,
    )
    assert allowed["estimated_credits"] == 0.7
    with pytest.raises(ValidationError, match="exceeds the daily budget") as exc:
        gate.enforce_shot_limit(
            "fractional-project", "runway_router", {},
            router_estimated_cost=0.7001, router_cost_known=True,
        )
    assert exc.value.metadata["daily_spent_credits"] == 0.3
    assert exc.value.metadata["projected_daily_credits"] == 1.0001


def test_fractional_history_cannot_be_truncated_to_bypass_router_daily_cap(tmp_path, monkeypatch):
    from app.services.render import RenderService

    calls = []
    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", "50")
    job = _job_with_frozen_contract()
    storage = DatabaseStorage(str(tmp_path / "fractional-router-daily-cap"))
    monkeypatch.setattr("app.services.render._storage", storage)
    _save_cost_history_job(
        storage,
        job_id="fractional-over-cap-history",
        project_id=job.project_id,
        metadata={"router_execution": {"estimated_cost_credits": 49.75}},
    )
    from app.services.generation_cost_gate import generation_cost_gate
    from app.services.render import RenderService
    monkeypatch.setattr(generation_cost_gate, "_renderer", RenderService())

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, payload))
        if payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5",
                    "provider": "runway",
                    "configId": "studio-production-router",
                    "estimatedCost": {"credits": 0.5},
                },
            }
        raise AssertionError("fractional daily over-cap cost must block live Router HTTP")

    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)
    result = _submit_authorized(monkeypatch, job)
    assert result.status == "failed"
    assert result.metadata["router_execution"]["cost_gate"]["daily_spent_credits"] == 49.75
    assert result.metadata["router_execution"]["cost_gate"]["projected_daily_credits"] == 50.25
    assert len(calls) == 1 and calls[0][1]["dryRun"] is True
    assert not any(method == "POST" and not payload.get("dryRun") for method, payload in calls)


@pytest.mark.parametrize("estimate", [None, True, "not-a-cost", float("nan")])
def test_invalid_persisted_cost_estimates_fail_closed(tmp_path, monkeypatch, estimate):
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / f"invalid-cost-{str(estimate)}"))
    monkeypatch.setattr("app.services.render._storage", storage)
    _save_cost_history_job(
        storage,
        job_id="invalid-cost-history",
        project_id="invalid-cost-project",
        metadata={"estimated_cost_credits": estimate},
    )
    gate = GenerationCostGate(renderer=RenderService())
    with pytest.raises(RuntimeError, match="no usable cost estimate|invalid cost estimate"):
        gate._daily_spent_credits("invalid-cost-project")


def test_router_resolution_and_quote_are_not_frozen_creative_values():
    contract = freeze_generation_contract(
        shot_id="s1",
        prompt="approved",
        parameters={
            "resolved_model": "some-model",
            "estimated_cost_credits": 500,
            "router_config_id": "some-config",
            "provider_job_id": "task-123",
        },
    )
    payload = contract.to_record()["payload"]
    assert "resolved_model" not in str(payload)
    assert "estimated_cost_credits" not in str(payload)
    assert "router_config_id" not in str(payload)
    assert "task-123" not in str(payload)
