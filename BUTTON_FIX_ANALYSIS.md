# Button Fix Analysis

## Buttons to Fix

### 1. ✅ "Revise" Button in ScreeningRoom
**Location**: `studio-app/src/pages/ScreeningRoom.tsx` line 1549
**Current Behavior**: Only stores decision in localStorage
**Expected Behavior**: Should open revision input and call revision API
**API Available**: `createClipRevision()` in studioApi.ts
**Status**: NEEDS FIX

### 2. ✅ "Analyze Continuity" Button in StudyRoom  
**Location**: `studio-app/src/pages/StudyRoom.tsx` line 1600
**Current Behavior**: Already calls `analyzeProjectContinuity()` API
**Status**: WORKING - No fix needed

### 3. ✅ "Refresh DNA" Button in FilmDNAPanel
**Location**: `studio-app/src/components/FilmDNAPanel.tsx` line 234
**Current Behavior**: Already calls `refreshFilmDNA()` API
**Status**: WORKING - No fix needed

### 4. Intelligence Panel Buttons
**Status**: Need to search for specific buttons that show panel but don't load data

## Buttons That Work (Do Not Touch)

- StudyRoom "Analyze Continuity" - Already calls API
- FilmDNAPanel "Refresh DNA" - Already calls API
- MultiUserCollaborationPanel vote buttons - Already call API

## Fix Plan

### Fix 1: Revise Button in ScreeningRoom

**Current Code** (line 1099-1107):
```typescript
function handleReviewDecision(decision: 'approve' | 'revise' | 'regenerate') {
  if (!activeScene?.scene_id) return
  const raw = localStorage.getItem('studio:screeningReviewActions')
  const existing = raw ? (JSON.parse(raw) as Record<string, string>) : {}
  const next = { ...existing, [activeScene.scene_id]: decision }
  localStorage.setItem('studio:screeningReviewActions', JSON.stringify(next))
  setActionFeedback(`Scene ${activeScene.scene_id} marked: ${decision}`)
}
```

**Needed Changes**:
1. Add state for revision modal/input
2. When decision === 'revise', show revision input UI
3. Collect revision prompt and reason from user
4. Call `createClipRevision()` API with:
   - review_id (need to create review first if not exists)
   - original_job_id (from render job)
   - provider: 'runway'
   - revision_prompt: user input
   - revision_reason: user input
5. Show loading state
6. Show success/error feedback
7. Optionally submit the revision render

**API Signature**:
```typescript
export async function createClipRevision(
  projectId: string, 
  payload: CreateClipRevisionPayload
): Promise<{ revision: ClipRevision }>

type CreateClipRevisionPayload = {
  review_id: string
  original_job_id: string
  provider: string
  revision_prompt: string
  revision_reason: string
  metadata?: Record<string, unknown>
}
```

### Fix 2: Search for Intelligence Panel Buttons

Need to search for buttons in:
- Timeline Intelligence panels
- Character Arc panels  
- Motif panels
- Any panel that shows but doesn't load data

Will search for these patterns:
- Buttons with "Load", "Refresh", "Analyze" text
- onClick handlers that don't call APIs
- Panels that render empty/placeholder data

## Implementation Steps

1. Fix Revise button in ScreeningRoom
   - Add revision modal state
   - Add revision form UI
   - Wire up createClipRevision API
   - Add loading/error states
   - Test the flow

2. Search for broken intelligence panel buttons
   - Grep for intelligence panel components
   - Check each for buttons
   - Verify onClick handlers call APIs
   - Fix any that don't

3. Run tests
   - npm test
   - Verify all 525 tests pass

4. Manual testing
   - Test Revise button flow
   - Test any fixed intelligence buttons
   - Verify visible results
