"""Locked-appearance block is scoped to the shot, never alphabetically truncated.

Regression coverage for the scene_001 finding: with an empty scene cast, the
block used to list the first three project-locked characters alphabetically
(DRE, ELENA, JAY) in every shot and cut MAYA (4th), even in shots reading
"Only MAYA visible."

Selection precedence (first non-empty scope wins):
  1. shot-assigned characters (intent focus names),
  2. the scene's declared cast,
  3. locked characters named in the shot text,
  4. locked characters named in ANY shot of the scene (union, logged),
  5. empty block plus a warning log — never the wrong characters.

Entries carry appearance only (age + look); reference-image staging sentences
(a rooftop, a garden, an auto shop, a street) must not leak into the shot.
"""
from __future__ import annotations

import json

from app.services.shot_prompt_builder import (
    build_locked_appearance_block,
    build_shot_aware_prompt,
    ensure_locked_appearance_in_prompt,
)


def _locked(name: str, age: str, look: str, staging: str) -> dict:
    return {
        "name": name,
        "age": age,
        "look": look,
        "visual_prompt_summary": staging,
        "continuity_state_json": json.dumps(
            {
                "appearance_approval": {
                    "status": "locked",
                    "description": f"{age}; {look}; {staging}",
                }
            }
        ),
    }


DRE = _locked(
    "DRE",
    "Early 30s",
    "Broad-shouldered Black man with medium brown textured skin and a short fade",
    "stands with a clenched jaw on a dark post-collapse Chicago street",
)
ELENA = _locked(
    "ELENA",
    "Early 60s",
    "Compact Black woman with brown sun-darkened skin and silver braids",
    "kneeling in a Pilsen community garden among winter kale",
)
JAY = _locked(
    "JAY",
    "Early 30s",
    "Wiry Black man with warm brown skin and short natural hair under a beanie",
    "stands in a sunlit South Side auto shop holding a rag",
)
MAYA = _locked(
    "MAYA",
    "Late 20s",
    "Lean Black woman with deep brown luminous skin and natural locs in a worn canvas jacket",
    "stands resolutely on a rooftop overlooking a dark Chicago skyline",
)
MOM = _locked(
    "MOM",
    "Late 50s",
    "Soft-built Black woman with deep brown skin and natural silver locs",
    "seated at a kitchen table in a Bronzeville apartment",
)

FOUR_LOCKED = [DRE, ELENA, JAY, MAYA]
EMPTY_CAST = {"scene_id": "scene_001", "characters": []}


def test_four_locked_empty_cast_no_alphabetical_truncation() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED, EMPTY_CAST, shot_text="The city holds its breath.", scene_shot_texts=None
    )
    # Nothing names anyone: empty is preferable to the wrong characters.
    assert block == ""


def test_scene_union_names_maya_in_all_five_shots() -> None:
    """Only shots 3 and 4 name Maya; shots 1, 2, 5 name nobody.

    The scene-level union must still put Maya — and only Maya — in all five.
    """
    shot_texts = [
        "Wide establishing shot. The L train moves through the skyline.",
        "Two-shot conversation over dinner. Laughter, families, restaurants.",
        "Only MAYA visible. Maya walks through the city watching small moments.",
        "Only MAYA visible. MAYA speaks about remembering.",
        "Close-up detail shot. Hands holding a crumpled piece of paper.",
    ]
    for text in shot_texts:
        block = build_locked_appearance_block(
            FOUR_LOCKED, EMPTY_CAST, shot_text=text, scene_shot_texts=shot_texts
        )
        assert "MAYA" in block, text
        for other in ("DRE", "ELENA", "JAY"):
            assert other not in block, (text, block)


def test_shot_with_only_maya_excludes_everyone_else() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED + [MOM],
        EMPTY_CAST,
        shot_text="Only MAYA visible. No extras.",
    )
    assert "MAYA" in block
    for other in ("DRE", "ELENA", "JAY", "MOM"):
        assert other not in block


def test_shot_with_two_characters_lists_both() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED,
        EMPTY_CAST,
        shot_text="MAYA and DRE face each other across the table.",
    )
    assert "MAYA" in block
    assert "DRE" in block
    assert "ELENA" not in block
    assert "JAY" not in block


def test_shot_assigned_focus_beats_shot_text() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED,
        EMPTY_CAST,
        shot_characters=["ELENA"],
        shot_text="MAYA walks alone.",
    )
    assert "ELENA" in block
    assert "MAYA" not in block


def test_declared_scene_cast_still_scopes() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED,
        {"scene_id": "scene_002", "characters": ["JAY", "MOM"]},
        shot_text="The shop hums.",
    )
    assert "JAY" in block
    assert "MAYA" not in block
    assert "DRE" not in block


def test_undeterminable_shot_yields_empty_block() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED, EMPTY_CAST, shot_text="Rain on an empty platform."
    )
    assert block == ""


def test_no_cap_over_many_locked_in_one_shot() -> None:
    six = FOUR_LOCKED + [MOM, _locked(
        "SIMONE",
        "Early 40s",
        "Black woman with medium brown skin and pinned-back braids",
        "sitting alone under cool fluorescent break room lighting",
    )]
    block = build_locked_appearance_block(
        six,
        EMPTY_CAST,
        shot_text="MAYA, DRE, ELENA, JAY, MOM and SIMONE gather at dawn.",
    )
    for name in ("MAYA", "DRE", "ELENA", "JAY", "MOM", "SIMONE"):
        assert name in block


def test_appearance_only_entries_drop_staging_but_keep_guard_tokens() -> None:
    block = build_locked_appearance_block(
        FOUR_LOCKED, EMPTY_CAST, shot_text="Only MAYA visible."
    )
    for staging in ("rooftop", "garden", "auto shop", "post-collapse street"):
        assert staging not in block
    # Drift-guard tokens survive: race, skin tone, hair.
    for token in ("Black woman", "deep brown", "locs"):
        assert token in block


def test_every_appearance_entry_keeps_race_skin_hair_tokens() -> None:
    expectations = {
        "DRE": ["Black man", "medium brown", "fade"],
        "ELENA": ["Black woman", "sun-darkened", "braids"],
        "JAY": ["Black man", "warm brown", "beanie"],
        "MAYA": ["Black woman", "deep brown", "locs"],
    }
    for char in FOUR_LOCKED:
        block = build_locked_appearance_block(
            [char], {"scene_id": "s", "characters": [char["name"]]}
        )
        assert char["name"] in block
        for token in expectations[char["name"]]:
            assert token in block, (char["name"], token, block)


def test_ensure_scopes_from_prompt_text_without_explicit_names() -> None:
    prompt = "Medium close-up. Only MAYA visible. No extras. Cinematic, film quality."
    ensured = ensure_locked_appearance_in_prompt(prompt, FOUR_LOCKED, EMPTY_CAST)
    assert "MAYA" in ensured
    assert "DRE" not in ensured


def test_build_shot_aware_prompt_scopes_block_to_segment_cast() -> None:
    scene = {
        "scene_id": "scene_001",
        "location": "DOWNTOWN CHICAGO",
        "time_of_day": "GOLDEN HOUR",
        "characters": [],
        "text": (
            "Chicago is alive. The L train moves through the skyline.\n"
            "MAYA (V.O.)\n"
            "People think the end of the world is fire.\n"
            "Maya walks through the city watching small moments.\n"
            "Only MAYA visible.\n"
            "CUT TO:\n"
        ),
    }
    prompt = build_shot_aware_prompt(
        scene_data=scene,
        shot_number=3,
        take_number=1,
        all_characters=FOUR_LOCKED,
        total_shots=5,
    )
    assert "Locked appearance" in prompt
    assert "MAYA" in prompt
    for other in ("DRE", "ELENA", "JAY"):
        assert f"{other} (" not in prompt
