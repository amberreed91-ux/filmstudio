from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel


class ReferenceAsset(BaseModel):
    ref_id: str
    kind: Literal["character_face", "character_full", "environment", "style"]
    image_url: str
    embedding: list[float] | None = None
    source_shot_id: str | None = None
    project_id: str
    # Optional library provenance. Legacy confirmed assets remain valid and
    # continue to behave as project-level references when these are absent.
    target_type: Literal["character", "setting"] | None = None
    target_id: str | None = None
    category: str | None = None
    approval_state: Literal["candidate", "approved", "rejected"] = "approved"
    canonical: bool = False
    source_kind: Literal["confirmed", "uploaded", "generated"] = "confirmed"
    # Snapshot provenance carried from existing character look locks. These
    # fields are trace-only; provider projection never writes them back.
    reference_role: str | None = None
    look_id: str | None = None
    lock_status: str | None = None
    source_status: str | None = None
    review_status: str | None = None
    capture_method: str | None = None
    reliability: str | None = None
    reference_created_at: str | None = None


class CharacterReferenceLock(BaseModel):
    lock_id: str
    project_id: str
    character_id: str
    character_name: str = ""
    source_shot_id: str
    image_url: str
    lock_status: Literal["provisional", "locked", "disabled", "superseded"] = "locked"
    provider: str = ""
    capture_method: str = "thumbnail"
    # "alternate_angle" holds a second, temporally-distant frame of the same
    # character from the same clip. happyhorse-1.1-r2v accepts up to 9 reference
    # images and identity holds noticeably better with more than one view, so a
    # character is no longer represented by a single frame.
    reference_role: Literal[
        "face", "full_body", "wardrobe", "temporary_state", "general", "alternate_angle"
    ] = "general"
    # A character can look materially different across a film — a costume change,
    # an injury, rain-soaked vs dry. One canonical reference per character forces
    # all of those through a single image, so the later look fights the reference
    # on every shot. Locks are keyed by look as well as role; "default" is the
    # single-look case and stays the common path.
    look_id: str = "default"
    # Frame quality at capture (edge-energy score from _score_candidate_frame).
    # Retained so a later, cleaner frame can be recognised as an upgrade rather
    # than merely different. 0.0 means unscored — e.g. a thumbnail or remote URL.
    frame_score: float = 0.0
    reliability: Literal["low", "medium", "high"] = "medium"
    source_job_id: str = ""
    source_status: Literal["approved", "provisional", "rejected", "failed", "superseded"] = "provisional"
    review_status: Literal["approved", "unreviewed", "rejected", "ambiguous"] = "unreviewed"
    trace_notes: str = ""
    created_at: str = ""
    updated_at: str = ""


class ConsistencyPayload(BaseModel):
    project_id: str
    refs: list[ReferenceAsset]
    weights: dict[str, float] = {}
    mode: Literal["identity_lock", "style_transfer", "environment_lock"]
    fallback_text: dict[str, str] = {}
    # Internal, deterministic selection audit (why each reference was chosen,
    # why others were excluded). For debugging and reproducibility in job
    # metadata/logs — never surfaced to filmmakers and never sent to providers.
    selection_audit: list[dict[str, Any]] | None = None


class ConsistencyIsolationError(ValueError):
    """Raised when a ReferenceAsset's project_id doesn't match the expected project."""
    pass


def validate_consistency_isolation(
    payload: ConsistencyPayload,
    expected_project_id: str,
) -> None:
    """Validate that all ReferenceAssets in the payload belong to the expected project.

    Raises ConsistencyIsolationError if the payload-level project_id or any
    individual ref's project_id does not match expected_project_id.
    This is the render-layer equivalent of the get_character project isolation
    check at the data layer (storage.py get_character).
    """
    if payload.project_id != expected_project_id:
        raise ConsistencyIsolationError(
            f"ConsistencyPayload project_id={payload.project_id!r} "
            f"does not match expected project_id={expected_project_id!r}"
        )
    for ref in payload.refs:
        if ref.project_id != expected_project_id:
            raise ConsistencyIsolationError(
                f"ReferenceAsset ref_id={ref.ref_id!r} kind={ref.kind!r} "
                f"has project_id={ref.project_id!r} which does not match "
                f"expected project_id={expected_project_id!r}"
            )


def to_runway(payload: ConsistencyPayload) -> dict[str, Any]:
    """Convert a ConsistencyPayload to Runway API request-body additions.

    Returns a dict with keys that mirror Runway's /v1/image_to_video payload
    shape, confirmed from RunwayAdapter.submit_job (adapters/__init__.py):
      - "promptImage": str | absent — the init-image URL from the highest-weight
        character_full ref. Absent when no character_full refs exist.
      - "promptTextExtra": str | absent — joined fallback_text values from all
        refs *except* the selected init-image ref, folded into a character_state
        string using "; " separator (matching resolve_character_block() in
        character_staging_service.py).

    Edge cases:
      - No character_full refs → no "promptImage" key (caller must use
        /v1/text_to_video instead of image_to_video).
      - Selected ref has no matching weight → defaults to 0.0, which still
        wins if it's the only character_full ref.
      - No fallback_text entries for remaining refs → no "promptTextExtra" key.
    """
    char_full = [ref for ref in payload.refs if ref.kind == "character_full"]

    selected = (
        max(char_full, key=lambda ref: payload.weights.get(ref.ref_id, 0.0))
        if char_full else None
    )

    result: dict[str, Any] = {}

    if selected is not None:
        result["promptImage"] = selected.image_url

    other_refs = [ref for ref in payload.refs if ref is not selected]
    extra_parts = [
        payload.fallback_text[ref.ref_id]
        for ref in other_refs
        if ref.ref_id in payload.fallback_text
    ]
    if extra_parts:
        result["promptTextExtra"] = "; ".join(extra_parts)

    return result
