"""
Director Intent Injection Utility.

Provides helper functions to inject director intent into Claude calls across
all intelligence services.

The director intent serves as a north star for all downstream intelligence,
ensuring that every AI decision is aligned with the director's creative vision.
"""
from typing import Optional, Dict, Any


def build_director_intent_prefix(intent: Optional[Dict[str, Any]]) -> str:
    """
    Build a director intent prefix for Claude system prompts.
    
    Only includes fields that are non-null/non-empty.
    If no intent exists or all fields are empty, returns empty string (silent fallback).
    
    Args:
        intent: The director intent dict from the project.
    
    Returns:
        A formatted string to prepend to Claude system prompts, or empty string.
    
    Example output:
        DIRECTOR INTENT:
        Genre: Neo-noir thriller
        Tone references: Arrival, Blade Runner 2049
        Emotional target: Audiences should feel contemplative unease
        Visual references: Deakins lighting, handheld intimacy
        What success looks like: A film that lingers in memory
        Avoid: Heavy-handed exposition, melodrama
    """
    if not intent:
        return ""
    
    lines = ["DIRECTOR INTENT:"]
    
    # Genre
    if intent.get("genre"):
        lines.append(f"Genre: {intent['genre']}")
    
    # Tone references
    if intent.get("tone_references") and len(intent["tone_references"]) > 0:
        refs = ", ".join(intent["tone_references"])
        lines.append(f"Tone references: {refs}")
    
    # Emotional target
    if intent.get("emotional_target"):
        lines.append(f"Emotional target: {intent['emotional_target']}")
    
    # Visual references
    if intent.get("visual_references") and len(intent["visual_references"]) > 0:
        refs = ", ".join(intent["visual_references"])
        lines.append(f"Visual references: {refs}")
    
    # What success looks like
    if intent.get("what_success_looks_like"):
        lines.append(f"What success looks like: {intent['what_success_looks_like']}")
    
    # What to avoid
    if intent.get("what_to_avoid") and len(intent["what_to_avoid"]) > 0:
        avoid = ", ".join(intent["what_to_avoid"])
        lines.append(f"Avoid: {avoid}")
    
    # If only the header line exists, return empty string (silent fallback)
    if len(lines) == 1:
        return ""
    
    # Add blank line after intent block
    lines.append("")
    
    return "\n".join(lines)


def inject_director_intent_into_prompt(
    base_prompt: str,
    intent: Optional[Dict[str, Any]],
) -> str:
    """
    Inject director intent prefix into a prompt.
    
    Prepends the intent prefix to the base prompt if intent exists.
    If no intent or all fields empty, returns base prompt unchanged.
    
    Args:
        base_prompt: The original prompt text.
        intent:      The director intent dict from the project.
    
    Returns:
        The prompt with intent prefix prepended, or original prompt if no intent.
    """
    prefix = build_director_intent_prefix(intent)
    
    if not prefix:
        return base_prompt
    
    return f"{prefix}{base_prompt}"


# ─────────────────────────────────────────────────────────────────────────────
# Render-prompt guidance
#
# `build_director_intent_prefix` above is written for Claude system prompts,
# where a multi-line prose block costs nothing and reads well. A video render
# prompt is a different consumer with different physics:
#
#   - It has a hard 512-character budget that the whole slot system exists to
#     manage (SLOT_BUDGETS in shot_prompt_builder).
#   - The provider weights early tokens far more heavily than later ones
#     (POSITIONAL_WEIGHTING_FINDING.md).
#
# Prepending the prose block to a render prompt therefore put project-level
# abstractions — genre, "what success looks like" — in the most heavily weighted
# position in the prompt, ahead of who is on screen and what they do, and pushed
# the shot itself toward the tail. With a realistic intent the prefix ran longer
# than the entire slotted prompt it was prefixing.
#
# These helpers produce the render-facing form instead: short, concrete, and
# limited to what a video model can actually act on.
# ─────────────────────────────────────────────────────────────────────────────

# Ceiling for intent guidance inside a render prompt. Small on purpose — this is
# standing project context competing against shot-specific content that only
# describes this one shot.
DIRECTOR_INTENT_RENDER_BUDGET = 90


def build_director_intent_render_guidance(
    intent: Optional[Dict[str, Any]],
    max_chars: int = DIRECTOR_INTENT_RENDER_BUDGET,
) -> str:
    """Compact, renderable director intent for a video prompt.

    Keeps only fields a video model can act on visually — the emotional register
    and visual references — and drops the ones it cannot: `genre` (a category,
    not an instruction), `what_success_looks_like` (a judgement about the
    finished film), and `what_to_avoid` (which belongs in the negative prompt;
    see `director_intent_negative_terms`).

    Returns "" when there is nothing renderable, so the caller adds nothing.
    """
    if not intent:
        return ""

    parts = []
    emotional_target = str(intent.get("emotional_target") or "").strip()
    if emotional_target:
        parts.append(emotional_target)

    visual_references = intent.get("visual_references")
    if isinstance(visual_references, list):
        refs = [str(ref).strip() for ref in visual_references if str(ref or "").strip()]
        if refs:
            parts.append(", ".join(refs))

    if not parts:
        return ""

    guidance = "; ".join(parts)
    if len(guidance) <= max_chars:
        return guidance

    # Trim whole clauses rather than cutting mid-phrase — a half-phrase is noise
    # the model still has to interpret.
    kept: list[str] = []
    running = 0
    for part in parts:
        addition = len(part) + (2 if kept else 0)
        if running + addition > max_chars:
            break
        kept.append(part)
        running += addition
    if kept:
        return "; ".join(kept)
    return parts[0][:max_chars].rstrip()


def director_intent_negative_terms(intent: Optional[Dict[str, Any]]) -> list:
    """The director's `what_to_avoid` list, for the negative prompt channel.

    "Avoid: melodrama" inside a positive prompt asks a video model to process a
    negation, which it does not do reliably — stating the thing is as likely to
    summon it as to suppress it. The negative prompt is where an exclusion
    actually functions as one.
    """
    if not intent:
        return []
    raw = intent.get("what_to_avoid")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item or "").strip()]
