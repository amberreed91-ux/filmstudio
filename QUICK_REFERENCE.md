# Quick Reference Card

## 🚀 Essential Commands

```bash
# Run full health check
./health_check.py

# Start backend server
./run_backend.sh

# Quick verification
./verify_backend.sh
```

## 🔍 Status Checks

```bash
# Check if backend is running
lsof -i :8010

# Test health endpoint
curl http://localhost:8010/health

# Test with pretty output
curl -s http://localhost:8010/health | jq
```

## 🗄️ Database Commands

```bash
# Open database
sqlite3 studio-backend/data/studio.db

# Quick queries
sqlite3 studio-backend/data/studio.db "SELECT COUNT(*) FROM projects;"
sqlite3 studio-backend/data/studio.db "SELECT COUNT(*) FROM render_jobs;"

# Check tables
sqlite3 studio-backend/data/studio.db ".tables"
```

## 🎬 API Endpoints

```bash
# Projects
curl http://localhost:8010/api/f51/studio/projects

# Render jobs
curl http://localhost:8010/api/f51/studio/render/jobs

# Overview
curl http://localhost:8010/api/f51/studio/overview

# Create render job (example)
curl -X POST http://localhost:8010/api/f51/studio/render/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj-001",
    "shot_id": "shot-test",
    "provider": "runway",
    "prompt": "A futuristic cityscape"
  }'
```

## 🐛 Troubleshooting

```bash
# Kill process on port 8010
lsof -ti :8010 | xargs kill -9

# Install dependencies
cd studio-backend && pip3 install -r requirements.txt

# Fix database lock
fuser -k studio-backend/data/studio.db

# Check Runway API key
grep RUNWAYML_API_SECRET studio-backend/.env
```

## 📁 Important Files

- `studio-backend/.env` - Configuration
- `studio-backend/data/studio.db` - Database
- `studio-backend/main.py` - Server entry
- `studio-app/package.json` - Frontend deps

## 🎯 Success Indicators

✅ health_check.py shows 30/30 passed  
✅ Backend on http://localhost:8010  
✅ /health returns {"status": "healthy"}  
✅ 17 database tables present  
✅ Runway API configured  

## 🔗 Helpful URLs

- Backend: http://localhost:8010
- API Docs: http://localhost:8010/docs
- Health: http://localhost:8010/health
- Frontend: http://localhost:5173

## 📞 Need Help?

1. Run `./health_check.py`
2. Check `HEALTH_CHECK_GUIDE.md`
3. Review `README_HEALTH_CHECK.md`
