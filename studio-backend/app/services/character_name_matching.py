from __future__ import annotations

import re


def character_name_match_position(text: str, name: str) -> int | None:
    """Return the first exact character-name match, never a substring match."""
    clean_text = str(text or "")
    clean_name = str(name or "").strip()
    if not clean_text or not clean_name:
        return None
    pattern = re.compile(
        rf"(?<![\w]){re.escape(clean_name)}(?![\w])",
        flags=re.IGNORECASE,
    )
    match = pattern.search(clean_text)
    return match.start() if match else None


def text_mentions_character(text: str, name: str) -> bool:
    return character_name_match_position(text, name) is not None
