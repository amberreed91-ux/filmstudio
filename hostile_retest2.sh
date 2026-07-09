#!/bin/bash

echo "=========================================="
echo "DETAILED VALIDATION TEST - CORRECTED"
echo "=========================================="

PROJECT_ID="project-20260413211515"

# Test 1: review-shot validation (422 is FastAPI's validation error code)
echo ""
echo "[TEST 1a] review-shot - Invalid decision value..."
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/projects/${PROJECT_ID}/review-shot" \
  -H "Content-Type: application/json" \
  -d '{"shot_id":"shot-123","decision":"INVALID","note":"test"}' \
  2>/dev/null)
CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")
echo "HTTP Code: $CODE"
echo "Response: $BODY"
if [ "$CODE" = "422" ] || [ "$CODE" = "400" ]; then
  echo "STATUS: PASS - Validation error returned (validation IS working)"
else
  echo "STATUS: FAIL - No validation error"
fi

echo ""
echo "[TEST 1b] review-shot - Missing required fields..."
RESPONSE2=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/projects/${PROJECT_ID}/review-shot" \
  -H "Content-Type: application/json" \
  -d '{}' \
  2>/dev/null)
CODE2=$(echo "$RESPONSE2" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $CODE2"
if [ "$CODE2" = "422" ] || [ "$CODE2" = "400" ]; then
  echo "STATUS: PASS - Required fields validated"
else
  echo "STATUS: FAIL"
fi

echo ""
echo "[TEST 1c] review-shot - Valid request..."
RESPONSE3=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/projects/${PROJECT_ID}/review-shot" \
  -H "Content-Type: application/json" \
  -d '{"shot_id":"test-shot","decision":"approved","note":"looks good"}' \
  2>/dev/null)
CODE3=$(echo "$RESPONSE3" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $CODE3"
if [ "$CODE3" = "200" ]; then
  echo "STATUS: PASS - Valid request accepted"
else
  echo "STATUS: INFO - Got $CODE3"
fi

echo ""
echo "=========================================="
echo "RENDER JOB VALIDATION TESTS"
echo "=========================================="

# Test 2: Render job - check the actual code
echo ""
echo "[TEST 2a] Checking render jobs endpoint source..."
# Look for validation in the render route
grep -n "provider" /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-backend/app/routes/render.py 2>/dev/null | head -20

echo ""
echo "[TEST 2b] Creating render job with INVALID provider..."
RENDER_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/render/jobs?project_id=${PROJECT_ID}&shot_id=test-shot&provider=FAKE_XYZ" 2>/dev/null)
RENDER_CODE=$(echo "$RENDER_RESP" | grep "HTTP_CODE" | cut -d: -f2)
RENDER_BODY=$(echo "$RENDER_RESP" | grep -v "HTTP_CODE")
echo "HTTP Code: $RENDER_CODE"
echo "Response: $RENDER_BODY"
if [ "$RENDER_CODE" = "200" ]; then
  PROVIDER=$(echo "$RENDER_BODY" | grep -o '"provider":"[^"]*"' | head -1 | cut -d'"' -f4)
  echo "Provider stored: $PROVIDER"
  if [ "$PROVIDER" = "FAKE_XYZ" ]; then
    echo "STATUS: FAIL - Invalid provider accepted!"
  fi
fi

echo ""
echo "[TEST 2c] Creating render job with EMPTY shot_id..."
RENDER_RESP2=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/render/jobs?project_id=${PROJECT_ID}&shot_id=&provider=simulated" 2>/dev/null)
RENDER_CODE2=$(echo "$RENDER_RESP2" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $RENDER_CODE2"
if [ "$RENDER_CODE2" = "200" ]; then
  echo "STATUS: FAIL - Empty shot_id accepted!"
fi

echo ""
echo "=========================================="
echo "STUDY REFERENCE LINKAGE TEST"
echo "=========================================="

# Create new project for study test
echo "[TEST 3a] Creating project for study test..."
NEW_PROJECT=$(curl -s -X POST "http://localhost:8010/api/f51/studio/ingest-script" \
  -F "title=Study-Link-Test-$(date +%s)" \
  -F "creative_intent=Testing study linkage" \
  -F "render_provider=simulated" \
  -F "script_text=INT. STUDY ROOM - DAY

A scene for study testing." 2>/dev/null)
NEW_PROJECT_ID=$(echo "$NEW_PROJECT" | grep -o '"project_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "New Project ID: $NEW_PROJECT_ID"

echo ""
echo "[TEST 3b] Creating study reference with project_id..."
STUDY_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/study-reference-prompt" \
  -F "project_id=${NEW_PROJECT_ID}" \
  -F "reference_prompt=Analyze cinematography" 2>/dev/null)
STUDY_CODE=$(echo "$STUDY_RESP" | grep "HTTP_CODE" | cut -d: -f2)
STUDY_ID=$(echo "$STUDY_RESP" | grep -o '"reference_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Study HTTP Code: $STUDY_CODE"
echo "Study ID: $STUDY_ID"

echo ""
echo "[TEST 3c] Checking if study is linked to project..."
sleep 1
PROJECT_CHECK=$(curl -s "http://localhost:8010/api/f51/studio/projects/${NEW_PROJECT_ID}" 2>/dev/null)
echo "$PROJECT_CHECK" | python3 -c "import sys,json; d=json.load(sys.stdin); print('reference_study_library:', d.get('reference_study_library', 'NOT FOUND'))" 2>/dev/null || echo "reference_study_library: null"

