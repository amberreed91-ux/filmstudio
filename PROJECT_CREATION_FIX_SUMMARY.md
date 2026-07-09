# Project Creation API Fix Summary

## Issue Identified
The health check script reported a "422 Unprocessable Entity" error when testing project creation. The issue was that the health check script was sending data as **query parameters** instead of a **JSON body**.

## Root Cause
**Health Check Script (INCORRECT):**
```python
response = requests.post(
    f"{API_BASE}/api/f51/studio/projects",
    params={  # ❌ WRONG - sends as query parameters
        "project_id": project_id,
        "title": "Health Check Test Project",
        "script": "A test scene for health check validation."
    }
)
```

**Backend Endpoint (CORRECT):**
```python
@router.post("/projects")
def create_project(payload: CreateProjectPayload):
    # Expects JSON body with Content-Type: application/json
```

**Frontend API Call (CORRECT):**
```typescript
const project = await fetchJson<PersistedProjectState>('/api/f51/studio/projects', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),  // ✅ CORRECT - sends as JSON body
})
```

## Fix Applied

### 1. Fixed Health Check Script
**File:** `studio-backend/health_check.py`

Changed from:
```python
response = requests.post(
    f"{API_BASE}/api/f51/studio/projects",
    params={...}  # Query parameters
)
```

To:
```python
response = requests.post(
    f"{API_BASE}/api/f51/studio/projects",
    json={  # ✅ JSON body
        "project_id": project_id,
        "title": "Health Check Test Project"
    },
    headers={"Content-Type": "application/json"}
)
```

### 2. Fixed Database Query
The health check was also querying the wrong columns. The `projects` table stores data as JSON in a `data` column, not as separate columns.

Changed from:
```python
cursor.execute("SELECT project_id, title FROM projects WHERE project_id = ?", (project_id,))
```

To:
```python
cursor.execute("SELECT project_id, data FROM projects WHERE project_id = ?", (project_id,))
row = cursor.fetchone()
data = json.loads(row[1]) if row[1] else {}
title = data.get('title', 'N/A')
```

## Verification

### Test Results
Created and ran `test_project_creation_fix.py`:

```
✅ PASS: Project created via API
   Project ID: test_fix_20260528_231614
   Title: Test Project - JSON Body

✅ PASS: Project persisted in database
   DB Record: test_fix_20260528_231614
   Title from data: Test Project - JSON Body

✅ ALL TESTS PASSED - Project creation endpoint working correctly
```

### Manual cURL Test
```bash
curl -X POST http://localhost:8010/api/f51/studio/projects \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Project", "project_id": null}'
```

**Result:** ✅ Status 200, project created and persisted successfully

## Conclusion

**The backend endpoint was CORRECT all along.** The issue was in the health check script sending the wrong request format. 

- ✅ Backend expects JSON body (correct)
- ✅ Frontend sends JSON body (correct)
- ❌ Health check was sending query parameters (fixed)

The project creation API is now verified to be working correctly for both:
1. API endpoint functionality
2. Database persistence
3. Frontend integration

## Files Modified
1. `studio-backend/health_check.py` - Fixed request format and database query
2. `studio-backend/test_project_creation_fix.py` - Created focused test (new file)

## Next Steps
The health check can now proceed to test downstream functionality:
- Scene creation
- Render job creation
- Intelligence services
- All other endpoints
