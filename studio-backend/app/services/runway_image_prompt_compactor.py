"""Deterministic, rule-based compaction of canonical board prompts (D4-B).

The canonical ``provider_neutral_prompt`` is never altered. This compactor
produces a SEPARATE, shorter Runway-targeted proposal (<=1000 UTF-16 units)
that a human must approve before any render may use it.

Determinism: same input string -> same output, no LLM, no randomness, no
wall-clock, no dict-ordering dependence. Rules are versioned
(``COMPACTOR_VERSION``); every record carries the source sha256, the rules
applied, dropped segments, and lengths so a human can review what was removed.

Priority order (keep first):
  1. subject/action + setting (shot-type template, location/time, action)
  2. camera/lens/lighting
  3. essential character looks (first mention kept; exact-duplicate locked tail dropped)
  4. mood
Drop first: rationale-like free text, exact duplicate sentences, performance
visible lines, then whole trailing clauses. Never cut mid-word: clauses are
dropped whole on sentence boundaries (". ", "; ", " | ").

Failure: when the prompt cannot be brought within limit without dropping a
priority-1 segment, compaction FAILS with a clear message (fail closed) rather
than emitting an over-limit or gutted prompt.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from app.services.runway_prompt_length import (
    RUNWAY_IMAGE_MAX_PROMPT_UTF16,
    utf16_length,
)

logger = logging.getLogger("runway-image-prompt-compactor")

COMPACTOR_VERSION = "d4-compactor-v1"

# Sentence-ish split that never cuts mid-word: keep the delimiter attached.
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.;|])\s+")

# Markers identifying low-priority / droppable content. Matched
# case-insensitively against whole clauses.
_RATIONALE_MARKERS = (
    "rationale:",
    "rationale ",
    "reference notes",
    "director's notes",
    "director notes",
    "edit bay note",
)
_LOCKED_TAIL_MARKER = "locked appearance"
_PERFORMANCE_MARKERS = ("performance:", "visible lines:", "dialogue beat:")
_MOOD_MARKERS = ("mood:",)
_STYLE_SUFFIX = "Cinematic, film quality, single continuous shot."


def canonical_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _split_clauses(text: str) -> list[str]:
    parts = [p.strip(" .") for p in _CLAUSE_SPLIT_RE.split(str(text or ""))]
    return [p for p in (p.strip() for p in parts) if p]


def _contains_any(clause: str, markers: tuple[str, ...]) -> bool:
    lowered = clause.lower()
    return any(m in lowered for m in markers)


def _dedupe_exact(clauses: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Drop exact-duplicate sentences (case/whitespace-insensitive), keep first."""
    seen: set[str] = set()
    kept: list[str] = []
    dropped: list[dict[str, Any]] = []
    for clause in clauses:
        key = re.sub(r"\s+", " ", clause.strip().lower())
        if key in seen:
            dropped.append(
                {
                    "rule": "drop_exact_duplicate",
                    "clause": clause[:280],
                    "utf16_removed": utf16_length(clause) + 2,
                }
            )
            continue
        seen.add(key)
        kept.append(clause)
    return kept, dropped


def compact_canonical_prompt(
    canonical_prompt: str,
    *,
    limit: int = RUNWAY_IMAGE_MAX_PROMPT_UTF16,
) -> dict[str, Any]:
    """Compact one canonical prompt into a Runway-sized proposal.

    Returns a record dict with keys: ok, image_prompt, source_sha256,
    compactor_version, rules_applied, dropped_segments, canonical_utf16,
    image_utf16, chars_removed, error (None on success).
    """
    canonical = str(canonical_prompt or "").strip()
    source_sha = canonical_sha256(canonical)
    canonical_len = utf16_length(canonical)
    rules_applied: list[str] = []
    dropped: list[dict[str, Any]] = []

    def join(clauses: list[str]) -> str:
        return ". ".join(c for c in clauses if c).strip() + ("." if clauses else "")

    if not canonical:
        return {
            "ok": False,
            "image_prompt": "",
            "source_sha256": source_sha,
            "compactor_version": COMPACTOR_VERSION,
            "rules_applied": ["fail_empty_canonical"],
            "dropped_segments": [],
            "canonical_utf16": 0,
            "image_utf16": 0,
            "chars_removed": 0,
            "error": "Canonical prompt is empty; nothing to compact.",
        }

    if canonical_len <= limit:
        return {
            "ok": True,
            "image_prompt": canonical,
            "source_sha256": source_sha,
            "compactor_version": COMPACTOR_VERSION,
            "rules_applied": ["passthrough_within_limit"],
            "dropped_segments": [],
            "canonical_utf16": canonical_len,
            "image_utf16": canonical_len,
            "chars_removed": 0,
            "error": None,
        }

    clauses = _split_clauses(canonical)

    # Rule 1: drop rationale-like free text first (never part of the image ask).
    kept: list[str] = []
    for clause in clauses:
        if _contains_any(clause, _RATIONALE_MARKERS):
            dropped.append(
                {
                    "rule": "drop_rationale",
                    "clause": clause[:280],
                    "utf16_removed": utf16_length(clause) + 2,
                }
            )
            continue
        kept.append(clause)
    if len(kept) != len(clauses):
        rules_applied.append("drop_rationale")
    clauses = kept

    # Rule 2: drop exact duplicate sentences (the locked tail duplicates seg 6 by design).
    clauses, dup_dropped = _dedupe_exact(clauses)
    if dup_dropped:
        rules_applied.append("drop_exact_duplicate")
        dropped.extend(dup_dropped)

    # Rule 3: drop the duplicated locked-appearance tail's repeats: keep the
    # FIRST locked-appearance clause (identity enforcement), drop later ones.
    kept = []
    seen_locked = False
    for clause in clauses:
        if _LOCKED_TAIL_MARKER in clause.lower():
            if seen_locked:
                dropped.append(
                    {
                        "rule": "drop_duplicate_locked_tail",
                        "clause": clause[:280],
                        "utf16_removed": utf16_length(clause) + 2,
                    }
                )
                continue
            seen_locked = True
        kept.append(clause)
    if len(kept) != len(clauses):
        rules_applied.append("drop_duplicate_locked_tail")
    clauses = kept

    # Rule 4: drop performance visible-lines clauses.
    kept = []
    for clause in clauses:
        if _contains_any(clause, _PERFORMANCE_MARKERS):
            dropped.append(
                {
                    "rule": "drop_performance_lines",
                    "clause": clause[:280],
                    "utf16_removed": utf16_length(clause) + 2,
                }
            )
            continue
        kept.append(clause)
    if len(kept) != len(clauses):
        rules_applied.append("drop_performance_lines")
    clauses = kept

    candidate = join(clauses)
    if utf16_length(candidate) <= limit:
        removed = canonical_len - utf16_length(candidate)
        logger.info(
            "project_id=%s job_id=%s provider=runway stage=image_prompt_compaction duration_ms=%d",
            "-", "-",
            0,
        )
        return {
            "ok": True,
            "image_prompt": candidate,
            "source_sha256": source_sha,
            "compactor_version": COMPACTOR_VERSION,
            "rules_applied": rules_applied or ["drop_rules_no_op"],
            "dropped_segments": dropped,
            "canonical_utf16": canonical_len,
            "image_utf16": utf16_length(candidate),
            "chars_removed": removed,
            "error": None,
        }

    # Rule 5: drop mood clauses (kept at lowest priority among keepers).
    kept = [c for c in clauses if not _contains_any(c, _MOOD_MARKERS)]
    if len(kept) != len(clauses):
        for clause in clauses:
            if _contains_any(clause, _MOOD_MARKERS):
                dropped.append(
                    {
                        "rule": "drop_mood",
                        "clause": clause[:280],
                        "utf16_removed": utf16_length(clause) + 2,
                    }
                )
        rules_applied.append("drop_mood")
        clauses = kept
        candidate = join(clauses)
        if utf16_length(candidate) <= limit:
            return {
                "ok": True,
                "image_prompt": candidate,
                "source_sha256": source_sha,
                "compactor_version": COMPACTOR_VERSION,
                "rules_applied": rules_applied,
                "dropped_segments": dropped,
                "canonical_utf16": canonical_len,
                "image_utf16": utf16_length(candidate),
                "chars_removed": canonical_len - utf16_length(candidate),
                "error": None,
            }

    # Rule 6: drop trailing non-priority clauses one at a time (never the
    # first clause = subject/action head; never the style suffix alone).
    # Priority-1 protection: stop before removing the head or the only
    # remaining locked-appearance clause.
    while len(clauses) > 2 and utf16_length(join(clauses)) > limit:
        victim_idx = len(clauses) - 1
        # Never drop the style suffix by itself while other drops remain:
        # prefer the clause before it.
        if clauses[victim_idx].rstrip(".").strip() == _STYLE_SUFFIX.rstrip(".") and len(clauses) > 2:
            victim_idx = len(clauses) - 2
        if victim_idx <= 0:
            break
        victim = clauses[victim_idx]
        if _LOCKED_TAIL_MARKER in victim.lower():
            # Only one locked clause remains (earlier dupes dropped) — stop.
            remaining_locked = sum(1 for c in clauses if _LOCKED_TAIL_MARKER in c.lower())
            if remaining_locked <= 1:
                break
        dropped.append(
            {
                "rule": "drop_trailing_clause",
                "clause": victim[:280],
                "utf16_removed": utf16_length(victim) + 2,
            }
        )
        del clauses[victim_idx]
        if "drop_trailing_clause" not in rules_applied:
            rules_applied.append("drop_trailing_clause")

    candidate = join(clauses)
    if utf16_length(candidate) <= limit and clauses:
        return {
            "ok": True,
            "image_prompt": candidate,
            "source_sha256": source_sha,
            "compactor_version": COMPACTOR_VERSION,
            "rules_applied": rules_applied,
            "dropped_segments": dropped,
            "canonical_utf16": canonical_len,
            "image_utf16": utf16_length(candidate),
            "chars_removed": canonical_len - utf16_length(candidate),
            "error": None,
        }

    return {
        "ok": False,
        "image_prompt": "",
        "source_sha256": source_sha,
        "compactor_version": COMPACTOR_VERSION,
        "rules_applied": rules_applied,
        "dropped_segments": dropped,
        "canonical_utf16": canonical_len,
        "image_utf16": utf16_length(candidate),
        "chars_removed": 0,
        "error": (
            f"Cannot compact {canonical_len} UTF-16 units to {limit} without "
            "removing the subject/action head or the locked-appearance keeper; "
            "hand-edit the scene/character text and regenerate."
        ),
    }
