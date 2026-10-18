"""Phase 2/6 — scene segmentation must stop at the canonical scene boundary.

Reproduces the scene_002 contamination found by the Multi Shot integrity audit.

The canonical screenplay for "I was reborn" (project_5907c60cddbc) reads, in
order (verbatim from the project's canonical script_text):

    OPENING
    EXT. DOWNTOWN CHICAGO — GOLDEN HOUR
    ... CUT TO:
    EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE
    ... (the timeline confrontation, the killing, THE SECOND CHANCE) ...
    She sits with that for a long moment. Then something shifts behind her eyes.
    Not grief. Not rage. Clarity.
    DRE — BEFORE THE FALL          <- all-caps SECTION HEADER, not a heading
    INT. DRE'S APARTMENT — NIGHTMaya visits Dre. ...   <- scene_003's heading

scene_002 therefore ENDS at "Not grief. Not rage. Clarity." and the next scene
begins at "INT. DRE'S APARTMENT". "DRE — BEFORE THE FALL", "THE SECOND CHANCE",
and "THE FIRST TIMELINE" are all-caps section headers INSIDE the stored scene
text, not scene headings. The audit found two concrete leak vectors:

1. Prompt regeneration named a character whose name is a SUBSTRING of a word
   in the shot text ("MOM" matched inside "moment" in "a long moment."),
   because _extract_characters_from_segment used a bare ``in`` check instead of
   a word-boundary match. Shot prompts for scene_002 said "Only DRE, MAYA, and
   MOM visible" even though MOM never appears in the scene.
2. Scene text can terminate on a dangling all-caps section header ("DRE —
   BEFORE THE FALL") when the section is the last content before the next
   scene heading. That trailing header is narrative structure, not scene
   content, and must not survive into shot narrative_function / prompts.
"""
from __future__ import annotations

import pytest

from app.services.audio_pipeline_service import _extract_dialogue_lines
from app.services.script_parser import ScriptParser


# Verbatim canonical screenplay excerpt (script_text offsets 434-2330).
SCREENPLAY = (
    "OPENING\n"
    "EXT. DOWNTOWN CHICAGO — GOLDEN HOUR\n"
    "Chicago is alive. The L train moves through the skyline. People fill the streets. Music,\n"
    "laughter, families, restaurants, Lake Michigan reflecting the sunset.\n"
    "Maya walks through the city watching small moments people take for granted.\n"
    "MAYA (V.O.)\n"
    "People think the end of the world is fire. Buildings\n"
    "falling. Chaos. But the hardest part is remembering\n"
    "when it was beautiful.\n"
    "CUT TO:\n"
    "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE\n"
    "The same city. Different world. The L train is frozen. Buildings are cracked. Nature has\n"
    "reclaimed the streets. The skyline still stands, but Chicago feels like a graveyard.\n"
    "Maya walks through the ruins. She reaches the Chicago River. The place where she\n"
    "died.\n"
    "THE FIRST TIMELINE\n"
    "Maya is surrounded by the people she trusted. Dre, her closest friend, stands among\n"
    "them. His jaw is tight. He won't look her in the eyes.\n"
    "DRE\nI need you to understand something.\n"
    "MAYA\nThat's funny.\n"
    "DRE\nWhat?\n"
    "MAYA\nYou always say that right before you do something\nyou know is wrong.\n"
    "DRE\nThings changed.\n"
    "MAYA\nNo. People changed.\n"
    "DRE\n(raises the gun)\nThere's not enough. You have to understand that.\n"
    "There is not enough for everyone.\n"
    "MAYA\nSo you decided that for all of us.\n"
    "DRE\nSomeone had to.\n"
    "(pulls the trigger)\n"
    "Maya is killed. Darkness.\n"
    "We hold on Dre's face for a beat after the shot. He doesn't look relieved. He looks like\n"
    "a man who just chose scarcity over trust — and already knows the cost.\n"
    "THE SECOND CHANCE\n"
    "Maya wakes up. Two months before the apocalypse. She remembers everything. The\n"
    "betrayal. The death. The collapse.\n"
    "She looks out at Chicago while it is still alive. The L train runs. People laugh below her\n"
    "window.\n"
    "MAYA\nI remember dying. So why am I here?\n"
    "She sits with that for a long moment. Then something shifts behind her eyes. Not grief.\n"
    "Not rage. Clarity.\n"
    "DRE — BEFORE THE FALL\n"
    "INT. DRE'S APARTMENT — NIGHTMaya visits Dre. He doesn't know what she knows. To him, everything is still normal.\n"
    "He's cooking. Music playing. The apartment feels lived-in, warm.\n"
    "MAYA (V.O.)\n"
    "This is the version of him I want to remember.\n"
    "DRE\nYou good? You're looking at me weird.\n"
)

SCENE_002_CHARS = ["DRE", "MAYA"]


def _parsed() -> list[dict]:
    return ScriptParser().extract_structured_scenes(SCREENPLAY)["scenes"]


def test_scene_002_is_the_second_scene():
    parsed = _parsed()
    assert [s["scene_id"] for s in parsed][:3] == ["scene_001", "scene_002", "scene_003"]


def test_scene_002_text_is_deterministic():
    first = _parsed()
    second = _parsed()
    assert second[1]["text"] == first[1]["text"]


def test_scene_002_stops_at_the_correct_boundary():
    """scene_002 must contain its own content and NOTHING from scene_003."""
    text = _parsed()[1]["text"]
    # Own content present (the last line of the true scene).
    assert "Not grief." in text and "Clarity." in text
    # The next scene must not leak in.
    assert "INT. DRE'S APARTMENT" not in text
    assert "He's cooking" not in text
    assert "Maya visits Dre" not in text
    assert "You good?" not in text


def test_next_scene_does_not_leak_into_scene_002():
    scene_003_text = _parsed()[2]["text"]
    assert scene_003_text.startswith("He's cooking")
    assert "I remember dying" not in scene_003_text


def test_scene_002_characters_do_not_leak_across_scenes():
    """The 'DRE — BEFORE THE FALL' section header must not be parsed as a
    character cue for scene_002, and scene_003's dialogue must not leak back."""
    parsed = _parsed()
    assert set(parsed[1]["characters"]) == {"DRE", "MAYA"}
    lines_002 = _extract_dialogue_lines(parsed[1]["text"], characters=SCENE_002_CHARS)
    speakers = {line["character"] for line in lines_002}
    assert speakers <= {"DRE", "MAYA"}
    # The first scene_003 line must be attributed to scene_003, not scene_002.
    lines_003 = _extract_dialogue_lines(parsed[2]["text"], characters=["DRE", "MAYA"])
    assert any(line["text"].startswith("This is the version of him") for line in lines_003)
    assert not any(line["text"].startswith("This is the version of him") for line in lines_002)


def test_scene_version_hash_changes_when_text_is_corrected():
    """A corrected scene text must produce a different scene version/hash so
    downstream derived state is invalidated."""
    from app.services.generation_context_service import generation_context_service

    parsed = _parsed()
    contaminated = dict(parsed[1])
    corrected = dict(parsed[1])
    corrected["text"] = parsed[1]["text"].replace(
        "\nDRE — BEFORE THE FALL", ""
    ).rstrip() + "\n"
    corrected["description"] = corrected["text"]
    v_contaminated = generation_context_service.scene_version(contaminated)
    v_corrected = generation_context_service.scene_version(corrected)
    assert v_contaminated != v_corrected


def test_downstream_storyboard_receives_only_corrected_scene_text():
    """The storyboard prompt builder consumes exactly the scene dict it is
    handed — corrected scene text in, corrected shot segments out."""
    from app.services.shot_prompt_builder import build_shot_aware_prompt

    scene = dict(_parsed()[1])
    scene["location"] = scene.get("location") or "Downtown Chicago"
    scene["time_of_day"] = scene.get("time_of_day") or ""
    prompt = build_shot_aware_prompt(
        scene_data=scene, shot_number=1, take_number=1, total_shots=5
    )
    assert "INT. DRE'S APARTMENT" not in prompt
    assert "Maya visits Dre" not in prompt
    assert "You good?" not in prompt
    # The prompt narrative function must come from scene_002's own text.
    assert "The same city" in prompt


# ── Cross-scene character leakage: substring matches are not characters ──────


def _prompt_characters(scene: dict, project_characters: list[dict], total_shots: int = 5):
    from app.services import shot_prompt_builder as spb

    found: set[str] = set()
    text = scene.get("text") or ""
    for shot_number in range(1, total_shots + 1):
        prompt = spb.build_shot_aware_prompt(
            scene_data=scene,
            shot_number=shot_number,
            take_number=1,
            all_characters=project_characters,
            total_shots=total_shots,
        )
        visible = next(
            (part for part in prompt.split(". ") if part.startswith("Only ")),
            "",
        )
        for name in project_characters:
            if name.get("name", "").lower() in visible.lower():
                found.add(name["name"])
    # Characters genuinely present in the scene text (whole-word) must be found.
    for name in project_characters:
        if name.get("name", "") in text:
            found.add(name["name"])
    return found


def test_mom_is_not_a_scene_002_character_despite_substring_match():
    """'MOM' matched inside 'moment' via a bare substring check and entered the
    visible-cast guard of shots 3-5. Character mention detection must use word
    boundaries, so MOM is never a scene_002 character."""
    parsed = _parsed()
    scene = dict(parsed[1])
    project_characters = [
        {"name": "DRE", "age": "Early 30s", "visual_prompt_summary": "broad-shouldered"},
        {"name": "MAYA", "age": "Late 20s", "visual_prompt_summary": "lean"},
        {"name": "MOM", "age": "50s", "visual_prompt_summary": "warm"},
    ]
    found = _prompt_characters(scene, project_characters)
    assert "MOM" not in found
    assert {"DRE", "MAYA"} <= found


def test_shot_visible_cast_guard_never_names_substring_characters():
    """The 'Only ... visible. No extras.' guard across every shot segment of
    scene_002 must name exactly the scene cast — never a substring collision."""
    from app.services import shot_prompt_builder as spb

    parsed = _parsed()
    scene = dict(parsed[1])
    project_characters = [
        {"name": "DRE", "age": "", "visual_prompt_summary": ""},
        {"name": "MAYA", "age": "", "visual_prompt_summary": ""},
        {"name": "MOM", "age": "", "visual_prompt_summary": ""},
    ]
    for shot_number in range(1, 6):
        prompt = spb.build_shot_aware_prompt(
            scene_data=scene,
            shot_number=shot_number,
            take_number=1,
            all_characters=project_characters,
            total_shots=5,
        )
        guard = next(
            (part for part in prompt.split(". ") if part.startswith("Only ")),
            None,
        )
        if guard is None:
            continue
        assert "MOM" not in guard, f"shot {shot_number} leaked MOM into the cast guard"
