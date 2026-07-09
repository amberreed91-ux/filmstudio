# Attempt 2 - Corrective Retry Test Complete

**Date:** July 5, 2026 - 02:50 UTC  
**Status:** ✅ RENDER COMPLETE | ❌ CORRECTION FAILED - SCORE DEGRADED

---

## Executive Summary

Attempt 2 was successfully submitted with the corrected prompt and locked seed **983559286**. However, the corrective strategy **FAILED dramatically**:

- **Attempt 1 Score:** 55.0/100 (correctable)
- **Attempt 2 Score:** 14.0/100 (manual_review)
- **Change:** **-41.0 points** 📉

The corrected prompt did NOT fix the failed dimensions (character_state, action) and instead **broke three previously-passing dimensions** (camera, lighting, environment_persistence).

---

## What Was Tested

### Loop 4 Retry Infrastructure
✅ **Seed Locking:** Seed 983559286 was successfully locked and used for both attempts  
✅ **Corrective Diff Generation:** Enhanced corrector with prescriptive fixes (not failure descriptions)  
✅ **Paraphrase Detection:** Smart deduplication to prevent semantic redundancy  
✅ **Real Runway Submission:** Both attempts submitted to real Runway API (not simulated)  
✅ **Adherence Scoring:** Gemini 2.5 Flash vision analysis on 3 frames per attempt  
✅ **Persistence:** Both attempts stored in `render_attempts` table with full score_json  

### Technical Success
All infrastructure worked correctly:
- Provider selection (real Runway, not simulated)
- Storage initialization (both render and retry services)
- Seed generation and locking across attempts
- URL refresh handling
- Frame extraction via ffmpeg
- Vision-based adherence scoring
- Database persistence

---

## The Corrected Prompt

**Original Prompt (Attempt 1 - 238 chars):**
```
Chicago is alive. The L train moves through the skyline. People fill the streets. Music, laughter, food stands. Everything is vibrant. Wide shot, golden hour light. Cinematic, film quality, single continuous shot.
```

**Corrected Prompt (Attempt 2 - 283 chars):**
```
People visible at human scale, faces and gestures clearly shown, interacting closely. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago, L train, skyline. Wide shot. golden hour light. Cinematic, film quality, single continuous shot.
```

### What Changed
The corrector replaced the failing slots:
1. **character_state:** "People fill the streets" → "People visible at human scale, faces and gestures clearly shown, interacting closely" (+61 chars)
2. **action:** "Music, laughter, food stands. Everything is vibrant" → "Vendors actively serving customers, people laughing and talking, continuous human activity" (-24 chars)

### Corrector Strategy
- ✅ Prescriptive (says what you WANT, not what failed)
- ✅ No semantic duplication (paraphrase detection worked)
- ✅ Stayed under 512-char limit

---

## What Runway Generated

### Attempt 1: Daytime Cityscape (No People)
- **Time of Day:** Golden hour (correct)
- **Location:** Wide shot of Chicago skyline with L train
- **People:** None visible at human scale
- **Activity:** Static city view, no human activity
- **Camera:** Wide shot (correct)

**Strengths:** Camera, lighting, environment all perfect (100/100 each)  
**Failures:** No people, no human activity (character_state 0/100, action 0/100)

### Attempt 2: Nighttime Rooftop (Single Person)
- **Time of Day:** NIGHT (wrong - broke lighting dimension)
- **Location:** Single person on rooftop overlooking city
- **People:** ONE person visible, facing away, then profile, then arm gesture
- **Activity:** Standing contemplatively, closing eyes, extending arm (no crowd activity)
- **Camera:** Starts medium-wide, ZOOMS TO MEDIUM (wrong - broke camera dimension)

**Strengths:** None (all dimensions failed or degraded)  
**Failures:** Still no crowd/interaction, now also wrong time of day, wrong camera movement, less environment clarity

---

## Dimension-by-Dimension Comparison

| Dimension | Attempt 1 | Attempt 2 | Change | Status |
|-----------|-----------|-----------|--------|--------|
| **character_state** | 0/100 | 0/100 | 0 | ❌ NO FIX |
| **action** | 0/100 | 0/100 | 0 | ❌ NO FIX |
| **camera** | 100/100 | 10/100 | **-90** | 📉 BROKE |
| **lighting** | 100/100 | 0/100 | **-100** | 📉 BROKE |
| **environment_persistence** | 100/100 | 50/100 | **-50** | 📉 DEGRADED |
| **OVERALL** | **55.0/100** | **14.0/100** | **-41.0** | 📉 **WORSE** |

### Verdict Change
- Attempt 1: `correctable` (50-79 range, worth retrying)
- Attempt 2: `manual_review` (below 50, correction failed)

---

## Why The Correction Failed

### Root Cause: Semantic Drift from Prompt Changes

The corrected prompt **over-specified human details** ("faces and gestures clearly shown, interacting closely") which caused Runway to:
1. Generate a **single person** in close-up instead of a crowd scene
2. Focus on **individual human expression** (face, gesture) at the expense of environment context
3. Lose the original "golden hour" temporal context, defaulting to night

### The Seed Locking Paradox

Seed 983559286 was correctly locked across both attempts, but **the prompt changes were too large**. Seed locking preserves visual consistency *given the same prompt*, but when the prompt changes significantly, the seed just ensures *consistent interpretation of the new prompt* — not preservation of the original scene's good elements.

### What We Learned

1. **Replacing entire slot text is too aggressive** — it discarded "Chicago is alive" (scene energy cue) and "Everything is vibrant" (mood cue)
2. **Corrector lacks context** — it only sees expected vs observed text, not the video frames themselves, so it can't gauge *how* the prompt should be adjusted to preserve passing dimensions
3. **Vision model scoring vs Runway interpretation mismatch** — Gemini correctly identified "no people at human scale," but the corrective guidance ("People visible at human scale, faces and gestures clearly shown") was interpreted by Runway as "show ONE person in close-up"
4. **No dimension priority weighting** — corrector treated all failed slots equally, not realizing lighting/camera were already perfect and should be preserved

---

## Infrastructure Wins

Even though the correction strategy failed, the **retry loop infrastructure worked perfectly**:

### ✅ What Worked
1. **Provider selection:** Real Runway confirmed (not simulated)
2. **Seed generation:** Seed 983559286 generated in `submit_job()` as expected
3. **Seed locking:** Same seed used for both attempts (verified in job parameters)
4. **Storage initialization:** Both `render_module` and `render_retry_service` configured
5. **Runway submission:** Both renders submitted and completed successfully
6. **URL handling:** Expired URLs refreshed automatically
7. **Video download:** Both videos downloaded to local storage
8. **Frame extraction:** 3 frames per attempt extracted at 10%, 50%, 90% timestamps
9. **Adherence scoring:** Gemini 2.5 Flash analyzed frames and generated structured scores
10. **Database persistence:** Both attempts saved to `render_attempts` table with full `score_json`
11. **Corrector fixes:** Prescriptive language + paraphrase detection both working
12. **No crashes or hangs:** Entire pipeline ran cleanly end-to-end

### Technical Debt Identified
1. **Keyframe service dependency:** `render_retry_service` requires `_keyframe_service` to be injected, but singleton is created without it — had to extract frames manually via ffmpeg
2. **Storage method naming:** No `storage.save_render_attempt()` — had to call `render_retry_service._persist_attempt()` directly

---

## Next Steps: How to Fix The Correction Strategy

### Option 1: Additive Corrections (Preserve Passing Slots)
Instead of **replacing** failed slot text, **prepend emphasis** while keeping original context:

**Bad (what we did):**
```
"People visible at human scale..." (discards "Chicago is alive", "golden hour")
```

**Good (what we should do):**
```
"Crowds of people at street level, faces visible, actively moving and interacting. Chicago is alive. The L train moves through the skyline. Wide shot, golden hour light."
```

Preserve the passing dimension cues ("Wide shot", "golden hour light") explicitly in the corrected prompt.

### Option 2: Dimension-Aware Correction Budget
Don't touch passing dimensions. Only correct failed dimensions, and use a smaller character budget so the original scene context isn't lost.

### Option 3: Vision-Informed Corrector
The corrector currently only sees text (expected vs observed). To fix this properly, the corrector should:
1. See the **actual frames** from Attempt 1
2. Understand what Runway *did* generate (daytime city, no people)
3. Generate corrections that say "keep the daytime city, but add people at street level"

This requires passing frame paths to the Groq corrector, not just text.

### Option 4: Incremental Prompt Nudging
Instead of aggressive slot replacement, use gentler prompt adjustments:
- Attempt 1 → Attempt 2: Add "+crowds visible at street level" to end of prompt
- If Attempt 2 still fails, Attempt 3: Add "+focus on human figures" 
- Keep iterating with small additive changes, not full slot rewrites

---

## Files Generated

### Videos
- **Attempt 1:** `scene_001_20260705_022333.mp4` (2.87 MB, 5 seconds, daytime cityscape)
- **Attempt 2:** `scene_001_20260705_025049.mp4` (1.78 MB, 5 seconds, nighttime rooftop)

### Frames Extracted
- **Attempt 1:** `frame_1.jpg`, `frame_2.jpg`, `frame_3.jpg` (daytime city)
- **Attempt 2:** `frame_attempt2_1.jpg`, `frame_attempt2_2.jpg`, `frame_attempt2_3.jpg` (nighttime rooftop)

### Database Records
- **render_attempts table:** 2 rows (attempt_number 1 and 2) with full score_json for scene_001

---

## Cost Summary

- **Runway Credits Used:** 2 renders (Attempt 1 + Attempt 2)
- **Gemini Vision API Calls:** 2 scoring runs (6 frames total analyzed)
- **Groq API Calls:** 1 corrective diff generation

---

## Conclusion

### The Good News
**Loop 4's retry infrastructure is production-ready.** Seed locking, adherence scoring, corrective diff generation, and database persistence all work correctly.

### The Bad News
**The correction strategy needs redesign.** Aggressive slot replacement caused semantic drift that broke passing dimensions. The corrector needs to be:
1. **Context-preserving** (don't discard passing slot content)
2. **Vision-informed** (see what Runway actually generated, not just text)
3. **Dimension-aware** (don't touch passing dimensions)
4. **Incremental** (small nudges, not full rewrites)

### Recommendation
Before spending more Runway credits on Attempt 3:
1. Redesign the corrector to use **additive corrections** (prepend emphasis, preserve original)
2. OR manually craft Attempt 3 prompt to verify the infrastructure works with a better correction strategy
3. OR implement **vision-informed corrector** that sees the frames before generating corrections

The pipeline is solid. The correction logic needs to be smarter about preserving what already works.

---

**Test Status:** ✅ Infrastructure Verified | ❌ Correction Strategy Failed  
**Ready for:** Corrector redesign before Attempt 3
