# Loop 2: Corrective Diff Generator - COMPLETE ✅

**Date:** 2026-07-04  
**Task:** Replace mock `_call_groq_corrector()` with real Groq API implementation  
**Status:** ✅ COMPLETE AND TESTED

---

## What Was Delivered

### 1. Real Groq Corrector Implementation
**File:** `studio-backend/app/services/adherence_service.py`

- ✅ Replaced mock with real Groq API call to Llama 3.3 70B Versatile
- ✅ Text-only reasoning over expected/observed gaps (no vision analysis)
- ✅ Forced JSON mode with exact CorrectiveDiff schema enforcement
- ✅ Truncation detection with automatic retry (2048 → 4096 tokens)
- ✅ Comprehensive validation of output schema
- ✅ Only generates ops for failed slots (passing slots ignored)
- ✅ Character budget tracking and enforcement

### 2. Manual Test Script Enhancement
**File:** `studio-backend/manual_adherence_check.py`

- ✅ Auto-generates corrective diff when verdict is "correctable"
- ✅ Checks for GROQ_API_KEY availability
- ✅ New `format_corrective_diff()` function for human-readable output
- ✅ Shows before/after comparison for modified slots
- ✅ Includes diff in JSON output mode

### 3. Test Scripts Created
**Files:**
- `studio-backend/test_corrector_direct.py` - Severe failure test (desert vs coastal)
- `studio-backend/test_corrector_variations.py` - Minor/moderate failure tests

---

## Test Results Summary

### Test 1: Severe Failures (Red Jacket in Desert vs Coastal Village)
**Scenario:** Completely wrong prompt tested against real footage expectations

| Dimension | Score | Strategy | Example Correction |
|-----------|-------|----------|-------------------|
| character_state | 15.0 | Negative constraint | "...blonde hair, not dark blue coat or dark hair" (+36) |
| action | 30.0 | Negative constraint | "...desert dunes, not along coastal path" (+24) |
| environment_persistence | 5.0 | Negative constraint | "...no vegetation, no buildings or ocean" (+24) |
| lighting | 40.0 | Negative constraint | "...deep shadows, not soft overcast" (+20) |

**Budget:** Started with 200 chars, used 104, remaining 96 chars

### Test 2: Minor Failure (Lighting Tint)
**Scenario:** Lighting present but slightly wrong tone (blue vs warm)

| Dimension | Score | Strategy | Correction |
|-----------|-------|----------|------------|
| lighting | 55.0 | Positive qualifier | "soft **warm** natural window light" (+7) |

### Test 3: Moderate Failures (Costume/Action Wrong)
**Scenario:** Character exists but details wrong

| Dimension | Score | Strategy | Correction |
|-----------|-------|----------|------------|
| character_state | 35.0 | Negative constraint | "red dress, long dark hair, no blue clothing" (+24) |
| action | 40.0 | Negative constraint | "dancing gracefully, not walking, in center..." (+23) |

---

## Key Findings

### Correction Strategy Pattern
The corrector adapts its approach based on failure severity:

1. **Minor failures (55+):** Adds positive qualifiers
   - "soft **warm** natural window light"
   - Small character delta (+7)
   - Reinforces intended quality without rejecting observed

2. **Moderate/Severe failures (<50):** Uses negative constraints
   - "not X", "no Y" clauses
   - Explicitly rejects what was observed
   - Larger character deltas (+20-36)

3. **Operation type selection:**
   - Model primarily uses `replace` operation
   - Varies the replacement text based on severity
   - `strengthen` and `prepend_emphasis` appear unused in these tests
   - May use different ops in other scenarios

### Reasoning Quality
- ✅ Each correction tied to specific evidence
- ✅ References expected vs observed gap
- ✅ Explains corrective intent clearly
- ✅ Appropriate to failure severity

---

## What Was NOT Done (As Specified)

Per requirements, these are explicitly deferred to Loop 3:

- ❌ Database persistence for scores/diffs
- ❌ Retry loop integration
- ❌ Frame extraction pipeline
- ❌ Automatic application in render workflow
- ❌ API route endpoints
- ❌ Seed locking enforcement

---

## Code Quality

### Error Handling
- ✅ JSON parse errors caught and logged
- ✅ Schema validation with clear error messages
- ✅ Truncation detection and retry
- ✅ Missing fields handled gracefully
- ✅ Invalid operation types rejected

### Logging
All key events logged with structured data:
```
GROQ_CORRECTOR_CALL | failed_dims=4 | chars_remaining=200 | max_output_tokens=2048
GROQ_CORRECTOR_FINISH_REASON | reason=stop
GROQ_CORRECTOR_SUCCESS | ops=4 | chars_remaining=96 | finish_reason=stop
CORRECTIVE_DIFF_GENERATED | shot=test_corrector | attempt=1 | ops=4
```

### Pattern Consistency
Matches existing codebase patterns:
- ✅ Same Groq client setup as other LLM calls
- ✅ Async/await with `asyncio.to_thread()` for sync SDK
- ✅ Token budget + retry logic mirrors vision scorer fix
- ✅ Structured logging with pipe-separated keys
- ✅ Service layer owns business logic (no route logic)

---

## Integration Readiness

The corrector is now ready for Loop 3 integration:

1. ✅ **Scoring works:** Vision model scores frames → identifies failed slots
2. ✅ **Correction works:** Groq generates ops based on failed slots
3. ✅ **Application works:** `apply_diff()` already implemented and tested
4. ⏳ **Database:** Need schema for persistence
5. ⏳ **Retry loop:** Need workflow orchestration
6. ⏳ **Frame extraction:** Need FFmpeg integration

---

## Example Output

**Input Failed Slots:**
```json
{
  "character_state": {
    "expected": "woman wearing bright red jacket, blonde hair",
    "observed": "woman in dark blue coat, dark hair",
    "score": 15.0
  },
  "environment_persistence": {
    "expected": "vast empty desert, no vegetation",
    "observed": "coastal fishing village, stone buildings, ocean visible",
    "score": 5.0
  }
}
```

**Generated Corrective Diff:**
```json
{
  "base_attempt": 1,
  "seed_locked": true,
  "ops": [
    {
      "slot": "character_state",
      "op": "replace",
      "old_text": "woman wearing bright red jacket, blonde hair",
      "new_text": "woman wearing bright red jacket, blonde hair, not dark blue coat or dark hair",
      "reason": "Character wearing dark blue not red, hair is dark not blonde",
      "char_delta": 36
    },
    {
      "slot": "environment_persistence",
      "op": "replace",
      "old_text": "vast empty desert, no vegetation",
      "new_text": "vast empty desert, no vegetation, no buildings or ocean",
      "reason": "Environment is coastal village not desert, completely different",
      "char_delta": 24
    }
  ],
  "chars_remaining": 140
}
```

---

## Next: Loop 3 (Database + Retry Loop)

Ready to proceed with:
1. Database schema for `adherence_scores` and `corrective_diffs` tables
2. Frame extraction service (FFmpeg 10%/50%/90%)
3. Retry loop orchestration (attempt 1 → score → diff → attempt 2)
4. API endpoints for adherence workflow
5. Seed locking mechanism
6. Compression strategy refinement

---

**Status:** ✅ Loop 2 complete. Corrector is production-ready for Loop 3 integration.
