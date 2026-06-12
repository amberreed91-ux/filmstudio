#!/bin/bash
# Verification script for hosted render output fixes

echo "=== Hosted Render Output Fix Verification ==="
echo ""

# Check if backend is running
echo "1. Checking if backend is running..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ Backend is running"
else
    echo "   ❌ Backend is not running"
    echo "   Start with: cd studio-backend && ./start_backend.sh"
    exit 1
fi

# Check if frontend is running
echo ""
echo "2. Checking if frontend is running..."
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "   ✅ Frontend is running"
else
    echo "   ❌ Frontend is not running"
    echo "   Start with: cd studio-app && npm run dev"
    exit 1
fi

# Check provider status
echo ""
echo "3. Checking Runway provider status..."
PROVIDER_STATUS=$(curl -s http://localhost:8000/api/providers | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data.get('providers', []):
    if p.get('provider_id') == 'runway':
        print(f\"Provider: {p.get('name')}\")
        print(f\"Status: {p.get('status')}\")
        print(f\"Mode: {p.get('provider_mode')}\")
        print(f\"Ready for hosted: {p.get('ready_for_hosted_generation')}\")
        print(f\"Missing requirements: {p.get('missing_requirements')}\")
        break
" 2>/dev/null)

if [ -n "$PROVIDER_STATUS" ]; then
    echo "$PROVIDER_STATUS"
else
    echo "   ⚠️  Could not fetch provider status"
fi

# Check for recent render jobs
echo ""
echo "4. Checking for recent render jobs..."
RECENT_JOBS=$(curl -s http://localhost:8000/api/projects | python3 -c "
import sys, json
data = json.load(sys.stdin)
projects = data.get('projects', [])
if projects:
    project_id = projects[0].get('project_id')
    print(project_id)
" 2>/dev/null)

if [ -n "$RECENT_JOBS" ]; then
    echo "   Found project: $RECENT_JOBS"
    
    JOB_INFO=$(curl -s "http://localhost:8000/api/projects/$RECENT_JOBS/render-jobs" | python3 -c "
import sys, json
data = json.load(sys.stdin)
jobs = data.get('jobs', [])
if jobs:
    for job in jobs[:3]:
        print(f\"Job ID: {job.get('id')}\")
        print(f\"  Provider: {job.get('provider')}\")
        print(f\"  Provider Job ID: {job.get('provider_job_id')}\")
        print(f\"  Status: {job.get('status')}\")
        output_url = job.get('output_payload', {}).get('asset_url', '')
        if output_url:
            print(f\"  Output URL: {output_url[:60]}...\")
        print()
else:
    print('No render jobs found')
" 2>/dev/null)
    
    echo "$JOB_INFO"
else
    echo "   ⚠️  No projects found"
fi

echo ""
echo "=== Verification Complete ==="
echo ""
echo "Manual checks to perform:"
echo "1. Open http://localhost:5173 in browser"
echo "2. Navigate to Screening Room"
echo "3. Check Live Render Activity panel shows:"
echo "   - Provider: 'Runway (Hosted)' (not 'No active provider')"
echo "   - Task ID: Shows Runway task ID"
echo "   - Job ID: Shows internal job ID (if different from task ID)"
echo "4. Check completed clips:"
echo "   - Display CloudFront URLs (not mock URLs)"
echo "   - No 'Mock external asset unavailable locally' message"
echo "   - Test shots show [TEST] prefix"
echo ""
