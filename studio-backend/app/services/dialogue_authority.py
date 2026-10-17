"""Canonical dialogue authority (Multi Shot integrity audit, Phase 3/3A).

ONE authoritative dialogue representation exists for production:

    Canonical screenplay (script_text)
        -> authoritative scene representation (execution_summary scenes, parsed
           directly from the screenplay)
        -> shot level dialogue assignment (Scene Direction / render-contract
           ``dialogue_lines``)
        -> Previs, audio/performance, subtitles, generation context

Everything else is advisory and must never become production dialogue.

Historical contamination: ``DialogueVoiceService.build_dialogue_lines`` invented
placeholder "performance scaffolding" text (e.g. "DRE carries the beat with
restrained subtext.") that was persisted into ``execution_summary.dialogue_lines``.
That fabricated text must never again reach production consumers.

Two bounded, additive mechanisms enforce the boundary:

1. ``is_placeholder_dialogue`` — a conservative, structural detector for the
   exact fabricated template produced by DialogueVoiceService. It recognizes
   the "<NAME> carries the beat with <subtext>." shape (and the Narrator
   variant) without flagging real screenplay lines. Detection is read-only:
   the historical records stay in place for auditability.

2. ``canonical_dialogue_lines`` — the one extractor production consumers call.
   It prefers pre-supplied shot/scene dialogue (creator-curated), filters
   placeholder rows out of stored projections, and otherwise derives the lines
   deterministically from the scene text itself via
   ``audio_pipeline_service._extract_dialogue_lines`` — the tested screenplay
   extractor. It never invents dialogue.

AI performance suggestions (voice_style_hint, emotional_subtext, pacing) remain
advisory enrichments AT MOST; the text of every production line comes from the
screenplay or the creator.
"""
from __future__ import annotations

import re
from typing import Any

# The exact fabricated template DialogueVoiceService.persisted into
# execution_summary.dialogue_lines: "{NAME} carries the beat with {subtext}."
_PLACEHOLDER_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z .'\-]{0,40}?)\s+carries the beat with\s+(?P<subtext>.+?)\.$"
)
_PLACEHOLDER_SUBTEXTS = {"restrained subtext"}

# Line keys a stored dialogue row may use for speaker/text.
_CHARACTER_KEYS = ("character", "character_name", "character_id")
_TEXT_KEYS = ("text", "line_text", "dialogue")


def is_placeholder_dialogue(text: str) -> bool:
    """True for DialogueVoiceService-scaffolded placeholder lines.

    Matches the exact generated template shape ("X carries the beat with
    restrained subtext.", including the trailing Behavior-memory /
    Performance-direction suffixes that service appends) so historical
    fabricated rows can be excluded from production dialogue without risking
    real screenplay lines.
    """
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return False
    if normalized.lower().endswith("carries the beat with restrained subtext."):
        return True
    match = _PLACEHOLDER_RE.match(normalized)
    return bool(match and match.group("subtext").strip().lower() in _PLACEHOLDER_SUBTEXTS)


def _row_text(row: dict[str, Any]) -> str:
    for key in _TEXT_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def filter_placeholder_lines(
    lines: Any,
) -> list[dict[str, Any]]:
    """Return only rows whose TEXT is real dialogue (never fabricated).

    Read-only: it does not mutate or delete historical records — production
    consumers simply stop treating fabricated rows as dialogue.
    """
    if not isinstance(lines, list):
        return []
    kept: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        if is_placeholder_dialogue(_row_text(row)):
            continue
        kept.append(row)
    return kept


def canonical_dialogue_lines(
    scene: dict[str, Any] | None = None,
    supplied_lines: Any = None,
    *,
    scene_id: str = "",
    characters: list[str] | None = None,
) -> list[dict[str, str]]:
    """Return the canonical dialogue lines for a scene/shot.

    Order of authority (never invents dialogue):
      1. ``supplied_lines`` — shot-level render-contract assignments or
         scene-level dialogue rows curated by the creator; placeholder rows are
         filtered out, everything else is passed through untouched.
      2. The scene's own stored ``dialogue_lines`` projection — placeholder
         rows filtered out; remaining rows are the parser's extraction.
      3. Deterministic extraction from the scene text itself
         (``audio_pipeline_service._extract_dialogue_lines``), the tested
         screenplay parser.

    Returned rows are simple ``{character, text}`` dicts plus any advisory
    voice fields already attached to a supplied row. Returns [] when the scene
    genuinely has no dialogue.
    """
    from app.services.audio_pipeline_service import _extract_dialogue_lines

    for source in (supplied_lines, (scene or {}).get("dialogue_lines")):
        rows = filter_placeholder_lines(source)
        if rows:
            return [
                {
                    **{
                        str(key): str(value)
                        for key, value in row.items()
                        if value is not None
                    },
                }
                for row in rows
            ]

    text = ""
    if isinstance(scene, dict):
        text = str(
            scene.get("text")
            or scene.get("scene_text")
            or scene.get("script_text")
            or scene.get("description")
            or ""
        )
    if not text.strip():
        return []
    return [
        {"character": str(line["character"]), "text": str(line["text"])}
        for line in _extract_dialogue_lines(text, characters=characters)
        if str(line.get("text") or "").strip()
    ]


def canonical_scene_dialogue_for_audio(
    project: dict[str, Any] | None,
    scene: dict[str, Any] | None,
    scene_id: str,
    *,
    characters: list[str] | None = None,
) -> list[dict[str, str]] | None:
    """Scene-level canonical dialogue for audio/performance consumers.

    Reads the project's stored ``execution_summary.dialogue_lines`` projection
    for this scene with fabricated placeholder rows excluded, then falls back
    to deterministic extraction from the scene text. Returns None only when
    neither the scene nor its text is available, so callers can keep their
    existing "no dialogue available" handling.
    """
    stored: list[dict[str, Any]] = []
    summary = (project or {}).get("execution_summary") or {}
    raw = summary.get("dialogue_lines")
    if isinstance(raw, list) and scene_id:
        stored = [
            row
            for row in filter_placeholder_lines(raw)
            if str(row.get("scene_id") or "") == scene_id
        ]
    lines = canonical_dialogue_lines(
        scene,
        stored or None,
        scene_id=scene_id,
        characters=characters,
    )
    if lines:
        return lines
    if scene is None:
        return None
    return []
