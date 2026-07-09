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
