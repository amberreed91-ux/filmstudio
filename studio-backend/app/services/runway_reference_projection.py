"""Runway reference projection policy ``runway_reference_projection/v1``.

This module is an independent, explicit Router video projection policy for the
frozen Scene 002 canonical five. It is intentionally NOT a generic reference
ranking engine: v1 accepts exactly one canonical input shape and applies one
explicitly enumerated selection rule.

Accepted v1 shape (canonical order preserved end to end)::

    (character:DRE, face)
    (character:MAYA, face)
    (character:MAYA, general)
    (character:MAYA, alternate_angle)
    (setting, environment)

Selection rule (enumerated, not ranked)::

    KEEP: DRE face, MAYA face, MAYA general, Scene 002 environment
    OMIT: MAYA alternate_angle  (studio_role == alternate_angle)

Discipline enforced here:

- The Router video capacity (4) is asserted at execution time against the
  single authoritative Router constant. Any other capacity fails closed.
- Output order is the original frozen canonical order after filtering. No
  weight sorting, no alphabetical sorting, no reordering for Runway.
- The explanatory role weights below are recorded as audit metadata only and
  are never consulted to determine the omission, so future weight changes
  cannot silently change v1 behavior.
- This module never selects, mutates, substitutes, reorders, or repairs
  canonical truth. It never touches the network, never submits a provider
  request, and never contacts any provider.
- URI materialization stays authorization-gated: local canonical paths can
  be transferred only after the creator authorization has validated the exact
  frozen binding and the selected local bytes match its fingerprint. Accepted
  provider URI forms are preserved byte-for-byte.
- The omitted reference is fingerprinted for auditability but is never
  materialized and never reaches the Router request builder.

Fingerprinting uses the existing ``local_reference_sha256`` byte verifier for
local canonical paths. Remote accepted provider URIs (``https://``,
``runway://``, ``data:image/``) are fingerprinted by their exact URI bytes,
since their content lives outside local verification and their provider URI
is an execution alias, never a canonical replacement.

Generic policy ``v2`` (``project_runway_v2``) accepts the explicitly defined
generic shape — one to four canonical references with zero or more character
identity rows plus exactly one setting environment anchor — and selects every
validated row in frozen order (the binding fits Router capacity, so nothing
is omitted). All v1 safety disciplines apply unchanged. ``v1`` still accepts
exactly the frozen Scene 002 five and is otherwise untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.providers import runway_router_provider
from app.services.scene002_contract_only import local_reference_sha256

POLICY_ID = "runway_reference_projection"
POLICY_VERSION = "v1"
POLICY_VERSION_V2 = "v2"
CAPACITY = 4

OMISSION_REASON_CODE = "capacity_4_of_5__lowest_identity_support_tier"
OMISSION_REASON_CODE_V2 = "within_capacity_no_omission"

# Explanatory policy metadata ONLY. These values are recorded in the audit
# record so the omission is human-legible, but selection never reads them.
# The v1 omission is the enumerated rule "omit studio_role == alternate_angle".
EXPLANATORY_TIER_WEIGHTS: dict[str, float] = {
    "face": 1.0,
    "general": 0.9,
    "alternate_angle": 0.7,
}

DROPPED_WEIGHT = EXPLANATORY_TIER_WEIGHTS["alternate_angle"]
RETAINED_IDENTITY_TIERS = ["face:1.0", "general:0.9"]

# G-F5-ROLE-1: body-only character looks sync as canonical ``full_body``
# rows (reference_asset_service look sync); they project as plain character
# reference images on the Router, exactly like face/general/alternate_angle.
_SUPPORTED_STUDIO_ROLES = frozenset({"face", "full_body", "general", "alternate_angle", "environment"})
_COMPOSITION_STUDIO_ROLES = frozenset({"storyboard", "storyboard_last"})
_TEMPORAL_STUDIO_ROLES = frozenset({"first", "last", "first_frame", "last_frame"})

_EXPECTED_TARGET_TYPES = ("character", "character", "character", "character", "setting")
_EXPECTED_STUDIO_ROLES = ("face", "face", "general", "alternate_angle", "environment")

_ACCEPTED_PROVIDER_SCHEMES = ("https://", "runway://", "data:image/")

_MAX_URI_LENGTH = 2048

# Projection execution fields. These live under job.metadata["router_execution"]
# and must never appear in the provider-neutral frozen creative contract.
PROJECTION_EXECUTION_FIELDS = (
    "projection_policy_id",
    "projection_policy_version",
    "selected_ref_ids",
    "omitted_ref_ids",
    "omission_reason_codes",
    "provider_role_map",
    "provider_uris",
    "source_uri_fingerprints",
    "projection_digest",
)


class RunwayReferenceProjectionError(ValueError):
    """Structured, fail-closed projection failure with a machine-readable code."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.detail: dict[str, Any] = {"code": code, **details}


def _fail(code: str, message: str, **details: Any) -> RunwayReferenceProjectionError:
    return RunwayReferenceProjectionError(code, message, **details)


def _default_backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _assert_router_capacity() -> int:
    """Fail closed unless the Router video reference capacity is exactly 4."""
    capacity = runway_router_provider.ROUTER_VIDEO_MAX_REFERENCE_IMAGES
    if capacity != CAPACITY:
        raise _fail(
            "capacity_mismatch",
            f"runway_reference_projection/v1 requires Router video capacity 4 "
            f"(observed {capacity!r}); refusing to adapt the policy.",
            observed_capacity=capacity,
            required_capacity=CAPACITY,
        )
    return capacity


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _canonical_token(value: Any) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def normalize_studio_role(studio_role: Any) -> str:
    """Pure Studio-role to Runway-role normalization.

    Canonical identity/environment roles (``face``, ``full_body``,
    ``general``, ``alternate_angle``, ``environment``) all normalize to
    ``reference``.
    True composition sources normalize ``storyboard`` to ``first`` and
    ``storyboard_last`` to ``last``. Anything else fails closed with
    ``unsupported_reference_role``; unknown roles are never coerced.
    """
    token = _canonical_token(studio_role)
    if token in _SUPPORTED_STUDIO_ROLES:
        return "reference"
    if token == "storyboard":
        return "first"
    if token == "storyboard_last":
        return "last"
    raise _fail(
        "unsupported_reference_role",
        f"Studio reference role {studio_role!r} has no Runway execution equivalent.",
        studio_role=_clean(studio_role),
    )


def _studio_role_of(row: dict[str, Any]) -> str:
    """Extract the canonical Studio role from either binding shape.

    Frozen contract references carry ``studio_role``; authority bindings carry
    ``role``. Both are honored without mutating the row.
    """
    for key in ("studio_role", "reference_role", "role"):
        token = _canonical_token(row.get(key))
        if token:
            return token
    return ""


def _router_role_of(row: dict[str, Any]) -> str:
    return _canonical_token(row.get("role"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate_uri(uri: Any, *, ref_id: str) -> str:
    value = uri if isinstance(uri, str) else ""
    if not value:
        raise _fail(
            "missing_uri",
            f"Canonical reference '{ref_id}' carries no URI; refusing to project.",
            ref_id=ref_id,
        )
    if value != value.strip():
        raise _fail(
            "malformed_uri",
            f"Canonical reference '{ref_id}' URI contains surrounding whitespace.",
            ref_id=ref_id,
        )
    if len(value) > _MAX_URI_LENGTH:
        raise _fail(
            "uri_too_long",
            f"Canonical reference '{ref_id}' URI exceeds {_MAX_URI_LENGTH} characters.",
            ref_id=ref_id,
            maximum=_MAX_URI_LENGTH,
        )
    return value


def _fingerprint_uri(uri: str, *, ref_id: str, backend_root: Path) -> str:
    """Fingerprint a provider URI exactly or hash bytes resolved under its mount."""
    if uri.lower().startswith(_ACCEPTED_PROVIDER_SCHEMES):
        return hashlib.sha256(uri.encode("utf-8")).hexdigest()
    try:
        from app.services.runway_ephemeral_upload import resolve_canonical_bytes

        data = resolve_canonical_bytes(uri, ref_id=ref_id, backend_root=backend_root)
        return hashlib.sha256(data).hexdigest()
    except (OSError, ValueError) as exc:
        raise _fail(
            "unavailable_source_bytes",
            f"Canonical reference '{ref_id}' source bytes cannot be verified: {exc}",
            ref_id=ref_id,
        ) from exc


def compute_source_fingerprints(
    canonical_refs: Any,
    *,
    backend_root: Path | None = None,
) -> dict[str, str]:
    """Fingerprint all canonical references, including any later omitted one."""
    if not isinstance(canonical_refs, list):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "runway_reference_projection/v1 requires an ordered list of canonical references.",
        )
    root = backend_root if backend_root is not None else _default_backend_root()
    fingerprints: dict[str, str] = {}
    for index, row in enumerate(canonical_refs):
        if not isinstance(row, dict):
            raise _fail(
                "invalid_canonical_count_or_shape",
                f"Canonical reference at index {index} is not an object.",
                index=index,
            )
        ref_id = _clean(row.get("ref_id"))
        if not ref_id:
            raise _fail(
                "invalid_canonical_count_or_shape",
                f"Canonical reference at index {index} carries no ref_id.",
                index=index,
            )
        uri = _validate_uri(row.get("uri"), ref_id=ref_id)
        fingerprints[ref_id] = _fingerprint_uri(uri, ref_id=ref_id, backend_root=root)
    return fingerprints


def materialize_uri(
    uri: Any,
    *,
    ref_id: str = "",
    allow_local_source_uri: bool = False,
    backend_root: Path | None = None,
) -> str:
    """Validate one URI without network access.

    Accepted provider URI forms (``https://``, ``runway://``,
    ``data:image/``) are returned byte-for-byte. Local canonical paths are
    accepted only behind creator authorization and verified as mounted assets;
    the adapter must replace them with ephemeral URIs before request creation.
    """
    value = _validate_uri(uri, ref_id=ref_id or "unknown")
    if value.lower().startswith(_ACCEPTED_PROVIDER_SCHEMES):
        return value
    parsed = urlparse(value)
    if allow_local_source_uri and not parsed.scheme and not parsed.netloc and not parsed.query and not parsed.fragment:
        # Local locators are internal only. Verify they resolve to an existing
        # mounted asset before allowing the authorized adapter to materialize.
        from app.services.runway_ephemeral_upload import resolve_canonical_bytes

        try:
            resolve_canonical_bytes(value, ref_id=ref_id or "unknown", backend_root=backend_root)
        except ValueError as exc:
            raise _fail("unavailable_source_bytes", str(exc), ref_id=ref_id or "unknown") from exc
        return value
    raise _fail(
        "unsupported_uri_scheme",
        f"Reference '{ref_id or 'unknown'}' uses a URI scheme Runway cannot fetch; "
        "no authorized materialization mechanism exists for local canonical paths.",
        ref_id=ref_id or "unknown",
        scheme=parsed.scheme[:24] if ":" in value else "",
    )


def materialize_selected(
    canonical_by_id: dict[str, dict[str, Any]],
    ref_ids: list[str],
    *,
    allow_local_source_uris: bool = False,
    backend_root: Path | None = None,
) -> dict[str, str]:
    """Materialize exactly the selected references, in the given order."""
    provider_uris: dict[str, str] = {}
    for ref_id in ref_ids:
        row = canonical_by_id.get(ref_id)
        if not isinstance(row, dict):
            raise _fail(
                "frozen_contract_or_binding_mismatch",
                f"Selected reference '{ref_id}' cannot be resolved to a canonical row.",
                ref_id=ref_id,
            )
        provider_uris[ref_id] = materialize_uri(
            row.get("uri"), ref_id=ref_id,
            allow_local_source_uri=allow_local_source_uris,
            backend_root=backend_root,
        )
    return provider_uris


def _validate_v1_shape(rows: list[dict[str, Any]]) -> None:
    """Enforce the exact Scene 002 five-reference canonical shape."""
    if len(rows) != 5:
        raise _fail(
            "invalid_canonical_count_or_shape",
            f"runway_reference_projection/v1 requires exactly 5 canonical references "
            f"(observed {len(rows)}).",
            canonical_count=len(rows),
        )
    ref_ids = [_clean(row.get("ref_id")) for row in rows]
    if any(not ref_id for ref_id in ref_ids):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Every canonical reference must carry a non-empty ref_id.",
        )
    if len(set(ref_ids)) != len(ref_ids):
        raise _fail(
            "ambiguous_selection",
            "Canonical reference identities are duplicated or ambiguous.",
            canonical_ref_ids=ref_ids,
        )

    target_types = [_clean(row.get("target_type")) for row in rows]
    if target_types != list(_EXPECTED_TARGET_TYPES):
        raise _fail(
            "invalid_canonical_count_or_shape",
            f"Canonical target-type shape {target_types} does not match the v1 "
            "Scene 002 shape [character, character, character, character, setting].",
            target_types=target_types,
        )

    for row in rows:
        studio_role = _studio_role_of(row)
        router_role = _router_role_of(row)
        if (
            router_role in {"first", "last"}
            or studio_role in _COMPOSITION_STUDIO_ROLES
            or studio_role in _TEMPORAL_STUDIO_ROLES
        ):
            raise _fail(
                "unsupported_provider_role",
                f"Canonical reference '{row.get('ref_id')}' carries composition "
                "frame semantics; v1 identity/environment references must not "
                "consume first/last capacity.",
                ref_id=_clean(row.get("ref_id")),
                router_role=router_role,
                studio_role=studio_role,
            )
        try:
            provider_role = normalize_studio_role(studio_role)
        except RunwayReferenceProjectionError:
            raise
        if provider_role != "reference":
            raise _fail(
                "unsupported_provider_role",
                f"Canonical reference '{row.get('ref_id')}' does not normalize to "
                "the reference provider role.",
                ref_id=_clean(row.get("ref_id")),
                studio_role=studio_role,
            )

    studio_roles = [_studio_role_of(row) for row in rows]
    if sorted(studio_roles) != sorted(_EXPECTED_STUDIO_ROLES):
        raise _fail(
            "missing_required_reference",
            f"Canonical roles {studio_roles} omit a required v1 reference; v1 requires "
            "exactly [face, face, general, alternate_angle, environment].",
            studio_roles=studio_roles,
        )
    if studio_roles != list(_EXPECTED_STUDIO_ROLES):
        raise _fail(
            "invalid_canonical_count_or_shape",
            f"Canonical role order {studio_roles} contradicts the frozen v1 authority "
            "order [face, face, general, alternate_angle, environment].",
            studio_roles=studio_roles,
        )

    dre_identity = _clean(rows[0].get("target_id"))
    maya_identities = [_clean(rows[index].get("target_id")) for index in (1, 2, 3)]
    setting_identity = _clean(rows[4].get("target_id"))
    if not dre_identity or not all(maya_identities) or not setting_identity:
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Every canonical reference must carry a non-empty target identity.",
        )
    if dre_identity in maya_identities:
        raise _fail(
            "ambiguous_selection",
            "DRE and MAYA character identities are not distinct; v1 cannot bind "
            "per-character coverage.",
        )
    if len(set(maya_identities)) != 1:
        raise _fail(
            "ambiguous_selection",
            "MAYA identity references do not share one character identity.",
            maya_identities=maya_identities,
        )

    for row in rows:
        if row.get("approval_state") != "approved" or row.get("canonical") is not True:
            raise _fail(
                "unapproved_reference",
                f"Canonical reference '{row.get('ref_id')}' is not an approved "
                "canonical anchor.",
                ref_id=_clean(row.get("ref_id")),
                approval_state=row.get("approval_state"),
                canonical=row.get("canonical"),
            )


def policy_version_for_canonical_rows(canonical_refs: Any) -> str:
    """Select the projection policy version from the explicitly defined shapes.

    Exactly five canonical references route to v1 (the frozen Scene 002
    shape, validated in full by ``_validate_v1_shape``). One to four route to
    v2 (the generic shape, validated by ``_validate_v2_shape``). Anything
    else — empty, or above Router capacity — fails closed here so no caller
    has to guess. Count alone never authorizes: the selected policy still
    validates every row.
    """
    if not isinstance(canonical_refs, list) or not canonical_refs:
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Reference projection requires at least one canonical reference.",
        )
    if len(canonical_refs) == 5:
        return POLICY_VERSION
    if 1 <= len(canonical_refs) <= CAPACITY:
        return POLICY_VERSION_V2
    raise _fail(
        "invalid_canonical_count_or_shape",
        f"Reference projection supports at most {CAPACITY} canonical references "
        f"(observed {len(canonical_refs)}); narrow the binding before projecting.",
        canonical_count=len(canonical_refs),
    )


def compute_projection_digest(
    *,
    canonical_ref_ids: list[str],
    source_uri_fingerprints: dict[str, str],
    selected_ref_ids: list[str],
    omitted_ref_ids: list[str],
    studio_role_map: dict[str, str],
    provider_role_map: dict[str, str],
    provider_uris: dict[str, str] | None = None,
    policy_id: str = POLICY_ID,
    policy_version: str = POLICY_VERSION,
) -> str:
    """Deterministic SHA-256 over the canonical frozen projection inputs only.

    Projection identity covers the pinned policy, canonical/selected/omitted
    identities, source fingerprints, and role maps. Ephemeral execution
    aliases (``runway://`` URIs, upload timestamps, request IDs, temporary
    upload URLs) are deliberately excluded: the same canonical Scene 002
    inputs must produce the same ``projection_digest`` across repeated
    materializations. Execution-specific identity lives in
    ``app.services.runway_ephemeral_upload.compute_materialization_digest``.

    ``provider_uris`` is accepted (ignored) for backward compatibility with
    callers written before the B.5 digest correction; it never affects output.
    """
    _ = dict(provider_uris) if provider_uris is not None else None
    canonical = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "canonical_ref_ids": list(canonical_ref_ids),
        "source_uri_fingerprints": dict(source_uri_fingerprints),
        "selected_ref_ids": list(selected_ref_ids),
        "omitted_ref_ids": list(omitted_ref_ids),
        "studio_role_map": dict(studio_role_map),
        "provider_role_map": dict(provider_role_map),
    }
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()


def project_runway_v1(
    canonical_refs: list[dict[str, Any]],
    *,
    backend_root: Path | None = None,
    source_fingerprints: dict[str, str] | None = None,
    approved_reference_ids: list[str] | None = None,
    expected_binding: list[dict[str, Any]] | None = None,
    allow_local_source_uris: bool = False,
) -> dict[str, Any]:
    """Project the frozen Scene 002 five into exactly four Router references.

    Pure: no network calls, no provider submission, no mutation of the inputs.
    The omitted MAYA ``alternate_angle`` reference is fingerprinted for
    auditability and never materialized.
    """
    capacity = _assert_router_capacity()
    if not isinstance(canonical_refs, list):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "runway_reference_projection/v1 requires an ordered list of canonical references.",
        )
    rows = [dict(row) if isinstance(row, dict) else row for row in canonical_refs]
    if any(not isinstance(row, dict) for row in rows):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Canonical references must be objects.",
        )
    rows = [row for row in rows if isinstance(row, dict)]

    for index, row in enumerate(rows):
        _validate_uri(row.get("uri"), ref_id=_clean(row.get("ref_id")) or f"index_{index}")

    _validate_v1_shape(rows)

    if expected_binding is not None:
        identity_fields = ("ref_id", "uri", "target_type", "target_id", "canonical", "approval_state")
        actual = [
            {key: row.get(key) for key in identity_fields if key in row}
            for row in rows
        ]
        expected = [
            {key: row.get(key) for key in identity_fields if key in row}
            for row in expected_binding
        ]
        actual_roles = [_studio_role_of(row) for row in rows]
        expected_roles = [
            _studio_role_of(row) if isinstance(row, dict) else ""
            for row in expected_binding
        ]
        if actual != expected or actual_roles != expected_roles:
            raise _fail(
                "frozen_contract_or_binding_mismatch",
                "Canonical ordering or binding identity contradicts the frozen authority.",
            )

    if approved_reference_ids is not None:
        missing = [ref_id for ref_id in approved_reference_ids if ref_id not in {_clean(row.get("ref_id")) for row in rows}]
        if missing:
            raise _fail(
                "frozen_contract_or_binding_mismatch",
                "Scene coverage requires canonical references absent from the projection inputs.",
                missing_reference_ids=missing,
            )

    root = backend_root if backend_root is not None else _default_backend_root()
    # Local canonical paths are permitted only for authorized projections, but
    # authorization does not replace byte verification: every local source
    # (including an omitted row) must resolve beneath the configured mount.
    recomputed = compute_source_fingerprints(rows, backend_root=root)
    if source_fingerprints is not None:
        if dict(source_fingerprints) != recomputed:
            raise _fail(
                "source_fingerprint_mismatch",
                "Supplied source fingerprints do not match recomputed canonical bytes.",
            )
    fingerprints = recomputed

    canonical_ref_ids = [_clean(row.get("ref_id")) for row in rows]
    omitted_row = rows[3]
    if _studio_role_of(omitted_row) != "alternate_angle":
        raise _fail(
            "ambiguous_selection",
            "The v1 enumerated omission requires studio_role == alternate_angle "
            "at the fourth canonical position.",
        )
    # Explicit enumerated rule: omit studio_role == alternate_angle for the
    # validated Scene 002 shape. No weight ranking is consulted here.
    selected_ref_ids = [canonical_ref_ids[0], canonical_ref_ids[1], canonical_ref_ids[2], canonical_ref_ids[4]]
    omitted_ref_ids = [canonical_ref_ids[3]]

    studio_role_map = {ref_id: _studio_role_of(row) for ref_id, row in zip(canonical_ref_ids, rows)}
    provider_role_map = {ref_id: "reference" for ref_id in selected_ref_ids}

    canonical_by_id = {ref_id: row for ref_id, row in zip(canonical_ref_ids, rows)}
    provider_uris = materialize_selected(
        canonical_by_id,
        selected_ref_ids,
        allow_local_source_uris=allow_local_source_uris,
        backend_root=root,
    )
    if omitted_ref_ids[0] in provider_uris:
        raise _fail(
            "ambiguous_selection",
            "The omitted reference must never be materialized for the Router request.",
        )

    digest = compute_projection_digest(
        canonical_ref_ids=canonical_ref_ids,
        source_uri_fingerprints=fingerprints,
        selected_ref_ids=selected_ref_ids,
        omitted_ref_ids=omitted_ref_ids,
        studio_role_map=studio_role_map,
        provider_role_map=provider_role_map,
    )

    dre_identity = _clean(rows[0].get("target_id"))
    maya_identity = _clean(rows[1].get("target_id"))
    return {
        "projection_policy_id": POLICY_ID,
        "projection_policy_version": POLICY_VERSION,
        "capacity": capacity,
        "canonical_count": len(canonical_ref_ids),
        "selected_count": len(selected_ref_ids),
        "omitted_count": len(omitted_ref_ids),
        "canonical_ref_ids": canonical_ref_ids,
        "selected_ref_ids": selected_ref_ids,
        "omitted_ref_ids": omitted_ref_ids,
        "omission_reason_codes": [OMISSION_REASON_CODE],
        "studio_role_map": studio_role_map,
        "provider_role_map": provider_role_map,
        "source_uri_fingerprints": fingerprints,
        "provider_uris": provider_uris,
        "projection_digest": digest,
        "dropped_tier": "alternate_angle",
        "dropped_weight": DROPPED_WEIGHT,
        "retained_identity_tiers": list(RETAINED_IDENTITY_TIERS),
        "setting_anchor_preserved": True,
        "per_character_coverage_preserved": [f"DRE:1:{dre_identity}", f"MAYA:2:{maya_identity}"],
        "first_count": 0,
        "last_count": 0,
        "reference_count": len(selected_ref_ids),
        "explanatory_tier_weights": dict(EXPLANATORY_TIER_WEIGHTS),
        "omission_detail_note": (
            "Informational only; the machine-readable omission_reason_codes field "
            "is authoritative. Four of five canonical references fit capacity 4; "
            "the lowest identity-support tier (alternate_angle) is omitted while "
            "per-character coverage and the setting anchor are preserved."
        ),
    }


def _validate_v2_shape(rows: list[dict[str, Any]]) -> None:
    """Enforce the explicitly defined generic reference shape.

    One to four canonical references: zero or more character identity rows
    (studio roles face/full_body/general/alternate_angle) plus exactly one
    setting environment anchor. Every row must be an approved canonical anchor with a
    unique identity, a non-empty target, and a role that normalizes to the
    ``reference`` provider role. Composition or temporal roles, unknown
    roles, duplicate identities, missing approvals, and missing setting
    anchors all fail closed with named codes. No Scene 002 project, scene, or
    character identity appears anywhere in this policy.
    """
    if not 1 <= len(rows) <= CAPACITY:
        raise _fail(
            "invalid_canonical_count_or_shape",
            f"runway_reference_projection/v2 requires 1 to {CAPACITY} canonical "
            f"references (observed {len(rows)}).",
            canonical_count=len(rows),
        )
    ref_ids = [_clean(row.get("ref_id")) for row in rows]
    if any(not ref_id for ref_id in ref_ids):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Every canonical reference must carry a non-empty ref_id.",
        )
    if len(set(ref_ids)) != len(ref_ids):
        raise _fail(
            "ambiguous_selection",
            "Canonical reference identities are duplicated or ambiguous.",
            canonical_ref_ids=ref_ids,
        )
    target_types = [_clean(row.get("target_type")) for row in rows]
    if any(target not in {"character", "setting"} for target in target_types):
        raise _fail(
            "invalid_canonical_count_or_shape",
            f"Canonical target types {target_types} are not all character/setting.",
            target_types=target_types,
        )
    setting_rows = [row for row in rows if _clean(row.get("target_type")) == "setting"]
    if len(setting_rows) != 1:
        raise _fail(
            "ambiguous_environment_reference" if len(setting_rows) > 1 else "missing_required_reference",
            "The generic projection requires exactly one setting environment "
            f"anchor (observed {len(setting_rows)}).",
            environment_reference_count=len(setting_rows),
        )
    for row in rows:
        studio_role = _studio_role_of(row)
        router_role = _router_role_of(row)
        if (
            router_role in {"first", "last"}
            or studio_role in _COMPOSITION_STUDIO_ROLES
            or studio_role in _TEMPORAL_STUDIO_ROLES
        ):
            raise _fail(
                "unsupported_provider_role",
                f"Canonical reference '{row.get('ref_id')}' carries composition "
                "frame semantics; generic identity/environment references must "
                "not consume first/last capacity.",
                ref_id=_clean(row.get("ref_id")),
                router_role=router_role,
                studio_role=studio_role,
            )
        if _clean(row.get("target_type")) == "setting":
            if studio_role != "environment":
                raise _fail(
                    "invalid_canonical_count_or_shape",
                    f"Setting reference '{row.get('ref_id')}' must carry the "
                    "environment studio role.",
                    ref_id=_clean(row.get("ref_id")),
                    studio_role=studio_role,
                )
        elif studio_role not in {"face", "full_body", "general", "alternate_angle"}:
            raise _fail(
                "invalid_canonical_count_or_shape",
                f"Character reference '{row.get('ref_id')}' carries unsupported "
                f"studio role '{studio_role}'; v2 supports face, full_body, "
                "general, alternate_angle.",
                ref_id=_clean(row.get("ref_id")),
                studio_role=studio_role,
            )
        try:
            provider_role = normalize_studio_role(studio_role)
        except RunwayReferenceProjectionError:
            raise
        if provider_role != "reference":
            raise _fail(
                "unsupported_provider_role",
                f"Canonical reference '{row.get('ref_id')}' does not normalize to "
                "the reference provider role.",
                ref_id=_clean(row.get("ref_id")),
                studio_role=studio_role,
            )
    for row in rows:
        if not _clean(row.get("target_id")):
            raise _fail(
                "invalid_canonical_count_or_shape",
                f"Canonical reference '{row.get('ref_id')}' carries no target identity.",
                ref_id=_clean(row.get("ref_id")),
            )
    for row in rows:
        if row.get("approval_state") != "approved" or row.get("canonical") is not True:
            raise _fail(
                "unapproved_reference",
                f"Canonical reference '{row.get('ref_id')}' is not an approved "
                "canonical anchor.",
                ref_id=_clean(row.get("ref_id")),
                approval_state=row.get("approval_state"),
                canonical=row.get("canonical"),
            )


def project_runway_v2(
    canonical_refs: list[dict[str, Any]],
    *,
    backend_root: Path | None = None,
    source_fingerprints: dict[str, str] | None = None,
    approved_reference_ids: list[str] | None = None,
    expected_binding: list[dict[str, Any]] | None = None,
    allow_local_source_uris: bool = False,
) -> dict[str, Any]:
    """Project a generic 1-to-4 canonical binding onto Router references.

    Pure: no network calls, no provider submission, no mutation of the inputs.
    The binding fits Router capacity, so every canonical reference is
    selected in frozen order and nothing is omitted. Selection is the
    enumerated rule "select all validated rows" — no weight ranking is
    consulted. All v1 safety disciplines (frozen order, byte fingerprints,
    authorization-gated materialization, digest replay) apply unchanged.
    """
    capacity = _assert_router_capacity()
    if not isinstance(canonical_refs, list):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "runway_reference_projection/v2 requires an ordered list of canonical references.",
        )
    rows = [dict(row) if isinstance(row, dict) else row for row in canonical_refs]
    if any(not isinstance(row, dict) for row in rows):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Canonical references must be objects.",
        )
    rows = [row for row in rows if isinstance(row, dict)]

    for index, row in enumerate(rows):
        _validate_uri(row.get("uri"), ref_id=_clean(row.get("ref_id")) or f"index_{index}")

    _validate_v2_shape(rows)

    if expected_binding is not None:
        identity_fields = ("ref_id", "uri", "target_type", "target_id", "canonical", "approval_state")
        actual = [
            {key: row.get(key) for key in identity_fields if key in row}
            for row in rows
        ]
        expected = [
            {key: row.get(key) for key in identity_fields if key in row}
            for row in expected_binding
        ]
        actual_roles = [_studio_role_of(row) for row in rows]
        expected_roles = [
            _studio_role_of(row) if isinstance(row, dict) else ""
            for row in expected_binding
        ]
        if actual != expected or actual_roles != expected_roles:
            raise _fail(
                "frozen_contract_or_binding_mismatch",
                "Canonical ordering or binding identity contradicts the frozen authority.",
            )

    if approved_reference_ids is not None:
        missing = [ref_id for ref_id in approved_reference_ids if ref_id not in {_clean(row.get("ref_id")) for row in rows}]
        if missing:
            raise _fail(
                "frozen_contract_or_binding_mismatch",
                "Scene coverage requires canonical references absent from the projection inputs.",
                missing_reference_ids=missing,
            )

    root = backend_root if backend_root is not None else _default_backend_root()
    recomputed = compute_source_fingerprints(rows, backend_root=root)
    if source_fingerprints is not None:
        if dict(source_fingerprints) != recomputed:
            raise _fail(
                "source_fingerprint_mismatch",
                "Supplied source fingerprints do not match recomputed canonical bytes.",
            )
    fingerprints = recomputed

    canonical_ref_ids = [_clean(row.get("ref_id")) for row in rows]
    selected_ref_ids = list(canonical_ref_ids)
    omitted_ref_ids: list[str] = []

    studio_role_map = {ref_id: _studio_role_of(row) for ref_id, row in zip(canonical_ref_ids, rows)}
    provider_role_map = {ref_id: "reference" for ref_id in selected_ref_ids}

    canonical_by_id = {ref_id: row for ref_id, row in zip(canonical_ref_ids, rows)}
    provider_uris = materialize_selected(
        canonical_by_id,
        selected_ref_ids,
        allow_local_source_uris=allow_local_source_uris,
        backend_root=root,
    )

    digest = compute_projection_digest(
        canonical_ref_ids=canonical_ref_ids,
        source_uri_fingerprints=fingerprints,
        selected_ref_ids=selected_ref_ids,
        omitted_ref_ids=omitted_ref_ids,
        studio_role_map=studio_role_map,
        provider_role_map=provider_role_map,
        policy_version=POLICY_VERSION_V2,
    )

    character_rows = [row for row in rows if _clean(row.get("target_type")) == "character"]
    coverage: list[str] = []
    for target_id in dict.fromkeys(_clean(row.get("target_id")) for row in character_rows):
        count = sum(1 for row in character_rows if _clean(row.get("target_id")) == target_id)
        coverage.append(f"{target_id}:{count}")
    retained_tiers = sorted({
        f"{role}:{EXPLANATORY_TIER_WEIGHTS[role]}"
        for role in (studio_role_map[ref_id] for ref_id in selected_ref_ids)
        if role in EXPLANATORY_TIER_WEIGHTS
    })
    return {
        "projection_policy_id": POLICY_ID,
        "projection_policy_version": POLICY_VERSION_V2,
        "capacity": capacity,
        "canonical_count": len(canonical_ref_ids),
        "selected_count": len(selected_ref_ids),
        "omitted_count": 0,
        "canonical_ref_ids": canonical_ref_ids,
        "selected_ref_ids": selected_ref_ids,
        "omitted_ref_ids": omitted_ref_ids,
        "omission_reason_codes": [OMISSION_REASON_CODE_V2],
        "studio_role_map": studio_role_map,
        "provider_role_map": provider_role_map,
        "source_uri_fingerprints": fingerprints,
        "provider_uris": provider_uris,
        "projection_digest": digest,
        "dropped_tier": None,
        "dropped_weight": None,
        "retained_identity_tiers": retained_tiers,
        "setting_anchor_preserved": True,
        "per_character_coverage_preserved": coverage,
        "first_count": 0,
        "last_count": 0,
        "reference_count": len(selected_ref_ids),
        "explanatory_tier_weights": dict(EXPLANATORY_TIER_WEIGHTS),
        "omission_detail_note": (
            "Informational only; the machine-readable omission_reason_codes field "
            "is authoritative. The binding fits Router capacity, so every "
            "validated canonical reference is selected in frozen order."
        ),
    }


def _canonical_rows_from_contract_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    references = payload.get("references")
    if not isinstance(references, list):
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Frozen generation contract carries no reference list.",
        )
    marked = [dict(row) for row in references if isinstance(row, dict) and row.get("source") == "canonical_reference_binding"]
    if marked and 1 <= len(marked) <= 5:
        return marked
    if references and 1 <= len(references) <= 5 and all(isinstance(row, dict) for row in references):
        return [dict(row) for row in references if isinstance(row, dict)]
    raise _fail(
        "invalid_canonical_count_or_shape",
        "Frozen contract does not carry 1 to 5 canonical references.",
        reference_count=len(references),
    )


# ── Phase B.9: declared projection, authorization, local preparation ─────────

# job.metadata keys that declare which projection the execution path must use.
PROJECTION_METADATA_KEY = "reference_projection"
AUTHORIZATION_METADATA_KEY = "reference_projection_authorization"

# Audit identity for the authorization gate. This is NOT a second projection
# policy: selection stays in ``project_runway_v1`` exclusively.
AUTHORIZATION_POLICY_ID = "runway_reference_projection_authorization"
AUTHORIZATION_FIELD = "authorized_environment_ref_id"


def canonical_bindings_from_contract(contract_record: Any) -> list[dict[str, Any]]:
    """Frozen-contract canonical bindings in frozen order (public wrapper).

    Reuses the existing contract reader; it never selects, filters, or
    reorders the canonical five.
    """
    from app.services.generation_contract import FrozenGenerationContract

    try:
        contract = FrozenGenerationContract.from_record(contract_record)
    except ValueError as exc:
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            f"Frozen generation contract failed verification: {exc}",
        ) from exc
    return _canonical_rows_from_contract_payload(contract.payload())


def authorize_environment_reference(
    canonical_refs: Any,
    *,
    authorized_environment_ref_id: Any,
    rejected_environment_ref_ids: Any = (),
    authorization: dict[str, Any] | None = None,
    project_id: str | None = None,
    scene_id: str | None = None,
    setting_id: str | None = None,
    current_version_id: str | None = None,
    approved_version_id: str | None = None,
    storyboard_version_id: str | None = None,
    frozen_reference_binding_sha256: str | None = None,
    frozen_binding: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Enforce the creator-authorized environment binding for one projection.

    Pure and read-only. The authorized identity must be present, the canonical
    inputs must contain exactly one environment reference, that reference must
    BE the authorized identity, and no rejected identity may appear anywhere.
    Every other outcome fails closed. This gate never chooses, replaces,
    reorders, or materializes a reference — selection stays in
    ``project_runway_v1``.
    """
    if authorization is not None:
        if not isinstance(authorization, dict):
            raise _fail("missing_reference_authority", "The creator authorization record is malformed.")
        required = {
            "project_id": project_id,
            "scene_id": scene_id,
            "setting_id": setting_id,
            "current_version_id": current_version_id,
            "approved_version_id": approved_version_id,
            "storyboard_version_id": storyboard_version_id,
            "frozen_reference_binding_sha256": frozen_reference_binding_sha256,
        }
        for field, expected in required.items():
            observed = authorization.get(field)
            if not isinstance(expected, str) or not expected or observed != expected:
                raise _fail(                "reference_authorization_mismatch",
 f"Reference authorization does not prove {field}.", field=field)
        if not isinstance(frozen_binding, list) or not frozen_binding:
            raise _fail(                "reference_authorization_mismatch",
 "Frozen reference binding is missing or malformed.")
        binding_digest = hashlib.sha256(_canonical_json(frozen_binding).encode("utf-8")).hexdigest()
        if binding_digest != frozen_reference_binding_sha256:
            raise _fail(                "reference_authorization_mismatch",
 "Frozen reference binding digest is stale or mismatched.")
        if authorization.get("authorization_policy_id") != AUTHORIZATION_POLICY_ID:
            raise _fail(                "reference_authorization_mismatch",
 "Reference authorization policy identity is missing or stale.")
        if not authorization.get("current_version_id") == authorization.get("approved_version_id") == authorization.get("storyboard_version_id"):
            raise _fail(                "reference_authorization_mismatch",
 "Reference authorization is not tied to one approved production version.")
        authorized_environment_ref_id = authorization.get("authorized_environment_ref_id")
        # Decision A1: an empty rejected enumeration is valid (it means the
        # live rejected set is exactly empty); only a non-list is malformed.
        rejected_environment_ref_ids = authorization.get("rejected_environment_ref_ids")
        if rejected_environment_ref_ids is None:
            rejected_environment_ref_ids = []
        if not isinstance(rejected_environment_ref_ids, list):
            raise _fail(                "reference_authorization_mismatch",
 "Rejected reference identities are malformed.")
        bound_setting_rows = [
            row for row in frozen_binding
            if isinstance(row, dict) and row.get("target_type") == "setting"
        ]
        if len(bound_setting_rows) != 1:
            raise _fail("ambiguous_environment_reference", "Frozen binding must contain exactly one setting reference.")
        bound = bound_setting_rows[0]
        if (
            str(bound.get("ref_id") or "") != str(authorization.get("authorized_environment_ref_id") or "")
            or str(bound.get("project_id") or "") != str(authorization.get("project_id") or "")
            or str(bound.get("target_id") or "") != str(authorization.get("setting_id") or "")
            or str(bound.get("kind") or "") != "environment"
            or bound.get("canonical") is not True
            or str(bound.get("approval_state") or "") != "approved"
        ):
            raise _fail(                "reference_authorization_mismatch",
 "Frozen binding does not contain the authorized approved environment row.")
        source_fingerprint = authorization.get("source_fingerprint")
        if not isinstance(source_fingerprint, str) or len(source_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in source_fingerprint.lower()):
            raise _fail(                "reference_authorization_mismatch",
 "Authorized source fingerprint is missing or malformed.")
    authorized = _clean(authorized_environment_ref_id)
    if not authorized:
        raise _fail(
            "missing_reference_authority",
            "The creator-authorized environment reference identity is missing.",
        )
    if not isinstance(canonical_refs, list) or not canonical_refs:
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Reference authority cannot be enforced without canonical references.",
        )
    if any(not isinstance(row, dict) for row in canonical_refs):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Canonical references must be objects.",
        )
    ref_ids = [_clean(row.get("ref_id")) for row in canonical_refs]
    if any(not ref_id for ref_id in ref_ids):
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Every canonical reference must carry a non-empty ref_id.",
        )
    if len(set(ref_ids)) != len(ref_ids):
        raise _fail(
            "ambiguous_selection",
            "Canonical reference identities are duplicated or ambiguous.",
            canonical_ref_ids=ref_ids,
        )
    rejected = {
        _clean(ref_id)
        for ref_id in (rejected_environment_ref_ids or [])
        if _clean(ref_id)
    }
    conflicting = sorted(rejected.intersection(ref_ids))
    if conflicting:
        raise _fail(
            "rejected_reference_present",
            "A rejected reference is present in the canonical projection inputs; "
            "refusing to project.",
            rejected_ref_ids=conflicting,
        )
    environment_rows = [
        dict(row) for row in canonical_refs if _studio_role_of(row) == "environment"
    ]
    if len(environment_rows) != 1:
        raise _fail(
            "ambiguous_environment_reference",
            "The projection requires exactly one environment reference "
            f"(observed {len(environment_rows)}).",
            environment_reference_count=len(environment_rows),
        )
    anchor = environment_rows[0]
    observed = _clean(anchor.get("ref_id"))
    if observed != authorized:
        raise _fail(
            "unauthorized_environment_reference",
            "The canonical environment reference is not the creator-authorized "
            "identity for this projection.",
            **{AUTHORIZATION_FIELD: authorized, "observed_environment_ref_id": observed},
        )
    if (
        str(anchor.get("target_type") or "") != "setting"
        or str(anchor.get("target_id") or "") != str((authorization or {}).get("setting_id") or anchor.get("target_id") or "")
        or str(anchor.get("approval_state") or "") != "approved"
        or anchor.get("canonical") is not True
    ):
        raise _fail("unauthorized_environment_reference", "Authorized environment reference is rejected, unapproved, noncanonical, or incorrectly scoped.")
    return anchor


def project_authorized_environment(
    canonical_refs: list[dict[str, Any]],
    *,
    policy_version: str = POLICY_VERSION,
    authorized_environment_ref_id: Any = None,
    rejected_environment_ref_ids: Any = (),
    authorization: dict[str, Any] | None = None,
    project_id: str | None = None,
    scene_id: str | None = None,
    setting_id: str | None = None,
    current_version_id: str | None = None,
    approved_version_id: str | None = None,
    storyboard_version_id: str | None = None,
    frozen_reference_binding_sha256: str | None = None,
    frozen_binding: list[dict[str, Any]] | None = None,
    backend_root: Path | None = None,
    source_fingerprints: dict[str, str] | None = None,
    expected_binding: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Authorize the creator's environment binding, then project the policy shape.

    Reuses ``project_runway_v1`` (exactly five) or ``project_runway_v2``
    (one to four) verbatim, selected by the explicit ``policy_version`` —
    there is exactly one selection policy per version. The authorized
    identity is recorded on the returned projection record for audit; it
    never enters the frozen creative contract.
    """
    anchor = authorize_environment_reference(
        canonical_refs,
        authorized_environment_ref_id=authorized_environment_ref_id,
        rejected_environment_ref_ids=rejected_environment_ref_ids,
        authorization=authorization,
        project_id=project_id,
        scene_id=scene_id,
        setting_id=setting_id,
        current_version_id=current_version_id,
        approved_version_id=approved_version_id,
        storyboard_version_id=storyboard_version_id,
        frozen_reference_binding_sha256=frozen_reference_binding_sha256,
        frozen_binding=frozen_binding,
    )
    authorized = _clean(anchor.get("ref_id"))
    root = backend_root if backend_root is not None else _default_backend_root()
    fingerprints = compute_source_fingerprints(canonical_refs, backend_root=root)
    expected_fingerprints = dict(source_fingerprints) if source_fingerprints is not None else fingerprints
    if fingerprints != expected_fingerprints:
        raise _fail("source_fingerprint_mismatch", "Authorized source fingerprints do not match the exact canonical reference bytes.")
    if authorization is not None:
        prepared = prepare_local_reference(
            anchor, backend_root=root, expected_sha256=authorization.get("source_fingerprint"),
        )
        if prepared.get("content_sha256") != authorization.get("source_fingerprint"):
            raise _fail("source_fingerprint_mismatch", "Authorized environment content differs from its frozen fingerprint.")
    if policy_version == POLICY_VERSION:
        projector = project_runway_v1
    elif policy_version == POLICY_VERSION_V2:
        projector = project_runway_v2
    else:
        raise _fail(
            "unavailable_policy_version",
            f"Unsupported projection policy version {policy_version!r}; v1 or v2 only.",
            policy_version=policy_version,
        )
    record = projector(
        canonical_refs,
        backend_root=root,
        source_fingerprints=fingerprints,
        expected_binding=expected_binding,
        allow_local_source_uris=authorization is not None,
    )
    selected_environment = [
        ref_id
        for ref_id in record["selected_ref_ids"]
        if record["studio_role_map"].get(ref_id) == "environment"
    ]
    if selected_environment != [authorized]:
        raise _fail(
            "unauthorized_environment_reference",
            "The projected selection does not carry exactly the authorized "
            "environment reference.",
            **{
                AUTHORIZATION_FIELD: authorized,
                "selected_environment_ref_ids": selected_environment,
            },
        )
    record["authorization_policy_id"] = AUTHORIZATION_POLICY_ID
    record[AUTHORIZATION_FIELD] = authorized
    if authorization is not None:
        record["authorization_binding_sha256"] = authorization.get("frozen_reference_binding_sha256")
        record["authorization_identity"] = {
            key: authorization[key] for key in (
                "project_id", "scene_id", "setting_id", "current_version_id",
                "approved_version_id", "storyboard_version_id",
                "authorized_environment_ref_id", "frozen_reference_binding_sha256", "source_fingerprint",
            )
        }
    return record


def prepare_local_reference(
    canonical_row: Any,
    *,
    backend_root: Path | None = None,
    expected_sha256: Any = None,
) -> dict[str, Any]:
    """Non-network preparation of one local canonical reference (Phase B.9).

    Resolves the exact canonical bytes and their SHA-256 through the existing
    ephemeral-upload byte resolver, so a later, separately authorized
    materialization can transport them through the existing upload design.
    Performs NO network call, mints no provider URI, and never mutates
    canonical truth (the canonical URI stays unchanged).

    When ``expected_sha256`` is supplied the resolved bytes must match it
    (``source_fingerprint_mismatch``); a mismatch is detected before any
    transport could occur.
    """
    from app.services.runway_ephemeral_upload import (
        RunwayEphemeralUploadError,
        canonical_filename,
        resolve_canonical_bytes,
        verify_source_fingerprint,
    )
    if not isinstance(canonical_row, dict):
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Local reference preparation requires a canonical reference row.",
        )
    ref_id = _clean(canonical_row.get("ref_id"))
    if not ref_id:
        raise _fail(
            "invalid_canonical_count_or_shape",
            "Local reference preparation requires a non-empty ref_id.",
        )
    uri = _validate_uri(canonical_row.get("uri"), ref_id=ref_id)
    root = backend_root if backend_root is not None else _default_backend_root()
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme.lower() in {"http", "https", "runway", "data"}:
        if hashlib.sha256(uri.encode("utf-8")).hexdigest() != expected_sha256:
            raise _fail("source_fingerprint_mismatch", "Authorized provider URI differs from its frozen fingerprint.", ref_id=ref_id)
        return {
            "ref_id": ref_id,
            "uri": uri,
            "filename": "",
            "content_sha256": expected_sha256,
            "content_bytes": 0,
            "preparation_status": "provider_addressable",
            "preparation_method": "uri_fingerprint",
            "provider_uri": uri,
            "network_calls": 0,
        }
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise _fail(
            "unsupported_canonical_uri",
            f"Canonical reference '{ref_id}' is not an explicit local asset path.",
            ref_id=ref_id,
        )
    if not isinstance(expected_sha256, str) or len(expected_sha256.strip()) != 64:
        raise _fail("source_fingerprint_mismatch", "Authorized local preparation requires the frozen SHA-256 fingerprint.", ref_id=ref_id)
    try:
        data = resolve_canonical_bytes(uri, ref_id=ref_id, backend_root=root)
    except RunwayEphemeralUploadError as exc:
        raise _fail(
            "unavailable_source_bytes" if exc.code == "missing_local_bytes" else exc.code,
            f"Canonical reference '{ref_id}' local bytes are not preparable: {exc}",
            ref_id=ref_id,
        ) from exc
    try:
        verify_source_fingerprint(data, expected_sha256, ref_id=ref_id)
        authority_sha256 = hashlib.sha256(data).hexdigest()
    except (RunwayEphemeralUploadError, ValueError) as exc:
        code = getattr(exc, "code", "source_fingerprint_mismatch")
        raise _fail(code, str(exc), ref_id=ref_id) from exc
    if authority_sha256 != expected_sha256:
        raise _fail("source_fingerprint_mismatch", "Authorized reference fingerprint does not match verified local bytes.", ref_id=ref_id)
    content_sha256 = hashlib.sha256(data).hexdigest()
    return {
        "ref_id": ref_id,
        "uri": uri,
        "filename": canonical_filename(uri),
        "content_sha256": content_sha256,
        "content_bytes": len(data),
        "preparation_status": "prepared",
        "preparation_method": "local_bytes_read_only",
        "provider_uri": None,
        "network_calls": 0,
    }


def reconstruct_projected_request(
    contract_record: Any,
    manifest: Any,
    projection_record: Any,
    *,
    backend_root: Path | None = None,
    config_id: str | None = None,
    dry_run: bool = False,
    materialized_provider_uris: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execution-side reconstruction for a projected Router video request.

    Revalidates the frozen contract, policy identity, capacity, fingerprints,
    selection, role maps, provider URIs, and digest, then delegates payload
    construction to the existing Router video request builder (whose safety
    checks are reused, not weakened). Only selected, materialized references
    reach the builder. Any mismatch fails closed without repair, reselection,
    substitution, or refreeze.
    """
    from app.services.generation_contract import FrozenGenerationContract

    if not isinstance(projection_record, dict):
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Projection record is missing or malformed.",
        )
    if projection_record.get("projection_policy_id") != POLICY_ID:
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Projection policy identity does not match runway_reference_projection.",
            projection_policy_id=projection_record.get("projection_policy_id"),
        )
    record_version = projection_record.get("projection_policy_version")
    if record_version not in (POLICY_VERSION, POLICY_VERSION_V2):
        raise _fail(
            "unavailable_policy_version",
            f"Unsupported projection policy version {record_version!r}; v1 or v2 only.",
            projection_policy_version=record_version,
        )
    if projection_record.get("capacity") != CAPACITY:
        raise _fail(
            "capacity_mismatch",
            "Projection capacity does not equal v1 capacity 4.",
            capacity=projection_record.get("capacity"),
        )
    _assert_router_capacity()

    try:
        contract = FrozenGenerationContract.from_record(contract_record)
    except ValueError as exc:
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            f"Frozen generation contract failed verification: {exc}",
        ) from exc
    payload = contract.payload()

    canonical_rows = _canonical_rows_from_contract_payload(payload)
    if [str(row.get("ref_id") or "") for row in canonical_rows] != list(projection_record.get("canonical_ref_ids") or []):
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Projection canonical identities do not match the frozen contract.",
        )

    root = backend_root if backend_root is not None else _default_backend_root()
    allow_local_sources = (
        projection_record.get("authorization_policy_id") == AUTHORIZATION_POLICY_ID
        and bool(_clean(projection_record.get(AUTHORIZATION_FIELD)))
    )
    if projection_record.get("authorization_policy_id") is not None and projection_record.get("authorization_policy_id") != AUTHORIZATION_POLICY_ID:
        raise _fail("reference_authorization_mismatch", "Projection authorization policy is unsupported or stale.")
    if allow_local_sources and (
        projection_record.get("authorization_binding_sha256")
        != (projection_record.get("authorization_identity") or {}).get("frozen_reference_binding_sha256")
    ):
        raise _fail("reference_authorization_mismatch", "Projection authorization is not tied to its frozen binding.")
    if allow_local_sources and projection_record.get(AUTHORIZATION_FIELD) != (projection_record.get("authorization_identity") or {}).get("authorized_environment_ref_id"):
        raise _fail("reference_authorization_mismatch", "Projection environment identity differs from its creator authorization.")
    replay_projector = project_runway_v1 if record_version == POLICY_VERSION else project_runway_v2
    replayed = replay_projector(
        canonical_rows,
        backend_root=root,
        source_fingerprints=dict(projection_record.get("source_uri_fingerprints") or {}),
        allow_local_source_uris=allow_local_sources,
    )

    for field in ("selected_ref_ids", "omitted_ref_ids", "studio_role_map", "provider_role_map", "provider_uris"):
        if replayed.get(field) != projection_record.get(field):
            raise _fail(
                "frozen_contract_or_binding_mismatch",
                f"Projection replay mismatch on field '{field}'; refusing to repair.",
                field=field,
            )
    if replayed.get("projection_digest") != projection_record.get("projection_digest"):
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Projection digest mismatch; refusing to repair.",
        )
    if allow_local_sources:
        authorization_identity = projection_record.get("authorization_identity")
        if (
            not isinstance(authorization_identity, dict)
            or projection_record.get(AUTHORIZATION_FIELD) != authorization_identity.get("authorized_environment_ref_id")
            or projection_record.get("authorization_binding_sha256") != authorization_identity.get("frozen_reference_binding_sha256")
        ):
            raise _fail("reference_authorization_mismatch", "Projection authorization identity failed its frozen-binding verification.")

    if not isinstance(manifest, dict) or not str(manifest.get("manifest_fingerprint") or ""):
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            "Reconstruction requires a creative manifest carrying its fingerprint.",
        )

    selected_local_ids = [
        ref_id for ref_id in replayed["selected_ref_ids"]
        if not str(replayed["provider_uris"].get(ref_id) or "").lower().startswith(_ACCEPTED_PROVIDER_SCHEMES)
    ]
    if selected_local_ids:
        if allow_local_sources and any(ref_id != projection_record.get(AUTHORIZATION_FIELD) for ref_id in selected_local_ids):
            raise _fail("reference_authorization_mismatch", "Only the creator-authorized environment may use local source bytes.")
        if not isinstance(materialized_provider_uris, dict) or set(materialized_provider_uris) != set(selected_local_ids):
            raise _fail("missing_runway_uri", "Authorized local references require ephemeral provider URIs for exactly the selected IDs.")
        for ref_id in selected_local_ids:
            provider_uri = materialized_provider_uris.get(ref_id)
            if not isinstance(provider_uri, str) or not provider_uri.startswith("runway://"):
                raise _fail("missing_runway_uri", "Local reference materialization did not produce a valid Runway URI.", ref_id=ref_id)
            replayed["provider_uris"][ref_id] = provider_uri

    builder = runway_router_provider.build_runway_router_video_request
    try:
        camera_plan = payload.get("camera_plan")
        prompt = str(payload.get("prompt") or "")
        if isinstance(camera_plan, dict) and camera_plan:
            prompt = runway_router_provider.project_frozen_camera_plan_prompt(prompt, camera_plan)
        request = builder(
            prompt,
            config_id=config_id,
            dry_run=dry_run,
            aspect_ratio=runway_router_provider.resolve_runway_router_aspect_ratio(
                payload.get("aspect_ratio")
            ),
            duration=payload.get("duration"),
            resolution=payload.get("resolution"),
            negative_prompt=str(payload.get("negative_prompt") or "") or None,
            generate_audio=payload.get("audio"),
            seed=payload.get("seed"),
            references=[
                {"uri": replayed["provider_uris"][ref_id], "role": "reference"}
                for ref_id in replayed["selected_ref_ids"]
            ],
            reference_videos=payload.get("reference_videos"),
            reference_audio=payload.get("reference_audio"),
            keyframes=payload.get("keyframes"),
            content_moderation=payload.get("content_moderation"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise _fail(
            "frozen_contract_or_binding_mismatch",
            f"Projected Router request failed existing builder verification: {exc}",
        ) from exc
    return {"projection": replayed, "runway_request": request}


def router_execution_metadata(projection_record: dict[str, Any]) -> dict[str, Any]:
    """Mirror projection fields into job.metadata["router_execution"]."""
    return {
        "projection_policy_id": projection_record.get("projection_policy_id"),
        "projection_policy_version": projection_record.get("projection_policy_version"),
        "authorization_policy_id": projection_record.get("authorization_policy_id"),
        "authorized_environment_ref_id": projection_record.get(AUTHORIZATION_FIELD),
        "authorization_binding_sha256": projection_record.get("authorization_binding_sha256"),
        "authorization_identity": dict(projection_record.get("authorization_identity") or {}),
        "capacity": projection_record.get("capacity"),
        "canonical_ref_ids": list(projection_record.get("canonical_ref_ids") or []),
        "selected_ref_ids": list(projection_record.get("selected_ref_ids") or []),
        "omitted_ref_ids": list(projection_record.get("omitted_ref_ids") or []),
        "omission_reason_codes": list(projection_record.get("omission_reason_codes") or []),
        "studio_role_map": dict(projection_record.get("studio_role_map") or {}),
        "provider_role_map": dict(projection_record.get("provider_role_map") or {}),
        "provider_uris": dict(projection_record.get("provider_uris") or {}),
        "source_uri_fingerprints": dict(projection_record.get("source_uri_fingerprints") or {}),
        "projection_digest": projection_record.get("projection_digest"),
        "dropped_tier": projection_record.get("dropped_tier"),
        "dropped_weight": projection_record.get("dropped_weight"),
        "retained_identity_tiers": list(projection_record.get("retained_identity_tiers") or []),
        "setting_anchor_preserved": projection_record.get("setting_anchor_preserved"),
        "per_character_coverage_preserved": list(
            projection_record.get("per_character_coverage_preserved") or []
        ),
    }


def record_projection_failure(code: str, message: str, **details: Any) -> dict[str, Any]:
    """Structured router_execution failure payload following existing conventions."""
    return {
        "routing_mode": "model_router",
        "reason": code,
        "error": code,
        "projection_policy_id": POLICY_ID,
        "projection_policy_version": POLICY_VERSION,
        "message": message,
        "detail": {"code": code, **details},
    }


__all__ = [
    "POLICY_ID",
    "POLICY_VERSION",
    "POLICY_VERSION_V2",
    "policy_version_for_canonical_rows",
    "project_runway_v2",
    "CAPACITY",
    "OMISSION_REASON_CODE",
    "EXPLANATORY_TIER_WEIGHTS",
    "PROJECTION_EXECUTION_FIELDS",
    "RunwayReferenceProjectionError",
    "normalize_studio_role",
    "compute_source_fingerprints",
    "materialize_uri",
    "materialize_selected",
    "compute_projection_digest",
    "project_runway_v1",
    "PROJECTION_METADATA_KEY",
    "AUTHORIZATION_METADATA_KEY",
    "AUTHORIZATION_POLICY_ID",
    "AUTHORIZATION_FIELD",
    "canonical_bindings_from_contract",
    "authorize_environment_reference",
    "project_authorized_environment",
    "prepare_local_reference",
    "reconstruct_projected_request",
    "router_execution_metadata",
    "record_projection_failure",
]
