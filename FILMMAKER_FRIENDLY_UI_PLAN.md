# Filmmaker-Friendly UI Transformation Plan

## Core Principle
**Show the director what to DO, not what the system IS doing internally.**

Hide all technical state. Surface all creative state.

---

## Implementation Status

### ✅ COMPLETED

1. **Created `userFacingText.ts` utility library**
   - Status transformations (pending → "Getting ready…", complete → "Ready", etc.)
   - Room name mappings (Lobby → Home, Production Board → Scenes, etc.)
   - Action button labels based on status
   - Friendly error messages
   - Empty state messages
   - Next step guidance system
   - Decision gate messages
   - Onboarding steps
   - Film stats formatting

2. **Updated routes.tsx - Primary Navigation**
   - Lobby → Home
   - Studio Dashboard → Overview
   - Writer's Room → Write
   - Production Board → Scenes
   - Screening Room → Watch
   - Archive → Archive (unchanged)

### 🔄 IN PROGRESS

3. **Update remaining routes.tsx entries**
   - Previs Room → Storyboard
   - Approval Room → Review
   - Study Room → Reference
   - Crew Ops → Studio Settings
   - Cost Manager → Usage
   - Project Slate → Project Info

4. **Update TopNav component**
   - Remove technical status line ("status: active • scenes: 0 • renders: 0")
   - Use friendly room names from routes

5. **Update StudioOverview (Dashboard) page**
   - Replace technical grid with "What to do next" card
   - Show one clear next step based on pipeline stage
   - Simple film stats in plain language
   - Remove Studio Brain Orchestration log
   - Remove Signal Board technical readouts
   - Remove graph node counts
   - Remove all system status indicators

6. **Update StudioLobby page**
   - Large friendly headline: "What are you making today?"
   - Subtitle: "Your AI film studio. Script to screen."
   - Two clear options: [+ Start a new film] and recent projects list
   - Remove technical status, provider info, pipeline state

7. **Update ProductionBoard (Scenes) page**
   - Simplify scene cards
   - Status in plain English
   - Shot count: "3 shots"
   - Progress as fraction: "2 of 3 ready" (no percentage bar)
   - ONE primary action button per card based on state
   - Remove provider mode, schema/payload status, internal job IDs

8. **Update PrevisRoom (Storyboard) page**
   - Large image area first
   - Simple scene summary in plain language
   - Friendly control labels
   - Remove "Director Console V1.0" label
   - Remove "CO-DIRECTOR MODE: Advisory"
   - Hide "Provider" field entirely

9. **Update ScreeningRoom (Watch) page**
   - Video player full width, large
   - Intelligence panels collapsed by default
   - "Show Analysis ›" button (quiet, bottom right)
   - When expanded: slides in from right as sidebar

10. **Update WritersRoom (Write) page**
    - Clean writing surface
    - Dark background, centered text column
    - Max 680px width, generous line height
    - Remove technical overlays

11. **Update DecisionGateCard component**
    - Replace "STUDIO DECISION GATE" with "Ready to watch?"
    - Friendly blocking messages
    - Plain language throughout

12. **Update all error messages**
    - Use `friendlyErrorMessage()` from userFacingText.ts
    - Never show stack traces, HTTP codes, raw exceptions

13. **Update all empty states**
    - Use `EMPTY_STATES` from userFacingText.ts
    - Friendly guidance instead of technical messages

14. **Add onboarding flow**
    - Show 3-step intro on Overview page for first-time users
    - Store dismissed state in localStorage
    - Simple numbered steps with dismiss button

15. **Hide technical readouts globally**
    - Find and remove/hide all instances of:
      - "Schema invalid · Provider valid · Payload unsafe"
      - "Comparable false · Auto Select false"
      - "Execution · Locked · Eligible true · Request blocked"
      - "Shots · 0 · Queue 0 · Ready 0"
      - "Takes · 1 · Comparable false · Auto Select false"
      - "Render · not_executed · Source mock · Output no"
      - "provider_mode=hosted_api · ready_for_hosted_generation=true"
      - Any raw field names (snake_case, camelCase)
      - Internal IDs shown prominently

---

## Files to Modify

### Core Utilities (✅ DONE)
- [x] `src/lib/userFacingText.ts` - Created

### Navigation & Routes (🔄 IN PROGRESS)
- [x] `src/routes.tsx` - Partially updated (primary nav done, need to finish remaining routes)
- [ ] `src/components/TopNav.tsx` - Remove technical status, use friendly names

### Pages
- [ ] `src/pages/StudioLobby.tsx` - Welcoming start screen
- [ ] `src/pages/StudioOverview.tsx` - One clear next step
- [ ] `src/pages/ProductionBoard.tsx` - Simplified scene cards
- [ ] `src/pages/PrevisRoom.tsx` - Visual first, friendly labels
- [ ] `src/pages/ScreeningRoom.tsx` - Video first, analysis secondary
- [ ] `src/pages/WritersRoom.tsx` - Clean writing surface
- [ ] `src/pages/Dashboard.tsx` - Friendly approval messages

### Components
- [ ] `src/components/DecisionGateCard.tsx` - Plain language
- [ ] `src/components/RenderActivityPanel.tsx` - Hide technical IDs (already partially done)
- [ ] `src/components/ProviderStatusBadge.tsx` - Hide or simplify
- [ ] `src/components/DirectorConsole.tsx` - Remove version labels
- [ ] `src/components/CoDirectorCollaborationPanel.tsx` - Remove "Advisory" mode labels
- [ ] `src/components/StudioBrainOrchestrationPanel.tsx` - Hide entirely from Overview
- [ ] `src/components/ProductionExecutionBay.tsx` - Simplify technical readouts
- [ ] `src/components/SceneBatchRenderer.tsx` - Friendly status messages

### Context & Hooks
- [ ] Review all status displays in context providers
- [ ] Ensure error messages use friendly transformations

---

## Testing Checklist

After all changes:
- [ ] Run `npm run build` - confirm no TypeScript errors introduced
- [ ] Run `npm test` - confirm all tests pass
- [ ] Manual testing:
  - [ ] First-time user sees onboarding
  - [ ] Navigation shows friendly names
  - [ ] No technical status strings visible
  - [ ] No snake_case field names visible
  - [ ] Error messages are friendly
  - [ ] Empty states are friendly
  - [ ] Scene cards show one clear action
  - [ ] Overview shows clear next step
  - [ ] Lobby is welcoming

---

## Implementation Strategy

1. ✅ Create utility library (DONE)
2. 🔄 Update navigation labels (IN PROGRESS)
3. Update each page systematically:
   - Start with StudioLobby (entry point)
   - Then StudioOverview (dashboard)
   - Then ProductionBoard (most complex)
   - Then remaining pages
4. Update components that show technical state
5. Global search for technical strings and replace
6. Test thoroughly
7. Document changes

---

## Search Patterns for Technical Strings

Use these patterns to find technical strings that need replacement:

```bash
# Status strings
grep -r "not_started\|mock\|simulated\|pending\|processing\|rendering" src/

# Technical field names
grep -r "provider_mode\|ready_for_hosted\|schema_invalid\|payload_unsafe" src/

# Internal IDs
grep -r "job_id\|task_id\|graph_id\|node_id" src/

# Technical labels
grep -r "Schema invalid\|Provider valid\|Payload unsafe\|Comparable false" src/

# Room names (old)
grep -r "Writer's Room\|Production Board\|Screening Room\|Previs Room\|Study Room\|Crew Ops\|Cost Manager\|Project Slate\|Approval Room" src/
```

---

## Notes

- All changes are UI/display only
- No API calls, state management, routing, or business logic changes
- No functionality removed, only hidden or reworded
- Backward compatible with existing data structures
- Can be rolled back by reverting display text changes
