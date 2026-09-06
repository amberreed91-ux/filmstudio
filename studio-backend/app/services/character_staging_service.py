"""
Character Staging Service — Phase 1 (schema + dual-read, zero behavior change).

Implements resolve_character_prompt() per CHARACTER_VPS_SCENE_CONTAMINATION §4.1.

Resolution order:
1. character_stagings row for (character_id, scene_id, shot_id) → appearance_override or staging_prompt
2. character_stagings row for (character_id, scene_id, NULL shot_id) → appearance_override or staging_prompt
3. Legacy fallback: "{name}: {visual_prompt_summary}" — byte-for-byte identical
   to today's injection in render.py / routes/__init__.py.

Phase 1 invariant: when description_status='legacy' and appearance_core IS NULL
(the current state of all 6 characters), the legacy fallback path MUST return
exactly what the current visual_prompt_summary injection produces. This is the
zero-render-regression guarantee.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from app.utils.character_appearance import appearance_approval, appearance_description

logger = logging.getLogger("studio-character-staging")


def _resolve_base_appearance(character: dict[str, Any]) -> str:
    """Resolve the base appearance string for a character.

    Returns the canonical appearance description (without name prefix) by
    checking the migrated path first, then falling back to the legacy
    visual_prompt_summary.

    This is extracted so the staging branch can combine base appearance
    with a scene-specific staging_prompt.
    """
    name = str(character.get("name") or "").strip()
    if appearance_approval(character).get("status") == "locked":
        return f"{name}: {appearance_description(character)}"

    # ── Migrated path ──────────────────────────────────────────────────────
    if str(character.get("description_status") or "").strip() == "migrated":
        core = str(character.get("appearance_core") or "").strip()
        if core:
            return f"{name}: {core}"

    # ── Legacy fallback ────────────────────────────────────────────────────
    vps = str(character.get("visual_prompt_summary") or "").strip()
    if vps:
        return f"{name}: {vps}"

    return name


def resolve_character_prompt(
    character: dict[str, Any],
    scene_id: str,
    shot_id: Optional[str],
    storage: Any | None = None,
) -> str:
    """Resolve the character prompt for a given scene/shot context.

    Args:
        character: Character dict from storage.get_character_by_name() or
            get_characters(). Must contain at least 'id', 'name', and
            'visual_prompt_summary'.
        scene_id: Scene identifier (e.g. "scene_001").
        shot_id: Optional shot identifier (e.g. "scene_001_shot_001").
        storage: Optional storage instance for staging lookups. When None,
            only the legacy fallback path is available.

    Returns:
        The resolved character prompt string. For legacy characters (the
        current state), this is byte-for-byte identical to:
            f"{name}: {visual_prompt_summary}"

    Phase 1 guarantee: zero render regression. The legacy fallback path
    produces exactly what render.py's _char_summaries.append() produces today.
    """
    name = str(character.get("name") or "").strip()
    character_id = str(character.get("id") or "").strip()

    # ── Staging lookup (Phase 2+ path) ─────────────────────────────────────
    if storage is not None and character_id:
        try:
            staging = storage.get_character_staging(character_id, scene_id, shot_id)
            if staging:
                override = (staging.get("appearance_override") or "").strip()
                if override:
                    if appearance_approval(character).get("status") == "locked":
                        return f"{_resolve_base_appearance(character)}. Scene appearance (preserve approved face, build, skin tone and age): {override}"
                    return override
                staging_prompt = (staging.get("staging_prompt") or "").strip()
                if staging_prompt:
                    # Combine base appearance with scene-specific staging
                    # per §4.1: f"{name}: {appearance}. In this shot: {staging_prompt}"
                    base = _resolve_base_appearance(character).rstrip(".")
                    return f"{base}. In this shot: {staging_prompt}"
        except Exception as exc:
            logger.debug(
                "CHARACTER_STAGING_LOOKUP_FAILED | character=%s scene=%s shot=%s err=%s",
                character_id, scene_id, shot_id, exc,
            )

    # ── No staging row found — fall through to base appearance resolution ──
    return _resolve_base_appearance(character)


def resolve_character_block(
    characters: list[dict[str, Any]],
    scene_id: str,
    shot_id: Optional[str],
    storage: Any | None = None,
) -> str:
    """Resolve the full "Characters: ..." block for a scene/shot.

    Mirrors the current assembly in render.py:
        char_block = "Characters: " + "; ".join(_char_summaries)

    Phase 1 guarantee: when all characters are legacy (description_status='legacy',
    appearance_core IS NULL, no stagings rows), the output is byte-for-byte
    identical to today's injected character block.
    """
    summaries: list[str] = []
    for char in characters:
        name = str(char.get("name") or "").strip()
        if not name:
            continue
        resolved = resolve_character_prompt(char, scene_id, shot_id, storage)
        if resolved:
            summaries.append(resolved)
    if not summaries:
        return ""
    return "Characters: " + "; ".join(summaries)
