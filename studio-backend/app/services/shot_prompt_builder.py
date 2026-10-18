"""
Shot-aware prompt builder for previs generation.

Generates unique, cinematically intelligent prompts for each shot/take combination
based on shot position, script tag type, and take variation.

Phase 2: Fixed-slot prompt assembly with character budgets and slot-addressable structure.
"""

import logging
import re
from typing import Optional
from app.utils.character_appearance import appearance_approval, appearance_description

logger = logging.getLogger(__name__)


# Fixed slot character budgets (Runway weights early tokens more heavily)
SLOT_BUDGETS = {
    "character_state": 210,      # Cast guard + visual canon + shot-specific staging
    "action": 110,                # One action per shot, not multiple
    "environment_persistence": 100,  # Recurring motifs/settings that must not drop out
    "camera": 70,                 # Controlled vocabulary: wide/medium/close, static/dolly/pan
    "lighting": 60,               # Controlled vocabulary where possible
    "reserve": 32,                # Unallocated headroom for corrections later
}

# Legacy preview/adherence display ceiling, not a verified vendor maximum.
# Slots total 582 before separators/suffixes and historically clipped later
# lighting and severed individual facts. RenderService.create_job collects
# losslessly; prompt_budget_service applies the final provider policy once all
# corrections and continuity facts have been assembled.
#
# Canonical-creative-integrity rule (Multi Shot audit, Phase 1):
# build_shot_aware_prompt — the storyboard regeneration path — MUST NOT cut the
# canonical prompt at this ceiling or any other. A prompt longer than a
# provider budget is an explicit readiness concern handled by
# prompt_budget_service (fail-closed) at job creation, never a silent edit of
# canonical creative content. This constant now bounds only the standalone
# slotted PREVIEW assembly (build_slotted_prompt), which is a UI display
# surface, not the canonical board prompt.
MAX_PROMPT_LENGTH = 512


# Shot framing templates by position
SHOT_FRAMING_BY_POSITION = {
    1: "Wide establishing shot. Camera far back. Full environment visible. Characters small in frame. Sets the location and mood.",
    2: "Medium shot. Characters from waist up. Action and dialogue beginning. Environment still visible but characters dominant.",
    3: "Medium close-up. Character faces and upper body. Emotional beats. Reaction shots.",
    4: "Close-up or detail shot. Eyes, hands, specific objects. Intimate or tense moments.",
}

# Shot framing templates by script tag type
SHOT_FRAMING_BY_TAG = {
    "S.H.": "Establishing wide shot",  # Scene Heading
    "ACT": "Dynamic medium shot showing the action described",  # Action
    "CHR": "Character introduction shot, medium close on the named character",  # Character cue
    "DLG": "Over-the-shoulder or two-shot framing for conversation",  # Dialogue
    "PAR": "Close-up on expression or action described in parenthetical",  # Parenthetical
    "TRN": "Wide shot preparing for scene change, often environmental",  # Transition
}

# Take variation instructions
TAKE_VARIATIONS = {
    1: "",  # Primary composition
    2: "Alternative angle: camera positioned 90 degrees from primary shot.",
    3: "Tighter framing: push in 30% closer than primary shot.",
}


def _classify_script_line_tag(line: str) -> Optional[str]:
    """
    Classify a script line by its tag type.
    
    Returns one of: S.H., ACT, CHR, DLG, PAR, TRN, or None
    """
    line = line.strip()
    
    # S.H. (Scene Heading) — starts with INT. or EXT.
    if re.match(r"^(INT\.|EXT\.)", line, re.IGNORECASE):
        return "S.H."
    
    # CHR (Character cue) — ALL CAPS name followed by dialogue or action
    if re.match(r"^[A-Z][A-Z\s\.\-\']{2,40}$", line) and not line.startswith("("):
        return "CHR"
    
    # PAR (Parenthetical) — (action or emotion)
    if line.startswith("(") and line.endswith(")"):
        return "PAR"
    
    # TRN (Transition) — FADE IN, CUT TO, etc.
    if re.match(r"^(FADE|CUT|DISSOLVE|WIPE)", line, re.IGNORECASE):
        return "TRN"
    
    # DLG (Dialogue) — mixed case, follows character cue
    if re.search(r"[a-z]", line) and not re.match(r"^[A-Z][A-Z\s\.\']{2,}", line):
        return "DLG"
    
    # ACT (Action) — default for other mixed-case lines
    if re.search(r"[a-z]", line):
        return "ACT"
    
    return None


def _segment_scene_text(scene_text: str, num_shots: int) -> list[str]:
    """
    Segment scene text into approximately equal chunks for each shot.
    
    Each segment should contain relevant action and dialogue for that shot.
    Returns list of text segments, one per shot.
    """
    if not scene_text or not scene_text.strip():
        return [""] * num_shots
    
    lines = [line.strip() for line in scene_text.split("\n") if line.strip()]
    
    # Filter out scene headings and transitions (they belong to Shot 1)
    content_lines = []
    heading_lines = []
    
    for line in lines:
        tag = _classify_script_line_tag(line)
        if tag in ("S.H.", "TRN"):
            heading_lines.append(line)
        else:
            content_lines.append(line)
    
    # If only 1 shot, return full text
    if num_shots == 1:
        return ["\n".join(heading_lines + content_lines)]
    
    # Distribute content lines across shots
    lines_per_shot = max(1, len(content_lines) // num_shots)
    segments = []
    
    for i in range(num_shots):
        start_idx = i * lines_per_shot
        end_idx = start_idx + lines_per_shot if i < num_shots - 1 else len(content_lines)
        
        # Shot 1 gets the heading
        if i == 0:
            shot_lines = heading_lines + content_lines[start_idx:end_idx]
        else:
            shot_lines = content_lines[start_idx:end_idx]
        
        segments.append("\n".join(shot_lines))
    
    return segments


def _extract_characters_from_segment(segment: str, all_characters: list[dict]) -> list[dict]:
    """
    Extract only characters mentioned in this segment.

    Returns list of character dicts with name and visual_prompt_summary.

    A name must match on a word boundary: a bare substring check cast "MOM" as
    a scene_002 character because the word "moment" contains "mom" (Multi Shot
    audit, cross-scene character leakage). Names are also matched case-
    sensitively on their stored form first (MOM vs. the lowercase word "mom"
    in prose) and case-insensitively only on whole words, so real dialogue
    cues like "Mom sets down her tea." still resolve.
    """
    if not all_characters or not segment:
        return []
    
    mentioned_characters = []
    
    for char in all_characters:
        char_name = char.get("name", "")
        if not char_name:
            continue
        
        pattern = rf"\b{re.escape(str(char_name).strip())}\b"
        if re.search(pattern, segment) or re.search(pattern, segment, re.IGNORECASE):
            mentioned_characters.append({
                "name": char_name,
                "visual_prompt_summary": appearance_description(char) if appearance_approval(char).get("status") == "locked" else char.get("visual_prompt_summary", ""),
                "age": char.get("age", ""),
            })
    
    return mentioned_characters


def _scene_character_names(scene_data: dict) -> set[str]:
    raw = scene_data.get("characters") or scene_data.get("character_appearances") or []
    if isinstance(raw, str):
        return {part.strip().lower() for part in raw.split(",") if part.strip()}
    if isinstance(raw, list):
        return {str(part).strip().lower() for part in raw if str(part).strip()}
    return set()


def _merge_scene_characters(
    segment_characters: list[dict],
    scene_data: dict,
    all_characters: list[dict],
) -> list[dict]:
    scene_names = _scene_character_names(scene_data)
    if not scene_names:
        return segment_characters

    merged = list(segment_characters)
    seen = {
        str(char.get("name") or "").strip().lower()
        for char in merged
        if str(char.get("name") or "").strip()
    }
    for char in all_characters:
        char_name = str(char.get("name") or "").strip()
        normalized = char_name.lower()
        if normalized and normalized in scene_names and normalized not in seen:
            merged.append({
                "name": char_name,
                "visual_prompt_summary": appearance_description(char) if appearance_approval(char).get("status") == "locked" else char.get("visual_prompt_summary", ""),
                "age": char.get("age", ""),
            })
            seen.add(normalized)
    return merged


def locked_appearance_characters(all_characters: list[dict] | None) -> list[dict]:
    """Return only characters with an approved (locked) appearance."""
    locked: list[dict] = []
    for char in all_characters or []:
        if not isinstance(char, dict):
            continue
        try:
            if appearance_approval(char).get("status") == "locked":
                locked.append(char)
        except Exception:
            continue
    return locked


def _match_locked_by_name(names: list[str] | None, locked: list[dict]) -> list[dict]:
    """Intersect an explicit name list with the locked characters.

    Matching is case-insensitive on the stored name. Order follows the input
    name list (shot relevance), never storage order, and duplicates collapse.
    """
    by_name: dict[str, dict] = {}
    for char in locked:
        if not isinstance(char, dict):
            continue
        key = str(char.get("name") or "").strip().lower()
        if key and key not in by_name:
            by_name[key] = char
    selected: list[dict] = []
    seen: set[str] = set()
    for raw in names or []:
        key = str(raw or "").strip().lower()
        if key in by_name and key not in seen:
            seen.add(key)
            selected.append(by_name[key])
    return selected


def _appearance_only_text(char: dict) -> str:
    """Render one block entry from appearance fields only, never staging.

    The locked approval description joins age + look + the reference-image
    prompt (visual_prompt_summary), whose staging sentences (a rooftop, a
    garden, an auto shop) contradict the shot's own scene. The block only
    needs the drift guard tokens — age, race/skin-tone, hair — which live in
    the look. Falls back to the full description only when no look exists.
    """
    name = str(char.get("name") or "").strip() or "character"
    age = str(char.get("age") or "").strip()
    look = str(char.get("look") or char.get("appearance_core") or "").strip()
    if not look:
        try:
            profile = appearance_approval(char).get("profile")
        except Exception:
            profile = None
        if isinstance(profile, dict):
            look = str(profile.get("look") or "").strip()
    if not look:
        try:
            look = str(appearance_description(char) or "").strip()
        except Exception:
            look = str(char.get("visual_prompt_summary") or "").strip()
    if look and age:
        return f"{name} ({age}): {look}"
    if look:
        return f"{name}: {look}"
    return name


def _scene_id_for_log(scene_data: dict | None) -> str:
    try:
        return str((scene_data or {}).get("scene_id") or "")
    except Exception:
        return ""


def build_locked_appearance_block(
    all_characters: list[dict] | None,
    scene_data: dict | None = None,
    max_characters: int | None = None,
    *,
    shot_characters: list[str] | None = None,
    shot_text: str | None = None,
    scene_shot_texts: list[str] | None = None,
) -> str:
    """Build a non-truncatable enforcement block for locked character looks.

    Covers the storyboard race-drift gap: the per-segment prompt only injects
    a character when their name appears in the shot text or scene cast list,
    so a locked look can silently drop out (pronouns, typos, empty cast).
    This block lists locked looks explicitly with a do-not-change directive
    so the image provider always receives race/skin-tone/age/gender tokens.
    Returns "" when nothing is locked.

    Selection precedence (first non-empty scope wins):
      1. shot_characters — names assigned to this shot (e.g. intent focus).
      2. the scene's declared cast (scene_data characters).
      3. locked characters named in shot_text.
      4. locked characters named in ANY shot of the scene (scene_shot_texts
         union) — a stage-log note records that this fallback fired.
      5. empty block plus a warning log. An empty block is preferable to the
         wrong characters: other scenes' locked faces must never leak in.

    There is deliberately no alphabetical truncation: every in-scope locked
    character is included. max_characters is honored only when explicitly
    passed (legacy callers); the default selects the whole scope.
    """
    locked = locked_appearance_characters(all_characters)
    if not locked:
        return ""
    scene_id = _scene_id_for_log(scene_data)
    selected: list[dict] = []
    scope = "none"
    # 1. Shot-assigned characters.
    if shot_characters:
        selected = _match_locked_by_name(list(shot_characters), locked)
        if selected:
            scope = "shot"
    # 2. Scene-declared cast.
    if not selected and isinstance(scene_data, dict):
        try:
            names = _scene_character_names(scene_data)
        except Exception:
            names = set()
        if names:
            scoped = [
                c for c in locked
                if str(c.get("name") or "").strip().lower() in names
            ]
            if scoped:
                selected = scoped
                scope = "scene_cast"
    # 3. Locked characters named in this shot's text.
    if not selected and shot_text:
        try:
            extracted = _extract_characters_from_segment(str(shot_text), locked)
        except Exception:
            extracted = []
        matched = _match_locked_by_name(
            [str(item.get("name") or "") for item in extracted], locked
        )
        if matched:
            selected = matched
            scope = "shot_text"
    # 4. Scene-level union: locked characters named in any shot of the scene.
    if not selected and scene_shot_texts:
        union_names: list[str] = []
        for text in scene_shot_texts:
            try:
                extracted = _extract_characters_from_segment(str(text or ""), locked)
            except Exception:
                continue
            union_names.extend(str(item.get("name") or "") for item in extracted)
        matched = _match_locked_by_name(union_names, locked)
        if matched:
            selected = matched
            scope = "scene_union"
            logger.info(
                "LOCKED_APPEARANCE_SCOPE | scope=scene_union | characters=%s | scene=%s",
                [str(c.get("name")) for c in selected],
                scene_id or "unknown",
            )
    if not selected:
        logger.warning(
            "LOCKED_APPEARANCE_EMPTY | no shot, cast, or text source named a locked character | scene=%s",
            scene_id or "unknown",
        )
        return ""
    if max_characters is not None:
        selected = selected[:max(1, max_characters)]
    parts = [_appearance_only_text(char) for char in selected if isinstance(char, dict)]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    if scope in ("shot", "shot_text", "scene_cast", "scene_union"):
        logger.info(
            "LOCKED_APPEARANCE_SCOPE | scope=%s | characters=%s | scene=%s",
            scope,
            [str(c.get("name")) for c in selected],
            scene_id or "unknown",
        )
    joined = "; ".join(parts)
    return (
        "Locked appearance - maintain exact look, do not change race, "
        f"skin tone, age, or gender: {joined}"
    )


def ensure_locked_appearance_in_prompt(
    prompt: str | None,
    all_characters: list[dict] | None,
    scene_data: dict | None = None,
    *,
    shot_characters: list[str] | None = None,
    shot_text: str | None = None,
    scene_shot_texts: list[str] | None = None,
) -> str:
    """Append the locked-appearance block when missing. Never truncates."""
    base = str(prompt or "").strip()
    if shot_characters is None and shot_text is None:
        # Scope from the text being ensured: its Characters line and prose
        # name this shot's cast more reliably than the project-wide list.
        shot_text = base
    block = build_locked_appearance_block(
        all_characters,
        scene_data,
        shot_characters=shot_characters,
        shot_text=shot_text,
        scene_shot_texts=scene_shot_texts,
    )
    if not block or "Locked appearance" in base:
        return base
    if not base:
        return f"{block}."
    return f"{base.rstrip('. ')}. {block}."



def _format_visible_cast_constraint(character_names: list[str]) -> str:
    """Build a compact cast guard for image/video providers."""
    names = [str(name or "").strip() for name in character_names if str(name or "").strip()]
    if not names:
        return ""
    joined = " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + f", and {names[-1]}"
    return f"Only {joined} visible. No extras."


def _determine_shot_type(shot_number: int, segment: str) -> str:
    """
    Determine the cinematically appropriate shot type description.
    
    Priority:
    1. Shot position for Shot 1 (always wide establishing)
    2. Script tag type (if identifiable)
    3. Shot position fallback
    """
    # Shot 1 is ALWAYS wide establishing regardless of content
    if shot_number == 1:
        return SHOT_FRAMING_BY_POSITION[1]
    
    # Check for dominant script tag in segment
    lines = [line.strip() for line in segment.split("\n") if line.strip()]
    tag_counts = {}
    
    for line in lines:
        tag = _classify_script_line_tag(line)
        if tag:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Use most common tag if present
    if tag_counts:
        dominant_tag = max(tag_counts, key=tag_counts.get)
        if dominant_tag in SHOT_FRAMING_BY_TAG:
            return SHOT_FRAMING_BY_TAG[dominant_tag]
    
    # Fall back to position-based framing
    if shot_number in SHOT_FRAMING_BY_POSITION:
        return SHOT_FRAMING_BY_POSITION[shot_number]
    
    # Shot 4+ defaults to close-up
    return SHOT_FRAMING_BY_POSITION[4]


def resolve_total_shots(
    scene_data: dict,
    shot_number: int,
    explicit_total: int | None = None,
) -> int:
    """Determine how many shots this scene is actually broken into.

    Scene text is segmented evenly across the shot count, so getting this wrong
    hands most shots the wrong beat: with a hardcoded assumption of 3, shot 2 of
    a 6-shot scene receives the action text belonging to roughly shot 3, and the
    prompt is then confidently, precisely about the wrong moment. Adherence
    scoring compares the render against that prompt and happily confirms a match.

    Resolution order:
      1. An explicit count passed by the caller.
      2. A count carried on the scene dict (`shot_count` / `total_shots`, or the
         length of a `shots` list) — both shapes exist in project state.
      3. The legacy `max(shot_number, 3)` heuristic, as a last resort.
    """
    if explicit_total and explicit_total > 0:
        return max(int(explicit_total), shot_number)

    if isinstance(scene_data, dict):
        for key in ("shot_count", "total_shots", "num_shots"):
            raw = scene_data.get(key)
            try:
                candidate = int(raw)
            except (TypeError, ValueError):
                continue
            if candidate > 0:
                return max(candidate, shot_number)

        shots = scene_data.get("shots")
        if isinstance(shots, list) and shots:
            return max(len(shots), shot_number)

    return max(shot_number, 3)


def build_shot_aware_prompt(
    scene_data: dict,
    shot_number: int,
    take_number: int,
    all_characters: list[dict] | None = None,
    audio_brief: dict | None = None,
    performance_context: dict | None = None,
    max_length: int | None = None,
    total_shots: int | None = None,
) -> str:
    """
    Build a shot-aware prompt for previs generation.

    Args:
        scene_data: Scene dict with text, location, time_of_day, emotional_tone, etc.
        shot_number: Shot number (1-based)
        take_number: Take number (1-based)
        all_characters: List of character dicts from project (optional)
        audio_brief: Audio context dict (optional)
        performance_context: Provider-neutral acting context with visible prompt lines (optional)
        max_length: Deprecated. Accepted for call compatibility and ignored:
            canonical prompts are never truncated by this builder. Provider
            budgets are enforced explicitly by prompt_budget_service.
        total_shots: Real number of shots in this scene. Falls back to the scene
            dict, then to a heuristic, when not supplied.

    Returns:
        Formatted prompt string following cinematic structure
    """
    scene_text = scene_data.get("text") or scene_data.get("script") or scene_data.get("description") or ""
    location = scene_data.get("location") or ""
    time_of_day = scene_data.get("time_of_day") or ""
    emotional_tone = scene_data.get("emotional_tone") or ""
    
    # Determine how many shots this scene is actually cut into, so the scene text
    # is segmented against the real breakdown rather than an assumed one.
    resolved_total_shots = resolve_total_shots(scene_data, shot_number, total_shots)

    # Segment scene text by shot
    segments = _segment_scene_text(scene_text, resolved_total_shots)
    shot_segment = segments[shot_number - 1] if shot_number <= len(segments) else ""
    
    # Determine shot type
    shot_type_desc = _determine_shot_type(shot_number, shot_segment)
    
    # Extract characters mentioned in this segment
    segment_characters = _extract_characters_from_segment(
        shot_segment,
        all_characters or []
    )
    segment_characters = _merge_scene_characters(
        segment_characters,
        scene_data,
        all_characters or [],
    )
    
    # Build prompt components
    parts = []
    
    # 1. Shot type description
    parts.append(shot_type_desc)
    
    # 2. Location and time of day
    if location and time_of_day:
        parts.append(f"{location}, {time_of_day}")
    elif location:
        parts.append(location)
    
    # 3. Relevant action segment
    if shot_segment:
        # Extract first 2 action lines
        action_lines = [
            line for line in shot_segment.split("\n")
            if _classify_script_line_tag(line) in ("ACT", "DLG", None)
        ]
        action_text = " ".join(action_lines[:2])
        if action_text:
            parts.append(action_text)
    
    # 4. Relevant characters with visual descriptions
    if segment_characters:
        visible_cast = _format_visible_cast_constraint(
            [str(char.get("name") or "") for char in segment_characters]
        )
        if visible_cast:
            parts.append(visible_cast)
        char_descs = []
        for char in segment_characters[:3]:  # Max 3 characters to avoid bloat
            name = char["name"]
            age = char.get("age", "")
            visual = char.get("visual_prompt_summary", "")
            if visual:
                char_descs.append(f"{name} ({age}): {visual}" if age else f"{name}: {visual}")
            elif age:
                char_descs.append(f"{name} ({age})")
            else:
                char_descs.append(name)
        if char_descs:
            parts.append("Characters: " + ", ".join(char_descs))
    
    # 5. Camera direction (from shot type)
    # Already embedded in shot_type_desc
    
    # 6. Mood/lighting from audio brief
    if audio_brief and "mood" in audio_brief:
        parts.append(f"Mood: {audio_brief['mood']}")
    elif emotional_tone:
        parts.append(f"Mood: {emotional_tone}")

    # 7. Performance Intelligence context: visible behavior only.
    # Motivation/subtext stays in the reasoning layer; render prompts get playable action.
    if isinstance(performance_context, dict):
        prompt_lines = performance_context.get("prompt_lines")
        if isinstance(prompt_lines, list):
            visible_lines = [str(line).strip() for line in prompt_lines if str(line).strip()]
            if visible_lines:
                parts.append("Performance: " + " ".join(visible_lines[:2]))
    
    # 8. Style suffix
    parts.append("Cinematic, film quality, single continuous shot.")
    
    # Join parts
    base_prompt = ". ".join(parts)
    
    # 8. Take variation (append for Take 2+)
    take_variation = TAKE_VARIATIONS.get(take_number, "")
    if take_variation:
        base_prompt += f" {take_variation}"
    
    # No truncation here. Canonical prompts are never silently cut to satisfy
    # a provider budget; prompt_budget_service enforces the provider limit
    # explicitly (fail-closed) at job creation with full provenance.

    # Locked looks are non-truncatable: append after assembly so race /
    # skin-tone tokens survive even when the scene text is long. No-op when
    # nothing is locked or the Characters line already carried the block.
    # The block is scoped to this shot's segment cast (falling back to the
    # scene-wide shot union), never the project-wide alphabetical list.
    try:
        base_prompt = ensure_locked_appearance_in_prompt(
            base_prompt,
            all_characters,
            scene_data,
            shot_characters=[
                str(char.get("name") or "")
                for char in (segment_characters or [])
                if str(char.get("name") or "").strip()
            ],
            scene_shot_texts=segments,
        )
    except Exception:
        pass
    
    logger.info(
        "SHOT_PROMPT_BUILT | shot=%d | take=%d | length=%d | type=%s",
        shot_number,
        take_number,
        len(base_prompt),
        shot_type_desc[:50],
    )
    
    return base_prompt


def get_shot_type_label(shot_number: int) -> str:
    """
    Get a short label for the shot type (for UI display).
    
    Returns: "WIDE", "MEDIUM", "CLOSE", or "DETAIL"
    """
    if shot_number == 1:
        return "WIDE"
    elif shot_number == 2:
        return "MEDIUM"
    elif shot_number == 3:
        return "CLOSE"
    else:
        return "DETAIL"


def _truncate_to_budget(text: str, budget: int) -> str:
    """Truncate text to fit within character budget."""
    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get():
        return text
    if len(text) <= budget:
        return text
    return text[:budget - 3] + "..."


def _compress_character_segment(segment: str, budget: int) -> str:
    """Compress one character segment while preserving shot-specific staging."""
    segment = segment.strip()
    if len(segment) <= budget:
        return segment

    marker = "In this shot:"
    if marker in segment:
        name = segment.split(":", 1)[0].strip()
        staging = segment.split(marker, 1)[1].strip()
        if name and staging:
            return _truncate_to_budget(f"{name}: {marker} {staging}", budget)

    return _truncate_to_budget(segment, budget)


def _fit_character_state_to_budget(text: str, budget: int) -> str:
    """Fit character_state without allowing early cast members to erase later ones."""
    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get():
        return text
    if len(text) <= budget:
        return text

    segments = [segment.strip() for segment in text.split(";") if segment.strip()]
    if (
        len(segments) >= 2
        and segments[0].startswith("Only ")
        and segments[1].strip().lower() in {"no extras", "no extras."}
    ):
        segments = [f"{segments[0]}; {segments[1]}", *segments[2:]]
    if len(segments) <= 1:
        return _truncate_to_budget(text, budget)

    separator_len = 2 * (len(segments) - 1)
    segment_budget = max(24, (budget - separator_len) // len(segments))
    compressed = [
        _compress_character_segment(segment, segment_budget)
        for segment in segments
    ]
    joined = "; ".join(compressed)
    if len(joined) <= budget:
        return joined

    while len(joined) > budget and segment_budget > 24:
        segment_budget -= 1
        compressed = [
            _compress_character_segment(segment, segment_budget)
            for segment in segments
        ]
        joined = "; ".join(compressed)

    return joined if len(joined) <= budget else _truncate_to_budget(joined, budget)


_SLOT_ASSEMBLY_ORDER = (
    "character_state",
    "action",
    "environment_persistence",
    "camera",
    "lighting",
)


def merge_identity_guidance_into_slots(slots: dict, guidance: str) -> None:
    """Fold identity guidance into the character_state slot, in place.

    Reconstructed 2026-08-25. render.py imported this (and
    merge_knowledge_guidance_into_slots below) from two call sites, but neither
    was ever defined here -- create_job raised ImportError on any shot that
    carried identity guidance, and the knowledge call only survived because its
    caller wrapped it in try/except. Both are kept deliberately conservative:
    they ADD guidance to the identity/target slot within that slot's existing
    budget and never when the text is already present, so they can only enrich a
    slot, never blank or reorder one.
    """
    if not isinstance(slots, dict):
        return
    text = " ".join(str(guidance or "").split())
    if not text:
        return
    current = str(slots.get("character_state") or "").strip()
    if text in current:
        return
    combined = f"{current}; {text}" if current else text
    slots["character_state"] = _truncate_to_budget(
        combined, SLOT_BUDGETS["character_state"]
    )


def merge_knowledge_guidance_into_slots(slots: dict, slot_guidance: dict) -> None:
    """Fold per-slot department/knowledge guidance into matching slots, in place.

    slot_guidance maps a slot name to guidance text. Each entry is appended to
    its slot within budget, never duplicated; unknown slot names and the reserve
    slot are ignored. See merge_identity_guidance_into_slots for why this exists.
    """
    if not isinstance(slots, dict) or not isinstance(slot_guidance, dict):
        return
    for slot_name, guidance in slot_guidance.items():
        if slot_name not in SLOT_BUDGETS or slot_name == "reserve":
            continue
        text = " ".join(str(guidance or "").split())
        if not text:
            continue
        current = str(slots.get(slot_name) or "").strip()
        if text in current:
            continue
        combined = f"{current}; {text}" if current else text
        slots[slot_name] = _truncate_to_budget(combined, SLOT_BUDGETS[slot_name])


def reassemble_prompt_from_slots(slots: dict) -> str:
    """Re-assemble prompt string from a slots dict.

    Shared by build_slotted_prompt and post-injection re-assembly so there
    is a single prompt-construction path, not a parallel one.
    """
    parts = [slots[s] for s in _SLOT_ASSEMBLY_ORDER if slots.get(s)]
    if parts:
        base_prompt = ". ".join(parts) + ". Cinematic, film quality."
    else:
        base_prompt = "Cinematic shot. Film quality."
    from app.prompt_assembly_context import collecting_generation_prompt
    if not collecting_generation_prompt.get() and len(base_prompt) > MAX_PROMPT_LENGTH - SLOT_BUDGETS["reserve"]:
        base_prompt = base_prompt[:MAX_PROMPT_LENGTH - SLOT_BUDGETS["reserve"] - 3] + "..."
    return base_prompt


def build_slotted_prompt(
    scene_data: dict,
    shot_number: int,
    character_visual_canon: str = "",
    action_text: str = "",
    environment_motifs: str = "",
    camera_direction: str = "",
    lighting_direction: str = "",
) -> dict:
    """
    Build a fixed-slot prompt with strict character budgets.
    
    Slots are assembled in priority order (most-emphasized first, as Runway weights early tokens more):
    1. character_state (140 chars) - visual canon only, no character names
    2. action (110 chars) - one action per shot
    3. environment_persistence (100 chars) - recurring motifs/settings
    4. camera (70 chars) - controlled vocabulary
    5. lighting (60 chars) - controlled vocabulary
    6. reserve (32 chars) - unallocated headroom for corrections
    
    Args:
        scene_data: Scene dict with metadata
        shot_number: Shot number (1-based)
        character_visual_canon: Visual description of characters (hands, face, build)
        action_text: Primary action for this shot
        environment_motifs: Recurring environmental elements
        camera_direction: Camera framing/movement
        lighting_direction: Lighting mood/style
    
    Returns:
        dict with:
            - "prompt": assembled prompt string (<=512 chars)
            - "slots": dict of {slot_name: text} for slot-level addressing
            - "budget_used": total characters used
            - "source_slots": slot text before budget compression, for the
              intent-fidelity check
            - "defaulted_slots": slots filled from a builder template rather than
              caller input, which the intent-fidelity check ignores
            - "budget_remaining": characters remaining
    """
    from app.services.script_parser import sanitize_render_slot
    
    # Build slots with budget enforcement.
    #
    # `source_slots` holds each slot sanitized but NOT yet compressed. It is the
    # last point at which the director's intent is still intact: everything after
    # this is budget enforcement, which silently removes text. Keeping it lets the
    # intent-fidelity check measure exactly what compression took out, instead of
    # trying to reconstruct it after the fact.
    slots = {}
    source_slots = {}
    # Slots the builder filled from a built-in template because the caller
    # supplied nothing. Compressing a default is not losing the director's
    # intent — there was none to lose — so the intent-fidelity check skips these.
    # Without this, the camera default (longer than its 70-char budget) would
    # report a loss on almost every shot and the signal would be worthless.
    defaulted_slots: list[str] = []
    
    # 1. character_state (140 chars) - visual canon only
    if character_visual_canon:
        sanitized = sanitize_render_slot("character_state", character_visual_canon)
        source_slots["character_state"] = sanitized
        slots["character_state"] = _fit_character_state_to_budget(
            sanitized,
            SLOT_BUDGETS["character_state"],
        )
    else:
        source_slots["character_state"] = ""
        slots["character_state"] = ""
    
    # 2. action (110 chars) - one action per shot
    if action_text:
        sanitized = sanitize_render_slot("action", action_text)
        source_slots["action"] = sanitized
        slots["action"] = _truncate_to_budget(sanitized, SLOT_BUDGETS["action"])
    else:
        source_slots["action"] = ""
        slots["action"] = ""
    
    # 3. environment_persistence (100 chars) - recurring motifs
    if environment_motifs:
        sanitized = sanitize_render_slot("environment_persistence", environment_motifs)
        source_slots["environment_persistence"] = sanitized
        slots["environment_persistence"] = _truncate_to_budget(sanitized, SLOT_BUDGETS["environment_persistence"])
    else:
        source_slots["environment_persistence"] = ""
        slots["environment_persistence"] = ""
    
    # 4. camera (70 chars) - controlled vocabulary
    if camera_direction:
        sanitized = sanitize_render_slot("camera", camera_direction)
        source_slots["camera"] = sanitized
        slots["camera"] = _truncate_to_budget(sanitized, SLOT_BUDGETS["camera"])
    else:
        # Default based on shot number
        shot_type = _determine_shot_type(shot_number, "")
        source_slots["camera"] = shot_type
        # Template explanations are optional; select complete sentences rather
        # than emitting a severed default such as "R...". Creator camera text
        # above remains intact for the final provider budget.
        default_camera_parts = []
        for sentence in re.split(r"(?<=[.!?])\s+", shot_type):
            candidate = " ".join(default_camera_parts + [sentence])
            if len(candidate) > SLOT_BUDGETS["camera"]:
                break
            default_camera_parts.append(sentence)
        slots["camera"] = " ".join(default_camera_parts) or shot_type
        defaulted_slots.append("camera")
    
    # 5. lighting (60 chars) - controlled vocabulary
    if lighting_direction:
        sanitized = sanitize_render_slot("lighting", lighting_direction)
        source_slots["lighting"] = sanitized
        slots["lighting"] = _truncate_to_budget(sanitized, SLOT_BUDGETS["lighting"])
    else:
        source_slots["lighting"] = ""
        slots["lighting"] = ""
    
    # 6. reserve (32 chars) - leave empty for now (correction headroom)
    source_slots["reserve"] = ""
    slots["reserve"] = ""
    
    # Assemble prompt from non-empty slots (shared reassembly path)
    base_prompt = reassemble_prompt_from_slots(slots)
    
    budget_used = len(base_prompt)
    budget_remaining = MAX_PROMPT_LENGTH - budget_used
    
    logger.info(
        "SLOTTED_PROMPT_BUILT | shot=%d | budget_used=%d | budget_remaining=%d",
        shot_number,
        budget_used,
        budget_remaining,
    )
    
    return {
        "prompt": base_prompt,
        "slots": slots,
        "source_slots": source_slots,
        "defaulted_slots": defaulted_slots,
        "budget_used": budget_used,
        "budget_remaining": budget_remaining,
    }
