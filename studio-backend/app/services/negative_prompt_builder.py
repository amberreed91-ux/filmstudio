"""
Negative prompt construction for video render jobs.

The slot system (`shot_prompt_builder`) is entirely positive: five slots
describing what the shot *is*, competing for a 512-character budget that the
provider weights front-to-back (POSITIONAL_WEIGHTING_FINDING.md). Everything the
shot must *not* contain either had to be spent out of that same budget or was
simply not said at all.

This module builds the negative side as a separate channel. It is passed to the
provider as its own field, so it costs nothing from the positive budget and
cannot displace a character description or a camera note.

Design notes:

- Kept short and concrete. Long negative prompts dilute; video models respond to
  a focused list of artifacts far better than to an essay.
- Grouped by concern so callers can opt out of a group (a deliberately
  handheld-looking shot should not fight "shaky camera").
- Cast exclusion is generated from the resolved cast, not hardcoded, and is
  additive to the positive cast guard in `character_state` rather than a
  replacement for it — the two reinforce each other.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Artifacts every narrative shot wants excluded, regardless of content.
BASE_ARTIFACT_NEGATIVES: tuple[str, ...] = (
    "text overlay",
    "subtitles",
    "captions",
    "watermark",
    "logo",
    "timecode",
    "split screen",
    "collage",
    "borders",
    "letterboxing",
)

# Generation failure modes specific to video models.
BASE_QUALITY_NEGATIVES: tuple[str, ...] = (
    "deformed hands",
    "extra fingers",
    "extra limbs",
    "morphing faces",
    "warping features",
    "flickering",
    "blurry",
    "low resolution",
)

# Camera behaviour that reads as amateur footage rather than a directed shot.
BASE_CAMERA_NEGATIVES: tuple[str, ...] = (
    "shaky camera",
    "jump cut",
    "sudden zoom",
    "camera whip pan",
)

# Framing/staging drift — a shot asked for as a single continuous take that
# quietly becomes a montage is one of the most common adherence failures.
BASE_STAGING_NEGATIVES: tuple[str, ...] = (
    "multiple shots",
    "scene change",
    "montage",
)

NEGATIVE_GROUPS: dict[str, tuple[str, ...]] = {
    "artifacts": BASE_ARTIFACT_NEGATIVES,
    "quality": BASE_QUALITY_NEGATIVES,
    "camera": BASE_CAMERA_NEGATIVES,
    "staging": BASE_STAGING_NEGATIVES,
}

# Providers whose submit payload carries a negative prompt field. Runway Gen-4
# has no negative prompt parameter, so building one for it would be silently
# discarded — the caller checks this rather than guessing.
PROVIDERS_SUPPORTING_NEGATIVE_PROMPT: frozenset[str] = frozenset(
    {"happyhorse", "happyhorse-r2v", "comfyui", "simulated", "local"}
)

# Keep the negative prompt from growing without bound. DashScope accepts long
# strings but effectiveness falls off; this is a guard, not a provider limit.
MAX_NEGATIVE_PROMPT_LENGTH = 500


def provider_supports_negative_prompt(provider: str) -> bool:
    """True when this provider's submit payload actually carries a negative prompt."""
    return str(provider or "").strip().lower() in PROVIDERS_SUPPORTING_NEGATIVE_PROMPT


def _dedupe_preserving_order(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        cleaned = str(term or "").strip().strip(",").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def build_cast_exclusion_terms(cast_names: list[str] | None) -> list[str]:
    """Negative terms that keep uninvited people out of the frame.

    Deliberately does not name the characters who *should* be present — a video
    model given "not MAYA" in a negative prompt frequently drops MAYA. It excludes
    the category of unwanted people instead.
    """
    names = [str(name or "").strip() for name in (cast_names or []) if str(name or "").strip()]
    terms = ["extra people", "background crowd", "bystanders", "additional characters"]
    if len(names) == 1:
        # A shot resolved to exactly one character is the case where a spurious
        # second person is both most likely and most damaging.
        terms.insert(0, "second person in frame")
    return terms


def build_negative_prompt(
    *,
    cast_names: list[str] | None = None,
    extra_terms: list[str] | None = None,
    disabled_groups: list[str] | None = None,
    max_length: int = MAX_NEGATIVE_PROMPT_LENGTH,
) -> str:
    """Build the negative prompt string for a render job.

    Args:
        cast_names: Characters resolved for this shot, used for cast exclusion.
        extra_terms: Shot- or project-specific exclusions (e.g. a standing
            correction, or a director note like "no rain").
        disabled_groups: Group names from NEGATIVE_GROUPS to leave out — for
            example ["camera"] on a shot that is deliberately handheld.
        max_length: Guard on total length.

    Returns:
        Comma-separated negative prompt, or "" if everything was disabled.
    """
    disabled = {str(name or "").strip().lower() for name in (disabled_groups or [])}

    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get():
        max_length = 10**9  # Final provider boundary budgets required exclusions first.
    terms: list[str] = []
    terms.extend(build_cast_exclusion_terms(cast_names))
    for group_name, group_terms in NEGATIVE_GROUPS.items():
        if group_name in disabled:
            continue
        terms.extend(group_terms)
    terms.extend(extra_terms or [])

    ordered = _dedupe_preserving_order(terms)
    if not ordered:
        return ""

    negative = ", ".join(ordered)
    if len(negative) > max_length:
        # Trim whole terms rather than cutting mid-phrase — a truncated term is
        # noise the provider still has to interpret.
        kept: list[str] = []
        running = 0
        for term in ordered:
            addition = len(term) + (2 if kept else 0)
            if running + addition > max_length:
                break
            kept.append(term)
            running += addition
        negative = ", ".join(kept)
        logger.debug(
            "NEGATIVE_PROMPT_TRIMMED | kept=%d | dropped=%d",
            len(kept),
            len(ordered) - len(kept),
        )

    return negative
