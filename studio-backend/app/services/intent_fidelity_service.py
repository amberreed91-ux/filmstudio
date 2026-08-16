"""
Intent fidelity — does the prompt we are about to send still say what the
director asked for?

Every other check in the render pipeline measures the render against the prompt.
`adherence_service` scores frames against `expected_slots`, and `expected_slots`
is the *already compressed* prompt. So the loop can answer "did the render match
the prompt we sent?" but it structurally cannot answer "did the prompt we sent
still contain what the director asked for?".

That gap has a specific failure mode. `character_state` has a 210-character
budget. If a director's description of a character runs longer, the excess is
removed by `_fit_character_state_to_budget` before the prompt is ever sent. The
render then faithfully reproduces the shortened prompt, adherence scores it
highly, the shot passes, a reference lock is promoted from it — and the detail
the director cared about is gone, with a green check next to it.

This module runs before the render is submitted. It compares the slot text as it
stood before budget enforcement against the prompt that is actually going out,
and reports what was removed. It costs no provider call and blocks nothing: the
director decides what to do about a drop, or ignores it.

Voice note: per AGENTS.md, director-facing output carries no scores, ratings, or
percentages. The structured payload here holds character counts for logging and
debugging; `advisory_note` is the human-facing surface and stays in plain
production language.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("intent_fidelity")


# Slots in the order they carry meaning for the director, which is also the
# order the provider weights them (POSITIONAL_WEIGHTING_FINDING.md).
TRACKED_SLOTS = (
    "character_state",
    "action",
    "environment_persistence",
    "camera",
    "lighting",
)

SLOT_LABELS = {
    "character_state": "who is on screen and how they look",
    "action": "what happens in the shot",
    "environment_persistence": "the setting",
    "camera": "the camera language",
    "lighting": "the light and tone",
}

# A drop smaller than this is compression noise — a trailing article, a stray
# clause fragment — not a lost idea. Staying quiet about those matters: per
# AGENTS.md, commentary that appears on every render stops being read.
MATERIAL_DROP_CHARS = 24

# Only elements at least this long count as a lost idea. "a" and "the" surviving
# or not tells the director nothing.
MIN_ELEMENT_CHARS = 4

# Ceiling on how many dropped elements to name. A note listing fifteen things is
# not actionable.
MAX_REPORTED_ELEMENTS = 6


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_truncation_marker(text: str) -> str:
    """Remove the ellipsis `_truncate_to_budget` appends, so it is not treated as content."""
    cleaned = _normalise(text)
    return cleaned[:-3].rstrip() if cleaned.endswith("...") else cleaned


def split_elements(text: str) -> list[str]:
    """Split slot text into the distinct ideas a director would recognise.

    Splits on clause boundaries — semicolons, commas, sentence ends — because
    that is how the prompt slots are actually written ("weathered hands, grey at
    the temples, never stops moving"). Each surviving fragment is one thing the
    director asked for.
    """
    cleaned = _strip_truncation_marker(text)
    if not cleaned:
        return []
    parts = re.split(r"[;,.]\s+|\.$", cleaned)
    return [part.strip() for part in parts if part and len(part.strip()) >= MIN_ELEMENT_CHARS]


def dropped_elements(source_text: str, final_text: str) -> list[str]:
    """Elements present in the director's text but absent from what is being sent.

    Comparison is case-insensitive and whitespace-normalised. A partially
    surviving element (the prompt kept its opening words before the cut) still
    counts as dropped, because a half-stated idea does not reliably render.
    """
    final_normalised = _strip_truncation_marker(final_text).lower()
    if not final_normalised:
        return split_elements(source_text)

    missing: list[str] = []
    for element in split_elements(source_text):
        if element.lower() not in final_normalised:
            missing.append(element)
    return missing


def diff_slot(source_text: str, final_text: str) -> dict:
    """Compare one slot before and after budget enforcement."""
    source_clean = _normalise(source_text)
    final_clean = _normalise(final_text)
    dropped = dropped_elements(source_clean, final_clean)
    chars_dropped = max(0, len(_strip_truncation_marker(source_clean)) - len(_strip_truncation_marker(final_clean)))
    return {
        "source_length": len(source_clean),
        "final_length": len(final_clean),
        "chars_dropped": chars_dropped,
        "dropped_elements": dropped,
        "truncated": final_clean.endswith("..."),
        "material": chars_dropped >= MATERIAL_DROP_CHARS or bool(dropped),
    }


def build_advisory_note(slot_reports: dict[str, dict]) -> str:
    """Director-facing summary of what the prompt no longer says.

    Names the dropped text in the director's own words rather than describing it,
    because the point is recognition — "that's the line I wanted" — not
    measurement. Returns "" when nothing material was lost, which is the common
    case and should stay silent.
    """
    affected = [
        (slot, report)
        for slot, report in slot_reports.items()
        if report.get("material") and report.get("dropped_elements")
    ]
    if not affected:
        return ""

    # Report in slot priority order so the most heavily weighted loss leads.
    affected.sort(key=lambda item: TRACKED_SLOTS.index(item[0]) if item[0] in TRACKED_SLOTS else 99)

    notes: list[str] = []
    for slot, report in affected[:2]:
        elements = report["dropped_elements"][:2]
        quoted = " and ".join(f'"{element}"' for element in elements)
        label = SLOT_LABELS.get(slot, slot.replace("_", " "))
        notes.append(f"The prompt no longer carries {quoted} in {label}.")

    if len(affected) > 2:
        notes.append("Other detail was trimmed to fit as well.")

    notes.append(
        "The shot will render as written, so this will not show up as a mismatch later — "
        "worth deciding now whether it belongs in the shot."
    )
    return " ".join(notes)


def build_intent_fidelity_report(
    *,
    source_slots: dict[str, str] | None,
    final_slots: dict[str, str] | None,
    prompt: str = "",
    shot_id: str = "",
    defaulted_slots: list[str] | None = None,
) -> dict:
    """Compare the director's uncompressed intent against the outgoing prompt.

    Args:
        source_slots: Slot text before budget enforcement.
        final_slots: Slot text actually being sent.
        prompt: The assembled prompt string, for provenance.
        shot_id: Shot identifier, for logging.
        defaulted_slots: Slots the builder filled from its own template. These
            are skipped: trimming a default is not losing the director's intent,
            and reporting it would fire on nearly every shot.

    Returns:
        A report dict. `status` is "intact" when nothing material was lost,
        "reduced" when it was, and "unknown" when there is nothing to compare —
        never a failure, because this check is advisory and must not gate a render.
    """
    if not isinstance(source_slots, dict) or not isinstance(final_slots, dict):
        return {
            "status": "unknown",
            "reason": "no_source_slots",
            "shot_id": shot_id,
            "slots": {},
            "advisory_note": "",
        }

    skipped = {str(slot) for slot in (defaulted_slots or [])}

    slot_reports: dict[str, dict] = {}
    for slot in TRACKED_SLOTS:
        if slot in skipped:
            continue
        source_text = str(source_slots.get(slot) or "")
        final_text = str(final_slots.get(slot) or "")
        if not source_text and not final_text:
            continue
        slot_reports[slot] = diff_slot(source_text, final_text)

    total_dropped = sum(report["chars_dropped"] for report in slot_reports.values())
    reduced_slots = [slot for slot, report in slot_reports.items() if report["material"]]
    advisory_note = build_advisory_note(slot_reports)

    report = {
        "status": "reduced" if reduced_slots else "intact",
        "shot_id": shot_id,
        "slots": slot_reports,
        "reduced_slots": reduced_slots,
        "chars_dropped_total": total_dropped,
        "prompt_length": len(_normalise(prompt)),
        "skipped_defaulted_slots": sorted(skipped),
        "advisory_note": advisory_note,
    }

    if reduced_slots:
        logger.info(
            "INTENT_FIDELITY_REDUCED | shot=%s | slots=%s | chars_dropped=%d",
            shot_id or "unknown",
            ",".join(reduced_slots),
            total_dropped,
        )

    return report
