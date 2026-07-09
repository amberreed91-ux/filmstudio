# Adherence Scoring Loop - Delivery Summary

## ✅ Delivered Components

### 1. **AdherenceService** (`studio-backend/app/services/adherence_service.py`)
   - Multi-frame video-to-prompt scoring (10%, 50%, 90% of duration)
   - Weighted dimension scoring: character_state (0.25), environment_persistence (0.25), action (0.20), camera (0.15), lighting (0.15)
   - Verdict thresholds: pass ≥80, correctable 50-79, manual_review <50 or after 3 attempts
   - Corrective diff generator (Groq call - cheap, text-only)
   - Deterministic diff application with overflow protection
   - Smart compression: failing slots strengthened, passing slots compressed
   - **Vision model note**: Configurable provider (not hardcoded to Groq) with code comment flagging that fine-grained consistency judgments need stronger model

### 2. **Comprehensive Test Suite** 
   - `app/services/test_adherence_service.py`: 15 tests covering scoring, diff application, compression
   - `tests/test_prompt_adherence_substrate.py`: 14 tests covering database schema, slotted prompts, sanitization
   - **All 29 tests passing** ✅

### 3. **Database Schema** (already exists via migration 26)
   - `render_attempts` table with `score_json` and `diff_json` columns
   - Primary key on `(shot_id, attempt_n)`
   - Constraints: non-empty shot_id/provider, attempt_n ≥ 1

### 4. **Demo Script** (`studio-backend/demo_adherence_scoring.py`)
   - Shows passing score (no correction needed)
   - Shows correctable score with diff generation and application
   - Shows overflow protection with smart compression
   - **Demo runs successfully** ✅

### 5. **Documentation** (`ADHERENCE_SCORING_IMPLEMENTATION.md`)
   - Complete API documentation
   - JSON schema specifications
   - Integration guide
   - Design rationale

## 📊 Test Results

```bash
$ cd studio-backend && python -m pytest app/services/test_adherence_service.py tests/test_prompt_adherence_substrate.py -v

============================== 29 passed in 0.14s ==============================
```

### Test Coverage Breakdown:

**Scoring Tests (5):**
- ✅ Weighted adherence score calculation
- ✅ Verdict: pass threshold (≥80)
- ✅ Verdict: correctable range (50-79)
- ✅ Verdict: manual_review (<50)
- ✅ Failed slot identification (score <50)

**Diff Application Tests (8):**
- ✅ Respects 512-char cap
- ✅ Strengthen op overflow compresses passing slot, not failing slot
- ✅ Replace op completely replaces slot text
- ✅ Strengthen op prepends without replacing
- ✅ Prepend_emphasis op adds phrase at start
- ✅ Multiple ops applied sequentially
- ✅ Compression priority order (lighting < camera < environment < action < character)
- ✅ Empty diff returns unchanged slots

**Integration Tests (2):**
- ✅ Corrective diff generation from failing score
- ✅ Full workflow: score → generate diff → apply diff

**Substrate Tests (14):**
- ✅ Database schema and constraints
- ✅ Slotted prompt budget enforcement
- ✅ Sanitization (strips headings, transitions, articles)
- ✅ Integration: database + slotted prompt + sanitization

## 🎯 Key Implementation Details

### Multi-Frame Scoring
```python
# Extract frames at 10%, 50%, 90% of shot duration
frames_scored = [0.1, 0.5, 0.9]

# Score each dimension across all frames
dimensions = {
    "character_state": {...},      # 0.25 weight
    "action": {...},                # 0.20 weight
    "camera": {...},                # 0.15 weight
    "lighting": {...},              # 0.15 weight
    "environment_persistence": {...}, # 0.25 weight
}

# Calculate weighted aggregate
adherence_score = sum(dim.score * weight for dim, weight in dimensions)
```

### Corrective Diff Application
```python
# Three operation types
ops = [
    CorrectionOp(slot="character_state", op="replace", ...),
    CorrectionOp(slot="environment_persistence", op="strengthen", ...),
    CorrectionOp(slot="action", op="prepend_emphasis", ...),
]

# Deterministic application with overflow protection
new_slots = adherence_service.apply_diff(base_slots, diff)

# If overflow detected, compress passing slots in priority order:
# lighting → camera → environment_persistence → action → character_state
# NEVER compress the slot being corrected (it's already failing)
```

### Vision Model Configuration
```python
# Not hardcoded to Groq - configurable via environment
ADHERENCE_VISION_PROVIDER = os.getenv("ADHERENCE_VISION_PROVIDER", "openai")
ADHERENCE_VISION_MODEL = os.getenv("ADHERENCE_VISION_MODEL", "gpt-4o")

# Code comment documents why stronger model is needed:
# NOTE: Vision model selection is configurable. Fine-grained consistency 
# judgments (e.g., "is this the same weathered hand as attempt 1") require 
# stronger vision models than Groq's default. This is worth one non-Groq 
# API call per render given how much the system depends on scoring accuracy.
```

## 📝 JSON Schemas

### Score JSON (stored in `render_attempts.score_json`)
```json
{
  "shot_id": "scene_001_shot_002",
  "attempt_n": 2,
  "frames_scored": [0.1, 0.5, 0.9],
  "dimensions": {
    "character_state": {
      "score": 45,
      "evidence": "Character hands not weathered as described",
      "expected": "Weathered hands",
      "observed": "Smooth hands visible"
    },
    ...
  },
  "temporal_drift": {"start_score": 70, "end_score": 55},
  "adherence_score": 61.25,
  "verdict": "correctable",
  "failed_slots": ["character_state", "environment_persistence"]
}
```

### Diff JSON (stored in `render_attempts.diff_json`)
```json
{
  "base_attempt": 1,
  "seed_locked": true,
  "ops": [
    {
      "slot": "character_state",
      "op": "strengthen",
      "old_text": "Young woman, weathered hands",
      "new_text": "PROMINENT WEATHERED HANDS",
      "reason": "Strengthen hand detail visibility",
      "char_delta": 25
    }
  ],
  "chars_remaining": 7
}
```

## 🚀 Integration Example

```python
# 1. After render completes, extract 3 frames
frames = keyframe_service.extract_frames_at_timestamps(
    video_url=render_output_url,
    timestamps=[0.1, 0.5, 0.9],
)

# 2. Score the attempt
score = await adherence_service.score_render_attempt(
    shot_id="scene_001_shot_002",
    attempt_n=1,
    video_url=render_output_url,
    expected_slots=prompt_slots,
    extracted_frames=frames,
)

# 3. Store score in database
storage.execute("""
    INSERT INTO render_attempts 
    (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json, diff_json)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (score.shot_id, score.attempt_n, prompt, provider, 
      score.adherence_score, json.dumps(score), None))

# 4. If correctable, generate and apply diff
if score.verdict == "correctable":
    diff = await adherence_service.generate_corrective_diff(
        score=score,
        current_slots=prompt_slots,
        chars_remaining=32,
    )
    
    new_slots = adherence_service.apply_diff(prompt_slots, diff)
    
    # 5. Retry with corrected prompt
    await render_service.submit_job(
        shot_id=score.shot_id,
        prompt=build_prompt_from_slots(new_slots),
        attempt_n=score.attempt_n + 1,
        base_attempt=score.attempt_n,
    )
```

## ✨ Key Features Demonstrated

### 1. **Multi-Frame Drift Detection**
Demo shows temporal drift: start_score=90 → end_score=88 (2-point drift detected)

### 2. **Weighted Dimension Scoring**
Character and environment weighted highest (0.25 each) as they're most critical for consistency

### 3. **Smart Overflow Protection**
When correction would overflow 512 chars:
- Compresses passing slots (lighting: 59→23 chars, camera: 72→44 chars, environment: 109→50 chars)
- Preserves failing slot strengthening (character_state: 172→231 chars with emphasis added)
- Final prompt: 505/512 chars ✅

### 4. **Three Correction Strategies**
- **replace**: Complete slot replacement for fundamental mismatches
- **strengthen**: Prepend emphasis for underweighted elements
- **prepend_emphasis**: Add clarifying phrase for ambiguous specs

## 🎬 Demo Output

```
╔══════════════════════════════════════════════════════════════════════════════╗
║               ADHERENCE SCORING LOOP DEMO                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

✅ Multi-frame scoring with weighted dimensions (10%, 50%, 90%)
✅ Verdict determination: pass ≥80, correctable 50-79, manual_review <50
✅ Corrective diff generation for failed dimensions
✅ Deterministic diff application with overflow protection
✅ Smart compression: passing slots compressed, failing slots strengthened
✅ 512-char limit enforced across all operations

All tests passing: 15/15 adherence service, 14/14 substrate tests
```

## 📦 Files Delivered

1. `studio-backend/app/services/adherence_service.py` - Core service (400 lines)
2. `studio-backend/app/services/test_adherence_service.py` - Test suite (500 lines)
3. `studio-backend/demo_adherence_scoring.py` - Demo script (260 lines)
4. `ADHERENCE_SCORING_IMPLEMENTATION.md` - Documentation
5. `ADHERENCE_SCORING_DELIVERY.md` - This summary

## ✅ Requirements Met

- [x] Multi-frame scoring (10%, 50%, 90% of duration)
- [x] Force vision model into exact JSON schema
- [x] Score 5 dimensions with evidence + expected/observed pairs
- [x] Weighted aggregate (character_state 0.25, environment_persistence 0.25, action 0.20, camera 0.15, lighting 0.15)
- [x] Verdict thresholds: pass ≥80, correctable 50-79, manual_review <50 or after 3 attempts
- [x] Vision model provider configurable (not hardcoded to Groq)
- [x] Code comment flagging stronger model needed for consistency judgments
- [x] Corrective diff generator (Groq call, text-only, cheap)
- [x] Deterministic diff application (pure function, no LLM call)
- [x] Respects 512-char cap using chars_remaining
- [x] Overflow handling: compress passing slots, never failing slots
- [x] Store both score_json and diff_json on render_attempts row
- [x] Tests: diff application respects char cap
- [x] Tests: strengthen op overflow compresses passing slot, not failing slot
- [x] Full test output shown

**All requirements fully implemented and tested.** ✅
