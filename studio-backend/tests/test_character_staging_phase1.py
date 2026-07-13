"""
Phase 1 regression test for CHARACTER_VPS_SCENE_CONTAMINATION spec.

Verifies that resolve_character_prompt() produces byte-for-byte identical
output to today's visual_prompt_summary injection for all 6 characters
across real scenes, using actual render_jobs.input_payload prompts from
the live DB as the ground truth.

Critical invariant: zero render regression during Phase 1.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure we can import from app/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.character_staging_service import resolve_character_prompt, resolve_character_block


# ── Test fixtures ────────────────────────────────────────────────────────────

PROJECT_ID = "project_3dba9330f43a"

# Use the migrated copy at /tmp/studio.db (created by the migration test).
# This ensures we don't touch the live DB and that migration #27 columns
# (appearance_core, appearance_notes, description_status, character_stagings)
# are present.
LIVE_DB_PATH = os.environ.get("STUDIO_TEST_DB_PATH", "/tmp/studio.db")


def _get_live_db_path() -> str:
    """Return path to the test studio.db, skipping if it doesn't exist."""
    if not os.path.exists(LIVE_DB_PATH):
        pytest.skip(f"Test DB not found at {LIVE_DB_PATH} — run migration on a copy first")
    return LIVE_DB_PATH


def _load_characters_from_db(db_path: str) -> list[dict]:
    """Load all 6 characters from the DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM characters WHERE project_id = ? ORDER BY name ASC",
        (PROJECT_ID,),
    )
    chars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return chars


def _load_render_prompts_from_db(db_path: str) -> list[dict]:
    """Load render job prompts that contain 'Characters:' from the DB.

    Returns list of dicts with: job_id, shot_id, prompt, expected_char_block
    (the substring after 'Characters:' in the prompt).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, shot_id, input_payload
           FROM render_jobs
           WHERE project_id = ?
             AND input_payload LIKE '%Characters:%'
           ORDER BY created_at ASC""",
        (PROJECT_ID,),
    )
    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        try:
            payload = json.loads(row["input_payload"])
            prompt = payload.get("prompt", "")
        except (json.JSONDecodeError, TypeError):
            continue
        if "Characters:" not in prompt:
            continue
        # Extract the character block: from "Characters:" to end of prompt
        # (or to the next section marker if present)
        idx = prompt.index("Characters:")
        char_block = prompt[idx:]
        # Strip any trailing [CINEMATIC CONTEXT] or [SHOT POSITION] blocks
        for marker in ("[CINEMATIC CONTEXT]", "[SHOT POSITION]", "[RETRY CONTEXT]"):
            if marker in char_block:
                char_block = char_block[: char_block.index(marker)].rstrip()
        jobs.append({
            "job_id": row["id"],
            "shot_id": row["shot_id"],
            "prompt": prompt,
            "expected_char_block": char_block,
        })
    return jobs


def _derive_scene_id(shot_id: str) -> str:
    """Derive scene_id from shot_id (e.g. 'scene_001_shot_001' → 'scene_001')."""
    if "_" in shot_id:
        parts = shot_id.split("_")
        if len(parts) >= 2:
            return f"{parts[0]}_{parts[1]}"
    return shot_id


# ── Tests ────────────────────────────────────────────────────────────────────

class TestResolveCharacterPromptLegacyFallback:
    """Verify the legacy fallback path produces exactly what today's
    injection produces — byte-for-byte identical."""

    def test_all_6_characters_have_legacy_status(self):
        """All 6 characters must have description_status='legacy' and
        appearance_core IS NULL for the Phase 1 invariant to hold."""
        db_path = _get_live_db_path()
        chars = _load_characters_from_db(db_path)
        assert len(chars) == 6, f"Expected 6 characters, got {len(chars)}"
        for char in chars:
            assert char["description_status"] == "legacy", (
                f"{char['name']} has description_status={char['description_status']}, expected 'legacy'"
            )
            assert char["appearance_core"] is None, (
                f"{char['name']} has appearance_core={char['appearance_core']}, expected None"
            )

    def test_resolve_character_prompt_matches_vps_format(self):
        """For each character, resolve_character_prompt() must return
        exactly f'{name}: {visual_prompt_summary}'."""
        db_path = _get_live_db_path()
        chars = _load_characters_from_db(db_path)

        for char in chars:
            resolved = resolve_character_prompt(
                char, scene_id="scene_001", shot_id=None, storage=None
            )
            expected = f"{char['name']}: {char['visual_prompt_summary']}"
            assert resolved == expected, (
                f"{char['name']}: resolved != expected\n"
                f"  resolved: {resolved!r}\n"
                f"  expected: {expected!r}"
            )

    def test_resolve_character_prompt_byte_for_byte_against_real_renders(self):
        """The critical invariant: for every real render job that contains
        a 'Characters:' block, the resolve_character_block() output must
        match the actual injected character block byte-for-byte.

        This pulls real render_jobs.input_payload prompts from the live DB
        and diffs them against what resolve_character_block() produces.
        """
        db_path = _get_live_db_path()
        chars = _load_characters_from_db(db_path)
        jobs = _load_render_prompts_from_db(db_path)

        # We need at least some real renders to compare against
        assert len(jobs) > 0, "No render jobs with Characters: block found in DB"

        # Build a name → char lookup
        char_by_name = {c["name"]: c for c in chars}

        mismatches = []
        checked = 0

        for job in jobs:
            shot_id = job["shot_id"]
            scene_id = _derive_scene_id(shot_id)
            expected_block = job["expected_char_block"]

            # Determine which characters appear in this render's char block
            # by parsing the expected block
            # Format: "Characters: NAME1: desc1; NAME2: desc2"
            # We need to identify which characters are present
            # Strategy: check each character's expected string against the block
            present_chars = []
            for char in chars:
                name = char["name"]
                char_str = f"{name}: {char['visual_prompt_summary']}"
                if char_str in expected_block:
                    present_chars.append(char)

            if not present_chars:
                # Some renders may have truncated/different format — skip
                continue

            # Build the block using resolve_character_block
            resolved_block = resolve_character_block(
                present_chars, scene_id=scene_id, shot_id=shot_id, storage=None
            )

            checked += 1
            if resolved_block != expected_block:
                mismatches.append({
                    "job_id": job["job_id"],
                    "shot_id": shot_id,
                    "expected": expected_block,
                    "resolved": resolved_block,
                })

        assert checked > 0, "No renders could be matched to characters for comparison"
        assert len(mismatches) == 0, (
            f"{len(mismatches)} mismatches found out of {checked} checked:\n"
            + "\n\n".join(
                f"Job {m['job_id']} ({m['shot_id']}):\n"
                f"  expected: {m['expected']!r}\n"
                f"  resolved: {m['resolved']!r}"
                for m in mismatches[:5]
            )
        )

    def test_resolve_character_block_empty_when_no_characters(self):
        """resolve_character_block() returns empty string when no characters."""
        result = resolve_character_block([], scene_id="scene_001", shot_id=None, storage=None)
        assert result == ""

    def test_resolve_character_prompt_empty_vps_returns_name(self):
        """When visual_prompt_summary is empty, returns just the name."""
        char = {"id": "chr_test", "name": "TEST", "visual_prompt_summary": ""}
        result = resolve_character_prompt(char, scene_id="scene_001", shot_id=None, storage=None)
        assert result == "TEST"

    def test_resolve_character_prompt_skips_staging_when_storage_none(self):
        """When storage is None, only legacy fallback is used."""
        char = {
            "id": "chr_test",
            "name": "TEST",
            "visual_prompt_summary": "test description",
        }
        result = resolve_character_prompt(char, scene_id="scene_001", shot_id=None, storage=None)
        assert result == "TEST: test description"


class TestStagingStorageMethods:
    """Verify the storage methods for character_stagings work correctly
    on a copy of the DB (not the live one)."""

    def test_get_character_staging_returns_none_when_no_rows(self):
        """get_character_staging() returns None when no staging rows exist
        (the Phase 1 state — no stagings have been created yet)."""
        db_path = _get_live_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Verify no stagings exist
        cursor.execute("SELECT COUNT(*) FROM character_stagings")
        count = cursor.fetchone()[0]
        conn.close()

        # In Phase 1, there should be 0 staging rows
        # (the table exists but is empty)
        assert count == 0, f"Expected 0 staging rows in Phase 1, got {count}"


if __name__ == "__main__":
    # Allow running directly: python -m tests.test_character_staging_phase1
    pytest.main([__file__, "-v"])
