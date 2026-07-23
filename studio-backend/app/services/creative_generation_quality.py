"""Shared quality checks for context-grounded creative LLM responses."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


_GENERIC_REPLY_FRAGMENTS = (
    "tell me more about your intent",
    "could you clarify your intent",
    "can you clarify your intent",
    "this looks good overall",
    "great job",
)


def _semantic_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", str(value or "").lower()))


def semantic_similarity(left: str, right: str) -> float:
    """Compare wording while ignoring punctuation and whitespace changes."""
    return SequenceMatcher(None, _semantic_text(left), _semantic_text(right)).ratio()


def is_near_verbatim(source: str, candidate: str) -> bool:
    """Reject punctuation-only and minimally expanded rewrites."""
    source_text = _semantic_text(source)
    candidate_text = _semantic_text(candidate)
    added_words = set(candidate_text.split()) - set(source_text.split())
    return (
        semantic_similarity(source, candidate) >= 0.86
        or len(added_words) < 10
        or len(candidate_text) <= len(source_text) + 45
    )


def co_director_response_issue(
    response: str,
    *,
    request_is_clear: bool,
    requires_grounding: bool,
    grounding_terms: tuple[str, ...],
) -> str | None:
    """Return why a response should be retried, or ``None`` when usable."""
    text = str(response or "").strip()
    lowered = text.lower()
    if requires_grounding and len(_semantic_text(text).split()) < 8:
        return "too_short"
    if any(fragment in lowered for fragment in _GENERIC_REPLY_FRAGMENTS):
        return "generic_or_deflecting"
    if re.search(r"\b(?:score|rating)\s*[:=-]?\s*\d", lowered) or "%" in text:
        return "numeric_evaluation"
    if request_is_clear and requires_grounding and grounding_terms:
        matched_terms = {term for term in grounding_terms if term in lowered}
        if len(matched_terms) < min(2, len(grounding_terms)):
            return "not_grounded"
    return None
