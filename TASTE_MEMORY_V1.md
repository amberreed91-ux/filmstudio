# Taste Memory v1 - Implementation Complete

**Date**: June 6, 2026  
**Status**: ✅ FRONTEND SESSION ONLY - NO PERSISTENCE

---

## Overview

Implemented Taste Memory v1 following AGENTS.md Creative Memory Rules. This is a **frontend session-only** implementation that tracks filmmaker preferences from repeated choices—slowly, softly, reversibly.

**Key Principle from AGENTS.md**:
> "Infer filmmaker preferences from repeated choices — slowly, softly, reversibly"

---

## Requirements from AGENTS.MD ✅

### ✅ What This Implementation Does

- ✅ **Tracks one axis**: `emotional_residue_vs_structural_clarity`
- ✅ **Infers from Revision Emphasis toggle** in Screening Room
- ✅ **Uses tendency language only**: "you tend to..." never "you always..."
- ✅ **Confidence labels only**: `emerging` / `consistent` / `strong` — NO percentages
- ✅ **One event never defines taste** — Patterns over time define advisory tendencies
- ✅ **Never blocks workflow actions** — Pure advisory, never restrictive
- ✅ **Frontend session only** — Not saved, resets when session ends
- ✅ **Explicitly editable and forgettable** — Clear button provided

### ❌ What This Implementation Avoids (Per AGENTS.md)

- ❌ **NO automatic saving** from toggles - Session only
- ❌ **NO percentages or scores** - Only confidence labels
- ❌ **NO permanent personality claims** - Session preview only
- ❌ **NO "you always" language** - Only "you tend to"
- ❌ **NO blocking of workflow** - Pure observation

---

## Implementation Details

### Architecture

**Custom Hook**: `useTasteMemory()` (`studio-app/src/hooks/useTasteMemory.ts`)
- Observes revision emphasis toggle behavior
- Calculates confidence based on observation count and consistency
- Provides tendency language (no scores)
- Debounces observations to avoid over-counting rapid toggles

**Integration**: `ScreeningCinematicShowcase.tsx`
- Records observation when user changes revision emphasis
- Displays taste profile in existing "Director Taste Profile, Session Preview" section
- Shows observation count for transparency
- Clears memory when user clicks "Clear Session Read"

### Taste Axis Tracked

**Single Axis**: `emotional_residue_vs_structural_clarity`

**Emotional Residue**:
- Favors longer emotional carryover between scenes
- Prioritizes feeling and mood over pacing efficiency
- Values ambiguity and emotional lingering

**Structural Clarity**:
- Favors cleaner pacing and tighter editorial flow
- Prioritizes readability and sequence clarity
- Values efficient storytelling over emotional ambiguity

---

## Confidence Calculation

### Thresholds

**Observation Count Requirements**:
- `emerging`: At least 2 observations
- `consistent`: At least 4 observations
- `strong`: At least 7 observations

**Consistency Ratio Required** (how often same choice made):
- `emerging`: 60% of observations on same axis
- `consistent`: 70% of observations on same axis
- `strong`: 80% of observations on same axis

### Examples

**Scenario 1: Emerging Confidence**
- User toggles to "Emotional Residue" 2 times
- User toggles to "Structural Clarity" 1 time
- Total: 3 observations, 66% emotional residue
- **Result**: `emerging` confidence, leans toward `emotional_residue`
- **Message**: "Early signs suggest you may lean toward emotional residue, though more choices are needed to confirm."

**Scenario 2: Consistent Confidence**
- User toggles to "Structural Clarity" 4 times
- User toggles to "Emotional Residue" 1 time
- Total: 5 observations, 80% structural clarity
- **Result**: `consistent` confidence, leans toward `structural_clarity`
- **Message**: "You tend to lean toward structural clarity in revision decisions."

**Scenario 3: Strong Confidence**
- User toggles to "Emotional Residue" 7 times
- User toggles to "Structural Clarity" 1 time
- Total: 8 observations, 87.5% emotional residue
- **Result**: `strong` confidence, leans toward `emotional_residue`
- **Message**: "Across this session, you tend to favor emotional residue when refining cuts."

---

## Tendency Language

### Language Rules from AGENTS.md ✅

- ✅ **Use "you tend to..." never "you always..."**
- ✅ **Uncertain where evidence is thin**
- ✅ **Supportive and non-judgmental**
- ✅ **Session-scoped, not permanent**

### Actual Messages Used

**Insufficient Data** (<2 observations):
```
"The Studio is still observing your creative choices to understand your tendencies."
```

**Emerging Confidence** (2-3 observations, 60%+ consistency):
```
"Early signs suggest you may lean toward [axis], though more choices are needed to confirm."
```

**Consistent Confidence** (4-6 observations, 70%+ consistency):
```
"You tend to lean toward [axis] in revision decisions."
```

**Strong Confidence** (7+ observations, 80%+ consistency):
```
"Across this session, you tend to favor [axis] when refining cuts."
```

---

## Observation Debouncing

**Problem**: Rapid toggle changes shouldn't be counted as multiple observations
**Solution**: 2-second debounce window

**Behavior**:
- If user toggles multiple times within 2 seconds, only the first toggle is recorded
- This prevents "toggle spam" from inflating observation count
- Encourages thoughtful, intentional choices

**Example**:
1. User clicks "Emotional Residue" at 10:00:00 → ✅ Recorded
2. User clicks "Structural Clarity" at 10:00:01 → ❌ Ignored (within 2 seconds)
3. User clicks "Emotional Residue" at 10:00:03 → ✅ Recorded (>2 seconds later)

---

## UI Integration

### Location

**Component**: `ScreeningCinematicShowcase`
**Section**: "Revision Timeline" panel (bottom section)
**Subsection**: "Director Taste Profile, Session Preview"

### Visual Display

**When Hidden** (tastePreviewHidden = true):
- No taste profile shown
- User can toggle visibility with "Show Taste Preview" button

**When Visible** (tastePreviewHidden = false):

#### Before Enough Data (<2 observations):
```
┌─────────────────────────────────────────────────────┐
│ DIRECTOR TASTE PROFILE, SESSION PREVIEW             │
│                                                     │
│ Current axis: Emerging                              │
│                                                     │
│ The Studio is still observing your creative        │
│ choices to understand your tendencies.              │
│                                                     │
│ The Studio is treating this as a temporary         │
│ creative read, not a permanent profile.             │
└─────────────────────────────────────────────────────┘
```

#### After Enough Data (≥2 observations):
```
┌─────────────────────────────────────────────────────┐
│ DIRECTOR TASTE PROFILE, SESSION PREVIEW             │
│                                                     │
│ Current leaning: Emotional Residue                  │
│ Confidence: Consistent                              │
│                                                     │
│ You tend to lean toward emotional residue in       │
│ revision decisions.                                 │
│                                                     │
│ The Studio is treating this as a temporary         │
│ creative read, not a permanent profile.             │
└─────────────────────────────────────────────────────┘
```

### Controls

**"Clear Session Read" Button**:
- Resets all taste observations
- Clears confidence and leaning
- Restarts observation count from 0

**"Show/Hide Taste Preview" Button**:
- Toggles visibility of taste profile panel
- Does NOT clear observations (they continue tracking)

**Observation Counter**:
- Shown in explainer text: "Observations: 5"
- Provides transparency about how much data is collected

---

## Files Created/Modified

### 1. Created: `useTasteMemory.ts` Hook

**Location**: `studio-app/src/hooks/useTasteMemory.ts`

**Purpose**: Custom React hook for tracking taste preferences

**Exports**:
```typescript
{
  // State
  currentLeaning: TasteAxis | null
  confidence: TasteConfidence
  observationCount: number
  
  // Actions
  recordObservation: (axis, context) => void
  clearMemory: () => void
  
  // Helpers
  getTendencyMessage: () => string
  getConfidenceLabel: () => TasteConfidence
  getCurrentLeaning: () => TasteAxis | null
  getObservationCount: () => number
  hasEnoughData: () => boolean
}
```

**Key Features**:
- Debounced observations (2-second window)
- Confidence calculation based on thresholds
- Tendency language generation
- Session-only state (no persistence)

### 2. Modified: `ScreeningCinematicShowcase.tsx`

**Changes**:
- Imported `useTasteMemory` hook
- Added `useEffect` to record observations when emphasis changes
- Added `useEffect` to clear memory when user clears session
- Updated "Emerging Taste Read" to use real taste data
- Updated "Director Taste Profile, Session Preview" to show:
  - Current leaning (axis)
  - Confidence level
  - Tendency message
  - Observation count

**Lines Modified**: ~30 lines

---

## User Experience Flow

### Scenario 1: Building Taste Profile

**Step 1** - User opens Screening Room:
```
Emerging Taste Read:
"Taste read is still emerging. The Studio needs more revision choices before saying more."

Observations: 0
```

**Step 2** - User selects "Emotional Residue":
```
Emerging Taste Read:
"The Studio is still observing your creative choices to understand your tendencies."

Observations: 1
```

**Step 3** - User works, then selects "Emotional Residue" again (3+ seconds later):
```
Emerging Taste Read:
"Early signs suggest you may lean toward emotional residue, though more choices are needed to confirm."

Director Taste Profile:
Current leaning: Emotional Residue
Confidence: Emerging

Observations: 2
```

**Step 4** - After 5 consistent choices for "Emotional Residue":
```
Emerging Taste Read:
"You tend to lean toward emotional residue in revision decisions."

Director Taste Profile:
Current leaning: Emotional Residue
Confidence: Consistent

Observations: 5
```

**Step 5** - After 8 choices (7 emotional, 1 structural):
```
Emerging Taste Read:
"Across this session, you tend to favor emotional residue when refining cuts."

Director Taste Profile:
Current leaning: Emotional Residue
Confidence: Strong

Observations: 8
```

### Scenario 2: Clearing Memory

**User clicks "Clear Session Read"**:
- All observations deleted
- Confidence resets to "emerging"
- Leaning resets to null
- Counter resets to 0
- UI shows: "The Studio is still observing your creative choices..."

### Scenario 3: Mixed Preferences

**User alternates between both axes** (3 emotional, 3 structural):
```
Emerging Taste Read:
"The Studio is still observing your creative choices to understand your tendencies."

Current leaning: (none - 50/50 split)
Observations: 6
```

---

## Technical Implementation

### State Management

**useState** for component-level state:
- `revisionEmphasis` - Current toggle selection
- `sessionTasteCleared` - Whether user cleared memory

**Custom Hook** (`useTasteMemory`) for observation state:
- `observations[]` - Array of timestamped observations
- `currentLeaning` - Calculated dominant axis
- `confidence` - Calculated confidence level
- `observationCount` - Total observations recorded

### Observation Recording

**Trigger**: `useEffect` watches `revisionEmphasis` changes

**Logic**:
```typescript
useEffect(() => {
  if (!sessionTasteCleared && props.revisions.length > 0) {
    tasteMemory.recordObservation(revisionEmphasis, 'revision_emphasis_toggle')
  }
}, [revisionEmphasis, sessionTasteCleared, props.revisions.length, tasteMemory])
```

**Conditions**:
- ✅ Only records if session not cleared
- ✅ Only records if revisions exist (context present)
- ✅ Debounced within hook (2-second window)

### Memory Clearing

**Trigger**: User clicks "Clear Session Read" button

**Logic**:
```typescript
useEffect(() => {
  if (sessionTasteCleared) {
    tasteMemory.clearMemory()
  }
}, [sessionTasteCleared, tasteMemory])
```

**Result**:
- All observations deleted
- State resets to initial values
- UI updates immediately

---

## Testing Recommendations

### Manual Testing

1. **Building Taste Profile**:
   - [ ] Open Screening Room with revisions
   - [ ] Toggle "Emotional Residue" → Verify observation count increments
   - [ ] Toggle again after 3 seconds → Verify count increments
   - [ ] Toggle within 2 seconds → Verify count does NOT increment (debounced)
   - [ ] After 2 observations → Verify "emerging" confidence shown
   - [ ] After 5 observations (4 same axis) → Verify "consistent" confidence
   - [ ] After 8 observations (7 same axis) → Verify "strong" confidence

2. **Tendency Language**:
   - [ ] <2 observations → Verify "still observing" message
   - [ ] 2-3 observations → Verify "Early signs suggest" message
   - [ ] 4-6 observations → Verify "You tend to lean" message
   - [ ] 7+ observations → Verify "Across this session, you tend to favor" message
   - [ ] All messages use "tend to" language, never "always"

3. **Clearing Memory**:
   - [ ] Build taste profile to "consistent"
   - [ ] Click "Clear Session Read"
   - [ ] Verify observation count resets to 0
   - [ ] Verify confidence resets to "emerging"
   - [ ] Verify message returns to "still observing"
   - [ ] Toggle again → Verify observations start from 0

4. **Mixed Preferences**:
   - [ ] Alternate between both axes
   - [ ] Verify no dominant leaning shown if 50/50 split
   - [ ] Verify message acknowledges uncertainty

5. **UI Visibility**:
   - [ ] Click "Hide Taste Preview" → Verify panel hidden
   - [ ] Click "Show Taste Preview" → Verify panel shown
   - [ ] Verify observations continue tracking when hidden

---

## AGENTS.md Compliance

### Creative Memory Rules ✅

From AGENTS.md:
> ### Taste Memory (v1 — frontend session only, not yet persistent)
> - Infer filmmaker preferences from repeated choices — slowly, softly, reversibly
> - Track axes: `emotional_residue_vs_structural_clarity`, `intimacy_vs_scope`, `ambiguity_vs_exposition`, `visual_consistency_vs_experimentation`, `pacing_patience`
> - Use tendency language only: "you tend to..." never "you always..."
> - Confidence labels: `emerging`, `consistent`, `strong` — no percentages
> - One event never defines taste — patterns over time define advisory tendencies
> - Never use taste memory to block workflow actions

**Implementation Compliance**:
- ✅ Tracks exactly one axis: `emotional_residue_vs_structural_clarity`
- ✅ Infers from repeated choices (revision emphasis toggle)
- ✅ Slowly: Requires multiple observations (2, 4, 7 thresholds)
- ✅ Softly: Uses "you tend to" language, never absolute
- ✅ Reversibly: Clear button provided, session-only (no persistence)
- ✅ Tendency language only: No "always" or definitive claims
- ✅ Confidence labels: emerging/consistent/strong - NO percentages
- ✅ Patterns over time: Single toggle doesn't define taste
- ✅ Never blocks workflow: Pure advisory, no UI restrictions

### What Must NEVER Be Remembered Automatically ✅

From AGENTS.md:
> - Every click or transient UI interaction
> - Temporary one-off toggles
> - Private/raw notes without explicit consent
> - Permanent personality claims

**Implementation Compliance**:
- ✅ Doesn't record every click - only deliberate emphasis changes
- ✅ Debounces to avoid counting temporary toggles
- ✅ Session-only - no permanent storage
- ✅ No personality claims - uses "you tend to" language

---

## Future Enhancements (Not in Scope)

These are intentionally **NOT implemented** for v1:

### v2: Persistence
- Save taste observations to project memory
- Load past observations when returning to project
- Track across sessions, not just within session

### v2: Additional Axes
- `intimacy_vs_scope`
- `ambiguity_vs_exposition`
- `visual_consistency_vs_experimentation`
- `pacing_patience`

### v2: Additional Observation Points
- Scene comparison behavior
- Approval vs revision patterns
- Cut decision journal entries
- Prompt override patterns

### v2: Explicit Save Flow
- "Save this decision to project memory" button (per AGENTS.md)
- User must explicitly consent to persist
- Every saved memory must be editable

---

## Performance Impact

### Zero Performance Cost ✅

- **No API calls** - Pure frontend state
- **No database queries** - Session memory only
- **No localStorage** - Intentionally not persisted
- **Minimal memory** - Array of observations (~100 bytes each)
- **Debounced** - Prevents excessive state updates

### Memory Usage: Negligible

- Single custom hook (~150 lines)
- Observation array (max ~20-30 observations per session)
- React state (~1KB total)

---

## Health Check: 40/40 PASSED ✅

```
Total Checks: 40
Passed: 40
Failed: 0
Duration: 1.71s
```

All systems healthy after implementation.

---

## Documentation

### Code Comments

The hook includes comprehensive JSDoc comments:
```typescript
/**
 * Taste Memory v1 - Frontend Session Only
 * 
 * Track filmmaker preferences from repeated choices — slowly, softly, reversibly.
 * Following AGENTS.md Taste Memory Rules:
 * - Infer from revision emphasis toggle behavior only
 * - Track one axis: emotional_residue_vs_structural_clarity
 * - Use tendency language only: "you tend to..." never "you always..."
 * - Confidence labels: emerging/consistent/strong — no percentages
 * - One event never defines taste — patterns over time define advisory tendencies
 * - Never block workflow actions
 */
```

---

## Conclusion

✅ **Taste Memory v1 Complete**  
✅ **Frontend Session Only**  
✅ **Single Axis Tracked**: emotional_residue_vs_structural_clarity  
✅ **Tendency Language Only** ("you tend to...")  
✅ **Confidence Labels Only** (emerging/consistent/strong)  
✅ **No Scores or Percentages**  
✅ **Slowly, Softly, Reversibly**  
✅ **Never Blocks Workflow**  
✅ **Health Check Passed (40/40)**

The Taste Memory v1 feature is now live in Screening Room, providing filmmakers with gentle, reversible insight into their creative tendencies—without permanent personality claims or workflow restrictions.

**Next Step (v2)**: Add explicit-save flow and project-level persistence per AGENTS.md rules.

