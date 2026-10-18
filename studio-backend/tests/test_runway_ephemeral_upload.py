"""Focused tests for Runway ephemeral materialization (Phase B.5).

Reference materialization only — no generation. Every test uses injected
fakes; no test contacts Runway, requires credentials, renders, runs
preflight, runs a continuity review, or runs a Router dry run. Any real
provider call fails loudly.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.services import runway_ephemeral_upload as up
from app.services import runway_reference_projection as proj
from app.services.providers import runway_router_provider
from app.services.runway_ephemeral_upload import (
    EPHEMERAL_TTL_SECONDS,
    MATERIALIZATION_METHOD,
    RunwayEphemeralUploadError,
    compute_materialization_digest,
    is_materialization_expired,
    materialize_one,
    materialize_projection_selection,
    materialize_selected_ephemeral,
    request_upload_allocation,
    resolve_canonical_bytes,
    transmit_multipart,
    validate_materialization_record,
    validate_runway_uri,
)

DRE_ID = "char_dre_scene002"
MAYA_ID = "char_maya_scene002"
SETTING_ID = "loc_scene002"

DRE_FACE = "ref_dre_face"
MAYA_FACE = "ref_maya_face"
MAYA_GENERAL = "ref_maya_general"
MAYA_ALT = "ref_maya_alt"
ENV = "ref_scene002_env"

SELECTED = [DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV]


def _row(ref_id: str, uri: str, target_type: str, target_id: str, studio_role: str) -> dict[str, Any]:
    return {
        "ref_id": ref_id,
        "uri": uri,
        "target_type": target_type,
        "target_id": target_id,
        "studio_role": studio_role,
        "role": "reference",
        "category": studio_role,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "character_face" if target_type == "character" else "environment",
        "source": "canonical_reference_binding",
    }


def _local_five(tmp_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Five canonical rows backed by real local bytes + frozen fingerprints."""
    specs = [
        (DRE_FACE, "character", DRE_ID, "face", b"dre-face-bytes-001"),
        (MAYA_FACE, "character", MAYA_ID, "face", b"maya-face-bytes-002"),
        (MAYA_GENERAL, "character", MAYA_ID, "general", b"maya-general-bytes-003"),
        (MAYA_ALT, "character", MAYA_ID, "alternate_angle", b"maya-alt-bytes-004"),
        (ENV, "setting", SETTING_ID, "environment", b"env-bytes-005"),
    ]
    rows: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    for ref_id, target_type, target_id, role, data in specs:
        target = tmp_path / f"{ref_id}.png"
        target.write_bytes(data)
        rows.append(_row(ref_id, str(target), target_type, target_id, role))
        fingerprints[ref_id] = hashlib.sha256(data).hexdigest()
    return rows, fingerprints


class _FakeRunway:
    """Injectable stand-in for POST /v1/uploads + multipart uploadUrl."""

    def __init__(self, *, uri_prefix: str = "runway://ephemeral/alloc-A-") -> None:
        self.uri_prefix = uri_prefix
        self.allocation_calls: list[dict[str, Any]] = []
        self.multipart_calls: list[dict[str, Any]] = []
        self.fail_multipart = False

    def post_json(self, url: str, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        assert url.endswith("/v1/uploads"), f"unexpected allocation URL: {url}"
        assert api_key and "test" in api_key or api_key == "key_test_1234"
        call = {"url": url, "payload": dict(payload)}
        self.allocation_calls.append(call)
        tag = payload["filename"]
        return {
            "uploadUrl": f"https://uploads.example.test/signed/{tag}",
            "fields": {"key": f"signed-key/{tag}", "policy": "signed-policy", "signature": "signed-sig"},
            "runwayUri": f"{self.uri_prefix}{tag}",
        }

    def post_multipart(self, upload_url: str, fields: dict[str, str], file_bytes: bytes, filename: str) -> None:
        self.multipart_calls.append(
            {"upload_url": upload_url, "fields": dict(fields), "file_bytes": bytes(file_bytes), "filename": filename}
        )
        if self.fail_multipart:
            raise OSError("simulated transport failure")


@pytest.fixture()
def provider_call_guard(monkeypatch):
    """Fail loudly on any real provider network/submission attempt."""
    calls = {"network": 0, "submit": 0, "generate": 0}

    def _guarded_urlopen(*args, **kwargs):
        calls["network"] += 1
        raise AssertionError("real provider network must not be contacted")

    async def _guarded_submit(*args, **kwargs):
        calls["submit"] += 1
        raise AssertionError("provider submission must not be invoked")

    monkeypatch.setattr(runway_router_provider, "urlopen", _guarded_urlopen)
    if hasattr(runway_router_provider, "submit_runway_router_video_render"):
        monkeypatch.setattr(runway_router_provider, "submit_runway_router_video_render", _guarded_submit)
    for name in ("submit_runway_router_image_render", "submit_runway_router_audio_render"):
        if hasattr(runway_router_provider, name):
            monkeypatch.setattr(runway_router_provider, name, _guarded_submit)
    yield calls
    assert calls == {"network": 0, "submit": 0, "generate": 0}


@pytest.fixture()
def api_key(monkeypatch):
    monkeypatch.setenv("RUNWAY_API_KEY", "key_test_1234")
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    return "key_test_1234"


def _code_of(exc_info) -> str:
    return exc_info.value.code


# ── Fingerprint protection ──────────────────────────────────────────────────

def test_matching_bytes_permit_upload(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    by_id = {row["ref_id"]: row for row in rows}
    record = materialize_selected_ephemeral(
        by_id, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="proj-digest",
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert len(fake.allocation_calls) == 4
    assert len(fake.multipart_calls) == 4
    assert set(record["provider_uris"]) == set(SELECTED)


def test_changed_bytes_refuse_upload_with_zero_network_calls(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    # Canonical bytes change after the fingerprint was frozen (first selected
    # ref, so no allocation may occur at all).
    (tmp_path / f"{DRE_FACE}.png").write_bytes(b"tampered-bytes")
    fake = _FakeRunway()
    by_id = {row["ref_id"]: row for row in rows}
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_selected_ephemeral(
            by_id, list(SELECTED),
            source_fingerprints=fingerprints,
            backend_root=tmp_path,
            projection_digest="proj-digest",
            _post_json=fake.post_json,
            _post_multipart=fake.post_multipart,
        )
    assert _code_of(exc_info) == "source_fingerprint_mismatch"
    assert fake.allocation_calls == []
    assert fake.multipart_calls == []


# ── Upload allocation ───────────────────────────────────────────────────────

def test_allocation_request_shape(tmp_path, provider_call_guard, api_key) -> None:
    captured: dict[str, Any] = {}

    def _post_json(url: str, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = dict(payload)
        captured["api_key"] = api_key
        return {
            "uploadUrl": "https://uploads.example.test/signed/x",
            "fields": {"key": "k", "policy": "p"},
            "runwayUri": "runway://ephemeral/x",
        }

    allocation = request_upload_allocation("dre-face.png", _post_json=_post_json)
    assert captured["url"] == runway_router_provider.get_runway_router_base_url() + "/v1/uploads"
    assert captured["payload"] == {"filename": "dre-face.png", "type": "ephemeral"}
    assert captured["api_key"] == "key_test_1234"
    assert allocation["runway_uri"] == "runway://ephemeral/x"


def test_allocation_uses_pinned_api_version_and_existing_credential(tmp_path, provider_call_guard, api_key) -> None:
    assert runway_router_provider.RUNWAY_API_VERSION == "2024-11-06"
    seen: dict[str, Any] = {}
    real_default = up._default_post_json

    def _spy(url: str, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        seen["url"] = url
        return {"uploadUrl": "https://uploads.example.test/signed/x", "fields": {"k": "v"}, "runwayUri": "runway://ephemeral/x"}

    # Default transport builds the versioned, credentialed request; prove the
    # header construction without touching the network by inspecting source.
    import inspect

    source = inspect.getsource(real_default)
    assert "RUNWAY_API_VERSION" in source
    assert "Authorization" in source
    request_upload_allocation("f.png", _post_json=_spy)
    assert seen["url"].endswith("/v1/uploads")


# ── Multipart ───────────────────────────────────────────────────────────────

def test_multipart_transmits_exact_bytes_with_fields_preserved(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    by_id = {row["ref_id"]: row for row in rows}
    record = materialize_selected_ephemeral(
        by_id, [DRE_FACE],
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="proj-digest",
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert len(fake.multipart_calls) == 1
    call = fake.multipart_calls[0]
    original = (tmp_path / f"{DRE_FACE}.png").read_bytes()
    assert call["file_bytes"] == original
    assert hashlib.sha256(call["file_bytes"]).hexdigest() == fingerprints[DRE_FACE]
    assert call["fields"] == {"key": f"signed-key/{DRE_FACE}.png", "policy": "signed-policy", "signature": "signed-sig"}
    assert call["filename"] == f"{DRE_FACE}.png"
    # Returned allocation fields are preserved verbatim; file field is separate.
    assert "file" not in call["fields"]
    assert record["provider_uris"][DRE_FACE].startswith("runway://")


def test_no_image_transformation_occurs(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    materialize_one(
        DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
        backend_root=tmp_path, projection_digest="p",
        _post_json=fake.post_json, _post_multipart=fake.post_multipart,
    )
    assert fake.multipart_calls[0]["file_bytes"] == (tmp_path / f"{DRE_FACE}.png").read_bytes()


# ── URI validation ──────────────────────────────────────────────────────────

def test_valid_runway_uri_accepted() -> None:
    assert validate_runway_uri("runway://ephemeral/abc123", ref_id="r") == "runway://ephemeral/abc123"


@pytest.mark.parametrize(
    "uri",
    [
        "https://cdn.example.test/x.png",
        "http://cdn.example.test/x.png",
        "data:image/png;base64,AAA",
        "file:///tmp/x.png",
        "http://localhost:8000/x.png",
        "",
        "runway://",
    ],
)
def test_invalid_provider_uri_forms_fail_closed(uri: str) -> None:
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        validate_runway_uri(uri, ref_id="r")
    assert _code_of(exc_info) == "malformed_runway_uri"


# ── Omission ────────────────────────────────────────────────────────────────

def test_selected_four_uploaded_and_alternate_angle_never_uploaded(
    tmp_path, provider_call_guard, api_key
) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    by_id = {row["ref_id"]: row for row in rows}
    record = materialize_selected_ephemeral(
        by_id, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="proj-digest",
        omitted_ref_ids=[MAYA_ALT],
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert set(record["provider_uris"]) == {DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV}
    assert MAYA_ALT not in record["provider_uris"]
    uploaded_filenames = {call["filename"] for call in fake.multipart_calls}
    assert f"{MAYA_ALT}.png" not in uploaded_filenames
    assert len(fake.multipart_calls) == 4


# ── Canonical immutability ──────────────────────────────────────────────────

def test_canonical_truth_immutable_after_materialization(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    by_id = {row["ref_id"]: row for row in rows}
    before_rows = copy.deepcopy(rows)
    before_map = copy.deepcopy(by_id)
    before_order = [row["ref_id"] for row in rows]
    fake = _FakeRunway()
    materialize_selected_ephemeral(
        by_id, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="proj-digest",
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert rows == before_rows
    assert by_id == before_map
    assert [row["ref_id"] for row in rows] == before_order
    for row, original in zip(rows, before_rows):
        assert row["ref_id"] == original["ref_id"]
        assert row["uri"] == original["uri"]
        assert row["studio_role"] == original["studio_role"]
        assert row["approval_state"] == original["approval_state"]


# ── Projection digest vs materialization digest ─────────────────────────────

def _https_five() -> list[dict[str, Any]]:
    return [
        _row(DRE_FACE, "https://cdn.example.test/scene002/dre-face.png", "character", DRE_ID, "face"),
        _row(MAYA_FACE, "https://cdn.example.test/scene002/maya-face.png", "character", MAYA_ID, "face"),
        _row(MAYA_GENERAL, "https://cdn.example.test/scene002/maya-general.png", "character", MAYA_ID, "general"),
        _row(MAYA_ALT, "https://cdn.example.test/scene002/maya-alt.png", "character", MAYA_ID, "alternate_angle"),
        _row(ENV, "https://cdn.example.test/scene002/env.png", "setting", SETTING_ID, "environment"),
    ]


def test_projection_digest_ignores_ephemeral_uris(provider_call_guard) -> None:
    first = proj.project_runway_v1(_https_five())
    second = proj.project_runway_v1(_https_five())
    assert first["projection_digest"] == second["projection_digest"]
    # Even wildly different ephemeral aliases must not move the digest.
    recomputed = proj.compute_projection_digest(
        canonical_ref_ids=first["canonical_ref_ids"],
        source_uri_fingerprints=first["source_uri_fingerprints"],
        selected_ref_ids=first["selected_ref_ids"],
        omitted_ref_ids=first["omitted_ref_ids"],
        studio_role_map=first["studio_role_map"],
        provider_role_map=first["provider_role_map"],
        provider_uris={ref_id: f"runway://ephemeral/totally-different-{ref_id}" for ref_id in first["selected_ref_ids"]},
    )
    assert recomputed == first["projection_digest"]


def test_same_projection_different_allocations_give_different_materialization_digests(
    tmp_path, provider_call_guard, api_key
) -> None:
    rows, fingerprints = _local_five(tmp_path)
    by_id = {row["ref_id"]: row for row in rows}
    record_a = materialize_selected_ephemeral(
        by_id, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="stable-projection-digest",
        materialized_at="2026-10-01T00:00:00Z",
        _post_json=_FakeRunway(uri_prefix="runway://ephemeral/alloc-A-").post_json,
        _post_multipart=lambda *a, **k: None,
    )
    record_b = materialize_selected_ephemeral(
        by_id, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="stable-projection-digest",
        materialized_at="2026-10-01T01:00:00Z",
        _post_json=_FakeRunway(uri_prefix="runway://ephemeral/alloc-B-").post_json,
        _post_multipart=lambda *a, **k: None,
    )
    assert record_a["projection_digest"] == record_b["projection_digest"] == "stable-projection-digest"
    assert record_a["provider_uris"] != record_b["provider_uris"]
    assert record_a["materialization_digests"] != record_b["materialization_digests"]


def test_materialization_digest_differs_when_provider_uri_differs() -> None:
    digest_a = compute_materialization_digest(
        projection_digest="p", ref_id=DRE_FACE, source_sha256="a" * 64,
        provider_uri="runway://ephemeral/one", materialized_at="2026-10-01T00:00:00Z",
    )
    digest_b = compute_materialization_digest(
        projection_digest="p", ref_id=DRE_FACE, source_sha256="a" * 64,
        provider_uri="runway://ephemeral/two", materialized_at="2026-10-01T00:00:00Z",
    )
    assert digest_a != digest_b


# ── Provider role separation ────────────────────────────────────────────────

def test_all_materialized_roles_remain_reference(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    record = materialize_selected_ephemeral(
        {row["ref_id"]: row for row in rows}, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="p",
        provider_role_map={ref_id: "reference" for ref_id in SELECTED},
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert set(record["provider_role_map"].values()) == {"reference"}
    for forbidden in ("first", "last", "storyboard", "storyboard_last"):
        assert forbidden not in json.dumps(record["provider_role_map"])


# ── Execution metadata ──────────────────────────────────────────────────────

def test_execution_metadata_shape(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    record = materialize_selected_ephemeral(
        {row["ref_id"]: row for row in rows}, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="proj-digest",
        canonical_ref_ids=[row["ref_id"] for row in rows],
        omitted_ref_ids=[MAYA_ALT],
        omission_reason_codes=["capacity_4_of_5__lowest_identity_support_tier"],
        studio_role_map={row["ref_id"]: row["studio_role"] for row in rows},
        provider_role_map={ref_id: "reference" for ref_id in SELECTED},
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    for field in (
        "projection_policy_id", "projection_policy_version", "projection_digest",
        "canonical_ref_ids", "selected_ref_ids", "omitted_ref_ids", "omission_reason_codes",
        "studio_role_map", "provider_role_map", "source_uri_fingerprints", "provider_uris",
    ):
        assert field in record, f"missing execution field: {field}"
    assert record["materialization_method"] == MATERIALIZATION_METHOD
    assert record["materialization_status"] == "materialized"
    assert record["materialization_timestamp"]
    assert record["materialization_digests"]
    assert set(record["materialization_digests"]) == set(SELECTED)


# ── Failure coverage (every failure fails closed) ───────────────────────────

def test_failure_missing_upload_url(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)

    def _post_json(url, payload, *, api_key):
        return {"fields": {"k": "v"}, "runwayUri": "runway://ephemeral/x"}

    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
            backend_root=tmp_path, _post_json=_post_json, _post_multipart=lambda *a, **k: None,
        )
    assert _code_of(exc_info) == "missing_upload_url"


def test_failure_missing_upload_fields(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)

    def _post_json(url, payload, *, api_key):
        return {"uploadUrl": "https://uploads.example.test/signed/x", "runwayUri": "runway://ephemeral/x"}

    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
            backend_root=tmp_path, _post_json=_post_json, _post_multipart=lambda *a, **k: None,
        )
    assert _code_of(exc_info) == "missing_upload_fields"


def test_failure_missing_runway_uri(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)

    def _post_json(url, payload, *, api_key):
        return {"uploadUrl": "https://uploads.example.test/signed/x", "fields": {"k": "v"}}

    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
            backend_root=tmp_path, _post_json=_post_json, _post_multipart=lambda *a, **k: None,
        )
    assert _code_of(exc_info) == "missing_runway_uri"


def test_failure_malformed_runway_uri(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)

    def _post_json(url, payload, *, api_key):
        return {
            "uploadUrl": "https://uploads.example.test/signed/x",
            "fields": {"k": "v"},
            "runwayUri": "https://cdn.example.test/not-runway.png",
        }

    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
            backend_root=tmp_path, _post_json=_post_json, _post_multipart=lambda *a, **k: None,
        )
    assert _code_of(exc_info) == "malformed_runway_uri"


def test_failure_multipart_failure_never_retries_same_allocation(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    fake.fail_multipart = True
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
            backend_root=tmp_path, _post_json=fake.post_json, _post_multipart=fake.post_multipart,
        )
    assert _code_of(exc_info) == "multipart_upload_failed"
    # Exactly one allocation and exactly one transmission attempt: no retry.
    assert len(fake.allocation_calls) == 1
    assert len(fake.multipart_calls) == 1


def test_failure_allocation_error_fails_closed(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)

    def _post_json(url, payload, *, api_key):
        raise OSError("connection reset")

    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], fingerprints[DRE_FACE],
            backend_root=tmp_path, _post_json=_post_json, _post_multipart=lambda *a, **k: None,
        )
    assert _code_of(exc_info) == "upload_allocation_failed"


def test_failure_fingerprint_mismatch(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    tampered = dict(fingerprints)
    tampered[DRE_FACE] = "0" * 64
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_one(
            DRE_FACE, rows[0]["uri"], tampered[DRE_FACE],
            backend_root=tmp_path, _post_json=fake.post_json, _post_multipart=fake.post_multipart,
        )
    assert _code_of(exc_info) == "source_fingerprint_mismatch"
    assert fake.allocation_calls == []


def test_failure_missing_local_bytes(tmp_path, provider_call_guard, api_key) -> None:
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        resolve_canonical_bytes("/nonexistent/scene002/dre.png", ref_id=DRE_FACE, backend_root=tmp_path)
    assert _code_of(exc_info) == "missing_local_bytes"


def test_failure_unsupported_canonical_uri(provider_call_guard) -> None:
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        resolve_canonical_bytes("https://cdn.example.test/scene002/dre-face.png", ref_id=DRE_FACE)
    assert _code_of(exc_info) == "unsupported_canonical_uri"


def test_failure_invalid_selected_ref_id(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        materialize_selected_ephemeral(
            {row["ref_id"]: row for row in rows}, [DRE_FACE, "ref_unknown"],
            source_fingerprints={**fingerprints, "ref_unknown": "a" * 64},
            backend_root=tmp_path,
            _post_json=fake.post_json,
            _post_multipart=fake.post_multipart,
        )
    assert _code_of(exc_info) == "invalid_selected_ref_id"


def test_failure_missing_credential(tmp_path, provider_call_guard, monkeypatch) -> None:
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        request_upload_allocation("f.png", _post_json=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert _code_of(exc_info) == "missing_runway_api_key"


# ── Expiration ──────────────────────────────────────────────────────────────

def test_expiration_boundary() -> None:
    assert EPHEMERAL_TTL_SECONDS == 24 * 60 * 60
    now = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(hours=23)).isoformat().replace("+00:00", "Z")
    stale = (now - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
    assert is_materialization_expired(fresh, now=now) is False
    assert is_materialization_expired(stale, now=now) is True
    assert is_materialization_expired("", now=now) is True
    assert is_materialization_expired("not-a-timestamp", now=now) is True


def test_expired_materialization_record_fails_closed() -> None:
    stale = (datetime.now(timezone.utc) - timedelta(hours=25, minutes=1)).isoformat().replace("+00:00", "Z")
    record = {
        "materialization_timestamp": stale,
        "provider_uris": {DRE_FACE: "runway://ephemeral/old"},
    }
    with pytest.raises(RunwayEphemeralUploadError) as exc_info:
        validate_materialization_record(record)
    assert _code_of(exc_info) == "materialization_expired"


def test_fresh_materialization_record_validates(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    record = materialize_selected_ephemeral(
        {row["ref_id"]: row for row in rows}, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="p",
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert validate_materialization_record(record) is record


def test_repeated_materialization_keeps_projection_digest_but_renews_execution(
    tmp_path, provider_call_guard, api_key
) -> None:
    """Same canonical projection + new valid materialization = valid new execution."""
    rows, fingerprints = _local_five(tmp_path)
    by_id = {row["ref_id"]: row for row in rows}
    kwargs: dict[str, Any] = {
        "source_fingerprints": fingerprints,
        "backend_root": tmp_path,
        "projection_digest": "stable-projection-digest",
    }
    first = materialize_selected_ephemeral(
        by_id, list(SELECTED), materialized_at="2026-10-01T00:00:00Z",
        _post_json=_FakeRunway(uri_prefix="runway://ephemeral/first-").post_json,
        _post_multipart=lambda *a, **k: None, **kwargs,
    )
    second = materialize_selected_ephemeral(
        by_id, list(SELECTED), materialized_at="2026-10-01T01:00:00Z",
        _post_json=_FakeRunway(uri_prefix="runway://ephemeral/second-").post_json,
        _post_multipart=lambda *a, **k: None, **kwargs,
    )
    assert first["projection_digest"] == second["projection_digest"]
    assert first["provider_uris"] != second["provider_uris"]
    assert validate_materialization_record(first, now=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc))
    assert validate_materialization_record(second, now=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc))


# ── Gate wiring: uploader receives only the projection's selection ──────────

def test_materialize_projection_selection_consumes_v1_selection(provider_call_guard, api_key, tmp_path) -> None:
    projection = proj.project_runway_v1(_https_five())
    assert projection["selected_ref_ids"] == SELECTED
    assert projection["omitted_ref_ids"] == [MAYA_ALT]
    # Local canonical rows share the same ref identities; the uploader takes
    # exactly the projection's selected IDs and never the omitted one.
    local_rows, fingerprints = _local_five(tmp_path)
    local_projection = dict(projection)
    local_projection["source_uri_fingerprints"] = fingerprints
    fake = _FakeRunway()
    record = materialize_projection_selection(
        local_projection,
        {row["ref_id"]: row for row in local_rows},
        backend_root=tmp_path,
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    assert record["selected_ref_ids"] == SELECTED
    assert record["omitted_ref_ids"] == [MAYA_ALT]
    assert MAYA_ALT not in record["provider_uris"]
    assert len(fake.multipart_calls) == 4
    # The projection record itself is never mutated.
    assert projection["selected_ref_ids"] == SELECTED


# ── Prohibitions: no generation surface is reachable ────────────────────────

def test_uploader_module_has_no_generation_surface() -> None:
    # Structural markers only (endpoint paths, payload keys, call sites) —
    # prose mentions in the module docstring are not call sites.
    source = Path(up.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "/v1/generate/",
        "/v1/text_to_video",
        "/v1/image_to_video",
        "/v1/text_to_image",
        '"dryRun"',
        "dryRun=",
        "submit_runway",
        "submit_job",
        "continuity_review",
        "preflight(",
        "render_scene",
        "create_job",
        "RunwaySDK",
        "runway_sdk",
    ):
        assert forbidden not in source, f"generation surface reachable: {forbidden}"


def test_uploader_does_not_reference_legacy_selection() -> None:
    source = Path(up.__file__).read_text(encoding="utf-8")
    for forbidden in ("to_runway", "project_references_for_provider", "runway_capability"):
        assert forbidden not in source, f"legacy selection path referenced: {forbidden}"


def test_no_generation_endpoints_called(tmp_path, provider_call_guard, api_key) -> None:
    rows, fingerprints = _local_five(tmp_path)
    fake = _FakeRunway()
    materialize_selected_ephemeral(
        {row["ref_id"]: row for row in rows}, list(SELECTED),
        source_fingerprints=fingerprints,
        backend_root=tmp_path,
        projection_digest="p",
        _post_json=fake.post_json,
        _post_multipart=fake.post_multipart,
    )
    for call in fake.allocation_calls:
        assert "/v1/generate" not in call["url"]
        assert call["payload"].get("type") == "ephemeral"
