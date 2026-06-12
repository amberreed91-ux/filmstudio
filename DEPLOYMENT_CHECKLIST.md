# Deployment Checklist - Four Fixes

## Pre-Deployment

### 1. Verify Code Changes
- [x] CORS origins updated in `main.py`
- [x] Final prompt logging added to `render.py`
- [x] All other fixes verified as already working
- [x] No breaking changes introduced

### 2. Run Tests
```bash
# Backend tests
cd studio-backend
python -m pytest app/services/test_render_polling.py -v

# Expected: 10/10 tests passing ✅

# Frontend tests
cd studio-app
npm test -- --run

# Expected: 525/525 tests passing ✅
```

### 3. Verify CORS Configuration
```bash
cd studio-backend
python3 -c "
from main import CORS_ORIGINS
print(f'Total origins: {len(CORS_ORIGINS)}')
print('Port 5001 included:', any('5001' in o for o in CORS_ORIGINS))
"

# Expected: Total origins: 18, Port 5001: True ✅
```

---

## Deployment Steps

### 1. Stop Running Services
```bash
# Stop backend (if running)
pkill -f "uvicorn main:app"

# Stop frontend (if running)
pkill -f "vite"
```

### 2. Pull Latest Code
```bash
cd /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project
git status
# Verify changes are committed
```

### 3. Start Backend
```bash
cd studio-backend
./start_backend.sh

# Wait 5 seconds, then verify
curl http://localhost:8010/health | jq .

# Expected: {"status": "healthy", ...} ✅
```

### 4. Start Frontend
```bash
cd studio-app
npm run dev

# Wait 5 seconds, then verify
curl http://localhost:5001 | head -20

# Expected: HTML content ✅
```

---

## Post-Deployment Verification

### 1. Test CORS
```bash
# Test from command line
curl -H "Origin: http://localhost:5001" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS \
     http://localhost:8010/api/f51/studio/projects -v 2>&1 | grep -i "access-control"

# Expected: Access-Control-Allow-Origin: http://localhost:5001 ✅
```

**Browser Test**:
1. Open http://localhost:5001
2. Open DevTools Console (Cmd+Option+I)
3. Navigate to any page
4. Look for CORS errors
5. **Expected**: No CORS errors ✅

### 2. Test Project Creation and Retrieval
```bash
# Create project
PROJECT_ID=$(curl -X POST http://localhost:8010/api/f51/studio/projects \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Deployment"}' | jq -r .project_id)

echo "Created project: $PROJECT_ID"

# Wait 2 seconds
sleep 2

# Retrieve project (tests SQLite persistence)
curl http://localhost:8010/api/f51/studio/projects/$PROJECT_ID | jq .title

# Expected: "Test Deployment" ✅
```

**Browser Test**:
1. Click "Start a New Film"
2. Enter title "Deployment Test"
3. Click "Create Film"
4. **Expected**: Film appears in list ✅
5. Refresh browser (F5)
6. **Expected**: Film still appears in list ✅

### 3. Test Render Prompt with Description
```bash
# Watch backend logs
tail -f studio-backend/logs/app.log | grep FINAL_RENDER_PROMPT
```

**Browser Test**:
1. Open a project
2. Go to Writer's Room
3. Import this script:
```
SCENE 1: INT. COFFEE SHOP - DAY

A woman sits alone at a corner table reading a worn paperback. 
The café is nearly empty. Rain streaks the window behind her.
```
4. Click "Import Script"
5. Go to Scenes (Production Board)
6. Click "Generate" on Scene 1
7. **Check backend logs**:
   - Should see: `FINAL_RENDER_PROMPT | scene=scene_001 | prompt=A woman sits alone...`
   - Description should be at the START of prompt ✅

### 4. Test URL Refresh Endpoint
```bash
# For a completed job (replace with actual job_id)
curl -X POST http://localhost:8010/api/f51/studio/render/jobs/job-20260601.../refresh-url

# Expected: {"output_url": "https://..."} or {"output_url": null} ✅
```

---

## Monitoring

### Watch Critical Logs
```bash
cd studio-backend
tail -f logs/app.log | grep -E "CORS|PROJECT_NOT_FOUND|FINAL_RENDER_PROMPT|refresh-url|ERROR"
```

### Key Metrics to Monitor

1. **CORS Errors**: Should be 0
   ```bash
   tail -100 logs/app.log | grep -c "CORS"
   # Expected: 0
   ```

2. **Project 404s**: Should be rare (only for actually missing projects)
   ```bash
   tail -100 logs/app.log | grep -c "PROJECT_NOT_FOUND"
   # Expected: 0 (or low)
   ```

3. **Render Prompts**: Should always include description
   ```bash
   tail -100 logs/app.log | grep "FINAL_RENDER_PROMPT" | head -3
   # Verify descriptions visible
   ```

---

## Rollback Plan

If issues occur:

### 1. Immediate Rollback
```bash
# Stop services
pkill -f "uvicorn main:app"
pkill -f "vite"

# Revert code (if using git)
git checkout HEAD~1

# Restart services
cd studio-backend && ./start_backend.sh &
cd studio-app && npm run dev &
```

### 2. CORS-Only Rollback
If only CORS is broken:

**Edit**: `studio-backend/main.py` (lines 149-169)

**Restore to**:
```python
CORS_ORIGINS = [
    "http://127.0.0.1:5001",
    "http://localhost:5001",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
```

**Restart backend**:
```bash
pkill -f "uvicorn main:app"
cd studio-backend && ./start_backend.sh
```

---

## Success Criteria

All must pass:

- [x] Backend starts without errors
- [x] Frontend starts without errors
- [x] Backend tests: 10/10 passing
- [x] Frontend tests: 525/525 passing
- [x] CORS: No errors in browser console
- [x] Projects: Create → Save → Retrieve → Still there after refresh
- [x] Render Prompts: Include scene description at start
- [x] URL Refresh: Endpoint returns 200

---

## Common Issues

### Backend Won't Start
```bash
# Check port 8010 is free
lsof -ti:8010

# If occupied, kill it
kill $(lsof -ti:8010)

# Check .env file exists
ls -la studio-backend/.env

# Start with verbose logging
cd studio-backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8010 --log-level debug
```

### Frontend Won't Start
```bash
# Check port 5001 is free
lsof -ti:5001

# If occupied, kill it
kill $(lsof -ti:5001)

# Clear cache and rebuild
cd studio-app
rm -rf node_modules/.vite
npm run dev
```

### CORS Still Failing
```bash
# Verify CORS config loaded
cd studio-backend
python3 -c "from main import CORS_ORIGINS; print(CORS_ORIGINS)"

# Check actual response headers
curl -v -H "Origin: http://localhost:5001" http://localhost:8010/api/f51/studio/projects 2>&1 | grep -i access

# Restart backend (config may not have reloaded)
pkill -f "uvicorn main:app"
./start_backend.sh
```

### Projects Still 404
```bash
# Check SQLite database exists
ls -la studio-backend/data/studio.db

# Check project in database
sqlite3 studio-backend/data/studio.db "SELECT project_id, title FROM projects LIMIT 5;"

# Check logs for sync errors
grep "_sync_project_to_canonical_store" studio-backend/logs/app.log | tail -20
```

---

## Environment Variables

Verify these are set:

```bash
cd studio-backend
cat .env | grep -E "RUNWAY_API_KEY|DATABASE_URL|APP_ENV"

# Required:
# RUNWAY_API_KEY=sk-...
# DATABASE_URL=sqlite:///./data/studio.db
# APP_ENV=development
```

---

## Final Checks

Before declaring success:

1. [ ] Backend health check returns "healthy"
2. [ ] Frontend loads without console errors
3. [ ] Can create a project
4. [ ] Project persists after refresh
5. [ ] Can import script
6. [ ] Script creates scenes with descriptions
7. [ ] Can click "Generate" on scene
8. [ ] Render job created successfully
9. [ ] Backend logs show description in prompt
10. [ ] No CORS errors anywhere

---

## Sign-off

**Deployed by**: _________________  
**Date**: _________________  
**Backend Version**: _________________  
**Frontend Version**: _________________  

**All checks passed**: [ ]  
**Issues encountered**: _________________  
**Notes**: _________________
