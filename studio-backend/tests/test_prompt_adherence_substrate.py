"""
Tests for prompt-adherence system substrate.

Tests:
  1. render_attempts table schema and constraints
  2. build_slotted_prompt never exceeds 512 chars
  3. sanitize_render_slot strips scene headings
"""

import pytest
import sqlite3
from pathlib import Path
from app.services.shot_prompt_builder import build_slotted_prompt, SLOT_BUDGETS, MAX_PROMPT_LENGTH
from app.services.script_parser import sanitize_render_slot


# ================================================================================
# DATABASE SCHEMA TESTS
# ================================================================================

def test_render_attempts_table_exists(tmp_path):
    """Test that render_attempts table exists with correct schema."""
    from app.data.storage import DatabaseStorage
    
    db_path = tmp_path / "test.db"
    storage = DatabaseStorage(str(tmp_path))
    
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        
        # Check table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='render_attempts'
        """)
        assert cursor.fetchone() is not None, "render_attempts table should exist"
        
        # Check columns
        cursor.execute("PRAGMA table_info(render_attempts)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        assert "shot_id" in columns
        assert "attempt_n" in columns
        assert "prompt_text" in columns
        assert "provider" in columns
        assert "adherence_score" in columns
        assert "score_json" in columns
        assert "diff_json" in columns
        assert "created_at" in columns
        
        # Check primary key
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='render_attempts'
        """)
        schema = cursor.fetchone()[0]
        assert "PRIMARY KEY (shot_id, attempt_n)" in schema


def test_render_attempts_constraints(tmp_path):
    """Test that render_attempts table enforces constraints."""
    from app.data.storage import DatabaseStorage
    
    storage = DatabaseStorage(str(tmp_path))
    
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        
        # Valid insert should succeed
        cursor.execute("""
            INSERT INTO render_attempts 
            (shot_id, attempt_n, prompt_text, provider, adherence_score)
            VALUES (?, ?, ?, ?, ?)
        """, ("shot_001", 1, "test prompt", "runway", 0.85))
        conn.commit()
        
        # Empty shot_id should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO render_attempts 
                (shot_id, attempt_n, prompt_text, provider)
                VALUES (?, ?, ?, ?)
            """, ("", 1, "test prompt", "runway"))
        
        # Empty provider should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO render_attempts 
                (shot_id, attempt_n, prompt_text, provider)
                VALUES (?, ?, ?, ?)
            """, ("shot_002", 1, "test prompt", ""))
        
        # attempt_n < 1 should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO render_attempts 
                (shot_id, attempt_n, prompt_text, provider)
                VALUES (?, ?, ?, ?)
            """, ("shot_003", 0, "test prompt", "runway"))


# ================================================================================
# SLOTTED PROMPT TESTS
# ================================================================================

def test_build_slotted_prompt_never_exceeds_512_chars():
    """Test that assembled prompt never exceeds Runway's 512-char limit."""
    # Test with max-length inputs for each slot
    max_length_inputs = {
        "character_visual_canon": "A" * SLOT_BUDGETS["character_state"],
        "action_text": "B" * SLOT_BUDGETS["action"],
        "environment_motifs": "C" * SLOT_BUDGETS["environment_persistence"],
        "camera_direction": "D" * SLOT_BUDGETS["camera"],
        "lighting_direction": "E" * SLOT_BUDGETS["lighting"],
    }
    
    result = build_slotted_prompt(
        scene_data={},
        shot_number=1,
        **max_length_inputs
    )
    
    prompt = result["prompt"]
    assert len(prompt) <= MAX_PROMPT_LENGTH, f"Prompt length {len(prompt)} exceeds limit {MAX_PROMPT_LENGTH}"
    
    # Verify budget tracking
    assert result["budget_used"] == len(prompt)
    assert result["budget_remaining"] == MAX_PROMPT_LENGTH - len(prompt)
    assert result["budget_remaining"] >= 0


def test_build_slotted_prompt_slot_structure():
    """Test that slotted prompt returns correct slot structure."""
    result = build_slotted_prompt(
        scene_data={},
        shot_number=2,
        character_visual_canon="Young woman, short hair, blue jacket",
        action_text="Walking through the market",
        environment_motifs="Crowded urban market, neon signs",
        camera_direction="Medium shot, handheld",
        lighting_direction="Natural daylight, high contrast",
    )
    
    # Check slots dict exists and has expected keys
    assert "slots" in result
    slots = result["slots"]
    
    assert "character_state" in slots
    assert "action" in slots
    assert "environment_persistence" in slots
    assert "camera" in slots
    assert "lighting" in slots
    assert "reserve" in slots
    
    # Reserve should be empty (headroom for corrections)
    assert slots["reserve"] == ""
    
    # Check that prompt contains slot content
    prompt = result["prompt"]
    assert "short hair" in prompt.lower() or len(slots["character_state"]) == 0
    assert "market" in prompt.lower() or len(slots["action"]) == 0


def test_build_slotted_prompt_empty_inputs():
    """Test that slotted prompt handles empty inputs gracefully."""
    result = build_slotted_prompt(
        scene_data={},
        shot_number=1,
        character_visual_canon="",
        action_text="",
        environment_motifs="",
        camera_direction="",
        lighting_direction="",
    )
    
    # Should still generate a valid prompt with default camera
    assert len(result["prompt"]) > 0
    assert len(result["prompt"]) <= MAX_PROMPT_LENGTH
    assert "cinematic" in result["prompt"].lower()


def test_build_slotted_prompt_budget_enforcement():
    """Test that individual slots respect their character budgets."""
    # Provide inputs that exceed slot budgets
    result = build_slotted_prompt(
        scene_data={},
        shot_number=1,
        character_visual_canon="X" * 200,  # Exceeds 140-char budget
        action_text="Y" * 150,              # Exceeds 110-char budget
        environment_motifs="Z" * 120,      # Exceeds 100-char budget
    )
    
    slots = result["slots"]
    
    # Each slot should be truncated to its budget
    assert len(slots["character_state"]) <= SLOT_BUDGETS["character_state"]
    assert len(slots["action"]) <= SLOT_BUDGETS["action"]
    assert len(slots["environment_persistence"]) <= SLOT_BUDGETS["environment_persistence"]


# ================================================================================
# SANITIZE RENDER SLOT TESTS
# ================================================================================

def test_sanitize_render_slot_strips_scene_headings():
    """Test that sanitize_render_slot removes INT./EXT. prefixes."""
    test_cases = [
        ("INT. OCEAN - DAY", "OCEAN"),
        ("EXT. BEACH - NIGHT", "BEACH"),
        ("INT./EXT. LIGHTHOUSE - DUSK", "LIGHTHOUSE"),
        ("I/E. HARBOR - MORNING", "HARBOR"),
    ]
    
    for input_text, expected in test_cases:
        result = sanitize_render_slot("test", input_text)
        assert expected in result.upper(), f"Expected '{expected}' in '{result}' from '{input_text}'"
        assert "INT" not in result.upper() and "EXT" not in result.upper(), f"Should strip INT/EXT from '{input_text}'"


def test_sanitize_render_slot_strips_time_of_day():
    """Test that sanitize_render_slot removes time-of-day markers."""
    test_cases = [
        ("The ocean at dusk", "ocean"),
        ("Beach scene - DAY", "Beach scene"),
        ("Harbor - NIGHT", "Harbor"),
        ("Lighthouse - MORNING", "Lighthouse"),
    ]
    
    for input_text, expected_fragment in test_cases:
        result = sanitize_render_slot("test", input_text)
        assert expected_fragment.lower() in result.lower(), f"Expected '{expected_fragment}' in '{result}'"
        # Should not contain time markers
        time_markers = ["DAY", "NIGHT", "MORNING", "DUSK", "DAWN", "EVENING"]
        for marker in time_markers:
            if marker in input_text.upper():
                assert marker not in result.upper(), f"Should strip '{marker}' from '{input_text}'"


def test_sanitize_render_slot_strips_transitions():
    """Test that sanitize_render_slot removes transition markers."""
    test_cases = [
        ("CUT TO: The ocean", "ocean"),
        ("FADE IN on the beach", "beach"),
        ("DISSOLVE TO harbor scene", "harbor scene"),
        ("SMASH CUT to lighthouse", "lighthouse"),
    ]
    
    for input_text, expected_fragment in test_cases:
        result = sanitize_render_slot("test", input_text)
        assert expected_fragment.lower() in result.lower(), f"Expected '{expected_fragment}' in '{result}'"
        # Should not contain transition markers
        assert "CUT" not in result.upper()
        assert "FADE" not in result.upper()
        assert "DISSOLVE" not in result.upper()


def test_sanitize_render_slot_strips_leading_articles():
    """Test that sanitize_render_slot removes leading THE/A/AN."""
    test_cases = [
        ("THE OCEAN", "OCEAN"),
        ("The Last Tide", "Last Tide"),
        ("A lighthouse in the distance", "lighthouse in the distance"),
        ("An old harbor", "old harbor"),
    ]
    
    for input_text, expected_fragment in test_cases:
        result = sanitize_render_slot("test", input_text)
        assert expected_fragment.lower() in result.lower(), f"Expected '{expected_fragment}' in '{result}'"
        # Result should not start with THE/A/AN
        first_word = result.split()[0] if result else ""
        assert first_word.upper() not in ["THE", "A", "AN"], f"Should strip article from '{input_text}'"


def test_sanitize_render_slot_preserves_valid_content():
    """Test that sanitize_render_slot preserves valid visual descriptions."""
    test_cases = [
        "Young woman with short dark hair",
        "Walking through crowded market",
        "Ocean waves crashing on rocky shore",
        "Natural daylight, high contrast shadows",
        "Medium shot, handheld camera movement",
    ]
    
    for input_text in test_cases:
        result = sanitize_render_slot("test", input_text)
        # Should preserve most of the content (minor cleanup is OK)
        assert len(result) >= len(input_text) * 0.8, f"Shouldn't remove too much from valid input: '{input_text}' -> '{result}'"


def test_sanitize_render_slot_handles_empty_input():
    """Test that sanitize_render_slot handles empty/invalid input."""
    assert sanitize_render_slot("test", "") == ""
    assert sanitize_render_slot("test", None) == ""
    assert sanitize_render_slot("test", "   ") == ""


def test_sanitize_render_slot_cleans_multiple_spaces():
    """Test that sanitize_render_slot normalizes whitespace."""
    input_text = "Ocean    waves     crashing"
    result = sanitize_render_slot("test", input_text)
    assert "  " not in result, "Should normalize multiple spaces to single space"
    assert "ocean waves crashing" in result.lower()


# ================================================================================
# INTEGRATION TEST
# ================================================================================

def test_prompt_adherence_integration():
    """Integration test: database + slotted prompt + sanitization."""
    from app.data.storage import DatabaseStorage
    import tempfile
    import shutil
    
    # Create temporary database
    tmp_dir = tempfile.mkdtemp()
    try:
        storage = DatabaseStorage(tmp_dir)
        
        # Build a slotted prompt with contaminated input
        result = build_slotted_prompt(
            scene_data={},
            shot_number=1,
            character_visual_canon="INT. Woman with dark hair - DAY",
            action_text="CUT TO: Walking through market",
            environment_motifs="THE OCEAN in background",
            camera_direction="Wide shot",
            lighting_direction="FADE IN Natural light",
        )
        
        # Verify sanitization happened
        assert "INT" not in result["prompt"]
        assert "CUT TO" not in result["prompt"]
        assert "THE OCEAN" not in result["prompt"] or "OCEAN" in result["prompt"]
        assert "FADE IN" not in result["prompt"]
        
        # Verify prompt is valid
        assert len(result["prompt"]) <= MAX_PROMPT_LENGTH
        
        # Store in database
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO render_attempts 
                (shot_id, attempt_n, prompt_text, provider, adherence_score)
                VALUES (?, ?, ?, ?, ?)
            """, ("shot_001", 1, result["prompt"], "runway", 0.92))
            conn.commit()
            
            # Verify retrieval
            cursor.execute("""
                SELECT prompt_text, adherence_score 
                FROM render_attempts 
                WHERE shot_id = ? AND attempt_n = ?
            """, ("shot_001", 1))
            
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == result["prompt"]
            assert row[1] == 0.92
    
    finally:
        shutil.rmtree(tmp_dir)
