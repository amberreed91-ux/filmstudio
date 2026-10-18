"""Focused regression tests: the production Runway Router adapter path invokes
the existing ``runway_reference_projection/v1`` policy (Phase B.9).

Non-generative: no rendering, no preflight, no continuity review, no Runway
upload, no provider request, no credits. Every network boundary is a test
double, and the fail-closed tests assert zero provider contact.

The reference identities mirror the creator's Scene 002 authorization:
SELECT ``ref_set_99caf0f5fd1a471eb3c89d4fb9cac11c`` and REJECT
``ref_set_0ac27f51f04d4bc982fc75c8ad87371e`` /
``ref_set_ef979b6074b942ccb2740d70b95223cb``.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import replace

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services import runway_reference_projection as projection
from app.services.generation_contract import (
    FrozenGenerationContract,
    freeze_dialogue_handoff,
    freeze_generation_contract,
)
from app.services.reference_validation import frozen_reference_payload
from app.services.providers import runway_router_provider
from app.services.shot_manifest import build_shot_manifest, recompute_manifest_fingerprint

AUTHORIZED_ENV = "ref_set_99caf0f5fd1a471eb3c89d4fb9cac11c"
REJECTED_ENV_A = "ref_set_0ac27f51f04d4bc982fc75c8ad87371e"
REJECTED_ENV_B = "ref_set_ef979b6074b942ccb2740d70b95223cb"
REJECTED_ENV_IDS = [REJECTED_ENV_A, REJECTED_ENV_B]

DRE_FACE = "ref_look_dre_face"
MAYA_FACE = "ref_look_maya_face"
MAYA_GENERAL = "ref_look_maya_general"
MAYA_ALT = "ref_look_maya_alt"

DRE_ID = "chr_f1425498cb68"
MAYA_ID = "chr_3c9e91741ef3"
SETTING_ID = "loc-c8f88b9c"

SHOT_ID = "scene_001_shot_001"
PROJECT_ID = "project-contract-test"

_ROUTER_AUTHORITY_OWNER = "router-authority-owner"
_ROUTER_AUTHORITY_BOARD_SHOT = "board-shot-authority"


def _bind_router_execution_authority(job: RenderJobModel):
    from types import SimpleNamespace

    owner = _ROUTER_AUTHORITY_OWNER
    manifest = job.metadata["creative_generation_manifest"]
    scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
    scene_id = str(scene.get("scene_id") or "").strip()
    storyboard = manifest.get("storyboard") if isinstance(manifest.get("storyboard"), dict) else {}
    version_id = str(storyboard.get("storyboard_version") or "").strip() or "test-board-v1"
    try:
        contract = FrozenGenerationContract.from_record(job.metadata["creative_generation_contract"])
    except Exception:
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
    contract = FrozenGenerationContract.from_record(job.metadata["creative_generation_contract"])
    canonical_references = [
        reference.to_dict()
        for reference in contract.references
        if reference.source == "canonical_reference_binding"
    ]
    character_ids = list(dict.fromkeys(
        str(row.get("target_id") or "") for row in canonical_references
        if row.get("target_type") == "character"
    ))
    reference_state = {"rows": [
        {
            "ref_id": row.get("ref_id"),
            "project_id": job.project_id,
            "target_type": row.get("target_type"),
            "target_id": row.get("target_id"),
            "kind": row.get("kind"),
            "category": row.get("category"),
            "image_url": row.get("uri"),
            "canonical": row.get("canonical"),
            "approval_state": row.get("approval_state"),
            "source_kind": row.get("source_kind"),
        }
        for row in canonical_references
    ]}
    # Decision A1: the double's live setting rows mirror the job's recorded
    # rejected enumeration, so the adapter's exact-equality check verifies
    # against genuine fixture data (tests that tamper the record afterwards
    # still exercise the mismatch path).
    _record = ((job.metadata or {}).get("reference_projection_authorization") or {})
    if not isinstance(_record, dict):
        _record = {}
    _record_setting = str(_record.get("setting_id") or SETTING_ID)
    for _rejected_id in (_record.get("rejected_environment_ref_ids") or []):
        _rejected_id = str(_rejected_id or "").strip()
        if not _rejected_id:
            continue
        reference_state["rows"].append({
            "ref_id": _rejected_id,
            "project_id": job.project_id,
            "target_type": "setting",
            "target_id": _record_setting,
            "kind": "environment",
            "category": "environment",
            "image_url": f"https://cdn.example.test/rejected/{_rejected_id}.png",
            "canonical": False,
            "approval_state": "rejected",
            "source_kind": "confirmed",
        })
    reference_project = {
        "project_id": job.project_id,
        "execution_summary": {"scenes": [{
            "scene_id": scene_id,
            "heading": "INT. TEST ROOM - DAY",
            "setting_id": SETTING_ID,
            "character_ids": character_ids,
        }]},
    }
    storage = SimpleNamespace(
        get_job=lambda job_id: durable.model_copy(deep=True) if job_id == job.id else None,
        access_project_owner=lambda project_id: owner if project_id == job.project_id else None,
        get_project=lambda project_id: {} if project_id == job.project_id else None,
        get_storyboard_blueprint=lambda project_id, scene_id: blueprint,
        get_storyboard_blueprint_version=lambda version_id_: version if version_id_ == version_id else None,
        get_storyboard_shot=lambda shot_id: shot if shot_id == _ROUTER_AUTHORITY_BOARD_SHOT else None,
        get_character=lambda character_id, project_id: (
            {"id": character_id, "name": character_id, "project_id": project_id}
            if project_id == job.project_id and character_id in character_ids else None
        ),
        get_universe_nodes=lambda project_id: ([{
            "node_id": SETTING_ID, "project_id": project_id, "node_type": "location",
            "name": "Test Room", "first_scene": scene_id, "last_scene": scene_id,
        }] if project_id == job.project_id else []),
        list_reference_assets=lambda **kwargs: [
            row for row in reference_state["rows"]
            if row.get("project_id") == kwargs.get("project_id")
            and (not kwargs.get("target_type") or row.get("target_type") == kwargs["target_type"])
            and (not kwargs.get("target_id") or row.get("target_id") == kwargs["target_id"])
        ][:kwargs.get("limit", 50)],
        reference_state=reference_state,
        reference_project=reference_project,
    )
    return storage

ENV_HTTPS = "https://cdn.example.test/scene002/env.png"


def _row(ref_id, uri, target_type, target_id, studio_role, kind, **overrides):
    row = {
        "ref_id": ref_id,
        "uri": uri,
        "target_type": target_type,
        "target_id": target_id,
        "role": "reference",
        "category": studio_role,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": kind,
        "studio_role": studio_role,
        "source": "canonical_reference_binding",
    }
    row.update(overrides)
    return row


def _canonical_five(*, env_ref_id: str = AUTHORIZED_ENV, env_uri: str = ENV_HTTPS,
                    env_overrides: dict | None = None) -> list[dict]:
    """The frozen Scene 002 canonical five, in canonical order."""
    return [
        _row(DRE_FACE, "https://cdn.example.test/scene002/dre-face.png", "character", DRE_ID, "face", "character_face"),
        _row(MAYA_FACE, "https://cdn.example.test/scene002/maya-face.png", "character", MAYA_ID, "face", "character_face"),
        _row(MAYA_GENERAL, "https://cdn.example.test/scene002/maya-general.png", "character", MAYA_ID, "general", "character_full"),
        _row(MAYA_ALT, "https://cdn.example.test/scene002/maya-alt.png", "character", MAYA_ID, "alternate_angle", "character_full"),
        _row(env_ref_id, env_uri, "setting", SETTING_ID, "environment", "environment", **(env_overrides or {})),
    ]


def _authorization() -> dict:
    return {
        "authorized_environment_ref_id": AUTHORIZED_ENV,
        "rejected_environment_ref_ids": list(REJECTED_ENV_IDS),
    }


def _build_job(rows: list[dict], *, authorization=None, projection_record=None) -> RenderJobModel:
    """Build a valid synthetic Router job carrying the given frozen references."""
    from app.services.camera_provenance import camera_plan_digest, canonical_camera_instructions
    from app.services.scene_coverage_contract import build_scene_coverage_contract

    prompt = "Approved Scene 002 prompt bytes: keep the exact punctuation!"
    camera_plan = {"camera": "Hold", "framing": "Wide"}
    camera_parameters = {
        "camera_plan": camera_plan,
        "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": PROJECT_ID,
        "camera_source_scene_id": "scene_001",
        "camera_source_shot_id": SHOT_ID,
        "camera_target_project_id": PROJECT_ID,
        "camera_target_scene_id": "scene_001",
        "camera_target_shot_id": SHOT_ID,
        "reference_roles": [row["studio_role"] for row in rows],
    }
    camera_parameters["camera_source_digest"] = camera_plan_digest(
        camera_plan, "USER_SPECIFIED", source_project_id=PROJECT_ID,
        source_scene_id="scene_001", source_shot_id=SHOT_ID,
    )
    camera_parameters["camera_instructions"] = canonical_camera_instructions(camera_plan, "USER_SPECIFIED")
    scene_text = "INT. TEST ROOM - DAY\nA single lamp glows beside a closed book."
    project = {"project_id": PROJECT_ID, "script_text": scene_text,
               "execution_summary": {"scenes": [], "dialogue_lines": []}}
    scene = {"scene_id": "scene_001", "heading": "INT. TEST ROOM - DAY",
             "text": scene_text, "setting_id": SETTING_ID}
    shot = {
        "shot_id": SHOT_ID, "scene_id": "scene_001", "shot_number": 1,
        "parameters": {
            **camera_parameters,
            "dialogue_disposition": "INTENTIONAL_SILENCE",
            "dialogue_disposition_reason": "The approved shot contains no spoken dialogue.",
        },
        "dialogue_disposition": "INTENTIONAL_SILENCE",
        "dialogue_disposition_reason": "The approved shot contains no spoken dialogue.",
    }
    requirements = {
        "setting_id": SETTING_ID,
        "characters": {DRE_ID: {"name": "DRE"}, MAYA_ID: {"name": "MAYA"}},
        "reference_binding": rows,
    }
    coverage_probe, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID, project=project, scene=scene,
        shots=[shot], reference_requirements=requirements,
    )
    creator_decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"],
         "status": "ASSIGNED", "shot_id": SHOT_ID, "reason": ""}
        for row in coverage_probe["content_units"]
    ]
    creator_decisions.extend([
        {"obligation_type": "shot_content", "obligation_id": SHOT_ID,
         "status": "UNRESOLVED", "shot_id": None, "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": SHOT_ID,
         "status": "INTENTIONAL_SILENCE",
         "reason": "The approved shot contains no spoken dialogue."},
    ])
    coverage, coverage_blockers, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID, project=project, scene=scene,
        shots=[shot], reference_requirements=requirements,
        creator_decisions=creator_decisions,
    )
    assert not coverage_blockers, coverage_blockers
    shot_coverage = coverage["shots"][0]
    canonical_role_by_id = {row["ref_id"]: row["studio_role"] for row in rows}
    references = [
        {**row, "role": "reference",
         "studio_role": canonical_role_by_id.get(row["ref_id"], row.get("category") or "reference"),
         "source": "canonical_reference_binding"}
        for row in shot_coverage["approved_reference_bindings"]
    ]
    dialogue_handoff = freeze_dialogue_handoff(scene_id="scene_001", shot_id=SHOT_ID, lines=[])
    contract = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt=prompt,
        negative_prompt="No extra people.",
        reference_assets=references,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
        dialogue_handoff=dialogue_handoff,
        parameters={
            "duration": 5,
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "seed": 43,
            "audio_intent": "generate",
            "content_moderation": "standard",
            **camera_parameters,
        },
    )
    manifest = build_shot_manifest(
        project_id=PROJECT_ID,
        scene_id="scene_001",
        scene=None,
        scene_version="test-scene-v1",
        storyboard_version="board-v1" if authorization is not None else "test-board-v1",
        scene_lineage=coverage,
        entries=[{
            "shot_id": SHOT_ID,
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
                    **(({"kind": ref.kind}) if ref.kind else {}),
                }
                for ref in contract.references
            ],
            "generation_contract_digest": contract.creative_digest(),
            "aspect_ratio": contract.aspect_ratio,
            "resolution": contract.resolution,
            "seed": contract.seed,
            "references": [ref.uri for ref in contract.references],
            "camera_plan": json.loads(contract.camera_plan_json),
            "camera_provenance": contract.camera_provenance,
            "camera_instructions": json.loads(contract.camera_instructions_json),
            "camera_source_digest": contract.camera_source_digest,
            "camera_source_project_id": contract.camera_source_project_id,
            "camera_source_scene_id": contract.camera_source_scene_id,
            "camera_source_shot_id": contract.camera_source_shot_id,
            "camera_source_storyboard_shot_id": contract.camera_source_storyboard_shot_id,
            "camera_target_project_id": contract.camera_target_project_id,
            "camera_target_scene_id": contract.camera_target_scene_id,
            "camera_target_shot_id": contract.camera_target_shot_id,
            "parameters": json.loads(contract.creative_parameters_json),
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
        {key: ref.get(key) for key in (
            "ref_id", "uri", "target_type", "target_id", "role", "category",
            "canonical", "approval_state", "source_kind", "kind",
        ) if key in ref}
        for ref in manifest["shots"][0]["reference_binding"]
    ]
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
    record = contract.to_record()
    metadata: dict = {
        "creative_generation_contract": record,
        "creative_generation_manifest": manifest,
        "creative_manifest_fingerprint": manifest["manifest_fingerprint"],
        "creative_contract_digest": contract.creative_digest(),
        "creative_generation_identity": {
            "job_id": "job-contract-test",
            "project_id": PROJECT_ID,
            "shot_id": SHOT_ID,
            "provider": "runway_router",
        },
    }
    if projection_record is not None:
        metadata[projection.PROJECTION_METADATA_KEY] = projection_record
    if authorization is not None:
        if isinstance(authorization, dict) and authorization.get("authorized_environment_ref_id") == AUTHORIZED_ENV and "authorization_policy_id" not in authorization:
            binding = [dict(row) for row in rows]
            for row in binding:
                row["project_id"] = PROJECT_ID
                row["role"] = row.get("studio_role") or row.get("role")
            binding_digest = hashlib.sha256(
                json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            authorization_record = {
                **authorization,
                "authorization_policy_id": projection.AUTHORIZATION_POLICY_ID,
                "project_id": PROJECT_ID,
                "scene_id": "scene_001",
                "setting_id": SETTING_ID,
                "current_version_id": "board-v1",
                "approved_version_id": "board-v1",
                "storyboard_version_id": "board-v1",
                "frozen_reference_binding": binding,
                "frozen_reference_binding_sha256": binding_digest,
                "source_fingerprint": hashlib.sha256(str(rows[-1]["uri"]).encode("utf-8")).hexdigest(),
            }
            metadata[projection.AUTHORIZATION_METADATA_KEY] = authorization_record
            metadata["frozen_reference_binding"] = copy.deepcopy(binding)
            metadata["frozen_reference_binding_sha256"] = binding_digest
            metadata["creative_generation_identity"]["project_id"] = PROJECT_ID
        else:
            metadata[projection.AUTHORIZATION_METADATA_KEY] = authorization
    return RenderJobModel(
        id="job-contract-test",
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        provider="runway_router",
        status="pending",
        input_payload=RenderJobInput(
            shot_id=SHOT_ID,
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
                    {
                        "ref_id": ref.ref_id, "uri": ref.uri, "target_type": ref.target_type,
                        "target_id": ref.target_id, "role": ref.studio_role, "category": ref.category,
                        "canonical": ref.canonical, "approval_state": ref.approval_state,
                        "source_kind": ref.source_kind, "kind": ref.kind,
                        "studio_role": ref.studio_role, "source": ref.source,
                    }
                    for ref in contract.references
                ],
                "consistency_payload": frozen_reference_payload(
                    [
                        {
                            "ref_id": ref.ref_id, "uri": ref.uri, "target_type": ref.target_type,
                            "target_id": ref.target_id, "role": ref.studio_role, "category": ref.category,
                            "canonical": ref.canonical, "approval_state": ref.approval_state,
                            "source_kind": ref.source_kind, "kind": ref.kind,
                        }
                        for ref in contract.references
                        if ref.source == "canonical_reference_binding"
                    ],
                    project_id=PROJECT_ID,
                ),
                "scene_coverage": coverage,
                "scene_coverage_shot": shot_coverage,
                "dialogue_lines": contract.payload().get("dialogue_handoff", {}).get("payload", {}).get("lines", []),
                "dialogue_handoff": contract.payload().get("dialogue_handoff", {}),
            },
            consistency_payload=frozen_reference_payload(
                [
                    {
                        "ref_id": ref.ref_id, "uri": ref.uri, "target_type": ref.target_type,
                        "target_id": ref.target_id, "role": ref.studio_role, "category": ref.category,
                        "canonical": ref.canonical, "approval_state": ref.approval_state,
                        "source_kind": ref.source_kind, "kind": ref.kind,
                    }
                    for ref in contract.references
                    if ref.source == "canonical_reference_binding"
                ],
                project_id=PROJECT_ID,
            ),
        ),
        metadata=metadata,
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


@pytest.fixture()
def provider_calls(monkeypatch):
    """Injected Router transport double; records every attempted provider call."""
    calls: list[tuple[str, dict]] = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, copy.deepcopy(payload)))
        if method == "POST" and payload and payload.get("dryRun"):
            return {"dryRun": True, "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": runway_router_provider.get_router_config_id(),
                "estimatedCost": {"credits": 20},
            }}
        if method == "POST":
            return {"dryRun": False, "id": "task-local", "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": runway_router_provider.get_router_config_id(),
                "estimatedCost": {"credits": 20},
            }}
        return {"id": "task-local", "status": "SUCCEEDED", "output": ["https://cdn.test/out.mp4"]}

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)
    monkeypatch.setattr(runway_router_provider.time, "sleep", lambda *_: None)
    return calls


def _submit(job: RenderJobModel) -> RenderJobModel:
    from unittest.mock import patch
    from app.services import reference_validation

    storage = _bind_router_execution_authority(job)
    with patch("app.data.storage.get_storage", return_value=storage), patch.object(
        reference_validation.project_store, "get_project", return_value=storage.reference_project,
    ):
        return asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(
            job, authority_storage=storage, reference_storage=storage,
        ))


def _reason(job: RenderJobModel) -> str:
    return str((job.metadata or {}).get("router_execution", {}).get("reason") or "")


def _projection_gate(rows: list[dict], authorization):
    """Call the adapter's declared-projection gate directly.

    An unapproved or ambiguous environment binding cannot survive the scene
    coverage builder, so this exercises the exact code the submit path calls
    with a frozen contract built without scene coverage.
    """
    contract = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved prompt bytes.",
        reference_assets=[dict(row) for row in rows],
        parameters={"duration": 5, "aspect_ratio": "16:9"},
    )
    adapter = RunwayRouterAdapter(_provider_config())
    binding = [dict(row) for row in rows]
    for row in binding:
        row["project_id"] = PROJECT_ID
        row["role"] = row.get("studio_role") or row.get("role")
    authorization_record = {
        **_authorization(),
        "project_id": PROJECT_ID,
        "scene_id": "scene_001",
        "setting_id": SETTING_ID,
        "current_version_id": "board-v1",
        "approved_version_id": "board-v1",
        "storyboard_version_id": "board-v1",
        "authorization_policy_id": projection.AUTHORIZATION_POLICY_ID,
        "frozen_reference_binding": binding,
        "frozen_reference_binding_sha256": hashlib.sha256(
            json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "source_fingerprint": hashlib.sha256(str(rows[-1]["uri"]).encode("utf-8")).hexdigest(),
    }
    metadata = {
        projection.AUTHORIZATION_METADATA_KEY: authorization_record,
        "frozen_reference_binding": binding,
        "creative_generation_identity": {"project_id": PROJECT_ID},
    }
    result = adapter._declared_reference_projection(
        metadata=metadata,
        contract_record=contract.to_record(),
        manifest_record={
            "manifest_fingerprint": "manifest-fingerprint",
            "scene": {"scene_id": "scene_001"},
            "storyboard": {"storyboard_version_scene_id": "scene_001", "storyboard_version": "board-v1"},
        },
        router_config_id="studio-production-router",
        context_refs=[],
    )
    if result[0]:
        return (*result[:4], {})
    return result



# ── Authorized projection reaches the provider ──────────────────────────────

def test_declared_projection_uses_authorized_environment_and_preserves_everything(provider_calls, monkeypatch, tmp_path):
    rows = _canonical_five()
    job = _build_job(rows, authorization=_authorization())
    # Authority binding is part of the test baseline: the execution boundary
    # must leave these exact authorized proofs untouched.
    reference_storage = _bind_router_execution_authority(job)
    frozen_before = copy.deepcopy(job.metadata["creative_generation_contract"])
    manifest_before = copy.deepcopy(job.metadata["creative_generation_manifest"])
    input_before = json.loads(job.input_payload.model_dump_json())

    from unittest.mock import patch
    from app.services import reference_validation

    with patch("app.data.storage.get_storage", return_value=reference_storage), patch.object(
        reference_validation.project_store, "get_project", return_value=reference_storage.reference_project,
    ):
        result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(
            job, authority_storage=reference_storage, reference_storage=reference_storage,
        ))

    assert result.status == "complete", result.error_message
    live_posts = [payload for method, payload in provider_calls if method == "POST" and not payload.get("dryRun")]
    assert len(live_posts) == 1
    body = live_posts[0]
    # Only the four selected, provider-addressable references are forwarded, in
    # canonical order, all normalized to the provider `reference` role.
    assert body["input"]["referenceImages"] == [
        {"uri": "https://cdn.example.test/scene002/dre-face.png", "role": "reference"},
        {"uri": "https://cdn.example.test/scene002/maya-face.png", "role": "reference"},
        {"uri": "https://cdn.example.test/scene002/maya-general.png", "role": "reference"},
        {"uri": ENV_HTTPS, "role": "reference"},
    ]
    # The omitted MAYA alternate_angle reference never reaches the provider.
    assert all("maya-alt" not in item["uri"] for item in body["input"]["referenceImages"])
    # The frozen prompt is preserved through the same deterministic camera
    # projection the unprojected path uses — never rewritten or truncated.
    contract = FrozenGenerationContract.from_record(frozen_before)
    expected_prompt = runway_router_provider.project_frozen_camera_plan_prompt(
        contract.prompt, json.loads(contract.camera_plan_json)
    )
    assert body["input"]["promptText"] == expected_prompt
    assert contract.prompt in expected_prompt
    # Frozen creative fields and mutable render inputs are untouched.
    assert job.metadata["creative_generation_contract"] == frozen_before
    assert job.metadata["creative_generation_manifest"] == manifest_before
    assert json.loads(job.input_payload.model_dump_json()) == input_before
    assert result.provider_job_id == "task-local"
    assert result.metadata["router_execution"]["runway_task_id"] == result.provider_job_id
    assert result.metadata["router_execution"]["provider_output_identity"] == {
        "provider_task_id": result.provider_job_id,
        "output_url": "https://cdn.test/out.mp4",
        "association_source": "runway_router_polled_task",
    }
    assert result.metadata["router_execution"]["output_identity"] == {
        "render_job_id": result.id,
        "provider_task_id": result.provider_job_id,
        "output_url": "https://cdn.test/out.mp4",
        "association_source": "runway_router_polled_task",
    }
    assert result.output_payload is not None
    normalized_output = result.output_payload.metadata["provider_response_normalized"]["output"]
    normalized_metadata = result.output_payload.metadata["provider_response_normalized"]["metadata"]
    assert normalized_metadata["task_id"] == result.provider_job_id
    assert normalized_metadata["render_job_id"] == result.id
    assert normalized_metadata["runway_output_identity"] == result.metadata["router_execution"]["output_identity"]
    assert result.output_payload.metadata["reference_projection"]["selected_ref_ids"] == [
        DRE_FACE, MAYA_FACE, MAYA_GENERAL, AUTHORIZED_ENV
    ]
    from app.data.storage import DatabaseStorage
    from app.services.render import RenderService
    from app.services.video_asset_service import VideoAssetService
    from unittest.mock import patch

    storage = DatabaseStorage(":memory:")
    storage.save_job(result)
    monkeypatch.setattr("app.services.render._storage", storage)
    with patch("app.services.render._storage", storage):
        service = RenderService()
        service._jobs[result.id] = result
        service._provider_configs["runway_router"] = _provider_config()
        assets = asyncio.run(service.get_job_outputs(result.id))
    assert len(assets) == 1
    asset_record = next(asset for asset in VideoAssetService(storage).list_assets_for_project(result.project_id))

    assert asset_record.source_type == "generated_output"
    assert asset_record.source_url == result.output_payload.asset_url
    assert asset_record.metadata["render_job_id"] == result.id
    assert asset_record.metadata["provider_task_id"] == result.provider_job_id
    assert assets[0].metadata["video_asset_id"] == asset_record.asset_id
    assert (assets[0].job_id, assets[0].project_id, assets[0].shot_id, assets[0].provider) == (
        result.id, result.project_id, result.shot_id, "runway_router"
    )
    assert assets[0].url == result.output_payload.asset_url == "https://cdn.test/out.mp4"


@pytest.mark.parametrize(
    ("tamper", "expected_assets"),
    [
        ("provider_task_id", 0),
        ("render_job_id", 0),
        ("normalized_output_url", 0),
        ("job_output_url", 0),
        ("execution_task_id", 0),
        ("valid", 1),
    ],
)
def test_router_asset_registration_requires_matching_render_task_and_output_identity(
    provider_calls, tamper, expected_assets
):
    job = _submit(_build_job(_canonical_five(), authorization=_authorization()))
    assert job.status == "complete"
    if tamper == "provider_task_id":
        job.output_payload.metadata["provider_response_normalized"]["metadata"]["task_id"] = "foreign-task"
    elif tamper == "render_job_id":
        job.output_payload.metadata["provider_response_normalized"]["metadata"]["render_job_id"] = "foreign-job"
    elif tamper == "normalized_output_url":
        job.output_payload.metadata["provider_response_normalized"]["output"]["video_url"] = "https://cdn.test/foreign.mp4"
    elif tamper == "job_output_url":
        job.output_payload.asset_url = "https://cdn.test/foreign.mp4"
    elif tamper == "execution_task_id":
        job.metadata["router_execution"]["runway_task_id"] = "foreign-task"

    assets = asyncio.run(RunwayRouterAdapter(_provider_config()).fetch_outputs(job))
    assert len(assets) == expected_assets
    if expected_assets:
        assert assets[0].job_id == job.id
        assert assets[0].url == "https://cdn.test/out.mp4"


@pytest.mark.parametrize(
    ("identity", "expected_reason"),
    [
        ({"provider_task_id": "task-without-association", "output_url": "https://cdn.test/out.mp4", "association_source": "runway_router_polled_task"}, None),
        (None, "provider_output_identity_missing"),
        (
            {
                "provider_task_id": "different-task",
                "output_url": "https://cdn.test/out.mp4",
                "association_source": "runway_router_polled_task",
            },
            "provider_output_identity_mismatch",
        ),
        (
            {
                "provider_task_id": "task-without-association",
                "output_url": "https://cdn.test/foreign.mp4",
                "association_source": "runway_router_polled_task",
            },
            "provider_output_identity_mismatch",
        ),
        (
            {
                "provider_task_id": "task-without-association",
                "output_url": "https://cdn.test/out.mp4",
                "association_source": "foreign_source",
            },
            "provider_output_identity_mismatch",
        ),
        (
            {
                "provider_task_id": "task-without-association",
                "output_url": "https://cdn.test/out.mp4",
                "association_source": "runway_router_polled_task",
            },
            None,
        ),
    ],
)
def test_router_task_output_requires_matching_task_and_output_identity(
    monkeypatch, provider_calls, identity, expected_reason
):
    """Only an output bound to the returned task ID and exact URL can complete."""
    job = _build_job(_canonical_five(), authorization=_authorization())
    storage = _bind_router_execution_authority(job)
    from app.services import reference_validation
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    monkeypatch.setattr(reference_validation.project_store, "get_project", lambda _project: storage.reference_project)

    meta = {"runway_task_id": "task-without-association"}
    if identity is not None:
        meta["output_identity"] = identity
    monkeypatch.setattr(
        runway_router_provider,
        "submit_runway_router_video_render",
        lambda *_args, **_kwargs: {
            "status": "success",
            "url": "https://cdn.test/out.mp4",
            "meta": meta,
        },
    )

    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(job))
    if expected_reason is None:
        assert result.status == "complete"
        assert result.provider_job_id == "task-without-association"
        assert result.metadata["router_execution"]["output_identity"] == {
            "render_job_id": result.id,
            "provider_task_id": "task-without-association",
            "output_url": "https://cdn.test/out.mp4",
            "association_source": "runway_router_polled_task",
        }
    else:
        assert result.status == "failed"
        assert result.metadata["router_execution"]["provider_output_identity"] == meta.get("output_identity", {})
        assert result.output_payload.metadata["provider_response_normalized"]["metadata"]["reason"] == expected_reason
        assert result.output_payload.asset_url == ""
        assert asyncio.run(RunwayRouterAdapter(_provider_config()).fetch_outputs(result)) == []


def test_router_task_output_without_identity_is_not_marked_complete(monkeypatch, provider_calls):
    job = _build_job(_canonical_five(), authorization=_authorization())
    storage = _bind_router_execution_authority(job)
    from app.services import reference_validation
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    monkeypatch.setattr(reference_validation.project_store, "get_project", lambda _project: storage.reference_project)
    monkeypatch.setattr(
        runway_router_provider,
        "submit_runway_router_video_render",
        lambda *_args, **_kwargs: {
            "status": "success",
            "url": "https://cdn.test/out.mp4",
            "meta": {"runway_task_id": "task-without-association"},
        },
    )
    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(job))
    assert result.status == "failed"
    assert result.output_payload.metadata["provider_response_normalized"]["metadata"]["reason"] == "provider_output_identity_missing"
    assert result.output_payload.asset_url == ""


def test_router_output_registration_fails_closed_without_matching_durable_asset(provider_calls, monkeypatch, tmp_path):
    from app.data.storage import DatabaseStorage
    from app.services.render import RenderService

    job = _submit(_build_job(_canonical_five(), authorization=_authorization()))
    storage = DatabaseStorage(str(tmp_path / "router-output-assets.sqlite"))
    monkeypatch.setattr("app.services.render._storage", storage)
    service = RenderService()
    service._jobs[job.id] = job
    service._provider_configs["runway_router"] = _provider_config()
    monkeypatch.setattr(
        "app.services.video_asset_service.VideoAssetService.register_generated_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("asset registration unavailable")),
    )
    assert asyncio.run(service.get_job_outputs(job.id)) == []


def test_no_declaration_keeps_the_unprojected_router_path_fail_closed(provider_calls):
    """Without a declaration the canonical five is NOT silently projected."""
    job = _build_job(_canonical_five())
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "required_reference_incompatible"
    assert provider_calls == []


def test_canonical_binding_requires_declared_projection_before_provider_calls(provider_calls):
    job = _build_job(_canonical_five(), authorization=_authorization())
    # The frozen contract remains valid, but remove the projection declaration
    # and authorization while keeping the persisted canonical binding.
    from app.services import runway_reference_projection

    job.metadata.pop(runway_reference_projection.AUTHORIZATION_METADATA_KEY, None)
    job.metadata.pop(runway_reference_projection.PROJECTION_METADATA_KEY, None)
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "reference_projection_declaration_missing"
    assert provider_calls == []


# ── Authorization gate ──────────────────────────────────────────────────────

@pytest.mark.parametrize("rejected_env", REJECTED_ENV_IDS)
def test_rejected_environment_reference_fails_closed(provider_calls, rejected_env):
    rows = _canonical_five(env_ref_id=rejected_env)
    job = _build_job(rows, authorization=_authorization())
    result = _submit(job)
    assert result.status == "failed"
    # The exact frozen setting row no longer matches the selected creator
    # authority, so the adapter rejects it before projection/reselection.
    assert _reason(result) == "reference_authorization_mismatch"
    assert provider_calls == []


def test_unknown_environment_reference_fails_closed(provider_calls):
    rows = _canonical_five(env_ref_id="ref_set_not_authorized")
    job = _build_job(rows, authorization=_authorization())
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "reference_authorization_mismatch"
    assert provider_calls == []


@pytest.mark.parametrize(
    "change",
    ["revoked", "deleted", "uri_changed", "wrong_project", "wrong_role", "wrong_target"],
)
def test_last_mile_revalidation_rejects_changed_current_reference_before_provider(
    provider_calls, monkeypatch, change,
):
    from app.services import reference_validation

    job = _build_job(_canonical_five(), authorization=_authorization())
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr(reference_validation.project_store, "get_project", lambda _project: storage.reference_project)
    rows = storage.reference_state["rows"]
    row = next(item for item in rows if item["ref_id"] == AUTHORIZED_ENV)
    if change == "revoked":
        row["approval_state"] = "rejected"
    elif change == "deleted":
        rows.remove(row)
    elif change == "uri_changed":
        row["image_url"] = "https://cdn.example.test/scene002/replaced-env.png"
    elif change == "wrong_project":
        row["project_id"] = "project-other"
    elif change == "wrong_role":
        row["category"] = "character_face"
    else:
        row["target_id"] = "loc-other"

    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(
        job, authority_storage=storage, reference_storage=storage,
    ))

    assert result.status == "failed"
    assert provider_calls == []


def test_projection_different_from_current_authorized_selection_blocks_provider(provider_calls, monkeypatch):
    """A stale mapping must fail before any provider call."""
    from app.services import reference_validation

    job = _build_job(_canonical_five(), authorization=_authorization())
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr(reference_validation.project_store, "get_project", lambda _project: storage.reference_project)
    row = next(item for item in storage.reference_state["rows"] if item["ref_id"] == AUTHORIZED_ENV)
    row["image_url"] = "https://cdn.example.test/scene002/not-the-authorized-environment.png"

    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(
        job, authority_storage=storage, reference_storage=storage,
    ))

    assert result.status == "failed"
    assert provider_calls == []


def test_reference_revoked_after_router_estimate_blocks_live_request(provider_calls, monkeypatch):
    from app.services import reference_validation

    job = _build_job(_canonical_five(), authorization=_authorization())
    storage = _bind_router_execution_authority(job)
    monkeypatch.setattr(reference_validation.project_store, "get_project", lambda _project: storage.reference_project)
    row = next(item for item in storage.reference_state["rows"] if item["ref_id"] == AUTHORIZED_ENV)
    original_transport = runway_router_provider._runway_router_request

    def revoke_after_estimate(url, *, method="GET", payload=None, api_key=None):
        if method == "POST" and payload and payload.get("dryRun"):
            provider_calls.append((method, copy.deepcopy(payload)))
            row["approval_state"] = "rejected"
            return {"dryRun": True, "routing": {
                "model": "gen4.5", "provider": "runway",
                "configId": runway_router_provider.get_router_config_id(),
                "estimatedCost": {"credits": 20},
            }}
        if method == "POST":
            provider_calls.append((method, copy.deepcopy(payload)))
            raise AssertionError("stale reference approval must block live Router submission")
        return original_transport(url, method=method, payload=payload, api_key=api_key)

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", revoke_after_estimate)
    result = asyncio.run(RunwayRouterAdapter(_provider_config())._submit_job_after_authorization(
        job, authority_storage=storage, reference_storage=storage,
    ))

    posts = [payload for method, payload in provider_calls if method == "POST"]
    assert result.status == "failed"
    assert len(posts) == 1 and posts[0].get("dryRun") is True
    assert not any(not payload.get("dryRun") for payload in posts)


def test_unapproved_environment_reference_fails_closed(provider_calls):
    rows = _canonical_five(env_overrides={"approval_state": "candidate"})
    code, _message, _refs, request, _execution = _projection_gate(rows, _authorization())
    assert code == "reference_authorization_mismatch"
    assert request is None
    assert provider_calls == []


def test_ambiguous_environment_reference_fails_closed(provider_calls):
    rows = _canonical_five()
    rows[2] = _row("ref_set_second_environment", "https://cdn.example.test/scene002/env2.png",
                   "setting", SETTING_ID, "environment", "environment")
    code, _message, _refs, request, _execution = _projection_gate(rows, _authorization())
    assert code == "reference_authorization_mismatch"
    assert request is None
    assert provider_calls == []


def test_missing_reference_authority_fails_closed(provider_calls):
    job = _build_job(_canonical_five(), authorization={"authorized_environment_ref_id": ""})
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "missing_reference_authority"
    assert provider_calls == []


def test_malformed_reference_authority_fails_closed(provider_calls):
    job = _build_job(_canonical_five(), authorization="not-a-record")
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "missing_reference_authority"
    assert provider_calls == []


def test_tampered_projection_fingerprint_fails_closed(provider_calls):
    rows = _canonical_five()
    record = projection.project_authorized_environment(
        rows, authorized_environment_ref_id=AUTHORIZED_ENV,
        rejected_environment_ref_ids=REJECTED_ENV_IDS,
    )
    record["source_uri_fingerprints"] = dict(record["source_uri_fingerprints"])
    record["source_uri_fingerprints"][MAYA_FACE] = "f" * 64
    job = _build_job(rows, projection_record=record)
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "reference_authorization_mismatch"
    assert provider_calls == []


def test_tampered_projection_selection_fails_closed(provider_calls):
    rows = _canonical_five()
    record = projection.project_authorized_environment(
        rows, authorized_environment_ref_id=AUTHORIZED_ENV,
        rejected_environment_ref_ids=REJECTED_ENV_IDS,
    )
    record = copy.deepcopy(record)
    record["selected_ref_ids"] = [DRE_FACE, MAYA_FACE, AUTHORIZED_ENV]
    job = _build_job(rows, projection_record=record)
    result = _submit(job)
    assert result.status == "failed"
    assert _reason(result) == "reference_authorization_mismatch"
    assert provider_calls == []


# ── Mounted local environment: fingerprint + selected-only ephemeral upload ─

def test_local_environment_reference_is_materialized_only_after_authorization(
    provider_calls, tmp_path, monkeypatch,
):
    from app import adapters
    from app.services import runway_ephemeral_upload as ephemeral

    backend_root = tmp_path / "backend"
    local_image = backend_root / "outputs" / "previs" / PROJECT_ID / "scene002_env.png"
    local_image.parent.mkdir(parents=True)
    payload = b"canonical-scene002-environment-bytes"
    local_image.write_bytes(payload)
    env_uri = f"/previs-assets/{PROJECT_ID}/scene002_env.png"
    rows = _canonical_five(env_uri=env_uri)

    # Point the production adapter's normal backend-root calculation at the
    # isolated temporary backend fixture; no repository media is touched.
    monkeypatch.setattr(adapters, "__file__", str(backend_root / "app" / "adapters" / "__init__.py"))

    class FakeUpload:
        def __init__(self):
            self.allocations = []
            self.multipart = []

        def post_json(self, url, allocation, *, api_key):
            self.allocations.append((url, dict(allocation)))
            return {
                "uploadUrl": "https://uploads.example.test/signed",
                "fields": {"key": "signed-key", "policy": "signed-policy"},
                "runwayUri": "runway://ephemeral/authorized-environment",
            }

        def post_multipart(self, url, fields, data, filename):
            self.multipart.append((url, dict(fields), bytes(data), filename))

    upload = FakeUpload()
    original_materialize = ephemeral.materialize_selected_ephemeral

    def materialize_with_fake(*args, **kwargs):
        kwargs["_post_json"] = upload.post_json
        kwargs["_post_multipart"] = upload.post_multipart
        return original_materialize(*args, **kwargs)

    monkeypatch.setattr(ephemeral, "materialize_selected_ephemeral", materialize_with_fake)
    job = _build_job(rows, authorization=_authorization())
    job.metadata[projection.AUTHORIZATION_METADATA_KEY]["source_fingerprint"] = hashlib.sha256(payload).hexdigest()
    _bind_router_execution_authority(job)
    frozen_before = copy.deepcopy(job.metadata["creative_generation_contract"])
    manifest_before = copy.deepcopy(job.metadata["creative_generation_manifest"])
    input_before = json.loads(job.input_payload.model_dump_json())

    result = _submit(job)

    assert result.status == "complete", result.error_message
    assert len(upload.allocations) == 1
    assert len(upload.multipart) == 1
    assert upload.multipart[0][2:] == (payload, "scene002_env.png")
    assert upload.allocations[0][1]["type"] == "ephemeral"
    assert len([call for call in provider_calls if call[0] == "POST" and not call[1].get("dryRun")]) == 1
    assert len([call for call in provider_calls if call[0] == "POST" and call[1].get("dryRun")]) == 1
    provider_payload = next(call[1] for call in provider_calls if call[0] == "POST" and not call[1].get("dryRun"))
    references = provider_payload["input"]["referenceImages"]
    assert [item["uri"] for item in references][-1] == "runway://ephemeral/authorized-environment"
    assert len(references) == 4
    assert [item["uri"] for item in references[:3]] == [
        "https://cdn.example.test/scene002/dre-face.png",
        "https://cdn.example.test/scene002/maya-face.png",
        "https://cdn.example.test/scene002/maya-general.png",
    ]
    assert all("maya-alt" not in str(item) for item in references)
    # Upload and request construction are execution-only: frozen creative data,
    # canonical references, and mutable render inputs remain unchanged.
    assert job.metadata["creative_generation_contract"] == frozen_before
    assert job.metadata["creative_generation_manifest"] == manifest_before
    assert json.loads(job.input_payload.model_dump_json()) == input_before
    assert job.metadata[projection.AUTHORIZATION_METADATA_KEY]["authorized_environment_ref_id"] == AUTHORIZED_ENV
    assert job.metadata[projection.AUTHORIZATION_METADATA_KEY]["source_fingerprint"] == hashlib.sha256(payload).hexdigest()


def test_prepare_local_reference_resolves_bytes_without_network(tmp_path):
    local_image = tmp_path / "scene002_env.png"
    payload = b"canonical-scene002-environment-bytes"
    local_image.write_bytes(payload)
    row = _row(AUTHORIZED_ENV, str(local_image), "setting", SETTING_ID, "environment", "environment")

    prepared = projection.prepare_local_reference(
        row, backend_root=tmp_path, expected_sha256=hashlib.sha256(payload).hexdigest(),
    )

    assert prepared["preparation_status"] == "prepared"
    assert prepared["network_calls"] == 0
    assert prepared["provider_uri"] is None
    assert prepared["content_bytes"] == len(payload)
    assert prepared["content_sha256"] == hashlib.sha256(payload).hexdigest()
    assert prepared["filename"] == "scene002_env.png"
    # Canonical truth is never mutated.
    assert row["uri"] == str(local_image)


def test_prepare_local_reference_fails_closed_on_missing_bytes(tmp_path):
    row = _row(AUTHORIZED_ENV, str(tmp_path / "absent.png"),
               "setting", SETTING_ID, "environment", "environment")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.prepare_local_reference(row, backend_root=tmp_path, expected_sha256="0" * 64)
    assert exc_info.value.code == "unavailable_source_bytes"


def test_prepare_local_reference_fails_closed_on_fingerprint_mismatch(tmp_path):
    local_image = tmp_path / "scene002_env.png"
    local_image.write_bytes(b"actual-bytes")
    row = _row(AUTHORIZED_ENV, str(local_image), "setting", SETTING_ID, "environment", "environment")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.prepare_local_reference(
            row, backend_root=tmp_path, expected_sha256="0" * 64,
        )
    assert exc_info.value.code == "source_fingerprint_mismatch"


def test_prepare_local_reference_accepts_pinned_provider_uri_without_network():
    row = _row(AUTHORIZED_ENV, ENV_HTTPS, "setting", SETTING_ID, "environment", "environment")
    fingerprint = hashlib.sha256(ENV_HTTPS.encode("utf-8")).hexdigest()
    prepared = projection.prepare_local_reference(row, expected_sha256=fingerprint)
    assert prepared["preparation_status"] == "provider_addressable"
    assert prepared["content_sha256"] == fingerprint
    assert prepared["provider_uri"] == ENV_HTTPS
    assert prepared["network_calls"] == 0


def test_prepare_local_reference_rejects_changed_provider_uri():
    row = _row(AUTHORIZED_ENV, ENV_HTTPS, "setting", SETTING_ID, "environment", "environment")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.prepare_local_reference(row, expected_sha256="0" * 64)
    assert exc_info.value.code == "source_fingerprint_mismatch"


# ── Incomplete frozen contracts ─────────────────────────────────────────────

def test_generic_four_projects_through_v2_to_mocked_provider(provider_calls):
    """A valid four-reference generic binding routes via v2 to the provider.

    Formerly ``test_incomplete_canonical_five_fails_closed``: R3.2 defines
    1-to-4 canonical bindings as the generic v2 shape, so omitting one MAYA
    row now yields a complete v2 delivery instead of a shape failure.
    """
    rows = _canonical_five()
    del rows[2]
    job = _build_job(rows, authorization=_authorization())
    result = _submit(job)
    assert result.status == "complete", result.error_message
    assert result.output_payload.metadata["reference_projection"]["projection_policy_version"] == "v2"
    assert result.output_payload.metadata["reference_projection"]["selected_ref_ids"] == [
        DRE_FACE, MAYA_FACE, MAYA_ALT, AUTHORIZED_ENV,
    ]
    assert result.output_payload.metadata["reference_projection"]["omitted_ref_ids"] == []
    live_posts = [payload for method, payload in provider_calls if method == "POST" and not payload.get("dryRun")]
    assert len(live_posts) == 1
    assert live_posts[0]["input"]["referenceImages"] == [
        {"uri": "https://cdn.example.test/scene002/dre-face.png", "role": "reference"},
        {"uri": "https://cdn.example.test/scene002/maya-face.png", "role": "reference"},
        {"uri": "https://cdn.example.test/scene002/maya-alt.png", "role": "reference"},
        {"uri": ENV_HTTPS, "role": "reference"},
    ]


def test_projection_module_only_delegates_selection(monkeypatch):
    """The authorization gate never re-implements the v1 selection rules."""
    rows = _canonical_five()
    calls: list[dict] = []
    original = projection.project_runway_v1

    def spy(canonical_refs, **kwargs):
        calls.append({"count": len(canonical_refs), "kwargs": sorted(kwargs)})
        return original(canonical_refs, **kwargs)

    monkeypatch.setattr(projection, "project_runway_v1", spy)
    record = projection.project_authorized_environment(
        rows, authorized_environment_ref_id=AUTHORIZED_ENV,
        rejected_environment_ref_ids=REJECTED_ENV_IDS,
    )
    assert calls == [{"count": 5, "kwargs": ["allow_local_source_uris", "backend_root", "expected_binding", "source_fingerprints"]}]
    assert record[projection.AUTHORIZATION_FIELD] == AUTHORIZED_ENV
    assert record["selected_ref_ids"] == [DRE_FACE, MAYA_FACE, MAYA_GENERAL, AUTHORIZED_ENV]
    assert record["omitted_ref_ids"] == [MAYA_ALT]
