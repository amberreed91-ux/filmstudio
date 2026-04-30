#!/bin/bash

echo "=========================================="
echo "HOSTILE TEST SUITE - RERUN VERIFICATION"
echo "Date: $(date)"
echo "=========================================="

# Create a test project first
echo ""
echo "[TEST 1] Creating test project for validation tests..."
PROJECT_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/ingest-script" \
  -F "title=Hostile-Rerun-Test-$(date +%s)" \
  -F "creative_intent=Testing validation fixes" \
  -F "render_provider=simulated" \
  -F "script_text=INT. TEST ROOM - DAY

A test scene for validation.

CHARACTER
Sample dialogue here." \
  2>/dev/null)
  
PROJECT_ID=$(echo "$PROJECT_RESPONSE" | grep -o '"project_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Project ID: $PROJECT_ID"

# Test 2: review-shot with invalid decision
echo ""
echo "[TEST 2a] review-shot with INVALID decision value..."
INVALID_DECISION=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/projects/${PROJECT_ID}/review-shot" \
  -H "Content-Type: application/json" \
  -d '{"shot_id":"shot-123","decision":"INVALID_DECISION_XYZ","note":"test"}' \
  2>/dev/null)
INVALID_CODE=$(echo "$INVALID_DECISION" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $INVALID_CODE"
if [ "$INVALID_CODE" = "400" ]; then
  echo "STATUS: PASS - Invalid decision rejected"
else
  echo "STATUS: FAIL - Expected 400, got $INVALID_CODE"
  echo "Response: $(echo "$INVALID_DECISION" | head -1)"
fi

# Test 3: review-shot with non-existent shot
echo ""
echo "[TEST 2b] review-shot with NON-EXISTENT shot..."
NONEXISTENT_SHOT=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/projects/${PROJECT_ID}/review-shot" \
  -H "Content-Type: application/json" \
  -d '{"shot_id":"NONEXISTENT_SHOT_999","decision":"approved","note":"test"}' \
  2>/dev/null)
NONEXISTENT_CODE=$(echo "$NONEXISTENT_SHOT" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $NONEXISTENT_CODE"
if [ "$NONEXISTENT_CODE" = "400" ]; then
  echo "STATUS: PASS - Non-existent shot rejected"
else
  echo "STATUS: FAIL - Expected 400, got $NONEXISTENT_CODE"
fi

# Test 4: Render job with invalid provider
echo ""
echo "[TEST 3a] Render job with INVALID provider..."
INVALID_PROVIDER=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/render/jobs?project_id=${PROJECT_ID}&shot_id=shot1&provider=FAKE_PROVIDER_XYZ" \
  2>/dev/null)
INVALID_PROV_CODE=$(echo "$INVALID_PROVIDER" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $INVALID_PROV_CODE"
if [ "$INVALID_PROV_CODE" = "400" ]; then
  echo "STATUS: PASS - Invalid provider rejected"
else
  echo "STATUS: FAIL - Expected 400, got $INVALID_PROV_CODE"
fi

# Test 5: Render job with empty shot_id
echo ""
echo "[TEST 3b] Render job with EMPTY shot_id..."
EMPTY_SHOT=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/render/jobs?project_id=${PROJECT_ID}&shot_id=&provider=simulated" \
  2>/dev/null)
EMPTY_SHOT_CODE=$(echo "$EMPTY_SHOT" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $EMPTY_SHOT_CODE"
if [ "$EMPTY_SHOT_CODE" = "400" ]; then
  echo "STATUS: PASS - Empty shot_id rejected"
else
  echo "STATUS: FAIL - Expected 400, got $EMPTY_SHOT_CODE"
fi

# Test 6: Task creation with invalid task_type
echo ""
echo "[TEST 4a] Task creation with INVALID task_type..."
INVALID_TASK=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/crew/projects/${PROJECT_ID}/tasks" \
  -H "Content-Type: application/json" \
  -d '{"agent_role":"script_analyst","task_type":"parse_script","title":"Test","description":"Testing"}' \
  2>/dev/null)
INVALID_TASK_CODE=$(echo "$INVALID_TASK" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $INVALID_TASK_CODE"
if [ "$INVALID_TASK_CODE" = "400" ]; then
  echo "STATUS: PASS - Invalid task_type rejected with 400"
elif [ "$INVALID_TASK_CODE" = "500" ]; then
  echo "STATUS: FAIL - Returns 500 instead of 400"
else
  echo "STATUS: PARTIAL - Got $INVALID_TASK_CODE"
fi

# Test 7: Valid task creation
echo ""
echo "[TEST 4b] Task creation with VALID task_type..."
VALID_TASK=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/crew/projects/${PROJECT_ID}/tasks" \
  -H "Content-Type: application/json" \
  -d '{"agent_role":"script_analyst","task_type":"analyze_script","title":"Analyze Script","description":"Test"}' \
  2>/dev/null)
VALID_TASK_CODE=$(echo "$VALID_TASK" | grep "HTTP_CODE" | cut -d: -f2)
echo "HTTP Code: $VALID_TASK_CODE"
if [ "$VALID_TASK_CODE" = "200" ] || [ "$VALID_TASK_CODE" = "201" ]; then
  echo "STATUS: PASS - Valid task created"
else
  echo "STATUS: FAIL - Expected success, got $VALID_TASK_CODE"
fi

# Test 8: Study reference linkage
echo ""
echo "[TEST 5] Study reference linkage test..."
STUDY_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8010/api/f51/studio/study-reference-prompt" \
  -F "project_id=${PROJECT_ID}" \
  -F "reference_prompt=Analyze cinematography style" \
  2>/dev/null)
STUDY_CODE=$(echo "$STUDY_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
echo "Study HTTP Code: $STUDY_CODE"

# Check if project now has study linked
sleep 1
PROJECT_CHECK=$(curl -s "http://localhost:8010/api/f51/studio/projects/${PROJECT_ID}" 2>/dev/null)
echo "Checking project for reference_study_library..."
if echo "$PROJECT_CHECK" | grep -q "reference_study_library"; then
  STUDY_LINK=$(echo "$PROJECT_CHECK" | grep -o '"reference_study_library":[^,}]*')
  echo "Reference Library: $STUDY_LINK"
  if echo "$STUDY_LINK" | grep -q "null"; then
    echo "STATUS: FAIL - Study NOT linked (null)"
  else
    echo "STATUS: PASS - Study IS linked"
  fi
else
  echo "STATUS: FAIL - reference_study_library field not found"
fi

echo ""
echo "=========================================="
echo "TEST SUMMARY"
echo "=========================================="
