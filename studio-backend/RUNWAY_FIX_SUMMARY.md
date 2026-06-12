# Runway Provider Fix - Summary

## ✅ PROBLEM SOLVED

Renders were using simulated mode instead of hosted Runway API despite the API key being present in `.env`.

## Root Cause

The issue was **environment variable loading timing**:
- Uvicorn with `--reload` uses a reloader process
- The reloader process doesn't properly inherit environment variables from `.env` file
- The `RenderService` singleton is created at module import time
- By the time the singleton initializes, the `.env` hasn't been loaded yet
- Result: `RUNWAYML_API_SECRET` was not available, causing `missing_requirements: ['api_key']`

## Solution Applied

Created `start_backend.sh` script that:
1. Loads `.env` file using `source`
2. Exports all variables with `set -a`
3. Verifies Runway API key is loaded
4. Starts uvicorn with proper environment

## Verification

### Before Fix
```json
{
  "provider_mode": "unavailable",
  "ready_for_hosted_generation": false,
  "missing_requirements": ["api_key"],
  "display_label": "Runway: hosted unavailable (api_key required)"
}
```

### After Fix
```json
{
  "provider_mode": "hosted_api",
  "ready_for_hosted_generation": true,
  "missing_requirements": [],
  "display_label": "Runway: Real provider mode active"
}
```

## Conditions for `ready_for_hosted_generation = True`

ALL of the following must be True (from `app/services/render.py` lines 246-251):

```python
ready_for_hosted_generation = bool(
    config.enabled                                              # ✅ True
    and not config.is_simulated                                 # ✅ True  
    and not missing_requirements                                # ✅ True (was False before fix)
    and not (provider_id == "runway" and test_mode == "mock_success")  # ✅ True
)
```

## No Other Issues Found

### ✅ Payload Validation
- Runway API payload only contains valid fields: `model`, `promptText`, `promptImage`, `duration`, `ratio`
- Internal fields (`continuity_context_injected`, `retry_of`, `retry_count`, `metadata`) are NOT sent to Runway
- They're only stored in `RenderJobModel` for internal tracking
- No "payload unsafe" or "schema invalid" blocking

### ✅ Test Mode Flags
- `RENDER_PROVIDER_TEST_MODE` is NOT set in `.env`
- No `USE_MOCK`, `FORCE_SIMULATED`, or similar flags exist
- `use_mock_success` parameter is only set when explicitly requested in `manual_overrides`

### ✅ Prompt Length
- No 512 char hard cap in render service (that's only for previs service)
- Runway API accepts longer prompts
- Continuity context injection works correctly

## Usage

### Start Backend
```bash
cd studio-backend
./start_backend.sh
```

### Verify Provider Status
```bash
curl http://localhost:8010/api/f51/studio/render/providers | jq '.[] | select(.provider_key=="runway")'
```

Expected output:
```json
{
  "provider_key": "runway",
  "provider_mode": "hosted_api",
  "ready_for_hosted_generation": true,
  "missing_requirements": [],
  "display_label": "Runway: Real provider mode active"
}
```

## Diagnostic Logging Added

Added comprehensive logging in `render.py` `create_job()` method (lines 472-503):

```python
logger.info(
    "RENDER_JOB_CREATED | job_id=%s | provider=%s | hosted=%s | key_present=%s | test_mode=%s | use_mock=%s | missing=%s",
    job_id,
    provider,
    ready_for_hosted,
    bool(runway_api_key),
    test_mode or "none",
    use_mock_success,
    missing_requirements or "none"
)
```

This will appear in logs when a render job is created, showing:
- Whether hosted mode is active (`hosted=True`)
- Whether the API key is present (`key_present=True`)
- Any blocking conditions

## Files Created/Modified

### Created
1. `studio-backend/start_backend.sh` - Startup script with proper environment loading
2. `studio-backend/diagnose_runway_provider.py` - Diagnostic script
3. `studio-backend/RUNWAY_PROVIDER_DIAGNOSIS.md` - Detailed diagnosis
4. `studio-backend/RUNWAY_FIX_SUMMARY.md` - This file

### Modified
1. `studio-backend/app/services/render.py` - Added diagnostic logging in `create_job()`

## Test Commands

```bash
# Check provider status
curl http://localhost:8010/api/f51/studio/render/providers | jq '.[] | select(.provider_key=="runway")'

# Run diagnostic script
python diagnose_runway_provider.py

# Check environment variable
echo $RUNWAYML_API_SECRET

# Submit a test render (check logs for "RENDER_JOB_CREATED" line)
```

## Next Steps

1. ✅ Backend is now using hosted Runway API
2. ✅ Provider status shows `ready_for_hosted_generation: true`
3. ✅ All tests pass
4. **Ready to submit real renders to Runway Gen-3 Alpha**

When you submit a render job, check the logs for:
```
RENDER_JOB_CREATED | job_id=... | provider=runway | hosted=True | key_present=True | test_mode=none | use_mock=False | missing=none
```

This confirms the job will use the hosted Runway API.

---

**Date**: May 28, 2026
**Status**: ✅ FIXED - Runway provider now using hosted API mode
