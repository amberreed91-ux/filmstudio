"""Routes for promoting rendered frames to ReferenceAssets.

Two-phase flow (propose → confirm) — no auto-promotion path exists:
  1. POST /{project_id}/shots/{shot_id}/propose-reference
       Read-only: checks adherence scores, returns a proposal (never saved).
  2. POST /{project_id}/reference-assets
       Write: explicitly persists a previously-proposed ReferenceAsset to the DB.
  3. GET  /{project_id}/reference-assets
       Read: lists confirmed ReferenceAssets from the DB (survives restarts).
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from app.models.consistency import ReferenceAsset
from app.services.stability import ValidationError
from app.services.reference_asset_service import (
    MAX_UPLOAD_BYTES,
    SCENE002_PROJECT_ID,
    SCENE002_SETTING_ID,
    reference_asset_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects", tags=["reference-assets"])


class ProposeReferenceBody(BaseModel):
    """Body for the propose-reference endpoint.

    Attributes:
        video_url: The output URL of the completed render to promote.
    """
    video_url: str


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1 — Propose (read-only)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}/shots/{shot_id}/propose-reference")
def propose_reference_asset(
    project_id: str,
    shot_id: str,
    body: ProposeReferenceBody,
):
    """Propose a ReferenceAsset from a qualifying render attempt.

    A shot qualifies when its *best* render attempt has:
      - dimensions.character_state.score >= 90
      - verdict == "pass"

    Returns the proposal as a ReferenceAsset without persisting it.
    The caller must POST to /{project_id}/reference-assets with the
    proposal body to confirm and persist.
    """
    try:
        return reference_asset_service.propose(project_id, shot_id, body.video_url)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/shots/{shot_id}/reference-binding")
def resolve_shot_reference_binding(project_id: str, shot_id: str):
    """Resolve one shot's authorized reference binding (read-only preview).

    Returns the server-resolved frozen binding with its digest for review and
    explicit confirmation in Production Desk. Creates no job, approves
    nothing, and invokes no provider. The binding becomes durable only when
    attached to a created render job, where the existing frozen-binding
    verifiers re-validate it before any provider submission.
    """
    try:
        return reference_asset_service.resolve_shot_binding(project_id, shot_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ConfirmShotReferenceBindingBody(BaseModel):
    """Explicit per-shot confirmation claim.

    Only the digest travels: the server re-resolves the current binding for
    the exact project and shot and persists a record only on a match.
    Nothing client-supplied is trusted as authorization.
    """
    model_config = ConfigDict(extra="forbid")
    expected_digest: str = Field(min_length=1, max_length=256)


@router.post("/{project_id}/shots/{shot_id}/reference-binding-confirmation")
def record_shot_reference_binding_confirmation(
    project_id: str,
    shot_id: str,
    body: ConfirmShotReferenceBindingBody,
):
    """Durably record one explicit shot confirmation (the ONLY write path).

    Re-verifies the carried digest against the freshly resolved binding and
    persists the server-resolved record on a match. Stale, unauthorized,
    cross-project, or wrong-shot claims fail closed and persist nothing.
    """
    try:
        return reference_asset_service.record_shot_confirmation(
            project_id, shot_id, body.expected_digest,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/shots/{shot_id}/reference-binding-confirmation")
def get_shot_reference_binding_confirmation(project_id: str, shot_id: str):
    """Recover one shot's confirmation status against current production state.

    Read-only: revalidates the durable record against the freshly resolved
    binding without creating, mutating, approving, or submitting anything.
    ``missing`` / ``stale`` / ``unverifiable`` are honest 200 verdicts — only
    ``confirmed`` may be shown as confirmed, and only the submission gate
    may treat it as authorization evidence.
    """
    try:
        return reference_asset_service.get_shot_confirmation(project_id, shot_id)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/reference-binding-confirmations")
def list_reference_binding_confirmations(project_id: str, scene_id: str = ""):
    """Recover every durable confirmation for one project scene with live status.

    Read-only recovery for reloads and navigation: rows are revalidated
    against current bindings; nothing is created or mutated here.
    """
    try:
        return reference_asset_service.list_scene_confirmations(project_id, scene_id)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/shots/{shot_id}/integrity-gates")
def get_shot_integrity_gates(project_id: str, shot_id: str):
    """Per-shot integrity gates for the visual gate pipeline (read-only).

    Pure reads only (SELECTs + in-memory derivation over loaded rows): no
    job creation, no provider calls, no dry runs, no preparation, no seed
    saves, no confirmation writes, no lazy table creation. Unknown projects
    and shots fail with 404. Gate states are ``pass`` / ``blocked`` /
    ``cant_check`` / ``not_yet``; ``spend.estimated_credits`` echoes only a
    value already persisted on the latest job (never a computed price, and
    never a number for local-ref shots); ``preflight`` never authorizes a
    future send.
    """
    from app.services.shot_integrity_gates_service import shot_integrity_gates_service
    from app.services.stability import StabilityError

    try:
        return shot_integrity_gates_service.get_gates(project_id, shot_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StabilityError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _sync_creator_references_best_effort(project_id: str) -> None:
    """Mirror approved looks/environments into the registry before listing.

    The visual-training panels read this registry, but approval status lives in
    character continuity documents and previs rows — so the registry is synced
    lazily here. Best-effort by design: a sync failure must never turn the
    read-only listing into a 500.
    """
    try:
        reference_asset_service.sync_creator_references(project_id)
    except Exception:
        logger.exception("REFERENCE_ASSET_LIST_SYNC_FAILED | project=%s", project_id)



class Scene002SettingReferenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_url: str = Field(min_length=1, max_length=4096)
    category: str = Field(default="environment", max_length=64)


class Scene002SettingReferenceCanonical(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical: Literal[True]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 — Confirm (explicit write, the ONLY persistence path)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}/reference-assets")
def confirm_reference_asset(project_id: str, payload: ReferenceAsset):
    """Persist a ReferenceAsset that was previously proposed.

    This is the ONLY code path that creates a live ReferenceAsset.
    There is no auto-promotion, no background job, no hook from the
    propose endpoint, and no middleware that calls this implicitly.
    """
    try:
        return {"reference_asset": reference_asset_service.confirm(project_id, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Scene 002 exact-entity setting reference manager (sync-free)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{project_id}/setting-references/{setting_id}")
def list_scene002_setting_references(project_id: str, setting_id: str):
    if setting_id != SCENE002_SETTING_ID:
        raise HTTPException(status_code=404, detail="Exact setting entity not found")
    try:
        rows = reference_asset_service.list_scene002_setting_references(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"project_id": project_id, "target_type": "setting", "target_id": setting_id,
            "reference_assets": rows, "count": len(rows)}


@router.post("/{project_id}/setting-references/{setting_id}")
def create_scene002_setting_reference(project_id: str, setting_id: str, payload: Scene002SettingReferenceCreate):
    if setting_id != SCENE002_SETTING_ID:
        raise HTTPException(status_code=404, detail="Exact setting entity not found")
    try:
        return {"reference_asset": reference_asset_service.create_scene002_setting_candidate(
            project_id, payload.image_url, category=payload.category,
        )}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/setting-references/{setting_id}/upload")
async def upload_scene002_setting_reference(
    project_id: str,
    setting_id: str,
    file: UploadFile = File(...),
    category: str = Form("environment"),
):
    """Register one uploaded image as a fresh exact-target candidate.

    Create-only: a fresh ``ref_set_`` identity, exactly
    ``setting/loc-c8f88b9c``, always ``candidate`` / non-canonical. It never
    upserts, never reuses an existing reference ID (including the legacy
    scene-targeted one), and never touches any other row.
    """
    if setting_id != SCENE002_SETTING_ID:
        raise HTTPException(status_code=404, detail="Exact setting entity not found")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        asset = reference_asset_service.upload_scene002_setting_candidate(
            project_id, data, category=category,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"reference_asset": asset}


@router.post("/{project_id}/setting-references/{setting_id}/{ref_id}/reject")
def reject_scene002_setting_reference(project_id: str, setting_id: str, ref_id: str):
    if setting_id != SCENE002_SETTING_ID:
        raise HTTPException(status_code=404, detail="Exact setting entity not found")
    try:
        return {"reference_asset": reference_asset_service.reject_scene002_setting_reference(project_id, ref_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{project_id}/setting-references/{setting_id}/{ref_id}/approve")
def approve_scene002_setting_reference(project_id: str, setting_id: str, ref_id: str):
    if setting_id != SCENE002_SETTING_ID:
        raise HTTPException(status_code=404, detail="Exact setting entity not found")
    try:
        return {"reference_asset": reference_asset_service.approve_scene002_setting_reference(project_id, ref_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{project_id}/setting-references/{setting_id}/{ref_id}/canonical")
def designate_scene002_setting_reference(project_id: str, setting_id: str, ref_id: str,
                                         payload: Scene002SettingReferenceCanonical):
    if setting_id != SCENE002_SETTING_ID:
        raise HTTPException(status_code=404, detail="Exact setting entity not found")
    try:
        return {"reference_asset": reference_asset_service.designate_scene002_setting_reference_canonical(project_id, ref_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3 — List confirmed assets (read from DB, survives restarts)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{project_id}/reference-library/{target_type}/{target_id}")
def get_reference_library(
    project_id: str,
    target_type: Literal["character", "setting"],
    target_id: str,
    sync: int = Query(default=1),
):
    """Return one entity's canonical, approved supporting, and candidate refs.

    ``sync=0`` skips the best-effort creator-reference sync for a pure read;
    any other value (including the default) preserves the existing sync-on-read.
    """
    if sync != 0:
        _sync_creator_references_best_effort(project_id)
    try:
        return reference_asset_service.list_library(project_id, target_type, target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/reference-library/{target_type}/{target_id}")
def add_reference_library_asset(
    project_id: str,
    target_type: Literal["character", "setting"],
    target_id: str,
    payload: ReferenceAsset,
):
    """Add an explicitly supplied library asset without changing the canonical ref."""
    if payload.project_id != project_id or payload.target_type != target_type or payload.target_id != target_id:
        raise HTTPException(status_code=400, detail="Reference asset scope does not match the URL")
    if target_type == "setting" and target_id == SCENE002_SETTING_ID:
        raise HTTPException(status_code=400, detail="Use the exact setting-reference create lifecycle")
    if payload.canonical:
        raise HTTPException(status_code=400, detail="Canonical references are changed only through the existing lock workflow")
    if payload.source_kind == "generated" and payload.approval_state == "approved":
        payload = payload.model_copy(update={"approval_state": "candidate"})
    try:
        saved = reference_asset_service.save_library_asset(payload.model_dump(mode="json"))
        if not saved:
            raise HTTPException(status_code=400, detail="Reference asset could not be saved")
        return reference_asset_service.get_asset(payload.ref_id) or payload.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/reference-library/{target_type}/{target_id}/upload")
async def upload_reference_library_asset(
    project_id: str,
    target_type: Literal["character", "setting"],
    target_id: str,
    file: UploadFile = File(...),
    category: str = Form("other"),
):
    """Register an uploaded image as a candidate supporting reference.

    Same registry, same approval gate, same consumption pipeline as URL-based
    additions. On any failure nothing is registered and nothing is approved —
    the canonical reference and existing pipeline state are untouched, and the
    filmmaker receives an actionable error and can retry.
    """
    if target_type == "setting" and target_id == SCENE002_SETTING_ID:
        raise HTTPException(status_code=400, detail="Use the exact setting-reference create lifecycle")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        asset = reference_asset_service.register_upload(
            project_id,
            target_type,
            target_id,
            category,
            data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"reference_asset": reference_asset_service.get_asset(asset["ref_id"]) or asset}


class ReferenceLibraryCanonical(BaseModel):
    """Body for explicit generic canonical designation.

    ``canonical`` must be exactly ``true`` (``extra`` is forbidden): the body
    states the intent, and the server decides whether the row is eligible.
    """
    model_config = ConfigDict(extra="forbid")
    canonical: Literal[True]


@router.post("/{project_id}/reference-library/setting/{target_id}/{ref_id}/canonical")
def designate_reference_library_canonical(
    project_id: str,
    target_id: str,
    ref_id: str,
    payload: ReferenceLibraryCanonical,
):
    """Explicitly designate one approved environment reference as canonical.

    Generic (parameterized) successor to the exact Scene 002 designation: the
    setting identity is the URL's ``target_id`` and is verified server-side
    against the project's canonical setting entity. The Scene 002 exact pair is
    refused here and keeps its own lifecycle. Nothing is approved, retargeted,
    or repaired by this call — only the canonical flag of the eligible row.
    """
    if project_id == SCENE002_PROJECT_ID and target_id == SCENE002_SETTING_ID:
        raise HTTPException(
            status_code=400,
            detail="Use the exact setting-reference canonical lifecycle",
        )
    try:
        return {
            "reference_asset": reference_asset_service.designate_setting_reference_canonical(
                project_id, target_id, ref_id,
            )
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/reference-library/{target_type}/{target_id}/{ref_id}/approve")
def approve_reference_library_asset(project_id: str, target_type: Literal["character", "setting"], target_id: str, ref_id: str):
    try:
        asset = reference_asset_service.get_asset(ref_id)
        if not asset or asset.get("target_type") != target_type or asset.get("target_id") != target_id:
            raise LookupError("Reference asset not found")
        return reference_asset_service.approve_supporting(project_id, ref_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{project_id}/reference-library/{target_type}/{target_id}/{ref_id}")
def remove_reference_library_asset(project_id: str, target_type: Literal["character", "setting"], target_id: str, ref_id: str):
    try:
        asset = reference_asset_service.get_asset(ref_id)
        if not asset or asset.get("target_type") != target_type or asset.get("target_id") != target_id:
            raise LookupError("Reference asset not found")
        reference_asset_service.remove_supporting(project_id, ref_id)
        return {"removed": True, "ref_id": ref_id}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{project_id}/reference-assets")
def list_reference_assets(
    project_id: str,
    kind: str | None = None,
    sync: int = Query(default=1),
):
    """List confirmed ReferenceAssets for a project from the DB.

    Creator-approved visuals (locked looks, approved environment stills) are
    synced into the registry first so the visual-training panels see every
    reference the creator has actually approved — not just assets promoted
    through the propose/confirm flow. ``sync=0`` skips that sync for a pure
    read; the default preserves the existing sync-on-read.
    """
    if sync != 0:
        _sync_creator_references_best_effort(project_id)
    assets = reference_asset_service.list_assets(project_id, kind)
    return {"reference_assets": assets, "count": len(assets)}
