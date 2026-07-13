"""Targeted unit test for save_character_staging() on a fresh DatabaseStorage.

Exercises the exact code path where the missing `nonlocal staging_id`
bug manifested: a fresh insert into an empty character_stagings table.

Without the fix, the assignment `staging_id = existing["id"]` inside
the `if existing:` branch makes staging_id a local variable for the
entire _write() function. On the INSERT path (else branch), staging_id
is local-but-unassigned → UnboundLocalError.

Also verifies the UPDATE path (second call with same keys) works correctly,
and that get_character_staging() retrieves what save_character_staging() wrote.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.storage import DatabaseStorage
from app.models import StudioProject


@pytest.fixture
def fresh_db(tmp_path):
    """Fresh DatabaseStorage with a project and two characters seeded.

    The character_stagings table has a FK constraint:
        FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
    and PRAGMA foreign_keys=ON is enforced, so characters must exist
    before stagings can be inserted.

    Returns (db, char_ids) where char_ids maps names to character IDs.
    """
    db = DatabaseStorage(str(tmp_path))
    project_id = "proj_staging_test"

    db.save_project(StudioProject(
        project_id=project_id,
        title="Staging Test",
        execution_summary={"scenes": []},
    ))

    db.save_character(project_id, "MAYA", {
        "visual_prompt_summary": "test vps",
        "description_status": "legacy",
    })
    maya = db.get_character_by_name(project_id, "MAYA")

    db.save_character(project_id, "DRE", {
        "visual_prompt_summary": "test vps",
        "description_status": "legacy",
    })
    dre = db.get_character_by_name(project_id, "DRE")

    return db, {"MAYA": maya["id"], "DRE": dre["id"]}


class TestSaveCharacterStagingFreshInsert:
    """Verify save_character_staging() works on a fresh insert (empty table).

    This is the exact path the nonlocal bug hits: no existing row →
    _write() enters the else branch → staging_id is local but unassigned
    → UnboundLocalError without the nonlocal fix.
    """

    def test_fresh_insert_returns_staging_dict(self, fresh_db):
        db, char_ids = fresh_db
        result = db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": None,
            "staging_prompt": "fresh bruise on her left cheek",
            "source": "manual",
        })

        assert isinstance(result, dict)
        assert result["character_id"] == char_ids["MAYA"]
        assert result["scene_id"] == "scene_002"
        assert result["shot_id"] is None
        assert result["staging_prompt"] == "fresh bruise on her left cheek"
        assert result["source"] == "manual"
        assert result["id"].startswith("cstg_")

    def test_fresh_insert_with_explicit_id_preserves_id(self, fresh_db):
        db, char_ids = fresh_db
        result = db.save_character_staging({
            "id": "cstg_custom_001",
            "character_id": char_ids["DRE"],
            "scene_id": "scene_001",
            "shot_id": "scene_001_shot_003",
            "staging_prompt": "scar on right hand",
            "source": "manual",
        })

        assert result["id"] == "cstg_custom_001"
        assert result["shot_id"] == "scene_001_shot_003"

    def test_fresh_insert_with_appearance_override(self, fresh_db):
        db, char_ids = fresh_db
        result = db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_003",
            "shot_id": None,
            "staging_prompt": "wounded, limping",
            "appearance_override": "MAYA: blood-stained jacket, limp in left leg",
            "source": "auto",
        })

        assert result["appearance_override"] == "MAYA: blood-stained jacket, limp in left leg"


class TestSaveCharacterStagingUpdate:
    """Verify save_character_staging() upserts correctly on second call.

    The UPDATE path (if existing:) worked even without the nonlocal fix
    because staging_id was assigned in that branch before use. These tests
    confirm the upsert semantics are correct after the fix.
    """

    def test_second_call_updates_existing_row(self, fresh_db):
        db, char_ids = fresh_db
        result1 = db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": None,
            "staging_prompt": "bruise on cheek",
            "source": "manual",
        })

        result2 = db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": None,
            "staging_prompt": "bruise healing, scar forming",
            "source": "manual",
        })

        assert result2["id"] == result1["id"]
        assert result2["staging_prompt"] == "bruise healing, scar forming"

        staging = db.get_character_staging(char_ids["MAYA"], "scene_002", None)
        assert staging is not None
        assert staging["staging_prompt"] == "bruise healing, scar forming"

    def test_update_preserves_id_from_existing_row(self, fresh_db):
        db, char_ids = fresh_db
        result1 = db.save_character_staging({
            "id": "cstg_original",
            "character_id": char_ids["DRE"],
            "scene_id": "scene_001",
            "shot_id": "scene_001_shot_001",
            "staging_prompt": "tense posture",
            "source": "manual",
        })

        result2 = db.save_character_staging({
            "character_id": char_ids["DRE"],
            "scene_id": "scene_001",
            "shot_id": "scene_001_shot_001",
            "staging_prompt": "relaxed posture",
            "source": "manual",
        })

        assert result2["id"] == "cstg_original"
        assert result2["staging_prompt"] == "relaxed posture"


class TestGetSaveRoundTrip:
    """Verify get_character_staging() retrieves what save_character_staging() wrote."""

    def test_scene_level_staging_retrieved_by_scene_id(self, fresh_db):
        db, char_ids = fresh_db
        db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": None,
            "staging_prompt": "scene-level staging note",
        })

        result = db.get_character_staging(char_ids["MAYA"], "scene_002", None)
        assert result is not None
        assert result["staging_prompt"] == "scene-level staging note"

    def test_shot_specific_staging_retrieved_by_shot_id(self, fresh_db):
        db, char_ids = fresh_db
        db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": "scene_002_shot_001",
            "staging_prompt": "shot-specific note",
        })

        result = db.get_character_staging(char_ids["MAYA"], "scene_002", "scene_002_shot_001")
        assert result is not None
        assert result["staging_prompt"] == "shot-specific note"

    def test_get_returns_none_for_nonexistent_staging(self, fresh_db):
        db, _ = fresh_db
        result = db.get_character_staging("chr_nonexistent", "scene_999", None)
        assert result is None

    def test_shot_specific_takes_precedence_over_scene_level(self, fresh_db):
        """get_character_staging() must return the shot-specific staging
        when one exists, falling back to scene-level only when no
        shot-specific row is found."""
        db, char_ids = fresh_db
        db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": None,
            "staging_prompt": "scene-level note",
        })
        db.save_character_staging({
            "character_id": char_ids["MAYA"],
            "scene_id": "scene_002",
            "shot_id": "scene_002_shot_003",
            "staging_prompt": "shot-3-specific note",
        })

        shot3 = db.get_character_staging(char_ids["MAYA"], "scene_002", "scene_002_shot_003")
        assert shot3 is not None
        assert shot3["staging_prompt"] == "shot-3-specific note"

        shot1 = db.get_character_staging(char_ids["MAYA"], "scene_002", "scene_002_shot_001")
        assert shot1 is not None
        assert shot1["staging_prompt"] == "scene-level note"
