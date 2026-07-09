# Corrective Diff Generator Implementation Report

**Date:** 2026-07-04  
**Component:** Adherence Service - Groq-based Corrective Diff Generator  
**Status:** ✅ IMPLEMENTED AND TESTED

---

## Summary

Successfully implemented the real Groq-based corrective diff generator in `adherence_service.py`. The mock implementation has been replaced with a production-ready Llama 3.3 70B corrector that analyzes vision scoring gaps and generates precise correction operations.

---

## Implementation Details

### 1. Core Corrector Implementation (`_call_groq_corrector`)

**Location:** `studio-backend/app/services/adherence_service.py`

**Key Features:**
- Uses Llama 3.3 70B Versatile via Groq API
- Text-only reasoning (cheap - no vision analysis)
- Forced JSON mode for structured output
- Truncation detection with automatic retry
- Comprehensive error handling and validation

**System Prompt:**
- Instructs model to act as prompt engineer
- Defines three operation types: `replace`, `strengthen`, `prepend_emphasis`
- Enforces character budget constraints
- Requires specific reasoning for each correction

**Token Budgets:**
- Default: 2048 tokens (typical correction JSON)
- Retry: 4096 tokens (if truncated)
- Same pattern as vision scorer fix (Loop 1)

**Validation:**
- Ensures `ops` and `chars_remaining` fields present
- Validates each op has required fields: `slot`, `op`, `old_text`, `new_text`, `reason`, `char_delta`
- Confirms operation types are valid
- Calculates `chars_remaining` if model omits it

---

## 2. Manual Test Script Enhancement

**Updated:** `studio-backend/manual_adherence_check.py`

**New Features:**
- Automatically calls corrector when verdict is "correctable"
- Checks for GROQ_API_KEY availability
- Displays corrective diff alongside score report
- Shows before/after comparison for modified slots
- Includes diff output in JSON mode

**New Function:** `format_corrective_diff()`
- Human-readable formatting for CorrectiveDiff objects
- Shows operation type, old/new text, reason, character delta
- Matches existing report formatting style

---

## 3. Direct Corrector Test

**Created:** `studio-backend/test_corrector_direct.py`

**Purpose:** Isolated testing of corrector logic without vision scoring dependency

**Test Case:** "Red Jacket in Desert" vs "Coastal Village"
- Simulates deliberately wrong prompt (desert scenario)
- Mocks vision scoring output (coastal village observed)
- 4 failed dimensions: character_state, action, environment_persistence, lighting
- 1 passing dimension: camera (score 65)

---

## Test Results

### Corrector Output Analysis

**Failed Dimensions Input:**
```
CHARACTER STATE (Score: 15.0)
  Expected:  woman wearing bright red jacket, blonde hair
  Observed:  woman in dark blue coat, dark hair, walking along coastal path
  Evidence:  Character is wearing dark blue clothing, not red. Hair appears dark, not blonde.

ACTION (Score: 30.0)
  Expected:  walking through sandy desert dunes
  Observed:  walking along rocky coastal cliffside path
  Evidence:  Character is walking along a coastal path, not through desert dunes.

ENVIRONMENT PERSISTENCE (Score: 5.0)
  Expected:  vast empty desert, no vegetation
  Observed:  coastal fishing village, stone buildings, ocean visible, lush vegetation
  Evidence:  Environment is coastal village with buildings and ocean, completely different from desert.

LIGHTING (Score: 40.0)
  Expected:  harsh midday sun, deep shadows
  Observed:  soft overcast daylight, diffused shadows
  Evidence:  Lighting is soft overcast, not harsh midday sun. No deep shadows visible.
```

**Generated Corrections (4 operations):**

1. **CHARACTER STATE** - `replace`
   - Old: `woman wearing bright red jacket, blonde hair`
   - New: `woman wearing bright red jacket, blonde hair, not dark blue coat or dark hair`
   - Reason: Character is wearing dark blue clothing, not red, and hair appears dark, not blonde. Completely replacing to ensure correct attire and hair color.
   - Delta: +36 chars

2. **ACTION** - `replace`
   - Old: `walking through sandy desert dunes`
   - New: `walking through sandy desert dunes, not along coastal path`
   - Reason: Character is walking along a coastal path, not through desert dunes. Replacing to ensure correct environment for the action.
   - Delta: +24 chars

3. **ENVIRONMENT PERSISTENCE** - `replace`
   - Old: `vast empty desert, no vegetation`
   - New: `vast empty desert, no vegetation, no buildings or ocean`
   - Reason: Environment is coastal village with buildings and ocean, completely different from desert. Replacing to ensure correct environment.
   - Delta: +24 chars

4. **LIGHTING** - `replace`
   - Old: `harsh midday sun, deep shadows`
   - New: `harsh midday sun, deep shadows, not soft overcast`
   - Reason: Lighting is soft overcast, not harsh midday sun. Replacing to ensure correct lighting conditions.
   - Delta: +20 chars

**Budget Management:**
- Starting: 200 chars remaining
- Total delta: +104 chars
- Final: 96 chars remaining

**Assembled Corrected Prompt (314 chars):**
```
woman wearing bright red jacket, blonde hair, not dark blue coat or dark hair. walking through sandy desert dunes, not along coastal path. vast empty desert, no vegetation, no buildings or ocean. wide establishing shot, drone perspective. harsh midday sun, deep shadows, not soft overcast. Cinematic, film quality.
```

---

## Analysis

### Correction Strategy

The corrector consistently uses **negative constraints** (adding "not X" clauses) to:
1. Reinforce the original intent
2. Explicitly reject what was observed
3. Guide the video generator away from the failed rendering

This is a sensible strategy because:
- It preserves the original positive description
- It adds specific constraints based on actual failure evidence
- It increases prompt specificity without complete rewrites
- It fits within character budget constraints

### Operation Type Usage

**Test 1: Severe Failures (scores 5-40)**
- All 4 corrections used `replace` operation
- ✅ Appropriate for large mismatches (desert vs coastal village)
- ✅ Each replacement adds negative constraint rather than full rewrite

**Test 2: Minor Failure (score 55 - "blue tint" vs "warm")**
- Used `replace` with minimal text change
- Added "warm" qualifier to existing text
- Delta: +7 chars only
- Strategy: Subtle reinforcement rather than negative constraint

**Test 3: Moderate Failures (scores 35-40 - "blue dress" vs "red", "walking" vs "dancing")**
- Both used `replace` with negative constraints
- "red dress, long dark hair, no blue clothing" (+24 chars)
- "dancing gracefully, not walking, in the center of the room" (+23 chars)
- Consistent with severe failure strategy

**Observation:** The model primarily uses `replace` operation across all failure severities, varying only the degree of modification:
- Minor failures: small positive additions ("soft **warm** natural window light")
- Moderate/severe failures: negative constraints ("not X", "no Y")

### Reasoning Quality

Each correction includes specific, evidence-based reasoning:
- References the observed vs expected gap
- Explains what needs to be enforced
- Directly tied to evidence from vision scorer

---

## Validation Checklist

- ✅ Real Groq API call implemented (not mock)
- ✅ Uses Llama 3.3 70B Versatile
- ✅ Input: failed_slots with expected/observed pairs
- ✅ Output: exact CorrectiveDiff schema
- ✅ Forced JSON mode via `response_format`
- ✅ Only failed slots get operations (camera dimension passed, no op generated)
- ✅ Truncation detection with retry logic
- ✅ Extended manual_adherence_check.py with auto-diff on "correctable" verdict
- ✅ Tested against deliberately-wrong case
- ✅ Corrections make semantic sense given the gaps

---

## What's NOT in This Implementation

Per requirements, the following are intentionally excluded (coming next):

- ❌ Database persistence for AdherenceScore or CorrectiveDiff
- ❌ Retry loop integration (attempt 1 → score → diff → attempt 2)
- ❌ Frame extraction pipeline integration
- ❌ Automatic diff application in render workflow
- ❌ Seed locking mechanism enforcement
- ❌ Compression slot selection heuristics based on passing/failing status

---

## Next Steps (Loop 3)

1. **Database Schema**: Add tables for `adherence_scores` and `corrective_diffs`
2. **Frame Extraction**: Integrate FFmpeg-based 10%/50%/90% frame extraction
3. **Retry Loop**: Connect scoring → diff generation → prompt update → re-render
4. **Route Integration**: Add adherence endpoints to studio API
5. **Seed Locking**: Ensure subsequent attempts use same seed
6. **Compression Strategy**: Refine `apply_diff()` to avoid compressing failed slots

---

## Files Changed

| File | Status | Description |
|------|--------|-------------|
| `studio-backend/app/services/adherence_service.py` | ✅ Modified | Replaced mock `_call_groq_corrector()` with real implementation |
| `studio-backend/manual_adherence_check.py` | ✅ Modified | Added auto-diff generation + formatting function |
| `studio-backend/test_corrector_direct.py` | ✅ Created | Isolated corrector test with severe failures (desert vs coastal) |
| `studio-backend/test_corrector_variations.py` | ✅ Created | Tests minor/moderate failures to observe operation selection |

---

## Additional Test Results

### Test 2: Minor Failure (Lighting Blue Tint)
```
Expected: soft natural window light
Observed: soft natural window light with slight blue tint
Score: 55.0

Operation: replace
Old: soft natural window light
New: soft warm natural window light
Delta: +7 chars
```

### Test 3: Moderate Failures (Blue Dress, Walking vs Dancing)
```
CHARACTER_STATE (Score 35.0):
  Expected: young woman, red dress, long dark hair
  Observed: young woman, blue dress, long dark hair
  Operation: replace
  New: young woman, red dress, long dark hair, no blue clothing
  Delta: +24 chars

ACTION (Score 40.0):
  Expected: dancing gracefully in center of room
  Observed: walking slowly across the room
  Operation: replace
  New: dancing gracefully, not walking, in the center of the room
  Delta: +23 chars
```

**Pattern Observed:** Corrector uses `replace` consistently but varies modification strategy:
- **Minor failures (55+):** Add positive qualifiers ("warm")
- **Moderate/Severe failures (<50):** Add negative constraints ("not X", "no Y")

---

## Log Evidence

```
2026-07-04 06:58:43 | INFO | adherence_service | GROQ_CORRECTOR_CALL | failed_dims=4 | chars_remaining=200 | max_output_tokens=2048
2026-07-04 06:58:43 | INFO | httpx | HTTP Request: POST https://api.groq.com/openai/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-04 06:58:43 | INFO | adherence_service | GROQ_CORRECTOR_FINISH_REASON | reason=stop
2026-07-04 06:58:43 | INFO | adherence_service | GROQ_CORRECTOR_SUCCESS | ops=4 | chars_remaining=96 | finish_reason=stop
2026-07-04 06:58:43 | INFO | adherence_service | CORRECTIVE_DIFF_GENERATED | shot=test_corrector | attempt=1 | ops=4
```

---

**Status:** Ready for Loop 3 (database persistence + retry loop integration)
