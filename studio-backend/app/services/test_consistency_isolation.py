from app.models.consistency import (
    ConsistencyPayload,
    ConsistencyIsolationError,
    ReferenceAsset,
    to_runway,
    validate_consistency_isolation,
)


def _ref(
    ref_id: str,
    kind: str = "character_full",
    project_id: str = "proj-a",
) -> ReferenceAsset:
    return ReferenceAsset(
        ref_id=ref_id,
        kind=kind,  # type: ignore[arg-type]
        image_url=f"https://example.com/{ref_id}.jpg",
        project_id=project_id,
    )


def _payload(
    project_id: str = "proj-a",
    refs: list[ReferenceAsset] | None = None,
    mode: str = "identity_lock",
    weights: dict[str, float] | None = None,
    fallback_text: dict[str, str] | None = None,
) -> ConsistencyPayload:
    return ConsistencyPayload(
        project_id=project_id,
        refs=refs or [],
        mode=mode,  # type: ignore[arg-type]
        weights=weights or {},
        fallback_text=fallback_text or {},
    )


def test_isolation_happy_path_all_refs_match() -> None:
    payload = _payload(refs=[
        _ref("ref-1"),
        _ref("ref-2"),
    ])
    validate_consistency_isolation(payload, "proj-a")


def test_isolation_rejects_payload_level_mismatch() -> None:
    payload = _payload(project_id="proj-b", refs=[
        _ref("ref-1"),
    ])
    try:
        validate_consistency_isolation(payload, "proj-a")
        assert False, "expected ConsistencyIsolationError"
    except ConsistencyIsolationError as e:
        assert "proj-b" in str(e)
        assert "proj-a" in str(e)


def test_isolation_rejects_ref_level_mismatch() -> None:
    payload = _payload(refs=[
        _ref("ref-ok"),
        _ref("ref-bad", project_id="proj-b"),
    ])
    try:
        validate_consistency_isolation(payload, "proj-a")
        assert False, "expected ConsistencyIsolationError"
    except ConsistencyIsolationError as e:
        assert "ref-bad" in str(e)
        assert "proj-b" in str(e)


def test_isolation_empty_refs_passes() -> None:
    payload = _payload()
    validate_consistency_isolation(payload, "proj-a")


def test_isolation_rejects_first_mismatch_among_many() -> None:
    payload = _payload(refs=[
        _ref("ref-1"),
        _ref("ref-2"),
        _ref("ref-3", project_id="proj-b"),
        _ref("ref-4"),
    ])
    try:
        validate_consistency_isolation(payload, "proj-a")
        assert False, "expected ConsistencyIsolationError"
    except ConsistencyIsolationError as e:
        assert "ref-3" in str(e)


# ============================================================================
# Tests: to_runway()
# ============================================================================

def test_to_runway_selects_highest_weight_character_full() -> None:
    payload = _payload(refs=[
        _ref("face", kind="character_face"),
        _ref("full-a", project_id="proj-a"),
        _ref("full-b", project_id="proj-a"),
        _ref("env", kind="environment"),
    ], weights={"full-a": 0.3, "full-b": 0.9})
    result = to_runway(payload)
    assert result["promptImage"] == "https://example.com/full-b.jpg"


def test_to_runway_no_character_full_refs() -> None:
    payload = _payload(refs=[
        _ref("face", kind="character_face"),
        _ref("env", kind="environment"),
    ])
    result = to_runway(payload)
    assert "promptImage" not in result


def test_to_runway_empty_refs() -> None:
    result = to_runway(_payload())
    assert result == {}


def test_to_runway_only_character_full_wins_without_weight() -> None:
    payload = _payload(refs=[
        _ref("face", kind="character_face"),
        _ref("only-full"),
    ])
    result = to_runway(payload)
    assert result["promptImage"] == "https://example.com/only-full.jpg"


def test_to_runway_fallback_text_excludes_selected_ref() -> None:
    payload = _payload(
        refs=[
            _ref("face", kind="character_face"),
            _ref("full-img"),
            _ref("env", kind="environment"),
        ],
        weights={"full-img": 1.0},
        fallback_text={
            "face": "close-up facial reference",
            "full-img": "must NOT appear",
            "env": "outdoor lighting conditions",
        },
    )
    result = to_runway(payload)
    assert result["promptImage"] == "https://example.com/full-img.jpg"
    assert "must NOT appear" not in result["promptTextExtra"]
    assert "close-up facial reference" in result["promptTextExtra"]
    assert "outdoor lighting conditions" in result["promptTextExtra"]


def test_to_runway_no_fallback_text_no_extra_key() -> None:
    payload = _payload(refs=[
        _ref("full-a"),
        _ref("env", kind="environment"),
    ])
    result = to_runway(payload)
    assert "promptImage" in result
    assert "promptTextExtra" not in result
