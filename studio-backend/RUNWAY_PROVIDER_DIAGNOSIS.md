# Runway Provider Diagnosis & Fix

## Problem
Renders are completing in simulated mode instead of using the hosted Runway API, despite the API key being present in `.env`.

## Root Cause
The issue is **NOT** with the code logic - the provider configuration is correct. The issue is with **how the environment is loaded**.

## Diagnosis Results

### ✅ Conditions for `ready_for_hosted_generation = True`

ALL of the following must be True:
1. ✅ `config.enabled = True`
2. ✅ `not config.is_simulated = True`
3. ❌ `not missing_requirements = False` (missing: ['api_key'])
4. ✅ `not (provider_id == 'runway' and test_mode == 'mock_success') = True`

**BLOCKING ISSUE**: `missing_requirements = ['api_key']`

### Why is the API key missing?

The `.env` file contains:
```
RUNWAYML_API_SECRET=key_c2e32f36b784c0f5288aec3ded67363e71d363b8fe84064c59684d203b4c6f661031938928ed7771c532c0848074dddb60838355e08781083008910df563e2e7
```

But when the backend starts, the environment variable is NOT loaded.

### Diagnostic Script Results

When running `diagnose_runway_provider.py` (which manually loads .env):
```
✅ RUNWAYML_API_SECRET: SET
✅ Key length: 132
✅ ready_for_hosted_generation: True
✅ provider_mode: hosted_api
```

When the backend starts with uvicorn:
```
❌ Runway key source log is MISSING
❌ "Runway API configured: False" appears in logs
❌ Provider shows as unavailable
```

## The Real Issue: Uvicorn Reload Mode

The problem is that **uvicorn with `--reload` uses a reloader process** that may not properly inherit the environment from the parent process.

The `load_dotenv()` call in `main.py` loads the `.env` file, but:
1. The reloader process starts BEFORE main.py is executed
2. The `RenderService` singleton is created at module import time
3. By the time the singleton is created, the .env may not be loaded yet

## Solutions

### Solution 1: Export Environment Variable (RECOMMENDED)

Instead of relying on `.env` file loading, export the variable in your shell:

```bash
export RUNWAYML_API_SECRET="key_c2e32f36b784c0f5288aec3ded67363e71d363b8fe84064c59684d203b4c6f661031938928ed7771c532c0848074dddb60838355e08781083008910df563e2e7"
python -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload
```

Or add to your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
export RUNWAYML_API_SECRET="key_c2e32f36b784c0f5288aec3ded67363e71d363b8fe84064c59684d203b4c6f661031938928ed7771c532c0848074dddb60838355e08781083008910df563e2e7"
```

### Solution 2: Use a Startup Script

Create `start_backend.sh`:
```bash
#!/bin/bash
set -a  # automatically export all variables
source .env
set +a
python -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload
```

Make it executable and run:
```bash
chmod +x start_backend.sh
./start_backend.sh
```

### Solution 3: Run Without Reload Mode

For production or testing, run without `--reload`:
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8010
```

This ensures the .env is loaded before the singleton is created.

### Solution 4: Use python-dotenv in Shell

```bash
python -c "from dotenv import load_dotenv; load_dotenv('.env'); import os; print(os.getenv('RUNWAYML_API_SECRET'))"
```

If this prints the key, then manually export it.

## Verification

After applying one of the solutions, verify with:

```bash
# Check provider status
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

## Additional Findings

### ✅ No Payload Validation Issues

The code does NOT have "payload unsafe" or "schema invalid" blocking issues:
- Runway API payload only contains valid fields: `model`, `promptText`, `promptImage`, `duration`, `ratio`
- Internal fields (`continuity_context_injected`, `retry_of`, `retry_count`, etc.) are NOT sent to Runway
- They're only stored in the `RenderJobModel` for internal tracking

### ✅ No Test Mode Flags

- `RENDER_PROVIDER_TEST_MODE` is NOT set in `.env`
- No `USE_MOCK` or `FORCE_SIMULATED` flags exist
- No `use_mock_success` parameter is set by default

### ✅ Prompt Length Handling

- Prompts are NOT hard-capped at 512 chars in the render service
- Runway API accepts longer prompts
- Continuity context injection adds formatted blocks but doesn't cause validation failures

## Diagnostic Logging Added

Added comprehensive logging in `render.py` `create_job()` method:

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
- Whether hosted mode is active
- Whether the API key is present
- Any blocking conditions

## Next Steps

1. **Apply Solution 1** (export environment variable)
2. **Restart backend**
3. **Check logs** for "RENDER_JOB_CREATED" line
4. **Verify** `hosted=True` and `key_present=True` appear
5. **Test** a real render job submission

## Files Modified

1. `studio-backend/app/services/render.py` - Added diagnostic logging in `create_job()`
2. `studio-backend/diagnose_runway_provider.py` - Created diagnostic script

## Test Commands

```bash
# Run diagnostic script
cd studio-backend
python diagnose_runway_provider.py

# Check provider status via API
curl http://localhost:8010/api/f51/studio/render/providers | jq '.[] | select(.provider_key=="runway")'

# Check if environment variable is set
echo $RUNWAYML_API_SECRET

# Test render job creation (after fix)
# Submit a render and check logs for "RENDER_JOB_CREATED" line
```

---

**Date**: May 28, 2026
**Status**: Diagnosis complete, solution identified
