from __future__ import annotations

import logging
import sqlite3
from typing import Any

from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services.project_store import project_store
from app.services.stability import ValidationError
from app.utils.character_appearance import appearance_approval

logger = logging.getLogger("studio-setting-anchor")


_VALID_TARGET_TYPES = {"character", "setting"}
SCENE002_PROJECT_ID = "project_5907c60cddbc"
SCENE002_SETTING_ID = "loc-c8f88b9c"
LEGACY_SCENE002_REFERENCE_ID = "ref_env_6b726885ed67ae4d"
_VALID_APPROVAL_STATES = {"approved", "candidate", "rejected"}


def _failure(
    *,
    scene_id: str,
    reason: str,
    target_type: str = "",
    target_id: str = "",
    recovery_action: str = "",
    failure_type: str = "reference_validation_failed",
) -> ValidationError:
    target_label = f" for {target_type} {target_id}" if target_type and target_id else ""
    message = f"Generation blocked: Scene {scene_id}{target_label}. {reason}"
    return ValidationError(
        message,
        stage="reference_validation",
        metadata={
            "failure_type": failure_type,
            "scene_id": scene_id,
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
            "recovery_action": recovery_action,
        },
    )


def _project_dict(project: Any) -> dict[str, Any] | None:
    if hasattr(project, "model_dump"):
        project = project.model_dump(mode="json")
    return project if isinstance(project, dict) else None


def _scene(project_id: str, scene_id: str) -> dict[str, Any]:
    project = _project_dict(project_store.get_project(project_id))
    if project is None:
        raise _failure(
            scene_id=scene_id,
            reason="the project could not be resolved",
            failure_type="project_not_found",
            recovery_action="Refresh the project and retry generation.",
        )
    summary = project.get("execution_summary")
    scenes = summary.get("scenes") if isinstance(summary, dict) else []
    scene = next(
        (row for row in scenes or [] if isinstance(row, dict) and str(row.get("scene_id") or "") == scene_id),
        None,
    )
    if scene is None:
        raise _failure(
            scene_id=scene_id,
            reason="the selected scene does not exist in this project",
            failure_type="unknown_scene",
            recovery_action="Refresh the scene list and select an existing scene.",
        )
    return scene


def _scene_character_tokens(scene: dict[str, Any]) -> tuple[list[str], bool]:
    explicit = scene.get("character_ids") or scene.get("character_id")
    if explicit is not None:
        values = explicit if isinstance(explicit, list) else [explicit]
        ids = []
        for value in values:
            if isinstance(value, dict):
                value = value.get("id") or value.get("character_id")
            if str(value or "").strip():
                ids.append(str(value).strip())
        return ids, True

    raw = scene.get("character_appearances") or scene.get("characters") or []
    values = raw if isinstance(raw, list) else [raw]
    tokens: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("id") or value.get("character_id") or value.get("name")
        if str(value or "").strip():
            tokens.append(str(value).strip())
    return tokens, False


def _resolve_characters(*, project_id: str, scene_id: str, scene: dict[str, Any], storage: Any) -> list[dict[str, Any]]:
    tokens, explicit_ids = _scene_character_tokens(scene)
    resolved: list[dict[str, Any]] = []
    for token in tokens:
        character = None
        if explicit_ids and callable(getattr(storage, "get_character", None)):
            character = storage.get_character(token, project_id)
        elif callable(getattr(storage, "get_character_by_name", None)):
            character = storage.get_character_by_name(project_id, token)
            if character is None and callable(getattr(storage, "get_character", None)):
                character = storage.get_character(token, project_id)
        if (
            not isinstance(character, dict)
            or (explicit_ids and str(character.get("id") or "") != token)
            or (character.get("project_id") and str(character.get("project_id")) != project_id)
        ):
            raise _failure(
                scene_id=scene_id,
                target_type="character",
                target_id=token,
                reason="the selected scene contains a character that cannot be resolved within this project",
                failure_type="unknown_character",
                recovery_action=f"Open Scene {scene_id} and assign an existing character in this project.",
            )
        resolved.append(character)

    if explicit_ids and len({str(character.get("id") or "") for character in resolved}) != len(resolved):
        raise _failure(
            scene_id=scene_id,
            target_type="character",
            reason="the selected scene repeats a character identity",
            failure_type="duplicate_character_identity",
        )
    return resolved


def shot_character_focus_tokens(shot: Any) -> list[str]:
    """Read ordered, explicit character-focus tokens from a shot representation."""
    def as_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            dumped = value.model_dump(mode="python")
            return dumped if isinstance(dumped, dict) else {}
        return {}

    row = as_mapping(shot)
    parameters = as_mapping(row.get("parameters") or getattr(shot, "parameters", None))
    intent = as_mapping(row.get("intent") or getattr(shot, "intent", None))
    raw = row.get("character_focus")
    if raw is None:
        raw = parameters.get("character_focus")
    if raw is None:
        raw = intent.get("character_focus")
    if raw is None:
        return []
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    tokens: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("character_id") or value.get("character_name") or value.get("id") or value.get("name")
        token = str(value or "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def resolve_shot_character_ids(*, shot: Any, known_characters: dict[str, Any]) -> list[str]:
    """Resolve focus only against the current scene cast, preserving creator order.

    An absent focus retains the established full-cast requirement. An explicit
    focus may narrow that set, but unresolved or ambiguous names never widen it.
    """
    tokens = shot_character_focus_tokens(shot)
    if not tokens:
        return list(known_characters)
    shot_row = shot if isinstance(shot, dict) else {}
    shot_id = str(shot_row.get("shot_id") or getattr(shot, "shot_id", "") or "unknown")
    resolved: list[str] = []
    for token in tokens:
        matches = [
            str(character_id) for character_id, value in known_characters.items()
            if token == str(character_id)
            or token.casefold() == str((value if isinstance(value, dict) else {}).get("name") or "").strip().casefold()
        ]
        if len(matches) != 1:
            raise ValueError(f"shot {shot_id} required character identity unresolved or ambiguous: {token}")
        if matches[0] not in resolved:
            resolved.append(matches[0])
    return resolved


def _scene_characters_for_focus(
    *, characters: list[dict[str, Any]], character_focus: list[str] | None, scene_id: str,
) -> list[dict[str, Any]]:
    if character_focus is None:
        return characters
    by_id = {str(character.get("id") or ""): character for character in characters}
    known = {key: {"name": value.get("name", "")} for key, value in by_id.items()}
    try:
        resolved = resolve_shot_character_ids(
            shot={"shot_id": scene_id, "character_focus": character_focus},
            known_characters=known,
        )
    except ValueError as exc:
        token = str(character_focus[0]) if character_focus else ""
        raise _failure(
            scene_id=scene_id,
            target_type="character",
            target_id=token,
            reason="the approved shot focus does not resolve uniquely within the scene's structured cast",
            failure_type="shot_character_focus_unresolved",
            recovery_action="Update the approved shot focus to use one character from the scene cast, then prepare again.",
        ) from exc
    return [by_id[character_id] for character_id in resolved]


def _asset_rows(storage: Any, *, project_id: str, target_type: str, target_id: str) -> list[dict[str, Any]]:
    reader = getattr(storage, "list_reference_assets", None)
    if not callable(reader):
        return []
    try:
        rows = reader(project_id=project_id, target_type=target_type, target_id=target_id, limit=50) or []
    except TypeError:
        rows = reader(project_id=project_id, limit=50) or []
    return [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("project_id") or project_id) == project_id
        and str(row.get("target_type") or "") == target_type
        and str(row.get("target_id") or "") == target_id
    ]


def _is_alias_table_absent(exc: BaseException) -> bool:
    """True only when the failure is a missing ``universe_id_aliases`` table.

    A missing table (or a storage double without alias methods) means the
    deployment predates aliasing: the anchor check must behave exactly as
    before, silently. Every other lookup failure falls back to exact-only
    but logs a warning so it is visible instead of silent.
    """
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        return "no such table" in text and "universe_id_aliases" in text
    return False


def _setting_anchor_target_ids(storage: Any, *, project_id: str, setting_id: str) -> set[str]:
    """Exact setting ID plus alias old_node_ids resolving to it, same project.

    Central gate-narrowing-safe widening: an anchor row bound to a retired
    ID is accepted only when the committed alias resolver maps that retired
    ID to the requested live setting node in the same project. Missing alias
    table (or storage without alias methods) returns exactly ``{setting_id}``
    — identical to today. Ambiguous aliases have no row by construction, so
    they refuse exactly as today.
    """
    ids: set[str] = {setting_id}
    try:
        lister = getattr(storage, "list_universe_id_aliases", None)
        if not callable(lister):
            return ids
        aliases = lister(project_id) or []
    except Exception as exc:  # noqa: BLE001 — broken alias registry fails closed to exact-only
        if _is_alias_table_absent(exc):
            return ids
        logger.warning(
            "SETTING_ANCHOR_ALIAS_LOOKUP_FAILED | project_id=%s setting_id=%s error=%s",
            project_id,
            setting_id,
            exc,
        )
        return ids
    from app.services.universe_id_resolution import resolve_setting_entity

    for alias in aliases or []:
        if not isinstance(alias, dict):
            continue
        if str(alias.get("project_id") or "") != project_id:
            continue
        if str(alias.get("current_node_id") or "") != setting_id:
            continue
        old_id = str(alias.get("old_node_id") or "").strip()
        if not old_id or old_id == setting_id:
            continue
        try:
            node = resolve_setting_entity(storage, project_id, old_id)
        except Exception as exc:  # noqa: BLE001 — a broken resolver fails closed per alias
            if _is_alias_table_absent(exc):
                continue
            logger.warning(
                "SETTING_ANCHOR_ALIAS_LOOKUP_FAILED | project_id=%s setting_id=%s error=%s",
                project_id,
                setting_id,
                exc,
            )
            continue
        if (
            node is not None
            and str(node.get("node_id") or "") == setting_id
            and str(node.get("project_id") or "") == project_id
        ):
            ids.add(old_id)
    return ids


def _setting_anchor_rows(storage: Any, *, project_id: str, setting_id: str) -> list[dict[str, Any]]:
    """All candidate setting anchor rows: exact plus alias-bound, deduped."""
    rows: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for target_id in sorted(_setting_anchor_target_ids(storage, project_id=project_id, setting_id=setting_id)):
        for row in _asset_rows(storage, project_id=project_id, target_type="setting", target_id=target_id):
            ref_id = str(row.get("ref_id") or "")
            if not ref_id or ref_id in seen_refs:
                continue
            seen_refs.add(ref_id)
            rows.append(row)
    return rows


def _approved_character_references(storage: Any, *, project_id: str, character: dict[str, Any]) -> list[dict[str, Any]]:
    """Return approved canonical character anchors in deterministic source order."""
    character_id = str(character.get("id") or "")
    references: list[dict[str, Any]] = []
    rows = _asset_rows(storage, project_id=project_id, target_type="character", target_id=character_id)
    for row in rows:
        if not (
            row.get("canonical")
            and row.get("approval_state", "approved") == "approved"
            and str(row.get("kind") or "") in {"character_face", "character_full"}
        ):
            continue
        uri = str(row.get("image_url") or "").strip()
        ref_id = str(row.get("ref_id") or "").strip()
        if not uri or not ref_id:
            continue
        references.append({
            "ref_id": ref_id,
            "uri": uri,
            "target_type": "character",
            "target_id": character_id,
            "role": str(row.get("category") or row.get("kind") or "character"),
            "category": str(row.get("category") or row.get("kind") or ""),
            "canonical": True,
            "approval_state": "approved",
            "source_kind": str(row.get("source_kind") or "confirmed"),
            "kind": str(row.get("kind") or "character_face"),
        })

    try:
        approval = appearance_approval(character)
    except Exception:
        approval = {}
    if approval.get("status") == "locked":
        for field, role in (("face_image_url", "face"), ("body_image_url", "full_body")):
            uri = str(approval.get(field) or "").strip()
            if uri:
                references.append({
                    "ref_id": f"appearance:{character_id}:{role}",
                    "uri": uri,
                    "target_type": "character",
                    "target_id": character_id,
                    "role": role,
                    "category": role,
                    "canonical": True,
                    "approval_state": "approved",
                    "source_kind": "confirmed",
                    "kind": "character_face" if role == "face" else "character_full",
                })

    lock_reader = getattr(storage, "list_character_reference_locks_for_character", None)
    if callable(lock_reader):
        try:
            locks = lock_reader(project_id, character_id, "locked", 9, None) or []
        except Exception:
            locks = []
        for lock in locks:
            uri = str(lock.get("image_url") or "").strip()
            if not (
                uri
                and str(lock.get("project_id") or project_id) == project_id
                and str(lock.get("character_id") or character_id) == character_id
                and str(lock.get("lock_status") or "") == "locked"
                and str(lock.get("source_status") or "approved") == "approved"
                and str(lock.get("review_status") or "approved") in {"approved", "unreviewed"}
            ):
                continue
            role = str(lock.get("reference_role") or "general")
            lock_look = str(lock.get("look_id") or "default")
            ref_id = f"charlock:{character_id}:{role}" if lock_look == "default" else f"charlock:{character_id}:{lock_look}:{role}"
            references.append({
                "ref_id": ref_id,
                "uri": uri,
                "target_type": "character",
                "target_id": character_id,
                "role": role,
                "category": role,
                "canonical": True,
                "approval_state": "approved",
                "source_kind": "confirmed",
                "kind": "character_face" if role == "face" else "character_full",
            })

    unique: list[dict[str, Any]] = []
    seen_reference_ids: set[str] = set()
    for reference in references:
        identity = str(reference.get("ref_id") or "")
        if not identity or identity in seen_reference_ids:
            continue
        seen_reference_ids.add(identity)
        unique.append(reference)
    return unique


def _approved_character_urls(storage: Any, *, project_id: str, character: dict[str, Any]) -> list[str]:
    return [row["uri"] for row in _approved_character_references(storage, project_id=project_id, character=character)]


def _approved_setting_references(storage: Any, *, project_id: str, setting_id: str) -> list[dict[str, Any]]:
    rows = _setting_anchor_rows(storage, project_id=project_id, setting_id=setting_id)
    references: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        uri = str(row.get("image_url") or "").strip()
        ref_id = str(row.get("ref_id") or "").strip()
        if not (
            ref_id
            and row.get("canonical")
            and row.get("approval_state", "approved") == "approved"
            and str(row.get("kind") or "") == "environment"
            and uri
            and ref_id not in seen_ids
            and not (project_id == SCENE002_PROJECT_ID and setting_id == SCENE002_SETTING_ID
                     and ref_id == LEGACY_SCENE002_REFERENCE_ID)
        ):
            continue
        seen_ids.add(ref_id)
        references.append({
            "ref_id": ref_id,
            "project_id": project_id,
            "uri": uri,
            "target_type": "setting",
            "target_id": setting_id,
            "role": str(row.get("category") or "environment"),
            "category": str(row.get("category") or ""),
            "canonical": True,
            "approval_state": "approved",
            "source_kind": str(row.get("source_kind") or "confirmed"),
            "kind": "environment",
        })
    return references


def _approved_setting_urls(storage: Any, *, project_id: str, setting_id: str) -> list[str]:
    return [row["uri"] for row in _approved_setting_references(storage, project_id=project_id, setting_id=setting_id)]


def _identity_roles(value: Any) -> list[str]:
    """Read immutable selected role assignments for a consistency payload."""
    roles: dict[str, str] = {}
    for ref in getattr(value, "refs", []) or []:
        ref_id = str(getattr(ref, "ref_id", "") or "")
        if ref_id:
            roles[ref_id] = str(getattr(ref, "reference_role", None) or getattr(ref, "category", None) or getattr(ref, "kind", "reference"))
    return list(roles.values())


def reference_binding_digest(binding: list[dict[str, Any]]) -> str:
    """Hash the full ordered reference binding for persistence integrity."""
    import hashlib
    import json

    canonical = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def contract_comparison_binding(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Project reference rows onto the shared contract-versus-manifest comparison shape.

    This is the single comparison shape used by Runway Router creation
    (``render.create_job``), reconstruction
    (``reconstruct_runway_router_video_request``), and the parity tests: the
    exact 10-key rows (``ref_id``, ``uri``, ``target_type``, ``target_id``,
    ``role``, ``category``, ``canonical``, ``approval_state``, ``source_kind``,
    plus ``kind`` when present). Either input shape is accepted — frozen
    contract references carrying ``studio_role``, or raw canonical binding
    rows carrying ``role`` (and, for settings, ``project_id``) — and both
    project to identical rows, so the equality stays exact without comparing
    project scoping away (scoping is enforced separately by
    ``assert_setting_project_scope``). Ordering is preserved; no sorting, no
    dropping, no substitution. Missing keys or non-mapping rows fail closed.
    """
    # Option A: known setting framing terms (e.g. "wide") compare as
    # studio_role="environment" for kind=environment + target_type=setting
    # rows only. Single source of truth: generation_contract.
    # _SETTING_FRAMING_TERMS (lazy import keeps this cycle-free, matching the
    # codebase pattern). Raw rows stay stored verbatim; this is
    # comparison-only so a freshly frozen contract matches its raw manifest
    # binding. Unknown, garbage and composition roles never remap.
    from app.services.generation_contract import _setting_framing_studio_role

    projected: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            raise ValueError("Reference binding comparison requires mapping rows")
        effective_role = row.get("studio_role") or row["role"]
        remapped = _setting_framing_studio_role(
            effective_role, kind=row.get("kind"), target_type=row.get("target_type")
        )
        if remapped is not None:
            effective_role = remapped
        entry: dict[str, Any] = {
            "ref_id": row["ref_id"],
            "uri": row["uri"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "role": effective_role,
            "category": row["category"],
            "canonical": row["canonical"],
            "approval_state": row["approval_state"],
            "source_kind": row["source_kind"],
        }
        if row.get("kind"):
            entry["kind"] = row["kind"]
        projected.append(entry)
    return projected


def assert_setting_project_scope(binding: list[dict[str, Any]] | None, project_id: str) -> None:
    """Require every setting-type row's ``project_id`` to equal the job's project.

    The shared comparison shape deliberately excludes ``project_id`` so raw
    manifest rows and frozen contract references compare exactly; this
    assertion enforces project scoping separately so it can never be compared
    away. Any setting row missing ``project_id`` or carrying a foreign project
    fails closed with ``ValueError``, the same fail-closed family as the
    neighboring creation and reconstruction checks.
    """
    for row in binding or []:
        if not isinstance(row, dict):
            raise ValueError("Reference binding scope check requires mapping rows")
        if row.get("target_type") == "setting":
            if str(row.get("project_id") or "") != str(project_id or ""):
                raise ValueError(
                    "Reference binding setting anchor project scope does not match the job project"
                )


def reference_binding_for_requirements(
    requirements: dict[str, Any],
    *,
    supplied_urls: list[str] | None = None,
    required_character_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Freeze approved canonical refs in character-scene order, then setting order.

    Explicit shot references are accepted only when they identify one of the
    already-resolved canonical anchors. They cannot add, replace, or reorder the
    canonical selection.
    """
    resolved_character_ids = list(requirements.get("character_ids", []))
    if required_character_ids is not None and list(required_character_ids) != resolved_character_ids:
        raise ValueError("required character IDs do not match the shot-focused canonical requirements")
    selected = [
        dict(row)
        for character_id in resolved_character_ids
        for row in (requirements.get("characters", {}).get(character_id, {}).get("references") or [])
    ]
    if requirements.get("setting_references") is not None:
        selected.extend(dict(row) for row in requirements.get("setting_references", []) or [])
    else:
        # Contract-only legacy mode can pin an already authorized projection
        # without consulting mutable ordinary scene-reference selection.
        selected.extend(dict(row) for row in requirements.get("approved_scene_binding", []) or [])
    allowed_uris = {str(row.get("uri") or "") for row in selected}
    for uri in supplied_urls or []:
        value = str(uri or "").strip()
        if value and value not in allowed_uris:
            raise ValueError("shot reference is not one of the prepared canonical scene references")
    return selected


def frozen_reference_payload(binding: list[dict[str, Any]], *, project_id: str) -> ConsistencyPayload:
    """Construct Router-compatible consistency metadata from the same frozen list."""
    refs = []
    for row in binding:
        refs.append(ReferenceAsset(
            ref_id=str(row.get("ref_id") or ""),
            kind=str(row.get("kind") or ("environment" if row.get("target_type") == "setting" else "character_face")),
            image_url=str(row.get("uri") or ""),
            project_id=project_id,
            target_type=row.get("target_type"),
            target_id=row.get("target_id"),
            category=str(row.get("category") or ""),
            approval_state="approved",
            canonical=True,
            source_kind=str(row.get("source_kind") or "confirmed"),
            reference_role=str(row.get("role") or "reference"),
        ))
    return ConsistencyPayload(
        project_id=project_id,
        refs=refs,
        weights={ref.ref_id: 1.0 for ref in refs},
        mode="identity_lock",
        fallback_text={},
    )


def verify_frozen_reference_payload(*, job: Any, binding: Any) -> None:
    """Reject any final payload whose identities, order, roles, or URIs drift."""
    if not isinstance(binding, list) or not all(isinstance(row, dict) for row in binding):
        raise _failure(scene_id="unknown", reason="the frozen reference binding is malformed", failure_type="frozen_reference_binding_invalid")
    input_payload = job.input_payload
    metadata = getattr(job, "metadata", None) if isinstance(getattr(job, "metadata", None), dict) else {}
    recorded_digest = metadata.get("frozen_reference_binding_sha256")
    actual_digest = reference_binding_digest(binding)
    if not isinstance(recorded_digest, str) or not recorded_digest or actual_digest != recorded_digest:
        raise _failure(scene_id="unknown", reason="the persisted prepared reference binding integrity check failed", failure_type="frozen_reference_binding_integrity_mismatch")
    if not binding:
        raise _failure(scene_id="unknown", reason="the frozen reference binding is empty", failure_type="frozen_reference_binding_invalid")
    if any(
        not str(row.get("ref_id") or "").strip()
        or not str(row.get("uri") or "").strip()
        or not row.get("canonical")
        or str(row.get("approval_state") or "") != "approved"
        or row.get("target_type") not in _VALID_TARGET_TYPES
        or not str(row.get("target_id") or "").strip()
        or not str(row.get("role") or "").strip()
        or not str(row.get("kind") or "").strip()
        for row in binding
    ):
        raise _failure(scene_id="unknown", reason="the frozen reference binding contains an unapproved or incomplete anchor", failure_type="frozen_reference_binding_invalid")
    input_payload = job.input_payload
    expected_uris = [str(row.get("uri") or "") for row in binding]
    actual_uris = list(getattr(input_payload, "referenceAssets", None) or [])
    consistency = getattr(input_payload, "consistency_payload", None)
    if isinstance(consistency, dict):
        try:
            consistency = ConsistencyPayload(**consistency)
        except Exception:
            consistency = None
    actual_refs = list(getattr(consistency, "refs", []) or []) if consistency is not None else []
    expected_ids = [str(row.get("ref_id") or "") for row in binding]
    actual_ids = [str(getattr(row, "ref_id", "") or "") for row in actual_refs]
    expected_semantics = [
        (
            str(row.get("target_type") or ""), str(row.get("target_id") or ""),
            str(row.get("role") or ""), str(row.get("category") or ""),
            bool(row.get("canonical")), str(row.get("approval_state") or ""),
            str(row.get("source_kind") or "confirmed"), str(row.get("kind") or ""),
        )
        for row in binding
    ]
    actual_semantics = [
        (
            str(getattr(row, "target_type", None) or ""),
            str(getattr(row, "target_id", None) or ""),
            str(getattr(row, "reference_role", None) or ""),
            str(getattr(row, "category", None) or ""),
            bool(getattr(row, "canonical", False)),
            str(getattr(row, "approval_state", "") or ""),
            str(getattr(row, "source_kind", "") or ""),
            str(getattr(row, "kind", "") or ""),
        )
        for row in actual_refs
    ]
    actual_ref_uris = [str(getattr(row, "image_url", "") or "") for row in actual_refs]
    actual_projects = [str(getattr(row, "project_id", "") or "") for row in actual_refs]
    expected_weights = {ref_id: 1.0 for ref_id in expected_ids}
    actual_weights = dict(getattr(consistency, "weights", {}) or {}) if consistency is not None else {}
    actual_fallback_text = dict(getattr(consistency, "fallback_text", {}) or {}) if consistency is not None else {}
    if (
        not all(expected_ids)
        or len(set(expected_ids)) != len(expected_ids)
        or not all(expected_uris)
        or actual_uris != expected_uris
        or actual_ref_uris != expected_uris
        or actual_ids != expected_ids
        or actual_semantics != expected_semantics
        or actual_projects != [str(job.project_id)] * len(binding)
        or consistency is None
        or getattr(consistency, "project_id", None) != str(job.project_id)
        or set(actual_weights) != set(expected_weights)
        or any(not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight != 1.0 for weight in actual_weights.values())
        or getattr(consistency, "mode", None) != "identity_lock"
        or actual_fallback_text
        or getattr(consistency, "selection_audit", None) not in (None, [])
    ):
        raise _failure(
            scene_id="unknown",
            reason="the final provider payload does not exactly match the prepared canonical reference binding",
            failure_type="frozen_reference_payload_mismatch",
        )


def _setting_id(scene: dict[str, Any], scene_id: str) -> str:
    explicit = scene.get("setting_id") or scene.get("location_id") or scene.get("environment_id")
    if isinstance(explicit, dict):
        explicit = explicit.get("id") or explicit.get("setting_id")
    if str(explicit or "").strip():
        return str(explicit).strip()
    # Human-readable location/setting text is not a canonical identifier.
    return ""


def _verify_setting_identity_provenance(
    *, storage: Any, project_id: str, scene_id: str | None, setting_id: str,
    require_approved_anchor: bool = True,
) -> dict[str, Any]:
    """Fail closed unless a canonical setting entity and approved anchor resolve.

    Reference-asset ``target_id`` values and production-design environment
    profiles do not establish setting identity. An exact project-scoped universe
    location node may resolve identity; an independently approved canonical
    environment reference is still required as its anchor. This remains
    read-only and never infers approval or creates setting identity.

    ``scene_id=None`` validates the entity without binding it to one scene (used
    by explicit designation, which is scoped to the setting entity rather than
    to a single scene). Every production resolve path still passes a real scene
    id, so scene binding is enforced exactly as before.
    """
    entity_reader = getattr(storage, "get_setting", None)
    entity = None
    if callable(entity_reader):
        try:
            entity = entity_reader(setting_id, project_id)
        except TypeError:
            try:
                entity = entity_reader(project_id=project_id, setting_id=setting_id)
            except Exception:  # noqa: BLE001 — a broken entity resolver fails closed
                entity = None
        except Exception:  # noqa: BLE001 — a broken entity resolver fails closed
            entity = None
    if entity is None:
        # Existing universe location nodes are project-scoped canonical source
        # entities (unlike free-form scene location labels or reference target
        # IDs). Resolve through the central alias-aware resolver: an exact
        # node match wins, otherwise a universe_id_aliases row maps a retired
        # ID to its live node. The resolver never guesses. The entity keeps
        # the requested setting_id so approved-anchor checks against
        # reference rows (which still carry the original target ID) work
        # without rewriting any reference.
        from app.services.universe_id_resolution import resolve_setting_entity

        node = resolve_setting_entity(storage, project_id, setting_id)
        if node is not None:
            entity = {
                "id": setting_id, "project_id": node.get("project_id"),
                "entity_type": node.get("node_type"), "name": node.get("name"),
                "first_scene": node.get("first_scene"), "last_scene": node.get("last_scene"),
            }
    if hasattr(entity, "model_dump"):
        entity = entity.model_dump(mode="json")
    entity_id = str((entity or {}).get("setting_id") or (entity or {}).get("id") or "") if isinstance(entity, dict) else ""
    entity_type = str(entity.get("entity_type") or entity.get("node_type") or "") if isinstance(entity, dict) else ""
    entity_scene = str(entity.get("first_scene") or "") if isinstance(entity, dict) else ""
    if (
        not isinstance(entity, dict)
        or entity_id != setting_id
        or str(entity.get("project_id") or "") != project_id
        or (entity.get("canonical") is False)
        or (entity.get("canonical") is not True and entity_type != "location")
        or (entity_type and entity_type != "location")
        or (bool(scene_id) and bool(entity_scene) and entity_scene != scene_id)
    ):
        raise _failure(
            scene_id=scene_id,
            target_type="setting",
            target_id=setting_id,
            reason="setting identity provenance is missing: no canonical project-scoped setting entity resolves this ID",
            failure_type="setting_identity_unproven",
            recovery_action=f"Resolve the canonical setting for Scene {scene_id} before generation; do not infer it from location text or a reference target ID.",
        )
    if require_approved_anchor:
        try:
            rows = _setting_anchor_rows(storage, project_id=project_id, setting_id=setting_id)
        except Exception:  # noqa: BLE001 — a broken reference registry fails closed
            rows = None
        allowed_target_ids = _setting_anchor_target_ids(storage, project_id=project_id, setting_id=setting_id) if rows is not None else {setting_id}
        approved_rows = [
            row for row in (rows or [])
            if row.get("canonical")
            and str(row.get("approval_state") or "") == "approved"
            and str(row.get("kind") or "") == "environment"
            and str(row.get("ref_id") or "").strip()
            and str(row.get("project_id") or "") == project_id
            and str(row.get("target_type") or "") == "setting"
            and str(row.get("target_id") or "") in allowed_target_ids
            and not (project_id == SCENE002_PROJECT_ID and setting_id == SCENE002_SETTING_ID
                     and str(row.get("ref_id") or "") == LEGACY_SCENE002_REFERENCE_ID)
        ]
        if rows is None or not approved_rows:
            raise _failure(
                scene_id=scene_id,
                target_type="setting",
                target_id=setting_id,
                reason="canonical setting has no verifiable approved environment anchor",
                failure_type="setting_identity_unverifiable" if rows is None else "canonical_setting_reference_missing",
                recovery_action=f"Approve a canonical environment reference for Scene {scene_id} after resolving its canonical setting entity.",
            )
    return entity


def verify_setting_entity_scope(*, storage: Any, project_id: str, setting_id: str) -> dict[str, Any]:
    """Fail closed unless the exact project-scoped canonical setting entity resolves.

    Used by explicit canonical designation: a scene-labelled or phantom target
    (for example a raw scene id, or an entity owned by another project) must
    never be able to receive canonical authority. Read-only; no approval is
    inferred and no identity is created.
    """
    clean_project = str(project_id or "").strip()
    clean_setting = str(setting_id or "").strip()
    if not clean_project:
        raise _failure(
            scene_id="",
            target_type="setting",
            reason="a project id is required to designate a canonical setting reference",
            failure_type="setting_identity_unproven",
        )
    if not clean_setting:
        raise _failure(
            scene_id="",
            target_type="setting",
            reason="a canonical setting entity id is required to designate a reference",
            failure_type="setting_id_missing",
        )
    return _verify_setting_identity_provenance(
        storage=storage,
        project_id=clean_project,
        scene_id=None,
        setting_id=clean_setting,
        require_approved_anchor=False,
    )


def resolve_canonical_setting_id(
    *, project_id: str, scene_id: str, storage: Any, scene: dict[str, Any] | None = None,
) -> str:
    """Resolve and validate one exact canonical setting entity without requiring an anchor."""
    if scene is None:
        scene = _scene(project_id, scene_id)
    elif not isinstance(scene, dict) or str(scene.get("scene_id") or "") != scene_id:
        raise _failure(
            scene_id=scene_id,
            reason="the supplied scene does not match the requested scene id",
            failure_type="unknown_scene",
        )
    setting_id = _setting_id(scene, scene_id)
    if not setting_id or setting_id == scene_id:
        node_reader = getattr(storage, "get_universe_nodes", None)
        if callable(node_reader):
            try:
                nodes = node_reader(project_id) or []
            except Exception:  # noqa: BLE001 — a broken resolver fails closed
                nodes = []
            scene_locations = [
                row for row in nodes
                if isinstance(row, dict)
                and str(row.get("project_id") or "") == project_id
                and str(row.get("node_type") or "") == "location"
                and str(row.get("first_scene") or "") == scene_id
                and str(row.get("last_scene") or "") == scene_id
                and str(row.get("node_id") or "").strip()
            ]
            if len(scene_locations) == 1:
                setting_id = str(scene_locations[0]["node_id"]).strip()
    if not setting_id or setting_id == scene_id:
        raise _failure(
            scene_id=scene_id,
            target_type="setting",
            reason="the selected scene has no resolvable canonical setting ID",
            failure_type="setting_id_missing",
        )
    _verify_setting_identity_provenance(
        storage=storage, project_id=project_id, scene_id=scene_id,
        setting_id=setting_id, require_approved_anchor=False,
    )
    return setting_id


def _selected_setting_reference(
    *, storage: Any, project_id: str, scene_id: str, setting_id: str, reference_id: str,
) -> dict[str, Any]:
    reader = getattr(storage, "get_reference_asset", None)
    row = reader(reference_id) if callable(reader) else None
    if (not isinstance(row, dict)
            or str(row.get("ref_id") or "") != reference_id
            or (project_id == SCENE002_PROJECT_ID and setting_id == SCENE002_SETTING_ID
                and reference_id == LEGACY_SCENE002_REFERENCE_ID)):
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=setting_id,
            reason="the explicitly selected setting reference does not exist",
            failure_type="setting_reference_not_found",
        )
    if str(row.get("project_id") or "") != project_id:
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=setting_id,
            reason="the selected setting reference belongs to another project",
            failure_type="reference_project_mismatch",
        )
    if str(row.get("target_type") or "") != "setting" or str(row.get("target_id") or "") != setting_id:
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=str(row.get("target_id") or ""),
            reason="the selected reference does not target the exact canonical setting entity",
            failure_type="reference_ownership_mismatch",
        )
    if str(row.get("kind") or "") != "environment":
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=setting_id,
            reason="the selected setting reference is not an environment reference",
            failure_type="reference_kind_mismatch",
        )
    if str(row.get("approval_state") or "") != "approved":
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=setting_id,
            reason="the selected setting reference is not approved",
            failure_type="unapproved_reference",
        )
    if not bool(row.get("canonical")):
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=setting_id,
            reason="the selected setting reference is not canonical",
            failure_type="noncanonical_reference",
        )
    from app.services.reference_asset_service import scene002_setting_asset_view
    visible = scene002_setting_asset_view(row)
    visible_uri = str(visible.get("image_url") or "").strip() if visible else ""
    if visible is None or not visible_uri:
        raise _failure(
            scene_id=scene_id, target_type="setting", target_id=setting_id,
            reason="the selected setting reference file or URI is not valid under the reference library rules",
            failure_type="invalid_reference_uri",
        )
    return {
        "ref_id": reference_id,
        "project_id": project_id,
        "uri": visible_uri,
        "target_type": "setting",
        "target_id": setting_id,
        "role": str(row.get("category") or "environment"),
        "category": str(row.get("category") or ""),
        "canonical": True,
        "approval_state": "approved",
        "source_kind": str(row.get("source_kind") or "confirmed"),
        "kind": "environment",
    }


def _scene_direction_setting_reference_decision(*, storage: Any, project_id: str, scene_id: str) -> dict[str, Any] | None:
    """Read a decision only from the Scene Direction metadata on the current board version."""
    blueprint_reader = getattr(storage, "get_storyboard_blueprint", None)
    version_reader = getattr(storage, "get_storyboard_blueprint_version", None)
    if not callable(blueprint_reader) or not callable(version_reader):
        return None
    try:
        blueprint = blueprint_reader(project_id, scene_id)
        if (
            blueprint is None
            or str(getattr(blueprint, "project_id", "")) != project_id
            or str(getattr(blueprint, "scene_id", "")) != scene_id
            or not str(getattr(blueprint, "current_version_id", "") or "").strip()
        ):
            return None
        version_id = str(blueprint.current_version_id)
        version = version_reader(version_id)
        approved_version_id = str(getattr(blueprint, "approved_version_id", "") or "")
        if (
            not approved_version_id
            or approved_version_id != version_id
            or version is None
            or str(getattr(version, "version_id", "")) != version_id
            or str(getattr(version, "project_id", "")) != project_id
            or str(getattr(version, "scene_id", "")) != scene_id
            or str(getattr(getattr(version, "status", ""), "value", getattr(version, "status", ""))).strip().lower()
            not in {"approved", "locked", "storyboardblueprintstatus.approved", "storyboardblueprintstatus.locked"}
        ):
            return None
        scene_direction = (getattr(version, "metadata", {}) or {}).get("scene_direction")
        decision = scene_direction.get("setting_reference_decision") if isinstance(scene_direction, dict) else None
        if decision is None:
            return None
        from app.models.scene_direction import SettingReferenceDecision
        return SettingReferenceDecision.model_validate(decision).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 — malformed persisted authority fails closed
        raise _failure(
            scene_id=scene_id,
            target_type="setting",
            reason="the persisted Scene Direction setting reference decision is malformed",
            failure_type="setting_reference_decision_invalid",
        ) from exc

def resolve_scene_reference_requirements(
    *,
    project_id: str,
    scene_id: str,
    storage: Any,
    require_setting_reference: bool = True,
    require_canonical_references: bool = True,
    scene: dict[str, Any] | None = None,
    character_focus: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve the selected scene and its approved canonical reference anchors.

    This function is intentionally read-only. It never creates provisional locks,
    changes approval state, or mutates scene/project data.

    ``scene`` lets a caller inject the canonical scene dict it already resolved
    from the same authoritative source (e.g. the batch pre-flight works from
    the project state it was handed). When omitted the scene is resolved from
    the project store as before.
    """
    if scene is None:
        scene = _scene(project_id, scene_id)
    elif not isinstance(scene, dict) or str(scene.get("scene_id") or "") != scene_id:
        raise _failure(
            scene_id=scene_id,
            reason="the supplied scene does not match the requested scene id",
            failure_type="unknown_scene",
            recovery_action="Refresh the scene list and select an existing scene.",
        )
    scene_characters = _resolve_characters(project_id=project_id, scene_id=scene_id, scene=scene, storage=storage)
    focused_characters = _scene_characters_for_focus(
        characters=scene_characters,
        character_focus=character_focus,
        scene_id=scene_id,
    )
    scene_character_ids = [str(character.get("id") or "").strip() for character in scene_characters]
    scene_character_requirements: dict[str, dict[str, Any]] = {
        str(character.get("id") or "").strip(): {
            "name": character.get("name", ""), "urls": [], "references": [],
        }
        for character in scene_characters
    }
    character_requirements: dict[str, dict[str, Any]] = {}
    focused_character_ids = {str(character.get("id") or "").strip() for character in focused_characters}
    for character in focused_characters:
        character_id = str(character.get("id") or "").strip()
        references = _approved_character_references(storage, project_id=project_id, character=character)
        urls = [row["uri"] for row in references]
        rows = _asset_rows(storage, project_id=project_id, target_type="character", target_id=character_id)
        if not urls and require_canonical_references:
            has_unapproved = any(row.get("approval_state") in {"candidate", "rejected"} for row in rows)
            raise _failure(
                scene_id=scene_id,
                target_type="character",
                target_id=character_id,
                reason=("only candidate or rejected references are available" if has_unapproved else "no approved canonical reference is available"),
                failure_type="canonical_character_reference_missing",
                recovery_action=f"Open Character {character.get('name') or character_id} Visual References and approve a canonical reference.",
            )
        requirement = {"name": character.get("name", ""), "urls": urls, "references": references}
        scene_character_requirements[character_id] = requirement
        if character_id in focused_character_ids:
            character_requirements[character_id] = requirement

    if require_setting_reference:
        setting_id = resolve_canonical_setting_id(
            project_id=project_id, scene_id=scene_id, storage=storage, scene=scene,
        )
    else:
        setting_id = _setting_id(scene, scene_id)
        if not setting_id or setting_id == scene_id:
            node_reader = getattr(storage, "get_universe_nodes", None)
            if callable(node_reader):
                try:
                    nodes = node_reader(project_id) or []
                except Exception:  # noqa: BLE001 — optional legacy lookup fails closed
                    nodes = []
                scene_locations = [
                    row for row in nodes
                    if isinstance(row, dict)
                    and str(row.get("project_id") or "") == project_id
                    and str(row.get("node_type") or "") == "location"
                    and str(row.get("first_scene") or "") == scene_id
                    and str(row.get("last_scene") or "") == scene_id
                    and str(row.get("node_id") or "").strip()
                ]
                if len(scene_locations) == 1:
                    setting_id = str(scene_locations[0]["node_id"]).strip()
    decision: dict[str, Any] | None = None
    setting_urls: list[str] = []
    setting_references: list[dict[str, Any]] = []
    if require_setting_reference:
        if project_id == SCENE002_PROJECT_ID and setting_id == SCENE002_SETTING_ID:
            decision = _scene_direction_setting_reference_decision(
                storage=storage, project_id=project_id, scene_id=scene_id,
            )
            if decision is None:
                raise _failure(
                    scene_id=scene_id, target_type="setting", target_id=setting_id,
                    reason="no explicit Scene Direction setting reference decision exists",
                    failure_type="setting_reference_decision_missing",
                    recovery_action=f"Select a reference for the canonical setting in Scene {scene_id} Scene Direction.",
                )
            if decision["canonical_setting_id"] != setting_id:
                raise _failure(
                    scene_id=scene_id, target_type="setting", target_id=decision["canonical_setting_id"],
                    reason="the Scene Direction decision does not match the resolved canonical setting entity",
                    failure_type="setting_reference_decision_identity_mismatch",
                )
            _verify_setting_identity_provenance(
                storage=storage, project_id=project_id, scene_id=scene_id,
                setting_id=setting_id, require_approved_anchor=False,
            )
            setting_references = [_selected_setting_reference(
                storage=storage, project_id=project_id, scene_id=scene_id,
                setting_id=setting_id, reference_id=decision["reference_id"],
            )]
            setting_urls = [setting_references[0]["uri"]]
        else:
            _verify_setting_identity_provenance(
                storage=storage, project_id=project_id, scene_id=scene_id,
                setting_id=setting_id, require_approved_anchor=True,
            )
            setting_references = _approved_setting_references(
                storage, project_id=project_id, setting_id=setting_id,
            )
            # Competing canonical environment anchors would make the setting's
            # production authority ambiguous: production must never pick a
            # reference the creator did not leave as the single authority.
            # Fail closed instead of forwarding several. (The Scene 002 exact
            # path above is governed by its explicit decision and is not
            # affected, and its id-bound listing semantics are unchanged.)
            if len(setting_references) > 1:
                raise _failure(
                    scene_id=scene_id,
                    target_type="setting",
                    target_id=setting_id,
                    reason="competing canonical environment references make the setting authority ambiguous",
                    failure_type="canonical_setting_reference_ambiguous",
                    recovery_action=(
                        f"Designate exactly one canonical environment reference for the setting of Scene {scene_id}, "
                        "then prepare again."
                    ),
                )
            setting_urls = [row["uri"] for row in setting_references]

    return {
        "scene_id": scene_id,
        "scene_character_ids": scene_character_ids,
        "scene_characters": scene_character_requirements,
        "character_ids": list(character_requirements),
        "characters": character_requirements,
        "setting_id": setting_id,
        "setting_urls": setting_urls,
        "setting_references": setting_references,
        "setting_reference_decision": decision if require_setting_reference else None,
        "allowed_urls": list(dict.fromkeys([url for item in character_requirements.values() for url in item["urls"]] + setting_urls)),
    }


def reference_binding_coverage_projection(binding: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project canonical records onto the exact per-shot coverage schema."""
    fields = ("canonical", "approval_state", "source_kind", "kind")
    projected: list[dict[str, Any]] = []
    for row in binding:
        projected.append({
            "ref_id": row.get("ref_id"),
            "uri": row.get("uri"),
            "target_type": row.get("target_type"),
            "target_id": row.get("target_id"),
            "role": row.get("role", row.get("studio_role")),
            # Category is an independent canonical identity field. Preserve an
            # explicitly empty category rather than deriving it from ``kind``;
            # the latter is separately bound and compared below.
            "category": row.get("category", ""),
            **{field: row.get(field) for field in fields},
        })
    return projected


def reference_binding_coverage_identity(binding: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """Return ordered, reference-ID-sensitive identity records.

    Coverage rows may contain ``None`` for optional fields omitted by legacy
    reference assets, while the frozen contract serializes their model defaults.
    Normalize only those absent-value representations; never derive category
    from kind or weaken non-empty identity comparisons.
    """
    return [(
        str(row.get("ref_id") or ""),
        str(row.get("uri") or ""),
        str(row.get("target_type") or ""),
        str(row.get("target_id") or ""),
        str(row.get("role") or ""),
        str(row.get("category") or ""),
        bool(row.get("canonical")),
        str(row.get("approval_state") or "approved"),
        str(row.get("source_kind") or "confirmed"),
        str(row.get("kind") or ""),
    ) for row in binding]



def verify_shot_reference_coverage_binding(
    *, actual_binding: list[dict[str, Any]], coverage_shot: dict[str, Any], allow_missing: bool = False,
) -> None:
    """Require exact ordered agreement between frozen bindings and coverage."""
    coverage_binding = coverage_shot.get("approved_reference_bindings")
    coverage_ids = coverage_shot.get("approved_reference_ids")
    if (
        not isinstance(coverage_binding, list)
        or any(not isinstance(row, dict) for row in coverage_binding)
        or not isinstance(coverage_ids, list)
        or any(not isinstance(ref_id, str) or not ref_id for ref_id in coverage_ids)
        or len(coverage_ids) != len(set(coverage_ids))
        or not all(isinstance(row, dict) for row in actual_binding)
    ):
        raise ValueError("prepared shot reference binding or approved coverage IDs are malformed")
    actual_ids = [str(row.get("ref_id") or "") for row in actual_binding]
    if set(actual_ids) < set(coverage_ids):
        if not allow_missing:
            raise ValueError("prepared shot reference binding omits an approved reference")
        indices = [coverage_ids.index(ref_id) for ref_id in actual_ids if ref_id in coverage_ids]
        if (
            len(indices) != len(actual_ids)
            or indices != sorted(indices)
            or reference_binding_coverage_identity(actual_binding)
            != reference_binding_coverage_identity([coverage_binding[index] for index in indices])
        ):
            raise ValueError("prepared shot reference binding disagrees with approved coverage IDs, order, or identity")
        return
    if (
        actual_ids != coverage_ids
        or coverage_ids != [str(row.get("ref_id") or "") for row in coverage_binding]
        or reference_binding_coverage_identity(actual_binding)
        != reference_binding_coverage_identity(coverage_binding)
    ):
        raise ValueError("prepared shot reference binding disagrees with approved coverage IDs, order, or identity")


def validate_frozen_reference_binding_current(*, job: Any, storage: Any) -> dict[str, Any]:
    """Re-resolve every frozen identity against current canonical state at send time."""
    metadata = getattr(job, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    binding = metadata.get("frozen_reference_binding")
    verify_frozen_reference_payload(job=job, binding=binding)
    project_id = str(getattr(job, "project_id", "") or "")
    from app.utils.helpers import derive_scene_id_from_shot_id

    scene_id = derive_scene_id_from_shot_id(str(getattr(job, "shot_id", "") or ""))
    if not project_id or not scene_id:
        raise _failure(scene_id=scene_id or "unknown", reason="the frozen reference binding has no project or scene identity", failure_type="frozen_reference_binding_invalid")
    if any(
        row.get("project_id") is not None and str(row.get("project_id") or "") != project_id
        for row in binding
    ):
        raise _failure(scene_id=scene_id, reason="the frozen reference binding belongs to another project", failure_type="reference_project_mismatch")

    contract_record = metadata.get("creative_generation_contract")
    contract_payload = contract_record.get("payload") if isinstance(contract_record, dict) else None
    coverage_shot = contract_payload.get("scene_coverage_shot") if isinstance(contract_payload, dict) else None
    if coverage_shot is None:
        coverage_shot = metadata.get("scene_coverage_shot")
    if isinstance(coverage_shot, dict) and str(coverage_shot.get("shot_id") or "") != str(getattr(job, "shot_id", "") or ""):
        raise _failure(scene_id=scene_id, reason="the frozen shot coverage belongs to another shot", failure_type="frozen_reference_contract_mismatch")

    if isinstance(coverage_shot, dict) and not metadata.get("scene002_contract_only"):
        required_character_ids = coverage_shot.get("required_character_ids")
        required_setting_id = str(coverage_shot.get("required_setting_id") or "")
        if not isinstance(required_character_ids, list) or any(not str(value or "").strip() for value in required_character_ids):
            raise _failure(scene_id=scene_id, reason="the frozen shot coverage character requirements are malformed", failure_type="frozen_reference_contract_mismatch")
        required_character_ids = [str(value) for value in required_character_ids]
        if len(required_character_ids) != len(set(required_character_ids)):
            raise _failure(scene_id=scene_id, reason="the frozen shot coverage repeats a character identity", failure_type="frozen_reference_contract_mismatch")
        scene_record = _scene(project_id, scene_id)
        requirements = resolve_scene_reference_requirements(
            project_id=project_id,
            scene_id=scene_id,
            storage=storage,
            scene=scene_record,
            character_focus=required_character_ids,
        )
        if required_setting_id != str(requirements.get("setting_id") or ""):
            raise _failure(scene_id=scene_id, reason="the prepared shot setting differs from current canonical scene identity", failure_type="frozen_reference_binding_stale")
    else:
        requirements = resolve_scene_reference_requirements(
            project_id=project_id,
            scene_id=scene_id,
            storage=storage,
        )

    current_candidates = reference_binding_for_requirements(requirements)
    current_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in current_candidates:
        current_by_id.setdefault(str(row.get("ref_id") or ""), []).append(row)
    current_in_frozen_order: list[dict[str, Any]] = []
    for row in binding:
        ref_id = str(row.get("ref_id") or "")
        matches = current_by_id.get(ref_id, [])
        if len(matches) != 1:
            raise _failure(
                scene_id=scene_id,
                target_type=str(row.get("target_type") or ""),
                target_id=str(row.get("target_id") or ""),
                reason="the prepared reference ID is missing, revoked, or ambiguous in current canonical reference state",
                failure_type="frozen_reference_binding_stale",
            )
        current_in_frozen_order.append(matches[0])
    if reference_binding_coverage_identity(reference_binding_coverage_projection(binding)) != reference_binding_coverage_identity(reference_binding_coverage_projection(current_in_frozen_order)):
        raise _failure(
            scene_id=scene_id,
            reason="the prepared reference binding differs from current canonical reference state",
            failure_type="frozen_reference_binding_stale",
        )
    if isinstance(coverage_shot, dict):
        try:
            verify_shot_reference_coverage_binding(
                actual_binding=[
                    {**row, "role": coverage_row.get("role")}
                    for row, coverage_row in zip(
                        reference_binding_coverage_projection(binding),
                        coverage_shot.get("approved_reference_bindings") or [],
                    )
                ],
                coverage_shot=coverage_shot,
            )
        except ValueError as exc:
            raise _failure(
                scene_id=scene_id,
                reason=str(exc),
                failure_type="frozen_reference_contract_mismatch",
            ) from exc
    return requirements


def authorize_runway_router_image_references(*, payload: Any, storage: Any = None) -> dict[str, Any]:
    """Authorize exact image reference IDs against the current approved board and registry."""
    if not isinstance(payload, dict):
        raise _failure(scene_id="unknown", reason="the image reference request is malformed", failure_type="image_reference_payload_invalid")
    project_id = str(payload.get("project_id") or "").strip()
    scene_id = str(payload.get("scene_id") or "").strip()
    shot_id = str(payload.get("shot_id") or "").strip()
    if not project_id or not scene_id or not shot_id:
        raise _failure(scene_id=scene_id or "unknown", reason="the image reference request is missing project, scene, or shot identity", failure_type="image_reference_payload_invalid")
    if storage is None:
        from app.data.storage import get_storage
        storage = get_storage("sqlite")

    scene = _scene(project_id, scene_id)
    blueprint_reader = getattr(storage, "get_storyboard_blueprint", None)
    version_reader = getattr(storage, "get_storyboard_blueprint_version", None)
    shot_reader = getattr(storage, "get_storyboard_shot", None)
    blueprint = blueprint_reader(project_id, scene_id) if callable(blueprint_reader) else None
    version_id = str(getattr(blueprint, "current_version_id", "") or "") if blueprint else ""
    approved_version_id = str(getattr(blueprint, "approved_version_id", "") or "") if blueprint else ""
    if (
        blueprint is None
        or str(getattr(blueprint, "project_id", "") or "") != project_id
        or str(getattr(blueprint, "scene_id", "") or "") != scene_id
        or not version_id
        or version_id != approved_version_id
    ):
        raise _failure(scene_id=scene_id, reason="the image request does not match the current approved storyboard version", failure_type="image_storyboard_not_approved")
    version = version_reader(version_id) if callable(version_reader) else None
    if (
        version is None
        or str(getattr(version, "version_id", "") or "") != version_id
        or str(getattr(version, "project_id", "") or "") != project_id
        or str(getattr(version, "scene_id", "") or "") != scene_id
        or str(getattr(version, "status", "")) not in {"approved", "StoryboardBlueprintStatus.APPROVED"}
    ):
        raise _failure(scene_id=scene_id, reason="the image request storyboard version is no longer approved", failure_type="image_storyboard_not_approved")
    storyboard_shot_id = str(payload.get("storyboard_shot_id") or "").strip()
    shot = shot_reader(storyboard_shot_id) if callable(shot_reader) and storyboard_shot_id else None
    if (
        shot is None
        or str(getattr(shot, "project_id", "") or "") != project_id
        or str(getattr(shot, "scene_id", "") or "") != scene_id
        or str(getattr(shot, "shot_id", "") or "") != shot_id
        or str(getattr(shot, "version_id", "") or "") != version_id
        or str(getattr(shot, "status", "")) not in {"approved", "StoryboardShotStatus.APPROVED"}
    ):
        raise _failure(scene_id=scene_id, reason="the image request does not match an approved shot on the current storyboard", failure_type="image_storyboard_shot_mismatch")
    visual_plan = getattr(shot, "visual_plan", {})
    visual_plan = visual_plan.model_dump(mode="python") if hasattr(visual_plan, "model_dump") else visual_plan
    render_contract = getattr(shot, "render_contract", {})
    render_contract = render_contract.model_dump(mode="python") if hasattr(render_contract, "model_dump") else render_contract
    visual_plan = visual_plan if isinstance(visual_plan, dict) else {}
    render_contract = render_contract if isinstance(render_contract, dict) else {}
    selected_ids = visual_plan.get("reference_asset_ids")
    selected_uris = render_contract.get("reference_assets")
    if not isinstance(selected_ids, list) or not isinstance(selected_uris, list) or not selected_ids:
        raise _failure(scene_id=scene_id, reason="the approved image shot has no explicit canonical reference selection", failure_type="reference_identity_unproven")
    selected_ids = [str(value or "").strip() for value in selected_ids]
    selected_uris = [str(value or "").strip() for value in selected_uris]
    requested = payload.get("references")
    requested_uris: list[str] = []
    requested_ids: list[str] = []
    if isinstance(requested, list):
        for value in requested:
            if isinstance(value, dict):
                requested_uris.append(str(
                    value.get("uri") or value.get("image_url") or value.get("url") or value.get("asset_url") or ""
                ).strip())
                requested_ids.append(str(value.get("ref_id") or value.get("reference_id") or "").strip())
            else:
                requested_uris.append(str(value or "").strip())
                requested_ids.append("")
    if (
        not all(selected_ids) or len(selected_ids) != len(set(selected_ids))
        or not all(selected_uris) or len(selected_uris) != len(set(selected_uris))
        or requested_uris != selected_uris
        or (any(requested_ids) and requested_ids != selected_ids)
    ):
        raise _failure(scene_id=scene_id, reason="the image shot references differ from its approved ordered selection", failure_type="shot_reference_binding_mismatch")

    shot_character_focus = shot_character_focus_tokens(
        getattr(shot, "intent", {}) if shot is not None else {}
    ) if shot is not None else []
    requirements = resolve_scene_reference_requirements(
        project_id=project_id,
        scene_id=scene_id,
        storage=storage,
        scene=scene,
        character_focus=shot_character_focus or None,
    )
    candidates = reference_binding_for_requirements(
        requirements,
        required_character_ids=requirements.get("character_ids"),
    )
    candidate_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        candidate_by_id.setdefault(str(row.get("ref_id") or ""), []).append(row)
    binding: list[dict[str, Any]] = []
    for ref_id, uri in zip(selected_ids, selected_uris):
        matches = candidate_by_id.get(ref_id, [])
        if len(matches) != 1:
            raise _failure(scene_id=scene_id, target_type="reference", target_id=ref_id, reason="the selected image reference ID is not a current canonical identity", failure_type="reference_identity_unproven")
        row = dict(matches[0])
        if str(row.get("uri") or "") != uri:
            raise _failure(scene_id=scene_id, target_type=str(row.get("target_type") or "reference"), target_id=str(row.get("target_id") or ref_id), reason="the selected image reference ID no longer resolves to its approved URI", failure_type="shot_reference_binding_mismatch")
        row["project_id"] = project_id
        binding.append(row)
    requested_binding = payload.get("reference_binding")
    if requested_binding is not None and requested_binding != binding:
        raise _failure(scene_id=scene_id, reason="the image request binding differs from its approved ordered references", failure_type="shot_reference_binding_mismatch")
    generation_context_id = str(payload.get("generation_context_id") or "").strip()
    if not generation_context_id:
        ledger = (scene.get("multi_shot_execution_ledger") or []) if isinstance(scene, dict) else []
        entry = next((row for row in ledger if isinstance(row, dict) and str(row.get("shot_id") or "") == shot_id), {})
        generation_context_id = str(entry.get("generation_context_id") or "").strip()
    return {
        "project_id": project_id,
        "scene_id": scene_id,
        "shot_id": shot_id,
        "storyboard_version_id": version_id,
        "storyboard_shot_id": storyboard_shot_id,
        "binding_sha256": reference_binding_digest(binding),
        "generation_context_id": generation_context_id,
        "binding": binding,
        "references": binding,
    }


def validate_generation_payload(
    *,
    job: Any,
    storage: Any,
    require_setting_reference: bool = True,
    require_canonical_references: bool = True,
) -> dict[str, Any]:
    """Validate the final assembled payload immediately before provider submission."""
    scene_id = str(getattr(job, "shot_id", "") or "")
    from app.utils.helpers import derive_scene_id_from_shot_id
    scene_id = derive_scene_id_from_shot_id(scene_id)
    metadata = getattr(job, "metadata", {}) if isinstance(getattr(job, "metadata", None), dict) else {}
    coverage_shot = None
    contract_record = metadata.get("creative_generation_contract")
    if isinstance(contract_record, dict) and isinstance(contract_record.get("payload"), dict):
        coverage_shot = contract_record["payload"].get("scene_coverage_shot")
    if coverage_shot is None:
        coverage_shot = metadata.get("scene_coverage_shot")
    binding = metadata.get("frozen_reference_binding")
    if binding is not None:
        verify_frozen_reference_payload(job=job, binding=binding)
        if isinstance(coverage_shot, dict):
            try:
                verify_shot_reference_coverage_binding(
                    actual_binding=reference_binding_coverage_projection(binding),
                    coverage_shot=coverage_shot,
                )
            except ValueError as exc:
                raise _failure(
                    scene_id=scene_id,
                    reason=str(exc),
                    failure_type="frozen_reference_contract_mismatch",
                ) from exc
        if require_setting_reference:
            frozen_setting = [row for row in binding if row.get("target_type") == "setting"]
            exact_scene002_selection = (
                str(job.project_id) == SCENE002_PROJECT_ID
                and len(frozen_setting) == 1
                and str(frozen_setting[0].get("target_id") or "") == SCENE002_SETTING_ID
            )
            if exact_scene002_selection:
                scene_record = _scene(str(job.project_id), scene_id)
                current_setting_id = resolve_canonical_setting_id(
                    project_id=str(job.project_id), scene_id=scene_id,
                    storage=storage, scene=scene_record,
                )
                exact_scene002_selection = current_setting_id == SCENE002_SETTING_ID
            if exact_scene002_selection:
                requirements = resolve_scene_reference_requirements(
                    project_id=str(job.project_id),
                    scene_id=scene_id,
                    storage=storage,
                    require_setting_reference=True,
                    require_canonical_references=require_canonical_references,
                )
                expected = requirements["setting_references"]
                if (
                    len(frozen_setting) != 1
                    or len(expected) != 1
                    or str(frozen_setting[0].get("ref_id") or "") != str(expected[0].get("ref_id") or "")
                    or str(frozen_setting[0].get("uri") or "") != str(expected[0].get("uri") or "")
                    or str(frozen_setting[0].get("target_id") or "") != str(requirements["setting_id"] or "")
                    or str(frozen_setting[0].get("project_id") or "") != str(job.project_id)
                    or str(frozen_setting[0].get("kind") or "") != "environment"
                    or str(frozen_setting[0].get("approval_state") or "") != "approved"
                    or not bool(frozen_setting[0].get("canonical"))
                ):
                    raise _failure(
                        scene_id=scene_id, target_type="setting", target_id=str(requirements.get("setting_id") or ""),
                        reason="the frozen reference binding differs from the explicitly selected Scene Direction reference",
                        failure_type="selected_setting_reference_missing",
                    )
            else:
                setting_ids = {str(row.get("target_id") or "") for row in frozen_setting}
                if len(frozen_setting) != 1 or len(setting_ids) != 1 or not next(iter(setting_ids), ""):
                    raise _failure(
                        scene_id=scene_id, target_type="setting",
                        reason="the frozen reference binding must identify exactly one scene setting",
                        failure_type="frozen_reference_binding_invalid",
                    )
                character_rows: dict[str, dict[str, Any]] = {}
                for row in binding:
                    if row.get("target_type") == "character":
                        character = character_rows.setdefault(str(row.get("target_id") or ""), {
                            "name": str(row.get("target_id") or ""), "urls": [], "references": [],
                        })
                        character["urls"].append(str(row["uri"]))
                        character["references"].append(dict(row))
                setting_id = next(iter(setting_ids))
                requirements = {
                    "scene_id": scene_id,
                    "character_ids": list(character_rows),
                    "characters": character_rows,
                    "setting_id": setting_id,
                    "setting_urls": [str(row["uri"]) for row in frozen_setting],
                    "setting_references": [dict(row) for row in frozen_setting],
                    "setting_reference_decision": None,
                    "allowed_urls": list(dict.fromkeys(str(row["uri"]) for row in binding)),
                }
        else:
            character_rows: dict[str, dict[str, Any]] = {}
            setting_ids: set[str] = set()
            for row in binding:
                target_id = str(row.get("target_id") or "")
                if row.get("target_type") == "character":
                    character = character_rows.setdefault(target_id, {"name": target_id, "urls": [], "references": []})
                    character["urls"].append(str(row["uri"]))
                    character["references"].append(dict(row))
                elif row.get("target_type") == "setting":
                    setting_ids.add(target_id)
            if len(setting_ids) != 1:
                raise _failure(scene_id=scene_id, reason="the frozen binding must identify exactly one scene setting", failure_type="frozen_reference_binding_invalid")
            setting_id = next(iter(setting_ids))
            setting_references = [dict(row) for row in binding if row.get("target_type") == "setting"]
            requirements = {
                "scene_id": scene_id,
                "character_ids": list(character_rows),
                "characters": character_rows,
                "setting_id": setting_id,
                "setting_urls": [str(row["uri"]) for row in setting_references],
                "setting_references": setting_references,
                "allowed_urls": list(dict.fromkeys(str(row["uri"]) for row in binding)),
            }
    else:
        focused_character_ids = None
        if isinstance(coverage_shot, dict) and isinstance(coverage_shot.get("required_character_ids"), list):
            focused_character_ids = [str(value) for value in coverage_shot["required_character_ids"]]
        requirements = resolve_scene_reference_requirements(
            project_id=str(job.project_id),
            scene_id=scene_id,
            storage=storage,
            require_setting_reference=require_setting_reference,
            require_canonical_references=require_canonical_references,
            character_focus=focused_character_ids,
        )
    input_payload = job.input_payload
    cp_raw = getattr(input_payload, "consistency_payload", None)
    cp = ConsistencyPayload(**cp_raw) if isinstance(cp_raw, dict) else cp_raw
    if cp is None:
        if not require_canonical_references:
            return requirements
        raise _failure(
            scene_id=scene_id,
            reason="the assembled payload contains no validated reference set",
            failure_type="reference_payload_missing",
            recovery_action="Resolve the scene's approved canonical references and retry.",
        )
    if cp.project_id != job.project_id:
        raise _failure(scene_id=scene_id, reason="the reference payload belongs to another project", failure_type="payload_project_mismatch")

    refs = list(cp.refs)
    if len(refs) > 9:
        raise _failure(scene_id=scene_id, reason="the resolved reference set exceeds the provider limit of 9 images", failure_type="provider_reference_limit")
    valid_char_refs: dict[str, list[str]] = {character_id: [] for character_id in requirements["character_ids"]}
    selected_setting_decision = requirements.get("setting_reference_decision")
    if selected_setting_decision:
        selected_ref_id = str(selected_setting_decision.get("reference_id") or "")
        setting_rows = [ref for ref in refs if ref.target_type == "setting"]
        selected_rows = [
            ref for ref in setting_rows
            if ref.ref_id == selected_ref_id
            and ref.project_id == str(job.project_id)
            and ref.target_type == "setting"
            and ref.target_id == requirements["setting_id"]
            and ref.kind == "environment"
            and ref.approval_state == "approved"
            and bool(ref.canonical)
            and ref.image_url in requirements["setting_urls"]
        ]
        if len(selected_rows) != 1 or len(setting_rows) != 1 or len(selected_rows) != len(setting_rows):
            raise _failure(
                scene_id=scene_id, target_type="setting", target_id=requirements["setting_id"],
                reason="the final payload does not contain the exact explicitly selected canonical environment reference",
                failure_type="selected_setting_reference_missing",
            )
    for ref in refs:
        if ref.approval_state != "approved":
            raise _failure(scene_id=scene_id, target_type=ref.target_type or "unknown", target_id=ref.target_id or "", reason="a candidate or rejected reference is present in the provider payload", failure_type="unapproved_reference")
        if ref.target_type not in {None, "character", "setting"}:
            raise _failure(scene_id=scene_id, reason="the payload contains a reference with an invalid target type", failure_type="invalid_reference_target_type")
        if ref.target_type == "character":
            if ref.target_id not in valid_char_refs:
                raise _failure(scene_id=scene_id, target_type="character", target_id=ref.target_id or "", reason="a character reference belongs to a different character", failure_type="reference_ownership_mismatch")
            valid_char_refs[ref.target_id].append(ref.image_url)
        elif ref.target_type == "setting" and ref.target_id != requirements["setting_id"]:
            raise _failure(scene_id=scene_id, target_type="setting", target_id=ref.target_id or "", reason="a setting reference belongs to a different setting", failure_type="reference_ownership_mismatch")
        elif ref.target_type is None:
            # Legacy payloads predate target-scoped reference metadata. They
            # remain admissible only when the exact URL is one of this scene's
            # resolved canonical anchors; an unrelated project asset fails closed.
            matched = [character_id for character_id, character in requirements["characters"].items() if ref.image_url in character["urls"]]
            if ref.image_url in requirements["setting_urls"]:
                matched.append(requirements["setting_id"])
            if len(matched) != 1:
                raise _failure(scene_id=scene_id, reason="the payload contains an unowned or ambiguous reference", failure_type="reference_ownership_mismatch")
            if matched[0] in valid_char_refs:
                valid_char_refs[matched[0]].append(ref.image_url)

    for character_id, character in requirements["characters"].items():
        if require_canonical_references and not any(url in character["urls"] for url in valid_char_refs.get(character_id, [])):
            raise _failure(scene_id=scene_id, target_type="character", target_id=character_id, reason="the final payload is missing its approved canonical character reference", failure_type="payload_canonical_reference_missing", recovery_action=f"Open Character {character.get('name') or character_id} Visual References and approve a canonical reference.")

    if require_canonical_references and requirements["setting_id"] and require_setting_reference and not any(
        ref.target_type == "setting"
        and ref.target_id == requirements["setting_id"]
        and ref.image_url in requirements["setting_urls"]
        and (
            not selected_setting_decision
            or (
                ref.ref_id == str(selected_setting_decision.get("reference_id") or "")
                and ref.kind == "environment"
                and ref.approval_state == "approved"
                and bool(ref.canonical)
            )
        )
        for ref in refs
    ):
        # Existing character-only provider adapters may carry environment anchors
        # in render parameters rather than ConsistencyPayload.
        context = input_payload.parameters.get("environment_continuity_context") if isinstance(input_payload.parameters, dict) else None
        selected = context.get("selected_references") if isinstance(context, dict) else []
        if selected_setting_decision or not any(isinstance(row, dict) and row.get("image_url") in requirements["setting_urls"] for row in selected or []):
            raise _failure(scene_id=scene_id, target_type="setting", target_id=requirements["setting_id"], reason="the final payload is missing its approved canonical environment reference", failure_type="payload_canonical_reference_missing", recovery_action=f"Open Scene {scene_id} setting references and approve the required environment reference.")

    raw_assets = list(getattr(input_payload, "referenceAssets", []) or [])
    if any(str(value).strip() not in requirements["allowed_urls"] for value in raw_assets if str(value).strip()):
        raise _failure(scene_id=scene_id, reason="the payload contains a reference from another scene or target", failure_type="stale_reference_payload")
    return requirements
