"""Fix B v2 to spec: shot/scene scoping, no fail-open, per-model trim.

Precedence (text): shot focus names → scene cast → shot text → scene union →
empty (warn). Reference-lock table is a filter for anchors only, never the
sole scoping mechanism. Empty table / no intersect → [] refs (no leak).
gen4_image (limit 3) trims preserving shot-named first.
"""
from __future__ import annotations

import json


def _locked(name: str, age: str, look: str, char_id: str, face_url: str = "", body_url: str = "") -> dict:
    approval: dict = {
        "status": "locked",
        "description": f"{age}; {look}; staging sentence that must not leak",
    }
    if face_url:
        approval["face_image_url"] = face_url
    if body_url:
        approval["body_image_url"] = body_url
    return {
        "id": char_id,
        "name": name,
        "age": age,
        "look": look,
        "continuity_state_json": json.dumps({"appearance_approval": approval}),
    }


def _service(characters: list[dict], lock_rows: list[dict]):
    from app.services.storyboard_blueprint_service import StoryboardBlueprintService

    class _FakeStorage:
        def list_character_reference_locks(self, project_id, lock_status=None, limit=200):
            assert lock_status == "locked"
            return lock_rows

        def get_characters(self, project_id):
            return characters

    return StoryboardBlueprintService(storage=_FakeStorage())  # type: ignore[arg-type]


DRE = _locked("DRE", "Early 30s", "Broad-shouldered Black man with medium brown skin", "chr_dre",
              "https://face/dre.jpg", "https://body/dre.jpg")
ELENA = _locked("ELENA", "Early 60s", "Compact Black woman with brown skin", "chr_elena",
                "https://face/elena.jpg")
JAY = _locked("JAY", "Early 30s", "Wiry Black man with warm brown skin", "chr_jay",
              "https://face/jay.jpg")
MAYA = _locked("MAYA", "Late 20s", "Lean Black woman with deep brown skin", "chr_maya",
               "https://face/maya.jpg", "https://body/maya.jpg")
MOM = _locked("MOM", "Late 50s", "Soft-built Black woman with deep brown skin", "chr_mom",
              "https://face/mom.jpg")
SIMONE = _locked("SIMONE", "Early 40s", "Black woman with medium brown skin", "chr_simone",
                 "https://face/simone.jpg")

SIX = [DRE, ELENA, JAY, MAYA, MOM, SIMONE]
LOCK_ROWS = [
    {"character_id": "chr_maya", "character_name": "MAYA", "lock_status": "locked"},
    {"character_id": "chr_mom", "character_name": "MOM", "lock_status": "locked"},
]


def test_lock_table_narrows_refs_to_maya_and_mom() -> None:
    svc = _service(SIX, LOCK_ROWS)
    narrowed = svc._locked_characters_for_prompt("proj", SIX)
    assert {c["name"] for c in narrowed} == {"MAYA", "MOM"}


def test_empty_lock_table_returns_no_refs() -> None:
    # v2: no fail-open — empty table means no authorized anchors, not 6 faces.
    svc = _service(SIX, [])
    assert svc._locked_characters_for_prompt("proj", SIX) == []
    assert svc._locked_reference_images_for_scene("proj", {"scene_id": "s", "characters": ["MAYA"]}) == []


def test_text_block_scopes_to_shot_not_lock_table() -> None:
    # DRE is appearance-locked but NOT reference-locked. A DRE shot must name
    # DRE in the text block even though the ref filter would drop her.
    svc = _service(SIX, LOCK_ROWS)
    block = svc._locked_block_for_scene(
        "proj", {"scene_id": "s", "characters": []},
        shot_characters=["DRE"], shot_text="DRE listens by the doorway.",
    )
    assert "DRE" in block
    assert "MAYA" not in block and "MOM" not in block


def test_per_shot_blocks_differ() -> None:
    svc = _service(SIX, LOCK_ROWS)
    dre_block = svc._locked_block_for_scene(
        "proj", {"scene_id": "s", "characters": []},
        shot_characters=["DRE"], shot_text="DRE listens.",
    )
    simone_chars = [_locked("SIMONE", "Early 40s", "Black woman with medium brown skin",
                             "chr_simone")]
    svc2 = _service(simone_chars + [MAYA], LOCK_ROWS + [
        {"character_id": "chr_simone", "character_name": "SIMONE", "lock_status": "locked"}])
    sim_block = svc2._locked_block_for_scene(
        "proj", {"scene_id": "s", "characters": []},
        shot_characters=["SIMONE"], shot_text="SIMONE pours tea.",
    )
    assert "DRE" in dre_block and "SIMONE" not in dre_block
    assert "SIMONE" in sim_block and "DRE" not in sim_block


def test_fourth_alphabetical_shot_named_never_dropped() -> None:
    # Alphabetical: DRE, ELENA, JAY, MAYA(4th), MOM, SIMONE. Shot names MAYA.
    svc = _service(SIX, LOCK_ROWS)
    block = svc._locked_block_for_scene(
        "proj", {"scene_id": "s", "characters": []},
        shot_text="Only MAYA visible. MAYA walks through the city.",
    )
    assert "MAYA" in block


def test_empty_scene_cast_falls_back_to_shot_text() -> None:
    svc = _service(SIX, LOCK_ROWS)
    block = svc._locked_block_for_scene(
        "proj", {"scene_id": "s", "characters": []},
        shot_text="MOM sets down her tea.",
    )
    assert "MOM" in block


def test_gen4_image_trim_preserves_shot_named_first() -> None:
    chars = [
        _locked("A", "30s", "Black man with short hair", "c1", "https://face/a.jpg", "https://body/a.jpg"),
        _locked("B", "30s", "Black woman with braids", "c2", "https://face/b.jpg", "https://body/b.jpg"),
        _locked("C", "30s", "Black man with fade", "c3", "https://face/c.jpg", "https://body/c.jpg"),
        _locked("D", "20s", "Black woman with locs", "c4", "https://face/d.jpg", "https://body/d.jpg"),
    ]
    rows = [{"character_id": f"c{i+1}", "character_name": n, "lock_status": "locked"}
            for i, n in enumerate(["A", "B", "C", "D"])]
    svc = _service(chars, rows)
    refs = svc._locked_reference_images_for_scene(
        "proj", {"scene_id": "s", "characters": []},
        shot_characters=["D"], shot_text="D studies the paper.",
        model_id="gen4_image",
    )
    # gen4_image limit is 3 refs: D's face must survive, total ≤ 3.
    assert len(refs) <= 3, refs
    assert "https://face/d.jpg" in refs, refs
