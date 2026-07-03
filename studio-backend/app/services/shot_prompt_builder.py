"""
Shot-aware prompt builder for previs generation.

Generates unique, cinematically intelligent prompts for each shot/take combination
based on shot position, script tag type, and take variation.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


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
    """
    if not all_characters or not segment:
        return []
    
    segment_lower = segment.lower()
    mentioned_characters = []
    
    for char in all_characters:
        char_name = char.get("name", "")
        if not char_name:
            continue
        
        # Check if character name appears in segment
        if char_name.lower() in segment_lower:
            mentioned_characters.append({
                "name": char_name,
                "visual_prompt_summary": char.get("visual_prompt_summary", ""),
                "age": char.get("age", ""),
            })
    
    return mentioned_characters


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


def build_shot_aware_prompt(
    scene_data: dict,
    shot_number: int,
    take_number: int,
    all_characters: list[dict] | None = None,
    audio_brief: dict | None = None,
    max_length: int = 512,
) -> str:
    """
    Build a shot-aware prompt for previs generation.
    
    Args:
        scene_data: Scene dict with text, location, time_of_day, emotional_tone, etc.
        shot_number: Shot number (1-based)
        take_number: Take number (1-based)
        all_characters: List of character dicts from project (optional)
        audio_brief: Audio context dict (optional)
        max_length: Max prompt length (default 512 for Runway)
    
    Returns:
        Formatted prompt string following cinematic structure
    """
    scene_text = scene_data.get("text") or scene_data.get("script") or scene_data.get("description") or ""
    location = scene_data.get("location") or ""
    time_of_day = scene_data.get("time_of_day") or ""
    emotional_tone = scene_data.get("emotional_tone") or ""
    
    # Determine total shots from scene (or assume based on shot_number)
    # This is a heuristic — frontend should pass total_shots if available
    total_shots = max(shot_number, 3)  # Assume at least 3 shots if not specified
    
    # Segment scene text by shot
    segments = _segment_scene_text(scene_text, total_shots)
    shot_segment = segments[shot_number - 1] if shot_number <= len(segments) else ""
    
    # Determine shot type
    shot_type_desc = _determine_shot_type(shot_number, shot_segment)
    
    # Extract characters mentioned in this segment
    segment_characters = _extract_characters_from_segment(
        shot_segment,
        all_characters or []
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
    
    # 7. Style suffix
    parts.append("Cinematic, film quality, single continuous shot.")
    
    # Join parts
    base_prompt = ". ".join(parts)
    
    # 8. Take variation (append for Take 2+)
    take_variation = TAKE_VARIATIONS.get(take_number, "")
    if take_variation:
        base_prompt += f" {take_variation}"
    
    # Truncate if needed
    if len(base_prompt) > max_length:
        base_prompt = base_prompt[:max_length - 3] + "..."
    
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
