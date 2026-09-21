"""Revision Identity Comparison Service.

Compares two cinematic identity snapshots (captured from director
signatures) and reports how the visual language shifted across a revision.

Advisory only:
  - no scores, ratings, or percentages
  - names concrete tags rather than quantifying overlap
  - says nothing when the snapshots agree or when evidence is missing
"""

from __future__ import annotations

from typing import Any

_AXES = (
    ("dominant_lighting_tags", "lighting"),
    ("dominant_mood_tags", "mood"),
    ("dominant_composition_tags", "composition"),
    ("dominant_palette", "palette"),
)


def _norm(values: Any) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _join(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


class RevisionIdentityComparisonService:
    """Builds advisory drift notes between two identity snapshots."""

    def compare(
        self,
        original: dict[str, Any] | None,
        revision: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(original, dict) or not isinstance(revision, dict):
            return self._empty()

        notes: list[str] = []
        for field, label in _AXES:
            before = _norm(original.get(field))
            after = _norm(revision.get(field))
            if not before and not after:
                continue
            dropped = sorted(before - after)
            added = sorted(after - before)
            if not dropped and not added:
                continue
            notes.append(self._axis_note(label, dropped, added))

        return {
            "drift_notes": notes,
            "summary": notes[0] if notes else "The visual language holds across the revision.",
            "advisory_only": True,
            "auto_regeneration_triggered": False,
        }

    def _axis_note(self, label: str, dropped: list[str], added: list[str]) -> str:
        if dropped and added:
            return (
                f"The revision shifts the {label} language away from "
                f"{_join(dropped)} toward {_join(added)}."
            )
        if dropped:
            return f"The revision drops {_join(dropped)} from the {label} language."
        return f"The revision introduces {_join(added)} into the {label} language."

    def _empty(self) -> dict[str, Any]:
        return {
            "drift_notes": [],
            "summary": "",
            "advisory_only": True,
            "auto_regeneration_triggered": False,
        }


revision_identity_comparison_service = RevisionIdentityComparisonService()
