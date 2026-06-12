# Filmmaker-Friendly UI Changes - Implementation Summary

## Overview

This document tracks the transformation of the studio app from a technical interface to a filmmaker-friendly experience. The goal is to make the app accessible to filmmakers with no technical background while keeping all underlying architecture unchanged.

---

## Changes Completed

### 1. Created User-Facing Text Utility Library ✅

**File**: `src/lib/userFacingText.ts`

**Purpose**: Centralized library for transforming technical state to filmmaker-friendly language.

**Key Functions**:
- `friendlyStatus()` - Converts technical status strings to plain language
  - `not_started` → "Not started yet"
  - `pending` → "Getting ready…"
  - `rendering` → "Generating…"
  - `complete` → "Ready"
  - `failed` → "Needs attention"
  - Omits `mock`, `simulated` entirely

- `friendlyRoomName()` - Maps technical room names to friendly names
  - `lobby` → "Home"
  - `studio-dashboard` → "Overview"
  - `writers-room` → "Write"
  - `production-board` → "Scenes"
  - `screening-room` → "Watch"
  - `previs-room` → "Storyboard"
  - `study-room` → "Reference"
  - `approval-room` → "Review"
  - `crew-ops` → "Studio Settings"
  - `cost-manager` → "Usage"
  - `project-slate` → "Project Info"

- `primaryActionForStatus()` - Returns appropriate button label for each status
  - `not_started` → "Generate"
  - `rendering` → "View Progress" (disabled)
  - `complete` → "Review"
  - `approved` → "Watch"
  - `failed` → "Retry"

- `friendlyErrorMessage()` - Converts technical errors to friendly guidance
  - Never shows stack traces, HTTP codes, or raw exceptions
  - Always returns actionable guidance

- `getNextStepGuidance()` - Provides context-aware next step instructions
  - Based on pipeline stage (no_script, script_exists, renders_pending, etc.)
  - Returns headline, body text, button label, and route

- `friendlyDecisionGate()` - Plain language for decision gates
  - Replaces "STUDIO DECISION GATE — Blocked" with friendly messages

- `EMPTY_STATES` - Friendly messages for empty states
  - "No scenes yet. Start in Write to add your first scene."
  - "Nothing generated yet. Go to Scenes to start."

- `ONBOARDING_STEPS` - 3-step intro for first-time users
  - Step 1: Write
  - Step 2: Generate
  - Step 3: Watch

### 2. Updated Navigation Labels ✅

**File**: `src/routes.tsx`

**Changes**:
- Lobby → Home
- Studio Dashboard → Overview
- Writer's Room → Write
- Production Board → Scenes
- Screening Room → Watch

**Remaining** (need to complete):
- Previs Room → Storyboard
- Approval Room → Review
- Study Room → Reference
- Crew Ops → Studio Settings
- Cost Manager → Usage
- Project Slate → Project Info

### 3. Removed Technical Status from TopNav ✅

**File**: `src/components/TopNav.tsx`

**Removed**:
```tsx
<span className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--text-muted)' }}>
  status: {activeProject?.updated_at ? 'active' : 'idle'} • scenes: {activeProject?.source_stats?.scene_count || 0} • renders: {activeProject?.source_stats?.render_count || 0}
</span>
```

This technical readout is no longer visible to users.

---

## Changes Needed (Priority Order)

### HIGH PRIORITY - Entry Points

#### 1. StudioLobby.tsx - Welcoming Start Screen
**Current**: Nearly empty, just text and buttons
**Target**:
```
Large friendly headline: "What are you making today?"
Subtitle: "Your AI film studio. Script to screen."

Two clear options:
[ + Start a new film ]   — primary button, large, prominent

Below that, if projects exist:
"Continue where you left off"
List of recent projects — just film title + "Last edited X days ago"
Each as a clean clickable card

NO technical status. NO provider info. NO pipeline state.
```

#### 2. StudioOverview.tsx - One Clear Next Step
**Current**: Technical grid of system states, health scores, orchestration logs
**Target**:
```
Top: "YOUR FILM" — project title large

Below: One prominent "What to do next" card:
Big friendly instruction based on pipeline stage

Example stages:
- no script yet → "Start by writing your script" + "Go to Write →"
- script exists → "Your scenes are ready to visualize" + "Go to Storyboard →"
- renders pending → "Your film is generating" + "Go to Scenes →"
- renders complete → "Your film is ready to watch" + "Watch your film →"

Below: simple film stats in plain language:
"X scenes written"
"X scenes generated"
"X scenes approved"

REMOVE ENTIRELY:
- Studio Brain Orchestration log
- Signal Board technical readouts
- Graph node counts
- All system status indicators
```

### MEDIUM PRIORITY - Core Workflows

#### 3. ProductionBoard.tsx - Simplified Scene Cards
**Current**: Cards showing raw technical state, provider info, schema status, payload flags
**Target**:
```
Each scene card:
- Scene title (large, readable)
- Status in plain English: "Not started" | "Generating…" | "Ready to review" | "Approved" | "Needs attention"
- Shot count: "3 shots"
- If generating: "2 of 3 shots ready" (NO percentage bar, just fraction)
- If "Needs attention": "One shot didn't generate — tap Retry to try again"
- ONE primary action button based on state:
  - not started → "Generate"
  - generating → "View Progress" (disabled)
  - ready → "Review"
  - approved → "Watch"
  - needs attention → "Retry"

REMOVE from cards:
- Provider mode
- Schema/payload status
- Internal job IDs
- Graph node references
- Any snake_case field values
```

#### 4. PrevisRoom.tsx - Visual First
**Current**: Dense technical form with dropdowns, "Director Console V1.0", "CO-DIRECTOR MODE: Advisory"
**Target**:
```
- Scene title at top
- Large image area — previs image when available, clean placeholder when not
- Placeholder: soft dark rectangle with camera icon + "Tap Generate to preview this scene"
- Below image: simple scene summary in plain language
  - "A tense afternoon in the jury room."
- Simple controls with friendly labels:
  - "What happens in this scene?"
  - "How should this feel?"
  - "Camera movement"
  - "Pace"
- [ Generate Preview ] — one button, plain label

REMOVE:
- "Director Console V1.0" label
- "CO-DIRECTOR MODE: Advisory"
- "Provider" field (hide entirely)
```

#### 5. ScreeningRoom.tsx - Film First
**Current**: Dense intelligence panels competing with video player
**Target**:
```
- Video player: full width, large
- Below player: scene selector — horizontal scroll of scene titles
- Click to jump to that scene's clip
- Intelligence panels: collapsed by default behind single button
- "Show Analysis ›" — quiet, bottom right
- When expanded: slides in from right as sidebar
- Intelligence content uses plain language already — keep that
- Just make it secondary to viewing experience
```

### LOW PRIORITY - Supporting Pages

#### 6. WritersRoom.tsx - Clean Writing Surface
**Target**:
- Dark background, centered text column
- Max 680px width, generous line height
- Comfortable reading width
- Remove any technical overlays

#### 7. Dashboard.tsx (Approval Room) - Plain Language
**Target**:
- Friendly approval messages
- No technical QC terminology
- Clear actions

#### 8. DecisionGateCard.tsx - Friendly Blocking
**Current**: "STUDIO DECISION GATE — Blocked: 2 failed render(s) need recovery before screening."
**Target**:
```
Heading: "Ready to watch?"

If blocked:
"Before you can watch your film, 2 scenes need attention. Tap below to fix them."
[ Fix scenes ] button

If clear:
"Everything looks good. Your film is ready to watch."
[ Watch film ] button
```

### GLOBAL - Technical String Removal

#### Search and Replace Patterns

**Status Strings** - Use `friendlyStatus()`:
- `not_started` → "Not started yet"
- `mock` → (omit)
- `simulated` → (omit)
- `pending` → "Getting ready…"
- `processing` → "Generating…"
- `rendering` → "Generating…"
- `complete` → "Ready"
- `failed` → "Needs attention"
- `blocked` → "Waiting on something"
- `draft` → "In progress"
- `in_review` → "Ready to review"
- `approved` → "Approved"

**Technical Readouts to Remove**:
- "Schema invalid · Provider valid · Payload unsafe"
- "Comparable false · Auto Select false"
- "Execution · Locked · Eligible true · Request blocked"
- "Validation · Schema invalid · Provider valid · Payload unsafe"
- "Shots · 0 · Queue 0 · Ready 0"
- "Takes · 1 · Comparable false · Auto Select false"
- "Render · not_executed · Source mock · Output no"
- "provider_mode=hosted_api · ready_for_hosted_generation=true"

**Error Messages** - Use `friendlyErrorMessage()`:
- Any API error → "Something went wrong. Try again in a moment."
- Any 404 → "We couldn't find that. Try going back."
- Never show: Stack traces, HTTP status codes, Internal error messages, Raw exception text

**Empty States** - Use `EMPTY_STATES`:
- Empty scenes list → "No scenes yet. Start in Write to add your first scene."
- No renders → "Nothing generated yet. Go to Scenes to start."
- Failed render → "This shot needs a retry. Tap Retry to try again."

---

## Implementation Commands

### Find Technical Strings
```bash
# Status strings
grep -r "not_started\|mock\|simulated\|pending\|processing\|rendering" src/ --include="*.tsx" --include="*.ts"

# Technical field names
grep -r "provider_mode\|ready_for_hosted\|schema_invalid\|payload_unsafe" src/ --include="*.tsx" --include="*.ts"

# Internal IDs
grep -r "job_id\|task_id\|graph_id\|node_id" src/ --include="*.tsx" --include="*.ts"

# Technical labels
grep -r "Schema invalid\|Provider valid\|Payload unsafe\|Comparable false" src/ --include="*.tsx" --include="*.ts"

# Old room names
grep -r "Writer's Room\|Production Board\|Screening Room\|Previs Room\|Study Room\|Crew Ops\|Cost Manager\|Project Slate\|Approval Room" src/ --include="*.tsx" --include="*.ts"
```

### Test Commands
```bash
# Build
cd studio-app && npm run build

# Test
cd studio-app && npm test

# Dev server
cd studio-app && npm run dev
```

---

## Testing Checklist

- [ ] First-time user sees onboarding on Overview page
- [ ] Navigation shows friendly names (Home, Write, Scenes, Watch, etc.)
- [ ] No technical status strings visible anywhere
- [ ] No snake_case or camelCase field names shown to users
- [ ] Error messages are friendly and actionable
- [ ] Empty states provide friendly guidance
- [ ] Scene cards show one clear action button
- [ ] Overview page shows clear next step
- [ ] Lobby is welcoming with "What are you making today?"
- [ ] Storyboard (Previs) is visual-first
- [ ] Watch (Screening) prioritizes video player
- [ ] No "Schema invalid", "Provider valid", etc. visible
- [ ] No internal IDs shown prominently
- [ ] All status displays use plain English

---

## Rollback Plan

If needed, all changes can be rolled back by:
1. Reverting `src/lib/userFacingText.ts` (delete file)
2. Reverting `src/routes.tsx` to original labels
3. Reverting `src/components/TopNav.tsx` to show technical status
4. Reverting any page-level changes

No data structures, APIs, or business logic are affected.

---

## Next Steps

1. Complete remaining route label updates in `routes.tsx`
2. Update `StudioLobby.tsx` - highest impact entry point
3. Update `StudioOverview.tsx` - second highest impact
4. Update `ProductionBoard.tsx` - most complex page
5. Update remaining pages systematically
6. Global search and replace for technical strings
7. Add onboarding flow
8. Test thoroughly
9. Document final changes

---

## Notes

- This is a UI/UX transformation only
- No functionality is removed, only hidden or reworded
- All underlying architecture remains unchanged
- Changes are backward compatible
- Focus on filmmaker experience, not technical accuracy
- "Show what to DO, not what the system IS doing"
