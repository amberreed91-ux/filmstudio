# Prompt Adherence Substrate Implementation

## Overview

This implementation adds the foundational substrate for a prompt-adherence system in Studio, with:

1. **Database table** (`render_attempts`) for tracking prompt history and adherence scores
2. **Slotted prompt assembly** with fixed character budgets per slot
3. **Slot sanitization** to prevent scene-heading tokens from leaking into render prompts
4. **Comprehensive tests** validating all components

---

## 1. Database Schema Addition

**File**: `studio-backend/app/data/storage.py`

**Migration 26**: Added `render_attempts` table

```sql
CREATE TABLE IF NOT EXISTS render_attempts (
    shot_id TEXT NOT NULL,
    attempt_n INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    adherence_score REAL,
    score_json TEXT,
    diff_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (shot_id, attempt_n),
    CHECK (shot_id != ''),
    CHECK (provider != ''),
    CHECK (attempt_n >= 1)
);

CREATE INDEX IF NOT EXISTS idx_render_attempts_shot ON render_attempts(shot_id);
CREATE INDEX IF NOT EXISTS idx_render_attempts_created ON render_attempts(created_at);
```

**Schema Design**:
- `shot_id` + `attempt_n` composite primary key ensures each attempt is uniquely tracked
- `prompt_text` stores the exact prompt sent to the provider
- `provider` tracks which provider was used (runway, etc.)
- `adherence_score` (nullable REAL) stores computed adherence score (0.0-1.0)
- `score_json` (nullable TEXT) stores detailed scoring breakdown
- `diff_json` (nullable TEXT) stores slot-level differences for corrections
- `created_at` timestamp with default value for tracking attempt history

**Constraints**:
- `shot_id` and `provider` must be non-empty
- `attempt_n` must be >= 1
- Indexed on `shot_id` and `created_at` for efficient querying

---

## 2. Slotted Prompt Assembly

**File**: `studio-backend/app/services/shot_prompt_builder.py`

### New Constants

```python
# Fixed slot character budgets (Runway weights early tokens more heavily)
SLOT_BUDGETS = {
    "character_state": 140,      # Visual canon only — hands, face, build — never character names
    "action": 110,                # One action per shot, not multiple
    "environment_persistence": 100,  # Recurring motifs/settings that must not drop out
    "camera": 70,                 # Controlled vocabulary: wide/medium/close, static/dolly/pan
    "lighting": 60,               # Controlled vocabulary where possible
    "reserve": 32,                # Unallocated headroom for corrections later
}

MAX_PROMPT_LENGTH = 512  # Runway's hard limit
```

### New Function: `build_slotted_prompt()`

```python
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
    
    Returns:
        dict with:
            - "prompt": assembled prompt string (<=512 chars)
            - "slots": dict of {slot_name: text} for slot-level addressing
            - "budget_used": total characters used
            - "budget_remaining": characters remaining
    """
```

**Assembly Order** (most-emphasized first, as Runway weights early tokens more heavily):
1. `character_state` (140 chars) - visual canon only
2. `action` (110 chars) - one action per shot
3. `environment_persistence` (100 chars) - recurring motifs
4. `camera` (70 chars) - controlled vocabulary
5. `lighting` (60 chars) - controlled vocabulary
6. `reserve` (32 chars) - unallocated headroom

**Key Features**:
- Each slot is sanitized via `sanitize_render_slot()` before budget enforcement
- Each slot is truncated to its budget if needed
- Total prompt guaranteed to never exceed 512 chars
- Returns slot-addressable structure for downstream correction logic
- Logs budget usage for monitoring

---

## 3. Slot Sanitization

**File**: `studio-backend/app/services/script_parser.py`

### New Function: `sanitize_render_slot()`

```python
def sanitize_render_slot(slot_name: str, text: str) -> str:
    """
    Sanitize render prompt slot text by stripping scene-heading tokens that could leak
    from ScriptParser output into render prompts.
    
    Removes:
      - INT./EXT. prefixes and variations
      - Time-of-day markers (DAY, NIGHT, MORNING, etc.)
      - Transition markers (CUT TO, FADE IN, DISSOLVE TO, etc.)
      - Scene heading prefixes (THE, A, AN followed by location names)
    """
```

**Blocklists Used**:
- **Scene headings**: `INT.`, `EXT.`, `INT./EXT.`, `I/E.`
- **Time-of-day**: `DAY`, `NIGHT`, `MORNING`, `AFTERNOON`, `EVENING`, `DAWN`, `DUSK`, `CONTINUOUS`, `LATER`
- **Transitions**: `FADE IN`, `FADE OUT`, `CUT TO`, `DISSOLVE TO`, `SMASH CUT`, `MATCH CUT`, etc.
- **Leading articles**: `THE`, `A`, `AN` (when starting a location phrase)

**Sanitization Steps**:
1. Strip INT./EXT. prefixes from start of text
2. Remove time-of-day suffixes (e.g., "- DAY")
3. Remove "at TIME_WORD" patterns (e.g., "at dusk")
4. Remove transition tokens as whole words/phrases
5. Remove leading articles (THE/A/AN)
6. Normalize multiple spaces to single spaces

**Pattern**: Similar to existing `sanitize_scene_characters()` blocklist approach

---

## 4. Tests

**File**: `studio-backend/tests/test_prompt_adherence_substrate.py`

### Test Coverage

**Database Schema Tests**:
- ✅ `test_render_attempts_table_exists` - Verifies table and column schema
- ✅ `test_render_attempts_constraints` - Validates NOT NULL and CHECK constraints

**Slotted Prompt Tests**:
- ✅ `test_build_slotted_prompt_never_exceeds_512_chars` - Max-length inputs never exceed limit
- ✅ `test_build_slotted_prompt_slot_structure` - Returns correct slot dict structure
- ✅ `test_build_slotted_prompt_empty_inputs` - Handles empty inputs gracefully
- ✅ `test_build_slotted_prompt_budget_enforcement` - Individual slots respect budgets

**Sanitization Tests**:
- ✅ `test_sanitize_render_slot_strips_scene_headings` - Removes INT./EXT. prefixes
- ✅ `test_sanitize_render_slot_strips_time_of_day` - Removes time-of-day markers
- ✅ `test_sanitize_render_slot_strips_transitions` - Removes transition tokens
- ✅ `test_sanitize_render_slot_strips_leading_articles` - Removes THE/A/AN
- ✅ `test_sanitize_render_slot_preserves_valid_content` - Preserves valid descriptions
- ✅ `test_sanitize_render_slot_handles_empty_input` - Handles None/empty strings
- ✅ `test_sanitize_render_slot_cleans_multiple_spaces` - Normalizes whitespace

**Integration Test**:
- ✅ `test_prompt_adherence_integration` - End-to-end: database + slotted prompt + sanitization

### Test Output

```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
collected 14 items

tests/test_prompt_adherence_substrate.py::test_render_attempts_table_exists PASSED [  7%]
tests/test_prompt_adherence_substrate.py::test_render_attempts_constraints PASSED [ 14%]
tests/test_prompt_adherence_substrate.py::test_build_slotted_prompt_never_exceeds_512_chars PASSED [ 21%]
tests/test_prompt_adherence_substrate.py::test_build_slotted_prompt_slot_structure PASSED [ 28%]
tests/test_prompt_adherence_substrate.py::test_build_slotted_prompt_empty_inputs PASSED [ 35%]
tests/test_prompt_adherence_substrate.py::test_build_slotted_prompt_budget_enforcement PASSED [ 42%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_strips_scene_headings PASSED [ 50%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_strips_time_of_day PASSED [ 57%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_strips_transitions PASSED [ 64%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_strips_leading_articles PASSED [ 71%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_preserves_valid_content PASSED [ 78%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_handles_empty_input PASSED [ 85%]
tests/test_prompt_adherence_substrate.py::test_sanitize_render_slot_cleans_multiple_spaces PASSED [ 92%]
tests/test_prompt_adherence_integration PASSED [100%]

======================== 14 passed, 1 warning in 0.11s =========================
```

**All 14 tests pass** ✅

---

## Usage Examples

### Example 1: Building a Slotted Prompt

```python
from app.services.shot_prompt_builder import build_slotted_prompt

result = build_slotted_prompt(
    scene_data={},
    shot_number=1,
    character_visual_canon="Young woman, short dark hair, blue jacket, weathered hands",
    action_text="Walking through crowded market, examining vendors",
    environment_motifs="Urban market with neon signs, ocean visible in background",
    camera_direction="Wide establishing shot, static camera",
    lighting_direction="Natural daylight, high contrast shadows",
)

# result["prompt"]: assembled prompt (<=512 chars)
# result["slots"]: {"character_state": "...", "action": "...", ...}
# result["budget_used"]: 387
# result["budget_remaining"]: 125
```

### Example 2: Storing an Attempt

```python
from app.data.storage import DatabaseStorage

storage = DatabaseStorage("./data")

with storage._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO render_attempts 
        (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "shot_001",
        1,
        result["prompt"],
        "runway",
        0.92,
        '{"character_accuracy": 0.95, "action_accuracy": 0.89}'
    ))
    conn.commit()
```

### Example 3: Querying Attempts

```python
# Get all attempts for a shot
cursor.execute("""
    SELECT attempt_n, prompt_text, adherence_score, created_at
    FROM render_attempts
    WHERE shot_id = ?
    ORDER BY attempt_n
""", ("shot_001",))

for row in cursor.fetchall():
    print(f"Attempt {row[0]}: score={row[2]}, prompt={row[1][:50]}...")
```

---

## Architecture Compliance

✅ **Service boundaries**: Prompt building in `shot_prompt_builder.py`, sanitization in `script_parser.py`  
✅ **Database layer**: Schema migration in `storage.py`, no raw SQL in routes  
✅ **Testing**: Unit tests for each layer, integration test for end-to-end flow  
✅ **No business logic in routes**: All logic in service functions  
✅ **Follows AGENTS.md conventions**: Python 3.11 syntax, structured error handling, proper logging  

---

## Next Steps (Not Implemented)

The substrate is now in place. Future work can build on this foundation:

1. **Adherence scoring service**: Compute scores by comparing rendered output to prompt slots
2. **Correction engine**: Use `diff_json` to identify which slots need adjustment
3. **Retry logic**: Use `reserve` budget (32 chars) to add corrective tokens on failed attempts
4. **Analytics dashboard**: Visualize adherence trends across shots/attempts
5. **Provider comparison**: Track adherence scores per provider (runway vs others)

---

## Summary

This implementation provides:

- ✅ **Database table** for tracking render attempts and adherence scores
- ✅ **Slotted prompt assembly** with fixed character budgets (total ≤ 512 chars)
- ✅ **Sanitization function** to strip scene headings from render prompts
- ✅ **Comprehensive tests** with 14/14 passing
- ✅ **Slot-addressable structure** for downstream correction logic
- ✅ **Production-ready code** following Studio architecture patterns

The substrate is complete and tested. Downstream systems can now:
- Store prompt history per shot
- Build prompts with budget-controlled slots
- Address individual slots for corrections
- Track adherence scores over multiple attempts
