# Adherence Scoring Loop Implementation

## Overview

Built the adherence scoring loop for multi-frame video-to-prompt consistency evaluation with corrective diff generation.

## Components

### 1. AdherenceService (`studio-backend/app/services/adherence_service.py`)

**Core functionality:**
- Multi-frame scoring (10%, 50%, 90% of shot duration) to detect temporal drift
- Vision model scoring across 5 dimensions with weighted aggregation
- Corrective diff generation for failed dimensions
- Deterministic diff application with overflow protection

**Key features:**
- **Dimension scoring**: character_state (0.25), environment_persistence (0.25), action (0.20), camera (0.15), lighting (0.15)
- **Verdict thresholds**: pass ≥80, correctable 50-79, manual_review <50 or after 3 attempts
- **Vision model note**: Configurable via `ADHERENCE_VISION_PROVIDER` - defaults to stronger model than Groq for fine-grained consistency judgments (e.g., "is this the same weathered hand as attempt 1")
- **Smart compression**: If a correction would overflow 512 chars, compresses passing slots (priority: lighting < camera < environment < action < character), never failing slots

### 2. Data Schema

**Database table** (already exists from migration 26):
```sql
CREATE TABLE render_attempts (
    shot_id TEXT NOT NULL,
    attempt_n INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    adherence_score REAL,
    score_json TEXT,        -- Full dimension scores + evidence
    diff_json TEXT,         -- Corrective operations for next attempt
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (shot_id, attempt_n)
);
```

### 3. Corrective Diff Operations

Three operation types:
- **replace**: Completely replace slot text
- **strengthen**: Prepend emphasis without replacing (e.g., "WEATHERED HANDS. {original}")
- **prepend_emphasis**: Add clarifying phrase at start (e.g., "Bright neon signs, {original}")

Diff format:
```json
{
  "base_attempt": 1,
  "seed_locked": true,
  "ops": [
    {
      "slot": "environment_persistence",
      "op": "strengthen",
      "old_text": "Urban market with neon signs",
      "new_text": "PROMINENT NEON SIGNS THROUGHOUT",
      "reason": "Neon signs dropped out in frames 2-3",
      "char_delta": 35
    }
  ],
  "chars_remaining": 12
}
```

### 4. Score JSON Schema

```json
{
  "shot_id": "scene_001_shot_002",
  "attempt_n": 2,
  "frames_scored": [0.1, 0.5, 0.9],
  "dimensions": {
    "character_state": {
      "score": 45,
      "evidence": "Character hands not weathered as described",
      "expected": "Weathered hands with visible scars",
      "observed": "Smooth hands visible in all frames"
    },
    "action": {
      "score": 85,
      "evidence": "Action clearly executed",
      "expected": "Walking through market",
      "observed": "Walking motion consistent"
    },
    "camera": {
      "score": 80,
      "evidence": "Camera framing adequate",
      "expected": "Medium shot",
      "observed": "Medium shot maintained"
    },
    "lighting": {
      "score": 75,
      "evidence": "Lighting acceptable",
      "expected": "Natural daylight",
      "observed": "Daylight lighting present"
    },
    "environment_persistence": {
      "score": 40,
      "evidence": "Neon signs missing in frames 2-3",
      "expected": "Neon signs visible throughout",
      "observed": "Neon signs only in frame 1"
    }
  },
  "temporal_drift": {
    "start_score": 70,
    "end_score": 55
  },
  "adherence_score": 61.25,
  "verdict": "correctable",
  "failed_slots": ["character_state", "environment_persistence"]
}
```

## Implementation Details

### Weighted Adherence Score Calculation

```python
adherence_score = (
    character_state_score * 0.25 +
    environment_persistence_score * 0.25 +
    action_score * 0.20 +
    camera_score * 0.15 +
    lighting_score * 0.15
)
```

### Overflow Protection Algorithm

When applying a diff operation would exceed 512 chars:
1. Calculate current assembled prompt length
2. If over budget, compress passing slots in priority order:
   - lighting (lowest priority)
   - camera
   - environment_persistence
   - action
   - character_state (highest priority)
3. **Never compress the slot being corrected** (it's already failing)
4. Truncate with "..." to maintain readable text
5. If no passing slots available, truncate the current operation

### Vision Model Provider Selection

```python
# Configuration
ADHERENCE_VISION_PROVIDER = os.getenv("ADHERENCE_VISION_PROVIDER", "openai")
ADHERENCE_VISION_MODEL = os.getenv("ADHERENCE_VISION_MODEL", "gpt-4o")

# NOTE: Fine-grained consistency judgments (e.g., "is this the same weathered 
# hand as attempt 1") require stronger vision models than Groq's default. This
# is worth one non-Groq API call per render given how much the system depends
# on scoring accuracy.
```

### Corrective Diff Generator (Groq)

Small, cheap Groq call to generate patch - only sees expected/observed text, not video:

```python
prompt = f"""You are a prompt engineer fixing video generation prompts.

These dimensions failed in the render:
- character_state: Expected 'Weathered hands', Observed 'Smooth hands' (Character hands not weathered)
- environment_persistence: Expected 'Neon signs', Observed 'No neon visible' (Neon signs missing in frames 2-3)

Current slots:
{json.dumps(current_slots, indent=2)}

Available character budget: 32

Generate correction operations. For each failed dimension, choose:
- "replace": completely replace the slot text
- "strengthen": prepend emphasis phrase without replacing
- "prepend_emphasis": add clarifying phrase at start

Respond ONLY with valid JSON: {...}
"""
```

## Test Coverage

### Unit Tests (`app/services/test_adherence_service.py`)

**Scoring tests:**
- ✅ Weighted adherence score calculation
- ✅ Verdict thresholds (pass ≥80, correctable 50-79, manual_review <50)
- ✅ Failed slot identification (score <50)

**Diff application tests:**
- ✅ Respects 512-char cap
- ✅ Strengthen op overflow compresses passing slot, not failing slot
- ✅ Replace op completely replaces slot text
- ✅ Strengthen op prepends without replacing
- ✅ Prepend_emphasis op adds phrase at start
- ✅ Multiple ops applied sequentially
- ✅ Compression priority order
- ✅ Empty diff returns unchanged slots

**Integration tests:**
- ✅ Corrective diff generation from failing score
- ✅ Full workflow: score → generate diff → apply diff

### Substrate Tests (`tests/test_prompt_adherence_substrate.py`)

- ✅ render_attempts table schema and constraints
- ✅ Slotted prompt budget enforcement (≤512 chars)
- ✅ Slot structure and reserve headroom
- ✅ Sanitization (strips scene headings, transitions, articles)
- ✅ Integration: database + slotted prompt + sanitization

## Test Results

```bash
# New adherence service tests
app/services/test_adherence_service.py ............... 15 passed in 0.08s

# Existing substrate tests
tests/test_prompt_adherence_substrate.py ............. 14 passed in 0.26s
```

## Usage Example

```python
from app.services.adherence_service import adherence_service

# 1. Score a render attempt
score = await adherence_service.score_render_attempt(
    shot_id="scene_001_shot_002",
    attempt_n=1,
    video_url="https://...",
    expected_slots={
        "character_state": "Young woman, weathered hands",
        "action": "Walking through market",
        "environment_persistence": "Neon signs visible",
        "camera": "Medium shot",
        "lighting": "Natural daylight",
    },
    extracted_frames=[
        "/path/to/frame_10.jpg",
        "/path/to/frame_50.jpg",
        "/path/to/frame_90.jpg",
    ],
)

# 2. If correctable, generate diff
if score.verdict == "correctable":
    diff = await adherence_service.generate_corrective_diff(
        score=score,
        current_slots=expected_slots,
        chars_remaining=32,
    )
    
    # 3. Apply diff to get corrected slots
    new_slots = adherence_service.apply_diff(
        base_slots=expected_slots,
        diff=diff,
    )
    
    # 4. Store both score and diff in database
    storage.execute("""
        INSERT INTO render_attempts 
        (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json, diff_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        score.shot_id,
        score.attempt_n,
        prompt_text,
        provider,
        score.adherence_score,
        json.dumps(score.__dict__),
        json.dumps(diff.__dict__),
    ))
```

## Next Steps

### To integrate with render pipeline:

1. **Frame extraction**: Add `KeyframeExtractionService` call after render completes to extract 3 frames at 10%, 50%, 90% timestamps
2. **Vision model integration**: Replace mock `_call_vision_model()` with actual API call (OpenAI GPT-4o recommended for consistency judgments)
3. **Groq corrector integration**: Replace mock `_call_groq_corrector()` with actual Groq API call
4. **Retry loop**: Integrate with render service to automatically retry with corrected prompts when verdict is "correctable"
5. **Manual review UI**: Add frontend surface for "manual_review" verdict cases (score <50 or 3 failed attempts)

### Configuration:

```bash
# Environment variables
ADHERENCE_VISION_PROVIDER=openai  # or anthropic, google
ADHERENCE_VISION_MODEL=gpt-4o     # Stronger model for consistency
GROQ_API_KEY=sk-...               # For corrective diff generation
```

## Design Notes

### Why 3 frames (10%, 50%, 90%)?

Temporal drift compounds over shot duration. Single-frame scoring misses:
- Character appearance changes (e.g., weathered hands become smooth)
- Environment elements dropping out (e.g., neon signs disappear mid-shot)
- Lighting shifts across the shot

### Why not Groq for vision scoring?

Fine-grained visual consistency judgments ("is this the same weathered hand as attempt 1?") require stronger vision models. Groq's vision model is optimized for speed but may miss subtle continuity issues. This is worth one non-Groq API call per render given how critical scoring accuracy is to the system.

### Why compress passing slots instead of failing slots?

The failing slot is being corrected for a reason - it's already below threshold. Compressing it further would make the issue worse. Instead, we borrow space from dimensions that are already passing (score ≥50) in priority order, preserving the highest-priority dimensions (character, action) and compressing lower-priority ones (lighting, camera) first.

### Why lock seed across retries?

Temporal consistency across attempts. If we change the seed, we get a completely different render that can't be compared to the original. Locking the seed ensures corrections are applied to the same underlying generation, making it easier to isolate what changed.
