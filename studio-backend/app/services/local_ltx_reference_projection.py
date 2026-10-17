"""Provider-specific projection for Local LTX's single-image i2v boundary.

This module does not select or mutate Reference Library truth. It projects the
already-selected, target-scoped consistency references into Local LTX's declared
capacity. The only supported non-canonical substitution is an explicitly planned
full-body framing with a canonical face anchor and an approved same-character
full-body reference. The canonical reference remains in the consistency payload
and is always recorded as available/fallback.
"""

from __future__ import annotations

from typing import Any


LOCAL_LTX_REFERENCE_CAPABILITY = {
    "maximum_reference_images": 1,
    "conditioning_mode": "i2v",
}

_FULL_BODY_FRAMINGS = {"full", "full body", "full body framing"}
_FACE_CATEGORIES = {"face", "facial", "headshot"}
_FULL_BODY_CATEGORIES = {"full_body", "fullbody", "body", "full"}
def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        # Work on a projection copy; never annotate/mutate canonical registry
        # rows or the caller's consistency payload.
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            result = dump(mode="json")
        except TypeError:
            result = dump()
        return result if isinstance(result, dict) else {}
    return {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _category(row: dict[str, Any]) -> str:
    category = _clean(row.get("category")).lower().replace("-", "_").replace(" ", "_")
    if category:
        return category
    role = _clean(row.get("reference_role")).lower().replace("-", "_").replace(" ", "_")
    if role:
        # A general character lock does not prove that its image is face-only or
        # full-body. Preserve that uncertainty rather than inferring from kind.
        return role
    # Legacy registry assets use character_face/character_full as their only
    # visual-role metadata.
    kind = _clean(row.get("kind")).lower()
    return "face" if kind == "character_face" else "full_body" if kind == "character_full" else ""


def _is_face(row: dict[str, Any]) -> bool:
    return _category(row) in _FACE_CATEGORIES


def _is_full_body(row: dict[str, Any]) -> bool:
    return _category(row) in _FULL_BODY_CATEGORIES


def _explicit_full_body_framing(scene_context: dict[str, Any]) -> bool:
    framing = _clean(scene_context.get("framing")).lower().replace("-", " ").replace("_", " ")
    return " ".join(framing.split()) in _FULL_BODY_FRAMINGS


def _source_matches_scene(row: dict[str, Any], scene_context: dict[str, Any]) -> bool:
    """Do not use a shot-attributed support image as another scene's context.

    Project-level references with no source shot remain eligible. A known source
    shot may be reused in its own shot or scene; opaque source identifiers fail
    closed for contextual substitution. Canonical truth is not filtered here.
    """
    source_shot_id = _clean(row.get("source_shot_id"))
    if not source_shot_id:
        return True
    current_shot_id = _clean(scene_context.get("shot_id"))
    current_scene_id = _clean(scene_context.get("scene_id"))
    if current_shot_id and source_shot_id == current_shot_id:
        return True
    if current_scene_id and (
        source_shot_id == current_scene_id
        or source_shot_id.startswith(f"{current_scene_id}_shot_")
    ):
        return True
    return False


def _eligible_refs(
    refs: list[Any],
    *,
    project_id: str,
    character_ids: set[str],
    setting_id: str,
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for raw in refs:
        row = _as_dict(raw)
        url = _clean(row.get("image_url"))
        approval_state = _clean(row.get("approval_state") or "approved").lower()
        lifecycle_states = {
            _clean(row.get(key)).lower()
            for key in ("lock_status", "source_status", "review_status", "status")
            if _clean(row.get(key))
        }
        if (
            not url
            or approval_state != "approved"
            or bool(row.get("stale") or row.get("is_stale"))
            or bool(lifecycle_states & {"stale", "superseded", "expired", "rejected", "candidate"})
            or _clean(row.get("project_id")) != project_id
            or _clean(row.get("target_type")) not in {"character", "setting"}
            or not _clean(row.get("target_id"))
            or (
                row.get("target_type") == "character"
                and _clean(row.get("target_id")) not in character_ids
            )
            or (
                row.get("target_type") == "setting"
                and (
                    not setting_id
                    or _clean(row.get("target_id")) != setting_id
                )
            )
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        row["image_url"] = url
        row["category"] = _category(row)
        eligible.append(row)
    return eligible


def project_local_ltx_reference(
    refs: list[Any],
    *,
    scene_context: dict[str, Any] | None = None,
    capability: dict[str, Any] | None = None,
    project_id: str = "",
    selection_audit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project Studio's selected refs to at most one approved Local LTX anchor.

    Stable payload order resolves ties; no timestamp, embeddings, visual scoring,
    prompt keyword inference, or provider-independent library policy is used.
    """
    declared = capability if isinstance(capability, dict) else LOCAL_LTX_REFERENCE_CAPABILITY
    capacity = declared.get("maximum_reference_images")
    mode = _clean(declared.get("conditioning_mode"))
    if capacity != 1 or mode != "i2v":
        return {
            "candidates": [],
            "selected": None,
            "canonical_reference_id": None,
            "canonical_available": False,
            "provider_capacity": capacity,
            "conditioning_mode": mode,
            "selection_reason": "provider does not declare the supported one-image i2v contract",
            "scene_context": dict(scene_context or {}),
        }

    context = dict(scene_context or {})
    character_ids_value = context.get("character_ids")
    character_ids = {
        _clean(value) for value in (character_ids_value or []) if _clean(value)
    } if isinstance(character_ids_value, list) else set()
    setting_id = _clean(context.get("setting_id"))
    raw_refs = list(refs or [])
    raw_character_refs_present = any(
        _clean(_as_dict(row).get("target_type")) == "character"
        for row in raw_refs
    )
    rows = _eligible_refs(
        raw_refs,
        project_id=project_id,
        character_ids=character_ids,
        setting_id=setting_id,
    )
    selection_reasons: dict[str, str] = {}

    def collect_reasons(value: Any) -> None:
        if isinstance(value, dict):
            ref_id = _clean(value.get("ref_id"))
            reason_text = _clean(value.get("reason") or value.get("_selection_reason"))
            if ref_id and reason_text:
                selection_reasons[ref_id] = reason_text
            for nested in value.values():
                collect_reasons(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_reasons(nested)

    collect_reasons(selection_audit or [])
    for row in rows:
        row["stage1_selection_reason"] = selection_reasons.get(_clean(row.get("ref_id")), "")
    character_refs = [row for row in rows if row.get("target_type") == "character"]
    canonical_character_refs = [row for row in character_refs if bool(row.get("canonical"))]
    canonical_ref = canonical_character_refs[0] if canonical_character_refs else None

    full_body_shot = _explicit_full_body_framing(context)
    primary: dict[str, Any] | None = None
    reason = ""

    if full_body_shot:
        # If identity truth already has a canonical full-body view, use it.
        primary = next((row for row in canonical_character_refs if _is_full_body(row)), None)
        if primary is not None:
            reason = "explicit full-body framing; selected the canonical full_body identity reference"
        elif canonical_ref is not None and _is_face(canonical_ref):
            # A supporting body view can condition physical presentation for an
            # explicitly full-body shot. The canonical face remains authoritative
            # in Studio's payload and is the upload fallback if this asset is stale.
            # When provenance names a source shot, only reuse it within that same
            # scene; a reference originating in a different scene cannot leak in.
            primary = next((
                row for row in character_refs
                if not bool(row.get("canonical"))
                and row.get("target_id") == canonical_ref.get("target_id")
                and _is_full_body(row)
                and _source_matches_scene(row, context)
            ), None)
            if primary is not None:
                reason = (
                    "explicit full-body framing; approved same-character full_body "
                    "reference supplies body/silhouette context while canonical face identity remains preserved"
                )

    if primary is None and canonical_ref is not None:
        primary = next((row for row in canonical_character_refs if _is_face(row)), canonical_ref)
        reason = (
            "canonical character identity reference retained; scene context does not "
            "explicitly require the full-body exception"
        )

    # Environment-only shots may use the current scene's already-scoped canonical
    # setting reference. Never let a setting reference replace a character anchor.
    canonical_setting = next((
        row for row in rows
        if row.get("target_type") == "setting" and bool(row.get("canonical"))
    ), None)
    # A setting image must never become an identity substitute. If any character
    # reference is present but no approved canonical character anchor survived
    # filtering, fail closed instead of masking the missing identity lock.
    if (
        primary is None
        and not character_ids
        and not raw_character_refs_present
        and canonical_setting is not None
    ):
        primary = canonical_setting
        reason = "setting-only shot; using the selected scene-owned canonical setting reference"
    elif primary is None and (character_ids or character_refs or raw_character_refs_present):
        reason = (
            "scene character ownership is unresolved or no approved canonical character anchor is available; "
            "refusing unrelated or supporting-only conditioning"
        )

    canonical_id = (
        _clean(canonical_ref.get("ref_id")) if canonical_ref
        else _clean(canonical_setting.get("ref_id")) if canonical_setting
        else None
    )
    canonical_available = bool(
        canonical_ref
        or (not character_ids and not raw_character_refs_present and canonical_setting)
    )
    candidates: list[dict[str, Any]] = []
    if primary is not None:
        candidates.append({
            "ref_id": _clean(primary.get("ref_id")) or None,
            "category": _category(primary) or None,
            "stage1_selection_reason": primary.get("stage1_selection_reason") or None,
            "image_url": _clean(primary.get("image_url")),
            "canonical": bool(primary.get("canonical")),
            "target_type": primary.get("target_type"),
            "target_id": primary.get("target_id"),
            "selection_reason": reason,
        })
        if not bool(primary.get("canonical")) and canonical_ref is not None:
            candidates.append({
                "ref_id": _clean(canonical_ref.get("ref_id")) or None,
                "category": _category(canonical_ref) or None,
                "stage1_selection_reason": canonical_ref.get("stage1_selection_reason") or None,
                "image_url": _clean(canonical_ref.get("image_url")),
                "canonical": True,
                "target_type": canonical_ref.get("target_type"),
                "target_id": canonical_ref.get("target_id"),
                "selection_reason": "safe fallback to the preserved canonical identity reference if the contextual asset is unavailable",
            })

    return {
        "candidates": candidates,
        "selected": candidates[0] if candidates else None,
        "canonical_reference_id": canonical_id,
        "canonical_available": canonical_available,
        "provider_capacity": 1,
        "conditioning_mode": "i2v",
        "selection_reason": reason,
        "scene_context": {
            key: value for key, value in context.items()
            if key in {"scene_id", "shot_id", "setting_id", "framing", "lighting", "time_of_day"}
            and value not in (None, "", [], {})
        },
        "studio_selected_references": [
            {
                "ref_id": _clean(row.get("ref_id")) or None,
                "category": _category(row) or None,
                "canonical": bool(row.get("canonical")),
                "target_type": row.get("target_type"),
                "target_id": row.get("target_id"),
                "approval_state": _clean(row.get("approval_state") or "approved"),
                "source_kind": row.get("source_kind"),
                "source_shot_id": row.get("source_shot_id"),
                "reference_created_at": row.get("reference_created_at") or row.get("created_at"),
                "reference_role": row.get("reference_role"),
                "look_id": row.get("look_id"),
                "lock_status": row.get("lock_status"),
                "source_status": row.get("source_status"),
                "review_status": row.get("review_status"),
                "capture_method": row.get("capture_method"),
                "reliability": row.get("reliability"),
                "stage1_selection_reason": row.get("stage1_selection_reason") or None,
            }
            for row in rows
        ],
        "not_consumed_count": max(0, len(rows) - (1 if primary is not None else 0)),
    }
