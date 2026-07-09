# Render System Diagnosis Report
**Date**: May 29, 2026  
**Status**: DIAGNOSIS ONLY - NO FIXES APPLIED

---

## ISSUE 1: PREVIS IMAGES DON'T MATCH SCENE DESCRIPTIONS

### Finding 1: Previs Image Service Exists But May Not Be Wired Up

**Location**: `studio-backend/app/services/previs_image_service.py`

**How It Works**:
1. ✅ **Uses Runway Gen-3 Alpha** - Not a local generator or placeholder
2. ✅ **Fetches scene data** - Has access to scene description, emotional tone, location, time of day
3. ✅ **Builds real prompts** - Uses `_build_previs_prompt()` method that includes:
   - Scene description
   - Emotional tone
   - Location
   - Time of day
   - Camera details (for shots)
   - Style suffix: "cinematic still, single frame, film photography, shallow depth of field"
4. ✅ **Calls Runway API** - Submits 3-second video jobs to Runway
5. ✅ **Extracts first frame** - Uses FFmpeg to extract frame from video
6. ⚠️ **Requires FFmpeg** - Service checks for FFmpeg availability on startup

**Example Prompt Built**:
```
A tense conversation in a dimly lit room. Tone: psychological tension. Location: INT. COFFEE SHOP. Time: DAY. Style: cinematic still, single frame, film photography, shallow depth of field
```

### Finding 2: No Previs Endpoint Found in Routes

**Searched for**: `POST /api/f51/studio/projects/{id}/previs/generate-scene/{scene_id}`

**Result**: ❌ **Endpoint does not exist in `app/routes/projects.py`**

The previs image service exists but is **not exposed via any API endpoint**. The frontend cannot call it.

### Finding 3: No Previs Images Table

**Checked**: SQLite database `studio.db`

**Result**: ❌ **No `previs_images` table exists**

The database is either:
- Empty/not initialized
- Using a different storage mechanism
- Previs images never actually saved

### Finding 4: Storage Service Reference

The `PrevisImageService` calls:
```python
self.storage.save_previs_image(
    project_id=project_id,
    scene_id=scene_id,
    shot_id=shot_id,
    image_path=output_path,
    job_id=job.id,
    status="complete",
    prompt_used=prompt,
    fallback=False
)
```

But the storage service implementation was not found in the codebase.

### Finding 5: FFmpeg Requirement

The service checks for FFmpeg on startup:
```python
FFMPEG_AVAILABLE = False
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
    FFMPEG_AVAILABLE = result.returncode == 0
```

If FFmpeg is not installed, previs image extraction will fail with:
```
"FFmpeg not found. Install FFmpeg to enable previs image extraction."
```

---

## ISSUE 2: RENDER JOBS FAILING WITH "IDLE" PROVIDER

### Finding 1: "Idle" Provider Display Logic

**Location**: `studio-app/src/lib/providerDisplay.ts`

```typescript
if (!normalized || normalized === 'idle' || normalized === 'unknown_provider') return 'Idle'
```

**Cause**: The provider field on the render job is either:
- Empty string
- null/undefined
- Explicitly set to "idle"
- Set to "unknown_provider"

### Finding 2: Provider Field Not Set on Job Creation

**Location**: `studio-backend/app/services/render.py`

The only place where `job.provider` is explicitly set is in the fallback case:
```python
if not config:
    config = self._provider_configs["simulated"]
    job.provider = "simulated"  # ← Only explicit assignment found
    logger.warning(f"Provider {job.provider} not found, falling back to simulated")
```

**Problem**: When a job is created with `provider="runway"`, the provider field is **never explicitly set on the job object**. It's only passed as a parameter but not assigned to `job.provider`.

### Finding 3: Runway Status Mapping

**Location**: `studio-backend/app/adapters/__init__.py` - `RunwayAdapter.get_job_status()`

**Status Mapping** (Lines 1000-1012):
```python
status_map = {
    "pending": "pending",
    "running": "rendering",
    "processing": "rendering",
    "rendering": "rendering",
    "succeeded": "complete",      # ← Maps "succeeded" to "complete"
    "complete": "complete",
    "completed": "complete",
    "failed": "failed",
    "error": "failed",
    "canceled": "failed",
    "cancelled": "failed",
}
job.status = status_map.get(raw_status, "failed")  # ← Defaults to "failed" if unknown
```

**Analysis**: The mapping looks correct. Runway returns:
- `"PENDING"` → mapped to `"pending"`
- `"RUNNING"` → mapped to `"rendering"`
- `"SUCCEEDED"` → mapped to `"complete"`
- `"FAILED"` → mapped to `"failed"`

However, the code converts to lowercase first:
```python
raw_status = str(response.get("status", "")).strip().lower()
```

So `"SUCCEEDED"` becomes `"succeeded"` and correctly maps to `"complete"`.

### Finding 4: Runway Response Logging

**Location**: `studio-backend/app/adapters/__init__.py`

The code has temporary debug logging:
```python
logger.info(
    "TEMP_RUNWAY_DEBUG request endpoint=%s model=%s payload=%s payload_schema=%s",
    endpoint, model, payload, {k: type(v).__name__ for k, v in payload.items()}
)
```

And:
```python
logger.info("TEMP_RUNWAY_DEBUG auth_probe endpoint=/v1/organization body=%s", auth_probe)
```

And:
```python
logger.info("Runway polling status: task_id=%s status=%s", task_id, poll_status or "unknown")
```

**But**: No logs were found because the backend log file doesn't exist or isn't being written.

### Finding 5: Video URL Extraction

**Location**: `studio-backend/app/adapters/__init__.py` - `RunwayAdapter._extract_video_url()`

```python
@staticmethod
def _extract_video_url(response: dict) -> Optional[str]:
    if not isinstance(response, dict):
        return None
    for key in ("video_url", "output_url", "url"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                value = item.get("video_url") or item.get("url")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None
```

**Analysis**: This checks multiple possible fields:
1. `response["video_url"]`
2. `response["output_url"]`
3. `response["url"]`
4. `response["output"][0]` (if list of strings)
5. `response["output"][0]["video_url"]` (if list of dicts)
6. `response["output"][0]["url"]` (if list of dicts)

This should handle most Runway response formats.

### Finding 6: Database Not Initialized

**Checked**: `studio.db` database

**Result**: ❌ **Database appears empty or not initialized**

Commands like:
```bash
sqlite3 studio.db ".tables"
sqlite3 studio.db ".schema"
```

Returned no output, suggesting:
- Database file exists but is empty
- No tables have been created
- Migrations haven't been run
- Or database is in a different location

**Impact**: Cannot query actual render job data to see:
- What prompt was sent
- What provider_job_id (task_id) was returned
- What status is stored
- What error_message exists
- What output_url was captured

### Finding 7: No Backend Logs Available

**Searched for**:
- `logs/studio.log`
- `studio.log`
- `*.log` files

**Result**: ❌ **No log files found**

**Impact**: Cannot see:
- Actual Runway API responses
- Status polling results
- Error messages
- Debug output from `TEMP_RUNWAY_DEBUG` logging

---

## ROOT CAUSES IDENTIFIED

### Previs Images Issue:
1. ✅ **Service exists and is well-implemented**
2. ❌ **No API endpoint to call the service**
3. ❌ **No database table to store results**
4. ❌ **Storage service not implemented**
5. ⚠️ **FFmpeg may not be installed**

### Render Failure Issue:
1. ❌ **Provider field never set on job object** - Only passed as parameter, never assigned to `job.provider`
2. ⚠️ **Database not initialized** - Cannot verify actual job data
3. ⚠️ **No logs available** - Cannot see actual Runway responses
4. ✅ **Status mapping looks correct** - Should handle SUCCEEDED → complete
5. ✅ **Video URL extraction looks robust** - Checks multiple fields

---

## WHAT NEEDS TO BE FIXED

### For Previs Images:
1. **Add API endpoint** in `app/routes/projects.py`:
   ```python
   @router.post("/projects/{project_id}/previs/generate-scene/{scene_id}")
   async def generate_scene_previs(project_id: str, scene_id: str):
       # Call PrevisImageService.generate_scene_hero()
   ```

2. **Create database table** for previs_images:
   ```sql
   CREATE TABLE previs_images (
       id TEXT PRIMARY KEY,
       project_id TEXT NOT NULL,
       scene_id TEXT NOT NULL,
       shot_id TEXT,
       image_path TEXT NOT NULL,
       job_id TEXT,
       status TEXT NOT NULL,
       prompt_used TEXT,
       fallback BOOLEAN DEFAULT 0,
       created_at TEXT NOT NULL
   );
   ```

3. **Implement storage service** `save_previs_image()` method

4. **Install FFmpeg** on the server

### For Render Failures:
1. **Set provider field on job creation** in `render.py`:
   ```python
   job.provider = provider  # Add this line after creating job
   ```

2. **Add logging to capture Runway responses**:
   ```python
   logger.info("RUNWAY_RAW_RESPONSE | task_id=%s | body=%s", task_id, response)
   ```

3. **Initialize database** - Run migrations to create tables

4. **Enable logging** - Configure log file output

5. **Verify status mapping** - Add test to confirm SUCCEEDED maps correctly

---

## NEXT STEPS

1. **Enable logging first** - Need to see actual Runway responses
2. **Initialize database** - Need to query actual job data
3. **Fix provider field assignment** - Critical for "Idle" issue
4. **Add previs endpoint** - Enable previs image generation
5. **Test with real render** - Trigger job and capture full response

---

## QUESTIONS TO ANSWER WITH FIXES

1. What is the exact JSON structure Runway returns for a completed task?
2. What field contains the video URL in Runway's response?
3. Is the status field uppercase ("SUCCEEDED") or lowercase ("succeeded")?
4. Why is the database empty - are migrations not running?
5. Where are logs being written, if anywhere?
6. Is FFmpeg installed on the server?
7. Does the storage service exist somewhere else in the codebase?

---

**END OF DIAGNOSIS REPORT**
