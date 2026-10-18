"""Focused regression tests: generic Runway reference projection (policy v2).

Covers the R3.2 delivery contract with identities that are deliberately NOT
Scene 002 (no DRE/MAYA/loc-c8f88b9c/project_5907c60cddbc anywhere): the v2
policy must authorize purely on approval, canonical authority, provenance,
target identity, fingerprint, and frozen-contract consistency.

Non-generative: no provider request, no credits. HTTPS fixtures fingerprint
by URI bytes; the mocked-adapter test doubles the Router transport and
asserts the exact wire shape.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services import runway_reference_projection as projection
from app.services.generation_contract import (
    FrozenGenerationContract,
    freeze_dialogue_handoff,
    freeze_generation_contract,
)
from app.services.providers import runway_router_provider
from app.services.reference_validation import frozen_reference_payload
from app.services.shot_manifest import build_shot_manifest, recompute_manifest_fingerprint

GEN_PROJECT = "project-generic-v2"
GEN_SCENE = "scene_gen_001"
GEN_SHOT = "scene_gen_001_shot_001"
GEN_SETTING = "set-gen-001"
GEN_VERSION = "gen-board-v1"
C1 = "chr-gen-aaa"
C2 = "chr-gen-bbb"
ENV_REF = "ref-gen-env-001"
C1_FACE = "ref-gen-c1-face"
C2_GENERAL = "ref-gen-c2-general"


def _grow(ref_id, uri, target_type, target_id, studio_role, kind, **overrides):
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


def _generic_three() -> list[dict]:
    """Two characters plus the setting anchor — the canonical generic shape."""
    return [
        _grow(C1_FACE, "https://cdn.example.test/generic/c1-face.png", "character", C1, "face", "character_face"),
        _grow(C2_GENERAL, "https://cdn.example.test/generic/c2-general.png", "character", C2, "general", "character_full"),
        _grow(ENV_REF, "https://cdn.example.test/generic/env.png", "setting", GEN_SETTING, "environment", "environment"),
    ]


def _code_of(exc_info) -> str:
    return str(getattr(exc_info.value, "code", ""))


def _gauth(rows, env_ref: str = ENV_REF, env_uri: str = "https://cdn.example.test/generic/env.png") -> dict:
    binding = []
    for row in rows:
        bound = dict(row)
        bound["project_id"] = GEN_PROJECT
        bound["role"] = row.get("studio_role") or row.get("role")
        binding.append(bound)
    digest = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "authorized_environment_ref_id": env_ref,
        "rejected_environment_ref_ids": ["ref-gen-rejected-000"],
        "authorization_policy_id": projection.AUTHORIZATION_POLICY_ID,
        "project_id": GEN_PROJECT,
        "scene_id": GEN_SCENE,
        "setting_id": GEN_SETTING,
        "current_version_id": GEN_VERSION,
        "approved_version_id": GEN_VERSION,
        "storyboard_version_id": GEN_VERSION,
        "frozen_reference_binding": binding,
        "frozen_reference_binding_sha256": digest,
        "source_fingerprint": hashlib.sha256(str(env_uri).encode("utf-8")).hexdigest(),
    }


# ── Policy dispatch ──────────────────────────────────────────────────────────

def test_policy_dispatch_routes_five_to_v1_and_one_to_four_to_v2():
    assert projection.policy_version_for_canonical_rows(_generic_three() * 1 + _generic_three()[:2]) == "v1"
    assert projection.policy_version_for_canonical_rows(_generic_three()) == "v2"
    assert projection.policy_version_for_canonical_rows(_generic_three()[:1]) == "v2"


def test_policy_dispatch_rejects_empty_and_over_capacity():
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.policy_version_for_canonical_rows([])
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.policy_version_for_canonical_rows(_generic_three() * 3)
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"
    with pytest.raises(projection.RunwayReferenceProjectionError):
        projection.policy_version_for_canonical_rows("not-a-list")


def test_project_authorized_environment_rejects_unknown_policy_version():
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_authorized_environment(
            _generic_three(), policy_version="v9",
            authorized_environment_ref_id=ENV_REF,
        )
    assert _code_of(exc_info) == "unavailable_policy_version"


def test_project_authorized_environment_defaults_to_v1():
    # Back-compat pin: callers that do not declare v2 keep v1 semantics, so a
    # three-row generic binding fails the v1 shape instead of projecting.
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_authorized_environment(
            _generic_three(), authorized_environment_ref_id=ENV_REF,
        )
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"


# ── Valid generic projections ────────────────────────────────────────────────

def test_valid_generic_three_selects_all_in_frozen_order():
    record = projection.project_authorized_environment(
        _generic_three(), policy_version="v2", authorized_environment_ref_id=ENV_REF,
    )
    assert record["projection_policy_version"] == "v2"
    assert record["selected_ref_ids"] == [C1_FACE, C2_GENERAL, ENV_REF]
    assert record["omitted_ref_ids"] == []
    assert record["omission_reason_codes"] == [projection.OMISSION_REASON_CODE_V2]
    assert record["setting_anchor_preserved"] is True
    assert record["per_character_coverage_preserved"] == [f"{C1}:1", f"{C2}:1"]
    assert record["provider_role_map"] == {C1_FACE: "reference", C2_GENERAL: "reference", ENV_REF: "reference"}
    assert set(record["provider_uris"]) == {C1_FACE, C2_GENERAL, ENV_REF}
    # Deterministic: same canonical bytes project the same digest.
    again = projection.project_authorized_environment(
        _generic_three(), policy_version="v2", authorized_environment_ref_id=ENV_REF,
    )
    assert again["projection_digest"] == record["projection_digest"]


def test_valid_environment_only_single_selects():
    rows = [_generic_three()[2]]
    record = projection.project_authorized_environment(
        rows, policy_version="v2", authorized_environment_ref_id=ENV_REF,
    )
    assert record["selected_ref_ids"] == [ENV_REF]
    assert record["per_character_coverage_preserved"] == []


def test_valid_generic_four_multi_character_selects_all():
    rows = [
        _grow("ref-gen-c1-face", "https://cdn.example.test/generic/c1f.png", "character", C1, "face", "character_face"),
        _grow("ref-gen-c1-gen", "https://cdn.example.test/generic/c1g.png", "character", C1, "general", "character_full"),
        _grow("ref-gen-c2-alt", "https://cdn.example.test/generic/c2a.png", "character", C2, "alternate_angle", "character_full"),
        _grow(ENV_REF, "https://cdn.example.test/generic/env.png", "setting", GEN_SETTING, "environment", "environment"),
    ]
    record = projection.project_authorized_environment(
        rows, policy_version="v2", authorized_environment_ref_id=ENV_REF,
    )
    assert record["selected_ref_ids"] == ["ref-gen-c1-face", "ref-gen-c1-gen", "ref-gen-c2-alt", ENV_REF]
    assert record["per_character_coverage_preserved"] == [f"{C1}:2", f"{C2}:1"]


# ── Generic rejections (every class fails closed) ────────────────────────────

def test_v2_rejects_five_rows_without_silent_selection():
    rows = _generic_three() + _generic_three()[:2]
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"


def test_v2_rejects_unapproved_and_noncanonical_rows():
    rows = _generic_three()
    rows[0] = dict(rows[0], approval_state="candidate")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "unapproved_reference"
    rows = _generic_three()
    rows[1] = dict(rows[1], canonical=False)
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "unapproved_reference"


def test_v2_rejects_duplicate_identities():
    rows = _generic_three()
    rows[1] = dict(rows[1], ref_id=C1_FACE)
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "ambiguous_selection"


def test_v2_rejects_missing_and_competing_setting_anchors():
    only_chars = _generic_three()[:2]
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(only_chars)
    assert _code_of(exc_info) == "missing_required_reference"
    rows = _generic_three() + [
        _grow("ref-gen-env-2", "https://cdn.example.test/generic/env2.png", "setting", "set-gen-002", "environment", "environment"),
    ]
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "ambiguous_environment_reference"


def test_v2_rejects_composition_unknown_and_mistyped_roles():
    rows = _generic_three()
    rows[0] = dict(rows[0], studio_role="storyboard", role="first")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "unsupported_provider_role"
    rows = _generic_three()
    rows[1] = dict(rows[1], studio_role="posing", role="reference", category="posing")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"
    rows = _generic_three()
    rows[2] = dict(rows[2], studio_role="wide", role="reference", category="wide")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"


def test_v2_rejects_missing_target_identity():
    rows = _generic_three()
    rows[0] = dict(rows[0], target_id="")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows)
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"


def test_v2_rejects_reordered_binding_and_tampered_fingerprints():
    rows = _generic_three()
    record = projection.project_runway_v2(rows)
    reordered = [rows[1], rows[0], rows[2]]
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(
            reordered, expected_binding=rows,
            source_fingerprints=dict(record["source_uri_fingerprints"]),
        )
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"
    tampered = dict(record["source_uri_fingerprints"])
    tampered[C1_FACE] = "0" * 64
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows, source_fingerprints=tampered)
    assert _code_of(exc_info) == "source_fingerprint_mismatch"
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows, approved_reference_ids=[C1_FACE, "ref-gen-missing"])
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"


def test_v2_rejects_local_uri_without_authorization(tmp_path):
    rows = _generic_three()
    rows[2] = dict(rows[2], uri="refs/local-env.png")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_runway_v2(rows, backend_root=tmp_path)
    assert _code_of(exc_info) == "unavailable_source_bytes"


def test_v2_materializes_authorized_local_bytes(tmp_path):
    local = tmp_path / "refs" / "local-env.png"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"generic-environment-bytes")
    rows = _generic_three()
    rows[2] = dict(rows[2], uri="refs/local-env.png")
    record = projection.project_runway_v2(rows, backend_root=tmp_path, allow_local_source_uris=True)
    assert record["provider_uris"][ENV_REF] == "refs/local-env.png"
    assert record["source_uri_fingerprints"][ENV_REF] == hashlib.sha256(b"generic-environment-bytes").hexdigest()


# ── Authorization binding (generic identities) ───────────────────────────────

def test_authorized_generic_binding_records_v2_identity():
    rows = _generic_three()
    record = projection.project_authorized_environment(
        rows, policy_version="v2", authorization=_gauth(rows),
        project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
        current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
        storyboard_version_id=GEN_VERSION,
        frozen_reference_binding_sha256=_gauth(rows)["frozen_reference_binding_sha256"],
        frozen_binding=_gauth(rows)["frozen_reference_binding"],
        expected_binding=rows,
    )
    assert record["projection_policy_version"] == "v2"
    assert record[projection.AUTHORIZATION_FIELD] == ENV_REF
    assert record["selected_ref_ids"] == [C1_FACE, C2_GENERAL, ENV_REF]
    assert record["authorization_identity"]["project_id"] == GEN_PROJECT


def test_generic_rejected_wrong_and_stale_authorizations_fail_closed():
    rows = _generic_three()
    good = _gauth(rows)
    rejected_auth = dict(good, rejected_environment_ref_ids=[C1_FACE])
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_authorized_environment(
            rows, policy_version="v2", authorization=rejected_auth,
            project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
            current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
            storyboard_version_id=GEN_VERSION,
            frozen_reference_binding_sha256=good["frozen_reference_binding_sha256"],
            frozen_binding=good["frozen_reference_binding"],
        )
    assert _code_of(exc_info) == "rejected_reference_present"
    # Authorizing a character row as the environment dies at the frozen-binding
    # check first (established code: reference_authorization_mismatch — the
    # binding's setting row no longer matches the selected authority).
    wrong_env = dict(good, authorized_environment_ref_id=C1_FACE)
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_authorized_environment(
            rows, policy_version="v2", authorization=wrong_env,
            project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
            current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
            storyboard_version_id=GEN_VERSION,
            frozen_reference_binding_sha256=good["frozen_reference_binding_sha256"],
            frozen_binding=good["frozen_reference_binding"],
        )
    assert _code_of(exc_info) == "reference_authorization_mismatch"
    stale = dict(good, frozen_reference_binding_sha256="0" * 64)
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_authorized_environment(
            rows, policy_version="v2", authorization=stale,
            project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
            current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
            storyboard_version_id=GEN_VERSION,
            frozen_reference_binding_sha256="0" * 64,
            frozen_binding=good["frozen_reference_binding"],
        )
    assert _code_of(exc_info) == "reference_authorization_mismatch"
    foreign = dict(good, project_id="project-other")
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.project_authorized_environment(
            rows, policy_version="v2", authorization=foreign,
            project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
            current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
            storyboard_version_id=GEN_VERSION,
            frozen_reference_binding_sha256=good["frozen_reference_binding_sha256"],
            frozen_binding=good["frozen_reference_binding"],
        )
    assert _code_of(exc_info) == "reference_authorization_mismatch"


# ── Reconstruction replay (generic) ──────────────────────────────────────────

def _freeze_generic(rows: list[dict], manifest_fingerprint: str = ""):
    return freeze_generation_contract(
        shot_id=GEN_SHOT,
        prompt="Approved generic prompt bytes: hold the exact cut.",
        reference_assets=[dict(row) for row in rows],
        parameters={"duration": 5, "aspect_ratio": "16:9"},
        manifest_fingerprint=manifest_fingerprint,
    )


def _manifest_record() -> dict:
    return {
        "manifest_fingerprint": "generic-manifest-fingerprint",
        "scene": {"scene_id": GEN_SCENE},
        "storyboard": {"storyboard_version_scene_id": GEN_SCENE, "storyboard_version": GEN_VERSION},
    }


def test_v2_reconstruction_replays_selection_and_digest():
    rows = _generic_three()
    contract = _freeze_generic(rows)
    record = projection.project_authorized_environment(
        projection.canonical_bindings_from_contract(contract.to_record()),
        policy_version="v2",
        authorization=_gauth(rows),
        project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
        current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
        storyboard_version_id=GEN_VERSION,
        frozen_reference_binding_sha256=_gauth(rows)["frozen_reference_binding_sha256"],
        frozen_binding=_gauth(rows)["frozen_reference_binding"],
    )
    rebuilt = projection.reconstruct_projected_request(
        contract.to_record(), _manifest_record(), record, dry_run=True,
    )
    assert rebuilt["projection"]["projection_digest"] == record["projection_digest"]
    assert [ref["uri"] for ref in rebuilt["runway_request"]["input"]["referenceImages"]] == [
        row["uri"] for row in rows
    ]
    tampered = copy.deepcopy(record)
    tampered["provider_uris"][C1_FACE] = "https://cdn.example.test/generic/other.png"
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.reconstruct_projected_request(contract.to_record(), _manifest_record(), tampered, dry_run=True)
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"
    tampered_version = copy.deepcopy(record)
    tampered_version["projection_policy_version"] = "v9"
    with pytest.raises(projection.RunwayReferenceProjectionError) as exc_info:
        projection.reconstruct_projected_request(contract.to_record(), _manifest_record(), tampered_version, dry_run=True)
    assert _code_of(exc_info) == "unavailable_policy_version"


# ── Mocked adapter boundary (generic identities, zero provider contact) ──────

def test_generic_binding_reaches_mocked_adapter_in_expected_shape(monkeypatch):
    calls: list = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, copy.deepcopy(payload)))
        raise AssertionError("generic adapter-gate test must not contact the provider")

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)
    rows = _generic_three()
    contract = _freeze_generic(rows)
    record = projection.project_authorized_environment(
        projection.canonical_bindings_from_contract(contract.to_record()),
        policy_version="v2",
        authorization=_gauth(rows),
        project_id=GEN_PROJECT, scene_id=GEN_SCENE, setting_id=GEN_SETTING,
        current_version_id=GEN_VERSION, approved_version_id=GEN_VERSION,
        storyboard_version_id=GEN_VERSION,
        frozen_reference_binding_sha256=_gauth(rows)["frozen_reference_binding_sha256"],
        frozen_binding=_gauth(rows)["frozen_reference_binding"],
    )
    adapter = RunwayRouterAdapter(ProviderConfig(
        provider_id="runway_router", name="Runway Router", enabled=True,
        is_simulated=False, api_key="test-key", api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"], capabilities=["video_generation", "model_routing"],
    ))
    failure, message, projected_refs, request_payload, execution = adapter._declared_reference_projection(
        metadata={projection.PROJECTION_METADATA_KEY: record},
        contract_record=contract.to_record(),
        manifest_record=_manifest_record(),
        router_config_id="studio-production-router",
        context_refs=[],
    )
    assert failure == "", message
    assert [ref["ref_id"] for ref in projected_refs] == [C1_FACE, C2_GENERAL, ENV_REF]
    assert [ref["image_url"] for ref in projected_refs] == [row["uri"] for row in rows]
    assert all(ref["role"] == "reference" for ref in projected_refs)
    wire = (request_payload.get("input") or {}).get("referenceImages") or []
    assert wire == [{"uri": row["uri"], "role": "reference"} for row in rows]
    assert execution["projection_policy_version"] == "v2"
    assert calls == []


def test_generic_authorization_path_reaches_mocked_adapter_without_provider_contact(monkeypatch):
    calls: list = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, copy.deepcopy(payload)))
        raise AssertionError("generic authorization-path test must not contact the provider")

    monkeypatch.setattr(runway_router_provider, "_runway_router_request", capture)
    rows = _generic_three()
    manifest = {
        "manifest_fingerprint": "",
        "scene": {"scene_id": GEN_SCENE},
        "storyboard": {"storyboard_version": GEN_VERSION, "storyboard_version_scene_id": GEN_SCENE},
        "shots": [{"shot_id": GEN_SHOT, "parameters": {}}],
        "batch": {},
    }
    manifest["manifest_fingerprint"] = recompute_manifest_fingerprint(manifest)
    contract = _freeze_generic(rows, manifest_fingerprint=manifest["manifest_fingerprint"])
    auth = _gauth(rows)
    adapter = RunwayRouterAdapter(ProviderConfig(
        provider_id="runway_router", name="Runway Router", enabled=True,
        is_simulated=False, api_key="test-key", api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"], capabilities=["video_generation", "model_routing"],
    ))
    metadata = {
        projection.AUTHORIZATION_METADATA_KEY: auth,
        "frozen_reference_binding": auth["frozen_reference_binding"],
        "creative_generation_identity": {"project_id": GEN_PROJECT},
    }
    failure, message, projected_refs, request_payload, execution = adapter._declared_reference_projection(
        metadata=metadata,
        contract_record=contract.to_record(),
        manifest_record=manifest,
        router_config_id="studio-production-router",
        context_refs=[],
    )
    assert failure == "", message
    assert [ref["ref_id"] for ref in projected_refs] == [C1_FACE, C2_GENERAL, ENV_REF]
    assert execution["projection_policy_version"] == "v2"
    # The replayed execution mirror carries routing identity only; the
    # creator authorization lives on the persisted projection record (pinned
    # by test_authorized_generic_binding_records_v2_identity above).
    assert calls == []