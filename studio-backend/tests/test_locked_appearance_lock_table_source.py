"""Fix B: locked-appearance block follows the reference-lock table, not the
project-wide appearance flag, and never truncates to 3.

scene_001 has six appearance-locked characters (DRE/ELENA/JAY/MAYA/MOM/SIMONE)
but only MAYA+MOM hold `character_reference_locks` rows with lock_status
'locked' (DRE is provisional). The block must narrow to the lock table so
DRE/ELENA/JAY prose stops leaking into every shot.
"""
from __future__ import annotations

import json


def _locked(name: str, age: str, look: str, char_id: str, face_url: str = "") -> dict:
    approval: dict = {
        "status": "locked",
        "description": f"{age}; {look}; staging sentence that must not leak",
    }
    if face_url:
        approval["face_image_url"] = face_url
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


DRE = _locked("DRE", "Early 30s", "Broad-shouldered Black man with medium brown skin", "chr_dre")
ELENA = _locked("ELENA", "Early 60s", "Compact Black woman with brown skin", "chr_elena")
JAY = _locked("JAY", "Early 30s", "Wiry Black man with warm brown skin", "chr_jay")
MAYA = _locked("MAYA", "Late 20s", "Lean Black woman with deep brown skin", "chr_maya")
MOM = _locked("MOM", "Late 50s", "Soft-built Black woman with deep brown skin", "chr_mom")
SIMONE = _locked("SIMONE", "Early 40s", "Black woman with medium brown skin", "chr_simone")

SIX = [DRE, ELENA, JAY, MAYA, MOM, SIMONE]
LOCK_ROWS = [
    {"character_id": "chr_maya", "character_name": "MAYA", "lock_status": "locked"},
    {"character_id": "chr_mom", "character_name": "MOM", "lock_status": "locked"},
]


def test_lock_table_narrows_to_maya_and_mom() -> None:
    svc = _service(SIX, LOCK_ROWS)
    narrowed = svc._locked_characters_for_prompt("proj", SIX)
    assert {c["name"] for c in narrowed} == {"MAYA", "MOM"}


def test_empty_lock_table_fails_open() -> None:
    svc = _service(SIX, [])
    assert len(svc._locked_characters_for_prompt("proj", SIX)) == 6


def test_block_with_lock_table_gives_maya_only_for_scene_001() -> None:
    svc = _service(SIX, LOCK_ROWS)
    scene = {"scene_id": "scene_001", "characters": []}
    shot_texts = [
        "The L train moves through the skyline.",
        "Two-shot conversation over dinner.",
        "Only MAYA visible. Maya walks through the city.",
        "Only MAYA visible. MAYA speaks about remembering.",
        "Close-up detail. Hands holding paper.",
    ]
    for text in shot_texts:
        block = svc._locked_block_for_scene(
            "proj", scene, shot_text=text, scene_shot_texts=shot_texts
        )
        assert "MAYA" in block, text
        for other in ("DRE", "ELENA", "JAY", "SIMONE", "MOM"):
            assert other not in block, (text, block)


def test_reference_images_are_not_truncated_to_three() -> None:
    chars = [
        _locked("A", "30s", "Black man with short hair", "c1", "https://face/a.jpg"),
        _locked("B", "30s", "Black woman with braids", "c2", "https://face/b.jpg"),
        _locked("C", "30s", "Black man with fade", "c3", "https://face/c.jpg"),
        _locked("D", "20s", "Black woman with locs", "c4", "https://face/d.jpg"),
    ]
    svc = _service(chars, [])
    refs = svc._locked_reference_images_for_scene("proj", {"scene_id": "s", "characters": []})
    assert refs == ["https://face/a.jpg", "https://face/b.jpg", "https://face/c.jpg", "https://face/d.jpg"]
