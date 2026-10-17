"""Runway ephemeral reference materialization (Phase B.5).

Narrow, creator-authorized byte transport for canonical reference material
only. This module NEVER generates, renders, runs preflight, runs continuity
review, or performs a Router dry run. It implements exactly one flow:

1. ``POST {base}/v1/uploads`` with ``{"filename": ..., "type": "ephemeral"}``
   using the existing Runway credential and pinned API version.
2. Transmit the EXACT canonical bytes (SHA-256 verified against the frozen
   ``source_sha256`` BEFORE any network call) to the returned multipart
   ``uploadUrl`` using the returned ``fields`` verbatim plus one ``file``
   field.
3. Record the returned ``runway://`` URI as execution metadata only.

Discipline enforced here:

- The projector (``runway_reference_projection.project_runway_v1``) remains
  pure and owns selection. This module never chooses references; it receives
  only already-selected reference IDs and uploads exactly those.
- Canonical truth is never mutated: ``ref_id``, ``uri``, ``studio_role``,
  ``approval_state``, and ordering are read-only inputs. The canonical URI
  stays the original local URI; the ``runway://`` URI exists only in the
  returned execution record.
- ``projection_digest`` (deterministic, canonical-only) is an INPUT to this
  module, never recomputed from ephemeral URIs. Each upload produces its own
  execution-specific ``materialization_digest``.
- A failed ``/v1/uploads`` allocation is NEVER retried with the same
  allocation. Upload failure yields a structured failure and stops; a fresh
  allocation is required for any later attempt.
- Provider URIs are temporary (documented 24-hour validity). Expired
  materializations fail closed; re-materialization creates a NEW execution
  record and never alters the canonical projection.
- No Runway SDK, no new credential variable, no public asset server, no
  proxy, no object-storage infrastructure, no generation endpoint.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from app.services.providers import runway_router_provider

MATERIALIZATION_METHOD = "runway_ephemeral_upload"
MATERIALIZATION_STATUS_MATERIALIZED = "materialized"

UPLOAD_PATH = "/v1/uploads"
UPLOAD_TYPE_EPHEMERAL = "ephemeral"

# Documented validity window for Runway ephemeral uploads.
EPHEMERAL_TTL_SECONDS = 24 * 60 * 60

_MAX_URI_LENGTH = 2048
_ACCEPTED_PROVIDER_SCHEMES = ("https://", "runway://", "data:image/")


class RunwayEphemeralUploadError(ValueError):
    """Structured, fail-closed materialization failure with a machine code."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.detail: dict[str, Any] = {"code": code, **details}


def _fail(code: str, message: str, **details: Any) -> RunwayEphemeralUploadError:
    return RunwayEphemeralUploadError(code, message, **details)


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _default_backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ── URI validation ──────────────────────────────────────────────────────────

def validate_runway_uri(uri: Any, *, ref_id: str = "") -> str:
    """Accept only the Router's ``runway://`` execution-alias form.

    ``https://``, ``http://``, ``data:image/``, ``file://``, localhost, and
    every other form fail closed. Nothing is coerced.
    """
    value = uri if isinstance(uri, str) else ""
    label = ref_id or "unknown"
    if not value or value != value.strip() or len(value) > _MAX_URI_LENGTH:
        raise _fail(
            "malformed_runway_uri",
            f"Materialized provider URI for '{label}' is missing or malformed; refusing to coerce.",
            ref_id=label,
        )
    if not value.startswith("runway://") or len(value) <= len("runway://"):
        raise _fail(
            "malformed_runway_uri",
            f"Materialized provider URI for '{label}' is not a runway:// execution alias; refusing to coerce.",
            ref_id=label,
            scheme=value.split(":", 1)[0][:24] if ":" in value else "",
        )
    return value


# ── Canonical byte resolution ───────────────────────────────────────────────

def _candidate_paths(uri: str, backend_root: Path) -> list[Path]:
    """Resolve only the exact configured mount URL or a backend-relative path."""
    parsed = urlparse(uri)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise _fail("unsupported_canonical_uri", "Canonical URI uses an unsupported local form.")
    decoded_path = unquote(parsed.path or uri)
    if "\\" in decoded_path or "\x00" in decoded_path:
        raise _fail("unsupported_canonical_uri", "Canonical URI contains unsupported path characters.")
    mounted_roots = {
        "/previs-assets": backend_root / "outputs" / "previs",
        "/outputs": backend_root / "outputs",
        "/static": backend_root / "static",
    }
    for mount, mount_root in mounted_roots.items():
        if decoded_path == mount or decoded_path.startswith(mount + "/"):
            relative = decoded_path[len(mount):].lstrip("/")
            relative_path = Path(relative)
            if not relative or relative_path.is_absolute() or ".." in relative_path.parts:
                raise _fail("unsupported_canonical_uri", "Mounted canonical path traversal is not permitted.")
            root = mount_root.resolve()
            candidate = root / relative_path
            try:
                candidate.resolve().relative_to(root)
            except ValueError as exc:
                raise _fail("unsupported_canonical_uri", "Mounted canonical asset resolves outside its configured root.") from exc
            return [candidate]

    raw = Path(decoded_path)
    root = backend_root.resolve()
    if not decoded_path or ".." in raw.parts:
        raise _fail("unsupported_canonical_uri", "Canonical path traversal is not permitted.")
    if raw.is_absolute():
        candidate = raw
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            # Legacy /nonexistent/... locators remain a missing-file case; an
            # existing absolute file outside the backend tree is never opened.
            if candidate.exists():
                raise _fail("unsupported_canonical_uri", "Absolute canonical path resolves outside the backend root.")
        return [candidate]
    candidate = root / raw
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise _fail("unsupported_canonical_uri", "Relative canonical path resolves outside the backend root.") from exc
    return [candidate]




def resolve_canonical_bytes(uri: Any, *, ref_id: str = "", backend_root: Path | None = None) -> bytes:
    """Read canonical bytes from an explicit backend asset mount.

    Remote/provider forms and unmounted absolute paths are never opened.
    Missing files and unsafe paths fail closed with structured errors.
    """
    label = ref_id or "unknown"
    value = uri if isinstance(uri, str) else ""
    if not value or value != value.strip():
        raise _fail(
            "missing_local_bytes",
            f"Canonical reference '{label}' carries no usable local URI.",
            ref_id=label,
        )
    if len(value) > _MAX_URI_LENGTH or "\\\\" in value or "\x00" in value:
        raise _fail("unsupported_canonical_uri", f"Canonical reference '{label}' URI is malformed.", ref_id=label)
    if value.lower().startswith(_ACCEPTED_PROVIDER_SCHEMES):
        raise _fail(
            "unsupported_canonical_uri",
            f"Canonical reference '{label}' is already provider-addressable; "
            "the ephemeral uploader transports local canonical bytes only.",
            ref_id=label,
        )
    root = backend_root if backend_root is not None else _default_backend_root()
    candidates = _candidate_paths(value, root)
    target = next((candidate for candidate in candidates if candidate.is_file()), None)
    if target is None:
        raise _fail(
            "missing_local_bytes",
            f"Canonical reference '{label}' bytes are not available locally; refusing to substitute.",
            ref_id=label,
        )
    data = target.read_bytes()
    if not data:
        raise _fail(
            "missing_local_bytes",
            f"Canonical reference '{label}' resolves to empty bytes; refusing to upload.",
            ref_id=label,
        )
    return data


def canonical_filename(uri: str) -> str:
    """Derive the upload ``filename`` from the canonical local path basename."""
    parsed = urlparse(uri)
    name = Path(parsed.path if parsed.scheme == "file" else uri).name.strip()
    if not name:
        raise _fail("missing_local_bytes", "Canonical URI yields no filename for the upload allocation.")
    return name


def verify_source_fingerprint(data: bytes, source_sha256: Any, *, ref_id: str = "") -> str:
    """Require transmitted bytes to equal the frozen authority fingerprint.

    Called BEFORE any network call. Mismatch fails closed and no upload is
    attempted. Fingerprints are never recomputed or silently replaced here.
    """
    label = ref_id or "unknown"
    expected = source_sha256.strip().lower() if isinstance(source_sha256, str) else ""
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise _fail(
            "source_fingerprint_mismatch",
            f"Canonical reference '{label}' carries no valid frozen source_sha256; refusing to upload.",
            ref_id=label,
        )
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise _fail(
            "source_fingerprint_mismatch",
            f"Canonical reference '{label}' bytes differ from the frozen source_sha256; refusing to upload.",
            ref_id=label,
        )
    return actual


# ── Digests ─────────────────────────────────────────────────────────────────

def compute_materialization_digest(
    *,
    projection_digest: str,
    ref_id: str,
    source_sha256: str,
    provider_uri: str,
    method: str = MATERIALIZATION_METHOD,
    materialized_at: str,
) -> str:
    """Execution-specific digest for one ephemeral provider allocation.

    Incorporates the deterministic ``projection_digest`` plus the allocation's
    own identity (``ref_id``, ``source_sha256``, ``provider_uri``, ``method``,
    timestamp). The same canonical projection re-materialized later keeps its
    ``projection_digest`` but yields a different ``materialization_digest``
    whenever the ephemeral allocation differs.
    """
    canonical = {
        "projection_digest": projection_digest,
        "ref_id": ref_id,
        "source_sha256": source_sha256,
        "provider_uri": provider_uri,
        "materialization_method": method,
        "materialized_at": materialized_at,
    }
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()


# ── Upload allocation: POST /v1/uploads ──────────────────────────────────────

def _default_post_json(url: str, payload: dict[str, Any], *, api_key: str) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Runway-Version": runway_router_provider.RUNWAY_API_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = runway_router_provider.get_runway_router_timeout_seconds()
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        raw = response.read().decode("utf-8")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Runway upload allocation returned a non-JSON response") from exc


def request_upload_allocation(
    filename: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    _post_json: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Obtain one ephemeral upload allocation via ``POST /v1/uploads``.

    Returns ``{"upload_url": ..., "fields": ..., "runway_uri": ...}`` after
    strict validation. Any missing/malformed field fails closed. The
    credential value never appears in errors or logs.
    """
    clean_name = _clean(filename)
    if not clean_name:
        raise _fail("missing_local_bytes", "Upload allocation requires a canonical filename.")
    key = (_clean(api_key) if api_key is not None
           else runway_router_provider.get_runway_router_api_key())
    if not key:
        raise _fail(
            "missing_runway_api_key",
            "Runway ephemeral upload requires the existing Runway credential; none is configured.",
        )
    base = (_clean(base_url) if base_url is not None
            else runway_router_provider.get_runway_router_base_url())
    if not base:
        raise _fail("upload_allocation_failed", "Runway API base URL is not configured.")
    url = base.rstrip("/") + UPLOAD_PATH
    payload = {"filename": clean_name, "type": UPLOAD_TYPE_EPHEMERAL}
    post = _post_json if _post_json is not None else _default_post_json
    try:
        response = post(url, payload, api_key=key)
    except RunwayEphemeralUploadError:
        raise
    except Exception as exc:  # noqa: BLE001 — allocation failure is fail-closed
        raise _fail(
            "upload_allocation_failed",
            "Runway upload allocation request failed; refusing to retry with this allocation.",
        ) from exc
    if not isinstance(response, dict):
        raise _fail(
            "upload_allocation_failed",
            "Runway upload allocation returned a malformed (non-object) response.",
        )
    upload_url = response.get("uploadUrl")
    fields = response.get("fields")
    runway_uri = response.get("runwayUri")
    if not isinstance(upload_url, str) or not upload_url.strip() or not upload_url.startswith("https://"):
        raise _fail(
            "missing_upload_url",
            "Runway upload allocation provided no usable uploadUrl; failing closed without fallback.",
        )
    if not isinstance(fields, dict) or not fields or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in fields.items()
    ):
        raise _fail(
            "missing_upload_fields",
            "Runway upload allocation provided no usable multipart fields; failing closed without fallback.",
        )
    if not isinstance(runway_uri, str) or not runway_uri.strip():
        raise _fail(
            "missing_runway_uri",
            "Runway upload allocation provided no provider URI; failing closed without fallback.",
        )
    validate_runway_uri(runway_uri)
    return {"upload_url": upload_url, "fields": dict(fields), "runway_uri": runway_uri}


# ── Multipart transmission ──────────────────────────────────────────────────

def _default_post_multipart(
    upload_url: str,
    fields: dict[str, str],
    file_bytes: bytes,
    filename: str,
) -> None:
    """Transmit exact bytes to the signed ``uploadUrl`` (no auth headers).

    Signed upload URLs carry their own authorization in ``fields``; Studio
    credentials are never attached to this request. Exactly one attempt is
    made — failures propagate so the caller can fail closed.
    """
    boundary = f"----StudioEphemeral{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
        + file_bytes
        + b"\r\n"
    )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    request = Request(
        upload_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    timeout = runway_router_provider.get_runway_router_timeout_seconds()
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        response.read()


def transmit_multipart(
    upload_url: str,
    fields: dict[str, str],
    file_bytes: bytes,
    filename: str,
    *,
    _post_multipart: Callable[..., Any] | None = None,
) -> None:
    """Perform the single permitted multipart transmission for an allocation.

    NEVER retried with the same allocation: any transport failure raises
    ``multipart_upload_failed`` and the caller must stop (a fresh
    ``POST /v1/uploads`` allocation is required for any later attempt).
    """
    if not file_bytes:
        raise _fail("missing_local_bytes", "Multipart transmission requires non-empty canonical bytes.")
    post = _post_multipart if _post_multipart is not None else _default_post_multipart
    try:
        post(upload_url, dict(fields), bytes(file_bytes), filename)
    except RunwayEphemeralUploadError:
        raise
    except Exception as exc:  # noqa: BLE001 — transport failure is fail-closed
        raise _fail(
            "multipart_upload_failed",
            "Multipart upload to the allocated uploadUrl failed; the allocation "
            "must not be retried — obtain a fresh allocation for any later attempt.",
        ) from exc


# ── Per-reference materialization ────────────────────────────────────────────

def materialize_one(
    ref_id: str,
    uri: Any,
    source_sha256: Any,
    *,
    backend_root: Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    projection_digest: str = "",
    materialized_at: str | None = None,
    _post_json: Callable[..., Any] | None = None,
    _post_multipart: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Upload one selected canonical reference and return its execution entry.

    Order of operations is load-bearing: resolve bytes → verify fingerprint
    → request allocation → transmit exact bytes → validate ``runway://`` URI.
    Zero network calls occur when the fingerprint mismatches.
    """
    label = _clean(ref_id)
    if not label:
        raise _fail("invalid_selected_ref_id", "Materialization requires a non-empty selected reference ID.")
    data = resolve_canonical_bytes(uri, ref_id=label, backend_root=backend_root)
    fingerprint = verify_source_fingerprint(data, source_sha256, ref_id=label)
    filename = canonical_filename(uri if isinstance(uri, str) else "")
    allocation = request_upload_allocation(
        filename, api_key=api_key, base_url=base_url, _post_json=_post_json
    )
    transmit_multipart(
        allocation["upload_url"],
        allocation["fields"],
        data,
        filename,
        _post_multipart=_post_multipart,
    )
    provider_uri = validate_runway_uri(allocation["runway_uri"], ref_id=label)
    timestamp = materialized_at or _isoformat(_utc_now())
    digest = compute_materialization_digest(
        projection_digest=projection_digest,
        ref_id=label,
        source_sha256=fingerprint,
        provider_uri=provider_uri,
        materialized_at=timestamp,
    )
    return {
        "ref_id": label,
        "provider_uri": provider_uri,
        "source_sha256": fingerprint,
        "filename": filename,
        "materialization_method": MATERIALIZATION_METHOD,
        "materialization_status": MATERIALIZATION_STATUS_MATERIALIZED,
        "materialized_at": timestamp,
        "expires_at": _isoformat(_parse_timestamp(timestamp) + timedelta(seconds=EPHEMERAL_TTL_SECONDS))
        if _parse_timestamp(timestamp) is not None else "",
        "materialization_digest": digest,
    }


# ── Gated batch materialization ─────────────────────────────────────────────

def materialize_selected_ephemeral(
    canonical_by_id: dict[str, dict[str, Any]],
    selected_ref_ids: list[str],
    *,
    source_fingerprints: dict[str, str],
    backend_root: Path | None = None,
    projection_digest: str = "",
    projection_policy_id: str = "runway_reference_projection",
    projection_policy_version: str = "v1",
    canonical_ref_ids: list[str] | None = None,
    omitted_ref_ids: list[str] | None = None,
    omission_reason_codes: list[str] | None = None,
    studio_role_map: dict[str, str] | None = None,
    provider_role_map: dict[str, str] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    materialized_at: str | None = None,
    _post_json: Callable[..., Any] | None = None,
    _post_multipart: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Materialize exactly the given selected references via ephemeral upload.

    This function NEVER selects: ``selected_ref_ids`` must be the exact
    selection already produced by ``project_runway_v1`` (the
    ``materialize_selected`` gate). Every selected ID must resolve to a
    canonical row and a frozen fingerprint; anything else fails closed.
    Canonical rows are read-only and never mutated.
    """
    if not isinstance(canonical_by_id, dict) or not isinstance(selected_ref_ids, list):
        raise _fail("invalid_selected_ref_id", "Materialization requires a canonical mapping and a selected ID list.")
    if not selected_ref_ids or any(not _clean(ref_id) for ref_id in selected_ref_ids):
        raise _fail("invalid_selected_ref_id", "Materialization requires non-empty selected reference IDs.")
    if len(set(selected_ref_ids)) != len(selected_ref_ids):
        raise _fail("invalid_selected_ref_id", "Selected reference IDs contain duplicates; refusing to upload.")
    if not isinstance(source_fingerprints, dict):
        raise _fail("source_fingerprint_mismatch", "Materialization requires the frozen source fingerprints.")

    entries: dict[str, dict[str, Any]] = {}
    provider_uris: dict[str, str] = {}
    digests: dict[str, str] = {}
    timestamp = materialized_at or _isoformat(_utc_now())
    for ref_id in selected_ref_ids:
        row = canonical_by_id.get(ref_id)
        if not isinstance(row, dict):
            raise _fail(
                "invalid_selected_ref_id",
                f"Selected reference '{ref_id}' cannot be resolved to a canonical row.",
                ref_id=ref_id,
            )
        expected = source_fingerprints.get(ref_id)
        if not isinstance(expected, str) or not expected.strip():
            raise _fail(
                "source_fingerprint_mismatch",
                f"Selected reference '{ref_id}' carries no frozen source fingerprint.",
                ref_id=ref_id,
            )
        entry = materialize_one(
            ref_id,
            row.get("uri"),
            expected,
            backend_root=backend_root,
            api_key=api_key,
            base_url=base_url,
            projection_digest=projection_digest,
            materialized_at=timestamp,
            _post_json=_post_json,
            _post_multipart=_post_multipart,
        )
        entries[ref_id] = entry
        provider_uris[ref_id] = entry["provider_uri"]
        digests[ref_id] = entry["materialization_digest"]

    canonical_ids = list(canonical_ref_ids) if canonical_ref_ids is not None else list(canonical_by_id.keys())
    omitted = list(omitted_ref_ids) if omitted_ref_ids is not None else [
        ref_id for ref_id in canonical_ids if ref_id not in set(selected_ref_ids)
    ]
    for ref_id in omitted:
        if ref_id in provider_uris:
            raise _fail(
                "invalid_selected_ref_id",
                f"Omitted reference '{ref_id}' must never be materialized.",
                ref_id=ref_id,
            )
    parsed_ts = _parse_timestamp(timestamp)
    return {
        "projection_policy_id": projection_policy_id,
        "projection_policy_version": projection_policy_version,
        "projection_digest": projection_digest,
        "canonical_ref_ids": canonical_ids,
        "selected_ref_ids": list(selected_ref_ids),
        "omitted_ref_ids": omitted,
        "omission_reason_codes": list(omission_reason_codes) if omission_reason_codes is not None else [],
        "studio_role_map": dict(studio_role_map) if studio_role_map is not None else {},
        "provider_role_map": dict(provider_role_map) if provider_role_map is not None else {},
        "source_uri_fingerprints": {ref_id: source_fingerprints[ref_id] for ref_id in selected_ref_ids},
        "provider_uris": provider_uris,
        "materialization_method": MATERIALIZATION_METHOD,
        "materialization_status": MATERIALIZATION_STATUS_MATERIALIZED,
        "materialization_timestamp": timestamp,
        "materialization_expires_at": _isoformat(parsed_ts + timedelta(seconds=EPHEMERAL_TTL_SECONDS))
        if parsed_ts is not None else "",
        "materialization_digests": digests,
        "materialization_entries": entries,
    }


def materialize_projection_selection(
    projection_record: dict[str, Any],
    canonical_by_id: dict[str, dict[str, Any]],
    *,
    backend_root: Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    materialized_at: str | None = None,
    _post_json: Callable[..., Any] | None = None,
    _post_multipart: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Upload exactly the selection carried by a ``project_runway_v1`` record.

    The projection record owns selection, role maps, fingerprints, and the
    deterministic ``projection_digest``; this function transports bytes and
    records execution metadata. The projection record itself is never mutated.
    """
    if not isinstance(projection_record, dict):
        raise _fail("invalid_selected_ref_id", "Materialization requires a projection record.")
    selected = projection_record.get("selected_ref_ids")
    if not isinstance(selected, list) or not selected:
        raise _fail("invalid_selected_ref_id", "Projection record carries no selected reference IDs.")
    fingerprints = projection_record.get("source_uri_fingerprints")
    if not isinstance(fingerprints, dict):
        raise _fail("source_fingerprint_mismatch", "Projection record carries no source fingerprints.")
    return materialize_selected_ephemeral(
        canonical_by_id,
        list(selected),
        source_fingerprints=dict(fingerprints),
        backend_root=backend_root,
        projection_digest=str(projection_record.get("projection_digest") or ""),
        projection_policy_id=str(projection_record.get("projection_policy_id") or "runway_reference_projection"),
        projection_policy_version=str(projection_record.get("projection_policy_version") or "v1"),
        canonical_ref_ids=list(projection_record.get("canonical_ref_ids") or []),
        omitted_ref_ids=list(projection_record.get("omitted_ref_ids") or []),
        omission_reason_codes=list(projection_record.get("omission_reason_codes") or []),
        studio_role_map=dict(projection_record.get("studio_role_map") or {}),
        provider_role_map=dict(projection_record.get("provider_role_map") or {}),
        api_key=api_key,
        base_url=base_url,
        materialized_at=materialized_at,
        _post_json=_post_json,
        _post_multipart=_post_multipart,
    )


# ── Expiration ──────────────────────────────────────────────────────────────

def is_materialization_expired(materialization_timestamp: Any, *, now: datetime | None = None) -> bool:
    """True when the 24-hour ephemeral window has elapsed (fail closed).

    Unparseable or missing timestamps are treated as expired.
    """
    parsed = _parse_timestamp(materialization_timestamp)
    if parsed is None:
        return True
    current = now.astimezone(timezone.utc) if isinstance(now, datetime) else _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current - parsed).total_seconds() >= EPHEMERAL_TTL_SECONDS


def validate_materialization_record(record: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Fail closed on expired (or timestamp-less) materialization records."""
    if not isinstance(record, dict):
        raise _fail("materialization_expired", "Materialization record is missing or malformed.")
    timestamp = record.get("materialization_timestamp")
    if is_materialization_expired(timestamp, now=now):
        raise _fail(
            "materialization_expired",
            "Ephemeral provider URIs exceeded the 24-hour validity window; "
            "perform a fresh authorized materialization instead of reusing them.",
            materialization_timestamp=timestamp,
        )
    provider_uris = record.get("provider_uris")
    if not isinstance(provider_uris, dict) or not provider_uris:
        raise _fail("missing_runway_uri", "Materialization record carries no provider URIs.")
    for ref_id, uri in provider_uris.items():
        validate_runway_uri(uri, ref_id=str(ref_id))
    return record


__all__ = [
    "MATERIALIZATION_METHOD",
    "MATERIALIZATION_STATUS_MATERIALIZED",
    "UPLOAD_PATH",
    "UPLOAD_TYPE_EPHEMERAL",
    "EPHEMERAL_TTL_SECONDS",
    "RunwayEphemeralUploadError",
    "validate_runway_uri",
    "resolve_canonical_bytes",
    "canonical_filename",
    "verify_source_fingerprint",
    "compute_materialization_digest",
    "request_upload_allocation",
    "transmit_multipart",
    "materialize_one",
    "materialize_selected_ephemeral",
    "materialize_projection_selection",
    "is_materialization_expired",
    "validate_materialization_record",
]


def _redact_for_log(text: Any) -> str:  # pragma: no cover — defensive helper
    redacted = str(text or "")
    for env_var in ("RUNWAY_API_KEY", "RUNWAYML_API_SECRET"):
        secret = os.getenv(env_var, "").strip()
        if secret and secret in redacted:
            redacted = redacted.replace(secret, f"[REDACTED:{env_var}]")
    return redacted
