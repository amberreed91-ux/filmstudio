"""Narrow execution boundary for durable Scene 002 contract-only rendering.

This module validates already-authorized records; it never selects a screenplay,
creates creative decisions, or reads project state as a render source.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

MODE = "SCENE_002_CONTRACT_ONLY"
CONTRACT_VERSION = 1
SPAN_CONVENTION = "python_unicode_codepoint_offsets_v1"
AUTHORITY_VERSION = 1
SNAPSHOT_TTL_SECONDS = 300
RESULT_ONLY_PROJECT_FIELDS = frozenset({"execution_summary"})
PROTECTED_PROJECT_FIELDS = frozenset({"project_id", "script_text", "ownership", "creative_approvals", "approvals", "coverage_decisions", "storyboard", "scenes", "references", "reference_assets", "standing_corrections"})
JOB_RESULT_FIELDS = frozenset({"status", "progress", "provider_job_id", "output_payload", "error_message", "retry_count", "updated_at", "completed_at", "metadata"})
EXECUTION_PARAMETER_KEYS = ("aspect_ratio", "duration", "resolution", "seed", "audio", "negative_prompt", "reference_videos", "reference_audio", "keyframes", "content_moderation", "creative_parameters")
REFERENCE_BINDING_FIELDS = ("ref_id", "uri", "role", "target_type", "target_id", "category", "canonical", "approval_state", "source_kind", "kind")
REFERENCE_DIGEST_FIELD = "content_sha256"
AUTHORITY_MODELS = frozenset({"scene002_authority_v1"})
AUTHORITY_HMAC_ENV = "SCENE002_AUTHORITY_HMAC_KEY"


def _frozen_provider_parameters(generation_contract: dict[str, Any]) -> dict[str, Any]:
    """Mirror the exact provider-input projection used by RenderService.create_job."""
    from app.services.generation_contract import FrozenGenerationContract

    frozen = FrozenGenerationContract.from_record(generation_contract).payload()
    parameters = dict(frozen.get("creative_parameters") or {})
    parameters.update(
        duration=frozen.get("duration"),
        aspect_ratio=frozen.get("aspect_ratio"),
        resolution=frozen.get("resolution"),
        seed=frozen.get("seed"),
    )
    if frozen.get("content_moderation") is not None:
        parameters["content_moderation"] = frozen["content_moderation"]
    for key in ("reference_videos", "reference_audio", "keyframes"):
        parameters[key] = frozen.get(key) or []
    return parameters


def execution_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Fields whose exact values authorize one provider request."""
    authority = payload.get("source_authority") if isinstance(payload.get("source_authority"), dict) else {}
    return {
        "contract_version": payload.get("contract_version"),
        "creative_fingerprint": payload.get("creative_fingerprint"),
        "provider": payload.get("provider"),
        "model_policy": payload.get("model_policy"),
        "routing_policy_id": payload.get("routing_policy_id"),
        "router_config_id": payload.get("router_config_id"),
        "execution_parameters": payload.get("execution_parameters"),
        "provider_input_parameters": payload.get("provider_input_parameters"),
        "seed_policy": payload.get("seed_policy"),
        "retry_policy": payload.get("retry_policy"),
        "reference_content_sha256": payload.get("reference_content_sha256"),
        "creative_identity_sha256": payload.get("creative_identity_sha256"),
        "generation_contract_sha256": payload.get("generation_contract_sha256"),
        "authority_id": authority.get("authority_id"),
        "authority_decision_id": payload.get("authority_decision_id"),
    }


def _reference_digest_value(row: dict[str, Any]) -> str:
    value = row.get(REFERENCE_DIGEST_FIELD)
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise Scene002ContractError("Protected authority requires a pinned immutable reference content SHA-256")
    return value.lower()


def _project_without_result_bookkeeping(project: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(canonical_json(project))
    normalized.pop("updated_at", None)
    summary = normalized.get("execution_summary")
    if isinstance(summary, dict):
        for key in ("one_button_render_jobs", "scene_pipeline_assemblies", "scene_assembly_jobs"):
            summary.pop(key, None)
    return normalized


def assert_no_protected_project_mutation(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Allow only the existing render bookkeeping lists to change in a project merge."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise Scene002ContractError("Protected project write requires before/after snapshots")
    if before.get("project_id") != after.get("project_id") or not before.get("project_id"):
        raise Scene002ContractError("Protected project identity cannot change")
    if _project_without_result_bookkeeping(before) != _project_without_result_bookkeeping(after):
        raise Scene002ContractError("Protected project persistence rejects creative-state changes")
    for key in RESULT_ONLY_PROJECT_FIELDS:
        old_summary = before.get(key) if isinstance(before.get(key), dict) else {}
        new_summary = after.get(key) if isinstance(after.get(key), dict) else {}
        for list_key in ("one_button_render_jobs", "scene_pipeline_assemblies", "scene_assembly_jobs"):
            old_rows, new_rows = old_summary.get(list_key, []), new_summary.get(list_key, [])
            if not isinstance(old_rows, list) or not isinstance(new_rows, list):
                raise Scene002ContractError("Protected project bookkeeping must remain list-valued")
        if {key: value for key, value in old_summary.items() if key not in {"one_button_render_jobs", "scene_pipeline_assemblies", "scene_assembly_jobs"}} != {key: value for key, value in new_summary.items() if key not in {"one_button_render_jobs", "scene_pipeline_assemblies", "scene_assembly_jobs"}}:
            raise Scene002ContractError("Protected project persistence rejects non-render summary changes")


def validate_protected_job_transition(previous: Any, updated: Any) -> None:
    """Enforce result-only field mutations and a narrow durable state machine."""
    before = {key: getattr(previous, key, None) for key in JOB_RESULT_FIELDS}
    after = {key: getattr(updated, key, None) for key in JOB_RESULT_FIELDS}
    immutable = ("id", "project_id", "shot_id", "provider", "created_at", "retry_of", "batch_id", "continuity_context_injected", "continuity_review", "retry_advisory")
    changed = [key for key in immutable if getattr(previous, key, None) != getattr(updated, key, None)]
    if changed:
        raise Scene002ContractError(f"Protected persistence rejects immutable job changes: {changed}")
    if protected_input_payload_identity(previous.input_payload) != protected_input_payload_identity(updated.input_payload):
        raise Scene002ContractError("Protected render persistence rejects changes to its immutable creative input")
    validate_result_only_metadata(after["metadata"], previous=before["metadata"])
    old_retry = int(getattr(previous, "retry_count", 0) or 0)
    new_retry = int(getattr(updated, "retry_count", 0) or 0)
    old_status = str(before["status"] or "")
    new_status = str(after["status"] or "")
    if new_retry not in {old_retry, old_retry + 1}:
        raise Scene002ContractError("Protected persistence allows at most one ordinary retry increment")
    if new_retry != old_retry:
        if old_status != "failed" or new_status != "pending":
            raise Scene002ContractError("Protected retry can start only from a failed result and must preserve the contract")
        if getattr(updated, "recovery_status", "") != "retrying":
            raise Scene002ContractError("Protected ordinary retry must retain the same durable execution record")
    elif getattr(previous, "recovery_status", "") != getattr(updated, "recovery_status", "") and getattr(updated, "recovery_status", "") not in {"active", "recovered_terminal", "recovery_failed", "stale_recovered", "orphan_reconciled"}:
        raise Scene002ContractError("Protected persistence rejects non-result recovery status changes")
    elif old_status != new_status and new_status not in {
        "pending": {"rendering", "complete", "failed", "cancelled"},
        "rendering": {"complete", "failed", "cancelled", "needs_review"},
        "failed": set(),
        "complete": set(),
        "cancelled": set(),
        "needs_review": set(),
        "skipped": set(),
    }.get(old_status, set()):
        raise Scene002ContractError(f"Protected job state transition is not permitted: {old_status} -> {new_status}")



def assert_protected_seed_unchanged(storage: Any, project_id: str, shot_id: str) -> None:
    """Block mutable seed/lock changes once a protected job pins a shot."""
    if storage is None or not callable(getattr(storage, "list_jobs", None)):
        raise Scene002ContractError("Protected seed mutation check requires durable render-job storage")
    try:
        jobs = storage.list_jobs(project_id=project_id, limit=5000)
    except TypeError:
        jobs = storage.list_jobs(project_id=project_id)
    for job in jobs or []:
        if str(getattr(job, "shot_id", "")) == shot_id and is_contract_only(job):
            raise Scene002ContractError("Shot seed and lock are frozen by a Scene 002 execution contract")


RETRY_POLICY = "ordinary_retry_same_contract_only"


class Scene002ContractError(ValueError):
    """Protected execution proof is missing, invalid, or no longer current."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def project_has_protected_execution(project: Any, *, storage: Any = None) -> bool:
    """Find durable Scene 002 mode without inferring it from mutable project state."""
    if not isinstance(project, dict):
        return False
    project_id = str(project.get("project_id") or "")
    if not project_id or storage is None or not callable(getattr(storage, "list_jobs", None)):
        return False
    try:
        jobs = storage.list_jobs(project_id=project_id, limit=5000)
    except TypeError:
        jobs = storage.list_jobs(project_id=project_id)
    return any(is_contract_only(job) for job in jobs or [])


def project_revision_guard(project: dict[str, Any]) -> str:
    """Hash protected project creative state while excluding result bookkeeping."""
    if not isinstance(project, dict) or not str(project.get("project_id") or ""):
        raise Scene002ContractError("Protected render requires an existing project snapshot")
    summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
    protected_summary = {
        key: value for key, value in summary.items()
        if key not in {"one_button_render_jobs", "scene_pipeline_assemblies", "scene_assembly_jobs"}
    }
    protected = {key: value for key, value in project.items() if key != "execution_summary"}
    protected["execution_summary"] = protected_summary
    return digest(protected)


def sign_authority_record(record: dict[str, Any]) -> dict[str, Any]:
    """Trusted repository-side issuer helper; never exposed as a public route."""
    secret = os.getenv(AUTHORITY_HMAC_ENV, "")
    if not secret:
        raise Scene002ContractError("Scene 002 authority signing key is not configured")
    signed = {key: value for key, value in record.items() if key != "authority_signature"}
    signature = hmac.new(secret.encode("utf-8"), canonical_json(signed).encode("utf-8"), hashlib.sha256).hexdigest()
    return {**signed, "authority_signature": signature}


def validate_authority_record(record: Any) -> dict[str, Any]:
    """Validate the immutable, repository-persisted prospective authority record."""
    if not isinstance(record, dict):
        raise Scene002ContractError("Scene 002 source authority record is missing")
    secret = os.getenv(AUTHORITY_HMAC_ENV, "")
    if not secret:
        raise Scene002ContractError("Scene 002 authority verification key is not configured")
    required = (
        "authority_id", "authority_decision_id", "authority_signature", "approved_by", "approved_at",
        "project_id", "scene_id", "screenplay_representation_id", "screenplay_text",
        "setting_identity", "approved_setting_anchor",
        "screenplay_sha256", "scene_content", "scene_heading", "scene_sha256", "scene_span",
        "storyboard_version_id", "storyboard_relationship", "provider_policy",
        "model_policy", "seed_policy", "retry_policy", "reference_content_sha256",
        "authorized_creative_fingerprint", "coverage_decision_ids", "coverage_decisions",
        "execution_parameters_by_shot", "ordered_shot_ids", "reference_bindings",
        "coverage_contract", "creative_manifest", "generation_contracts_by_shot",
    )
    if any(record.get(key) in (None, "") for key in required):
        raise Scene002ContractError("Scene 002 source authority record is incomplete")
    signed = {key: value for key, value in record.items() if key != "authority_signature"}
    expected_signature = hmac.new(secret.encode("utf-8"), canonical_json(signed).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(record.get("authority_signature") or ""), expected_signature):
        raise Scene002ContractError("Scene 002 source authority signature is invalid")
    if record.get("decision_status") != "approved":
        raise Scene002ContractError("Scene 002 source authority is not explicitly approved")
    if record.get("authority_version") != AUTHORITY_VERSION or record.get("authority_type") != "scene002_authority_v1":
        raise Scene002ContractError("Scene 002 authority identity version or type is missing or unsupported")
    if not str(record.get("authority_id") or "").strip() or not str(record.get("authority_decision_id") or "").strip():
        raise Scene002ContractError("Scene 002 authority identity is missing")
    if record.get("scene_id") != "scene_002":
        raise Scene002ContractError("Contract-only execution is restricted to scene_002")
    if not isinstance(record["coverage_decision_ids"], list) or not record["coverage_decision_ids"]:
        raise Scene002ContractError("Authority must name the source/version-scoped coverage decisions")
    if not isinstance(record["coverage_decisions"], list) or not record["coverage_decisions"]:
        raise Scene002ContractError("Authority must persist the exact source/version-scoped coverage decisions")
    if not isinstance(record["execution_parameters_by_shot"], dict):
        raise Scene002ContractError("Authority must bind exact per-shot execution parameters")
    if not isinstance(record["ordered_shot_ids"], list) or not record["ordered_shot_ids"] or any(not isinstance(item, str) or not item.strip() for item in record["ordered_shot_ids"]):
        raise Scene002ContractError("Authority must bind an exact ordered storyboard shot list")
    if not isinstance(record["reference_bindings"], list) or not record["reference_bindings"]:
        raise Scene002ContractError("Authority must bind exact reference identities")
    if any(not isinstance(row, dict) or not row.get("ref_id") or not row.get("uri") for row in record["reference_bindings"]):
        raise Scene002ContractError("Authorized reference identities are incomplete")
    for row in record["reference_bindings"]:
        _reference_digest_value(row)
    if len({str(row["ref_id"]) for row in record["reference_bindings"]}) != len(record["reference_bindings"]):
        raise Scene002ContractError("Authorized reference identities contain duplicate IDs")
    if not isinstance(record["setting_identity"], dict) or not record["setting_identity"].get("setting_id"):
        raise Scene002ContractError("Authority must bind the exact setting identity")
    if not isinstance(record["approved_setting_anchor"], dict) or not record["approved_setting_anchor"].get("anchor_id"):
        raise Scene002ContractError("Authority must bind an explicitly approved setting anchor")
    if record["approved_setting_anchor"].get("setting_id") != record["setting_identity"].get("setting_id"):
        raise Scene002ContractError("Approved setting anchor does not belong to the authorized setting")
    if not isinstance(record["model_policy"], dict) or not record["model_policy"].get("policy_id"):
        raise Scene002ContractError("Authority must bind an explicit model or model-routing policy")
    if not isinstance(record["storyboard_relationship"], dict) or not record["storyboard_relationship"].get("relationship"):
        raise Scene002ContractError("Authority must define the screenplay-to-storyboard relationship")
    if not isinstance(record["screenplay_text"], str) or not isinstance(record["scene_content"], str):
        raise Scene002ContractError("Authorized screenplay and scene content must be exact text")
    screenplay_bytes = record["screenplay_text"].encode("utf-8")
    scene_bytes = record["scene_content"].encode("utf-8")
    if hashlib.sha256(screenplay_bytes).hexdigest() != record["screenplay_sha256"]:
        raise Scene002ContractError("Authorized screenplay bytes do not match their SHA-256 identity")
    if hashlib.sha256(scene_bytes).hexdigest() != record["scene_sha256"]:
        raise Scene002ContractError("Authorized scene bytes do not match their SHA-256 identity")
    span = record["scene_span"]
    if not isinstance(span, dict) or span.get("convention") != SPAN_CONVENTION:
        raise Scene002ContractError("Authorized scene span convention is missing or unsupported")
    start, end = span.get("start"), span.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise Scene002ContractError("Authorized scene span offsets are malformed")
    if end - start != len(record["scene_content"]) or record["screenplay_text"][start:end] != record["scene_content"]:
        raise Scene002ContractError("Authorized scene span does not match the exact screenplay bytes")
    if span.get("sha256") != record["scene_sha256"]:
        raise Scene002ContractError("Authorized scene span hash is inconsistent")
    policy = record["provider_policy"]
    if not isinstance(policy, dict) or policy.get("provider") != "runway_router" or not policy.get("routing_policy_id") or not policy.get("router_config_id"):
        raise Scene002ContractError("Authority must bind the audited provider and exact routing configuration")
    if record["retry_policy"] != RETRY_POLICY:
        raise Scene002ContractError("Scene 002 authority permits only ordinary retries with the same contract")
    seed_policy = record["seed_policy"]
    if not isinstance(seed_policy, dict) or seed_policy.get("mode") not in {"fixed", "provider_random_authorized"}:
        raise Scene002ContractError("Scene 002 seed policy is missing or unsupported")
    if not isinstance(record["reference_content_sha256"], dict):
        raise Scene002ContractError("Authority reference content identities are malformed")
    if set(record["reference_content_sha256"]) != {str(row["ref_id"]) for row in record["reference_bindings"]}:
        raise Scene002ContractError("Authority reference digests do not cover the exact authorized reference bindings")
    if any(record["reference_content_sha256"].get(str(row["ref_id"])) != _reference_digest_value(row) for row in record["reference_bindings"]):
        raise Scene002ContractError("Reference content hashes do not match immutable digests pinned to the bindings")
    if set(record["execution_parameters_by_shot"]) != set(record["ordered_shot_ids"]):
        raise Scene002ContractError("Authority execution parameters do not cover exactly the authorized shots")
    if set(record["generation_contracts_by_shot"]) != set(record["ordered_shot_ids"]):
        raise Scene002ContractError("Authority frozen contracts do not cover exactly the authorized shots")
    from app.services.shot_manifest import recompute_manifest_fingerprint
    from app.services.scene_coverage_contract import verify_scene_coverage_contract
    manifest = record["creative_manifest"]
    if not isinstance(manifest, dict) or recompute_manifest_fingerprint(manifest) != record["authorized_creative_fingerprint"]:
        raise Scene002ContractError("Authority manifest does not match its authorized creative fingerprint")
    if manifest.get("scene", {}).get("project_id") != record["project_id"] or manifest.get("scene", {}).get("scene_id") != record["scene_id"]:
        raise Scene002ContractError("Authority manifest is scoped to a different project or scene")
    if manifest.get("storyboard", {}).get("storyboard_version") != record["storyboard_version_id"]:
        raise Scene002ContractError("Authority manifest storyboard version does not match its identity")
    if [str(row.get("shot_id") or "") for row in manifest.get("shots", []) if isinstance(row, dict)] != record["ordered_shot_ids"]:
        raise Scene002ContractError("Authority manifest shot order does not match its ordered shot identity")
    coverage = verify_scene_coverage_contract(record["coverage_contract"])
    if coverage.get("canonical_script_text") != record["screenplay_text"] or coverage.get("scene_content") != record["scene_content"]:
        raise Scene002ContractError("Authority coverage does not contain the exact frozen screenplay and scene")
    for shot_id in record["ordered_shot_ids"]:
        from app.services.generation_contract import FrozenGenerationContract
        frozen = FrozenGenerationContract.from_record(record["generation_contracts_by_shot"][shot_id])
        rows = [row for row in manifest["shots"] if row.get("shot_id") == shot_id]
        if len(rows) != 1 or frozen.shot_id != shot_id or frozen.prompt != rows[0].get("shot_prompt"):
            raise Scene002ContractError("Authority frozen shot contract differs from its manifest prompt identity")
    return record


def local_reference_sha256(uri: str, *, backend_root: Path) -> str:
    """Hash immutable local reference bytes from explicit backend mounts only."""
    from app.services.runway_ephemeral_upload import RunwayEphemeralUploadError, resolve_canonical_bytes

    try:
        data = resolve_canonical_bytes(uri, backend_root=backend_root)
    except RunwayEphemeralUploadError as exc:
        raise Scene002ContractError("Protected references require locally verifiable mounted bytes") from exc
    return hashlib.sha256(data).hexdigest()


def build_execution_contract(
    *, authority: dict[str, Any], project_id: str, scene_id: str,
    project_guard_sha256: str, manifest: dict[str, Any], entry: dict[str, Any],
    generation_contract: dict[str, Any], provider: str, router_config_id: str,
    reference_digests: dict[str, str],
) -> dict[str, Any]:
    authority = validate_authority_record(authority)
    if authority["project_id"] != project_id or authority["scene_id"] != scene_id:
        raise Scene002ContractError("Source authority is scoped to a different project or scene")
    if provider != authority["provider_policy"]["provider"] or router_config_id != authority["provider_policy"]["router_config_id"]:
        raise Scene002ContractError("Selected provider or router configuration is outside the authority")
    if reference_digests != authority["reference_content_sha256"]:
        raise Scene002ContractError("Resolved reference bytes do not match the authorized reference identities")
    prepared_binding = entry.get("reference_binding")
    expected_binding = authority["reference_bindings"]
    identity_fields = ("ref_id", "uri", "role", "target_type", "target_id", "category", "canonical", "approval_state", "source_kind", "kind")
    project_binding = [
        {key: row.get(key) for key in identity_fields if key in row}
        for row in prepared_binding
    ] if isinstance(prepared_binding, list) else None
    authority_binding = [
        {key: row.get(key) for key in identity_fields if key in row}
        for row in expected_binding
    ]
    if project_binding != authority_binding:
        raise Scene002ContractError("Prepared reference identity, order, role, or target differs from explicit authority")
    coverage = entry.get("scene_coverage")
    manifest_scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
    from app.services.shot_manifest import recompute_manifest_fingerprint
    from app.services.scene_coverage_contract import verify_scene_coverage_contract
    from app.services.generation_contract import FrozenGenerationContract
    try:
        frozen_contract = FrozenGenerationContract.from_record(generation_contract)
        verified_coverage = verify_scene_coverage_contract(coverage)
        manifest_fingerprint_valid = recompute_manifest_fingerprint(manifest) == manifest.get("manifest_fingerprint")
    except (TypeError, ValueError) as exc:
        raise Scene002ContractError(f"Prepared frozen contract or coverage proof is invalid: {exc}") from exc
    if not manifest_fingerprint_valid or verified_coverage != coverage:
        raise Scene002ContractError("Prepared manifest or coverage identity failed verification")
    if (
        authority["authorized_creative_fingerprint"] != manifest.get("manifest_fingerprint")
        or manifest_scene.get("project_id") != project_id
        or manifest_scene.get("scene_id") != scene_id
        or manifest_scene.get("canonical_script_sha256") != authority["screenplay_sha256"]
        or manifest_scene.get("scene_content_sha256") != authority["scene_sha256"]
        or manifest_scene.get("scene_source_start") != authority["scene_span"]["start"]
        or manifest_scene.get("scene_source_end") != authority["scene_span"]["end"]
        or not isinstance(coverage, dict)
        or coverage.get("canonical_script_text") != authority["screenplay_text"]
        or coverage.get("scene_content") != authority["scene_content"]
        or coverage.get("script_version_id") != authority["screenplay_representation_id"]
        or coverage.get("creator_decisions") != authority["coverage_decisions"]
        or sorted(str(row.get("decision_version_id") or "") for row in coverage.get("creator_decisions", []) if isinstance(row, dict)) != sorted(str(item) for item in authority["coverage_decision_ids"])
        or list(authority.get("ordered_shot_ids") or []) != [str(row.get("shot_id") or "") for row in manifest.get("shots", [])]
        or manifest.get("manifest_fingerprint") != recompute_manifest_fingerprint(manifest)
        or frozen_contract.shot_id != str(entry.get("shot_id") or "")
        or frozen_contract.prompt != str(entry.get("prompt") or "")
        or generation_contract.get("payload", {}).get("dialogue_handoff") != entry.get("dialogue_handoff")
        or frozen_contract.payload().get("scene_coverage") != coverage
        or frozen_contract.payload().get("scene_coverage_shot") != entry.get("shot_coverage")
    ):
        raise Scene002ContractError("Prepared creative input does not match the authorized screenplay and scene span")
    if manifest.get("storyboard", {}).get("storyboard_version") != authority["storyboard_version_id"]:
        raise Scene002ContractError("Prepared storyboard version is outside the source authority")
    setting_id = str(authority["setting_identity"].get("setting_id") or "")
    setting_refs = [row for row in (prepared_binding or []) if isinstance(row, dict) and row.get("target_type") == "setting" and str(row.get("target_id") or "") == setting_id]
    anchor_ref_id = str(authority["approved_setting_anchor"].get("reference_id") or "")
    if len(setting_refs) != 1 or not anchor_ref_id or setting_refs[0].get("ref_id") != anchor_ref_id:
        raise Scene002ContractError("Prepared setting reference is not the explicitly authorized anchor")
    authorized_parameters = authority["execution_parameters_by_shot"].get(str(entry.get("shot_id") or ""))
    actual_parameters = {
        key: generation_contract.get("payload", {}).get(key)
        for key in ("aspect_ratio", "duration", "resolution", "seed", "audio", "negative_prompt", "reference_videos", "reference_audio", "keyframes", "content_moderation", "creative_parameters")
    }
    if not isinstance(authorized_parameters, dict) or authorized_parameters != actual_parameters:
        raise Scene002ContractError("Execution parameters are outside the prospective authority decision")
    creator_decisions = coverage.get("creator_decisions") if isinstance(coverage.get("creator_decisions"), list) else []
    decision_ids = sorted({str(row.get("decision_version_id") or "") for row in creator_decisions if isinstance(row, dict) and row.get("decision_version_id")})
    if sorted(str(item) for item in authority["coverage_decision_ids"]) != decision_ids:
        raise Scene002ContractError("Coverage decision identities differ from the source authority")
    if canonical_json(authority["coverage_decisions"]) != canonical_json(creator_decisions):
        raise Scene002ContractError("Frozen coverage decision contents differ from the source authority")
    if authority["generation_contracts_by_shot"].get(str(entry.get("shot_id") or "")) != generation_contract:
        raise Scene002ContractError("Prepared frozen shot contract is not explicitly pinned by source authority")
    if authority["creative_manifest"] != manifest:
        raise Scene002ContractError("Prepared manifest is not the exact authorized creative manifest")
    if authority["coverage_contract"] != coverage:
        raise Scene002ContractError("Prepared coverage is not the exact authorized coverage contract")
    payload = {
        "mode": MODE,
        "contract_version": CONTRACT_VERSION,
        "project_id": project_id,
        "scene_id": scene_id,
        "shot_id": str(entry.get("shot_id") or ""),
        "source_authority": authority,
        "project_revision_guard_sha256": project_guard_sha256,
        "creative_manifest": manifest,
        "creative_fingerprint": str(manifest.get("manifest_fingerprint") or ""),
        "creative_identity_sha256": digest({
            "screenplay_sha256": authority["screenplay_sha256"],
            "scene_sha256": authority["scene_sha256"],
            "scene_span": authority["scene_span"],
            "storyboard_version_id": authority["storyboard_version_id"],
            "manifest_fingerprint": manifest.get("manifest_fingerprint"),
            "ordered_shot_ids": [str(row.get("shot_id") or "") for row in manifest.get("shots", [])],
            "ordered_prompts": [str(row.get("shot_prompt") or "") for row in manifest.get("shots", [])],
            "dialogue_handoff": entry.get("dialogue_handoff"),
            "coverage_contract": coverage,
            "reference_content_sha256": reference_digests,
            "setting_identity": authority["setting_identity"],
            "approved_setting_anchor": authority["approved_setting_anchor"],
            "reference_bindings": authority["reference_bindings"],
        }),
        "generation_contract": generation_contract,
        "generation_contract_sha256": str(generation_contract.get("sha256") or ""),
        "provider_input_parameters": _frozen_provider_parameters(generation_contract),
        "setting_identity": authority["setting_identity"],
        "approved_setting_anchor": authority["approved_setting_anchor"],
        "reference_bindings": authority["reference_bindings"],
        "dialogue_handoff": entry.get("dialogue_handoff"),
        "coverage_contract": coverage,
        "ordered_shot_ids": [str(row.get("shot_id") or "") for row in manifest.get("shots", [])],
        "ordered_prompts": [str(row.get("shot_prompt") or "") for row in manifest.get("shots", [])],
        "storyboard_version_id": authority["storyboard_version_id"],
        "provider": provider,
        "model_policy": authority["model_policy"],
        "routing_policy_id": authority["provider_policy"]["routing_policy_id"],
        "router_config_id": router_config_id,
        "execution_parameters": {
            key: generation_contract.get("payload", {}).get(key)
            for key in ("aspect_ratio", "duration", "resolution", "seed", "audio", "negative_prompt", "reference_videos", "reference_audio", "keyframes", "content_moderation", "creative_parameters")
        },
        "seed_policy": authority["seed_policy"],
        "retry_policy": RETRY_POLICY,
        "reference_content_sha256": reference_digests,
        "authority_decision_id": authority["authority_decision_id"],
    }
    payload["execution_identity_sha256"] = digest(execution_envelope(payload))
    if not payload["shot_id"] or not payload["creative_fingerprint"]:
        raise Scene002ContractError("Prepared shot or creative fingerprint is missing")
    fingerprint = digest(payload)
    return {"payload": payload, "execution_fingerprint": fingerprint}


def verify_authorized_execution_components(payload: Any, authority: Any) -> None:
    """Cross-check each frozen creative and execution identity against authority."""
    if not isinstance(payload, dict) or not isinstance(authority, dict):
        raise Scene002ContractError("Protected execution or source authority identity is missing")
    manifest = payload.get("creative_manifest") if isinstance(payload.get("creative_manifest"), dict) else {}
    scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
    shots = manifest.get("shots") if isinstance(manifest.get("shots"), list) else []
    shot_id = str(payload.get("shot_id") or "")
    rows = [row for row in shots if isinstance(row, dict) and row.get("shot_id") == shot_id]
    contract = payload.get("generation_contract") if isinstance(payload.get("generation_contract"), dict) else {}
    contract_payload = contract.get("payload") if isinstance(contract.get("payload"), dict) else {}
    coverage = payload.get("coverage_contract") if isinstance(payload.get("coverage_contract"), dict) else {}
    span = authority.get("scene_span") if isinstance(authority.get("scene_span"), dict) else {}
    expected_execution = authority.get("execution_parameters_by_shot", {}).get(shot_id) if isinstance(authority.get("execution_parameters_by_shot"), dict) else None
    bindings = payload.get("reference_bindings")
    references = contract_payload.get("references")
    if not isinstance(bindings, list) or not isinstance(references, list):
        raise Scene002ContractError("Protected reference identities cannot be recovered")
    contract_bindings = [
        {"ref_id": row.get("ref_id"), "uri": row.get("uri"), "role": row.get("studio_role"),
         "target_type": row.get("target_type"), "target_id": row.get("target_id"),
         "category": row.get("category"), "canonical": row.get("canonical"),
         "approval_state": row.get("approval_state"), "source_kind": row.get("source_kind"),
         **({"kind": row["kind"]} if row.get("kind") else {})}
        for row in references if isinstance(row, dict) and row.get("source") == "canonical_reference_binding"
    ]
    authority_bindings = [
        {"ref_id": row.get("ref_id"), "uri": row.get("uri"), "role": row.get("role"),
         "target_type": row.get("target_type"), "target_id": row.get("target_id"),
         "category": row.get("category"), "canonical": row.get("canonical"),
         "approval_state": row.get("approval_state"), "source_kind": row.get("source_kind"),
         **({"kind": row["kind"]} if row.get("kind") else {})}
        for row in authority.get("reference_bindings", []) if isinstance(row, dict)
    ]
    prompt = rows[0].get("shot_prompt") if len(rows) == 1 else None
    expected_dialogue = rows[0].get("dialogue_handoff") if len(rows) == 1 else None
    if (
        not isinstance(authority.get("reference_bindings"), list)
        or not isinstance(authority.get("reference_content_sha256"), dict)
        or any(
            not isinstance(row, dict)
            or not row.get("ref_id")
            or _reference_digest_value(row) != authority.get("reference_content_sha256", {}).get(str(row.get("ref_id") or ""))
            for row in authority.get("reference_bindings", [])
        )
    ):
        raise Scene002ContractError("Protected reference content identities are missing or inconsistent")
    if (
        payload.get("project_id") != authority.get("project_id")
        or payload.get("scene_id") != authority.get("scene_id")
        or scene.get("project_id") != authority.get("project_id")
        or scene.get("scene_id") != authority.get("scene_id")
        or scene.get("canonical_script_sha256") != authority.get("screenplay_sha256")
        or coverage.get("canonical_script_sha256") != authority.get("screenplay_sha256")
        or coverage.get("canonical_script_text") != authority.get("screenplay_text")
        or coverage.get("script_version_id") != authority.get("screenplay_representation_id")
        or scene.get("script_version_id") != authority.get("screenplay_representation_id")
        or scene.get("scene_content_sha256") != authority.get("scene_sha256")
        or coverage.get("scene_content_sha256") != authority.get("scene_sha256")
        or coverage.get("scene_content") != authority.get("scene_content")
        or scene.get("scene_source_start") != span.get("start")
        or scene.get("scene_source_end") != span.get("end")
        or payload.get("storyboard_version_id") != authority.get("storyboard_version_id")
        or manifest.get("storyboard", {}).get("storyboard_version") != authority.get("storyboard_version_id")
        or payload.get("creative_fingerprint") != authority.get("authorized_creative_fingerprint")
        or payload.get("ordered_shot_ids") != authority.get("ordered_shot_ids")
        or payload.get("ordered_shot_ids") != [str(row.get("shot_id") or "") for row in shots if isinstance(row, dict)]
        or payload.get("ordered_prompts") != [str(row.get("shot_prompt") or "") for row in shots if isinstance(row, dict)]
        or len(rows) != 1
        or prompt != contract_payload.get("prompt")
        or payload.get("dialogue_handoff") != expected_dialogue
        or payload.get("dialogue_handoff") != contract_payload.get("dialogue_handoff")
        or payload.get("coverage_contract") != contract_payload.get("scene_coverage")
        or coverage.get("creator_decisions") != authority.get("coverage_decisions")
        or sorted(str(row.get("decision_version_id") or "") for row in coverage.get("creator_decisions", []) if isinstance(row, dict)) != sorted(str(value) for value in authority.get("coverage_decision_ids", []))
        or payload.get("setting_identity") != authority.get("setting_identity")
        or payload.get("approved_setting_anchor") != authority.get("approved_setting_anchor")
        or bindings != authority.get("reference_bindings")
        or contract_bindings != authority_bindings
        or any(
            not isinstance(row, dict) or row.get(REFERENCE_DIGEST_FIELD) != authority.get("reference_content_sha256", {}).get(str(row.get("ref_id") or ""))
            for row in bindings
        )
        or payload.get("reference_content_sha256") != authority.get("reference_content_sha256")
        or payload.get("provider") != authority.get("provider_policy", {}).get("provider")
        or payload.get("model_policy") != authority.get("model_policy")
        or payload.get("provider_input_parameters") != _frozen_provider_parameters(contract)
        or payload.get("routing_policy_id") != authority.get("provider_policy", {}).get("routing_policy_id")
        or payload.get("router_config_id") != authority.get("provider_policy", {}).get("router_config_id")
        or payload.get("seed_policy") != authority.get("seed_policy")
        or payload.get("retry_policy") != authority.get("retry_policy")
        or payload.get("execution_parameters") != expected_execution
        or payload.get("execution_identity_sha256") != digest(execution_envelope(payload))
        or payload.get("creative_manifest") != authority.get("creative_manifest")
        or payload.get("coverage_contract") != authority.get("coverage_contract")
        or contract != authority.get("generation_contracts_by_shot", {}).get(shot_id)
    ):
        raise Scene002ContractError("Protected creative or execution identity differs from explicit source authority")


def verify_execution_contract(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        raise Scene002ContractError("Durable Scene 002 execution contract is missing")
    payload = record["payload"]
    if payload.get("mode") != MODE or payload.get("contract_version") != CONTRACT_VERSION:
        raise Scene002ContractError("Unsupported Scene 002 execution contract mode or version")
    if record.get("execution_fingerprint") != digest(payload):
        raise Scene002ContractError("Complete execution fingerprint verification failed")
    if payload.get("execution_identity_sha256") != digest(execution_envelope(payload)):
        raise Scene002ContractError("Complete immutable execution-envelope fingerprint verification failed")
    authority = validate_authority_record(payload.get("source_authority"))
    if payload.get("authority_decision_id") != authority.get("authority_decision_id"):
        raise Scene002ContractError("Execution contract authority identity is inconsistent")
    verify_authorized_execution_components(payload, authority)
    if payload.get("retry_policy") != RETRY_POLICY:
        raise Scene002ContractError("Protected retry policy was changed")
    authority = payload.get("source_authority") if isinstance(payload.get("source_authority"), dict) else {}
    shot_id = str(payload.get("shot_id") or "")
    execution_parameters = payload.get("execution_parameters")
    if (
        payload.get("routing_policy_id") != authority.get("provider_policy", {}).get("routing_policy_id")
        or payload.get("seed_policy") != authority.get("seed_policy")
        or not isinstance(execution_parameters, dict)
        or execution_parameters != authority.get("execution_parameters_by_shot", {}).get(shot_id)
    ):
        raise Scene002ContractError("Provider routing, seed, or execution parameters are outside source authority")
    expected_creative_identity = digest({
        "screenplay_sha256": authority.get("screenplay_sha256"),
        "scene_sha256": authority.get("scene_sha256"),
        "scene_span": authority.get("scene_span"),
        "storyboard_version_id": authority.get("storyboard_version_id"),
        "manifest_fingerprint": payload.get("creative_fingerprint"),
        "ordered_shot_ids": payload.get("ordered_shot_ids"),
        "ordered_prompts": payload.get("ordered_prompts"),
        "dialogue_handoff": payload.get("dialogue_handoff"),
        "coverage_contract": payload.get("coverage_contract"),
        "reference_content_sha256": payload.get("reference_content_sha256"),
        "setting_identity": payload.get("setting_identity"),
        "approved_setting_anchor": payload.get("approved_setting_anchor"),
        "reference_bindings": payload.get("reference_bindings"),
    })
    if payload.get("creative_identity_sha256") != expected_creative_identity:
        raise Scene002ContractError("Protected creative identity digest does not match the signed authority and frozen inputs")
    if (
        payload.get("project_id") != authority.get("project_id")
        or payload.get("scene_id") != authority.get("scene_id")
        or payload.get("storyboard_version_id") != authority.get("storyboard_version_id")
        or payload.get("provider") != authority.get("provider_policy", {}).get("provider")
        or payload.get("router_config_id") != authority.get("provider_policy", {}).get("router_config_id")
        or payload.get("model_policy") != authority.get("model_policy")
        or payload.get("reference_content_sha256") != authority.get("reference_content_sha256")
        or payload.get("setting_identity") != authority.get("setting_identity")
        or payload.get("approved_setting_anchor") != authority.get("approved_setting_anchor")
        or payload.get("reference_bindings") != authority.get("reference_bindings")
        or list(payload.get("ordered_shot_ids") or []) != list(authority.get("ordered_shot_ids") or [])
    ):
        raise Scene002ContractError("Execution identity is not a subset of its signed source authority")
    manifest = payload.get("creative_manifest") if isinstance(payload.get("creative_manifest"), dict) else {}
    authority = payload.get("source_authority") if isinstance(payload.get("source_authority"), dict) else {}
    if payload.get("creative_fingerprint") != authority.get("authorized_creative_fingerprint") or payload.get("creative_fingerprint") != manifest.get("manifest_fingerprint"):
        raise Scene002ContractError("Authorized creative fingerprint does not match the persisted manifest")
    manifest = payload.get("creative_manifest") if isinstance(payload.get("creative_manifest"), dict) else {}
    from app.services.shot_manifest import recompute_manifest_fingerprint
    from app.services.scene_coverage_contract import verify_scene_coverage_contract
    from app.services.generation_contract import FrozenGenerationContract
    try:
        frozen = FrozenGenerationContract.from_record(payload.get("generation_contract"))
        coverage = verify_scene_coverage_contract(payload.get("coverage_contract"))
    except (TypeError, ValueError) as exc:
        raise Scene002ContractError(f"Persisted creative proof cannot be verified: {exc}") from exc
    scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
    authorized_screenplay = authority.get("screenplay_text")
    if not isinstance(authorized_screenplay, str) or hashlib.sha256(authorized_screenplay.encode("utf-8")).hexdigest() != authority.get("screenplay_sha256"):
        raise Scene002ContractError("Authorized screenplay bytes do not match their identity")
    span = authority.get("scene_span") if isinstance(authority.get("scene_span"), dict) else {}
    if (
        span.get("convention") != SPAN_CONVENTION
        or not isinstance(span.get("start"), int)
        or not isinstance(span.get("end"), int)
        or span.get("start", -1) < 0
        or span.get("end", 0) <= span.get("start", 0)
        or authorized_screenplay[span["start"]:span["end"]] != authority.get("scene_content")
        or hashlib.sha256(str(authority.get("scene_content") or "").encode("utf-8")).hexdigest() != authority.get("scene_sha256")
    ):
        raise Scene002ContractError("Authorized scene identity or screenplay span is invalid")
    if (
        recompute_manifest_fingerprint(manifest) != manifest.get("manifest_fingerprint")
        or scene.get("canonical_script_sha256") != authority.get("screenplay_sha256")
        or scene.get("scene_content_sha256") != authority.get("scene_sha256")
        or scene.get("scene_source_start") != authority.get("scene_span", {}).get("start")
        or scene.get("scene_source_end") != authority.get("scene_span", {}).get("end")
        or scene.get("scene_id") != payload.get("scene_id")
        or coverage != payload.get("coverage_contract")
        or frozen.prompt != next((row.get("shot_prompt") for row in manifest.get("shots", []) if row.get("shot_id") == payload.get("shot_id")), None)
        or frozen.payload().get("scene_coverage_shot") != next((row.get("scene_coverage_shot") for row in manifest.get("shots", []) if row.get("shot_id") == payload.get("shot_id")), None)
        or list(payload.get("ordered_shot_ids") or []) != [str(row.get("shot_id") or "") for row in manifest.get("shots", [])]
        or list(payload.get("ordered_prompts") or []) != [str(row.get("shot_prompt") or "") for row in manifest.get("shots", [])]
        or manifest.get("storyboard", {}).get("storyboard_version") != payload.get("storyboard_version_id")
        or frozen.payload().get("dialogue_handoff") != payload.get("dialogue_handoff")
        or frozen.payload().get("scene_coverage") != coverage
        or payload.get("generation_contract_sha256") != payload.get("generation_contract", {}).get("sha256")
        or not isinstance(payload.get("provider_input_parameters"), dict)
        or payload.get("provider_input_parameters") != _frozen_provider_parameters(payload.get("generation_contract"))
        or payload.get("provider_input_parameters", {}).get("prompt") not in (None, frozen.prompt)
        or payload.get("provider_input_parameters", {}).get("negative_prompt") != frozen.negative_prompt
        or payload.get("provider_input_parameters", {}).get("seed") != frozen.seed
        or payload.get("provider_input_parameters", {}).get("duration") != frozen.duration
        or payload.get("provider_input_parameters", {}).get("aspect_ratio") != frozen.aspect_ratio
        or payload.get("provider_input_parameters", {}).get("resolution") != frozen.resolution
        or payload.get("provider_input_parameters", {}).get("audio_intent") is not frozen.audio
        or payload.get("provider_input_parameters", {}).get("dialogue_handoff") != payload.get("dialogue_handoff")
        or payload.get("provider_input_parameters", {}).get("scene_coverage") != payload.get("coverage_contract")
        or payload.get("provider_input_parameters", {}).get("scene_coverage_shot") != frozen.payload().get("scene_coverage_shot")
        or [
            {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind") if key in row}
            for row in payload.get("provider_input_parameters", {}).get("frozen_reference_binding", [])
            if isinstance(row, dict)
        ] != [
            {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind") if key in row}
            for row in payload.get("reference_bindings", [])
            if isinstance(row, dict)
        ]
    ):
        raise Scene002ContractError("Persisted Scene 002 creative identity does not match its screenplay, manifest, coverage, or dialogue proof")
    return payload


_IMMUTABLE_JOB_METADATA_KEYS = (
    "execution_mode", "scene002_execution_contract", "source_authority_id",
    "creative_generation_contract", "creative_generation_manifest",
    "creative_manifest_fingerprint", "creative_contract_digest",
    "creative_generation_identity", "frozen_reference_binding",
    "frozen_reference_binding_sha256", "creative_dialogue_handoff",
)
_RESULT_METADATA_KEYS = frozenset({
    *_IMMUTABLE_JOB_METADATA_KEYS,
    "pipeline_reliability", "runtime_status", "scene002_contract_failure",
    "router_execution", "provider_payload_metadata", "provider_failure",
    "render_lineage_failure",
    "reference_asset_failure", "persistence_failure",
})


def validate_result_only_metadata(metadata: Any, *, previous: dict[str, Any] | None = None) -> None:
    """Allow frozen creative proof plus narrowly scoped render bookkeeping only."""
    if not isinstance(metadata, dict):
        raise Scene002ContractError("Protected job metadata is missing")
    unexpected = set(metadata) - _RESULT_METADATA_KEYS
    if unexpected:
        raise Scene002ContractError(f"Protected persistence rejects non-result metadata fields: {sorted(unexpected)}")
    required = set(_IMMUTABLE_JOB_METADATA_KEYS)
    if not required.issubset(metadata):
        raise Scene002ContractError("Protected persistence requires the complete immutable creative proof")
    reliability = metadata.get("pipeline_reliability")
    if reliability is not None and (
        not isinstance(reliability, dict)
        or not isinstance(reliability.get("phase_timing", {}), dict)
        or set(reliability) - {"correlation_id", "idempotency_key", "idempotency_key_source", "created_at", "phase_timing", "failure_location"}
    ):
        raise Scene002ContractError("Protected persistence rejects non-result reliability metadata")
    if previous is not None:
        changed = [key for key in _IMMUTABLE_JOB_METADATA_KEYS if previous.get(key) != metadata.get(key)]
        if changed:
            raise Scene002ContractError(f"Protected persistence rejects changes to immutable metadata: {changed}")
        for key in _RESULT_METADATA_KEYS - set(_IMMUTABLE_JOB_METADATA_KEYS):
            if key in metadata and key in previous and key not in {"pipeline_reliability", "router_execution", "provider_payload_metadata", "provider_failure", "runtime_status", "scene002_contract_failure", "persistence_failure"} and previous[key] != metadata[key]:
                raise Scene002ContractError(f"Protected persistence rejects changes to result metadata field {key}")
        if "pipeline_reliability" in previous and "pipeline_reliability" in metadata:
            before = dict(previous["pipeline_reliability"] or {})
            after = dict(metadata["pipeline_reliability"] or {})
            if any(before.get(key) != after.get(key) for key in ("correlation_id", "idempotency_key", "idempotency_key_source", "created_at")):
                raise Scene002ContractError("Protected reliability identity is immutable")


def protected_input_payload_identity(input_payload: Any) -> dict[str, Any]:
    """Return provider intent without the mutable render-timing debug projection."""
    if input_payload is None:
        raise Scene002ContractError("Protected render input is missing")
    result = input_payload.model_dump(mode="json")
    parameters = result.get("parameters")
    if isinstance(parameters, dict):
        parameters.pop("zero_touch_debug", None)
    return result


def assert_ordinary_retry_matches(
    original: Any,
    persisted: Any,
    *,
    project: dict[str, Any] | None = None,
    router_config_id: str | None = None,
) -> dict[str, Any]:
    """Verify retry reuses exactly the durable request and contract."""
    original_payload = verify_job_contract(original, project=project, router_config_id=router_config_id)
    persisted_payload = verify_job_contract(persisted, project=project, router_config_id=router_config_id)
    if (
        original_payload != persisted_payload
        or original.id != persisted.id
        or original.project_id != persisted.project_id
        or original.shot_id != persisted.shot_id
        or original.provider != persisted.provider
        or protected_input_payload_identity(original.input_payload) != protected_input_payload_identity(persisted.input_payload)
    ):
        raise Scene002ContractError("Ordinary retry cannot reconstruct or alter the persisted Scene 002 contract")
    return persisted_payload


def reject_altered_retry(job: Any) -> None:
    if is_contract_only(job):
        raise Scene002ContractError("Altered retries are prohibited for Scene 002 contract-only execution")


def verify_job_contract(
    job: Any,
    *,
    project: dict[str, Any] | None = None,
    router_config_id: str | None = None,
    require_project: bool = True,
) -> dict[str, Any]:
    metadata = getattr(job, "metadata", None)
    if not isinstance(metadata, dict) or metadata.get("execution_mode") != MODE:
        raise Scene002ContractError("Protected job mode is missing")
    execution_record = metadata.get("scene002_execution_contract")
    payload = verify_execution_contract(execution_record)
    if metadata.get("source_authority_id") != payload.get("source_authority", {}).get("authority_id"):
        raise Scene002ContractError("Protected job source authority identity is missing or inconsistent")
    if (
        payload["project_id"] != job.project_id
        or payload["scene_id"] != job.shot_id.split("_shot_", 1)[0]
        or payload["shot_id"] != job.shot_id
        or payload["provider"] != job.provider
        or job.provider != "runway_router"
    ):
        raise Scene002ContractError("Protected job identity differs from its durable contract")
    frozen = metadata.get("creative_generation_contract")
    manifest = metadata.get("creative_generation_manifest")
    if frozen != payload.get("generation_contract") or manifest != payload.get("creative_manifest"):
        raise Scene002ContractError("Protected job lost or replaced its frozen creative proof")
    validate_result_only_metadata(metadata)
    input_payload = getattr(job, "input_payload", None)
    frozen_payload = frozen.get("payload", {}) if isinstance(frozen, dict) else {}
    parameters = input_payload.parameters if input_payload is not None and isinstance(input_payload.parameters, dict) else {}
    creative_parameters = {key: value for key, value in parameters.items() if key != "zero_touch_debug"}
    protected_binding = metadata.get("frozen_reference_binding")
    if not isinstance(protected_binding, list):
        raise Scene002ContractError("Protected reference binding cannot be recovered")
    binding_projection = [
        {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind") if key in row}
        for row in protected_binding if isinstance(row, dict)
    ]
    authority_binding_projection = [
        {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind") if key in row}
        for row in payload.get("reference_bindings", []) if isinstance(row, dict)
    ]
    if binding_projection != authority_binding_projection:
        raise Scene002ContractError("Protected job reference identities differ from the authority-bound contract")
    manifest = payload.get("creative_manifest") if isinstance(payload.get("creative_manifest"), dict) else {}
    shot_rows = manifest.get("shots") if isinstance(manifest.get("shots"), list) else []
    shot_ids = [str(row.get("shot_id") or "") for row in shot_rows if isinstance(row, dict)]
    prompts = [str(row.get("shot_prompt") or "") for row in shot_rows if isinstance(row, dict)]
    identity = metadata.get("creative_generation_identity")
    if not isinstance(identity, dict) or identity != {
        "job_id": job.id, "project_id": job.project_id, "shot_id": job.shot_id, "provider": job.provider,
    }:
        raise Scene002ContractError("Protected job identity metadata is missing or inconsistent")
    if (
        metadata.get("creative_manifest_fingerprint") != payload.get("creative_fingerprint")
        or metadata.get("frozen_reference_binding_sha256") != digest(protected_binding)
        or metadata.get("creative_dialogue_handoff") != payload.get("dialogue_handoff")
    ):
        raise Scene002ContractError("Protected job metadata does not preserve complete contract identities")
    if (
        input_payload is None
        or input_payload.prompt != frozen_payload.get("prompt")
        or input_payload.negative_prompt != frozen_payload.get("negative_prompt", "")
        or list(input_payload.referenceAssets or []) != [row.get("uri") for row in frozen_payload.get("references", [])]
        or creative_parameters != payload.get("provider_input_parameters")
        or payload.get("creative_fingerprint") != manifest.get("manifest_fingerprint")
        or payload.get("scene_id") != authority_scene_id(payload.get("source_authority"))
        or payload.get("ordered_shot_ids") != shot_ids
        or payload.get("ordered_prompts") != prompts
        or _creative_digest(frozen) != metadata.get("creative_contract_digest")
    ):
        raise Scene002ContractError("Protected provider payload differs from the authorized frozen input")
    if project is None and require_project:
        raise Scene002ContractError("Protected job requires an existing project revision witness")
    if project is not None and project_revision_guard(project) != payload.get("project_revision_guard_sha256"):
        raise Scene002ContractError("Project revision changed after the Scene 002 contract was prepared")
    if router_config_id is not None and router_config_id != payload.get("router_config_id"):
        raise Scene002ContractError("Router configuration changed after authorization")
    return payload


def authority_scene_id(authority: Any) -> str:
    return str(authority.get("scene_id") or "") if isinstance(authority, dict) else ""


def _creative_digest(record: Any) -> str:
    from app.services.generation_contract import FrozenGenerationContract

    return FrozenGenerationContract.from_record(record).creative_digest()


def verify_submission_boundary(
    job: Any, *, storage: Any, project: dict[str, Any] | None,
    router_config_id: str, backend_root: Path,
) -> dict[str, Any]:
    """Independently re-check durable authority, project revision, Router and bytes."""
    payload = verify_job_contract(job, project=project, router_config_id=router_config_id)
    metadata = getattr(job, "metadata", None)
    authority_id = str(metadata.get("source_authority_id") or "") if isinstance(metadata, dict) else ""
    if not authority_id or storage is None:
        raise Scene002ContractError("Durable source authority storage is unavailable")
    authority = storage.get_scene002_render_authority(authority_id, job.project_id)
    if authority != payload.get("source_authority"):
        raise Scene002ContractError("Signed source authority cannot be recovered exactly from durable storage")
    if project is None:
        raise Scene002ContractError("Protected execution requires an existing read-only project snapshot")
    verify_reference_bytes(job, payload, backend_root=backend_root)
    return payload


def verify_reference_bytes(job: Any, payload: dict[str, Any], *, backend_root: Path) -> None:
    expected = payload.get("reference_content_sha256")
    if not isinstance(expected, dict) or not expected:
        raise Scene002ContractError("Protected execution has no immutable reference content identities")
    binding = (getattr(job, "metadata", None) or {}).get("frozen_reference_binding")
    if not isinstance(binding, list):
        raise Scene002ContractError("Protected reference binding cannot be recovered")
    actual: dict[str, str] = {}
    seen: set[str] = set()
    for row in binding:
        if not isinstance(row, dict):
            raise Scene002ContractError("Protected reference binding is malformed")
        ref_id = str(row.get("ref_id") or "")
        uri = str(row.get("uri") or "")
        if not ref_id or not uri or ref_id in seen:
            raise Scene002ContractError("Protected reference identity is missing or duplicated")
        seen.add(ref_id)
        actual[ref_id] = local_reference_sha256(uri, backend_root=backend_root)
    if not actual or actual != expected:
        raise Scene002ContractError("Protected reference content changed after authorization")


def is_contract_only(job: Any) -> bool:
    metadata = getattr(job, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("execution_mode") == MODE:
        return True
    execution_record = metadata.get("scene002_execution_contract") if isinstance(metadata, dict) else None
    payload = execution_record.get("payload") if isinstance(execution_record, dict) else None
    return isinstance(payload, dict) and payload.get("mode") == MODE
