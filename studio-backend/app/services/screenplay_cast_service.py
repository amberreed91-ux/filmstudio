"""Source-backed cast discovery, including supporting and non-speaking roles."""
from __future__ import annotations

import re
from itertools import chain
from collections.abc import Callable

from app.services.character_name_matching import canonical_character_name, screenplay_aliases, INTRODUCED_NICKNAME

_WORD = r"[A-Z][A-Z’'\-]*\.?"
_NAME = rf"{_WORD}(?:[ \t]+{_WORD}){{0,4}}"
_CUE = re.compile(rf"^({_NAME}(?:[ \t]+#?\d+)?)(?:[ \t]*\((?:V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT[’']?D|PHONE|ON PHONE|FILTERED)\))*[ \t]*$")
_CAPS = re.compile(rf"(?<![\w’'])({_NAME})(?![\w’'])")
_WRAPPED = re.compile(rf"(?<![\w’'])({_WORD}[ \t]*\n\s*{_WORD})(?=,)")

_AGE = re.compile(r"^\s*,\s*(?:\d{1,2}(?!\d)|(?:early|mid|late)[ -]?(?:\s*\n\s*)?(?:\d{2}s|twenties|thirties|forties|fifties|sixties|seventies|eighties)|twenties|thirties|forties|fifties|sixties|seventies|eighties)\b")
_PERSON_DESCRIPTION = re.compile(r"^\s*,\s*(?:a|an)\s+(?:(?:young|old|older|tall|small|quiet|new)\s+)*(?:man|woman|boy|girl|child|guard|driver|nurse|doctor|officer|mechanic|teenager)\b")
_PERSON_ACTION = re.compile(r"^[ \t]+(?:takes|stands|sits|walks|runs|waits|watches|wears|carries|holds|enters|kneels|approaches)\b")
_HONORIFICS = {"MR", "MRS", "MS", "DR", "UNC", "AUNT", "UNCLE", "DETECTIVE", "OFFICER"}


def discover_cast(text: str, valid_name: Callable[[str], bool], roles: set[str]) -> tuple[list[str], dict[str, str]]:
    """Return ordered identities and unambiguous aliases; never infer surname matches."""
    def valid(name: str) -> bool:
        plain = re.sub(r"[.’'\-]", "", name)
        # Numbered extras and genuine speaking roles belong in a production cast.
        plain = re.sub(r"\s+#?\d+$", "", plain)
        if plain.split()[0] in {"ALL", "BOTH", "THREE", "FOUR", "FIVE", "SIX"}:
            return False
        return plain in roles or valid_name(plain)

    occurrences: list[tuple[int, str]] = []
    cues: set[str] = set()
    lines = list(re.finditer(r"[^\n]+", text))
    for index, line in enumerate(lines):
        value = line.group().strip()
        # Terminal full stops belong to dialogue/action, not speaker labels.
        if value.endswith("."):
            continue
        match = _CUE.fullmatch(value)
        if not match or not valid(match[1]):
            continue
        following = next((m.group().strip() for m in lines[index + 1:] if m.group().strip()), "")
        # A cue needs dialogue, including shouted dialogue. A second cue or a
        # heading is not evidence. Do not treat every capitalized line as cast.
        dialogue = following and (following.startswith("(") or any(c.islower() for c in following)
                                  or (not _CUE.fullmatch(following) and any(c in following for c in "!?.")))
        if following.lower().startswith(("written by", "a film by", "screenplay by")):
            dialogue = False
        if dialogue and not following.startswith(("INT.", "EXT.", "CUT TO", "FADE ")):
            name = match[1].rstrip(".")
            cues.add(name)
            occurrences.append((line.start(), name))

    introduced: list[str] = []
    introduction_positions: list[tuple[int, str]] = []
    aliases = screenplay_aliases(text)
    for canonical in dict.fromkeys(aliases.values()):
        position = text.find(canonical)
        if position < 0:
            position = 0
        occurrences.append((position, canonical))
        introduced.append(canonical)
    nickname_spans = [match.span() for match in INTRODUCED_NICKNAME.finditer(text)]
    for match in chain(_CAPS.finditer(text), _WRAPPED.finditer(text)):
        if any(start <= match.start() < end for start, end in nickname_spans):
            continue
        name = " ".join(match[1].split()).rstrip(".")
        if not valid(name):
            continue
        after = text[match.end():match.end() + 140]
        if (_AGE.match(after) or _PERSON_DESCRIPTION.match(after) or _PERSON_ACTION.match(after)
                or (len(name.split()) > 1 and name.split()[0] in cues and re.match(r"^\s*,\s*[a-z]", after))):
            occurrences.append((match.start(), name))
            introduced.append(name)
            introduction_positions.append((match.start(), name))

    # Plain full names (DEON HOLLIS, MR. BELL) deserve the same reconciliation
    # as quoted nicknames. Honorifics aren't first names. Shared first names
    # remain ambiguous rather than being assigned to whichever record came first.
    candidates: dict[str, set[str]] = {}
    for alias, canonical in aliases.items():
        candidates.setdefault(alias, set()).add(canonical)
    for name in introduced:
        canonical = canonical_character_name(name, aliases)
        candidates.setdefault(name, set()).add(canonical)
        words = name.split()
        first_index = 1 if words[0].rstrip('.') in _HONORIFICS and len(words) > 1 else 0
        if len(words) > first_index + 1 and '"' not in name:
            candidates.setdefault(words[first_index], set()).add(canonical)
    for cue in cues:
        if cue in candidates or " " in cue:
            continue
        first_cue = min(position for position, name in occurrences if name == cue)
        previous_cue = max((position for position, name in occurrences
                            if position < first_cue and name in cues), default=-1)
        nearby = {name for position, name in introduction_positions
                  if previous_cue < position < first_cue and first_cue - position < 300
                  and name.split()[-1] == cue}
        if len(nearby) == 1:
            # Surname-only cue immediately follows this person's introduction.
            # Shared surname alone, without this source context, is insufficient.
            candidates[cue] = nearby
    aliases = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    names = list(dict.fromkeys(canonical_character_name(name, aliases) for _, name in sorted(occurrences)))
    return names, aliases
