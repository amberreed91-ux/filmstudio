"""Storyboard prompt integrity (P0-3).

Detects corruption artifacts left by the historical 512-character prompt
truncation so a damaged prompt can never silently become approved generation
input. Detection is mechanical and read-only: it never rewrites, repairs, or
summarizes canonical prompts. A flagged prompt fails the generation gate
CLOSED until the authoritative prompt has been regenerated (a new board
version built by the current non-truncating builder) or explicitly repaired
and re-approved by the creator.

Known artifact classes (from the Multi Shot integrity audit, H-3):
- ``legacy_truncation_artifact``: an ellipsis left behind by the historical
  ``base_prompt[:509] + "..."`` cut that ran during board assembly.
- ``severed_terminal_fragment``: the prompt ends in a one-or-two letter
  fragment after sentence punctuation (e.g. "... stands . e").

A sentence severed but punctuated ("... The.") cannot be proven corrupt from
the string alone and is NOT flagged mechanically; it is covered by the
operator regeneration path and reported as a residual risk.
"""
from __future__ import annotations

import re
from typing import Any

_SEVERED_ENDING = re.compile(r"[.!?]\s*[A-Za-z]{1,2}$")
_ELLIPSIS_ARTIFACTS = ("...", "\u2026")


def detect_prompt_corruption(prompt: Any, *, source: str = "BOARD") -> list[str]:
    """Return a list of corruption issues for an approved board prompt.

    ``source`` is the prompt provenance: only BOARD (approved canonical board
    content) is gated. A USER_EDITED prompt is the creator's own approved
    text and is never second-guessed here.
    """
    if source != "BOARD":
        return []
    text = str(prompt or "")
    if not text.strip():
        return ["empty_prompt: the approved storyboard shot has no render prompt"]
    issues: list[str] = []
    for marker in _ELLIPSIS_ARTIFACTS:
        if marker in text:
            issues.append(
                "legacy_truncation_artifact: the approved prompt contains an ellipsis "
                "left by the historical 512-character truncation. Regenerate the "
                "storyboard version or repair and re-approve the prompt before rendering."
            )
            break
    stripped = text.rstrip()
    if _SEVERED_ENDING.search(stripped):
        issues.append(
            "severed_terminal_fragment: the approved prompt ends in a severed fragment "
            "rather than a complete sentence. Regenerate the storyboard version or "
            "repair and re-approve the prompt before rendering."
        )
    return issues
