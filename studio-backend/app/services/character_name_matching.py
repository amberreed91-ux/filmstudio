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


# Screenplay introductions provide explicit identity evidence. Never merge on
# a shared surname: siblings must remain separate characters.
INTRODUCED_NICKNAME = re.compile(
    r'(?<![\w])([A-Z][A-Z]+)[ \t]+["“]([A-Z][A-Z \t]*?)["”][ \t]+([A-Z][A-Z]+)(?![\w])'
)


def screenplay_aliases(text: str) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for match in INTRODUCED_NICKNAME.finditer(text):
        first, nickname, last = match.groups()
        nickname = " ".join(nickname.split())
        canonical = f'{first} "{nickname}" {last}'
        for alias in (first, nickname, f"{first} {last}", f"{first} {nickname} {last}", canonical):
            candidates.setdefault(alias, set()).add(canonical)
    return {alias: next(iter(names)) for alias, names in candidates.items() if len(names) == 1}


def canonical_character_name(name: str, aliases: dict[str, str]) -> str:
    key = " ".join(name.upper().replace("“", '"').replace("”", '"').split())
    if key in aliases:
        return aliases[key]
    # A shortened nickname cue (PRETTY / PRETTY BOY, KINK / KINKY TAILE)
    # is accepted only when it identifies one explicit nickname in this script.
    if len(key) >= 4 and " " not in key:
        matches = {canonical for alias, canonical in aliases.items()
                   if alias.startswith(key) and alias != canonical and
                   f'"{alias}"' in canonical}
        if len(matches) == 1:
            return next(iter(matches))
    return name
