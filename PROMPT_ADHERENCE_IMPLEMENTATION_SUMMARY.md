# Prompt Adherence Substrate Implementation Summary

## What Was Built

A complete substrate for prompt-adherence tracking in Studio, with:

1. **Database persistence** for render attempts and adherence scores
2. **Fixed-slot prompt assembly** with strict character budgets  
3. **Slot sanitization** to prevent scene-heading contamination
4. **Comprehensive test suite** (14 tests, all passing)

---

## Files Changed

### 1. Database Schema (`studio-backend/app/data/storage.py`)

**Added migration 26**: `render_attempts` table

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

**Purpose**: Track every render attempt with its exact prompt text, provider, and adherence score. Enables:
- Historical analysis of prompt effectiveness
- Slot-level corrections on failed attempts
- Provider comparison (runway vs others)

---

### 2. Prompt Builder (`studio-backend/app/services/shot_prompt_builder.py`)

**Added constants**:
```python
SLOT_BUDGETS = {
    "character_state": 140,      # Visual canon only — never character names
    "action": 110,                # One action per shot
    "environment_persistence": 100,  # Recurring motifs/settings
    "camera": 70,                 # Controlled vocabulary
    "lighting": 60,               # Controlled vocabulary
    "reserve": 32,                # Headroom for corrections
}

MAX_PROMPT_LENGTH = 512  # Runway's hard limit
```

**Added function**: `build_slotted_prompt()`

Returns a dict with:
- `prompt`: assembled string (<=512 chars guaranteed)
- `slots`: dict of {slot_name: text} for slot-level addressing
- `budget_used`: total characters used
- `budget_remaining`: characters remaining

**Key Design**:
- Slots assembled in priority order (character → action → environment → camera → lighting)
- Each slot sanitized via `sanitize_render_slot()` before budget enforcement
- Each slot truncated to budget if needed
- Reserve slot left empty for correction headroom
- Runway weights early tokens more, so most-emphasized slots come first

---

### 3. Slot Sanitization (`studio-backend/app/services/script_parser.py`)

**Added function**: `sanitize_render_slot(slot_name: str, text: str) -> str`

**Removes**:
- INT./EXT. prefixes (e.g., "INT. OCEAN - DAY" → "OCEAN")
- Time-of-day markers (e.g., "at dusk", "- NIGHT")
- Transition tokens (e.g., "CUT TO", "FADE IN")
- Leading articles (e.g., "THE OCEAN" → "OCEAN")

**Pattern**: Uses blocklists similar to existing `sanitize_scene_characters()` function

**Why needed**: ScriptParser output can leak scene-heading tokens into render prompts. This ensures prompts contain only visual descriptions, not structural script tokens.

---

### 4. Tests (`studio-backend/tests/test_prompt_adherence_substrate.py`)

**14 tests, all passing**:

**Database tests** (2):
- ✅ Table exists with correct schema
- ✅ Constraints enforced (NOT NULL, CHECK)

**Slotted prompt tests** (4):
- ✅ Never exceeds 512 chars (tested with max-length inputs)
- ✅ Returns correct slot structure
- ✅ Handles empty inputs gracefully
- ✅ Enforces individual slot budgets

**Sanitization tests** (7):
- ✅ Strips INT./EXT. prefixes
- ✅ Strips time-of-day markers
- ✅ Strips transition tokens
- ✅ Strips leading articles (THE/A/AN)
- ✅ Preserves valid visual descriptions
- ✅ Handles empty/None input
- ✅ Normalizes whitespace

**Integration test** (1):
- ✅ End-to-end: database + slotted prompt + sanitization

---

## Test Output

```bash
$ .venv/bin/python -m pytest tests/test_prompt_adherence_substrate.py -v

======================== 14 passed, 1 warning in 0.11s =========================
```

All tests pass ✅

---

## Usage Example

```python
from app.services.shot_prompt_builder import build_slotted_prompt
from app.data.storage import DatabaseStorage

# 1. Build slotted prompt
result = build_slotted_prompt(
    scene_data={},
    shot_number=1,
    character_visual_canon="Young woman, short dark hair, blue jacket",
    action_text="Walking through crowded market",
    environment_motifs="Urban market with neon signs, ocean in background",
    camera_direction="Wide establishing shot, static",
    lighting_direction="Natural daylight, high contrast",
)

# result["prompt"] is <=512 chars, ready for Runway
# result["slots"] is slot-addressable for corrections
# result["budget_used"] and result["budget_remaining"] for monitoring

# 2. Store attempt in database
storage = DatabaseStorage("./data")
with storage._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO render_attempts 
        (shot_id, attempt_n, prompt_text, provider, adherence_score)
        VALUES (?, ?, ?, ?, ?)
    """, ("shot_001", 1, result["prompt"], "runway", 0.92))
    conn.commit()

# 3. Query attempts later for analysis
cursor.execute("""
    SELECT attempt_n, prompt_text, adherence_score 
    FROM render_attempts 
    WHERE shot_id = ? 
    ORDER BY attempt_n
""", ("shot_001",))
```

---

## Architecture Compliance

✅ **Service boundaries**: No route logic, all in services  
✅ **Database layer**: Migration-based schema, no raw SQL in routes  
✅ **Testing**: Unit tests per layer, integration test end-to-end  
✅ **Python 3.11 conventions**: Type hints, str | None syntax  
✅ **Logging**: Stage logging with project_id, shot_id, budget_used  
✅ **AGENTS.md patterns**: Blocklist approach, stable contract design  

---

## Verification

Run after starting the backend:

```bash
cd studio-backend
.venv/bin/python verify_render_attempts_table.py
```

Expected output:
```
✅ Current schema version: 26
✅ render_attempts table exists
✅ Column exists: shot_id (TEXT)
✅ Column exists: attempt_n (INTEGER)
✅ Column exists: prompt_text (TEXT)
✅ Column exists: provider (TEXT)
✅ Column exists: adherence_score (REAL)
✅ Column exists: score_json (TEXT)
✅ Column exists: diff_json (TEXT)
✅ Column exists: created_at (TEXT)
✅ Indexes: ['idx_render_attempts_shot', 'idx_render_attempts_created', ...]
✅ Primary key constraint exists: (shot_id, attempt_n)
✅ Insert and retrieval test passed

✅ All verifications passed! render_attempts table is ready.
```

---

## What's Ready for Use

1. **Database table** ready to store render attempts
2. **Slotted prompt builder** ready to generate budget-controlled prompts
3. **Slot sanitization** ready to clean ScriptParser output
4. **Slot-addressable structure** ready for downstream correction logic
5. **Tests** confirming all components work

---

## Next Steps (Not Implemented)

The substrate is complete. Future work can build on this:

1. **Adherence scoring service**: Compare rendered output to prompt slots
2. **Correction engine**: Use `diff_json` to identify which slots need adjustment
3. **Retry logic**: Use `reserve` budget to add corrective tokens on attempt 2+
4. **Analytics dashboard**: Visualize adherence trends
5. **Provider comparison**: Track adherence per provider

---

## Summary

✅ **Database migration 26** added  
✅ **Slotted prompt assembly** with fixed budgets  
✅ **Slot sanitization** function  
✅ **14 tests passing**  
✅ **Verification script** provided  
✅ **Production-ready** code following Studio patterns

The prompt-adherence substrate is complete and tested.
