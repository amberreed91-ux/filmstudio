"""R4.5 session A — shared role/comparison/scope gates (F1, F2, F3, F4, F6).

Synthetic fixtures only. Socket-blocked; every refusal leg asserts zero jobs,
zero transport calls, and zero provider contact via tripwires.

Covers:
  5a. unit tests for contract_comparison_binding + assert_setting_project_scope
  5b. negative controls (unknown role, over-capacity, scope mismatch, tampering)
  5c. parity matrix across preflight / creation / reconstruction / adapter
"""
from __future__ import annotations

import pytest

from app.services.reference_validation import (
    assert_setting_project_scope,
    contract_comparison_binding,
)


def _contract_rows() -> list[dict]:
    return [
        {
            "uri": "https://cdn.test/face.png",
            "role": "reference",
            "studio_role": "face",
            "category": "face",
            "source": "canonical_reference_binding",
            "ref_id": "ref-face",
            "target_type": "character",
            "target_id": "char-1",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "uri": "https://cdn.test/set.png",
            "role": "reference",
            "studio_role": "environment",
            "category": "environment",
            "source": "canonical_reference_binding",
            "ref_id": "ref-set",
            "target_type": "setting",
            "target_id": "set-1",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "environment",
        },
    ]


def _raw_rows(*, project_id: str = "proj-1") -> list[dict]:
    return [
        {
            "ref_id": "ref-face",
            "uri": "https://cdn.test/face.png",
            "target_type": "character",
            "target_id": "char-1",
            "role": "face",
            "category": "face",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "ref-set",
            "project_id": project_id,
            "uri": "https://cdn.test/set.png",
            "target_type": "setting",
            "target_id": "set-1",
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "environment",
        },
    ]


# --- 5a: helper unit tests -------------------------------------------------


def test_comparison_binding_unifies_contract_and_raw_shapes():
    assert contract_comparison_binding(_contract_rows()) == contract_comparison_binding(_raw_rows())


def test_comparison_binding_exact_ten_keys():
    projected = contract_comparison_binding(_raw_rows())
    assert [sorted(row.keys()) for row in projected] == [
        sorted(["ref_id", "uri", "target_type", "target_id", "role", "category",
                "canonical", "approval_state", "source_kind", "kind"]),
    ] * 2
    assert projected[0]["role"] == "face"
    assert projected[1]["role"] == "environment"


def test_comparison_binding_omits_kind_when_absent():
    rows = _raw_rows()
    for row in rows:
        del row["kind"]
    projected = contract_comparison_binding(rows)
    assert all("kind" not in row for row in projected)


def test_comparison_binding_preserves_order_and_rejects_tampering():
    expected = contract_comparison_binding(_raw_rows())
    reordered = contract_comparison_binding(list(reversed(_raw_rows())))
    assert reordered != expected
    substituted = _raw_rows()
    substituted[0] = dict(substituted[0], uri="https://cdn.test/other.png")
    assert contract_comparison_binding(substituted) != expected
    dropped = _raw_rows()[:1]
    assert contract_comparison_binding(dropped) != expected


def test_comparison_binding_missing_key_fails_closed():
    rows = _raw_rows()
    del rows[0]["uri"]
    with pytest.raises((KeyError, ValueError)):
        contract_comparison_binding(rows)
    with pytest.raises(ValueError):
        contract_comparison_binding(["not-a-dict"])  # type: ignore[list-item]


def test_setting_scope_accepts_matching_project():
    assert_setting_project_scope(_raw_rows(project_id="proj-1"), "proj-1")


def test_setting_scope_rejects_foreign_project():
    with pytest.raises(ValueError, match="project scope"):
        assert_setting_project_scope(_raw_rows(project_id="proj-evil"), "proj-1")


def test_setting_scope_rejects_missing_project_id():
    rows = _raw_rows()
    del rows[1]["project_id"]
    with pytest.raises(ValueError, match="project scope"):
        assert_setting_project_scope(rows, "proj-1")


def test_setting_scope_ignores_character_rows():
    rows = _raw_rows()
    rows[0]["project_id"] = "proj-evil"
    assert_setting_project_scope(rows, "proj-1")


# --- 5b/5c: shared artifact harness -----------------------------------------
#
# One synthetic artifact triple (frozen contract + raw binding + manifest),
# built pipeline-realistically (face/environment studio roles, project_id on
# setting rows, fingerprint-consistent), driven through the real gates at all
# four layers. Socket-blocked; refusal legs assert zero jobs, zero transport
# calls, and zero provider contact.

R45_PROJECT = "proj-r45-gates"
R45_SCENE = "scene_001"
R45_SHOT = "scene_001_shot_001"

_R45_SETTING_ROLES = {"environment", "composition"}


def _r45_raw_binding(*, roles=("face", "environment"), project_id=R45_PROJECT) -> list[dict]:
    rows: list[dict] = []
    for index, spec in enumerate(roles):
        role, target = spec if isinstance(spec, tuple) else (spec, None)
        if target is None:
            target = "setting" if role in _R45_SETTING_ROLES else "character"
        if target == "setting":
            rows.append({
                "ref_id": f"r45-set-{index}",
                "project_id": project_id,
                "uri": f"https://cdn.test/r45-set-{index}.png",
                "target_type": "setting",
                "target_id": "set-1",
                "role": role,
                "category": role,
                "canonical": True,
                "approval_state": "approved",
                "source_kind": "confirmed",
                "kind": "environment",
            })
        else:
            rows.append({
                "ref_id": f"r45-face-{index}",
                "uri": f"https://cdn.test/r45-face-{index}.png",
                "target_type": "character",
                "target_id": "char-1",
                "role": role,
                "category": role,
                "canonical": True,
                "approval_state": "approved",
                "source_kind": "confirmed",
                "kind": "character_face",
            })
    return rows


def _r45_build(*, roles=("face", "environment"), project_id=R45_PROJECT) -> dict:
    """Freeze a fingerprint-consistent (contract, manifest, binding) triple."""
    import copy
    from dataclasses import replace

    from app.services.camera_provenance import (
        camera_plan_digest,
        canonical_camera_instructions,
    )
    from app.services.generation_contract import (
        freeze_dialogue_handoff,
        freeze_generation_contract,
    )
    from app.services.scene_coverage_contract import build_scene_coverage_contract
    from app.services.shot_manifest import (
        build_shot_manifest,
        recompute_manifest_fingerprint,
    )

    binding = _r45_raw_binding(roles=roles, project_id=project_id)
    scene_text = "INT. TEST ROOM - DAY\nA single lamp glows beside a closed book."
    project = {
        "project_id": R45_PROJECT,
        "script_text": scene_text,
        "execution_summary": {"scenes": [], "dialogue_lines": []},
    }
    scene = {
        "scene_id": R45_SCENE,
        "heading": "INT. TEST ROOM - DAY",
        "text": scene_text,
        "setting_id": "set-1",
    }
    plan = {"camera": "Slow dolly in", "framing": "Wide"}
    camera_parameters = {
        "camera_plan": plan,
        "camera_instructions": canonical_camera_instructions(plan, "USER_SPECIFIED"),
        "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": R45_PROJECT,
        "camera_source_scene_id": R45_SCENE,
        "camera_source_shot_id": R45_SHOT,
        "camera_target_project_id": R45_PROJECT,
        "camera_target_scene_id": R45_SCENE,
        "camera_target_shot_id": R45_SHOT,
    }
    camera_parameters["camera_source_digest"] = camera_plan_digest(
        plan, "USER_SPECIFIED", source_project_id=R45_PROJECT,
        source_scene_id=R45_SCENE, source_shot_id=R45_SHOT,
    )
    shot = {
        "shot_id": R45_SHOT,
        "scene_id": R45_SCENE,
        "shot_number": 1,
        "parameters": dict(camera_parameters),
        "dialogue_disposition": "INTENTIONAL_SILENCE",
        "dialogue_disposition_reason": "Parity harness carries no dialogue.",
    }
    requirements = {
        "setting_id": "set-1",
        "characters": (
            {"char-1": {"id": "char-1", "name": "Char"}}
            if any(row.get("target_type") == "character" for row in binding)
            else {}
        ),
        "reference_binding": copy.deepcopy(binding),
    }
    coverage_probe, _, _ = build_scene_coverage_contract(
        project_id=R45_PROJECT, project=project, scene=scene,
        shots=[shot], reference_requirements=requirements,
    )
    creator_decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"],
         "status": "ASSIGNED", "shot_id": R45_SHOT, "reason": ""}
        for row in coverage_probe["content_units"]
    ]
    creator_decisions.extend([
        {"obligation_type": "shot_content", "obligation_id": R45_SHOT,
         "status": "UNRESOLVED", "shot_id": None, "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": R45_SHOT,
         "status": "INTENTIONAL_SILENCE", "reason": "Parity harness carries no dialogue."},
    ])
    coverage, coverage_blockers, _ = build_scene_coverage_contract(
        project_id=R45_PROJECT, project=project, scene=scene,
        shots=[shot], reference_requirements=requirements,
        creator_decisions=creator_decisions,
    )
    assert not coverage_blockers, coverage_blockers
    shot_coverage = coverage["shots"][0]
    contract_rows = [
        {
            "uri": row["uri"], "role": "reference", "studio_role": row["role"],
            "category": row["category"], "source": "canonical_reference_binding",
            "ref_id": row["ref_id"], "target_type": row["target_type"],
            "target_id": row["target_id"], "canonical": row["canonical"],
            "approval_state": row["approval_state"], "source_kind": row["source_kind"],
            **({"kind": row["kind"]} if row.get("kind") else {}),
        }
        for row in binding
    ]
    dialogue_handoff = freeze_dialogue_handoff(scene_id=R45_SCENE, shot_id=R45_SHOT, lines=[])
    contract = freeze_generation_contract(
        shot_id=R45_SHOT,
        prompt="R4.5 parity prompt — approved bytes.",
        reference_assets=contract_rows,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
        dialogue_handoff=dialogue_handoff,
        parameters={
            "duration": 6, "aspect_ratio": "16:9", "resolution": "720p",
            "seed": 43, "audio_intent": "generate", **camera_parameters,
        },
    )
    manifest = build_shot_manifest(
        project_id=R45_PROJECT,
        scene_id=R45_SCENE,
        scene=None,
        scene_version="test-scene-v1",
        storyboard_version="test-board-v1",
        scene_lineage=coverage,
        entries=[{
            "shot_id": R45_SHOT,
            "shot_order": 1,
            "duration_seconds": contract.duration or 0,
            "prompt": contract.prompt,
            "negative_prompt": contract.negative_prompt,
            "audio_intent": contract.audio,
            "reference_roles": [ref.studio_role for ref in contract.references],
            "reference_binding": [
                {
                    "ref_id": ref.ref_id, "uri": ref.uri,
                    "target_type": ref.target_type, "target_id": ref.target_id,
                    "role": ref.studio_role, "category": ref.category,
                    "canonical": ref.canonical,
                    "approval_state": ref.approval_state,
                    "source_kind": ref.source_kind,
                    **({"kind": ref.kind} if ref.kind else {}),
                    **({"project_id": project_id} if ref.target_type == "setting" else {}),
                }
                for ref in contract.references
            ],
            "generation_contract_digest": contract.creative_digest(),
            "aspect_ratio": contract.aspect_ratio,
            "resolution": contract.resolution,
            "seed": contract.seed,
            "references": [ref.uri for ref in contract.references],
            "camera_plan": plan,
            "camera_provenance": "USER_SPECIFIED",
            "camera_instructions": camera_parameters["camera_instructions"],
            "camera_source_digest": camera_parameters["camera_source_digest"],
            "camera_source_project_id": R45_PROJECT,
            "camera_source_scene_id": R45_SCENE,
            "camera_source_shot_id": R45_SHOT,
            "camera_target_project_id": R45_PROJECT,
            "camera_target_scene_id": R45_SCENE,
            "camera_target_shot_id": R45_SHOT,
            "parameters": {},
            "scene_coverage": coverage,
            "shot_coverage": shot_coverage,
            "dialogue_handoff": contract.payload().get("dialogue_handoff", {}),
        }],
    )
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest["storyboard"] = {"storyboard_version": "test-board-v1"}
    manifest["shots"][0]["storyboard_shot_id"] = "board-r45"
    manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
    manifest["shots"][0]["scene_coverage"] = coverage
    manifest["shots"][0]["scene_coverage_shot"] = shot_coverage
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
    return {
        "contract_record": contract.to_record(),
        "manifest": manifest,
        "binding": binding,
        "fingerprint": manifest["manifest_fingerprint"],
    }


def _r45_retampered(artifact: dict, mutate) -> dict:
    """Copy an artifact triple, mutate its manifest binding, re-fingerprint."""
    import copy
    from dataclasses import replace

    from app.services.generation_contract import FrozenGenerationContract
    from app.services.shot_manifest import recompute_manifest_fingerprint

    out = copy.deepcopy(artifact)
    mutate(out["manifest"]["shots"][0])
    out["manifest"]["manifest_fingerprint"] = ""
    fingerprint = recompute_manifest_fingerprint(out["manifest"])
    out["manifest"]["manifest_fingerprint"] = fingerprint
    frozen = replace(
        FrozenGenerationContract.from_record(out["contract_record"]),
        manifest_fingerprint=fingerprint,
    )
    out["contract_record"] = frozen.to_record()
    out["manifest"]["shots"][0]["generation_contract_digest"] = frozen.creative_digest()
    out["fingerprint"] = fingerprint
    return out


def _r45_preflight(artifact: dict) -> dict:
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )

    service = SceneProductionPipelineService()
    entry = {
        "shot_id": R45_SHOT,
        "reference_binding": [dict(row) for row in artifact["binding"]],
        "manifest_provider": "runway_router",
        "blockers": [],
        "generation_contract": artifact["contract_record"],
        "reference_projection_authorization": None,
    }
    manifest = {
        "shots": [{
            "shot_id": R45_SHOT,
            "reference_binding": [dict(row) for row in artifact["binding"]],
        }],
        "manifest_fingerprint": "fp-r45",
    }
    return service.preflight_batch_authorization(
        project_id=R45_PROJECT,
        scene_id=R45_SCENE,
        entries=[entry],
        shot_manifest=manifest,
        expected_digests=None,
    )


def _r45_reconstruct(artifact: dict, monkeypatch: pytest.MonkeyPatch):
    from app.services.providers import runway_router_provider
    from app.services.providers.runway_router_provider import (
        reconstruct_runway_router_video_request,
    )

    calls: list = []

    def _tripwire(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("reconstruction must not touch the provider transport")

    monkeypatch.setattr(
        runway_router_provider, "_runway_router_request", _tripwire
    )
    try:
        result = reconstruct_runway_router_video_request(
            artifact["contract_record"], artifact["manifest"]
        )
    finally:
        assert calls == []
    return result


def _r45_create(artifact: dict, tmp_path, monkeypatch):
    from app.access_context import access_user_id
    from app.data.storage import DatabaseStorage
    from app.models import StudioProject
    from app.services import render as render_module
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / "r45-gates-storage"))
    monkeypatch.setattr(render_module, "_storage", storage)
    monkeypatch.setattr(
        render_module, "get_adapter",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("creation must not touch provider adapters")
        ),
    )
    from app.models.storyboard_blueprint import (
        StoryboardBlueprint,
        StoryboardBlueprintStatus,
        StoryboardBlueprintVersion,
        StoryboardShot,
        StoryboardShotStatus,
    )

    storage.save_project(StudioProject(project_id=R45_PROJECT, title="R4.5 gates"))
    storage.access_save_user({"username": "owner-r45", "user_id": "owner-r45"}, create=True)
    storage.access_claim_project(R45_PROJECT, "owner-r45")
    storage.save_storyboard_blueprint(StoryboardBlueprint(
        blueprint_id="board-r45", project_id=R45_PROJECT, scene_id=R45_SCENE,
        current_version_id="test-board-v1", approved_version_id="test-board-v1",
        status=StoryboardBlueprintStatus.APPROVED,
    ))
    storage.save_storyboard_blueprint_version(StoryboardBlueprintVersion(
        version_id="test-board-v1", blueprint_id="board-r45", project_id=R45_PROJECT,
        scene_id=R45_SCENE, status=StoryboardBlueprintStatus.APPROVED,
        approved_at="2026-10-10T12:00:00Z", approved_by="owner-r45",
        metadata={"production_approval": {"actor_id": "owner-r45", "actor_authenticated": True}},
    ))
    storage.save_storyboard_shot(StoryboardShot(
        storyboard_shot_id="board-r45", blueprint_id="board-r45", version_id="test-board-v1",
        project_id=R45_PROJECT, scene_id=R45_SCENE, shot_id=R45_SHOT, shot_number=1,
        status=StoryboardShotStatus.APPROVED,
    ))
    manifest = artifact["manifest"]
    contract_record = artifact["contract_record"]
    from app.services.generation_contract import FrozenGenerationContract

    frozen = FrozenGenerationContract.from_record(contract_record)
    token = access_user_id.set("owner-r45")
    try:
        job = RenderService().create_job(
            project_id=R45_PROJECT,
            shot_id=R45_SHOT,
            provider="runway_router",
            prompt=frozen.prompt,
            parameters={
                "dialogue_handoff": contract_record["payload"]["dialogue_handoff"],
                "dialogue_lines": [],
                "scene_coverage": contract_record["payload"]["scene_coverage"],
                "scene_coverage_shot": contract_record["payload"]["scene_coverage_shot"],
                "camera_plan": contract_record["payload"]["camera_plan"],
                "camera_provenance": contract_record["payload"]["camera_provenance"],
                "camera_instructions": contract_record["payload"]["camera_instructions"],
                "camera_source_digest": contract_record["payload"]["camera_source_digest"],
                "camera_source_project_id": contract_record["payload"]["camera_source_project_id"],
                "camera_source_scene_id": contract_record["payload"]["camera_source_scene_id"],
                "camera_source_shot_id": contract_record["payload"]["camera_source_shot_id"],
                "camera_target_project_id": contract_record["payload"]["camera_target_project_id"],
                "camera_target_scene_id": contract_record["payload"]["camera_target_scene_id"],
                "camera_target_shot_id": contract_record["payload"]["camera_target_shot_id"],
                "storyboard": {
                    "storyboard_shot_id": "board-r45",
                    "version_id": "test-board-v1",
                },
            },
            reference_assets=[
                row["uri"]
                for row in manifest["shots"][0]["reference_binding"]
            ],
            generation_contract=contract_record,
            creative_manifest=manifest,
            creative_manifest_fingerprint=artifact["fingerprint"],
            frozen_reference_binding=[
                dict(row)
                for row in manifest["shots"][0]["reference_binding"]
            ],
            dialogue_handoff=contract_record["payload"]["dialogue_handoff"],
            prepared_generation_contract=contract_record,
        )
    finally:
        access_user_id.reset(token)
    assert storage.list_jobs(project_id=R45_PROJECT) != []
    return job, storage


# --- 5b: negative controls -------------------------------------------------


def test_preflight_accepts_pipeline_realistic_batch():
    report = _r45_preflight(_r45_build())
    assert report["ready"] is True
    assert report["shots"][0]["policy_version"] == "v2"


def test_preflight_rejects_unknown_role_with_zero_jobs():
    report = _r45_preflight(_r45_build(roles=("face", "composition")))
    assert report["ready"] is False
    failed = [row for row in report["shots"] if not row["ok"]]
    assert len(failed) == 1
    assert failed[0]["failure_code"] == "unsupported_reference_role"


def test_preflight_rejects_garbage_role_with_zero_jobs():
    report = _r45_preflight(
        _r45_build(roles=("face", ("not_a_role", "setting")))
    )
    assert report["ready"] is False
    assert [row for row in report["shots"] if not row["ok"]][0][
        "failure_code"
    ] == "unsupported_reference_role"


@pytest.mark.parametrize("role", ["face", "general", "alternate_angle", "environment"])
def test_preflight_accepts_every_v2_studio_role(role):
    roles = (role,) if role == "environment" else (role, "environment")
    report = _r45_preflight(_r45_build(roles=roles))
    assert report["ready"] is True, report["shots"]


def test_preflight_rejects_over_capacity_everywhere_with_existing_code():
    rows = tuple(["face"] * 4 + ["environment"])
    report = _r45_preflight(_r45_build(roles=rows))
    assert report["ready"] is False
    failed = [row for row in report["shots"] if not row["ok"]]
    assert len(failed) == 1
    assert failed[0]["failure_code"] == "unsupported_reference_capacity"


def test_reconstruction_accepts_pipeline_realistic_batch(monkeypatch):
    wire = _r45_reconstruct(_r45_build(), monkeypatch)
    assert isinstance(wire, dict)
    assert wire["configId"]


def test_reconstruction_rejects_unknown_role(monkeypatch):
    with pytest.raises(
        ValueError, match="cannot represent a frozen reference role"
    ):
        _r45_reconstruct(_r45_build(roles=("face", "composition")), monkeypatch)


def test_reconstruction_rejects_over_capacity(monkeypatch):
    with pytest.raises(ValueError, match="more than four"):
        _r45_reconstruct(
            _r45_build(roles=tuple(["face"] * 4 + ["environment"])), monkeypatch
        )


def _r45_evil_scope(row: dict) -> None:
    row["reference_binding"][1] = {
        **row["reference_binding"][1], "project_id": "proj-evil"
    }


def test_reconstruction_rejects_foreign_project_scope(monkeypatch):
    artifact = _r45_build()
    tampered = _r45_retampered(artifact, _r45_evil_scope)
    with pytest.raises(ValueError, match="project scope"):
        _r45_reconstruct(tampered, monkeypatch)


def _r45_reverse(row: dict) -> None:
    row["reference_binding"].reverse()
    row["references"].reverse()
    row["reference_roles"].reverse()


def _r45_substitute_uri(row: dict) -> None:
    row["reference_binding"][0] = {
        **row["reference_binding"][0], "uri": "https://cdn.test/substituted.png"
    }
    row["references"][0] = "https://cdn.test/substituted.png"


def _r45_drop_row(row: dict) -> None:
    row["reference_binding"].pop()
    row["references"].pop()
    row["reference_roles"].pop()


_R45_TAMPERS = [_r45_reverse, _r45_substitute_uri, _r45_drop_row]
_R45_TAMPER_IDS = ["reordered", "substituted-uri", "dropped-row"]


@pytest.mark.parametrize("mutate", _R45_TAMPERS, ids=_R45_TAMPER_IDS)
def test_reconstruction_rejects_tampered_binding(monkeypatch, mutate):
    tampered = _r45_retampered(_r45_build(), mutate)
    with pytest.raises(ValueError, match="contradict the contract"):
        _r45_reconstruct(tampered, monkeypatch)


def test_creation_accepts_pipeline_realistic_batch(tmp_path, monkeypatch):
    job, _storage = _r45_create(_r45_build(), tmp_path, monkeypatch)
    assert job.provider == "runway_router"
    assert "creative_generation_contract" in (job.metadata or {})


def test_creation_rejects_foreign_project_scope(tmp_path, monkeypatch):
    artifact = _r45_build()
    tampered = _r45_retampered(artifact, _r45_evil_scope)
    with pytest.raises(ValueError, match="project scope"):
        _r45_create(tampered, tmp_path, monkeypatch)


@pytest.mark.parametrize("mutate", _R45_TAMPERS, ids=_R45_TAMPER_IDS)
def test_creation_rejects_tampered_binding(tmp_path, monkeypatch, mutate):
    # Any binding tamper is refused fail-closed before persistence (the
    # layered creation gates fire in order; the shared comparison shape is
    # pinned exactly at unit level above). Zero jobs may exist afterwards.
    from app.data.storage import DatabaseStorage

    artifact = _r45_build()
    tampered = _r45_retampered(artifact, mutate)
    with pytest.raises(ValueError):
        _r45_create(tampered, tmp_path, monkeypatch)
    assert (
        DatabaseStorage(str(tmp_path / "r45-gates-storage")).list_jobs(
            project_id=R45_PROJECT
        )
        == []
    )


def test_creation_has_no_role_gate_by_design(tmp_path, monkeypatch):
    """Creation judges comparison + scope only (approved parity table: creation
    carries no inline role check); roles are judged at preflight,
    reconstruction, and the adapter. Unknown roles therefore pass creation
    equality when consistent, and still cannot reach the wire."""
    job, _storage = _r45_create(
        _r45_build(roles=("face", "composition")), tmp_path, monkeypatch
    )
    assert job.provider == "runway_router"


# --- 5c: parity matrix -------------------------------------------------------


def test_parity_valid_artifact_agrees_everywhere(tmp_path, monkeypatch):
    import asyncio

    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.services.providers import runway_router_provider

    artifact = _r45_build()
    report = _r45_preflight(artifact)
    assert report["ready"] is True
    job, storage = _r45_create(artifact, tmp_path, monkeypatch)
    wire = _r45_reconstruct(artifact, monkeypatch)
    assert isinstance(wire, dict)

    # Scaffolding (pre-existing gap, reported for the F5 session, not gated
    # here): create_job persists only frozen_parameters into RenderJobInput,
    # so the adapter's mutable-input identity check cannot pass for a freshly
    # created job. Align the input snapshot to the frozen contract to isolate
    # the declaration gate this session must leave fail-closed.
    from app.services.generation_contract import FrozenGenerationContract as _Frozen

    _payload = _Frozen.from_record(
        job.metadata["creative_generation_contract"]
    ).payload()
    _params = dict(job.input_payload.parameters)
    _params.update(
        scene_coverage=_payload["scene_coverage"],
        scene_coverage_shot=_payload["scene_coverage_shot"],
        dialogue_handoff=_payload["dialogue_handoff"],
    )
    job.input_payload.parameters = _params
    storage.save_job(job)

    transport_calls: list = []

    def _tripwire(*args, **kwargs):
        transport_calls.append((args, kwargs))
        raise AssertionError("no provider contact before authorization")

    monkeypatch.setattr(
        runway_router_provider, "_runway_router_request", _tripwire
    )
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    config = ProviderConfig(
        provider_id="runway_router",
        name="Runway Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
    )
    submitted = asyncio.run(
        RunwayRouterAdapter(config)._submit_job_after_authorization(job)
    )
    assert submitted.status == "failed"
    reason = ((submitted.metadata or {}).get("router_execution") or {}).get("reason")
    assert reason == "reference_projection_declaration_missing"
    assert transport_calls == []


def test_parity_normalizer_agrees_with_all_role_gates():
    from app.services.runway_reference_projection import (
        RunwayReferenceProjectionError,
        normalize_studio_role,
    )

    for role in ("face", "full_body", "general", "alternate_angle", "environment"):
        assert normalize_studio_role(role) == "reference"
    assert normalize_studio_role("storyboard") == "first"
    assert normalize_studio_role("storyboard_last") == "last"
    for role in ("composition", "not_a_role", "", None):
        with pytest.raises(RunwayReferenceProjectionError) as exc_info:
            normalize_studio_role(role)
        assert exc_info.value.code == "unsupported_reference_role"
    # G-F5-ROLE-1: body-only looks project as plain character references.
    report = _r45_preflight(_r45_build(roles=("face", "environment", "full_body")))
    assert report["ready"] is True
    report = _r45_preflight(_r45_build(roles=("face", "environment", ("composition", "character"))))
    assert report["ready"] is False
    assert [row for row in report["shots"] if not row["ok"]][0][
        "failure_code"
    ] == "unsupported_reference_role"
