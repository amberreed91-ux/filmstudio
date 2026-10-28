from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models import SoundtrackConfig
from app.services.audio_pipeline_service import audio_pipeline_service
from app.services.render import render_service
from app.services.short_film_stitching_service import short_film_stitching_service
from app.services.generation_contract import (
    ROUTER_SELECTION_EVIDENCE_KEYS,
    GenerationContractError,
    freeze_dialogue_handoff,
    verify_dialogue_handoff,
)
from app.services.scene_coverage_contract import build_scene_coverage_contract, resolve_scene_lineage
from app.services.stability import ProviderError, StateError, ValidationError
from app.utils.helpers import (
    derive_scene_id_from_shot_id,
    derive_shot_number_from_shot_id,
)

logger = logging.getLogger(__name__)

SCENE_SCORE_AMBIENT_PROVIDERS = {"none", "manual_post_render", "ace_step", "musicgen"}


# Single source of truth: generation_contract._SETTING_FRAMING_TERMS. This
# thin delegate exists so the invariant projection uses the exact same
# vocabulary as the freeze; the set itself lives in exactly one place.
def _canonical_setting_framing_role(role: Any, *, kind: Any, target_type: Any) -> str | None:
    from app.services.generation_contract import _setting_framing_studio_role

    return _setting_framing_studio_role(role, kind=kind, target_type=target_type)


def _canonical_binding_to_contract_references(binding: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Project a raw canonical reference binding onto the frozen contract shape.

    This is the same shape used by the generate-scene verification path: the
    raw binding keeps ``role`` (and, for settings, ``project_id``), while the
    frozen contract stores ``role="reference"``, ``studio_role=<raw role>``,
    and ``source="canonical_reference_binding"``. The raw binding is never
    mutated here; ordering is preserved.

    Option A: a kind=environment + target_type=setting row carrying framing
    vocabulary (e.g. ``role="wide"``) projects to
    ``studio_role="environment"`` here so the invariant matches the frozen
    contract; the raw row itself is untouched.
    """
    projected: list[dict[str, Any]] = []
    for reference in binding or []:
        raw_role = reference["role"]
        studio_role = (
            _canonical_setting_framing_role(
                raw_role, kind=reference.get("kind"), target_type=reference.get("target_type")
            )
            or raw_role
        )
        projected.append({
            "uri": reference["uri"],
            "role": "reference",
            "studio_role": studio_role,
            "category": reference["category"],
            "source": "canonical_reference_binding",
            "ref_id": reference["ref_id"],
            "target_type": reference["target_type"],
            "target_id": reference["target_id"],
            "canonical": reference["canonical"],
            "approval_state": reference["approval_state"],
            "source_kind": reference["source_kind"],
            "kind": reference["kind"],
        })
    return projected


def _canonical_frozen_references(frozen: Any) -> list[dict[str, Any]]:
    """Return only the canonical binding references from a frozen contract.

    ``freeze_generation_contract()`` appends storyboard/last-frame composition
    references (``source="storyboard_frame_url"`` etc.) when the board frame is
    not itself an approved canonical URI. Those composition references are a
    separate provenance and must not be compared as though they were part of
    the canonical binding. Ordering is preserved; no sorting.
    """
    return [
        reference.to_dict()
        for reference in frozen.references
        if reference.source == "canonical_reference_binding"
    ]


def _decide_router_seed_before_freeze(*, project_id: str, shot_id: str) -> int | None:
    """Decide the Router seed before the freeze (R4.5-B1 F9, owner decision 2).

    Router jobs only. Reuses the stored shot seed or generates and saves a
    fresh one with the same distribution as the submit-time lock it replaces
    on this path, so no mutation occurs after authorization. Returns None
    when no durable seed store is available, preserving the pre-existing
    submit-time behavior instead of inventing an unrecorded seed.
    """
    try:
        from app.data.storage import get_storage as _get_storage

        store = _get_storage("sqlite")
    except Exception:
        return None
    if store is None:
        return None
    try:
        existing = store.get_shot_seed(project_id, shot_id)
    except Exception:
        return None
    if existing is not None and existing.get("seed") is not None:
        try:
            seed_val = int(existing["seed"])
        except (TypeError, ValueError):
            return None
        logger.info(
            "SEED_REUSED_BEFORE_FREEZE | project=%s | shot=%s | seed=%d | stage=seed_before_freeze",
            project_id, shot_id, seed_val,
        )
        return seed_val
    try:
        seed_val = secrets.randbits(31)
        store.save_shot_seed(project_id, shot_id, seed_val)
    except Exception:
        return None
    logger.info(
        "SEED_GENERATED_BEFORE_FREEZE | project=%s | shot=%s | seed=%d | stage=seed_before_freeze",
        project_id, shot_id, seed_val,
    )
    return seed_val


# Phase 2B D5 shot filter: per-request spend ceiling shared with the
# canonical workflow surface (canonical_production_workflow_service -
# _RENDER_CREDIT_CEILING_ENV_VAR). One env var, one default, enforced here
# against the SUM of the selected entries.
SHOT_FILTER_CREDIT_CEILING_ENV_VAR = "RUNWAY_RENDER_MAX_CREDITS"
SHOT_FILTER_CREDIT_CEILING_DEFAULT = 300.0


def entry_freeze_blocked(entry: dict[str, Any]) -> bool:
    """True when this single entry must not mint a frozen contract.

    Per-shot freeze gate (Fix C): only the entry's own signals block it —
    UNRESOLVED coverage, prompt/coverage mismatch, missing/unapproved/stale
    image prompt, or its own pre-freeze blockers (e.g. missing authoritative
    camera plan for Router, corrupt board text, unresolvable binding). A
    sibling shot's failure never appears here, so one bad shot cannot poison
    the batch.
    """
    shot_coverage = entry.get("shot_coverage") or {}
    if shot_coverage.get("content_coverage_state") == "UNRESOLVED":
        return True
    if bool(entry.get("prompt_coverage_problems")):
        return True
    if not entry.get("image_prompt_ready", True):
        return True
    # Own pre-freeze blockers (camera, binding, corruption, cost, dialogue)
    # hold out this entry only; siblings with empty blockers still freeze.
    try:
        blockers = entry.get("blockers") or []
    except Exception:
        blockers = []
    return bool(blockers)


def filtered_render_credit_ceiling() -> float:
    raw = os.getenv(SHOT_FILTER_CREDIT_CEILING_ENV_VAR, str(SHOT_FILTER_CREDIT_CEILING_DEFAULT))
    try:
        ceiling = float(str(raw).strip())
    except (TypeError, ValueError):
        ceiling = float(SHOT_FILTER_CREDIT_CEILING_DEFAULT)
    if ceiling != ceiling or ceiling <= 0:  # NaN or non-positive falls back
        return float(SHOT_FILTER_CREDIT_CEILING_DEFAULT)
    return ceiling


class SceneProductionPipelineService:
    """Coordinate ordered shot rendering, per-shot dialogue, and scene stitching."""

    def __init__(
        self,
        *,
        render_svc: Any = None,
        audio_svc: Any = None,
        stitching_svc: Any = None,
        backend_root: Path | None = None,
    ) -> None:
        self.render_service = render_svc or render_service
        self.audio_service = audio_svc or audio_pipeline_service
        self.stitching_service = stitching_svc or short_film_stitching_service
        self.backend_root = backend_root or Path(__file__).resolve().parents[2]
        # Short-lived snapshots are process-local. Requests routed to another
        # worker fail closed; this service runs as one Uvicorn worker today.
        self._prepared_scene_batches: dict[str, dict[str, Any]] = {}

    async def generate_scene(
        self,
        *,
        project_id: str,
        scene_id: str,
        project: dict[str, Any],
        provider: str | None = None,
        overwrite: bool = False,
        on_audio_overrun: str = "freeze_last_frame",
        score_ambient_provider: str | None = None,
        soundtrack_config: SoundtrackConfig | None = None,
        save_project: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
        prepared_snapshot_id: str | None = None,
        execution_mode: str | None = None,
        source_authority_id: str | None = None,
        expected_reference_binding_digests: dict[str, str] | None = None,
        require_persisted_confirmation: bool = False,
        storyboard_shot_ids: list[str] | None = None,
        allow_full_package: bool = False,
        acknowledge_unknown_cost: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not project_id.strip() or not scene_id.strip():
            raise ValidationError("project_id and scene_id are required", stage="scene_pipeline")
        if not isinstance(project, dict):
            raise ValidationError("Project payload is required", stage="scene_pipeline")
        provider = self._resolve_generation_provider(provider)
        protected_mode = execution_mode == "SCENE_002_CONTRACT_ONLY"
        if execution_mode not in (None, "SCENE_002_CONTRACT_ONLY"):
            raise ValidationError("Unsupported scene execution mode", stage="scene_pipeline_contract")
        if protected_mode and (scene_id != "scene_002" or not source_authority_id or not prepared_snapshot_id):
            raise ValidationError(
                "Scene 002 contract-only execution requires an explicit authority and prepared snapshot",
                stage="scene_pipeline_contract",
                metadata={"failure_type": "missing_scene002_contract"},
            )
        if protected_mode and provider != "runway_router":
            raise ValidationError("Scene 002 contract-only execution requires the audited Runway Router boundary", stage="scene_pipeline_contract")
        if protected_mode and (storyboard_shot_ids is not None or allow_full_package):
            raise ValidationError(
                "Shot filters do not apply to contract-only execution",
                stage="scene_pipeline_contract",
            )
        if protected_mode:
            if soundtrack_config and soundtrack_config.enabled:
                raise ValidationError("Contract-only execution does not authorize soundtrack or assembly", stage="scene_pipeline_contract")
            batch = self._consume_prepared_scene_batch(
                prepared_snapshot_id or "",
                project_id=project_id,
                scene_id=scene_id,
                provider=provider,
                project=project,
                require_current_project=False,
                execution_mode=execution_mode,
                source_authority_id=source_authority_id,
            )
            return await self._submit_contract_only_batch(batch=batch, project=project)

        scene = self._find_scene(project, scene_id)
        if scene is None:
            raise StateError(f"Scene {scene_id} not found", stage="scene_pipeline")

        # Input validation runs BEFORE the gates, so operator mistakes are
        # reported as their own errors rather than as readiness blockers.
        resolved_score_provider = self._normalize_scene_score_provider(score_ambient_provider)
        soundtrack_config = self._resolve_soundtrack_config(
            provider=resolved_score_provider,
            config=soundtrack_config,
        )

        # ── D5 shot-filter shape checks (Phase 2B) ─────────────────────
        # Operator mistakes fail fast here, before any batch work. Unknown
        # ids need the prepared entries, so they are checked after the
        # whole-scene gates below. Legacy callers pass neither field and
        # keep the exact whole-scene behavior.
        filtered_request = storyboard_shot_ids is not None or bool(allow_full_package)
        client_idempotency_base = str(idempotency_key or "").strip() or "scene-pipeline"
        cleaned_filter: list[str] = []
        if storyboard_shot_ids is not None:
            cleaned_filter = [str(value).strip() for value in storyboard_shot_ids]
            if any(not value for value in cleaned_filter):
                raise ValidationError(
                    "Shot filter contains an empty storyboard_shot_id",
                    stage="scene_pipeline_shot_filter",
                )
            seen_filter_ids: set[str] = set()
            duplicate_filter_ids: list[str] = []
            for value in cleaned_filter:
                if value in seen_filter_ids and value not in duplicate_filter_ids:
                    duplicate_filter_ids.append(value)
                seen_filter_ids.add(value)
            if duplicate_filter_ids:
                raise ValidationError(
                    f"Shot filter names duplicates: {', '.join(duplicate_filter_ids)}",
                    stage="scene_pipeline_shot_filter",
                    metadata={"duplicate_storyboard_shot_ids": duplicate_filter_ids},
                )
            if len(cleaned_filter) > 1 and not allow_full_package:
                raise ValidationError(
                    "Rendering more than one shot requires allow_full_package=true; "
                    "a single shot needs no flag",
                    stage="scene_pipeline_shot_filter",
                    metadata={"requested_storyboard_shot_ids": cleaned_filter},
                )
            if not cleaned_filter and not allow_full_package:
                raise ValidationError(
                    "A shot filter is required: name storyboard_shot_ids, or pass "
                    "allow_full_package=true for the whole scene",
                    stage="scene_pipeline_shot_filter",
                )

        # ── Generation readiness + cost gates (P0-4) ───────────────────────
        # The batch path goes through the SAME protection stack as the Previs
        # path: generation context, camera provenance, prompt integrity,
        # reference requirements, and cost limits — evaluated for EVERY shot
        # BEFORE any job is created. A batch is all-or-nothing: one blocked
        # shot blocks the batch (there is no partial generation mode here).
        if prepared_snapshot_id:
            batch = self._consume_prepared_scene_batch(
                prepared_snapshot_id,
                project_id=project_id,
                scene_id=scene_id,
                provider=provider,
                project=project,
                require_current_project=not protected_mode,
                execution_mode=execution_mode,
                source_authority_id=source_authority_id,
            )
        else:
            if protected_mode:
                raise ValidationError("Contract-only execution never prepares from mutable project state", stage="scene_pipeline_contract")
            batch = self.prepare_scene_batch(
                project_id=project_id,
                scene_id=scene_id,
                project=project,
                provider=provider,
                # R4.5-B3.1 (F5, M2): the generic projection-authorization
                # mint is active only on the submission entrypoint, which the
                # route already signals via require_persisted_confirmation.
                # All other callers (previs, dry-runs, UI surfaces) keep
                # byte-identical outputs.
                mint_generic_authorization=require_persisted_confirmation,
            )
        if not batch["ready"]:
            raise ValidationError(
                "Generation blocked: the batch scene render failed its readiness gates. "
                + " ".join(batch["blockers"]),
                stage="generation_readiness",
                metadata={
                    "blockers": batch["blockers"],
                    "shot_count": len(batch["shots"]),
                    "manifest_fingerprint": (batch.get("manifest") or {}).get("manifest_fingerprint"),
                },
            )
        shots = batch["shots"]
        entries = batch["entries"]
        shot_manifest = batch["manifest"]
        protected_contracts: dict[str, dict[str, Any]] = {}
        if protected_mode:
            from app.services.scene002_contract_only import (
                Scene002ContractError,
                build_execution_contract,
                local_reference_sha256,
                project_revision_guard,
                validate_authority_record,
            )
            from app.services.providers.runway_router_provider import get_router_config_id

            try:
                authority = self._load_scene002_authority(project_id, source_authority_id)
                validate_authority_record(authority)
                project_guard = project_revision_guard(project)
                for entry in entries:
                    reference_digests = {
                        str(row.get("ref_id") or ""): local_reference_sha256(
                            str(row.get("uri") or ""), backend_root=self.backend_root
                        )
                        for row in (entry.get("reference_binding") or [])
                    }
                    if not reference_digests:
                        raise Scene002ContractError("Scene 002 contract-only execution requires content-addressed references")
                    record = build_execution_contract(
                        authority=authority, project_id=project_id, scene_id=scene_id,
                        project_guard_sha256=project_guard, manifest=shot_manifest, entry=entry,
                        generation_contract=entry.get("generation_contract"), provider=provider,
                        router_config_id=get_router_config_id(), reference_digests=reference_digests,
                    )
                    protected_contracts[str(entry["shot_id"])] = record
            except (Scene002ContractError, TypeError, ValueError, KeyError) as exc:
                raise ValidationError(
                    f"Scene 002 contract-only execution blocked: {exc}",
                    stage="scene_pipeline_contract",
                    metadata={"failure_type": "invalid_scene002_execution_contract"},
                ) from exc
        if (
            len(shots) != len(entries)
            or {str(shot.get("shot_id") or "") for shot in shots} != {str(entry.get("shot_id") or "") for entry in entries}
            or len({str(entry.get("shot_id") or "") for entry in entries}) != len(entries)
        ):
            raise StateError("Prepared scene batch has inconsistent shot entries", stage="scene_pipeline_snapshot")
        shots_by_id = {str(shot.get("shot_id") or ""): shot for shot in shots}
        shots = [shots_by_id[str(entry["shot_id"])] for entry in entries]
        scene = deepcopy(batch.get("scene_snapshot") or scene)
        if protected_mode:
            expected_snapshot_guard = project_revision_guard(project)
            if any(
                record.get("payload", {}).get("project_revision_guard_sha256") != expected_snapshot_guard
                for record in protected_contracts.values()
            ):
                raise ValidationError("Protected project revision changed after contract creation", stage="scene_pipeline_contract")
        try:
            from app.services.shot_manifest import recompute_manifest_fingerprint
            from app.services.scene_coverage_contract import verify_scene_coverage_contract

            expected_manifest_fingerprint = str(shot_manifest.get("manifest_fingerprint") or "")
            if not expected_manifest_fingerprint or recompute_manifest_fingerprint(shot_manifest) != expected_manifest_fingerprint:
                raise GenerationContractError("Creative manifest fingerprint is invalid")
            coverage_contract = verify_scene_coverage_contract(batch.get("scene_coverage"))
            manifest_scene = shot_manifest.get("scene") if isinstance(shot_manifest.get("scene"), dict) else {}
            if (manifest_scene.get("project_id") != project_id
                    or manifest_scene.get("scene_id") != scene_id
                    or manifest_scene.get("canonical_script_sha256") != coverage_contract.get("canonical_script_sha256")
                    or manifest_scene.get("scene_source_identity") != coverage_contract.get("scene_source_identity")
                    or manifest_scene.get("scene_source_start") != coverage_contract.get("scene_source_start")
                    or manifest_scene.get("scene_source_end") != coverage_contract.get("scene_source_end")):
                raise GenerationContractError("Frozen manifest scene lineage does not match the resolved coverage contract")
            for entry in entries:
                handoff = verify_dialogue_handoff(
                    entry.get("dialogue_handoff"), scene_id=scene_id, shot_id=str(entry.get("shot_id") or "")
                )
                if entry.get("dialogue_lines") != handoff["lines"]:
                    raise GenerationContractError("Prepared dialogue lines do not match their frozen handoff")
                manifest_rows = [
                    row for row in (shot_manifest.get("shots") or [])
                    if isinstance(row, dict) and row.get("shot_id") == entry["shot_id"]
                ]
                if len(manifest_rows) != 1 or manifest_rows[0].get("dialogue_handoff") != entry["dialogue_handoff"]:
                    raise GenerationContractError("Prepared dialogue handoff does not match its creative manifest")
                if any(
                    manifest_rows[0].get(field) != entry.get(field, "")
                    for field in (
                        "camera_plan",
                        "camera_provenance",
                        "camera_instructions",
                        "camera_source_digest",
                        "camera_source_project_id",
                        "camera_source_scene_id",
                        "camera_source_shot_id",
                        "camera_source_storyboard_shot_id",
                        "camera_target_project_id",
                        "camera_target_scene_id",
                        "camera_target_shot_id",
                    )
                ):
                    raise GenerationContractError("Prepared camera source does not match its creative manifest")
                if manifest_rows[0].get("scene_coverage") != coverage_contract:
                    raise GenerationContractError("Prepared scene coverage does not match the creative manifest")
                if manifest_rows[0].get("scene_coverage_shot") != entry.get("shot_coverage"):
                    raise GenerationContractError("Prepared per-shot coverage does not match the creative manifest")
                if entry.get("shot_coverage") not in coverage_contract.get("shots", []):
                    raise GenerationContractError("Prepared shot coverage does not match the authoritative scene map")
                if entry.get("manifest_fingerprint") != expected_manifest_fingerprint:
                    raise GenerationContractError("Prepared dialogue references a stale creative manifest")
                from app.services.generation_contract import FrozenGenerationContract

                frozen = FrozenGenerationContract.from_record(entry.get("generation_contract"))
                if frozen.payload().get("dialogue_handoff") != entry["dialogue_handoff"]:
                    raise GenerationContractError("Frozen generation contract dialogue does not match its manifest")
                if frozen.payload().get("scene_coverage") != coverage_contract:
                    raise GenerationContractError("Frozen generation contract scene coverage does not match its manifest")
                contract_coverage_shots = [row for row in coverage_contract.get("shots", []) if row.get("shot_id") == entry.get("shot_id")]
                if len(contract_coverage_shots) != 1 or frozen.payload().get("scene_coverage_shot") != contract_coverage_shots[0]:
                    raise GenerationContractError("Frozen generation contract per-shot coverage does not match its manifest")
                if manifest_rows[0].get("scene_coverage") != coverage_contract:
                    raise GenerationContractError("Creative manifest scene coverage does not match the READY contract")
                if manifest_rows[0].get("scene_coverage_shot") != contract_coverage_shots[0]:
                    raise GenerationContractError("Creative manifest shot coverage does not match the frozen contract")
                if manifest_rows[0].get("reference_binding") != entry.get("reference_binding"):
                    raise GenerationContractError("Creative manifest reference binding does not match the frozen shot selection")
                camera_payload = frozen.payload()
                if (
                    camera_payload.get("camera_plan") != entry.get("camera_plan")
                    or camera_payload.get("camera_provenance") != entry.get("camera_provenance")
                    or camera_payload.get("camera_instructions") != entry.get("camera_instructions", [])
                    or camera_payload.get("camera_source_digest") != entry.get("camera_source_digest")
                    or camera_payload.get("camera_source_project_id") != entry.get("camera_source_project_id", "")
                    or camera_payload.get("camera_source_scene_id") != entry.get("camera_source_scene_id", "")
                    or camera_payload.get("camera_source_shot_id") != entry.get("camera_source_shot_id", "")
                    or camera_payload.get("camera_source_storyboard_shot_id") != entry.get("camera_source_storyboard_shot_id", "")
                    or camera_payload.get("camera_target_project_id") != entry.get("camera_target_project_id", "")
                    or camera_payload.get("camera_target_scene_id") != entry.get("camera_target_scene_id", "")
                    or camera_payload.get("camera_target_shot_id") != entry.get("camera_target_shot_id", "")
                ):
                    raise GenerationContractError("Prepared camera source does not match the frozen camera contract")
                if frozen.creative_digest() != entry.get("generation_contract_digest"):
                    raise GenerationContractError("Frozen generation contract digest does not match its prepared entry")
                from app.services.reference_validation import (
                    reference_binding_coverage_projection,
                    verify_shot_reference_coverage_binding,
                )
                verify_shot_reference_coverage_binding(
                    actual_binding=reference_binding_coverage_projection(entry.get("reference_binding") or []),
                    coverage_shot=contract_coverage_shots[0],
                )
                expected_contract_references = _canonical_binding_to_contract_references(
                    entry.get("reference_binding")
                )
                canonical_frozen_references = _canonical_frozen_references(frozen)
                if canonical_frozen_references != expected_contract_references:
                    raise GenerationContractError("Frozen generation contract references do not match its canonical binding")
                frozen_all_references = frozen.payload().get("references") or []
                references_match = (
                    (entry.get("references") or []) == [reference["uri"] for reference in frozen_all_references]
                    and (entry.get("reference_roles") or []) == [reference["studio_role"] for reference in frozen_all_references]
                    and entry.get("generation_settings", {}).get("frozen_reference_binding") == entry.get("reference_binding")
                )
                if not references_match:
                    raise GenerationContractError("Prepared reference values do not match the frozen canonical binding")
                manifest_reference_rows = [
                    row for row in (shot_manifest.get("shots") or [])
                    if isinstance(row, dict) and row.get("shot_id") == entry["shot_id"]
                ]
                if len(manifest_reference_rows) != 1:
                    raise GenerationContractError("Prepared shot is missing from its creative manifest")
                if entry.get("reference_binding") and (
                    manifest_reference_rows[0].get("reference_binding") != entry.get("reference_binding")
                    or manifest_reference_rows[0].get("references") != [row["uri"] for row in entry.get("reference_binding") or []]
                    or manifest_reference_rows[0].get("reference_roles") != [row["role"] for row in entry.get("reference_binding") or []]
                ):
                    raise GenerationContractError("Prepared references do not match their creative manifest")
                if frozen.manifest_fingerprint != shot_manifest.get("manifest_fingerprint"):
                    raise GenerationContractError("Frozen generation contract manifest fingerprint is stale")
        except (GenerationContractError, ValueError, KeyError, TypeError) as exc:
            raise ValidationError(
                f"Generation blocked: invalid frozen dialogue handoff: {exc}",
                stage="generation_dialogue_integrity",
                metadata={"failure_type": "invalid_dialogue_handoff", "scene_id": scene_id},
            ) from exc
        # ── All-or-nothing batch authorization preflight (R4.1A) ─────────
        # Every required shot must pass preflight before the first job is
        # created. A single failing shot rejects the whole batch with zero
        # jobs; provider execution is untouched (later per-job failures keep
        # their existing handling). Preflight itself never creates jobs or
        # contacts providers; creation-time, submit-time, and adapter-level
        # checks all remain active below.
        authorization = self.preflight_batch_authorization(
            project_id=project_id,
            scene_id=scene_id,
            entries=entries,
            shot_manifest=shot_manifest,
            expected_digests=expected_reference_binding_digests,
            require_persisted_confirmation=require_persisted_confirmation,
        )
        if not authorization["ready"]:
            failures = "; ".join(
                f"{row['shot_id'] or '?'}: {row['message']}"
                for row in authorization["shots"]
                if not row["ok"]
            )
            raise ValidationError(
                "Batch authorization preflight rejected one or more shots; "
                f"no jobs were created. {failures}",
                stage="batch_authorization_preflight",
                metadata={
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "failure_type": "batch_authorization_preflight_rejected",
                    "authorization": authorization,
                },
            )
        # R4.3: durable authorization evidence. ``authorization`` is the
        # preflight decision that authorizes this batch; index its per-shot
        # verdicts so every created job below carries the decision that
        # authorized it. The shared manifest fingerprint + snapshot id keep
        # the batch enumerable per job even when execution fails partway.
        authorization_by_shot = {
            str(row.get("shot_id") or ""): row
            for row in (authorization.get("shots") or [])
            if isinstance(row, dict)
        }
        # ── D5 selection AFTER the whole-scene gates (Phase 2B) ────────
        # Every gate above still applied to EVERY shot; this only narrows
        # which frozen entries are turned into render jobs, reusing their
        # frozen payloads byte-for-byte (same prompt, contract, manifest).
        submission_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = list(zip(shots, entries))
        if filtered_request:
            selected_entries = self._select_filtered_entries(
                entries=entries,
                storyboard_shot_ids=cleaned_filter,
                allow_full_package=allow_full_package,
            )
            selected_ids = {str(entry.get("shot_id") or "") for entry in selected_entries}
            submission_pairs = [
                (shot, entry) for shot, entry in zip(shots, entries)
                if str(entry.get("shot_id") or "") in selected_ids
            ]
            # Router ceiling (Phase 6): the batch cost picture is locally
            # unpriced for runway_router, so price each selected router shot
            # with one advisory non-billing dry-run BEFORE the spend guard
            # and before any job row. Preflight authorization already passed,
            # so no provider is contacted for an unauthorized batch.
            await self._estimate_filtered_router_shots(
                project_id=project_id,
                provider=provider,
                selected_entries=selected_entries,
                shot_manifest=shot_manifest,
            )
            self._refuse_unestimated_router_shots(
                project_id=project_id,
                selected_entries=selected_entries,
            )
            self._enforce_filtered_spend_guards(
                project_id=project_id,
                provider=provider,
                selected_entries=selected_entries,
                acknowledge_unknown_cost=acknowledge_unknown_cost,
            )
            self._refuse_duplicate_filtered_submit(
                project=project,
                project_id=project_id,
                scene_id=scene_id,
                selected_entries=selected_entries,
            )
        batch_manifest_fingerprint = str((shot_manifest or {}).get("manifest_fingerprint") or "")
        batch_snapshot_id = str(batch.get("prepared_snapshot_id") or "")
        per_shot_score_provider = "none" if resolved_score_provider == "manual_post_render" else resolved_score_provider

        if protected_mode:
            if soundtrack_config and soundtrack_config.enabled:
                raise ValidationError("Scene 002 contract-only permits render outputs only; audio and assembly are outside this boundary", stage="scene_pipeline_contract")
            # Protected execution stops at verified provider outputs. It does
            # not launch unbound audio/stitch jobs or project-summary writers.
            results = []
            for entry in entries:
                job = self.render_service.create_job(
                    project_id=project_id,
                    shot_id=str(entry["shot_id"]),
                    provider=provider,
                    prompt=entry["prompt"],
                    reference_assets=deepcopy(entry["references"]),
                    parameters=deepcopy(entry["generation_settings"]),
                    frozen_reference_binding=deepcopy(entry.get("reference_binding") or []),
                    generation_context_id=entry.get("generation_context_id", ""),
                    creative_manifest_fingerprint=shot_manifest.get("manifest_fingerprint", ""),
                    creative_manifest=shot_manifest,
                    dialogue_handoff=deepcopy(entry["dialogue_handoff"]),
                    generation_contract=entry.get("generation_contract"),
                    prepared_generation_contract=entry.get("generation_contract"),
                    execution_mode="SCENE_002_CONTRACT_ONLY",
                    scene002_execution_contract=deepcopy(protected_contracts[str(entry["shot_id"])]),
                    source_authority_id=source_authority_id,
                )
                self._assert_prepared_scene_batch_current(batch, project=project, scene_id=scene_id)
                completed = await self._submit_and_wait(job.id)
                if getattr(completed, "status", "") != "complete" or not self._job_output_url(completed):
                    raise ProviderError("Protected render did not produce a verified output", stage="scene_pipeline_contract")
                results.append({
                    "shot_id": str(entry["shot_id"]),
                    "render_job_id": str(getattr(completed, "id", "")),
                    "output_url": self._job_output_url(completed),
                    "status": "complete",
                    "execution_fingerprint": protected_contracts[str(entry["shot_id"])]["execution_fingerprint"],
                })
            return {
                "status": "complete",
                "project_id": project_id,
                "scene_id": scene_id,
                "execution_mode": "SCENE_002_CONTRACT_ONLY",
                "shots": results,
                "shot_manifest": shot_manifest,
                "assembly": None,
                "output_url": None,
                "prepared_snapshot_id": batch.get("prepared_snapshot_id", ""),
            }

        working_project = deepcopy(project)
        summary = self._ensure_execution_summary(working_project)
        render_rows = summary.setdefault("one_button_render_jobs", [])
        if not isinstance(render_rows, list):
            render_rows = []
            summary["one_button_render_jobs"] = render_rows

        rendered_shots: list[dict[str, Any]] = []
        for index, (shot, prepared_entry) in enumerate(submission_pairs, start=1):
            shot_id = str(prepared_entry["shot_id"])
            # Every generation input comes from the same prepared entry that
            # produced the READY verdict; do not resolve shots or derive prompts here.
            prompt = prepared_entry["prompt"]
            self._assert_prepared_scene_batch_current(batch, project=project, scene_id=scene_id)
            # Hardening: every filtered create carries an explicit,
            # deterministic idempotency key (client key when supplied, else
            # the frozen manifest fingerprint) so a replayed or concurrent
            # request reuses the same job row instead of minting a second
            # one. Legacy whole-scene creates are untouched.
            filtered_job_key: str | None = None
            if filtered_request:
                filtered_job_key = ":".join((
                    client_idempotency_base,
                    batch_manifest_fingerprint,
                    shot_id,
                ))
            filtered_parameters = deepcopy(prepared_entry["generation_settings"])
            if filtered_request:
                # Hardening: every filtered create carries an explicit,
                # deterministic idempotency key inside parameters (client
                # key when supplied, else the frozen manifest fingerprint)
                # so a replayed or concurrent request reuses the same job
                # row instead of minting a second one. Legacy whole-scene
                # creates are untouched.
                filtered_parameters["idempotency_key"] = ":".join((
                    client_idempotency_base,
                    batch_manifest_fingerprint,
                    shot_id,
                ))
            job_arguments = {
                "project_id": project_id,
                "shot_id": shot_id,
                "provider": provider,
                "prompt": prompt,
                "reference_assets": deepcopy(prepared_entry["references"]),
                "parameters": filtered_parameters,
                "generation_contract": deepcopy(prepared_entry.get("generation_contract")) if provider == "runway_router" else None,
                "frozen_reference_binding": deepcopy(prepared_entry.get("reference_binding") or []),
                "metadata": self._batch_authorized_job_metadata(
                    prepared_entry=prepared_entry,
                    shot_verdict=authorization_by_shot.get(shot_id, {}),
                    project_id=project_id,
                    scene_id=scene_id,
                    manifest_fingerprint=batch_manifest_fingerprint,
                    prepared_snapshot_id=batch_snapshot_id,
                    batch_shot_index=index,
                    batch_shot_count=len(submission_pairs),
                    confirmation_enforced=require_persisted_confirmation,
                ),
                "generation_context_id": prepared_entry.get("generation_context_id", ""),
                "creative_manifest_fingerprint": shot_manifest.get("manifest_fingerprint", ""),
                "creative_manifest": shot_manifest,
                "dialogue_handoff": deepcopy(prepared_entry["dialogue_handoff"]),
                "prepared_generation_contract": deepcopy(prepared_entry.get("generation_contract")),
            }
            if provider == "runway_router":
                job_arguments["generation_contract"] = prepared_entry.get("generation_contract")
            elif prepared_entry.get("generation_contract"):
                job_arguments["prepared_generation_contract"] = prepared_entry["generation_contract"]
            if provider == "runway_router":
                # R4.5-B1 (F8): carry the digest-linked selection evidence so
                # creation persists it with the frozen proof. Entries without
                # a linked digest (e.g. unresolved coverage) forward nothing.
                forwarding = prepared_entry.get("router_selection_evidence")
                if (
                    isinstance(forwarding, dict)
                    and isinstance(forwarding.get("selection"), dict)
                    and isinstance(forwarding.get("contract_digest"), str)
                    and forwarding["contract_digest"]
                ):
                    job_metadata = dict(job_arguments.get("metadata") or {})
                    job_metadata["router_selection_evidence"] = deepcopy(forwarding)
                    job_arguments["metadata"] = job_metadata
            job = self.render_service.create_job(**job_arguments)
            if not protected_mode:
                self._link_storyboard_render_if_present(shot, getattr(job, "id", ""))
            completed_job = await self._submit_and_wait(job.id)
            source_url = self._job_output_url(completed_job)
            source_path = self._local_output_path(source_url)
            if source_path is None:
                raise ProviderError(
                    f"Rendered shot {shot_id} does not have a local video path for audio merge",
                    stage="scene_pipeline_audio_merge",
                    metadata={"provider": getattr(completed_job, "provider", None), "shot_id": shot_id},
                )

            # Re-verify immediately before audio. An explicit empty list is a
            # frozen silence decision, not permission to re-extract scene text.
            dialogue_handoff = verify_dialogue_handoff(
                prepared_entry.get("dialogue_handoff"), scene_id=scene_id, shot_id=shot_id
            )
            dialogue_lines = deepcopy(dialogue_handoff["lines"])
            audio_result = await self.audio_service.generate_full_pipeline(
                scene_id=shot_id,
                project_id=project_id,
                scene_text=self._scene_text(scene) if dialogue_handoff["lines"] else "",
                mood=str(scene.get("emotional_tone") or scene.get("tone") or ""),
                score_notes="",
                ambient_notes="",
                silence_flag=False,
                video_path=source_path,
                estimated_duration_seconds=float(prepared_entry["duration_seconds"] or scene.get("duration_seconds") or 5.0),
                on_audio_overrun=on_audio_overrun,
                score_ambient_provider=per_shot_score_provider,
                characters=self._scene_characters(scene),
                dialogue_lines=dialogue_lines,
                dialogue_handoff=deepcopy(prepared_entry["dialogue_handoff"]),
                narrative_audio=True,
                dialogue_scene_id=scene_id,
                dialogue_shot_id=shot_id,
                scene_context={"scene": scene, "shot": shot, "shot_index": index, "shot_count": len(submission_pairs)},
            )
            final_url = audio_result.get("final_video_url") or source_url
            consistency = self._consistency_summary(completed_job)
            render_row = {
                "scene_id": scene_id,
                "shot_id": shot_id,
                "job_id": getattr(completed_job, "id", ""),
                "status": "complete",
                "provider": getattr(completed_job, "provider", provider or ""),
                "output_url": final_url,
                "source_output_url": source_url,
                "audio_pipeline_job_id": audio_result.get("job_id"),
                "dialogue_provider": audio_result.get("dialogue_provider"),
                "score_ambient_provider": resolved_score_provider,
                "per_shot_score_ambient_provider": audio_result.get("score_ambient_provider"),
                "consistency": consistency,
                "generation_context_id": prepared_entry.get("generation_context_id", ""),
                "shot_version": prepared_entry.get("shot_version", ""),
            }
            self._upsert_render_row(render_rows, render_row)
            rendered_shots.append(
                {
                    "shot_id": shot_id,
                    "render_job_id": getattr(completed_job, "id", ""),
                    "audio": audio_result,
                    "consistency": consistency,
                }
            )

        if filtered_request and len(submission_pairs) < len(entries):
            # Subset atomicity (Phase 2B item 2): per-shot render rows are
            # upserted and persisted below, but NO scene assembly is written
            # — a partial stitch must never overwrite the scene's assembly
            # row or its assembly file, and no soundtrack is mixed for a
            # subset. The full manifest still rides on every job, so each
            # take verifies against the whole-scene freeze.
            selected_shot_ids = [str(entry.get("shot_id") or "") for _, entry in submission_pairs]
            omitted_shot_ids = [
                str(entry.get("shot_id") or "") for entry in entries
                if str(entry.get("shot_id") or "") not in set(selected_shot_ids)
            ]
            if save_project is not None and not protected_mode:
                saved = save_project(working_project)
                if isinstance(saved, dict):
                    working_project = saved
            single_output_url: str | None = None
            if len(rendered_shots) == 1:
                audio_payload = rendered_shots[0].get("audio")
                if isinstance(audio_payload, dict):
                    single_output_url = str(audio_payload.get("final_video_url") or "") or None
            return {
                "status": "complete",
                "project_id": project_id,
                "scene_id": scene_id,
                "shots": rendered_shots,
                "stitch": None,
                "assembly": None,
                "assembly_skipped": "subset_selection_has_no_scene_assembly",
                "output_url": single_output_url,
                "score_ambient_provider": resolved_score_provider,
                "soundtrack_status": self._soundtrack_status(soundtrack_config),
                "shot_manifest": shot_manifest,
                "prepared_snapshot_id": batch.get("prepared_snapshot_id", ""),
                "shot_filter": {
                    "storyboard_shot_ids": cleaned_filter,
                    "allow_full_package": bool(allow_full_package),
                    "filtered_from": "full_scene_batch",
                    "selected_shot_ids": selected_shot_ids,
                    "omitted_shot_ids": omitted_shot_ids,
                },
            }
        stitch_result = self.stitching_service.stitch_scene(
            project_id=project_id,
            scene_id=scene_id,
            project=working_project,
            overwrite=overwrite,
            soundtrack_config=soundtrack_config,
        )
        status = self._scene_status_from_stitch(stitch_result)
        assembly = self._scene_assembly_row(
            project_id=project_id,
            scene_id=scene_id,
            status=status,
            stitch_result=stitch_result,
            rendered_shots=rendered_shots,
            score_ambient_provider=resolved_score_provider,
            soundtrack_status=self._soundtrack_status(soundtrack_config),
        )
        self._upsert_scene_assembly(summary, assembly)

        if save_project is not None and not protected_mode:
            saved = save_project(working_project)
            if isinstance(saved, dict):
                working_project = saved

        return {
            "status": status,
            "project_id": project_id,
            "scene_id": scene_id,
            "shots": rendered_shots,
            "stitch": stitch_result,
            "assembly": assembly,
            "output_url": stitch_result.get("output_url"),
            "score_ambient_provider": resolved_score_provider,
            "soundtrack_status": self._soundtrack_status(soundtrack_config),
            "shot_manifest": shot_manifest,
            "prepared_snapshot_id": batch.get("prepared_snapshot_id", ""),
        }

    # ══ D5 shot filter + spend guards (Phase 2B) ═════════════════════════

    @staticmethod
    def _select_filtered_entries(
        *,
        entries: list[dict[str, Any]],
        storyboard_shot_ids: list[str],
        allow_full_package: bool,
    ) -> list[dict[str, Any]]:
        """Narrow frozen batch entries to the requested storyboard shots.

        The batch stays whole-scene; only job creation is narrowed. Unknown
        ids are refused by name. Order follows the request.
        """
        if not storyboard_shot_ids:
            if not allow_full_package:
                raise ValidationError(
                    "A shot filter is required: name storyboard_shot_ids, or pass "
                    "allow_full_package=true for the whole scene",
                    stage="scene_pipeline_shot_filter",
                )
            return list(entries)
        available = {
            str(entry.get("storyboard_shot_id") or "").strip()
            for entry in entries
        } - {""}
        unknown = [value for value in storyboard_shot_ids if value not in available]
        if unknown:
            raise ValidationError(
                f"Shot filter names shots outside this scene batch: {', '.join(unknown)}",
                stage="scene_pipeline_shot_filter",
                metadata={"unknown_storyboard_shot_ids": unknown},
            )
        by_board_id: dict[str, dict[str, Any]] = {}
        for entry in entries:
            key = str(entry.get("storyboard_shot_id") or "").strip()
            if key and key not in by_board_id:
                by_board_id[key] = entry
        return [by_board_id[value] for value in storyboard_shot_ids]

    async def _estimate_filtered_router_shots(
        self,
        *,
        project_id: str,
        provider: str | None,
        selected_entries: list[dict[str, Any]],
        shot_manifest: dict[str, Any] | None,
    ) -> None:
        """Price selected runway_router shots with one advisory dry-run each.

        Runs after preflight authorization and before the spend guard and
        before any job row. Non-router entries and already-estimated entries
        are untouched. Each estimate is stamped onto its entry's own
        ``cost_estimate`` picture (advisory, no margin); a hung or failing
        dry-run is bounded by the router timeout and stamps unestimated.
        """
        from app.services.generation_cost_gate import generation_cost_gate
        from app.services.providers.runway_router_provider import (
            get_runway_router_timeout_seconds,
        )

        resolved = str(provider or "").strip().lower()
        if resolved != "runway_router":
            return
        timeout_seconds = get_runway_router_timeout_seconds()
        for entry in selected_entries:
            shot_id = str(entry.get("shot_id") or "?")
            current = entry.get("cost_estimate")
            if isinstance(current, dict) and current.get("estimated") is True:
                continue
            contract_record = entry.get("generation_contract")
            if not isinstance(contract_record, dict) or not isinstance(shot_manifest, dict):
                entry["cost_estimate"] = {
                    "model": None,
                    "duration_seconds": entry.get("duration_seconds"),
                    "estimated_credits": None,
                    "estimated": False,
                    "estimate_source": "runway_router_dry_run",
                    "advisory": True,
                    "failure_class": "missing_frozen_contract",
                }
                continue
            # Local-reference router shots are priced by the materialized
            # price probe (real alias, dry-run only, never a generation)
            # instead of the placeholder estimator. The placeholder path
            # stays for every non-materializing case. The submit path is
            # unchanged and never receives the probe's alias.
            if self._entry_has_local_router_refs(contract_record):
                try:
                    from app.adapters import RunwayRouterAdapter
                    from app.models import ProviderConfig

                    _probe = RunwayRouterAdapter(
                        ProviderConfig(provider_id="runway_router", name="Runway Router")
                    )
                    estimated = await asyncio.wait_for(
                        asyncio.to_thread(
                            _probe.price_with_materialized_reference,
                            contract_record=contract_record,
                            manifest_record=shot_manifest,
                            reference_binding=entry.get("reference_binding"),
                            project_id=project_id,
                            shot_id=shot_id,
                            backend_root=self.backend_root,
                        ),
                        timeout=timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    estimated = {
                        "model": None,
                        "duration_seconds": entry.get("duration_seconds"),
                        "estimated_credits": None,
                        "estimated": False,
                        "estimate_source": "runway_router_materialized_probe",
                        "advisory": True,
                        "failure_class": "probe_timeout",
                    }
                entry["cost_estimate"] = estimated
                logger.info(
                    "project_id=%s job_id=%s provider=runway_router stage=router_price_probe_applied duration_ms=%d",
                    project_id,
                    shot_id,
                    0,
                )
                continue
            try:
                estimated = await asyncio.wait_for(
                    asyncio.to_thread(
                        generation_cost_gate.estimate_router_shot_via_dry_run,
                        contract_record=contract_record,
                        manifest=shot_manifest,
                    ),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                estimated = {
                    "model": None,
                    "duration_seconds": entry.get("duration_seconds"),
                    "estimated_credits": None,
                    "estimated": False,
                    "estimate_source": "runway_router_dry_run",
                    "advisory": True,
                    "failure_class": "dry_run_timeout",
                }
            entry["cost_estimate"] = estimated
            logger.info(
                "project_id=%s job_id=%s provider=runway_router stage=router_spend_estimate_applied duration_ms=%d",
                project_id,
                shot_id,
                0,
            )

    @staticmethod
    def _entry_has_local_router_refs(contract_record: Any) -> bool:
        """True when a frozen contract carries a reference Runway cannot fetch.

        Local (non-``https://``/``runway://``/``data:image/``) URIs route the
        entry to the materialized price probe; every other entry keeps the
        placeholder estimator. Read-only: never mutates the contract.
        """
        payload = contract_record.get("payload") if isinstance(contract_record, dict) else None
        refs = payload.get("references") if isinstance(payload, dict) else None
        if not isinstance(refs, list):
            return False
        for ref in refs:
            uri = ref.get("uri") if isinstance(ref, dict) else None
            if not isinstance(uri, str) or not uri:
                continue
            if not uri.startswith(("https://", "runway://", "data:image/")):
                return True
        return False

    @staticmethod
    def _refuse_unestimated_router_shots(
        *,
        project_id: str,
        selected_entries: list[dict[str, Any]],
    ) -> None:
        """Fail closed when a router shot has no verified dry-run estimate.

        Additive refusal only: router entries stamped unestimated by the
        dry-run estimator or the materialized price probe are refused even
        when ``acknowledge_unknown_cost`` is true, because an unverified
        ceiling cannot be evaluated. Non-router entries keep the existing
        acknowledgement semantics in the spend guard below; nothing already
        allowed becomes refused.
        """
        unestimated = [
            str(entry.get("shot_id") or "?")
            for entry in selected_entries
            if isinstance(entry.get("cost_estimate"), dict)
            and entry["cost_estimate"].get("estimate_source")
            in ("runway_router_dry_run", "runway_router_materialized_probe")
            and entry["cost_estimate"].get("estimated") is not True
        ]
        if not unestimated:
            return
        raise ValidationError(
            f"Shot(s) {', '.join(unestimated)} have no verified Runway router cost estimate "
            "(the advisory non-billing dry-run estimate was unavailable or failed); "
            "resubmission requires a successful estimate — acknowledge_unknown_cost "
            "cannot waive it for runway_router",
            stage="scene_pipeline_spend_guard",
            metadata={
                "project_id": project_id,
                "unknown_cost_shot_ids": unestimated,
                "estimate_source": "runway_router_dry_run",
                "advisory": True,
            },
        )

    @staticmethod
    def _enforce_filtered_spend_guards(
        *,
        project_id: str,
        provider: str | None,
        selected_entries: list[dict[str, Any]],
        acknowledge_unknown_cost: bool,
    ) -> None:
        """Server-side spend guards over the SELECTED entries, pre-creation.

        Estimates are the batch's own per-shot cost pictures (no new provider
        contact). Known credits are summed and refused over the per-request
        ceiling with no acknowledgement bypass; any unknown estimate requires
        explicit acknowledgement. Simulated providers never spend.
        """
        resolved = str(provider or "").strip().lower()
        if resolved in {"", "simulated"}:
            return
        ceiling = filtered_render_credit_ceiling()
        known_total = 0.0
        unknown_shot_ids: list[str] = []
        for entry in selected_entries:
            shot_id = str(entry.get("shot_id") or "?")
            estimate = entry.get("cost_estimate")
            credited = None
            if isinstance(estimate, dict) and estimate.get("estimated") is True:
                try:
                    credited = float(estimate.get("estimated_credits"))
                except (TypeError, ValueError):
                    credited = None
            if credited is None:
                unknown_shot_ids.append(shot_id)
            else:
                known_total += credited
        if unknown_shot_ids and not acknowledge_unknown_cost:
            raise ValidationError(
                f"Shot(s) {', '.join(unknown_shot_ids)} have no verified cost estimate; pass "
                "acknowledge_unknown_cost=true to proceed without one",
                stage="scene_pipeline_spend_guard",
                metadata={
                    "project_id": project_id,
                    "unknown_cost_shot_ids": unknown_shot_ids,
                    "ceiling_credits": ceiling,
                    "ceiling_env_var": SHOT_FILTER_CREDIT_CEILING_ENV_VAR,
                },
            )
        if known_total > ceiling:
            raise ValidationError(
                f"Selected shots estimate ({known_total:g} credits, advisory) exceeds the per-request "
                f"ceiling ({ceiling:g} credits, {SHOT_FILTER_CREDIT_CEILING_ENV_VAR}); "
                "the ceiling is applied to the estimate exactly, with no margin",
                stage="scene_pipeline_spend_guard",
                metadata={
                    "project_id": project_id,
                    "estimated_credits": known_total,
                    "ceiling_credits": ceiling,
                    "ceiling_env_var": SHOT_FILTER_CREDIT_CEILING_ENV_VAR,
                    "selected_shot_ids": [str(entry.get("shot_id") or "") for entry in selected_entries],
                    "advisory": True,
                },
            )

    def _refuse_duplicate_filtered_submit(
        self,
        *,
        project: dict[str, Any],
        project_id: str,
        scene_id: str,
        selected_entries: list[dict[str, Any]],
    ) -> None:
        """Refuse a filtered submit when the shot already has a live job.

        Two evidence sources: the durable execution-summary rows (completed
        takes) and the persisted render/job tables (ANY non-failed job —
        queued, submitted, rendering, complete — including leftovers from a
        crashed request). A failed prior attempt never blocks a retry.
        """
        summary = project.get("execution_summary")
        rows = summary.get("one_button_render_jobs") if isinstance(summary, dict) else None
        completed_jobs: dict[tuple[str, str], str] = {}
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or str(row.get("status") or "") != "complete":
                    continue
                completed_jobs[(str(row.get("scene_id") or ""), str(row.get("shot_id") or ""))] = str(row.get("job_id") or "")
        dupes = [
            str(entry.get("shot_id") or "")
            for entry in selected_entries
            if (scene_id, str(entry.get("shot_id") or "")) in completed_jobs
        ]
        dupe_job_ids = [completed_jobs[(scene_id, shot_id)] for shot_id in dupes]
        # Persisted render/job tables: the summary only records completed
        # takes, so consult job history for anything still live.
        reader = getattr(self.render_service, "list_persisted_jobs", None)
        if callable(reader):
            try:
                jobs = reader(project_id=project_id)
            except Exception as exc:
                raise ValidationError(
                    "Studio cannot verify prior submissions because persisted render history "
                    "could not be read; generation is blocked.",
                    stage="scene_pipeline_shot_filter",
                    metadata={
                        "cost_status": "history_unavailable",
                        "history_error": type(exc).__name__,
                    },
                ) from exc
            wanted = {str(entry.get("shot_id") or "") for entry in selected_entries}
            for job in jobs or []:
                try:
                    provider = str(getattr(job, "provider", "") or "").strip().lower()
                    shot_id = str(getattr(job, "shot_id", "") or "")
                    status = str(getattr(job, "status", "") or "")
                except Exception:
                    continue
                if provider not in {"runway_router", "runway"} or shot_id not in wanted:
                    continue
                if status == "failed":
                    continue
                if shot_id not in dupes:
                    dupes.append(shot_id)
                    dupe_job_ids.append(str(getattr(job, "id", "") or ""))
        if dupes:
            raise ValidationError(
                f"Shot(s) {', '.join(dupes)} already have a scene-pipeline render that has not "
                "failed; resubmission is refused to prevent a duplicate charge",
                stage="scene_pipeline_shot_filter",
                metadata={
                    "duplicate_shot_ids": dupes,
                    "existing_job_ids": dupe_job_ids,
                },
            )

    def count_prior_router_submissions(
        self,
        *,
        project_id: str,
        shot_ids: list[str],
    ) -> dict[str, dict[str, int]]:
        """Count persisted Runway render jobs per shot (read-only, advisory).

        Returns ``{shot_id: {"total": n, "failed": m}}``. Feeds the
        single-take dialog's "N Runway submissions" line; failed attempts
        are shown but never block a retry. Never raises: history gaps
        report zero rather than blocking preflight.
        """
        wanted = {str(value) for value in shot_ids if str(value)}
        if not wanted:
            return {}
        try:
            jobs = self.render_service.list_persisted_jobs(project_id=project_id)
        except Exception:
            return {}
        counts: dict[str, dict[str, int]] = {}
        for job in jobs or []:
            try:
                provider = str(getattr(job, "provider", "") or "").strip().lower()
                shot_id = str(getattr(job, "shot_id", "") or "")
                status = str(getattr(job, "status", "") or "")
            except Exception:
                continue
            if provider not in {"runway_router", "runway"} or shot_id not in wanted:
                continue
            row = counts.setdefault(shot_id, {"total": 0, "failed": 0})
            row["total"] += 1
            if status == "failed":
                row["failed"] += 1
        return counts

    # ══ All-or-nothing batch authorization preflight (R4.1A) ═══════════════

    @staticmethod
    def _batch_authorized_job_metadata(
        *,
        prepared_entry: dict[str, Any],
        shot_verdict: dict[str, Any],
        project_id: str,
        scene_id: str,
        manifest_fingerprint: str,
        prepared_snapshot_id: str,
        batch_shot_index: int,
        batch_shot_count: int,
        confirmation_enforced: bool,
    ) -> dict[str, Any]:
        """Attach durable batch-authorization evidence to a created job (R4.3).

        Additive only: the existing reference-projection authorization (when
        present) is preserved untouched, and a compact ``batch_authorization``
        record captures the preflight decision that authorized this job —
        verdict, policy version, digest status, batch position, and whether
        durable-confirmation enforcement was active. No gate behavior changes:
        downstream authorization compares durable vs in-memory metadata, which
        match because the stamp is set before creation, and the idempotency
        key never reads metadata.
        """
        metadata: dict[str, Any] = {}
        if prepared_entry.get("reference_projection_authorization"):
            metadata["reference_projection_authorization"] = deepcopy(
                prepared_entry["reference_projection_authorization"]
            )
        if isinstance(prepared_entry.get("generic_authorization_audit"), dict):
            metadata["generic_authorization_audit"] = deepcopy(
                prepared_entry["generic_authorization_audit"]
            )
        metadata["batch_authorization"] = {
            "preflight": "batch_authorization_preflight",
            "project_id": project_id,
            "scene_id": scene_id,
            "manifest_fingerprint": manifest_fingerprint,
            "prepared_snapshot_id": prepared_snapshot_id,
            "batch_shot_index": batch_shot_index,
            "batch_shot_count": batch_shot_count,
            "shot_verdict": "authorized" if shot_verdict.get("ok") is True else "unmapped",
            "policy_version": shot_verdict.get("policy_version"),
            "digest": shot_verdict.get("digest"),
            "confirmation_enforced": bool(confirmation_enforced),
        }
        return metadata

    @staticmethod
    def _persisted_confirmation_failure(
        binder: Any,
        project_id: str,
        shot_id: str,
        expected_digests: dict[str, str] | None,
    ) -> tuple[str, str] | None:
        """Enforce one shot's durable-confirmation requirement (R4.2).

        Returns ``(failure_code, message)`` when the shot must not proceed,
        or ``None`` when its persisted confirmation revalidates against the
        freshly resolved binding. Read-only: nothing is created or mutated.
        A shot whose current binding cannot be resolved keeps the
        pre-existing semantics — there is nothing confirmable, so the
        remaining preflight checks decide — unless a stale record claims
        otherwise, which fails closed.
        """
        stored = binder.get_persisted_confirmation_digest(project_id, shot_id)
        try:
            binder.resolve_shot_binding(project_id, shot_id)
        except (LookupError, ValueError, ValidationError):
            if stored is None:
                return None
            return (
                "confirmed_reference_binding_unresolvable",
                f"Shot {shot_id} carries a durable confirmation whose current binding "
                "cannot be verified against canonical state; resolve the shot again "
                "and confirm before submitting.",
            )
        if stored is None:
            return (
                "missing_confirmation",
                f"Shot {shot_id} has no durable reference-binding confirmation; "
                "confirm the shot's current binding before submitting.",
            )
        carried = (expected_digests or {}).get(shot_id)
        if carried is not None and str(carried).strip() != stored:
            return (
                "confirmation_mismatch",
                f"Shot {shot_id} carries a digest that does not match its durable "
                "confirmation; resolve the shot again and confirm before submitting.",
            )
        try:
            binder.verify_confirmed_binding(project_id, shot_id, stored)
        except ValidationError as exc:
            code = str((exc.metadata or {}).get("failure_type") or "confirmed_reference_binding_stale")
            return (code, str(exc.message))
        except (LookupError, ValueError):
            return (
                "confirmed_reference_binding_unresolvable",
                f"Shot {shot_id} carries a durable confirmation that cannot be "
                "verified against current canonical state; resolve the shot again "
                "and confirm before submitting.",
            )
        return None

    def preflight_batch_authorization(
        self,
        *,
        project_id: str,
        scene_id: str,
        entries: list[dict[str, Any]],
        shot_manifest: dict[str, Any] | None,
        expected_digests: dict[str, str] | None,
        require_persisted_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Verify every requested shot is authorized BEFORE any job creation.

        Read-only accumulation over the established canonical layers — this
        method never raises for per-shot failures, never creates jobs, and
        never contacts a provider. Shots are evaluated in order; every shot
        receives a structured result. The checks, in order per shot:

        1. stable shot identity (malformed or duplicated identifiers fail);
        2. Desk-confirmed binding digest — only when the caller supplies
           expectations, with the exact semantics of the confirmed-binding
           verifier (the client digest is never trusted; only the freshly
           resolved server binding decides);
        2b. durable confirmation (R4.2) — only when
           ``require_persisted_confirmation`` is True: the shot must carry a
           project-scoped persisted confirmation whose digest still matches
           the freshly resolved binding. Missing, mismatched, stale, or
           unverifiable confirmations fail closed. Shots with no resolvable
           current binding keep the pre-existing semantics (nothing to
           confirm; the remaining checks decide);
        3. upstream readiness — a shot still carrying prepare blockers
           cannot be authorized (its blockers stay owned by the readiness
           verdict; no second failure is invented for it);
        4. creative-manifest membership — exactly one manifest row carrying
           the entry's frozen binding;
        5. binding currency — every row an approved canonical anchor and
           exactly one setting authority;
        6. projection policy — Scene 002 keeps its v1 authorization proof
           untouched (presence + binding-digest match, no re-validation);
           generic ``runway_router`` shots must satisfy the exact
           submit-time Router rules applied to their frozen contract
           (representable frozen roles, at most four references — the
           R4.0A interim capacity policy). Other providers defer to their
           own submit-time checks, which remain active after preflight.

        Returns a structured report; the caller rejects the whole batch
        when ``ready`` is False. The Production Integrity Gate remains the
        final authorization boundary at submission.
        """
        from app.services.generation_contract import FrozenGenerationContract
        from app.services.reference_asset_service import ReferenceAssetService
        from app.services.reference_validation import (
            SCENE002_PROJECT_ID,
            reference_binding_digest,
        )
        from app.services.runway_reference_projection import CAPACITY as ROUTER_CAPACITY
        from app.services.runway_reference_projection import normalize_studio_role

        if not isinstance(entries, list):
            raise ValidationError(
                "Batch authorization preflight requires an ordered entry list",
                stage="batch_authorization_preflight",
            )
        if expected_digests is not None and not isinstance(expected_digests, dict):
            raise ValidationError(
                "Confirmed reference binding digests must map shot IDs to digest strings",
                stage="batch_authorization_preflight",
                metadata={"failure_type": "confirmed_reference_binding_malformed"},
            )
        binder = ReferenceAssetService() if (expected_digests is not None or require_persisted_confirmation) else None
        manifest_shots = shot_manifest.get("shots") if isinstance(shot_manifest, dict) else None
        if not isinstance(manifest_shots, list):
            manifest_shots = []
        is_scene002 = (
            str(project_id or "") == SCENE002_PROJECT_ID
            and str(scene_id or "") == "scene_002"
        )
        # Router submit-time rules, mirrored exactly (provider boundary:
        # frozen roles representable via normalize_studio_role, at most
        # ROUTER_CAPACITY references). Preflight applies them to the same
        # frozen artifact — never stricter than submission, only earlier, so
        # no valid batch can newly fail. Roles are judged by their normalized
        # provider role, exactly as the unprojected submission path judges
        # them; unknown studio roles stay rejected with
        # unsupported_reference_role.

        def _fail(
            shot_id: str,
            code: str,
            category: str,
            message: str,
            *,
            digest: str,
            policy_version: str | None = None,
        ) -> dict[str, Any]:
            return {
                "shot_id": shot_id,
                "ok": False,
                "failure_code": code,
                "failure_category": category,
                "message": message,
                "policy_version": policy_version,
                "digest": digest,
            }

        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                results.append(_fail(
                    "", "malformed_shot_id", "shot_identity",
                    "A batch entry is malformed; every entry must carry its stable shot identifier.",
                    digest="skipped_no_expectations" if binder is None else "not_required",
                ))
                continue
            raw_id = entry.get("shot_id")
            shot_id = str(raw_id).strip() if isinstance(raw_id, str) else ""
            if not shot_id:
                results.append(_fail(
                    "", "malformed_shot_id", "shot_identity",
                    "A batch entry carries no shot identifier; it cannot be authorized against any project.",
                    digest="skipped_no_expectations" if binder is None else "not_required",
                ))
                continue
            if shot_id in seen:
                results.append(_fail(
                    shot_id, "duplicate_shot_id", "shot_identity",
                    f"Shot {shot_id} appears more than once in the batch; duplicated shots cannot be authorized.",
                    digest="skipped_no_expectations" if binder is None else "not_required",
                ))
                continue
            seen.add(shot_id)

            digest_status = "skipped_no_expectations"
            if binder is not None:
                if shot_id in (expected_digests or {}):
                    try:
                        binder.verify_confirmed_binding(project_id, shot_id, expected_digests[shot_id])
                        digest_status = "verified"
                    except ValidationError as exc:
                        code = str((exc.metadata or {}).get("failure_type") or "confirmed_reference_binding_unresolvable")
                        results.append(_fail(shot_id, code, "confirmation", exc.message, digest="rejected"))
                        continue
                    except (LookupError, ValueError):
                        results.append(_fail(
                            shot_id, "confirmed_reference_binding_unresolvable", "confirmation",
                            "The confirmed reference binding cannot be verified against "
                            "current canonical state; resolve the shot again and confirm "
                            "before submitting.",
                            digest="rejected",
                        ))
                        continue
                else:
                    digest_status = "not_required"

            # Durable-confirmation enforcement (R4.2): a persisted record is
            # evidence of a previous explicit approval, never authorization —
            # the stored digest is re-verified against the freshly resolved
            # binding here, and the full R4.1A preflight below still runs.
            if require_persisted_confirmation and binder is not None:
                persisted_failure = self._persisted_confirmation_failure(
                    binder, project_id, shot_id, expected_digests
                )
                if persisted_failure is not None:
                    code, message = persisted_failure
                    results.append(_fail(shot_id, code, "confirmation", message, digest="rejected"))
                    continue
                if digest_status in ("skipped_no_expectations", "not_required"):
                    digest_status = "verified"

            if entry.get("blockers"):
                results.append(_fail(
                    shot_id, "upstream_blockers", "generation_contract",
                    f"Shot {shot_id} carries unresolved readiness blockers; resolve them before authorization.",
                    digest=digest_status,
                ))
                continue

            manifest_rows = [
                row for row in manifest_shots
                if isinstance(row, dict) and str(row.get("shot_id") or "") == shot_id
            ]
            if len(manifest_rows) != 1:
                results.append(_fail(
                    shot_id, "missing_generation_contract", "generation_contract",
                    f"Shot {shot_id} is missing from its creative manifest; no generation contract can be produced for it.",
                    digest=digest_status,
                ))
                continue
            entry_binding = entry.get("reference_binding")
            binding_rows = list(entry_binding) if isinstance(entry_binding, list) else []
            if binding_rows and manifest_rows[0].get("reference_binding") != entry_binding:
                results.append(_fail(
                    shot_id, "missing_generation_contract", "generation_contract",
                    f"Shot {shot_id} prepared references do not match their creative manifest.",
                    digest=digest_status,
                ))
                continue

            policy_version: str | None = None
            if binding_rows:
                unapproved = [
                    row for row in binding_rows
                    if not isinstance(row, dict)
                    or row.get("approval_state") != "approved"
                    or row.get("canonical") is not True
                ]
                if unapproved:
                    results.append(_fail(
                        shot_id, "unapproved_reference", "reference_authorization",
                        f"Shot {shot_id} references a reference that is not an approved canonical anchor.",
                        digest=digest_status,
                    ))
                    continue
                setting_rows = [row for row in binding_rows if row.get("target_type") == "setting"]
                if len(setting_rows) > 1:
                    results.append(_fail(
                        shot_id, "ambiguous_setting_authority", "setting_authority",
                        f"Shot {shot_id} carries more than one canonical setting anchor; a single setting authority is required.",
                        digest=digest_status,
                    ))
                    continue
                if not setting_rows:
                    results.append(_fail(
                        shot_id, "missing_setting_authority", "setting_authority",
                        f"Shot {shot_id} carries no canonical setting anchor.",
                        digest=digest_status,
                    ))
                    continue
                if is_scene002:
                    authorization = entry.get("reference_projection_authorization")
                    auth_digest = (
                        authorization.get("frozen_reference_binding_sha256")
                        if isinstance(authorization, dict) else ""
                    )
                    if not isinstance(authorization, dict) or auth_digest != reference_binding_digest(binding_rows):
                        results.append(_fail(
                            shot_id, "missing_reference_authority", "reference_authorization",
                            f"Shot {shot_id} Scene 002 authorization proof is missing or does not match its frozen binding.",
                            digest=digest_status,
                            policy_version="v1",
                        ))
                        continue
                    policy_version = "v1"
                elif entry.get("manifest_provider") == "runway_router":
                    try:
                        frozen = FrozenGenerationContract.from_record(entry.get("generation_contract"))
                        frozen_refs = frozen.payload().get("references") or []
                    except Exception:  # noqa: BLE001 — any unparsable frozen proof fails closed
                        frozen_refs = []
                    if not isinstance(frozen_refs, list) or not frozen_refs:
                        results.append(_fail(
                            shot_id, "invalid_generation_contract", "generation_contract",
                            f"Shot {shot_id} produced no parsable frozen generation contract.",
                            digest=digest_status,
                            policy_version="v2",
                        ))
                        continue
                    bad_roles = []
                    for ref in frozen_refs:
                        if not isinstance(ref, dict):
                            bad_roles.append(ref)
                            continue
                        try:
                            normalize_studio_role(ref.get("studio_role"))
                        except ValueError:
                            bad_roles.append(ref)
                    if bad_roles:
                        results.append(_fail(
                            shot_id, "unsupported_reference_role", "reference_authorization",
                            f"Shot {shot_id} carries a frozen reference role the Router cannot represent.",
                            digest=digest_status,
                            policy_version="v2",
                        ))
                        continue
                    if len(frozen_refs) > ROUTER_CAPACITY:
                        results.append(_fail(
                            shot_id, "unsupported_reference_capacity", "reference_capacity",
                            f"Shot {shot_id} exceeds the currently supported reference capacity "
                            f"({ROUTER_CAPACITY} references). Narrow the approved binding before "
                            "generating — references are never dropped or substituted automatically.",
                            digest=digest_status,
                            policy_version="v2",
                        ))
                        continue
                    policy_version = "v2"
            results.append({
                "shot_id": shot_id,
                "ok": True,
                "failure_code": None,
                "failure_category": None,
                "message": None,
                "policy_version": policy_version,
                "digest": digest_status,
            })

        passed = sum(1 for row in results if row["ok"])
        report = {
            "ready": all(row["ok"] for row in results),
            "project_id": project_id,
            "scene_id": scene_id,
            "shot_count": len(results),
            "passed_count": passed,
            "failed_count": len(results) - passed,
            "digest_expectations": "provided" if expected_digests is not None else "absent",
            "shots": results,
        }
        logger.info(
            "BATCH_AUTHORIZATION_PREFLIGHT | project=%s | scene=%s | ready=%s | passed=%d | failed=%d",
            project_id,
            scene_id,
            report["ready"],
            passed,
            len(results) - passed,
        )
        return report

    # ══ Batch generation pre-flight (P0-4) ══════════════════════════════════

    def prepare_scene_batch(
        self,
        *,
        project_id: str,
        scene_id: str,
        project: dict[str, Any],
        provider: str | None = None,
        execution_mode: str | None = None,
        source_authority_id: str | None = None,
        mint_generic_authorization: bool = False,
    ) -> dict[str, Any]:
        """Run the FULL readiness + cost stack for every shot of a scene batch.

        Reuses the exact services the Previs path uses (no second versions):

            Canonical Scene → Current Storyboard → Current Shot List →
            Current References → Current Camera State → Generation Context →
            Readiness Gate → Cost Gate → [Model Router] → Provider Payload →
            Provider Boundary

        Returns a batch record with per-shot validated entries (prompt,
        versions, references, camera, generation context), a canonical shot
        manifest, and an aggregate readiness verdict. This is also the dry-run
        surface: it never creates a job or touches a provider, and identical
        canonical state yields an identical manifest fingerprint.
        """
        from app.services.generation_context_service import generation_context_service
        from app.services.generation_cost_gate import generation_cost_gate
        from app.services.prompt_integrity import detect_prompt_corruption
        from app.services.shot_manifest import build_shot_manifest
        from app.services.stability import ValidationError as _ValidationError

        if execution_mode == "SCENE_002_CONTRACT_ONLY":
            raise _ValidationError("Contract-only preparation requires the explicit durable source authority entrypoint", stage="scene_pipeline_contract")
        if execution_mode is not None:
            raise _ValidationError("Unsupported scene execution mode", stage="scene_pipeline_contract")
        if not str(project_id or "").strip() or not str(scene_id or "").strip():
            raise _ValidationError("project_id and scene_id are required", stage="scene_pipeline")
        provider = self._resolve_generation_provider(provider)
        original_project = deepcopy(project)
        authority = None
        protected_mode = execution_mode == "SCENE_002_CONTRACT_ONLY"
        if protected_mode:
            project = deepcopy(project)
            project["execution_mode"] = execution_mode
        if execution_mode not in (None, "SCENE_002_CONTRACT_ONLY"):
            raise ValidationError("Unsupported scene execution mode", stage="scene_pipeline_contract")
        if protected_mode:
            if scene_id != "scene_002" or provider != "runway_router" or not source_authority_id:
                raise ValidationError("Scene 002 preparation requires explicit authority and the audited provider", stage="scene_pipeline_contract")
            from app.services.scene002_contract_only import (
                local_reference_sha256,
                project_revision_guard,
                validate_authority_record,
            )
            authority = validate_authority_record(self._load_scene002_authority(project_id, source_authority_id))
            if authority.get("project_id") != project_id:
                raise ValidationError("Scene 002 authority belongs to a different project", stage="scene_pipeline_contract")
            guard = project_revision_guard(project)
            expected_refs = authority["reference_content_sha256"]
            actual_refs = {
                str(row["ref_id"]): local_reference_sha256(str(row["uri"]), backend_root=self.backend_root)
                for row in authority["reference_bindings"]
            }
            if actual_refs != expected_refs:
                raise ValidationError("Authorized reference content is unavailable or changed", stage="scene_pipeline_contract")
            batch = self._build_contract_only_batch(
                project_id=project_id,
                authority_id=source_authority_id,
                authority=authority,
                project_guard_sha256=guard,
                provider=provider,
            )
            self._register_prepared_scene_batch(batch, provider=provider)
            return batch
        scene = self._find_scene(project, scene_id)
        if scene is None:
            raise StateError(f"Scene {scene_id} not found", stage="scene_pipeline")
        if protected_mode and (not authority or scene.get("storyboard_version_id") not in (None, "", authority["storyboard_version_id"])):
            raise ValidationError("Protected scene shell does not match authorized storyboard identity", stage="scene_pipeline_contract")

        # Current Storyboard → Current Shot List: storyboard-first selection,
        # followed by strict scene ownership checks before any downstream lookup.
        scene = deepcopy(scene)
        shots, source_kind, source_key = self._resolve_shot_source(
            project,
            scene,
            project_id=project_id,
        )
        # Keep the immutable source fingerprint before preflight enriches these
        # working shot dictionaries with derived camera, coverage, and reference
        # data. Revalidation compares against the original authoritative source.
        shot_source_fingerprint = self._snapshot_fingerprint(
            self._sort_shots(scene.get("shots") or []) if source_kind == "scene_shots" else shots
        )
        if not shots:
            raise StateError(f"Scene {scene_id} has no renderable shots", stage="scene_pipeline")
        if protected_mode and source_kind != "storyboard":
            raise ValidationError("Protected preparation requires the exact authorized storyboard source; mutable project shot fallbacks are prohibited", stage="scene_pipeline_contract")
        if protected_mode:
            protected_storyboard_service = __import__("app.services.storyboard_blueprint_service", fromlist=["storyboard_blueprint_service"]).storyboard_blueprint_service
            actual_board_versions: set[str] = set()
            for shot in shots:
                meta = (shot.get("parameters") or {}).get("storyboard") if isinstance(shot.get("parameters"), dict) else None
                if not isinstance(meta, dict) or not meta.get("storyboard_shot_id"):
                    raise ValidationError("Protected preparation requires explicit storyboard shot identities", stage="scene_pipeline_contract")
                storyboard_shot = protected_storyboard_service.storage.get_storyboard_shot(str(meta["storyboard_shot_id"]))
                if (
                    storyboard_shot is None
                    or str(getattr(storyboard_shot, "version_id", "") or "") != str(authority["storyboard_version_id"])
                    or str(getattr(storyboard_shot, "project_id", "") or "") != project_id
                    or str(getattr(storyboard_shot, "scene_id", "") or "") != scene_id
                    or str(getattr(storyboard_shot, "shot_id", "") or "") != str(shot.get("shot_id") or "")
                ):
                    raise ValidationError("Storyboard shot cannot be recovered from the exact authorized version", stage="scene_pipeline_contract")
                actual_board_versions.add(str(getattr(storyboard_shot, "version_id", "") or ""))
                # Only the approved storyboard prompt is creative authority here.
                # Descriptions and mutable project-shot prompts are not substitutes.
                storyboard_prompt = getattr(storyboard_shot, "prompt", None)
                if not isinstance(storyboard_prompt, str) or not storyboard_prompt.strip():
                    raise ValidationError("Authorized storyboard shot has no frozen prompt", stage="scene_pipeline_contract")
                shot["prompt"] = storyboard_prompt
                shot_parameters = shot.setdefault("parameters", {})
                shot_parameters["storyboard"]["version_id"] = authority["storyboard_version_id"]
            if actual_board_versions != {str(authority["storyboard_version_id"])}:
                raise ValidationError("Ordered shots do not all match the authorized storyboard version", stage="scene_pipeline_contract")
            if [str(shot.get("shot_id") or "") for shot in shots] != [str(value) for value in authority.get("ordered_shot_ids", [])]:
                raise ValidationError("Ordered shots differ from the explicit authorized shot sequence", stage="scene_pipeline_contract")
        shot_by_id = {str(shot.get("shot_id") or ""): shot for shot in shots}
        if len(shot_by_id) != len(shots):
            raise ValidationError(
                "Scene batch contains duplicate shot identifiers.",
                stage="scene_pipeline_shot_ownership",
                metadata={"failure_type": "duplicate_shot_id", "scene_id": scene_id},
            )

        lineage = resolve_scene_lineage(project_id, project, scene)
        blockers: list[str] = []
        if protected_mode:
            # Authority bytes, not mutable project.script_text, are the lineage source.
            authority_project = dict(project)
            authority_project["script_text"] = authority["screenplay_text"]
            authority_project["script_version_id"] = authority["screenplay_representation_id"]
            lineage = resolve_scene_lineage(project_id, authority_project, scene)
            # Coverage must consume the same immutable screenplay bytes. Use a
            # local projection only; never write the authority text to project state.
            coverage_project = deepcopy(project)
            coverage_project["script_text"] = authority["screenplay_text"]
            coverage_project["script_version_id"] = authority["screenplay_representation_id"]
        else:
            coverage_project = project
        if protected_mode and (
            lineage.get("canonical_script_sha256") != authority.get("screenplay_sha256")
            or lineage.get("scene_content_sha256") != authority.get("scene_sha256")
            or lineage.get("scene_source_start") != authority.get("scene_span", {}).get("start")
            or lineage.get("scene_source_end") != authority.get("scene_span", {}).get("end")
            or lineage.get("script_version_id") != authority.get("screenplay_representation_id")
        ):
            raise ValidationError("Authorized screenplay bytes, scene span, or representation identity changed", stage="scene_pipeline_contract")
        if lineage.get("status") != "RESOLVED" and not protected_mode:
            blockers.append("canonical scene lineage unresolved: selected scene does not match canonical project script_text")
        # Version-scoped Scene Direction decisions ride on the current approved
        # board version (persisted on the primary shot by SceneDirectionService).
        # They are the ONLY authoritative source for assignment, omission, and
        # silence; legacy fields cannot establish creator intent.
        creator_coverage_decisions = (
            deepcopy(authority["coverage_decisions"])
            if protected_mode and authority
            else next((
                rows for shot in shots
                if isinstance((rows := (shot.get("parameters") or {}).get("creator_coverage_decisions")), list)
            ), None)
        )
        entries: list[dict[str, Any]] = []
        generation_context_ids: list[str] = []

        for index, shot in enumerate(shots, start=1):
            shot_id = str(shot.get("shot_id") or f"{scene_id}_shot_{index:03d}").strip()
            parameters = deepcopy(shot.get("parameters")) if isinstance(shot.get("parameters"), dict) else {}
            if protected_mode:
                prompt = str(shot.get("prompt") or "")
                if not prompt.strip():
                    raise ValidationError("Authorized storyboard prompt is missing", stage="scene_pipeline_contract")
            else:
                prompt = self._shot_prompt(scene, shot, index, len(shots))
            # Provider-bound text for storyboard-backed shots is ALWAYS the
            # approved, hash-linked image prompt — never the board's
            # provider_neutral_prompt. Resolution happens below once the
            # current board shot is known; ``prompt`` above stays the board
            # text so board-integrity checks keep reading board text.
            send_prompt: str | None = None
            send_prompt_sha256 = ""
            send_prompt_error = ""
            send_prompt_applies = False
            reference_assets = [str(url) for url in (shot.get("reference_assets") or shot.get("source_refs") or [])]
            storyboard_meta = parameters.get("storyboard") if isinstance(parameters.get("storyboard"), dict) else {}

            # Current Camera State + Generation Context (real shot version).
            current_shot = None
            board_version = str(storyboard_meta.get("version_id") or "")
            storyboard_shot_id = str(storyboard_meta.get("storyboard_shot_id") or "")
            if storyboard_shot_id:
                try:
                    from app.services.storyboard_blueprint_service import storyboard_blueprint_service

                    candidate = storyboard_blueprint_service.storage.get_storyboard_shot(storyboard_shot_id)
                    if (
                        candidate is not None
                        and str(getattr(candidate, "version_id", "") or "") == board_version
                        and str(getattr(candidate, "shot_id", "") or "") == shot_id
                        and str(getattr(candidate, "project_id", "") or "") == project_id
                        and str(getattr(candidate, "scene_id", "") or "") == scene_id
                        and str(getattr(candidate, "storyboard_shot_id", "") or "") == storyboard_shot_id
                    ):
                        current_shot = candidate
                except Exception:
                    current_shot = None
            if not protected_mode and storyboard_shot_id:
                send_prompt_applies = True
                send_prompt, send_prompt_sha256, send_prompt_error = (
                    self._resolve_storyboard_send_prompt(
                        shot_id=shot_id,
                        storyboard_shot_id=storyboard_shot_id,
                        current_shot=current_shot,
                    )
                )
            from app.services.camera_provenance import (
                CAMERA_PROVENANCE_AI,
                CAMERA_PROVENANCE_CREATOR,
                CAMERA_PROVENANCE_STORYBOARD,
                CAMERA_PROVENANCE_UNSPECIFIED,
                authoritative_camera_source,
                camera_plan_digest,
                canonical_camera_instructions,
            )
            from app.services.generation_context_service import (
                CameraInstruction,
                pending_ai_camera_suggestions,
            )

            camera_blockers: list[str] = []
            try:
                camera_plan, camera_provenance = authoritative_camera_source(
                    storyboard_shot_id=storyboard_shot_id,
                    project_id=project_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    shot=current_shot,
                    fallback_parameters=parameters,
                )
            except GenerationContractError as exc:
                camera_plan, camera_provenance = {}, CAMERA_PROVENANCE_UNSPECIFIED
                camera_blockers.append(f"camera provenance: {exc}")
            pending_suggestions = pending_ai_camera_suggestions(current_shot) if current_shot is not None else {}
            if camera_provenance == CAMERA_PROVENANCE_UNSPECIFIED and pending_suggestions:
                camera_provenance = CAMERA_PROVENANCE_AI
            try:
                if camera_provenance == CAMERA_PROVENANCE_AI:
                    camera_plan = {}
                    readiness_camera_instructions = generation_context_service.derive_camera_instructions(
                        ai_suggested_camera=pending_suggestions or None
                    )
                else:
                    readiness_camera_instructions = [
                        CameraInstruction(**row)
                        for row in canonical_camera_instructions(camera_plan, camera_provenance)
                    ]
                camera_instructions = [
                    CameraInstruction(**row)
                    for row in canonical_camera_instructions(camera_plan, camera_provenance)
                ]
            except (GenerationContractError, ValueError) as exc:
                camera_blockers.append(f"camera provenance: {exc}")
                camera_instructions = generation_context_service.derive_camera_instructions()
                readiness_camera_instructions = list(camera_instructions)
            parameters["camera_plan"] = deepcopy(camera_plan)
            parameters["camera_provenance"] = camera_provenance
            parameters.update(
                camera_source_project_id=project_id,
                camera_source_scene_id=scene_id,
                camera_source_shot_id=shot_id,
                camera_source_storyboard_shot_id=(
                    storyboard_shot_id if camera_provenance == CAMERA_PROVENANCE_STORYBOARD else ""
                ),
                camera_target_project_id=project_id,
                camera_target_scene_id=scene_id,
                camera_target_shot_id=shot_id,
            )
            parameters["camera_source_digest"] = camera_plan_digest(
                camera_plan,
                camera_provenance,
                source_project_id=parameters["camera_source_project_id"],
                source_scene_id=parameters["camera_source_scene_id"],
                source_shot_id=parameters["camera_source_shot_id"],
                source_storyboard_shot_id=parameters["camera_source_storyboard_shot_id"],
            )
            shot["parameters"] = deepcopy(parameters)
            shot["camera_plan"] = deepcopy(camera_plan)
            shot["camera_provenance"] = camera_provenance
            shot["camera_source_digest"] = parameters["camera_source_digest"]
            for camera_field in (
                "camera_source_project_id", "camera_source_scene_id", "camera_source_shot_id",
                "camera_source_storyboard_shot_id", "camera_target_project_id",
                "camera_target_scene_id", "camera_target_shot_id",
            ):
                shot[camera_field] = parameters[camera_field]
            shot["camera_instructions"] = deepcopy(parameters.get("camera_instructions") or [])
            context = generation_context_service.create_generation_context(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=shot_id,
                scene=scene,
                storyboard_context={"version": board_version} if board_version else None,
                reference_assets=reference_assets,
                camera_instructions=readiness_camera_instructions,
                prompt_source="BOARD" if storyboard_meta else "DERIVED",
                shot=current_shot if current_shot is not None else shot,
                require_shot_version=True,
                canonical_script_text=(authority["screenplay_text"] if protected_mode else project.get("script_text")) if isinstance((authority["screenplay_text"] if protected_mode else project.get("script_text")), str) else None,
            )
            generation_context_ids.append(context.generation_context_id)

            # Readiness gate — identical service to the Previs path.
            readiness = generation_context_service.validate_generation_context(
                context=context,
                current_scene=scene,
                current_storyboard_context={"version": board_version} if board_version else None,
                current_reference_assets=reference_assets,
                expected_scene_id=scene_id,
                expected_shot_id=shot_id,
                current_shot=current_shot if current_shot is not None else shot,
                canonical_script_text=(authority["screenplay_text"] if protected_mode else project.get("script_text")) if isinstance((authority["screenplay_text"] if protected_mode else project.get("script_text")), str) else None,
            )
            shot_blockers = [*camera_blockers, *readiness.blockers]
            if send_prompt_applies and send_prompt_error:
                shot_blockers.append(send_prompt_error)
            if provider == "runway_router" and not camera_plan:
                shot_blockers.append("camera plan: Runway Router requires an authoritative camera plan")

            # Prompt integrity (P0-3): a corrupted approved board prompt must
            # block the whole batch before anything reaches a provider.
            # Provenance integrity (integrity-repair workstream): the check runs
            # on the BOARD prompt itself, NOT on the post-derivation prompt —
            # appending the "[SHOT POSITION]" block ends the string in terminal
            # punctuation, which masks a severed terminal fragment in the
            # underlying board content (previs checks the raw board prompt and
            # was flagging prompts the batch path passed).
            if storyboard_meta:
                board_prompt = str(
                    (shot.get("prompt") or shot.get("description") or shot.get("visual_description") or "")
                ).strip()
                issues = detect_prompt_corruption(board_prompt, source="BOARD")
                shot_blockers.extend(issues)

            # Resolve the canonical approved references from the scene snapshot
            # and project-scoped registry. Ordinary shots use only their
            # authorized coverage selection; Scene 002 keeps its explicit
            # authority-pinned five-reference path.
            from app.services.reference_validation import (
                reference_binding_for_requirements,
                resolve_scene_reference_requirements,
                shot_character_focus_tokens,
                verify_shot_reference_coverage_binding,
            )

            requirements = None
            reference_binding: list[dict[str, Any]] = []
            reference_projection_authorization = None
            try:
                from app.data.storage import get_storage as _get_storage

                _validation_storage = _get_storage("sqlite")
                scene_requirements = resolve_scene_reference_requirements(
                    project_id=project_id,
                    scene_id=scene_id,
                    storage=_validation_storage,
                    scene=scene,
                    require_canonical_references=False,
                )
                shot_focus = shot_character_focus_tokens(shot)
                if not shot_focus and current_shot is not None:
                    shot_focus = shot_character_focus_tokens({
                        "character_focus": list(getattr(getattr(current_shot, "intent", None), "character_focus", []) or [])
                    })
                if not shot_focus:
                    shot_focus = shot_character_focus_tokens({
                        "character_focus": list(shot.get("character_focus") or (shot.get("intent") or {}).get("character_focus", []))
                    })
                focus_supplied = bool(shot_focus)
                if current_shot is not None:
                    focus_supplied = focus_supplied or getattr(
                        getattr(current_shot, "intent", None), "character_focus", None
                    ) is not None
                effective_focus = shot_focus if shot_focus else ([] if focus_supplied else None)
                requirements = resolve_scene_reference_requirements(
                    project_id=project_id,
                    scene_id=scene_id,
                    storage=_validation_storage,
                    scene=scene,
                    character_focus=effective_focus,
                )
                required_character_ids = list(requirements.get("character_ids") or [])
                if not protected_mode:
                    # Ordinary video requests freeze the exact binding they
                    # resolve. Scene 002 retains its creator-authorized legacy
                    # projection order and fixed five-reference shape.
                    requirements["setting_references"] = [
                        row for row in requirements.get("setting_references") or []
                        if row.get("target_type") == "setting"
                        and str(row.get("target_id") or "") == str(requirements.get("setting_id") or "")
                    ]
                    if len(requirements["setting_references"]) != 1:
                        raise ValueError("required setting reference is missing or ambiguous for the approved shot")
                    requirements["setting_urls"] = [row["uri"] for row in requirements["setting_references"]]
                    requirements["allowed_urls"] = list(dict.fromkeys([
                        *[uri for item in requirements.get("characters", {}).values() for uri in item.get("urls", [])],
                        *requirements["setting_urls"],
                    ]))
                shot["character_focus"] = deepcopy(shot_focus)
                parameters["character_focus"] = deepcopy(shot_focus)
                parameters["character_focus_ids"] = list(required_character_ids)
                requirements["scene_character_ids"] = scene_requirements.get("scene_character_ids") or scene_requirements.get("character_ids") or []
                requirements["scene_characters"] = deepcopy(scene_requirements.get("characters") or {})
                requirements["approved_scene_binding"] = reference_binding_for_requirements(scene_requirements)
                # Composition conditioning is not a canonical identity claim.
                # The board frame (and symmetrically a last-frame reference)
                # stays in render parameters/composition conditioning; only
                # genuine identity URLs are validated as supplied identity refs.
                _composition_urls = {
                    str(parameters.get("storyboard_frame_url") or "").strip(),
                    str(parameters.get("last_frame_reference_url") or "").strip(),
                }
                _composition_urls.discard("")
                _identity_supplied_urls = [
                    url for url in reference_assets
                    if str(url or "").strip() not in _composition_urls
                ]
                if protected_mode:
                    reference_binding = reference_binding_for_requirements(
                        requirements,
                        supplied_urls=_identity_supplied_urls,
                        required_character_ids=required_character_ids,
                    )
                else:
                    # Use exact existing canonical records, not every eligible
                    # character anchor in the scene. Preserve source order,
                    # and disambiguate same-URI assets by their persisted IDs.
                    candidate_binding = reference_binding_for_requirements(
                        requirements,
                        required_character_ids=required_character_ids,
                    )
                    declared_reference_ids = shot.get("approved_reference_ids")
                    if declared_reference_ids is None:
                        visual_plan = shot.get("visual_plan") if isinstance(shot.get("visual_plan"), dict) else {}
                        declared_reference_ids = visual_plan.get("reference_asset_ids")
                    if declared_reference_ids is not None:
                        if not isinstance(declared_reference_ids, list) or any(not str(value or "").strip() for value in declared_reference_ids):
                            raise ValueError("approved shot reference IDs are malformed")
                        id_order = [str(value) for value in declared_reference_ids]
                        if len(id_order) != len(set(id_order)):
                            raise ValueError("approved shot reference IDs are ambiguous or duplicated")
                        by_id = {str(row.get("ref_id") or ""): row for row in candidate_binding}
                        if len(by_id) != len(candidate_binding) or set(id_order) != set(by_id):
                            raise ValueError("approved shot reference IDs do not exactly match its focused eligible references")
                        reference_binding = [by_id[ref_id] for ref_id in id_order]
                    else:
                        # Legacy URI-only shot references can be retained only
                        # where every URI maps to exactly one focused canonical
                        # identity. Unknown or ambiguous URLs block instead of
                        # selecting a convenient substitute.
                        supplied_identity_uris = list(dict.fromkeys(_identity_supplied_urls))
                        if not supplied_identity_uris:
                            reference_binding = candidate_binding
                        else:
                            uri_order = supplied_identity_uris
                            by_uri: dict[str, list[dict[str, Any]]] = {}
                            for row in candidate_binding:
                                by_uri.setdefault(str(row.get("uri") or ""), []).append(row)
                            if len(uri_order) != len(candidate_binding) or any(
                                uri not in by_uri or len(by_uri[uri]) != 1 for uri in uri_order
                            ) or len(set(uri_order)) != len(uri_order):
                                raise ValueError("legacy approved shot reference selection is incomplete or ambiguous; re-approve with exact reference IDs")
                            reference_binding = [by_uri[uri][0] for uri in uri_order]
                    if any(
                        row.get("target_type") == "character"
                        and str(row.get("target_id") or "") not in set(required_character_ids)
                        for row in reference_binding
                    ):
                        raise ValueError("approved shot reference selection contains a character outside its required focus")
                    reference_ids = [str(row.get("ref_id") or "") for row in reference_binding]
                    if len(reference_ids) != len(set(reference_ids)):
                        raise ValueError("approved shot reference selection contains duplicate reference IDs")
                    if not any(
                        row.get("target_type") == "setting"
                        and str(row.get("target_id") or "") == str(requirements.get("setting_id") or "")
                        for row in reference_binding
                    ):
                        raise ValueError("approved shot reference selection is missing its required setting reference")
                    selected_ids = set(reference_ids)
                    selected_character_ids = {
                        str(row.get("target_id") or "") for row in reference_binding
                        if row.get("target_type") == "character"
                    }
                    if selected_character_ids != set(required_character_ids):
                        raise ValueError("approved shot reference selection is missing a required focused character anchor")
                    requirements["characters"] = {
                        character_id: requirements["characters"][character_id]
                        for character_id in required_character_ids
                    }
                    requirements["character_ids"] = list(required_character_ids)
                    requirements["setting_references"] = [
                        row for row in reference_binding if row.get("target_type") == "setting"
                    ]
                    requirements["setting_urls"] = [row["uri"] for row in requirements["setting_references"]]
                    requirements["allowed_urls"] = [row["uri"] for row in reference_binding]
                    requirements["reference_binding"] = deepcopy(reference_binding)
                reference_projection_authorization = None
                generic_authorization_audit: dict[str, Any] | None = None
                if provider == "runway_router" and project_id == "project_5907c60cddbc" and scene_id == "scene_002":
                    reference_projection_authorization = self._build_reference_projection_authorization(
                        project_id=project_id,
                        scene_id=scene_id,
                        storyboard_version_id=board_version,
                        setting_decision=requirements.get("setting_reference_decision"),
                        version_contract={
                            "current_version_id": requirements.get("current_version_id"),
                            "approved_version_id": requirements.get("approved_version_id"),
                            "storyboard_version_id": requirements.get("storyboard_version_id"),
                            "production_version_authorized": requirements.get("production_version_authorized"),
                        },
                        binding=reference_binding,
                    )
                elif (
                    provider == "runway_router"
                    and mint_generic_authorization is True
                ):
                    # R4.5-B3.1 (F5, generic projection authorization). Generic
                    # Router entries mint their declaration record through the
                    # approved scene-mint service (persisted confirmation +
                    # environment basis, Q1-Q5) bound to this shot's frozen
                    # binding, storyboard triple, and setting authority. Scene
                    # 002 keeps its authority-pinned branch above, byte-identical.
                    # Minting is opt-in: dry-run/preview callers leave the flag
                    # off and see byte-identical outputs (None record).
                    minted = self._build_generic_reference_projection_authorization(
                        project_id=project_id,
                        scene_id=scene_id,
                        shot_id=shot_id,
                        storyboard_version_id=board_version,
                        binding=reference_binding,
                        scene=scene,
                        storage=_validation_storage,
                    )
                    reference_projection_authorization = minted["authorization"]
                    generic_authorization_audit = minted["audit"]
                reference_assets = [str(row["uri"]) for row in reference_binding]
                reference_roles = [str(row.get("role") or "reference") for row in reference_binding]
                context.reference_version = generation_context_service.reference_version(
                    reference_assets=reference_assets
                )
                bound_readiness = generation_context_service.validate_generation_context(
                    context=context,
                    current_scene=scene,
                    current_storyboard_context={"version": board_version} if board_version else None,
                    current_reference_assets=reference_assets,
                    expected_scene_id=scene_id,
                    expected_shot_id=shot_id,
                    current_shot=current_shot if current_shot is not None else shot,
                    canonical_script_text=(authority["screenplay_text"] if protected_mode else project.get("script_text")) if isinstance((authority["screenplay_text"] if protected_mode else project.get("script_text")), str) else None,
                )
                shot_blockers.extend(bound_readiness.blockers)
            except Exception as exc:
                shot_blockers.append(
                    f"reference gate: {getattr(exc, 'message', None) or str(exc) or type(exc).__name__}"
                )
                requirements = None
                reference_binding = []
                reference_roles = []
                reference_projection_authorization = None
                generic_authorization_audit = None

            # Reference requirements and their canonical binding are resolved
            # before collision detection. An unresolved/missing binding remains
            # empty and has already added a fail-closed reference blocker above.
            # Storyboard frames stay composition evidence: if the same URI is
            # also a canonical identity anchor, preserve both provenances and
            # let the existing aggregate collision gate block generation.
            frame_url = str(parameters.get("storyboard_frame_url") or "").strip()
            frame_identity_collision = bool(
                frame_url
                and any(
                    str(row.get("uri") or "") == frame_url and row.get("target_type") in {"character", "setting"}
                    for row in reference_binding
                )
            )
            # Collision provenance lives in the entry-level
            # ``storyboard_frame_identity_collision`` coverage flag and in the
            # frozen per-shot coverage record
            # (``scene_coverage_shot.storyboard_frame_identity_collision``,
            # written by ``freeze_generation_contract``). It is deliberately
            # not stored in ``parameters`` so it can never enter the canonical
            # ``creative_parameters`` path; ``EXECUTION_ONLY_PARAMETER_KEYS``
            # additionally classifies it as non-creative defense-in-depth.
            shot["parameters"] = deepcopy(parameters)

            # Cost gate — the shared implementation, evaluated for THIS shot
            # (the whole-batch projection is gated below via batch_estimate).
            # Ordinary Router quotes are checked in the provider adapter before
            # any live task. Contract-only requests carry explicit authorized
            # pricing policy and skip all preflight provider requests.
            try:
                estimate = generation_cost_gate.enforce_shot_limit(
                    project_id,
                    provider or "runway",
                    parameters,
                    "",
                    allow_unknown_cost_for_preflight=(provider or "runway") == "runway_router",
                )
            except _ValidationError as exc:
                shot_blockers.append(f"cost gate: {exc.message}")
                estimate = None

            try:
                if "dialogue_lines" in parameters:
                    supplied_dialogue_lines = parameters.get("dialogue_lines")
                    if not isinstance(supplied_dialogue_lines, list):
                        raise GenerationContractError("structured dialogue_lines must be a list")
                    dialogue_lines = self._dialogue_lines_for_shot(
                        project, scene_id, shot_id, supplied_lines=supplied_dialogue_lines
                    ) or []
                else:
                    dialogue_lines = self._dialogue_lines_for_shot(
                        project,
                        scene_id,
                        shot_id,
                        allow_scene_fallback=len(shots) == 1,
                    ) or []
            except GenerationContractError as exc:
                shot_blockers.append(f"dialogue handoff: {exc}")
                dialogue_lines = []
            try:
                dialogue_handoff = freeze_dialogue_handoff(
                    scene_id=scene_id, shot_id=shot_id, lines=dialogue_lines
                )
            except GenerationContractError as exc:
                shot_blockers.append(f"dialogue handoff: {exc}")
                dialogue_handoff = freeze_dialogue_handoff(scene_id=scene_id, shot_id=shot_id, lines=[])

            # The coverage contract is authoritative for dialogue selection.
            # Legacy handoff construction above remains a derived presentation
            # step, but cannot assign or invent a canonical line.
            entries.append(
                {
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "shot_id": shot_id,
                    "character_focus": deepcopy(shot.get("character_focus") or (shot.get("intent") or {}).get("character_focus", [])),
                    "storyboard_shot_id": storyboard_shot_id,
                    "shot_order": index,
                    "prompt": send_prompt if send_prompt_applies else prompt,
                    "image_prompt_ready": (not send_prompt_applies) or not send_prompt_error,
                    "image_prompt_sha256": send_prompt_sha256,
                    "scene_version": context.scene_version,
                    "source_shot_version": self._snapshot_fingerprint(shot),
                    "dialogue_handoff": dialogue_handoff,
                    "dialogue_lines": deepcopy(dialogue_handoff["payload"]["lines"]),
                    "generation_context": context.to_dict(),
                    "negative_prompt": str(parameters.get("negative_prompt") or ""),
                    "audio_intent": parameters.get("audio_intent", parameters.get("generate_audio", False)),
                    "reference_roles": list(reference_roles),
                    "reference_binding": deepcopy(reference_binding),
                    "reference_projection_authorization": deepcopy(reference_projection_authorization),
                    "generic_authorization_audit": deepcopy(generic_authorization_audit),
                    "storyboard_frame_identity_collision": frame_identity_collision,
                    "aspect_ratio": str(parameters.get("aspect_ratio") or parameters.get("ratio") or "16:9"),
                    "resolution": parameters.get("resolution"),
                    "seed": parameters.get("seed"),
                    "parameters": parameters,
                "generation_settings": {
                    **deepcopy(parameters),
                    **({"reference_projection_authorization": deepcopy(reference_projection_authorization)}
                       if reference_projection_authorization is not None else {}),
                },
                "manifest_provider": "runway_router" if provider == "runway_router" else "",
                    "duration_seconds": float(
                        shot.get("duration_seconds") or scene.get("duration_seconds") or 5
                    ),
                    "camera_instructions": [c.to_dict() for c in camera_instructions],
                    "camera_plan": deepcopy(parameters.get("camera_plan") or {}),
                    "camera_provenance": camera_provenance,

                    "camera_source_digest": parameters.get("camera_source_digest", ""),
                    "camera_source_project_id": parameters.get("camera_source_project_id", ""),
                    "camera_source_scene_id": parameters.get("camera_source_scene_id", ""),
                    "camera_source_shot_id": parameters.get("camera_source_shot_id", ""),
                    "camera_source_storyboard_shot_id": parameters.get("camera_source_storyboard_shot_id", ""),
                    "camera_target_project_id": parameters.get("camera_target_project_id", ""),
                    "camera_target_scene_id": parameters.get("camera_target_scene_id", ""),
                    "camera_target_shot_id": parameters.get("camera_target_shot_id", ""),
                    "references": reference_assets,
                    "reference_version": context.reference_version,
                    "generation_context_id": context.generation_context_id,
                    "shot_version": (
                        self._shot_version_with_image_prompt(context.shot_version, send_prompt_sha256)
                        if send_prompt_applies and not send_prompt_error and send_prompt_sha256
                        else context.shot_version
                    ),
                    "blockers": shot_blockers,
                    "cost_estimate": estimate,
                    "reference_requirements": (
                        {
                            "setting_id": requirements.get("setting_id"),
                            "setting_urls": requirements.get("setting_urls"),
                            "character_ids": requirements.get("scene_character_ids"),
                            "scene_character_ids": requirements.get("scene_character_ids"),
                            "characters": deepcopy(requirements.get("scene_characters") or {}),
                            "approved_scene_binding": deepcopy(requirements.get("approved_scene_binding") or []),
                            "required_character_ids": list(required_character_ids),
                            "reference_binding": deepcopy(reference_binding),
                        }
                        if requirements
                        else None
                    ),
                }
            )

        for entry in entries:
            blockers.extend(f"Shot {entry['shot_id']}: {blocker}" for blocker in entry["blockers"])

        # Build authoritative scene/dialogue coverage only after explicit shot
        # assignments and approved reference requirements have been resolved.
        # Current version-scoped Scene Direction decisions are the only source
        # of assignment/omission/silence; legacy fields cannot satisfy coverage.
        coverage_requirements = next((
            {**(entry.get("reference_requirements") or {}),
             "characters": deepcopy((entry.get("reference_requirements") or {}).get("characters") or {}),
             "reference_binding": deepcopy((entry.get("reference_requirements") or {}).get("approved_scene_binding") or [])}
            for entry in entries if entry.get("reference_requirements")
        ), {})
        if protected_mode:
            # An explicit frozen authority is the execution boundary, not an
            # instruction to run readiness or repair mutable canonical state.
            blockers.clear()
            for entry in entries:
                entry["blockers"] = []
            coverage_requirements["setting_id"] = authority["setting_identity"]["setting_id"]
            coverage_requirements["characters"] = {
                str(row.get("target_id")): {"name": str(row.get("target_id"))}
                for row in authority["reference_bindings"] if row.get("target_type") == "character"
            }
            coverage_requirements["reference_binding"] = deepcopy(authority["reference_bindings"])
        if protected_mode:
            coverage_contract = deepcopy(authority["coverage_contract"])
            shot_manifest = deepcopy(authority["creative_manifest"])
            authoritative_rows = shot_manifest.get("shots") if isinstance(shot_manifest.get("shots"), list) else []
            for entry in entries:
                rows = [row for row in authoritative_rows if isinstance(row, dict) and row.get("shot_id") == entry.get("shot_id")]
                frozen_record = authority["generation_contracts_by_shot"].get(str(entry.get("shot_id") or ""))
                if len(rows) != 1 or not isinstance(frozen_record, dict):
                    raise ValidationError("Explicit authority does not pin a complete ordered shot contract", stage="scene_pipeline_contract")
                from app.services.generation_contract import FrozenGenerationContract
                frozen = FrozenGenerationContract.from_record(frozen_record)
                entry["prompt"] = frozen.prompt
                entry["negative_prompt"] = frozen.negative_prompt
                entry["generation_contract"] = frozen_record
                entry["dialogue_handoff"] = frozen.payload().get("dialogue_handoff")
                entry["scene_coverage"] = coverage_contract
                entry["shot_coverage"] = frozen.payload().get("scene_coverage_shot")
                entry["reference_binding"] = deepcopy(authority["reference_bindings"])
                entry["references"] = [row.get("uri") for row in authority["reference_bindings"]]
                entry["reference_roles"] = [row.get("role") for row in authority["reference_bindings"]]
                entry["generation_settings"] = deepcopy(frozen.payload())
                entry["duration_seconds"] = frozen.duration or 0
                entry["aspect_ratio"] = frozen.aspect_ratio
                entry["resolution"] = frozen.resolution
                entry["seed"] = frozen.seed
                rows[0]["shot_prompt"] = frozen.prompt
            from app.services.shot_manifest import recompute_manifest_fingerprint
            if recompute_manifest_fingerprint(shot_manifest) != authority["authorized_creative_fingerprint"]:
                raise ValidationError("Explicit authoritative manifest fingerprint is invalid", stage="scene_pipeline_contract")
            from app.services.scene_coverage_contract import verify_scene_coverage_contract
            try:
                verify_scene_coverage_contract(coverage_contract)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"Frozen authorized coverage is invalid: {exc}", stage="scene_pipeline_contract") from exc
            if coverage_contract.get("creator_decisions") != authority["coverage_decisions"]:
                raise ValidationError("Frozen authorized coverage differs from its explicit authority", stage="scene_pipeline_contract")
            coverage_blockers = []
            coverage_dialogue = {
                str(row.get("shot_id") or ""): [
                    line for line in coverage_contract.get("dialogue", [])
                    if line.get("dialogue_id") in set(row.get("covered_dialogue_ids") or [])
                ]
                for row in coverage_contract.get("shots", []) if isinstance(row, dict)
            }
        else:
            coverage_contract, coverage_blockers, coverage_dialogue = build_scene_coverage_contract(
                project_id=project_id,
                project=coverage_project,
                scene=scene,
                shots=shots,
                reference_requirements=coverage_requirements,
                creator_decisions=creator_coverage_decisions,
                legacy_sources_blocked=True,
            )
        if protected_mode and (
            not coverage_contract.get("creator_decisions")
            or coverage_contract.get("creator_decisions") != authority["coverage_decisions"]
        ):
            raise ValidationError("Protected coverage is not completely authorized by the frozen authority record", stage="scene_pipeline_contract")
        blockers.extend(coverage_blockers)
        # Storyboard-frame identity collision: a board frame bound as a canonical
        # character/setting anchor cannot silently become identity truth. Fail
        # the readiness gate closed until the creator separates the provenance
        # (dedicated identity anchor or a distinct composition frame).
        for entry in entries:
            if entry.get("storyboard_frame_identity_collision"):
                blockers.append(
                    f"shot {entry['shot_id']} storyboard frame is also bound as a canonical identity"
                    " reference; separate composition conditioning from identity anchoring"
                    " before generation"
                )
        coverage_shots = {row["shot_id"]: row for row in coverage_contract["shots"]}
        for entry in entries:
            shot_coverage = coverage_shots.get(entry["shot_id"])
            if not shot_coverage:
                blockers.append(f"shot {entry['shot_id']} coverage contract is missing")
                continue
            entry["scene_coverage"] = deepcopy(coverage_contract)
            entry["shot_coverage"] = deepcopy(shot_coverage)
            # The earlier per-shot resolver already used the approved shot
            # focus and canonical registry. Coverage now independently records
            # its authorized ordered selection; disagreement blocks here rather
            # than triggering another ranking, substitution, or widening pass.
            from app.services.reference_validation import (
                reference_binding_coverage_projection,
                verify_shot_reference_coverage_binding,
            )
            actual_binding = reference_binding_coverage_projection(entry.get("reference_binding") or [])
            try:
                verify_shot_reference_coverage_binding(
                    actual_binding=actual_binding,
                    coverage_shot=shot_coverage,
                )
            except ValueError as exc:
                blockers.append(f"shot {entry['shot_id']} {exc}")
            expected_dialogue = coverage_dialogue.get(entry["shot_id"], [])
            explicit_handoff_lines = [
                {**row, "scene_id": scene_id, "shot_id": entry["shot_id"]}
                for row in expected_dialogue
                if str(row.get("line_id") or "") in set(shot_coverage.get("covered_dialogue_ids") or [])
            ]
            entry["dialogue_handoff"] = freeze_dialogue_handoff(
                scene_id=scene_id, shot_id=entry["shot_id"], lines=explicit_handoff_lines
            )
            if {
                str(row.get("line_id") or "") for row in entry["dialogue_handoff"]["payload"]["lines"]
            } != set(shot_coverage.get("covered_dialogue_ids") or []):
                blockers.append(
                    f"shot {entry['shot_id']} frozen dialogue handoff does not match current creator coverage"
                )
            entry["dialogue_lines"] = deepcopy(explicit_handoff_lines)
            # Provenance stamping: prove the frozen handoff corresponds to the
            # canonical dialogue covered by this shot. Unassigned, omitted, or
            # unresolved lines must never appear as authoritative dialogue.
            covered_by_shot = set(shot_coverage.get("covered_dialogue_ids") or [])
            for row in explicit_handoff_lines:
                if str(row.get("line_id") or "") not in covered_by_shot:
                    blockers.append(
                        f"shot {entry['shot_id']} dialogue handoff contains a line that"
                        f" coverage does not assign to this shot: {row.get('line_id')}"
                    )
            # Prompt consistency: the approved prompt must agree with the shot's
            # resolved coverage. Divergence is exposed as a blocking integrity
            # error — approved prompts are never silently rewritten.
            from app.services.generation_contract import _prompt_dialogue_problems

            all_canonical_lines = coverage_contract.get("dialogue") or []
            assigned_lines = [line for line in all_canonical_lines if line["dialogue_id"] in covered_by_shot]
            not_assigned_lines = [line for line in all_canonical_lines if line["dialogue_id"] not in covered_by_shot]
            prompt_problems = _prompt_dialogue_problems(
                prompt=entry["prompt"],
                assigned_dialogue=assigned_lines,
                omitted_dialogue=not_assigned_lines,
            )
            if prompt_problems:
                entry["prompt_coverage_problems"] = prompt_problems
                blockers.extend(
                    f"shot {entry['shot_id']} prompt/coverage mismatch: {problem}"
                    for problem in prompt_problems
                )

        # Batch-level preflight cost picture. A total is populated only when

        # every shot has an honest provider/model estimate; routed jobs remain
        # explicitly unpriced until Runway reports routing/cost metadata.
        # No downgrade or prompt/duration adjustment is performed here.
        batch_estimate = generation_cost_gate.estimate_batch(
            provider=provider or "runway",
            shots=[shot.get("parameters") or {} for shot in shots],
        )
        if provider == "runway_router":
            # R4.5-B1 (F8, owner decision 3: freeze {} for Router jobs, never
            # for non-router providers). The nine selection keys are class (2)
            # metadata whose authoritative carriers (scene_coverage,
            # dialogue_handoff, references) are frozen and verified
            # independently; the frozen creative parameters stay empty so the
            # Router wire body — which has no field for them — loses nothing.
            # The stripped values are recorded as digest-linked evidence, not
            # dropped silently (linked to the contract digest below).
            for entry in entries:
                selection: dict[str, Any] = {}
                entry_parameters = entry.get("parameters")
                entry_settings = entry.get("generation_settings")
                for selection_key in ROUTER_SELECTION_EVIDENCE_KEYS:
                    if isinstance(entry_parameters, dict) and selection_key in entry_parameters:
                        selection[selection_key] = deepcopy(entry_parameters.pop(selection_key))
                    if isinstance(entry_settings, dict) and selection_key in entry_settings:
                        entry_settings.pop(selection_key, None)
                entry["router_selection_evidence"] = {"selection": selection}
        # Freeze each shot's approved values before deriving the manifest
        # fingerprint. The manifest records the provider-neutral contract digest;
        # execution resolution and cost never enter it.
        from app.services.generation_contract import FrozenGenerationContract, freeze_generation_contract

        for entry in entries:
            if entry_freeze_blocked(entry):
                # Per-shot freeze: only this entry's own unresolved coverage
                # (UNRESOLVED state or prompt/coverage mismatch) or its own
                # missing/unapproved/stale image prompt blocks its contract.
                # One bad shot no longer poisons the batch: healthy entries
                # still freeze so the batch verdict can name the single bad
                # shot instead of producing zero contracts. Batch-level
                # `blockers` still carry the global verdict. Blocked entries
                # carry an empty sendable prompt so the manifest renders
                # "Prompt unavailable" instead of stale board text.
                entry["generation_contract"] = None
                entry["generation_contract_digest"] = ""
                continue
            if provider == "runway_router" and entry.get("seed") is None:
                # R4.5-B1 (F9, owner decision 2: seed before freeze). The seed
                # decided here flows into the frozen contract, the manifest
                # and the persisted job input before the last durable write,
                # so submit-time performs no post-authorization mutation.
                # Non-router batches keep the existing submit-time lock and
                # explicit seeds are never replaced.
                decided_seed = _decide_router_seed_before_freeze(
                    project_id=project_id, shot_id=str(entry.get("shot_id") or "")
                )
                if decided_seed is not None:
                    entry["seed"] = decided_seed
            approved_parameters = deepcopy(entry.get("parameters") or {})
            approved_parameters["project_id"] = project_id
            approved_parameters["scene_id"] = scene_id
            approved_parameters["duration"] = entry["duration_seconds"]
            approved_parameters["aspect_ratio"] = entry["aspect_ratio"]
            if entry.get("resolution") is not None:
                approved_parameters["resolution"] = entry["resolution"]
            if entry.get("seed") is not None:
                approved_parameters["seed"] = entry["seed"]
            approved_parameters["reference_roles"] = list(entry.get("reference_roles") or [])

            approved_parameters["audio_intent"] = entry.get("audio_intent", False)
            approved_parameters["negative_prompt"] = entry.get("negative_prompt", "")
            camera_plan = deepcopy(entry.get("camera_plan") or {})
            approved_parameters["camera_plan"] = camera_plan
            approved_parameters["camera_provenance"] = entry["camera_provenance"]
            approved_parameters["camera_instructions"] = deepcopy(entry.get("camera_instructions") or [])
            approved_parameters["camera_source_digest"] = entry["camera_source_digest"]
            approved_parameters["project_id"] = project_id
            approved_parameters["scene_id"] = scene_id
            for field in (
                "camera_source_project_id", "camera_source_scene_id", "camera_source_shot_id",
                "camera_source_storyboard_shot_id", "camera_target_project_id",
                "camera_target_scene_id", "camera_target_shot_id", "camera_instructions",
            ):
                approved_parameters[field] = entry.get(field, "")
            approved_parameters["dialogue_lines"] = deepcopy(entry["dialogue_handoff"]["payload"]["lines"])
            approved_parameters["dialogue_handoff"] = deepcopy(entry["dialogue_handoff"])
            approved_parameters["scene_coverage"] = deepcopy(entry.get("scene_coverage") or {})
            approved_parameters["scene_coverage_shot"] = deepcopy(entry.get("shot_coverage") or {})
            if entry.get("reference_projection_authorization") is not None:
                entry["generation_settings"]["reference_projection_authorization"] = deepcopy(entry["reference_projection_authorization"])
            reference_rows = [
                {
                    "uri": row["uri"],
                    "studio_role": row.get("role") or "reference",
                    "source": "canonical_reference_binding",
                    "ref_id": row.get("ref_id") or "",
                    "target_type": row.get("target_type") or "",
                    "target_id": row.get("target_id") or "",
                    "category": row.get("category") or "",
                    "canonical": bool(row.get("canonical")),
                    "approval_state": row.get("approval_state") or "approved",
                    "source_kind": row.get("source_kind") or "confirmed",
                    "kind": row.get("kind") or "character_face",
                }
                for row in entry.get("reference_binding") or []
            ]
            try:
                frozen = freeze_generation_contract(
                    shot_id=entry["shot_id"],
                    prompt=entry["prompt"],
                    negative_prompt=entry["negative_prompt"],
                    reference_assets=reference_rows,
                    parameters=approved_parameters,
                    dialogue_handoff=entry["dialogue_handoff"],
                    scene_coverage=entry.get("scene_coverage"),
                    scene_coverage_shot=entry.get("shot_coverage"),
                )
            except GenerationContractError as exc:
                # A freeze refusal (e.g. scene-wide coverage still unresolved)
                # holds out this entry only: the batch stays inspectable and
                # sibling shots are unaffected. Freeze stays fail-closed; the
                # refusal is recorded on the entry and the batch verdict.
                entry["generation_contract"] = None
                entry["generation_contract_digest"] = ""
                freeze_blocker = f"freeze refused: {exc}"
                if isinstance(entry.get("blockers"), list):
                    entry["blockers"].append(freeze_blocker)
                blockers.append(f"Shot {entry['shot_id']}: {freeze_blocker}")
                continue
            entry["generation_contract"] = frozen.to_record()
            entry["generation_contract_digest"] = frozen.creative_digest()
            entry["duration_seconds"] = frozen.duration or 0
            entry["audio_intent"] = frozen.audio
            entry["aspect_ratio"] = frozen.aspect_ratio
            entry["resolution"] = frozen.resolution
            entry["seed"] = frozen.seed
            entry["camera_plan"] = json.loads(frozen.camera_plan_json)
            entry["references"] = [reference.uri for reference in frozen.references]
            entry["reference_roles"] = [reference.studio_role for reference in frozen.references]
            # Deterministic reference binding contract: the raw canonical
            # binding (character rows: 10 keys; setting rows: 11 keys with
            # ``project_id``) and the frozen contract (normalized 12-key
            # payload with ``role="reference"`` and
            # ``source="canonical_reference_binding"``) are different schemas,
            # so strict dict equality is invalid. Project the raw binding onto
            # the frozen shape (same projection as the generate-scene
            # verification path) and compare only the canonical references in
            # the frozen contract. Storyboard/last-frame composition references
            # appended by ``freeze_generation_contract()`` are a separate
            # provenance and must not fail the canonical invariant. Fail closed
            # on any genuine canonical difference; ordering is preserved.
            expected_canonical_references = _canonical_binding_to_contract_references(
                entry.get("reference_binding")
            )
            canonical_frozen_references = _canonical_frozen_references(frozen)
            if canonical_frozen_references != expected_canonical_references:
                raise GenerationContractError("Frozen generation contract references do not match prepared canonical reference binding")
            entry["generation_contract"] = frozen.to_record()
            entry["generation_settings"].update(
                frozen_reference_binding=deepcopy(entry.get("reference_binding")),
                duration=frozen.duration,
                aspect_ratio=frozen.aspect_ratio,
                resolution=frozen.resolution,
                seed=frozen.seed,
                negative_prompt=frozen.negative_prompt,
                audio_intent=frozen.audio,
                camera_plan=json.loads(frozen.camera_plan_json),
                camera_provenance=entry["camera_provenance"],
                camera_source_digest=entry["camera_source_digest"],
                camera_source_project_id=entry.get("camera_source_project_id", ""),
                camera_source_scene_id=entry.get("camera_source_scene_id", ""),
                camera_source_shot_id=entry.get("camera_source_shot_id", ""),
                camera_source_storyboard_shot_id=entry.get("camera_source_storyboard_shot_id", ""),
                reference_roles=list(entry["reference_roles"]),
                dialogue_lines=deepcopy(entry["dialogue_handoff"]["payload"]["lines"]),
                dialogue_handoff=deepcopy(entry["dialogue_handoff"]),
                scene_coverage=deepcopy(entry.get("scene_coverage") or {}),
                scene_coverage_shot=deepcopy(entry.get("shot_coverage") or {}),
            )

        if protected_mode:
            manifest = deepcopy(authority["creative_manifest"])
            if manifest != shot_manifest:
                raise ValidationError("Protected inputs cannot reconstruct or alter the authorized manifest", stage="scene_pipeline_contract")
        else:
            manifest = build_shot_manifest(
                project_id=project_id,
                scene_id=scene_id,
                scene=scene,
                scene_version=generation_context_service.scene_version(
                    scene, project.get("script_text") if isinstance(project.get("script_text"), str) else None
                ),
                storyboard_version=str(
                    next((str((shot.get("parameters") or {}).get("storyboard", {}).get("version_id") or "") for shot in shots if isinstance((shot.get("parameters") or {}).get("storyboard"), dict)), "")
                ),
                entries=entries,
                generation_context_ids=generation_context_ids,
                scene_lineage=lineage,
            )
        from dataclasses import replace

        for entry in entries:
            if not entry.get("generation_contract"):
                continue
            contract = FrozenGenerationContract.from_record(entry["generation_contract"])
            final_contract = replace(
                contract, manifest_fingerprint=manifest["manifest_fingerprint"]
            )
            entry["generation_contract"] = final_contract.to_record()
            entry["generation_contract_digest"] = final_contract.creative_digest()

        if provider == "runway_router":
            # Digest-link the selection evidence created above. The creative
            # digest excludes the manifest fingerprint, so it is stable across
            # the fingerprint replacement just performed.
            for entry in entries:
                evidence = entry.get("router_selection_evidence")
                if (
                    isinstance(evidence, dict)
                    and entry.get("generation_contract")
                    and entry.get("generation_contract_digest")
                ):
                    evidence["contract_digest"] = str(entry["generation_contract_digest"])
        for entry in entries:
            entry["manifest_fingerprint"] = manifest["manifest_fingerprint"]
            entry["generation_settings"].setdefault("negative_prompt", entry["negative_prompt"])
            entry["generation_settings"]["camera_plan"] = deepcopy(entry["camera_plan"])
            entry["generation_settings"]["camera_provenance"] = entry["camera_provenance"]
            entry["generation_settings"]["camera_source_digest"] = entry["camera_source_digest"]
            entry["generation_settings"]["camera_instructions"] = deepcopy(entry.get("camera_instructions") or [])
            for field in (
                "camera_source_project_id",
                "camera_source_scene_id",
                "camera_source_shot_id",
                "camera_source_storyboard_shot_id",
                "camera_target_project_id",
                "camera_target_scene_id",
                "camera_target_shot_id",
            ):

                entry["generation_settings"][field] = entry.get(field, "")
            entry["generation_settings"]["scene_coverage"] = deepcopy(entry.get("scene_coverage") or {})
            entry["generation_settings"]["scene_coverage_shot"] = deepcopy(entry.get("shot_coverage") or {})
            entry["generation_settings"].setdefault("reference_roles", list(entry["reference_roles"]))
            entry["generation_settings"].setdefault("frozen_reference_binding", deepcopy(entry["reference_binding"]))
            entry["generation_settings"]["preserve_shot_prompt"] = True


        batch = {
            "project_id": project_id,
            "scene_id": scene_id,
            "ready": not blockers,
            "blockers": blockers,
            "shots": shots,
            "entries": entries,
            "scene_coverage": coverage_contract,
            "manifest": manifest,
            "generation_context_ids": generation_context_ids,
            "cost_estimate": batch_estimate,
            "scene_snapshot": scene,
            "scene_snapshot_fingerprint": self._snapshot_fingerprint(scene),
            "canonical_script_sha256": hashlib.sha256(str((authority or {}).get("screenplay_text") if protected_mode else project.get("script_text") or "").encode("utf-8")).hexdigest(),
            "source_kind": source_kind,
            "source_key": source_key,
            "shot_source_fingerprint": shot_source_fingerprint,
            "provider": provider,
            **({
                "execution_mode": "SCENE_002_CONTRACT_ONLY",
                "source_authority_id": source_authority_id,
                "source_authority": deepcopy(authority),
                "project_revision_guard_sha256": project_revision_guard(original_project),
            } if protected_mode and authority else {}),
        }
        if not blockers:
            self._register_prepared_scene_batch(batch, provider=provider)
        return batch

    def _build_reference_projection_authorization(
        self,
        *,
        project_id: str,
        scene_id: str,
        storyboard_version_id: str,
        setting_decision: Any,
        version_contract: Any,
        binding: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bind persisted Scene Direction authority to the actual frozen production proof."""
        from app.services.reference_validation import reference_binding_digest
        from app.services.scene_direction_service import SceneDirectionService
        from app.services import runway_reference_projection as projection
        from app.services.runway_ephemeral_upload import resolve_canonical_bytes
        from app.services.reference_asset_service import scene002_setting_asset_view
        from app.services.scene002_contract_only import Scene002ContractError
        from app.services.stability import ValidationError as _ValidationError

        storage = getattr(self.render_service, "_storage", None)
        if storage is None:
            from app.data.storage import get_storage
            storage = get_storage("sqlite")
        blueprint = storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None:
            raise _ValidationError("Runway setting authorization requires a storyboard authority", stage="scene_pipeline_reference_authority")
        current_id = str(getattr(blueprint, "current_version_id", "") or "")
        approved_id = str(getattr(blueprint, "approved_version_id", "") or "")
        if not approved_id and str(getattr(blueprint, "status", "")) == "approved":
            approved_id = current_id
        version_id = str((version_contract or {}).get("storyboard_version_id") or "")
        version = storage.get_storyboard_blueprint_version(version_id) if version_id else None
        if (
            not (version_contract or {}).get("production_version_authorized")
            or not current_id or current_id != approved_id or current_id != version_id
            or version_id != storyboard_version_id
            or version is None
            or str(getattr(version, "project_id", "")) != project_id
            or str(getattr(version, "scene_id", "")) != scene_id
            or str(getattr(getattr(version, "status", ""), "value", getattr(version, "status", ""))) != "approved"
            or any(str((version_contract or {}).get(key) or "") != version_id for key in ("current_version_id", "approved_version_id", "storyboard_version_id"))
        ):
            raise _ValidationError("Runway authorization is not tied to the current approved storyboard version", stage="scene_pipeline_reference_authority")
        persisted_decision = SceneDirectionService(storage)._setting_reference_decision(version)
        if persisted_decision is None or persisted_decision.model_dump(mode="json") != setting_decision:
            raise _ValidationError("Persisted Scene Direction decision changed before reference authorization", stage="scene_pipeline_reference_authority")
        setting_id = str(setting_decision.canonical_setting_id)
        selected_id = str(setting_decision.reference_id)
        selected_rows = [
            row for row in binding
            if isinstance(row, dict) and row.get("target_type") == "setting"
            and str(row.get("target_id") or "") == setting_id
            and str(row.get("ref_id") or "") == selected_id
            and str(row.get("kind") or "") == "environment"
        ]
        all_setting_rows = [row for row in binding if isinstance(row, dict) and row.get("target_type") == "setting"]
        if len(selected_rows) != 1 or len(all_setting_rows) != 1:
            raise _ValidationError("Frozen binding must carry exactly the explicitly selected setting environment", stage="scene_pipeline_reference_authority")
        selected = selected_rows[0]
        if (
            str(selected.get("project_id") or "") != project_id
            or str(selected.get("approval_state") or "") != "approved"
            or selected.get("canonical") is not True
            or str(selected.get("target_id") or "") != setting_id
        ):
            raise _ValidationError("Selected environment reference is not approved and canonical for the exact project setting", stage="scene_pipeline_reference_authority")
        row = storage.get_reference_asset(selected_id)
        if (
            not isinstance(row, dict) or str(row.get("project_id") or "") != project_id
            or str(row.get("target_type") or "") != "setting" or str(row.get("target_id") or "") != setting_id
            or str(row.get("kind") or "") != "environment" or str(row.get("approval_state") or "") != "approved"
            or not bool(row.get("canonical")) or str(row.get("approval_state") or "") == "rejected"
        ):
            raise _ValidationError("Selected environment reference is stale, rejected, or ambiguous", stage="scene_pipeline_reference_authority")
        uri = str(selected.get("uri") or "")
        row_uri = str(row.get("image_url") or "")
        if row_uri.startswith(("/outputs/", "/previs-assets/")):
            visible = scene002_setting_asset_view(row)
            uri = str(visible.get("image_url") or "") if visible else ""
        elif row_uri.lower().startswith(("http://", "https://")):
            uri = row_uri
        if not uri:
            raise _ValidationError("Selected environment reference has no usable canonical URI", stage="scene_pipeline_reference_authority")
        try:
            from urllib.parse import urlparse

            parsed_uri = urlparse(uri)
            if parsed_uri.scheme:
                fingerprint = hashlib.sha256(uri.encode("utf-8")).hexdigest()
            else:
                content = resolve_canonical_bytes(uri, ref_id=selected_id, backend_root=self.backend_root)
                fingerprint = hashlib.sha256(content).hexdigest()
        except (Scene002ContractError, OSError, ValueError) as exc:
            raise _ValidationError("Selected environment fingerprint could not be verified", stage="scene_pipeline_reference_authority") from exc
        return {
            "authorization_policy_id": projection.AUTHORIZATION_POLICY_ID,
            "project_id": project_id,
            "scene_id": scene_id,
            "setting_id": setting_id,
            "current_version_id": current_id,
            "approved_version_id": approved_id,
            "storyboard_version_id": version_id,
            "authorized_environment_ref_id": selected_id,
            "rejected_environment_ref_ids": [],
            "frozen_reference_binding_sha256": reference_binding_digest(binding),
            "frozen_reference_binding": deepcopy(binding),
            "source_fingerprint": fingerprint,
        }

    def _build_generic_reference_projection_authorization(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_id: str,
        storyboard_version_id: str,
        binding: list[dict[str, Any]],
        scene: dict[str, Any] | None,
        storage: Any,
    ) -> dict[str, Any]:
        """Mint a generic Router projection authorization through the scene-mint service.

        R4.5-B3.1 (F5): the approved ``scene_mint_service`` (persisted
        confirmation + environment basis, Q1-Q5) enforces the mint liveness —
        a stored per-shot confirmation must exist, the environment basis must
        cover every live non-authorized row, and the rejected list must
        exactly match the live rejected enumeration (A1: empty for
        single-environment scenes). This builder binds that
        minted pass to the shot's frozen binding, storyboard version triple,
        and canonical setting authority, returning ``{"authorization": ...,
        "audit": ...}``. Any failure raises fail-closed; the caller records
        it as a prepare blocker with zero jobs.

        Focused-shot note: per-shot entries legitimately narrow the scene cast
        (``character_focus``), while durable confirmations cover the
        scene-level canonical resolution — the same semantic the batch
        preflight enforces (stored digest vs freshly resolved binding, never
        entry vs stored). The record therefore carries ``confirmed_digest``
        (scene-level creator approval, verified live here at mint) alongside
        ``frozen_reference_binding_sha256`` (the entry chain the adapter
        re-verifies). The adapter never equates the two; each chain is
        verified at its own gate.
        """
        from app.services import runway_reference_projection as projection
        from app.services.reference_asset_service import ReferenceAssetService
        from app.services.reference_validation import (
            _approved_setting_references,
            _asset_rows,
            reference_binding_digest,
            resolve_canonical_setting_id,
        )
        from app.services.reference_validation import _verify_setting_identity_provenance
        from app.services.scene_direction_service import SceneDirectionService
        from app.services.scene_mint_service import (
            EnvironmentRowStore,
            SceneMintService,
            ShotConfirmationStore,
        )
        from app.services.stability import (
            elapsed_ms,
            log_stage_event,
            start_timer,
        )
        from app.services.stability import ValidationError as _ValidationError

        started = start_timer()
        stage = "scene_pipeline_reference_authority"

        def _refuse(code: str, message: str) -> _ValidationError:
            log_stage_event(
                project_id=project_id,
                job_id=shot_id,
                provider="runway_router",
                stage=stage,
                duration_ms=elapsed_ms(started),
                extra={"result": "refused", "code": code},
            )
            return _ValidationError(message, stage=stage, metadata={"failure_type": code})

        try:
            if not isinstance(binding, list) or not binding:
                raise _refuse("missing_reference_authority", f"Shot {shot_id} carries no frozen reference binding to authorize.")
            # M5 — storyboard version authority: the per-shot board version
            # must equal the live current==approved triple (non-empty).
            blueprint = storage.get_storyboard_blueprint(project_id, scene_id) if storage is not None else None
            if blueprint is None:
                raise _refuse("missing_storyboard_version_authority", f"Shot {shot_id} has no storyboard authority to mint against.")
            current_id = str(getattr(blueprint, "current_version_id", "") or "")
            approved_id = str(getattr(blueprint, "approved_version_id", "") or "")
            triple = str(storyboard_version_id or "").strip()
            if not triple or not current_id or current_id != approved_id or current_id != triple:
                raise _refuse(
                    "storyboard_version_authority_mismatch",
                    f"Shot {shot_id} is not pinned to the current approved storyboard version.",
                )
            version = storage.get_storyboard_blueprint_version(triple)
            version_status = str(getattr(getattr(version, "status", ""), "value", getattr(version, "status", "")) if version is not None else "").strip().lower()
            if (
                version is None
                or str(getattr(version, "project_id", "") or "") != project_id
                or str(getattr(version, "scene_id", "") or "") != scene_id
                or version_status not in {"approved", "locked"}
            ):
                raise _refuse(
                    "storyboard_version_authority_mismatch",
                    f"Shot {shot_id} storyboard version is not an approved production version.",
                )
            # M3/M4 — persisted confirmation, verified live against the fresh
            # canonical resolution (the same verifier the batch preflight uses).
            binder = ReferenceAssetService(storage)
            stored_row = storage.get_shot_reference_confirmation(project_id, shot_id)
            stored_digest = str((stored_row or {}).get("confirmed_digest") or "").strip()
            if not stored_digest:
                raise _refuse(
                    "missing_confirmation",
                    f"Shot {shot_id} has no durable reference-binding confirmation; confirm the shot's current binding before submitting.",
                )
            try:
                binder.verify_confirmed_binding(project_id, shot_id, stored_digest)
            except _ValidationError as exc:
                raise _refuse(
                    str((exc.metadata or {}).get("failure_type") or "confirmed_reference_binding_stale"),
                    str(exc.message),
                ) from exc
            # M6 — setting authority: exactly one setting row in the frozen
            # binding, approved + canonical + project-scoped; the persisted
            # Scene Direction decision binds it when one exists, otherwise the
            # canonical setting resolution + provenance check decides.
            setting_rows = [row for row in binding if isinstance(row, dict) and row.get("target_type") == "setting"]
            if len(setting_rows) != 1:
                raise _refuse("ambiguous_setting_authority", f"Shot {shot_id} must carry exactly one canonical setting anchor.")
            selected = setting_rows[0]
            selected_id = str(selected.get("ref_id") or "")
            setting_id = str(selected.get("target_id") or "")
            if (
                not selected_id
                or not setting_id
                or str(selected.get("project_id") or "") != project_id
                or str(selected.get("approval_state") or "") != "approved"
                or selected.get("canonical") is not True
                or str(selected.get("kind") or "") != "environment"
            ):
                raise _refuse(
                    "missing_setting_authority",
                    f"Shot {shot_id} setting anchor is not an approved canonical environment for this project.",
                )
            live_row = storage.get_reference_asset(selected_id)
            if (
                not isinstance(live_row, dict)
                or str(live_row.get("project_id") or "") != project_id
                or str(live_row.get("target_type") or "") != "setting"
                or str(live_row.get("target_id") or "") != setting_id
                or str(live_row.get("kind") or "") != "environment"
                or str(live_row.get("approval_state") or "") != "approved"
                or not bool(live_row.get("canonical"))
            ):
                raise _refuse(
                    "missing_setting_authority",
                    f"Shot {shot_id} setting anchor is stale, rejected, or ambiguous.",
                )
            try:
                persisted_decision = SceneDirectionService(storage)._setting_reference_decision(version)
            except Exception:  # noqa: BLE001 — no persisted decision reads as absent
                persisted_decision = None
            if persisted_decision is not None:
                if (
                    str(persisted_decision.canonical_setting_id) != setting_id
                    or str(persisted_decision.reference_id) != selected_id
                ):
                    raise _refuse(
                        "missing_setting_authority",
                        f"Shot {shot_id} setting anchor does not match the persisted Scene Direction decision.",
                    )
            else:
                canonical_setting_id = resolve_canonical_setting_id(
                    project_id=project_id, scene_id=scene_id, storage=storage, scene=scene,
                )
                if canonical_setting_id != setting_id:
                    raise _refuse("missing_setting_authority", f"Shot {shot_id} setting anchor is not the canonical setting.")
                _verify_setting_identity_provenance(
                    storage=storage, project_id=project_id, scene_id=scene_id,
                    setting_id=setting_id, require_approved_anchor=True,
                )
            # M7 — environment enumeration through the approved mint service:
            # every live environment row for the setting enters the mint
            # stores with its real approval state; the mint records the exact
            # rejected enumeration (A1: possibly empty for single-environment
            # scenes) and enforces basis coverage (Q2).
            env_rows = [
                row for row in _asset_rows(storage, project_id=project_id, target_type="setting", target_id=setting_id)
                if isinstance(row, dict) and str(row.get("kind") or "") == "environment" and str(row.get("ref_id") or "").strip()
            ]
            approved_anchors = _approved_setting_references(storage, project_id=project_id, setting_id=setting_id)
            if len(approved_anchors) != 1 or str(approved_anchors[0].get("ref_id") or "") != selected_id:
                raise _refuse(
                    "ambiguous_environment_reference",
                    f"Shot {shot_id} setting does not resolve to exactly one approved canonical anchor.",
                )
            confirmations = ShotConfirmationStore()
            confirmations.save(project_id, shot_id, stored_digest)
            environments = EnvironmentRowStore()
            for row in env_rows:
                state = str(row.get("approval_state") or "").strip()
                environments.put(str(row.get("ref_id")), state if state in ("approved", "candidate", "rejected") else "candidate")
            mint = SceneMintService(confirmations, environments)
            try:
                scene_pass = mint.generate_scene(project_id, shot_id, require_persisted_confirmation=True)
            except _ValidationError as exc:
                raise _refuse(
                    str((exc.metadata or {}).get("refusal_code") or "SCENE_NOT_MINTED"),
                    str(exc.message),
                ) from exc
            rejected_ids = list(scene_pass.rejected_environment_ref_ids)
            if any(not str(ref_id).strip() for ref_id in rejected_ids):
                raise _refuse("unlisted_environment_authority", f"Shot {shot_id} rejected environment enumeration is malformed.")
            # M8 — Router representability (defense in depth; preflight mirrors).
            for row in binding:
                try:
                    projection.normalize_studio_role(row.get("role"))
                except ValueError:
                    raise _refuse(
                        "unsupported_reference_role",
                        f"Shot {shot_id} carries a frozen reference role the Router cannot represent.",
                    ) from None
            if not 1 <= len(binding) <= projection.CAPACITY:
                raise _refuse(
                    "unsupported_reference_capacity",
                    f"Shot {shot_id} exceeds the currently supported reference capacity ({projection.CAPACITY} references).",
                )
            fingerprints = projection.compute_source_fingerprints(binding, backend_root=self.backend_root)
            source_fingerprint = str(fingerprints.get(selected_id) or "")
            if len(source_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in source_fingerprint.lower()):
                raise _refuse("missing_setting_authority", f"Shot {shot_id} setting source fingerprint is missing or malformed.")
            binding_digest = reference_binding_digest(binding)
            rejected_states = sorted({
                str(next((row.get("approval_state") for row in env_rows if str(row.get("ref_id")) == ref_id), "") or "")
                for ref_id in rejected_ids
            })
            authorization = {
                "authorization_policy_id": projection.AUTHORIZATION_POLICY_ID,
                "project_id": project_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
                "confirmation_id": str((stored_row or {}).get("confirmation_id") or "") or None,
                "confirmed_digest": stored_digest,
                "setting_id": setting_id,
                "current_version_id": current_id,
                "approved_version_id": approved_id,
                "storyboard_version_id": triple,
                "authorized_environment_ref_id": selected_id,
                "rejected_environment_ref_ids": rejected_ids,
                "environment_basis": {
                    "mode": "single_canonical_environment",
                    "setting_id": setting_id,
                    "authorized_environment_ref_id": selected_id,
                    "enumerated_rejected_ref_ids": list(rejected_ids),
                    "rejected_approval_states": rejected_states,
                    "approved_anchor_count": 1,
                    "enumerated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "reference_asset_rows",
                },
                "frozen_reference_binding": deepcopy(binding),
                "frozen_reference_binding_sha256": binding_digest,
                "source_fingerprint": source_fingerprint,
            }
            audit = {
                "minted_at": datetime.now(timezone.utc).isoformat(),
                "confirmation_id": authorization["confirmation_id"],
                "confirmed_digest": stored_digest,
                "binding_digest": binding_digest,
                "storyboard_version_id": triple,
                "setting_id": setting_id,
                "authorized_environment_ref_id": selected_id,
                "environment_basis_mode": "single_canonical_environment",
                "policy_version": "v2",
            }
        except _ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 — fail closed, never a 500
            raise _refuse("missing_reference_authority", f"Shot {shot_id} generic authorization cannot be minted: {type(exc).__name__}") from exc
        log_stage_event(
            project_id=project_id,
            job_id=shot_id,
            provider="runway_router",
            stage=stage,
            duration_ms=elapsed_ms(started),
            extra={"result": "minted", "setting_id": setting_id},
        )
        return {"authorization": authorization, "audit": audit}

    def _build_contract_only_batch(
        self,
        *,
        project_id: str,
        authority_id: str,
        authority: dict[str, Any],
        project_guard_sha256: str,
        provider: str,
    ) -> dict[str, Any]:
        """Project durable authority into a one-use execution snapshot only."""
        from app.services.generation_contract import FrozenGenerationContract
        from app.services.scene002_contract_only import MODE

        manifest = deepcopy(authority["creative_manifest"])
        coverage = deepcopy(authority["coverage_contract"])
        shot_rows = manifest.get("shots") if isinstance(manifest.get("shots"), list) else []
        shots: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        for order, shot_id in enumerate(authority["ordered_shot_ids"], start=1):
            row = next((item for item in shot_rows if isinstance(item, dict) and item.get("shot_id") == shot_id), None)
            record = authority["generation_contracts_by_shot"].get(shot_id)
            if not isinstance(row, dict) or not isinstance(record, dict):
                raise ValidationError("Frozen authority is missing an ordered shot contract", stage="scene_pipeline_contract")
            frozen = FrozenGenerationContract.from_record(record)
            frozen_payload = frozen.payload()
            binding = deepcopy(authority["reference_bindings"])
            parameters = deepcopy(frozen_payload.get("creative_parameters") or {})
            parameters.update({
                "project_id": project_id,
                "scene_id": authority["scene_id"],
                "duration": frozen.duration,
                "aspect_ratio": frozen.aspect_ratio,
                "resolution": frozen.resolution,
                "seed": frozen.seed,
                "audio_intent": frozen.audio,
                "negative_prompt": frozen.negative_prompt,
                "camera_plan": deepcopy(frozen_payload.get("camera_plan") or {}),
                "camera_provenance": frozen.camera_provenance,
                "camera_source_digest": frozen.camera_source_digest,
                "camera_instructions": deepcopy(frozen_payload.get("camera_instructions") or []),
                "camera_source_project_id": frozen.camera_source_project_id,
                "camera_source_scene_id": frozen.camera_source_scene_id,
                "camera_source_shot_id": frozen.camera_source_shot_id,
                "camera_source_storyboard_shot_id": frozen.camera_source_storyboard_shot_id,
                "camera_target_project_id": frozen.camera_target_project_id,
                "camera_target_scene_id": frozen.camera_target_scene_id,
                "camera_target_shot_id": frozen.camera_target_shot_id,
                "reference_roles": [str(item.get("role") or "reference") for item in binding],
                "frozen_reference_binding": deepcopy(binding),
                "dialogue_lines": deepcopy((frozen_payload.get("dialogue_handoff") or {}).get("payload", {}).get("lines", [])),
                "dialogue_handoff": deepcopy(frozen_payload.get("dialogue_handoff") or {}),
                "scene_coverage": deepcopy(coverage),
                "scene_coverage_shot": deepcopy(frozen_payload.get("scene_coverage_shot") or {}),
                "preserve_shot_prompt": True,
            })
            shot = {"shot_id": shot_id, "scene_id": authority["scene_id"], "parameters": {"storyboard": {
                "storyboard_shot_id": row.get("storyboard_shot_id"),
                "version_id": authority["storyboard_version_id"],
            }}}
            shots.append(shot)
            entries.append({
                "project_id": project_id,
                "scene_id": authority["scene_id"],
                "shot_id": shot_id,
                "shot_order": order,
                "prompt": frozen.prompt,
                "negative_prompt": frozen.negative_prompt,
                "dialogue_handoff": deepcopy(frozen_payload.get("dialogue_handoff") or {}),
                "dialogue_lines": deepcopy(parameters["dialogue_lines"]),
                "scene_coverage": deepcopy(coverage),
                "shot_coverage": deepcopy(frozen_payload.get("scene_coverage_shot") or {}),
                "generation_contract": deepcopy(record),
                "generation_contract_digest": frozen.creative_digest(),
                "generation_settings": parameters,
                "reference_binding": binding,
                "references": [str(item["uri"]) for item in binding],
                "reference_roles": [str(item.get("role") or "reference") for item in binding],
                "duration_seconds": float(frozen.duration or 0),
                "aspect_ratio": frozen.aspect_ratio,
                "resolution": frozen.resolution,
                "seed": frozen.seed,
                "camera_plan": deepcopy(frozen_payload.get("camera_plan") or {}),
                "camera_provenance": frozen.camera_provenance,
                "camera_instructions": deepcopy(frozen_payload.get("camera_instructions") or []),
                "camera_source_digest": frozen.camera_source_digest,
                "camera_source_project_id": frozen.camera_source_project_id,
                "camera_source_scene_id": frozen.camera_source_scene_id,
                "camera_source_shot_id": frozen.camera_source_shot_id,
                "camera_source_storyboard_shot_id": frozen.camera_source_storyboard_shot_id,
                "camera_target_project_id": frozen.camera_target_project_id,
                "camera_target_scene_id": frozen.camera_target_scene_id,
                "camera_target_shot_id": frozen.camera_target_shot_id,
                "blockers": [],
            })
        return {
            "project_id": project_id,
            "scene_id": authority["scene_id"],
            "execution_mode": MODE,
            "source_authority_id": authority_id,
            "source_authority": deepcopy(authority),
            "project_revision_guard_sha256": project_guard_sha256,
            "provider": provider,
            "manifest": manifest,
            "scene_coverage": coverage,
            "shots": shots,
            "entries": entries,
            "ready": True,
            "blockers": [],
            "cost_estimate": None,
            "source_kind": "authorized_manifest",
            "source_key": authority_id,
        }

    async def _submit_contract_only_batch(self, *, batch: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
        """Submit only exact authority-pinned inputs; never run readiness or recovery."""
        from app.services.scene002_contract_only import (
            Scene002ContractError,
            build_execution_contract,
            local_reference_sha256,
            validate_authority_record,
        )
        from app.services.providers.runway_router_provider import get_router_config_id

        authority = validate_authority_record(batch.get("source_authority"))
        records = []
        for entry in batch.get("entries") or []:
            self._assert_prepared_scene_batch_current(batch, project=project, scene_id=batch["scene_id"])
            digests = {
                str(row.get("ref_id") or ""): local_reference_sha256(str(row.get("uri") or ""), backend_root=self.backend_root)
                for row in entry.get("reference_binding") or []
            }
            if digests != authority["reference_content_sha256"]:
                raise ValidationError("Authorized reference content changed before submission", stage="scene_pipeline_contract")
            records.append(build_execution_contract(
                authority=authority,
                project_id=batch["project_id"],
                scene_id=batch["scene_id"],
                project_guard_sha256=batch["project_revision_guard_sha256"],
                manifest=batch["manifest"],
                entry=entry,
                generation_contract=entry["generation_contract"],
                provider=batch["provider"],
                router_config_id=get_router_config_id(),
                reference_digests=digests,
            ))
        results = []
        for entry, execution_record in zip(batch["entries"], records):
            self._assert_prepared_scene_batch_current(batch, project=project, scene_id=batch["scene_id"])
            execution_contract = execution_record.get("payload", {})
            execution_parameters = deepcopy(execution_contract.get("provider_input_parameters") or {})
            entry_parameters = deepcopy(entry.get("generation_settings") or {})
            for key in ("model", "project_id", "scene_id", "reference_roles", "frozen_reference_binding", "dialogue_lines", "dialogue_handoff", "scene_coverage", "scene_coverage_shot", "preserve_shot_prompt", "camera_plan", "camera_provenance", "camera_source_digest", "camera_instructions", "camera_source_project_id", "camera_source_scene_id", "camera_source_shot_id", "camera_source_storyboard_shot_id", "camera_target_project_id", "camera_target_scene_id", "camera_target_shot_id"):
                if key in entry_parameters:
                    execution_parameters[key] = entry_parameters[key]
            job = self.render_service.create_job(
                project_id=batch["project_id"],
                shot_id=entry["shot_id"],
                provider=batch["provider"],
                prompt=entry["prompt"],
                reference_assets=deepcopy(entry["references"]),
                parameters=execution_parameters,
                frozen_reference_binding=deepcopy(entry["reference_binding"]),
                creative_manifest_fingerprint=batch["manifest"]["manifest_fingerprint"],
                creative_manifest=deepcopy(batch["manifest"]),
                dialogue_handoff=deepcopy(entry["dialogue_handoff"]),
                generation_contract=deepcopy(entry["generation_contract"]),
                prepared_generation_contract=deepcopy(entry["generation_contract"]),
                execution_mode="SCENE_002_CONTRACT_ONLY",
                scene002_execution_contract=execution_record,
                source_authority_id=batch["source_authority_id"],
            )
            completed = await self._submit_and_wait(job.id)
            if getattr(completed, "status", "") != "complete" or not self._job_output_url(completed):
                raise ProviderError("Protected render did not produce a verified output", stage="scene_pipeline_contract")
            results.append({
                "shot_id": entry["shot_id"],
                "render_job_id": str(getattr(completed, "id", "")),
                "output_url": self._job_output_url(completed),
                "status": "complete",
                "execution_fingerprint": execution_record["execution_fingerprint"],
            })
        return {
            "status": "complete",
            "project_id": batch["project_id"],
            "scene_id": batch["scene_id"],
            "execution_mode": "SCENE_002_CONTRACT_ONLY",
            "shots": results,
            "shot_manifest": deepcopy(batch["manifest"]),
            "assembly": None,
            "output_url": None,
            "prepared_snapshot_id": batch.get("prepared_snapshot_id", ""),
        }

    def _register_prepared_scene_batch(self, batch: dict[str, Any], *, provider: str | None) -> None:
        now = time.time()
        self._prepared_scene_batches = {
            key: value for key, value in self._prepared_scene_batches.items()
            if value.get("expires_at", 0) > now
        }
        if len(self._prepared_scene_batches) >= 256:
            self._prepared_scene_batches = dict(
                sorted(
                    self._prepared_scene_batches.items(),
                    key=lambda row: row[1].get("expires_at", 0),
                    reverse=True,
                )[:255]
            )
        token = secrets.token_urlsafe(32)
        record = deepcopy(batch)
        record["provider"] = provider
        record["expires_at"] = now + 300
        record["prepared_snapshot_id"] = token
        self._prepared_scene_batches[token] = record
        batch["prepared_snapshot_id"] = token

    def _consume_prepared_scene_batch(
        self,
        token: str,
        *,
        project_id: str,
        scene_id: str,
        provider: str | None,
        project: dict[str, Any],
        require_current_project: bool = True,
        execution_mode: str | None = None,
        source_authority_id: str | None = None,
    ) -> dict[str, Any]:
        batch = self._prepared_scene_batches.get(token)
        if batch is not None and batch.get("execution_mode") == "SCENE_002_CONTRACT_ONLY":
            # Protected snapshots are consumed once; they are never rebuilt or
            # replaced from project state if missing, expired, or mismatched.
            self._prepared_scene_batches.pop(token, None)
        else:
            batch = self._prepared_scene_batches.pop(token, None)
        if batch is None or batch.get("expires_at", 0) <= time.time():
            raise ValidationError(
                "The prepared scene batch is unavailable or expired; protected execution cannot reconstruct it.",
                stage="scene_pipeline_snapshot",
                metadata={"failure_type": "prepared_snapshot_expired", "scene_id": scene_id},
            )
        if batch.get("project_id") != project_id or batch.get("scene_id") != scene_id or batch.get("provider") != provider:
            raise ValidationError(
                "The prepared scene batch does not match this generation request.",
                stage="scene_pipeline_snapshot",
                metadata={"failure_type": "prepared_snapshot_identity_mismatch", "scene_id": scene_id},
            )
        if (
            batch.get("execution_mode") != execution_mode
            or batch.get("source_authority_id") != source_authority_id
            or (execution_mode == "SCENE_002_CONTRACT_ONLY" and not isinstance(batch.get("source_authority"), dict))
        ):
            raise ValidationError(
                "Prepared snapshot mode or prospective authority differs from this request.",
                stage="scene_pipeline_snapshot",
                metadata={"failure_type": "prepared_snapshot_authority_mismatch", "scene_id": scene_id},
            )
        if require_current_project:
            self._assert_prepared_scene_batch_current(batch, project=project, scene_id=scene_id)
        elif batch.get("execution_mode") == "SCENE_002_CONTRACT_ONLY":
            from app.services.scene002_contract_only import project_revision_guard, validate_authority_record
            authority = self._load_scene002_authority(project_id, source_authority_id or "")
            if authority != batch.get("source_authority"):
                raise ValidationError("Prepared source authority changed or cannot be recovered", stage="scene_pipeline_contract")
            validate_authority_record(authority)
            if project_revision_guard(project) != batch.get("project_revision_guard_sha256"):
                raise ValidationError("Protected project revision changed after source authorization", stage="scene_pipeline_contract")
        elif (
            batch.get("manifest", {}).get("scene", {}).get("canonical_script_sha256")
            != batch.get("scene_coverage", {}).get("canonical_script_sha256")
            or batch.get("manifest", {}).get("scene", {}).get("scene_content_sha256")
            != batch.get("scene_coverage", {}).get("scene_content_sha256")
        ):
            raise ValidationError("Prepared snapshot lineage is inconsistent", stage="scene_pipeline_contract")
        batch["prepared_snapshot_id"] = token
        return batch

    def _project_from_authorized_source(self, project: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
        """Build only the input projection from explicit authority, never from current screenplay text."""
        selected = deepcopy(project)
        # Do not treat the selected authority as a rewrite of mutable project screenplay state.
        # Lineage is projected separately from the authority bytes during preparation.
        selected["script_version_id"] = authority["screenplay_representation_id"]
        scene_id = str(authority["scene_id"])
        found = False
        summary = selected.get("execution_summary") if isinstance(selected.get("execution_summary"), dict) else {}
        for container in (summary.get("scenes"), selected.get("scenes")):
            if not isinstance(container, list):
                continue
            for row in container:
                if isinstance(row, dict) and str(row.get("scene_id") or "") == scene_id:
                    row["heading"] = authority["scene_heading"]
                    row["text"] = authority["scene_content"]
                    row["description"] = authority["scene_content"]
                    row["scene_text"] = authority["scene_content"]
                    found = True
        if not found:
            raise ValidationError("Authorized Scene 002 projection has no corresponding scene shell", stage="scene_pipeline_contract")
        return selected

    def _load_scene002_authority(self, project_id: str, authority_id: str) -> dict[str, Any]:
        storage = getattr(self.render_service, "_storage", None)
        if storage is None:
            from app.services.render import _storage as storage
        if storage is None or not callable(getattr(storage, "get_scene002_render_authority", None)):
            raise ValidationError("Durable Scene 002 authority storage is unavailable", stage="scene_pipeline_contract")
        authority = storage.get_scene002_render_authority(authority_id, project_id)
        if not isinstance(authority, dict):
            raise ValidationError("Scene 002 source authority could not be recovered", stage="scene_pipeline_contract")
        return authority

    def _assert_prepared_scene_batch_current(
        self,
        batch: dict[str, Any],
        *,
        project: dict[str, Any],
        scene_id: str,
    ) -> None:
        if batch.get("execution_mode") == "SCENE_002_CONTRACT_ONLY":
            from app.services.scene002_contract_only import project_revision_guard, validate_authority_record
            authority = self._load_scene002_authority(
                str(batch.get("project_id") or ""),
                str(batch.get("source_authority_id") or ""),
            )
            if authority != batch.get("source_authority"):
                raise ValidationError("Prepared source authority changed or cannot be recovered", stage="scene_pipeline_contract")
            validate_authority_record(authority)
            if project_revision_guard(project) != batch.get("project_revision_guard_sha256"):
                raise ValidationError("Protected project revision changed after source authorization", stage="scene_pipeline_contract")
            return
        project_id = str(batch.get("project_id") or "")
        current_scene = self._find_scene(project, scene_id)
        if current_scene is None or self._snapshot_fingerprint(current_scene) != batch.get("scene_snapshot_fingerprint"):
            raise ValidationError(
                "The scene changed after preflight; run preflight again before generation.",
                stage="scene_pipeline_snapshot",
                metadata={"failure_type": "stale_scene_snapshot", "scene_id": scene_id},
            )
        current_script_hash = hashlib.sha256(str(project.get("script_text") or "").encode("utf-8")).hexdigest()
        if current_script_hash != batch.get("canonical_script_sha256"):
            raise ValidationError(
                "The canonical screenplay changed after preflight; rebuild the generation contract.",
                stage="scene_pipeline_lineage",
                metadata={"failure_type": "stale_canonical_script", "scene_id": scene_id},
            )
        source_kind = batch.get("source_kind")
        if source_kind == "scene_shots":
            current_source = self._sort_shots(current_scene.get("shots") or [])
        elif source_kind in {"shot_candidates", "scene_render_jobs", "video_render_assets"}:
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            candidates = summary.get(source_kind) or []
            current_source = [
                item for item in candidates
                if isinstance(item, dict)
                and (
                    str(item.get("scene_id") or "").strip() == scene_id
                    or derive_scene_id_from_shot_id(str(item.get("shot_id") or "").strip()) == scene_id
                )
            ]
            current_source = self._sort_shots(current_source)
        elif source_kind == "storyboard":
            from app.services.storyboard_blueprint_service import storyboard_blueprint_service

            current_source = [
                self._snapshot_value(row)
                for row in storyboard_blueprint_service.scene_render_inputs(project_id, scene_id) or []
            ]
        elif source_kind == "single_shot_fallback":
            current_source = batch.get("shots")
        else:
            current_source = None
        if current_source is None or self._snapshot_fingerprint(current_source) != batch.get("shot_source_fingerprint"):
            raise ValidationError(
                "The shot set changed after preflight; run preflight again before generation.",
                stage="scene_pipeline_snapshot",
                metadata={"failure_type": "stale_shot_snapshot", "scene_id": scene_id},
            )
        if source_kind == "storyboard":
            self._assert_storyboard_send_prompts_current(batch, project_id=project_id, scene_id=scene_id)

    def _assert_storyboard_send_prompts_current(
        self,
        batch: dict[str, Any],
        *,
        project_id: str,
        scene_id: str,
    ) -> None:
        """Reject a prepared snapshot whose approved image prompts changed.

        Board bytes are covered by the shot-source fingerprint above; image
        prompts live in a separate table, so an edit/approval after preflight
        would otherwise submit the preflight-time text. Entries that were
        already blocked at preflight are skipped — their blockers (not this
        snapshot) refuse generation until a fresh preflight.
        """
        from app.services.storyboard_blueprint_service import (
            storyboard_blueprint_service,
        )

        blueprint = storyboard_blueprint_service.storage.get_storyboard_blueprint(project_id, scene_id)
        approved_version = str(getattr(blueprint, "approved_version_id", "") or "") if blueprint else ""
        current_version = str(getattr(blueprint, "current_version_id", "") or "") if blueprint else ""
        for entry in batch.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            storyboard_shot_id = str(entry.get("storyboard_shot_id") or "")
            if not storyboard_shot_id:
                continue
            if not entry.get("image_prompt_ready") or not str(entry.get("prompt") or ""):
                continue
            shot_id = str(entry.get("shot_id") or "")
            current_shot = None
            try:
                candidate = storyboard_blueprint_service.storage.get_storyboard_shot(storyboard_shot_id)
                if (
                    candidate is not None
                    and str(getattr(candidate, "version_id", "") or "") == approved_version
                    and str(getattr(candidate, "version_id", "") or "") == current_version
                    and str(getattr(candidate, "shot_id", "") or "") == shot_id
                    and str(getattr(candidate, "project_id", "") or "") == project_id
                    and str(getattr(candidate, "scene_id", "") or "") == scene_id
                ):
                    current_shot = candidate
            except Exception:
                current_shot = None
            text, _, error = self._resolve_storyboard_send_prompt(
                shot_id=shot_id,
                storyboard_shot_id=storyboard_shot_id,
                current_shot=current_shot,
            )
            if error or text != str(entry.get("prompt") or ""):
                raise ValidationError(
                    f"Shot {shot_id}: the approved image prompt changed after "
                    "preflight; run preflight again before generation.",
                    stage="scene_pipeline_snapshot",
                    metadata={"failure_type": "stale_image_prompt_snapshot", "scene_id": scene_id},
                )

    def _snapshot_fingerprint(self, value: Any) -> str:
        if isinstance(value, list):
            normalized = [self._snapshot_value(item) for item in value]
        else:
            normalized = self._snapshot_value(value)
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _snapshot_value(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        elif hasattr(value, "__dict__") and not isinstance(value, dict):
            value = vars(value)
        if isinstance(value, dict):
            return {str(key): self._snapshot_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._snapshot_value(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _scene_ownership_matches(self, *, selected_scene_id: str, shot: dict[str, Any]) -> bool:
        explicit_scene_id = str(shot.get("scene_id") or "").strip()
        shot_id = str(shot.get("shot_id") or "").strip()
        derived_scene_id = derive_scene_id_from_shot_id(shot_id) if shot_id else ""
        # Downstream reference validation derives scene identity from shot_id,
        # so both encoded and explicit ownership must match this selection.
        return derived_scene_id == selected_scene_id and (
            not explicit_scene_id or explicit_scene_id == selected_scene_id
        )

    def _require_shot_ownership(self, *, selected_scene_id: str, shots: list[dict[str, Any]]) -> None:
        foreign = [
            {"shot_id": str(shot.get("shot_id") or ""), "scene_id": str(shot.get("scene_id") or "")}
            for shot in shots
            if not self._scene_ownership_matches(selected_scene_id=selected_scene_id, shot=shot)
        ]
        if foreign:
            raise ValidationError(
                f"Scene {selected_scene_id} contains shots owned by another scene.",
                stage="scene_pipeline_shot_ownership",
                metadata={"failure_type": "foreign_scene_shot", "scene_id": selected_scene_id, "foreign_shots": foreign},
            )

    def _resolve_shot_source(
        self,
        project: dict[str, Any],
        scene: dict[str, Any],
        *,
        project_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str, str]:
        scene_id = str(scene.get("scene_id") or "").strip()
        project_id = str(project_id or project.get("project_id") or "").strip()
        if project_id and scene_id:
            from app.services.storyboard_blueprint_service import storyboard_blueprint_service

            blueprint_shots = storyboard_blueprint_service.scene_render_inputs(project_id, scene_id)
            if blueprint_shots is not None:
                shots = [self._snapshot_value(row) for row in blueprint_shots]
                self._require_shot_ownership(selected_scene_id=scene_id, shots=shots)
                return shots, "storyboard", "storyboard"
        scene_shots = scene.get("shots")
        shots = [self._snapshot_value(shot) for shot in scene_shots if isinstance(shot, dict)] if isinstance(scene_shots, list) else []
        if shots:
            self._require_shot_ownership(selected_scene_id=scene_id, shots=shots)
            return self._sort_shots(shots), "scene_shots", "shots"

        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        for candidate_key in ("shot_candidates", "scene_render_jobs", "video_render_assets"):
            candidates = summary.get(candidate_key) or []
            matched = [
                self._snapshot_value(item)
                for item in candidates
                if isinstance(item, dict)
                and (
                    str(item.get("scene_id") or "").strip() == scene_id
                    or derive_scene_id_from_shot_id(str(item.get("shot_id") or "").strip()) == scene_id
                )
            ]
            self._require_shot_ownership(selected_scene_id=scene_id, shots=matched)
            if matched:
                return self._sort_shots(matched), candidate_key, candidate_key

        ledger = scene.get("multi_shot_execution_ledger")
        if isinstance(ledger, list) and any(isinstance(entry, dict) for entry in ledger):
            logger.warning(
                "LEGACY_MULTI_SHOT_LEDGER_EXCLUDED | project_id=%s | scene_id=%s | entries=%d",
                project_id,
                scene_id,
                len([entry for entry in ledger if isinstance(entry, dict)]),
            )
        if project.get("execution_mode") == "SCENE_002_CONTRACT_ONLY":
            raise ValidationError("Protected preparation forbids single-shot scene-text fallback", stage="scene_pipeline_contract")
        shots = [{"shot_id": f"{scene_id}_shot_001", "description": self._scene_text(scene)}]
        self._require_shot_ownership(selected_scene_id=scene_id, shots=shots)
        return shots, "single_shot_fallback", "scene_text"

    def _sort_shots(self, shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            shots,
            key=lambda item: (
                derive_shot_number_from_shot_id(str(item.get("shot_id") or "")) or 999999,
                str(item.get("shot_id") or ""),
            ),
        )

    def _link_storyboard_render_if_present(self, shot: dict[str, Any], render_job_id: str) -> None:
        parameters = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
        storyboard_meta = parameters.get("storyboard") if isinstance(parameters, dict) else None
        if not isinstance(storyboard_meta, dict) or not render_job_id:
            return
        try:
            from app.services.storyboard_blueprint_service import storyboard_blueprint_service

            storyboard_shot_id = str(storyboard_meta.get("storyboard_shot_id") or "").strip()
            storyboard_shot = storyboard_blueprint_service.storage.get_storyboard_shot(storyboard_shot_id)
            if storyboard_shot is not None:
                storyboard_blueprint_service.link_render_job(
                    shot=storyboard_shot,
                    render_job_id=render_job_id,
                    link_type=str(storyboard_meta.get("link_type") or "scene_pipeline_render"),
                )
        except Exception as exc:
            logger.debug("Storyboard scene-pipeline render link skipped for %s: %s", render_job_id, exc)

    def _resolve_generation_provider(self, provider: str | None) -> str | None:
        """Resolve scene-pipeline Runway selection to its immutable Router path."""
        selected = provider
        if selected is None:
            get_default = getattr(self.render_service, "get_default_provider", None)
            if callable(get_default):
                selected = get_default()
        normalized = str(selected or "").strip().lower()
        if normalized == "runway":
            return "runway_router"
        if normalized == "simulated":
            return "simulated"
        if normalized in {"runway_router", ""}:
            return normalized or None
        return normalized

    def _find_scene(self, project: dict[str, Any], scene_id: str) -> dict[str, Any] | None:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        for container in (summary.get("scenes"), project.get("scenes")):
            if not isinstance(container, list):
                continue
            for scene in container:
                if isinstance(scene, dict) and str(scene.get("scene_id") or "") == scene_id:
                    return scene
        return None

    def _resolve_ordered_shots(self, project: dict[str, Any], scene: dict[str, Any]) -> list[dict[str, Any]]:
        shots, _, _ = self._resolve_shot_source(project, scene)
        return shots

    def _resolve_storyboard_send_prompt(
        self,
        *,
        shot_id: str,
        storyboard_shot_id: str,
        current_shot: Any,
    ) -> tuple[str, str, str]:
        """Resolve the provider-bound text for one storyboard-backed shot.

        Returns ``(text, sha256, error)``. On success ``error`` is empty and
        ``text`` is the approved, hash-linked image prompt with ``sha256``
        its hex digest. On ANY failure ``text`` is empty and ``error``
        carries the fail-closed message (missing / stale / unapproved /
        empty / over-limit / unresolvable board shot) — callers must block
        the shot and must never fall back to the board prompt. Never raises.
        The D6 central gate (``resolve_provider_send_text``) performs the
        state checks; this wrapper only translates the typed error into the
        per-shot ``(text, sha, error)`` contract.
        """
        import hashlib as _hashlib

        if current_shot is None:
            return (
                "",
                "",
                f"Shot {shot_id}: storyboard shot {storyboard_shot_id} cannot be "
                "resolved from the approved board version; re-approve the "
                "board before generation.",
            )
        try:
            from app.services.storyboard_blueprint_service import (
                storyboard_blueprint_service as _blueprint_service,
            )
            from app.services.storyboard_image_prompt_service import (
                storyboard_image_prompt_service as _image_prompt_service,
            )
            from app.services.stability import StateError as _StateError
            from app.services.stability import ValidationError as _ValidationError

            _image_prompt_service.set_storage(_blueprint_service.storage)
            text = _image_prompt_service.resolve_provider_send_text(current_shot)
        except (_StateError, _ValidationError) as exc:
            message = str(getattr(exc, "message", None) or str(exc) or "").strip()
            return "", "", message or f"Shot {shot_id}: approved image prompt is not render-ready."
        except Exception as exc:
            logger.warning(
                "IMAGE_PROMPT_RESOLVE_FAILED | shot=%s | storyboard_shot=%s | cause=%s",
                shot_id,
                storyboard_shot_id,
                type(exc).__name__,
            )
            return (
                "",
                "",
                f"Shot {shot_id}: approved image prompt cannot be verified "
                f"({type(exc).__name__}); derive and approve it before generation.",
            )
        return text, _hashlib.sha256(text.encode("utf-8")).hexdigest(), ""

    def _shot_version_with_image_prompt(self, board_shot_version: str, image_prompt_sha256: str) -> str:
        """Bind the sendable image prompt into the shot version hash.

        The board-only version is blind to image-prompt edits; combining it
        with the approved text digest means any image-prompt change yields a
        different shot version (and, via the sent prompt, a different
        manifest fingerprint and contract digest).
        """
        from app.services.generation_context_service import _stable_hash

        return _stable_hash(
            {
                "board_shot_version": board_shot_version,
                "image_prompt_sha256": image_prompt_sha256,
            }
        )

    def _shot_prompt(self, scene: dict[str, Any], shot: dict[str, Any], index: int, total: int) -> str:
        base = str(
            shot.get("prompt")
            or shot.get("description")
            or shot.get("visual_description")
            or self._scene_text(scene)
        ).strip()
        position = f"Shot {index} of {total} in scene. Maintain character identity and visual continuity."
        return f"{base}\n\n[SHOT POSITION]\n{position}".strip()

    def _scene_text(self, scene: dict[str, Any]) -> str:
        return str(
            scene.get("scene_text")
            or scene.get("script_text")
            or scene.get("text")
            or scene.get("description")
            or scene.get("summary")
            or ""
        ).strip()

    def _scene_characters(self, scene: dict[str, Any]) -> list[str]:
        raw = scene.get("characters") or []
        if not isinstance(raw, list):
            return []
        names: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict) and str(item.get("name") or "").strip():
                names.append(str(item["name"]).strip())
        return names

    def _dialogue_lines_for_shot(
        self,
        project: dict[str, Any],
        scene_id: str,
        shot_id: str,
        *,
        allow_scene_fallback: bool = False,
        supplied_lines: Any = None,
    ) -> list[dict[str, str]] | None:
        """Canonical dialogue for this shot (dialogue-authority service).

        Reads the stored projection with fabricated placeholder rows excluded,
        then falls back to deterministic screenplay extraction from the scene
        text. Fabricated DialogueVoiceService lines can no longer become the
        audio/performance dialogue source (Multi Shot integrity audit, Phase 3).
        """
        from app.services.dialogue_authority import canonical_dialogue_lines, filter_placeholder_lines

        if supplied_lines is not None:
            # Shot contract assignments take precedence, but scoped rows from a
            # different owner are stale rather than silently reassigned.
            scoped = []
            for row in supplied_lines if isinstance(supplied_lines, list) else []:
                if not isinstance(row, dict):
                    raise GenerationContractError("Structured dialogue row must be an object")
                if row.get("scene_id") not in (None, "", scene_id) or row.get("shot_id") not in (None, "", shot_id):
                    raise GenerationContractError("Structured dialogue row belongs to a different scene or shot")
                scoped.append(row)
            return canonical_dialogue_lines(None, scoped, scene_id=scene_id)

        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        raw_lines = summary.get("dialogue_lines")
        if not isinstance(raw_lines, list):
            raw_lines = []
        lines: list[dict[str, str]] = []
        for line in filter_placeholder_lines(raw_lines):
            if not isinstance(line, dict) or str(line.get("scene_id") or "") != scene_id:
                continue
            line_shot_id = str(line.get("shot_id") or "").strip()
            if line_shot_id != shot_id and not (allow_scene_fallback and not line_shot_id):
                continue
            lines.append({str(key): str(value) for key, value in line.items() if value is not None})
        if lines or not allow_scene_fallback:
            return lines
        # Scene fallback: derive deterministically from the scene text itself.
        scene = self._find_scene(project, scene_id) if callable(getattr(self, "_find_scene", None)) else None
        if scene is None:
            return None
        from app.services.dialogue_authority import canonical_dialogue_lines

        return canonical_dialogue_lines(
            scene,
            scene_id=scene_id,
            characters=self._scene_characters(scene),
        )

    async def _submit_and_wait(self, job_id: str, max_attempts: int = 90) -> Any:
        job = await self.render_service.submit_job(job_id)
        attempts = 0
        while getattr(job, "status", "") != "needs_review" and not getattr(job, "is_terminal", lambda: True)() and attempts < max_attempts:
            await asyncio.sleep(1)
            job = await self.render_service.get_job_status(job_id)
            attempts += 1
        if getattr(job, "status", "") == "needs_review":
            raise StateError(getattr(job, "error_message", None) or "Review required shot facts before rendering", stage="scene_pipeline_render")
        if getattr(job, "status", "") != "complete":
            raise ProviderError(
                f"Render job {job_id} did not complete",
                stage="scene_pipeline_render",
                metadata={"provider": getattr(job, "provider", None), "job_id": job_id},
            )
        return job

    def _job_output_url(self, job: Any) -> str:
        output = getattr(job, "output_payload", None)
        url = getattr(output, "asset_url", None) if output is not None else None
        if not isinstance(url, str) or not url.strip():
            raise ProviderError(
                f"Render job {getattr(job, 'id', '')} completed without output_url",
                stage="scene_pipeline_render",
                metadata={"provider": getattr(job, "provider", None), "job_id": getattr(job, "id", "")},
            )
        return url.strip()

    def _local_output_path(self, url_or_path: str) -> Path | None:
        value = str(url_or_path or "").strip()
        if not value:
            return None
        path = Path(value)
        if path.is_absolute() and path.exists():
            return path
        if value.startswith("/outputs/"):
            candidate = self.backend_root / value.lstrip("/")
            return candidate if candidate.exists() else None
        if value.startswith("outputs/"):
            candidate = self.backend_root / value
            return candidate if candidate.exists() else None
        return None

    def _ensure_execution_summary(self, project: dict[str, Any]) -> dict[str, Any]:
        summary = project.get("execution_summary")
        if not isinstance(summary, dict):
            summary = {}
            project["execution_summary"] = summary
        scenes = summary.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            project_scenes = project.get("scenes")
            if isinstance(project_scenes, list):
                summary["scenes"] = project_scenes
        return summary

    def _upsert_render_row(self, rows: list[Any], row: dict[str, Any]) -> None:
        for index, existing in enumerate(rows):
            if (
                isinstance(existing, dict)
                and str(existing.get("scene_id") or "") == row["scene_id"]
                and str(existing.get("shot_id") or "") == row["shot_id"]
            ):
                rows[index] = row
                return
        rows.append(row)

    def _scene_status_from_stitch(self, stitch_result: dict[str, Any]) -> str:
        return "complete" if stitch_result.get("status") in {"complete", "completed", "existing"} else "failed"

    def _scene_assembly_row(
        self,
        *,
        project_id: str,
        scene_id: str,
        status: str,
        stitch_result: dict[str, Any],
        rendered_shots: list[dict[str, Any]],
        score_ambient_provider: str,
        soundtrack_status: str,
    ) -> dict[str, Any]:
        return {
            "assembly_id": f"{project_id}_{scene_id}",
            "project_id": project_id,
            "scene_id": scene_id,
            "status": status,
            "output_url": stitch_result.get("output_url"),
            "output_path": stitch_result.get("output_path"),
            "duration_seconds": stitch_result.get("duration_seconds"),
            "clip_count": stitch_result.get("clip_count", len(rendered_shots)),
            "shot_ids": stitch_result.get("shot_ids") or [str(row.get("shot_id") or "") for row in rendered_shots],
            "score_ambient_provider": score_ambient_provider,
            "soundtrack_status": soundtrack_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _upsert_scene_assembly(self, summary: dict[str, Any], row: dict[str, Any]) -> None:
        assemblies = summary.setdefault("scene_pipeline_assemblies", [])
        if not isinstance(assemblies, list):
            assemblies = []
            summary["scene_pipeline_assemblies"] = assemblies
        for index, existing in enumerate(assemblies):
            if isinstance(existing, dict) and str(existing.get("scene_id") or "") == row["scene_id"]:
                assemblies[index] = row
                return
        assemblies.append(row)

    def _soundtrack_status(self, config: SoundtrackConfig | None) -> str:
        if not config or not config.enabled:
            return "deferred"
        if config.audio_url or config.local_audio_path:
            return "manual_post_render"
        return str(config.audio_source_type or "configured")

    def _consistency_summary(self, job: Any) -> dict[str, Any]:
        input_payload = getattr(job, "input_payload", None)
        payload = getattr(input_payload, "consistency_payload", None)
        explicit_refs = getattr(input_payload, "referenceAssets", None)
        if payload is None:
            return {
                "mode": "none",
                "attached": False,
                "reference_count": len(explicit_refs) if isinstance(explicit_refs, list) else 0,
                "reference_kinds": [],
                "primary_reference_url": None,
            }
        refs = getattr(payload, "refs", None)
        ref_items = refs if isinstance(refs, list) else []
        weights = getattr(payload, "weights", {}) if isinstance(getattr(payload, "weights", {}), dict) else {}
        primary = None
        char_full = [ref for ref in ref_items if getattr(ref, "kind", "") == "character_full"]
        if char_full:
            primary = max(char_full, key=lambda ref: weights.get(getattr(ref, "ref_id", ""), 0.0))
        return {
            "mode": getattr(payload, "mode", "identity_lock"),
            "attached": True,
            "reference_count": len(ref_items),
            "reference_kinds": [getattr(ref, "kind", "") for ref in ref_items],
            "primary_reference_url": getattr(primary, "image_url", None) if primary is not None else None,
        }

    def _normalize_scene_score_provider(self, provider: str | None) -> str:
        normalized = (provider or "none").strip().lower()
        aliases = {
            "": "none",
            "off": "none",
            "skip": "none",
            "disabled": "none",
            "no_provider": "none",
            "no-provider": "none",
            "manual": "manual_post_render",
            "manual-post-render": "manual_post_render",
            "manual_post": "manual_post_render",
            "post_render": "manual_post_render",
            "post-render": "manual_post_render",
            "ace": "ace_step",
            "ace-step": "ace_step",
            "acestep": "ace_step",
            "music_gen": "musicgen",
            "music-gen": "musicgen",
            "musicgen-small": "musicgen",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in SCENE_SCORE_AMBIENT_PROVIDERS:
            raise ValidationError(
                "Scene score/ambient provider must be one of "
                f"{sorted(SCENE_SCORE_AMBIENT_PROVIDERS)}",
                stage="scene_soundtrack",
                metadata={"provider": provider},
            )
        return normalized

    def _resolve_soundtrack_config(
        self,
        *,
        provider: str,
        config: SoundtrackConfig | None,
    ) -> SoundtrackConfig | None:
        if provider != "manual_post_render":
            return config
        if not config or not config.enabled or not (config.audio_url or config.local_audio_path):
            raise ValidationError(
                "manual_post_render score/ambient requires a scene-level soundtrack source",
                stage="scene_soundtrack",
                metadata={"provider": provider},
            )
        config.audio_source_type = config.audio_source_type or "local_file"
        return config


scene_production_pipeline_service = SceneProductionPipelineService()
