"""Read the explicit appearance approval carried by a production character."""
from __future__ import annotations

import json
from typing import Any


APPEARANCE_FIELDS = frozenset({
    "name", "age", "look", "visual_prompt_summary", "appearance_core",
    "appearance_notes", "description_status", "identity_core_json", "default_appearance_json",
})


def continuity_document(character: dict[str, Any]) -> dict[str, Any]:
    raw = character.get("continuity_state_json")
    if not raw:
        return {}
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict):
        raise ValueError("Character continuity state must be an object")
    return value


def appearance_approval(character: dict[str, Any]) -> dict[str, Any]:
    value = continuity_document(character).get("appearance_approval", {})
    if not isinstance(value, dict):
        raise ValueError("Character appearance approval must be an object")
    return value


def appearance_description(character: dict[str, Any]) -> str:
    approval = appearance_approval(character)
    if approval.get("status") == "locked":
        return str(approval["description"])
    pieces = [character.get("age"), character.get("look") or character.get("appearance_core"), character.get("visual_prompt_summary")]
    return "; ".join(dict.fromkeys(str(piece).strip() for piece in pieces if str(piece or "").strip()))


def approved_reference_rows(character: dict[str, Any]) -> list[dict[str, Any]] | None:
    """None preserves legacy behavior; an explicit draft deliberately has no anchors."""
    from app.models.consistency import CharacterReferenceLock

    approval = appearance_approval(character)
    if not approval:
        return None
    if approval.get("status") != "locked":
        return []
    return [CharacterReferenceLock(
        lock_id=f"lookapproval:{character['id']}:{approval['version']}:{role}",
        project_id=character["project_id"], character_id=character["id"], character_name=character.get("name", ""),
        source_shot_id="character-look-approval", image_url=approval[field],
        reference_role=role, capture_method="director_override", lock_status="locked",
        reliability="high", source_status="approved", review_status="approved",
        created_at=approval["approved_at"], updated_at=approval["approved_at"],
        trace_notes=f"Creator approved appearance version {approval['version']}",
    ).model_dump(mode="json") for field, role in (("face_image_url", "face"), ("body_image_url", "full_body")) if approval.get(field)]
