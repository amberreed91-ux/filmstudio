"""Scene staging: turn each screenplay beat into stageable per-shot fields.

Shared by two callers so the logic never forks:
  - the previs API endpoint POST /previs/stage-scene (front end), and
  - scripts/generate_shot_staging.py (terminal).

This service is deliberately the ONLY place the staging prompt and the
field mapping live. It does not call an LLM or touch the database itself — the
caller passes the LLM in and persists the result — so it stays pure and
testable, and so the API path can reuse the app's own get_llm_completion_with_
fallback exactly the way the sibling previs assists (shot-count, enhance-prompt)
do, rather than a bespoke provider call.

The staging fields map onto storyboard_shots.visual_plan, which is what the
render slot-builder reads. A field left blank means "the beat did not specify"
and is preserved as blank rather than invented — a confident-but-wrong lighting
plan is no better than the style-bible boilerplate this feature replaces.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Slot budgets the render prompt enforces; proposing longer text just guarantees
# a mid-word truncation downstream, so the model is told these limits.
FIELD_BUDGETS = {
    "action": 110,
    "camera_angle": 70,
    "lens_language": 50,
    "blocking": 90,
    "composition": 90,
    "lighting": 60,
}
STAGING_FIELDS = [
    "action", "camera_angle", "lens_language", "blocking",
    "composition", "lighting", "color_palette", "props",
]

_DIALOGUE_CUE = re.compile(r"^[A-Z][A-Z '\.]{2,}(\s*\(.*\))?$")
_TRANSITION = re.compile(r"^(CUT TO:|FADE (IN|OUT)|DISSOLVE TO:|SMASH CUT:)", re.I)
_PARENTHETICAL = re.compile(r"^\(.*\)$")
_FUSED_CUE = re.compile(r"([.!?])([A-Z]{2,}(?:\s*\(.*\))?)$")


def strip_screenplay_furniture(text: str) -> str:
    """Remove character cues, parentheticals, transitions and section headers.

    A video model cannot stage 'MAYA (V.O.)'. Leaving screenplay furniture in
    spends slot budget on something unrenderable and invites title cards.
    """
    kept: list[str] = []
    for raw_line in (text or "").splitlines():
        line = _FUSED_CUE.sub(r"\1", raw_line.strip())
        if not line:
            continue
        if _TRANSITION.match(line) or _PARENTHETICAL.match(line) or _DIALOGUE_CUE.match(line):
            continue
        kept.append(line)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def build_staging_messages(
    *,
    shot_number: int,
    total_shots: int,
    scene_id: str,
    purpose: str,
    location: str,
    framing: str,
    beat_text: str,
    characters_present: dict[str, str],
) -> tuple[str, str]:
    """Return (system_prompt, user_message) for one shot, matching the
    previs-assist contract (JSON-only reply parsed by parse_staging)."""
    who = ", ".join(f"{name}: {desc}" for name, desc in characters_present.items()) \
        or "(none named in this beat)"
    system_prompt = (
        "You are a first assistant director breaking a scene into shots for a "
        "text-to-video model, which can only render what is physically visible "
        "in a frame.\n\n"
        f"SHOT {shot_number} of {total_shots} in {scene_id}.\n"
        f"PURPOSE: {purpose or 'unspecified'}\n"
        f"LOCATION: {location or 'unspecified'}\n"
        f"FRAMING ALREADY SET: {framing or 'unspecified'}\n"
        f"CHARACTERS AND THEIR FIXED APPEARANCE: {who}\n\n"
        "Return ONLY a JSON object with these string keys:\n"
        f'  "action"        one physical action visible in THIS shot, max {FIELD_BUDGETS["action"]} chars. '
        "No dialogue, no interior thought, no V.O., no story context.\n"
        f'  "camera_angle"  max {FIELD_BUDGETS["camera_angle"]} chars, e.g. "low angle, eye level with the kettle"\n'
        f'  "lens_language" max {FIELD_BUDGETS["lens_language"]} chars, e.g. "wide, deep focus"\n'
        f'  "blocking"      max {FIELD_BUDGETS["blocking"]} chars — where people are and how they move\n'
        f'  "composition"   max {FIELD_BUDGETS["composition"]} chars — how the frame is arranged\n'
        f'  "lighting"      max {FIELD_BUDGETS["lighting"]} chars — the actual light: source, direction, quality\n'
        '  "color_palette" up to four colours, comma separated\n'
        '  "props"         objects that must be visible, comma separated\n\n'
        "RULES, and these matter more than completeness:\n"
        '1. Leave a field as an empty string "" if the beat does not tell you. '
        "Do not fill it with something plausible; an invented plan is worse than "
        "a blank one, because the director can fill a blank later.\n"
        '2. Never write an instruction to the filmmaker. "Use light to underline '
        'the beat" is not lighting; "Low sun through a west window, long shadows" is.\n'
        "3. Describe only this shot, not the scene around it.\n"
        "4. Do not restate the character's appearance — it is locked elsewhere.\n"
        "5. Respect the character limits. Output ONLY valid JSON, no other text."
    )
    user_message = (
        "THE BEAT THIS SHOT COVERS:\n"
        + strip_screenplay_furniture(beat_text)[:1500]
    )
    return system_prompt, user_message


def _extract_staging(parsed: Any) -> dict:
    """Pull our fields out of whatever shape the model returned (flat, wrapped,
    a list, or Title-Cased keys), so a shape mismatch is never mistaken for the
    model tastefully declining to answer."""
    if not isinstance(parsed, dict):
        return {}

    def _score(cand: dict) -> int:
        low = {str(k).lower() for k in cand}
        return sum(1 for f in STAGING_FIELDS if f in low)

    best, best_score = parsed, _score(parsed)
    for v in parsed.values():
        if isinstance(v, dict) and _score(v) > best_score:
            best, best_score = v, _score(v)
        elif isinstance(v, list) and v and isinstance(v[0], dict) and _score(v[0]) > best_score:
            best, best_score = v[0], _score(v[0])

    low = {str(k).lower(): val for k, val in best.items()}
    out: dict = {}
    for field in STAGING_FIELDS:
        val = low.get(field)
        if isinstance(val, list):
            val = ", ".join(str(x).strip() for x in val if str(x).strip())
        out[field] = str(val or "").strip()
    return out


def parse_staging(reply: str) -> dict:
    """Parse an LLM reply into the staging fields. Never raises: an unparseable
    reply yields all-blank, which the caller reports as a failure rather than
    silently persisting."""
    text = str(reply or "").strip()
    if "```" in text:
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = {}
    return _extract_staging(parsed)


def staging_to_visual_plan(staging: dict) -> dict:
    """Map the proposed staging onto storyboard_shots.visual_plan field names.

    Only non-empty fields are returned, so applying a proposal MERGES onto the
    existing visual_plan and never blanks a field the storyboard already set.
    color_palette is split into the list shape the visual_plan expects.
    """
    plan: dict = {}
    for field in ("action", "camera_angle", "lens_language", "blocking",
                  "composition", "lighting", "props"):
        value = str(staging.get(field) or "").strip()
        if value:
            plan[field] = value
    palette = str(staging.get("color_palette") or "").strip()
    if palette:
        colours = [c.strip() for c in palette.split(",") if c.strip()]
        if colours:
            plan["color_palette"] = colours
    return plan


def over_budget(staging: dict) -> dict:
    """Fields whose proposed text exceeds its slot budget (reported, not cut)."""
    return {
        f: len(str(staging.get(f) or ""))
        for f in FIELD_BUDGETS
        if len(str(staging.get(f) or "")) > FIELD_BUDGETS[f]
    }
