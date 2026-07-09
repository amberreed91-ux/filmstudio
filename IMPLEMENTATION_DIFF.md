# Implementation Diff Summary

## Overview

Built substrate for prompt-adherence system in Studio backend with:
- Database table for tracking render attempts
- Slotted prompt assembly with fixed character budgets
- Slot sanitization to prevent scene-heading contamination
- Comprehensive test suite (14 tests, all passing)

---

## Files Modified

### 1. `studio-backend/app/data/storage.py`

**Change**: Added migration 26 for `render_attempts` table

**Lines added**: ~20 lines

**Key changes**:
- New table: `render_attempts` with 8 columns
- Composite primary key: `(shot_id, attempt_n)`
- Two indexes: on `shot_id` and `created_at`
- CHECK constraints on `shot_id`, `provider`, `attempt_n`

**Schema**:
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
```

---

### 2. `studio-backend/app/services/shot_prompt_builder.py`

**Change**: Added slotted prompt assembly with fixed character budgets

**Lines added**: ~130 lines

**Key additions**:
- Constants: `SLOT_BUDGETS`, `MAX_PROMPT_LENGTH`
- Function: `build_slotted_prompt()` - builds slot-addressable prompts
- Function: `_truncate_to_budget()` - helper for budget enforcement

**Slot structure**:
```python
SLOT_BUDGETS = {
    "character_state": 140,      # Visual canon only
    "action": 110,                # One action per shot
    "environment_persistence": 100,  # Recurring motifs
    "camera": 70,                 # Controlled vocabulary
    "lighting": 60,               # Controlled vocabulary
    "reserve": 32,                # Correction headroom
}
```

**Returns**:
```python
{
    "prompt": "assembled prompt string (<=512 chars)",
    "slots": {"character_state": "...", "action": "...", ...},
    "budget_used": 387,
    "budget_remaining": 125
}
```

---

### 3. `studio-backend/app/services/script_parser.py`

**Change**: Added slot sanitization function

**Lines added**: ~60 lines

**Key addition**:
- Function: `sanitize_render_slot(slot_name, text)` - strips scene-heading tokens

**Removes**:
- INT./EXT. prefixes
- Time-of-day markers (DAY, NIGHT, MORNING, DUSK, etc.)
- Transition tokens (CUT TO, FADE IN, DISSOLVE TO, etc.)
- Leading articles (THE, A, AN)

**Example**:
```python
sanitize_render_slot("environment", "INT. THE OCEAN - DAY")
# Returns: "OCEAN"
```

---

## Files Created

### 1. `studio-backend/tests/test_prompt_adherence_substrate.py`

**Lines**: ~400 lines

**14 tests covering**:
- Database schema validation (2 tests)
- Slotted prompt assembly (4 tests)
- Slot sanitization (7 tests)
- Integration test (1 test)

**All tests pass**: ✅ 14/14

---

### 2. `studio-backend/verify_render_attempts_table.py`

**Lines**: ~150 lines

**Purpose**: Verification script to run after backend starts

**Checks**:
- Schema version >= 26
- Table exists with correct columns
- Indexes present
- Primary key constraint
- Insert/retrieval works

---

### 3. `studio-backend/PROMPT_ADHERENCE_SUBSTRATE_IMPLEMENTATION.md`

**Lines**: ~450 lines

**Contents**:
- Complete implementation documentation
- Usage examples
- Architecture compliance notes
- Test output

---

### 4. `studio-backend/SLOT_BUDGET_REFERENCE.md`

**Lines**: ~300 lines

**Contents**:
- Slot budget table
- Assembly order
- Sanitization rules
- Usage guidelines
- Quick reference card

---

### 5. `PROMPT_ADHERENCE_IMPLEMENTATION_SUMMARY.md`

**Lines**: ~250 lines

**Contents**:
- High-level summary
- Files changed overview
- Test results
- Verification instructions

---

## Code Statistics

| Metric | Count |
|--------|-------|
| Files modified | 3 |
| Files created | 5 |
| Total lines added (code) | ~210 lines |
| Total lines added (tests) | ~400 lines |
| Total lines added (docs) | ~1,000 lines |
| Database migrations added | 1 (migration 26) |
| Functions added | 3 |
| Tests added | 14 |
| Test pass rate | 100% (14/14) |

---

## Test Results

```bash
$ .venv/bin/python -m pytest tests/test_prompt_adherence_substrate.py -v

======================== 14 passed, 1 warning in 0.11s =========================
```

**All 14 tests pass** ✅

**Test categories**:
- ✅ Database schema (2 tests)
- ✅ Slotted prompts (4 tests)
- ✅ Sanitization (7 tests)
- ✅ Integration (1 test)

---

## Architecture Compliance

✅ **Service boundaries**: All business logic in services, not routes  
✅ **Database layer**: Migration-based schema, no raw SQL in routes  
✅ **Testing**: Unit + integration tests, no boundary violations  
✅ **Python 3.11**: Type hints, modern syntax (str | None)  
✅ **Error handling**: Structured stability error classes  
✅ **Logging**: Stage logging with context (shot_id, budget_used)  
✅ **AGENTS.md patterns**: Blocklist approach, stable contracts  

---

## Key Design Decisions

### 1. Why Slotted Structure?

**Problem**: Monolithic prompts can't be corrected at granular level.

**Solution**: Fixed slots with individual budgets enable:
- Slot-level corrections on failed attempts
- Addressable structure for downstream logic
- Budget enforcement per concern

### 2. Why Reserve Slot?

**Problem**: Corrections need headroom without violating 512-char limit.

**Solution**: 32-char reserve slot stays empty on first render, available for corrections on retries.

### 3. Why Sanitization?

**Problem**: ScriptParser output can leak scene headings ("INT. OCEAN - DAY") into render prompts.

**Solution**: Strip structural tokens before rendering, ensuring prompts contain only visual descriptions.

### 4. Why These Budgets?

**Priority order matches Runway token weighting**:
- Most-emphasized slots come first (character, action)
- Less-emphasized later (camera, lighting)
- Reserve last (correction headroom)

**Budget allocation**:
- Character state: 140 chars (most detail needed)
- Action: 110 chars (clear action description)
- Environment: 100 chars (persistent motifs)
- Camera: 70 chars (controlled vocab)
- Lighting: 60 chars (controlled vocab)
- Reserve: 32 chars (correction headroom)

Total: ≤512 chars (Runway's hard limit)

---

## Usage Pattern

```python
from app.services.shot_prompt_builder import build_slotted_prompt
from app.data.storage import DatabaseStorage

# 1. Build prompt with slotted structure
result = build_slotted_prompt(
    scene_data={},
    shot_number=1,
    character_visual_canon="Young woman, short dark hair, blue jacket",
    action_text="Walking through crowded market",
    environment_motifs="Urban market with neon signs, ocean in background",
    camera_direction="Wide establishing shot",
    lighting_direction="Natural daylight, high contrast",
)

# 2. Send to provider
render_output = runway_provider.submit(result["prompt"])

# 3. Store attempt
storage = DatabaseStorage("./data")
with storage._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO render_attempts 
        (shot_id, attempt_n, prompt_text, provider, adherence_score)
        VALUES (?, ?, ?, ?, ?)
    """, ("shot_001", 1, result["prompt"], "runway", 0.92))
    conn.commit()

# 4. On failure, use slots for correction
if adherence_score < 0.85:
    # Adjust specific slots, re-render
    corrected = build_slotted_prompt(
        scene_data={},
        shot_number=1,
        character_visual_canon=result["slots"]["character_state"] + ", more detail",
        # ... other slots
    )
```

---

## Next Steps (Not Implemented)

The substrate is complete. Future work can build on this:

1. **Adherence scoring service**: Compare rendered output to prompt slots
2. **Correction engine**: Use `diff_json` to identify failing slots
3. **Retry logic**: Use `reserve` slot for corrective tokens
4. **Analytics dashboard**: Visualize adherence trends
5. **Provider comparison**: Track adherence per provider

---

## Verification

After starting the backend:

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
✅ Primary key constraint exists: (shot_id, attempt_n)
✅ Insert and retrieval test passed

✅ All verifications passed!
```

---

## Summary

✅ **Complete substrate** for prompt-adherence tracking  
✅ **Production-ready** code following Studio patterns  
✅ **Comprehensive tests** with 14/14 passing  
✅ **Documentation** with usage examples and reference  
✅ **Verification script** for post-deployment checks  

The implementation is complete, tested, and ready for use.
