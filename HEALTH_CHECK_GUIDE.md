# AI Film Studio - Health Check & Quick Start Guide

## Overview
This guide helps you verify the health of your AI Film Studio application before continuing development.

## Prerequisites
- Python 3.10+
- Node.js 18+
- SQLite3

## Step 1: Run the Health Check

```bash
# From project root
cd /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project
python3 health_check.py
```

This will verify:
- ✅ Python environment and dependencies
- ✅ SQLite database accessibility and schema
- ✅ Runway API credentials validity
- ✅ Asset URLs and file system permissions
- ✅ All batch features A-F endpoints
- ✅ Backend server (if running)
- ✅ Frontend configuration

## Step 2: Start the Backend

### Option A: Direct Python
```bash
cd studio-backend
python3 main.py
```

The server will start on **http://localhost:8010**

### Option B: Using uvicorn (recommended for development)
```bash
cd studio-backend
uvicorn main:app --reload --host 0.0.0.0 --port 8010
```

### Verify Backend is Running
```bash
# Test health endpoint
curl http://localhost:8010/health

# Expected output:
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "components": {
#     "database": {"status": "ok"},
#     "render_service": {"status": "ok", "active_jobs": 0}
#   }
# }
```

## Step 3: Verify Critical Endpoints

### Projects Endpoint
```bash
curl http://localhost:8010/api/f51/studio/projects
```

### Render Jobs
```bash
curl http://localhost:8010/api/f51/studio/render/jobs
```

### Overview/Production Board
```bash
curl http://localhost:8010/api/f51/studio/overview
```

## Step 4: Start the Frontend (Optional)

```bash
cd studio-app

# Install dependencies (if not already done)
npm install

# Start dev server
npm run dev
```

The frontend will be available at **http://localhost:5173**

## Step 5: Verify Database Schema

```bash
cd studio-backend/data
sqlite3 studio.db

# Inside SQLite shell:
.tables                    # List all tables
SELECT COUNT(*) FROM projects;
SELECT COUNT(*) FROM render_jobs;
SELECT * FROM projects LIMIT 1;
.exit
```

## Expected Tables

The database should have these critical tables:
- `projects` - Project metadata
- `render_jobs` - Render job tracking
- `video_assets` - Video file tracking
- `video_keyframes` - Extracted keyframes
- `video_frame_analyses` - Frame analysis results
- `crew_tasks` - Agent task queue
- `project_memories` - Memory system
- `sessions` - Authentication sessions

## Troubleshooting

### Issue: Database locked
```bash
# Kill any stale connections
fuser -k studio-backend/data/studio.db
```

### Issue: Runway API not working
Check your `.env` file:
```bash
cd studio-backend
cat .env | grep RUNWAYML_API_SECRET
```

Make sure the key starts with `key_` and is valid.

### Issue: Port 8010 already in use
```bash
# Find process using port 8010
lsof -i :8010

# Kill it if needed
kill -9 <PID>
```

### Issue: Dependencies missing
```bash
# Backend
cd studio-backend
pip3 install -r requirements.txt

# Frontend
cd studio-app
npm install
```

## Batch Features Checklist

| Feature | Endpoint | Status |
|---------|----------|--------|
| A - Projects | `/api/f51/studio/projects` | Check |
| B - Crew Agents | `/api/f51/studio/crew/agents` | Check |
| C - Memory System | `/api/f51/studio/memory` | Check |
| D - Scene Intelligence | `/api/f51/studio/scene-intelligence` | Check |
| E - Render Pipeline | `/api/f51/studio/render/jobs` | Check |
| F - Production Board | `/api/f51/studio/overview` | Check |

## Next Steps

Once all checks pass:

1. **Test Runway Integration**
   ```bash
   # Create a test render job
   curl -X POST http://localhost:8010/api/f51/studio/render/jobs \
     -H "Content-Type: application/json" \
     -d '{
       "project_id": "proj-001",
       "shot_id": "shot-test",
       "provider": "runway",
       "prompt": "A futuristic cityscape at night"
     }'
   ```

2. **Monitor render jobs**
   ```bash
   # Watch job status
   watch -n 2 'curl -s http://localhost:8010/api/f51/studio/render/jobs | jq'
   ```

3. **Check asset files**
   ```bash
   ls -lh studio-backend/outputs/video/
   ls -lh studio-backend/outputs/renders/
   ```

## Development Workflow

```bash
# Terminal 1: Backend with auto-reload
cd studio-backend
uvicorn main:app --reload --port 8010

# Terminal 2: Frontend with hot reload
cd studio-app
npm run dev

# Terminal 3: Run health checks periodically
watch -n 60 python3 health_check.py
```

## Production Considerations

Before deploying:
- [ ] Set proper Runway API rate limits
- [ ] Configure database backups
- [ ] Set up log rotation
- [ ] Configure CORS for production domains
- [ ] Enable SSL/TLS
- [ ] Set environment-specific .env files
- [ ] Configure asset CDN if needed

## Support

If you encounter issues not covered here, check:
- Application logs: `studio-backend/logs/`
- Database integrity: Run `PRAGMA integrity_check;` in SQLite
- Network connectivity: Ensure Runway API is reachable
- Disk space: Check available space for video outputs

---

**Last Updated**: 2024
**Version**: 1.0.0
