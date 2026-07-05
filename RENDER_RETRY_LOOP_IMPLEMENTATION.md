# Render Retry Loop Implementation

## Summary

Implemented the automated render retry loop for the Previs Bay pipeline with database persistence, adherence scoring, prompt correction, and "stuck shot" detection.

## Implementation Details

### 1. Core Service: `render_retry_service.py`

Created `/app/services/render_retry_service.py` with the following capabilities:

#### Key Functions

**`evaluate_and_retry()`** - Main retry loop controller
- Extracts keyframes at 10%, 50%, 90% using keyframe_extraction_service
- Calls vision scorer (adherence_service) to get AdherenceScore
- Persists attempt to `render_attempts` table with full score_json
- Implements verdict-based logic:
  - **`pass`** (score >= 80): Stop, mark final
  - **`correctable`** (50 <= score < 80) AND attempt_n < 3:
    - Generate CorrectiveDiff via adherence_service
    - Persist diff_json to same row
    - Apply diff to prompt slots
    - Keep locked seed unchanged
    - Return corrected_slots for next attempt
  - **`manual_review`** (score < 50) OR attempt_n == 3: Stop, flag for manual review
  - **`stuck`**: Detected when score improves by < 5 points between attempts

**`download_runway_video()`** - Video download integration
- Downloads Runway video to local storage (`/outputs/renders/{project_id}/`)
- Required before frame extraction (addresses the "Runway outputs never downloaded" bug)
- Returns local file path

**`extract_representative_frames()`** - Frame extraction wrapper
- Calls keyframe_extraction_service in thread pool
- Returns 3 frame paths for adherence scoring

**`_persist_attempt()`** - Database persistence
- Inserts into `render_attempts` table
- Stores: shot_id, attempt_n, prompt_text, provider, adherence_score, score_json, diff_json (if applicable)

**`_is_stuck_shot()`** - Stuck shot detection
- Compares current score to previous attempt
- If improvement < 5 points: mark as "stuck", stop retry loop
- Avoids burning final attempt on unresponsive seeds

### 2. Database Schema

The `render_attempts` table (already exists via migration 26):

```sql
CREATE TABLE render_attempts (
    shot_id TEXT NOT NULL,
    attempt_n INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    adherence_score REAL,
    score_json TEXT,         -- Full AdherenceScore as JSON
    diff_json TEXT,          -- CorrectiveDiff as JSON (if correctable)
    created_at TEXT NOT NULL,
    PRIMARY KEY (shot_id, attempt_n)
);
```

### 3. Test Coverage

Created `test_render_retry_service.py` with 6 comprehensive tests:

1. **`test_evaluate_and_retry_passing_score`**: Passing score (84.0) stops retry loop
2. **`test_evaluate_and_retry_correctable_with_diff`**: Correctable score (62.5) generates diff and requests retry
3. **`test_evaluate_and_retry_manual_review`**: Manual review score (43.75) stops retry loop
4. **`test_stuck_shot_detection`**: Score improving from 60.0 to 63.0 (< 5 points) triggers stuck detection
5. **`test_max_attempts_reached`**: Attempt 3 stops retry even if correctable
6. **`test_persist_attempt`**: Verifies database persistence with score_json and diff_json

**All tests pass** ✅

### 4. Integration Points

The retry service is now ready to integrate into the render pipeline:

```python
from app.services.render_retry_service import render_retry_service

# After a render completes (status == "complete"):
# 1. Download video locally
video_path = await render_retry_service.download_runway_video(
    video_url=job.output_payload.asset_url,
    project_id=job.project_id,
    shot_id=job.shot_id,
)

# 2. Evaluate and determine if retry needed
result = await render_retry_service.evaluate_and_retry(
    shot_id=job.shot_id,
    attempt_n=current_attempt,
    video_url=job.output_payload.asset_url,
    video_path=video_path,
    asset_id=asset_id,
    project_id=job.project_id,
    provider=job.provider,
    current_prompt=assembled_prompt,
    prompt_slots=slot_dict,
    locked_seed=job.input_payload.parameters.get("seed"),
)

# 3. Handle verdict
if result["should_retry"]:
    # Submit new render with result["corrected_slots"]
    # Increment attempt_n
    # Keep locked_seed unchanged
    pass
else:
    # verdict is "pass", "manual_review", or "stuck"
    # Stop retry loop
    pass
```

### 5. Key Design Decisions

#### Stuck Shot Detection
- **Threshold**: 5 points improvement required between consecutive attempts
- **Rationale**: Avoids burning the final attempt on seeds that aren't responding to prompt corrections
- **Example**: 60.0 → 63.0 = only 3 points = stuck

#### Seed Locking
- **Rule**: Seed MUST stay unchanged across all retry attempts
- **Enforcement**: `locked_seed` parameter passed through entire pipeline
- **Rationale**: Allows fair comparison of prompt corrections on same visual foundation

#### Persistence Strategy
- **Full score_json**: Captures all dimension scores, evidence, temporal_drift for post-mortem analysis
- **Optional diff_json**: Only stored for correctable attempts, enables audit trail of what corrections were attempted

#### Max Attempts
- **Limit**: 3 attempts per shot
- **Enforcement**: Even if attempt 3 scores "correctable", verdict becomes "manual_review" to stop loop

## Architecture Compliance

✅ **No business logic in routes** - All retry logic in service layer  
✅ **Service boundaries respected** - render_retry_service orchestrates adherence_service and keyframe_service  
✅ **Database persistence** - All attempts recorded in render_attempts table  
✅ **Error handling** - Frame extraction failures and scoring errors handled gracefully  
✅ **Stage logging** - All key events logged with shot_id, attempt_n, score, verdict

## Next Steps (NOT Implemented Yet)

The following features were explicitly deferred per requirements:

1. **UI surfacing for stuck shots** - Show "stuck" status in Previs Bay UI
2. **Shots-to-adherence metrics endpoint** - GET /api/shots/{shot_id}/adherence_history
3. **Worst-slot leaderboard** - Dashboard showing which slots fail most often across all shots
4. **Actual render pipeline integration** - Wire retry loop into render.py / projects.py submission flow

These will be implemented after the core retry mechanics are validated in production.

## Test Results

```bash
$ pytest app/services/test_render_retry_service.py -v

test_evaluate_and_retry_passing_score PASSED
test_evaluate_and_retry_correctable_with_diff PASSED
test_evaluate_and_retry_manual_review PASSED
test_stuck_shot_detection PASSED
test_max_attempts_reached PASSED
test_persist_attempt PASSED

6 passed, 1 warning in 0.69s
```

## Files Created/Modified

### Created
- `app/services/render_retry_service.py` (442 lines)
- `app/services/test_render_retry_service.py` (689 lines)
- `RENDER_RETRY_LOOP_IMPLEMENTATION.md` (this file)

### Modified
- None (service is self-contained and ready for integration)

### Existing Dependencies
- `app/services/adherence_service.py` (scorer + corrector, Loop 1 complete)
- `app/services/keyframe_extraction_service.py` (frame extraction at 10%, 50%, 90%)
- `app/data/storage.py` (render_attempts table, migration 26)

## Credits

- **Loop 1**: Vision scorer and corrector validated
- **Loop 2**: Retry orchestration and persistence (this implementation)
- **Loop 3**: Pipeline integration (future work)
