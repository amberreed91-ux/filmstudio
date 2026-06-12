# Production Board Render Flow Analysis

## Current State Analysis

### Render Trigger Flow

The render flow in the studio-app works as follows:

1. **PrevisRoom** (`studio-app/src/pages/PrevisRoom.tsx`):
   - User clicks "Director Console" Generate button
   - Calls `handleDirectorGenerate()` which:
     - Calls `createJob(shotId, provider, prompt, referenceAssets)` from StudioContext
     - Calls `submitJob(job.id)` to submit the job
     - Provider is explicitly passed (e.g., "runway")
   - Jobs are created with proper provider and prompt

2. **StudioContext** (`studio-app/src/context/StudioContext.tsx`):
   - `createJob()` calls `createRenderJob()` from studioApi
   - `submitJob()` calls `submitRenderJob()` from studioApi
   - Starts polling job status every 3 seconds when job is rendering/pending
   - Updates renderJobs state with job status

3. **StudioApi** (`studio-app/src/lib/studioApi.ts`):
   - `createRenderJob()` sends POST to `/api/f51/studio/render/jobs` with:
     - project_id
     - shot_id
     - provider (optional, defaults to backend default)
     - prompt (optional)
     - reference_assets (optional)
     - parameters (optional)
   - `submitRenderJob()` sends POST to `/api/f51/studio/render/jobs/{jobId}/submit`
   - `getRenderJobStatus()` polls GET `/api/f51/studio/render/jobs/{jobId}/status`

4. **ProductionBoard** (`studio-app/src/pages/ProductionBoard.tsx`):
   - Loads render jobs via `listRenderJobs(projectId)` every 8 seconds
   - Displays jobs in ProductionExecutionBay component
   - Shows job status, provider, and output URLs
   - **ISSUE**: No Generate button visible on scene cards

5. **ScreeningRoom** (`studio-app/src/pages/ScreeningRoom.tsx`):
   - Loads render jobs via `listRenderJobs(projectId)` every 8 seconds
   - Video player uses `getPreferredAssetUrl()` to select video URL:
     - Priority: `job.output_payload.asset_url` (CloudFront URL)
     - Fallback: `job.output_url`
     - Fallback: `job.output_payload.thumbnail_url` or `job.preview_url`
   - Filters out mock URLs (`storage.example.com`)
   - **GOOD**: Video player correctly uses hosted URLs

## Issues Found

### 1. No Generate Button in Production Board Scene Cards

**Location**: `studio-app/src/pages/ProductionBoard.tsx`

**Problem**: The Production Board shows scene cards but does not have a "Generate" or "Render" button on individual scene cards. The only render controls are:
- ProductionExecutionBay: Shows render queue timeline but no per-scene Generate button
- SceneBatchRenderer: Has "Render All Shots" button but is not integrated into ProductionBoard

**Expected**: Each scene card should have a "Generate" button that:
- Calls `createJob()` with scene_id/shot_id
- Explicitly sets `provider: "runway"` (not "simulated")
- Shows loading state while job is pending
- Polls job status every 10 seconds
- Updates UI when job completes

### 2. No Duration Selector

**Location**: Scene cards in ProductionBoard

**Problem**: No UI to select render duration (5s, 10s, 15s, 20s)

**Expected**: Duration selector dropdown or buttons with:
- Options: 5s, 10s, 15s, 20s
- Default: 10s
- Pass `duration_seconds` in job parameters

### 3. No Real-Time Job Status Display

**Location**: Scene cards in ProductionBoard

**Problem**: Scene cards don't show real-time render job status

**Expected**: Each scene card should show:
- "Generating…" with elapsed time while job is rendering
- "Ready" with thumbnail when complete
- "Needs attention — tap Retry" when failed
- Auto-update every 10 seconds via polling

### 4. Video Player Already Fixed

**Location**: `studio-app/src/pages/ScreeningRoom.tsx`

**Status**: ✅ ALREADY CORRECT

The video player correctly:
- Uses `job.output_payload.asset_url` (CloudFront URL) first
- Falls back to `job.output_url`
- Filters out mock URLs
- Shows honest empty state when no URL available

## Recommended Fixes

### Fix 1: Add Generate Button to Scene Cards

**File**: `studio-app/src/pages/ProductionBoard.tsx`

Add a Generate button to each scene card that:
1. Calls `createJob(sceneId, "runway", prompt, [])` from StudioContext
2. Calls `submitJob(job.id)`
3. Shows loading state
4. Starts polling job status

### Fix 2: Add Duration Selector

**File**: `studio-app/src/pages/ProductionBoard.tsx`

Add duration selector UI:
```tsx
<select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
  <option value={5}>5s</option>
  <option value={10}>10s</option>
  <option value={15}>15s</option>
  <option value={20}>20s</option>
</select>
```

Pass duration in job parameters:
```ts
createJob(sceneId, "runway", prompt, [], { duration_seconds: duration })
```

### Fix 3: Add Real-Time Status Display

**File**: `studio-app/src/pages/ProductionBoard.tsx`

For each scene:
1. Find latest render job for scene
2. Show status based on job.status:
   - "pending" | "rendering" → "Generating… (Xs elapsed)"
   - "complete" | "success" → "Ready" + thumbnail
   - "failed" | "error" → "Needs attention — tap Retry"
3. Poll job status every 10 seconds while any job is pending/rendering

### Fix 4: Integrate SceneBatchRenderer

**File**: `studio-app/src/pages/ProductionBoard.tsx`

The SceneBatchRenderer component already exists and provides:
- "Render All Shots" button
- Batch progress indicator
- Per-job status display
- Retry buttons for failed jobs

**Action**: Import and use SceneBatchRenderer in ProductionBoard scene cards

## Implementation Priority

1. **HIGH**: Add Generate button to scene cards (Fix 1)
2. **HIGH**: Add real-time status display (Fix 3)
3. **MEDIUM**: Add duration selector (Fix 2)
4. **LOW**: Integrate SceneBatchRenderer (Fix 4)

## Testing Checklist

After implementing fixes:

- [ ] User can click Generate on a scene card
- [ ] Generate button shows "Generating…" loading state
- [ ] Job is created with provider="runway"
- [ ] Job is created with duration_seconds=10 (default)
- [ ] Job status updates every 10 seconds automatically
- [ ] Completed job shows "Ready" with thumbnail
- [ ] Failed job shows "Needs attention — tap Retry"
- [ ] Retry button works for failed jobs
- [ ] Duration selector allows choosing 5s/10s/15s/20s
- [ ] Completed video plays in ScreeningRoom with CloudFront URL
- [ ] All 525 frontend tests pass
- [ ] Build succeeds

## Next Steps

1. Read full ProductionBoard.tsx to find scene card rendering code
2. Add Generate button with onClick handler
3. Add duration selector state and UI
4. Add job status polling logic
5. Add status display UI
6. Test complete flow end-to-end
7. Run tests and verify build
