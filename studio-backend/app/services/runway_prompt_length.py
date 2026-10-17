"""Single source of truth for Runway gen4_image prompt length.

Runway documents ``promptText`` for gen4_image as max 1000 characters measured
in UTF-16 code units (verified 2026-09-27 against the official Runway Dev API
reference; re-verified 2026-10-17 per D4 scope item 1 — the live OpenAPI spec
was unreachable from this environment, so the 1000 UTF-16 value is retained
unchanged and fail-closed).

Python ``len()`` counts Unicode code points, which UNDERCOUNTS text with
non-BMP characters (emoji, some CJK extensions): each such character is 1
Python char but 2 UTF-16 code units. Using ``len()`` alone would therefore let
an over-limit prompt slip past the gate and fail at the provider. Always use
``utf16_length`` here for gate/compactor/guard decisions.
"""

from __future__ import annotations


# Runway gen4_image promptText cap: 1000 UTF-16 code units. Do not raise
# without re-verifying against docs.dev.runwayml.com/openapi.json.
RUNWAY_IMAGE_MAX_PROMPT_UTF16 = 1000

# Version tag for the length rule itself (bumped if the cap or unit changes).
RUNWAY_IMAGE_LENGTH_RULE_VERSION = "gen4_image-1000-utf16-v1"


def utf16_length(text: str | None) -> int:
    """Return the length of text in UTF-16 code units.

    Implemented via UTF-16-LE byte length // 2: no BOM, no surrogate
    ambiguity, correct for BMP and non-BMP characters alike.
    """
    if not text:
        return 0
    return len(str(text).encode("utf-16-le")) // 2


def is_over_limit(text: str | None, limit: int = RUNWAY_IMAGE_MAX_PROMPT_UTF16) -> bool:
    """True when the text exceeds the Runway image prompt limit."""
    return utf16_length(text) > limit


def overage(text: str | None, limit: int = RUNWAY_IMAGE_MAX_PROMPT_UTF16) -> int:
    """Number of UTF-16 units over the limit (0 when within limit)."""
    return max(0, utf16_length(text) - limit)
