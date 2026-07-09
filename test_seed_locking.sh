#!/bin/bash

PROJECT_ID="project_3dba9330f43a"
SCENE_ID="12"
BASE_URL="http://localhost:8000/api/f51/studio"

echo "=== Testing Seed Locking Feature ==="
echo ""

# Test 1: Generate storyboard
echo "Test 1: Generate storyboard for scene $SCENE_ID"
RESULT=$(curl -s -X POST "$BASE_URL/projects/$PROJECT_ID/scenes/$SCENE_ID/storyboard")
echo "Response: $RESULT"

SEED=$(echo "$RESULT" | grep -o '"seed":[0-9]*' | cut -d: -f2)
IMAGE_URL=$(echo "$RESULT" | grep -o '"image_url":"[^"]*' | cut -d'"' -f4)

if [ -z "$SEED" ]; then
  echo "❌ ERROR: No seed returned from storyboard generation"
  exit 1
fi

echo "✅ Seed obtained: $SEED"
echo ""

# Test 2: Generate again to confirm same seed
echo "Test 2: Generate again - should reuse same seed"
RESULT2=$(curl -s -X POST "$BASE_URL/projects/$PROJECT_ID/scenes/$SCENE_ID/storyboard")
SEED2=$(echo "$RESULT2" | grep -o '"seed":[0-9]*' | cut -d: -f2)

if [ "$SEED" = "$SEED2" ]; then
  echo "✅ Seed reused correctly: $SEED2 = $SEED"
else
  echo "❌ Seed changed unexpectedly: $SEED2 != $SEED"
  exit 1
fi
echo ""

# Test 3: Toggle seed lock
echo "Test 3: Lock the seed"
LOCK_RESULT=$(curl -s -X PATCH "$BASE_URL/projects/$PROJECT_ID/scenes/$SCENE_ID/previs/seed" \
  -H "Content-Type: application/json" \
  -d '{"locked": true}')
echo "Response: $LOCK_RESULT"

LOCKED=$(echo "$LOCK_RESULT" | grep -o '"locked":[^,}]*' | cut -d: -f2)
if [ "$LOCKED" = "true" ]; then
  echo "✅ Seed locked successfully"
else
  echo "❌ Failed to lock seed"
  exit 1
fi
echo ""

echo "=== All tests passed! ==="
