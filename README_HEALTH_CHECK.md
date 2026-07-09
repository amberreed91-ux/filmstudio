# AI Film Studio - Health Check System

## Quick Start

### 1. Run the Comprehensive Health Check
```bash
./health_check.py
```

This performs 7 comprehensive checks:
1. ✅ Python Environment & Dependencies
2. ✅ Database Health & Schema Integrity
3. ✅ Backend Configuration (Runway API, etc.)
4. ✅ Frontend Configuration
5. ✅ Asset URLs & File System
6. ✅ API Endpoints (if server is running)
7. ✅ Batch Features A-F Endpoints

### 2. Start the Backend Server
```bash
./run_backend.sh
```

This script will:
- Check Python version
- Activate virtual environment (if present)
- Verify dependencies
- Check database existence
- Validate configuration
- Ensure port 8010 is available
- Start the FastAPI server with auto-reload

---

## Detailed Check Breakdown

### Check 1: Python Environment
**What it checks:**
- Python 3.10+ installed
- `requirements.txt` exists
- Critical packages: `fastapi`, `uvicorn`, `pydantic`, `aiohttp`, `sqlite3`

**Fix if fails:**
```bash
cd studio-backend
pip3 install -r requirements.txt
```

### Check 2: Database Health
**What it checks:**
- SQLite database file exists at `studio-backend/data/studio.db`
- Database is accessible (can connect)
- All 17 critical tables present:
  - `projects`
  - `render_jobs`
  - `sessions`
  - `video_assets`
  - `video_keyframes`
  - `video_frame_analyses`
  - `crew_tasks`
  - `project_memories`
  - `scene_memories`
  - `character_memories`
  - `style_memories`
  - `review_memories`
  - `continuity_issues`
  - `style_signatures`
  - `director_signatures`
  - `workflow_executions`
  - `short_film_reviews`

**Fix if fails:**
```bash
# Backup existing database
cp studio-backend/data/studio.db studio-backend/data/studio.db.backup

# Restart backend to trigger schema initialization
cd studio-backend
python3 main.py
# Press Ctrl+C after startup completes
```

### Check 3: Backend Configuration
**What it checks:**
- `.env` file exists
- `RUNWAYML_API_SECRET` is configured (not placeholder)
- `main.py` exists
- `app/` directory structure intact

**Fix if fails:**
```bash
cd studio-backend

# Create .env from example (if you have one)
cp .env.example .env

# Or create manually
cat > .env << EOF
RUNWAYML_API_SECRET=key_your_actual_runway_key_here
COGVIDEO_REPO_PATH=/path/to/CogVideo
COGVIDEO_PYTHON_PATH=/path/to/CogVideo/.venv/bin/python
COGVIDEO_OUTPUT_DIR=./outputs/video
COGVIDEO_MODEL_VARIANT=cogvideox
COGVIDEO_TIMEOUT_SECONDS=600
EOF
```

### Check 4: Frontend Configuration
**What it checks:**
- `package.json` exists and is valid JSON
- Critical dependencies present: `react`, `react-dom`, `react-router-dom`
- `node_modules/` installed
- `vite.config.ts` exists

**Fix if fails:**
```bash
cd studio-app

# Install dependencies
npm install

# If package-lock.json conflicts
rm package-lock.json node_modules -rf
npm install
```

### Check 5: Asset URLs & File System
**What it checks:**
- `outputs/` directory exists
- Subdirectories: `video/`, `previs/`, `renders/`
- `data/` directory exists
- Write permissions on `outputs/`

**Fix if fails:**
```bash
cd studio-backend

# Create directories
mkdir -p outputs/video outputs/previs outputs/renders
mkdir -p data

# Fix permissions
chmod -R 755 outputs data
```

### Check 6: API Endpoints
**What it checks (if server is running):**
- `/health` returns 200
- `/` returns 200
- `/api/f51/studio/projects` responds
- `/api/f51/studio/overview` responds

**Fix if fails:**
```bash
# Make sure server is running
./run_backend.sh

# In another terminal, test manually
curl http://localhost:8010/health
```

### Check 7: Batch Features A-F
**What it checks (if server is running):**
- Feature A: Projects endpoint
- Feature B: Crew Agents endpoint
- Feature C: Memory System endpoint
- Feature D: Scene Intelligence endpoint
- Feature E: Render Pipeline endpoint
- Feature F: Production Board endpoint

---

## Manual Verification Commands

### Test Database Directly
```bash
cd studio-backend/data
sqlite3 studio.db

-- List all tables
.tables

-- Check schema migration version
SELECT * FROM schema_migrations ORDER BY version DESC LIMIT 1;

-- Count records
SELECT COUNT(*) FROM projects;
SELECT COUNT(*) FROM render_jobs;

-- View sample project
SELECT project_id, json_extract(data, '$.title') as title FROM projects LIMIT 1;

.exit
```

### Test API Endpoints Manually
```bash
# Health check with details
curl -s http://localhost:8010/health | jq

# List projects
curl -s http://localhost:8010/api/f51/studio/projects | jq

# List render jobs
curl -s http://localhost:8010/api/f51/studio/render/jobs | jq

# Get overview/production board
curl -s http://localhost:8010/api/f51/studio/overview | jq
```

### Test Runway API
```bash
# Check if credentials are valid (requires server running)
curl -s http://localhost:8010/health | jq '.components.circuit_breakers'
```

### Check File Assets
```bash
# List video outputs
ls -lh studio-backend/outputs/video/

# List previs images
ls -lh studio-backend/outputs/previs/

# List rendered clips
ls -lh studio-backend/outputs/renders/

# Check database file size
du -h studio-backend/data/studio.db
```

---

## Common Issues & Solutions

### Issue: "Database is locked"
**Cause:** Multiple processes accessing SQLite simultaneously

**Solution:**
```bash
# Find processes using the database
lsof studio-backend/data/studio.db

# Kill stale connections
fuser -k studio-backend/data/studio.db

# Restart server
./run_backend.sh
```

### Issue: "Runway API credentials invalid"
**Cause:** Missing or incorrect API key

**Solution:**
1. Get your API key from https://app.runwayml.com/
2. Update `.env`:
   ```bash
   RUNWAYML_API_SECRET=key_your_actual_key_here
   ```
3. Restart server

### Issue: "Port 8010 already in use"
**Cause:** Another process using the port

**Solution:**
```bash
# Find the process
lsof -i :8010

# Kill it
lsof -ti :8010 | xargs kill -9

# Or use a different port
cd studio-backend
uvicorn main:app --reload --port 8011
```

### Issue: "Dependencies missing"
**Cause:** Python packages not installed

**Solution:**
```bash
cd studio-backend
pip3 install -r requirements.txt

# Or use a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

### Issue: "Table does not exist"
**Cause:** Database schema not initialized or corrupted

**Solution:**
```bash
# Option 1: Delete and reinitialize (loses data!)
rm studio-backend/data/studio.db
./run_backend.sh
# Press Ctrl+C after startup

# Option 2: Manual migration (safer)
cd studio-backend
sqlite3 data/studio.db < migrations/create_tables.sql
```

---

## Continuous Monitoring

### Watch health status
```bash
watch -n 5 'curl -s http://localhost:8010/health | jq'
```

### Monitor render jobs
```bash
watch -n 2 'curl -s http://localhost:8010/api/f51/studio/render/jobs | jq length'
```

### Check database growth
```bash
watch -n 60 'du -h studio-backend/data/studio.db'
```

---

## Production Readiness Checklist

Before deploying to production:

- [ ] All health checks pass
- [ ] Runway API credentials configured
- [ ] Database backups configured
- [ ] Log rotation enabled
- [ ] CORS configured for production domains
- [ ] SSL/TLS certificates installed
- [ ] Environment variables secured
- [ ] Rate limiting configured
- [ ] Monitoring/alerting set up
- [ ] Asset CDN configured (if needed)
- [ ] Database connection pooling optimized
- [ ] Error tracking enabled (Sentry, etc.)

---

## Architecture Overview

```
studio-project/
├── health_check.py          # Comprehensive health verification
├── run_backend.sh           # Quick backend startup
├── HEALTH_CHECK_GUIDE.md    # Detailed guide (this file)
│
├── studio-backend/          # Python/FastAPI backend
│   ├── main.py              # Server entry point
│   ├── requirements.txt     # Python dependencies
│   ├── .env                 # Configuration
│   ├── data/
│   │   └── studio.db        # SQLite database
│   ├── outputs/             # Generated assets
│   │   ├── video/           # Video renders
│   │   ├── previs/          # Previs images
│   │   └── renders/         # Final renders
│   └── app/                 # Application code
│       ├── routes/          # API endpoints
│       ├── services/        # Business logic
│       └── data/
│           └── storage.py   # Database layer
│
└── studio-app/              # React/TypeScript frontend
    ├── package.json         # Node dependencies
    ├── vite.config.ts       # Build configuration
    └── src/                 # Application code
```

---

## Support Resources

- **Health Check Tool**: `./health_check.py`
- **Backend Starter**: `./run_backend.sh`
- **API Documentation**: http://localhost:8010/docs (when server running)
- **Database Schema**: See `studio-backend/app/data/storage.py`

---

**Version**: 1.0.0  
**Last Updated**: 2024
