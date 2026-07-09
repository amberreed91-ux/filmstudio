"""Tests for dialogue extraction contamination fix.

Locks in the scene_002 line 9 case (78-word contaminated extraction must never
happen again) plus other real contaminated lines found during the full-dataset
re-run: the SUPPLIES false character cue, the FINAL CONFRONTATION false cue,
the vocative-address case ("Maya. You're my people. Always."), and the
COASTAL RENEWAL PROJECT false cue in The Last Tide.

These tests use the REAL stored scene text (with action/description lines that
have no blank-line separators from dialogue — the exact format that caused the
original contamination).
"""
from __future__ import annotations

from app.services.audio_pipeline_service import _extract_dialogue_lines


# ── Real scene text (verbatim from project_state_store.json) ─────────────────

SCENE_002_TEXT = (
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
    "DRE\n(raises the gun)\nThere's not enough. You have to understand that.\nThere is not enough for everyone.\n"
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
    "DRE — BEFORE THE FALL"
)
SCENE_002_CHARS = ["DRE", "MAYA"]

SCENE_003_TEXT = (
    "Maya visits Dre. He doesn't know what she knows. To him, everything is still normal.\n"
    "He's cooking. Music playing. The apartment feels lived-in, warm.\n"
    "She watches him from the doorway before he notices her.\n"
    "MAYA (V.O.)\nThis is the version of him I want to remember. The\n"
    "one who used to split his last twenty dollars with me at\n"
    "the gas station. The one who showed up when I\n"
    "needed him. That person was real. I have to believe\nthat.\n"
    "Dre turns and sees her.\n"
    "DRE\nYou good? You're looking at me weird.\n"
    "MAYA\nI'm fine. Just tired.\n"
    "DRE\nYou eat?\n"
    "MAYA\nYeah.\n"
    "He puts a plate in front of her anyway. She looks down at it. She knows that in two\n"
    "months this apartment will be stripped bare. She knows what hunger will do to him.\n"
    "MAYA\nHey. If something happened — something bad —\nyou'd tell me, right?\n"
    "DRE\nWhat kind of something?\n"
    "MAYA\nI don't know. Anything. Would you come to me?\n"
    "DRE\n(beat, easy smile)\nMaya. You're my people. Always.\n"
    "She nods. She almost believes him.\n"
    "THE COUNTDOWN\n"
    "Maya creates a survival blueprint. Food. Water. Power. Medical. Security. People.\n"
    "She writes two lists.\n"
    "The first list: names of people she will save.\n"
    "The second list: names she cannot. Dre's name is not on either list yet.\n"
    "She stares at both lists for a long time. Then she folds them and puts them away.\n"
    "THE HOMESTEAD\n"
    "EXT./INT. ABANDONED HIGH RISE, DOWNTOWN CHICAGO — DAY\n"
    "Maya finds an abandoned high rise in Downtown Chicago. A building everyone forgot.\n"
    "She sees a future inside it. She transforms it into a survival sanctuary.\n"
    "The rooftop becomes a farm. Hydroponics. Seeds. Rain collection. Winter preparation.\n"
    "The building gets solar power, batteries, generators, storage rooms, a medical area,\n"
    "security systems, and emergency exits.\n"
    "MAYA (V.O.)\nI'm not preparing for monsters. I'm preparing for\npeople. People are always the hardest part.\n"
    "SUPPLIES\n"
    "Maya collects supplies before the world knows it needs them. Food. Water filters.\n"
    "Medicine. Tools. Seeds. Preservation equipment. Repair materials.\n"
    "She learns how to maintain everything. Every decision matters because she knows\n"
    "time is running out.\n"
    "THE SUPPLY RUN — WHAT GOES WRONG"
)
SCENE_003_CHARS = ["DRE", "MAYA"]

SCENE_005_TEXT = (
    "She sits on the floor. Looks at what she saved. Then at the list of what she lost.\n"
    "MAYA\n(to herself)\nNot enough. It's never going to be enough.\n"
    "She stays there for a moment. Then she gets back up. She writes a new list. Different\n"
    "warehouses. Different approach. She adapts.\n"
    "THE CHOSEN — RECRUITMENT"
)
SCENE_005_CHARS = ["MAYA"]

TIDE_SCENE_005_TEXT = (
    "Mara walks along the wall.\n\n"
    "On one side, her neighborhood.\n\n"
    "On the other, glass houses with perfect ocean views.\n\n"
    "She looks at a sign:\n\n"
    "COASTAL RENEWAL PROJECT\n\n"
    "She laughs quietly.\n\n"
    "Not because it is funny.\n\n"
    "Because she understands."
)
TIDE_SCENE_005_CHARS: list[str] = []

SCENE_009_TEXT = (
    "Maya visits her mother. Her mother notices she is different.\n"
    "MOM\nWhat?\nMAYA\nNothing.\nMOM\nYou have been staring at me forever.\n"
    "MAYA\nI just forgot what it felt like to see you.\n"
    "Mom sets down her tea. She looks at her daughter.\n"
    "MOM\nBaby. What's going on with you?\n"
    "MAYA\nI need you to trust me about something.\n"
    "MOM\nI always trust you.\n"
    "MAYA\nEven if I can't explain it yet.\n"
    "A long beat. Mom reaches across the table and covers Maya's hand with hers.\n"
    "MOM\nWhere do you need me to go?\n"
    "Maya exhales for the first time in weeks.\n"
    "DRE NOTICES"
)
SCENE_009_CHARS = ["MOM", "MAYA"]

SCENE_013_TEXT = (
    "Inside are Maya's chosen survivors. Her mother. Jay. Simone. Elena. Others she\n"
    "trusted. The building has food. Water. Power. Life.\n"
    "Simone runs the medical floor. Jay keeps the power on. Elena tends the rooftop farm.\n"
    "Maya's mother moves through all of it — feeding people, keeping rhythm, being the\n"
    "warmth the building needs.\n"
    "Outside, the city continues falling apart.\n"
    "FINAL CONFRONTATION\n"
    "EXT./INT. THE HOMESTEAD — DAY\n"
    "Dre finds the building. He looks rough — hollowed out, hungry. But his eyes are still\n"
    "sharp. He sees everything.\n"
    "The lights. The gardens. The survivors. He sees Maya's mother alive through a\n"
    "window.\n"
    "He understands she knew.\n"
    "DRE\nHow?\n"
    "Maya says nothing.\n"
    "DRE\nHow did you know?\n"
    "MAYA\nI had a nightmare.\n"
    "DRE\nA nightmare.\n"
    "MAYA\nThe kind you wake up from different.\n"
    "DRE\n(quiet, not accusatory — just broken)\nYou could have saved us.\n"
    "MAYA\nI tried.\n"
    "DRE\nWhen?\n"
    "MAYA\nBefore you became the person who needed saving.\n"
    "A long silence. Dre looks at the building — the life inside it. Then back at Maya.\n"
    "DRE\n(barely)\nscared.\n"
    "I was scared. I want you to know that. I was so\n"
    "MAYA\nI know.\n"
    "DRE\nDoes it matter?\n"
    "MAYA\n(beat)\nIt matters that you said it.\n"
    "Maya gives Dre supplies. A map. A chance. But not her sanctuary. Not her future. She\n"
    "watches him go. She doesn't look away until he's gone.\n"
    "ENDING"
)
SCENE_013_CHARS = ["DRE", "MAYA"]


# ── Tests ────────────────────────────────────────────────────────────────────


def test_scene_002_line_9_not_contaminated():
    """The required regression case: scene_002 line 9 (DRE) must be 3 words
    'Someone had to.', not the 78-word contaminated extraction that included
    75 words of action/description ('Maya is killed. Darkness. We hold on
    Dre's face...').
    """
    lines = _extract_dialogue_lines(SCENE_002_TEXT, characters=SCENE_002_CHARS)
    assert len(lines) >= 9, f"expected >=9 lines, got {len(lines)}"

    line_9 = lines[8]
    assert line_9["character"] == "DRE"
    assert line_9["text"] == "Someone had to."
    assert len(line_9["text"].split()) == 3

    # The contaminated extraction was 78 words — this must never return.
    assert len(line_9["text"].split()) != 78


def test_scene_002_line_10_not_contaminated():
    """MAYA's line 10 was 32 words (absorbed 'She sits with that for a long
    moment...'). Correct extraction is 8 words: 'I remember dying. So why am
    I here?'
    """
    lines = _extract_dialogue_lines(SCENE_002_TEXT, characters=SCENE_002_CHARS)
    line_10 = lines[9]
    assert line_10["character"] == "MAYA"
    assert line_10["text"] == "I remember dying. So why am I here?"
    assert len(line_10["text"].split()) == 8
    assert len(line_10["text"].split()) != 32


def test_scene_002_total_word_count_corrected():
    """scene_002 total was 159 (contaminated). Corrected: 60."""
    lines = _extract_dialogue_lines(SCENE_002_TEXT, characters=SCENE_002_CHARS)
    total = sum(len(d["text"].split()) for d in lines)
    assert total == 60, f"expected 60, got {total}"


def test_scene_003_vocative_dialogue_preserved():
    """DRE's vocative line 'Maya. You're my people. Always.' (5 words) must
    NOT be flagged as an action line. The old extractor produced 132 words
    by absorbing 'She nods. She almost believes him.' + section headers.
    """
    lines = _extract_dialogue_lines(SCENE_003_TEXT, characters=SCENE_003_CHARS)
    vocative = next(
        (d for d in lines if d["character"] == "DRE" and "You're my people" in d["text"]),
        None,
    )
    assert vocative is not None, "vocative DRE line 'Maya. You're my people. Always.' was dropped"
    assert vocative["text"] == "Maya. You're my people. Always."
    assert len(vocative["text"].split()) == 5
    assert len(vocative["text"].split()) != 132


def test_scene_003_supplies_not_character_cue():
    """SUPPLIES is a section header, not a character. The old extractor treated
    it as a character cue and absorbed 43 words of action/description as its
    'dialogue'. The fix must not produce any line attributed to SUPPLIES.
    """
    lines = _extract_dialogue_lines(SCENE_003_TEXT, characters=SCENE_003_CHARS)
    supplies_lines = [d for d in lines if d["character"] == "SUPPLIES"]
    assert supplies_lines == [], f"SUPPLIES should not be a character cue, got {supplies_lines}"


def test_scene_003_maya_vo_not_contaminated():
    """MAYA (V.O.) first line was 49 words (included 'Dre turns and sees her.'
    action text). Corrected: 44 words of pure V.O. dialogue.
    """
    lines = _extract_dialogue_lines(SCENE_003_TEXT, characters=SCENE_003_CHARS)
    maya_vo = lines[0]
    assert maya_vo["character"] == "MAYA"
    assert "Dre turns" not in maya_vo["text"]
    wc = len(maya_vo["text"].split())
    assert wc == 44, f"expected 44, got {wc}"


def test_scene_003_yeah_not_contaminated():
    """MAYA's 'Yeah.' was 35 words (absorbed 'He puts a plate in front of her
    anyway...'). Corrected: 1 word.
    """
    lines = _extract_dialogue_lines(SCENE_003_TEXT, characters=SCENE_003_CHARS)
    yeah_line = next((d for d in lines if d["text"].strip() == "Yeah."), None)
    assert yeah_line is not None, "'Yeah.' line was dropped"
    assert len(yeah_line["text"].split()) == 1
    assert len(yeah_line["text"].split()) != 35


def test_scene_005_action_text_not_absorbed():
    """scene_005 was 34 words (absorbed 'She stays there for a moment. Then she
    gets back up. She writes a new list...'). Corrected: 8 words.
    """
    lines = _extract_dialogue_lines(SCENE_005_TEXT, characters=SCENE_005_CHARS)
    assert len(lines) == 1
    total = sum(len(d["text"].split()) for d in lines)
    assert total == 8, f"expected 8, got {total}"
    assert total != 34


def test_tide_scene_005_coastal_renewal_not_character_cue():
    """COASTAL RENEWAL PROJECT is a sign description, not a character. The old
    extractor treated it as a character cue and absorbed 'She laughs quietly.'
    as its 3-word 'dialogue'. Corrected: 0 dialogue lines.
    """
    lines = _extract_dialogue_lines(TIDE_SCENE_005_TEXT, characters=TIDE_SCENE_005_CHARS)
    coastal = [d for d in lines if "COASTAL" in d["character"]]
    assert coastal == [], f"COASTAL RENEWAL PROJECT should not be a character, got {coastal}"
    assert lines == [], f"scene with no real dialogue should produce empty list, got {lines}"


def test_backward_compatible_without_characters():
    """When characters=None (no character list available), the extractor must
    still work via structural terminators (scene headings, multi-word ALL-CAPS
    headers). scene_002's 'THE SECOND CHANCE' section header must still end
    the DRE dialogue block even without the character list.
    """
    lines = _extract_dialogue_lines(SCENE_002_TEXT, characters=None)
    line_9 = lines[8]
    # Without characters, "Maya is killed." is not caught as action (no char
    # list to match "Maya"), but "THE SECOND CHANCE" multi-word ALL-CAPS
    # header still terminates the block. So line 9 is larger than 3 but
    # must NOT be the full 78-word contamination.
    wc = len(line_9["text"].split())
    assert wc < 78, f"without characters, still must not reach 78-word contamination (got {wc})"
    assert "Someone had to." in line_9["text"]


def test_scene_009_line_8_long_beat_action_not_absorbed():
    """scene_009 line 8 (MAYA) must be 7 words 'Even if I can't explain it
    yet.', not the 21-word contaminated extraction that absorbed the action
    line 'A long beat. Mom reaches across the table and covers Maya's hand
    with hers.'

    The action line opens with 'A long beat.' — a classic screenplay
    beat/pause direction. The _is_action_line() detector catches this via a
    curated pause-noun set (beat/silence/pause/moment/stillness/breath)
    without breaking real dialogue that starts with 'A ' (e.g. 'A nightmare.'
    in scene_013).
    """
    lines = _extract_dialogue_lines(SCENE_009_TEXT, characters=SCENE_009_CHARS)
    assert len(lines) == 9, f"expected 9 lines, got {len(lines)}"

    line_8 = lines[7]
    assert line_8["character"] == "MAYA"
    assert line_8["text"] == "Even if I can't explain it yet."
    wc = len(line_8["text"].split())
    assert wc == 7, f"expected 7 words, got {wc}"
    assert wc != 21, "the 21-word contamination (absorbed 'A long beat. Mom reaches...') must never return"
    assert "A long beat" not in line_8["text"]
    assert "Mom reaches" not in line_8["text"]

    total = sum(len(d["text"].split()) for d in lines)
    assert total == 51, f"scene_009 total should be 51 words, got {total}"


def test_scene_013_line_9_long_silence_action_not_absorbed():
    """scene_013 line 9 (MAYA) must be 8 words 'Before you became the person
    who needed saving.', not the 25-word contaminated extraction that
    absorbed 'A long silence. Dre looks at the building — the life inside
    it. Then back at Maya.'

    This test also locks in the critical ambiguity guard: DRE's real
    dialogue 'A nightmare.' (line 4) must remain preserved as spoken text.
    'A nightmare.' starts with 'A ' but 'nightmare' is NOT in the curated
    pause-noun set, so it is correctly NOT flagged as an action line. A
    naive 'A <noun>' detector would wrongly strip it.
    """
    lines = _extract_dialogue_lines(SCENE_013_TEXT, characters=SCENE_013_CHARS)
    assert len(lines) == 13, f"expected 13 lines, got {len(lines)}"

    line_9 = lines[8]
    assert line_9["character"] == "MAYA"
    assert line_9["text"] == "Before you became the person who needed saving."
    wc = len(line_9["text"].split())
    assert wc == 8, f"expected 8 words, got {wc}"
    assert wc != 25, "the 25-word contamination (absorbed 'A long silence. Dre looks...') must never return"
    assert "A long silence" not in line_9["text"]
    assert "Dre looks" not in line_9["text"]

    # Ambiguity guard: 'A nightmare.' is REAL dialogue (DRE, line 4), not
    # an action line. The curated pause-noun set must NOT flag it.
    nightmare = next(
        (d for d in lines if d["character"] == "DRE" and d["text"].strip() == "A nightmare."),
        None,
    )
    assert nightmare is not None, (
        "'A nightmare.' (DRE line 4) was wrongly stripped as an action line — "
        "the pause-noun set is too broad"
    )
    assert len(nightmare["text"].split()) == 2

    total = sum(len(d["text"].split()) for d in lines)
    assert total == 58, f"scene_013 total should be 58 words, got {total}"
