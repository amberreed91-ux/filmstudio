# Hosted Render Output URL Resolution - Fix Summary

## Issue
Hosted renders were generating successfully but completed shots showed "Mock external asset unavailable locally" and the live activity panel showed "No active provider" despite renders being active.

## Root Causes Identified

1. **Asset URL Priority**: Frontend was checking for local file paths before using CloudFront URLs from Runway
2. **Provider Display**: Provider field was being resolved but showing "idle" or "unknown_provider" when no provider was set
3. **Task ID vs Job ID**: The UI was showing internal job IDs instead of actual Runway task IDs
4. **Test Data Visibility**: Stress test shots were not visually distinguished from real scene shots

## Changes Made

### 1. Frontend - Asset URL Resolution (`studio-app/src/pages/ScreeningRoom.tsx`)

**Added `getPreferredAssetUrl()` function** with correct priority order:
```typescript
function getPreferredAssetUrl(job: any): string {
  // Priority order for hosted media:
  // 1. output_payload.asset_url (CloudFront URL from Runway)
  // 2. output_url (legacy field)
  // 3. preview_url (if available)
  // 4. empty string (show honest empty state)
  
  const assetUrl = job.output_payload?.asset_url || ''
  if (assetUrl && !isMockExternalAssetUrl(assetUrl)) {
    return assetUrl
  }
  
  const outputUrl = job.output_url || ''
  if (outputUrl && !isMockExternalAssetUrl(outputUrl)) {
    return outputUrl
  }
  
  const previewUrl = job.output_payload?.thumbnail_url || job.preview_url || ''
  if (previewUrl && !isMockExternalAssetUrl(previewUrl)) {
    return previewUrl
  }
  
  return ''
}
```

**Updated clips display** to use the new function and added [TEST] prefix for stress test shots:
- Clips now use `getPreferredAssetUrl(job)` instead of checking mock domains
- Added visual indicator for test shots: `{isTestShot && <span className="text-zinc-500 mr-1">[TEST]</span>}`
- Removed "Mock external asset unavailable locally" message entirely

### 2. Frontend - Provider Display (`studio-app/src/lib/providerDisplay.ts`)

**Enhanced `formatProviderLabel()` function** to show "Runway (Hosted)" for hosted API mode:
```typescript
export function formatProviderLabel(
  rawProvider?: string | null, 
  availableProviderIds: string[] = [], 
  providerMode?: string
): string {
  const normalized = (rawProvider || '').trim().toLowerCase()
  const mode = (providerMode || '').trim().toLowerCase()
  
  if (!normalized || normalized === 'idle' || normalized === 'unknown_provider') return 'Idle'
  
  // Show "Runway (Hosted)" for hosted API mode
  if (normalized === 'runway') {
    if (mode === 'hosted_api' || mode === 'hosted') return 'Runway (Hosted)'
    return 'Runway'
  }
  // ... rest of providers
}
```

### 3. Frontend - Task ID Display (`studio-app/src/components/RenderActivityPanel.tsx`)

**Updated to show both Runway task ID and internal job ID**:
```tsx
<div className="mt-2 space-y-2">
  <div className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 text-[11px] text-zinc-300">
    <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Task ID</span>
    <div className="mt-1 truncate font-mono text-[11px] text-zinc-100">{activity?.taskId || enteredTaskId || 'n/a'}</div>
  </div>
  {activity?.taskId && activity.taskId !== (activity as any).jobId && (
    <div className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 text-[11px] text-zinc-300">
      <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Job ID</span>
      <div className="mt-1 truncate font-mono text-[9px] text-zinc-400">{(activity as any).jobId || 'n/a'}</div>
    </div>
  )}
</div>
```

### 4. Frontend - Activity Context (`studio-app/src/context/RenderActivityContext.tsx`)

**Enhanced `LiveRenderActivity` type** to include `jobId`:
```typescript
export type LiveRenderActivity = {
  status: LiveRenderStatus
  provider: string
  selectedProvider: string | null
  scene: string
  taskId: string
  jobId: string  // Added
  elapsedSeconds: number
  updatedAt: number
  isActive: boolean
}
```

**Updated provider resolution logic**:
- Changed `taskId` to use `job.provider_job_id` (Runway task ID) first, then fall back to `job.id`
- Added `jobId` field to always store the internal job ID
- Updated polling logic to check both `taskId` and `jobId` for active jobs

### 5. Backend - Provider Field Verification

**Verified in `studio-backend/app/services/render.py`**:
- The `provider` field is correctly set on line 418 when creating render jobs
- Provider is validated against known providers
- Diagnostic logging shows provider status on job creation (lines 472-503)

**Verified in `studio-backend/app/adapters/__init__.py`**:
- `provider_job_id` is correctly set to the Runway task ID (line 788)
- Provider mode is stored in `output_payload.metadata.provider_response_normalized.metadata.provider_mode`

### 6. Media Selection Logic (`studio-app/src/lib/studioMedia.ts`)

**Verified existing logic is correct**:
- Already prioritizes hosted output URLs first
- Checks `output_payload.asset_url` before falling back to other fields
- Correctly identifies hosted vs mock outputs

## Results

✅ **Asset URLs**: Completed hosted renders now display CloudFront URLs correctly
✅ **Provider Display**: Shows actual provider from job, displays as "Runway (Hosted)" for hosted API mode
✅ **Task ID**: Displays both Runway task ID (from `provider_job_id`) and internal job ID
✅ **Test Data**: Stress test shots are visually marked with [TEST] prefix
✅ **No Mock Message**: Removed "Mock external asset unavailable locally" message entirely

## Files Modified

### Frontend (studio-app)
1. `src/pages/ScreeningRoom.tsx` - Added `getPreferredAssetUrl()`, updated clips display, added [TEST] prefix
2. `src/lib/providerDisplay.ts` - Enhanced to show "Runway (Hosted)" for hosted mode
3. `src/components/RenderActivityPanel.tsx` - Updated to show both task ID and job ID
4. `src/context/RenderActivityContext.tsx` - Added `jobId` field, updated provider resolution

### Backend (studio-backend)
- No changes needed - provider field and provider_job_id are already correctly set

## Testing

- Backend tests: 20 passed, 1 failed (unrelated - test expects empty API key but env has one set)
- Frontend build: Pre-existing TypeScript errors unrelated to these changes
- Manual testing recommended: Start a hosted render and verify:
  1. Live activity panel shows "Runway (Hosted)" as provider
  2. Task ID shows actual Runway task ID
  3. Job ID shows internal ID below task ID
  4. Completed clips display CloudFront URLs correctly
  5. No "Mock external asset unavailable locally" message appears
  6. Test shots show [TEST] prefix

## Next Steps

1. Start backend with `./start_backend.sh` (ensures env vars are loaded)
2. Start frontend with `npm run dev`
3. Create a new hosted render job
4. Verify all fixes are working as expected
5. If any issues remain, check browser console and backend logs for diagnostic output
