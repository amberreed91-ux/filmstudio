#!/bin/bash
#
# Example workflow for testing adherence scoring with real video
#
# This script demonstrates:
# 1. Extracting 3 frames from a video at 10%, 50%, 90% positions
# 2. Running the manual adherence check with those frames
#

set -e  # Exit on error

# Configuration
VIDEO_FILE="${1:-test_render.mp4}"
TEMP_DIR="./adherence_test_frames"

# Check if video file exists
if [ ! -f "$VIDEO_FILE" ]; then
    echo "❌ Error: Video file not found: $VIDEO_FILE"
    echo "Usage: $0 <video_file.mp4>"
    exit 1
fi

# Check if GROQ_API_KEY is set
if [ -z "$GROQ_API_KEY" ]; then
    echo "❌ Error: GROQ_API_KEY environment variable not set"
    echo "Please run: export GROQ_API_KEY='your_api_key_here'"
    exit 1
fi

echo "════════════════════════════════════════════════════════════════════════════"
echo "ADHERENCE SCORING TEST WORKFLOW"
echo "════════════════════════════════════════════════════════════════════════════"
echo "Video file: $VIDEO_FILE"
echo ""

# Create temporary directory for frames
mkdir -p "$TEMP_DIR"

# Get video duration in seconds
echo "📹 Analyzing video..."
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO_FILE")
echo "   Duration: ${DURATION}s"

# Calculate frame positions (10%, 50%, 90%)
POS_10=$(echo "$DURATION * 0.1" | bc)
POS_50=$(echo "$DURATION * 0.5" | bc)
POS_90=$(echo "$DURATION * 0.9" | bc)

echo ""
echo "🎬 Extracting frames at:"
echo "   10% position: ${POS_10}s"
echo "   50% position: ${POS_50}s"
echo "   90% position: ${POS_90}s"

# Extract frames using ffmpeg
FRAME_10="$TEMP_DIR/frame_10pct.jpg"
FRAME_50="$TEMP_DIR/frame_50pct.jpg"
FRAME_90="$TEMP_DIR/frame_90pct.jpg"

ffmpeg -ss "$POS_10" -i "$VIDEO_FILE" -frames:v 1 -q:v 2 "$FRAME_10" -loglevel error
ffmpeg -ss "$POS_50" -i "$VIDEO_FILE" -frames:v 1 -q:v 2 "$FRAME_50" -loglevel error
ffmpeg -ss "$POS_90" -i "$VIDEO_FILE" -frames:v 1 -q:v 2 "$FRAME_90" -loglevel error

echo "   ✓ Frames extracted to: $TEMP_DIR/"

# Prompt user for expected slot text
echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "ENTER EXPECTED SLOT TEXT"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Please enter the expected text for each dimension:"
echo "(This should match what you specified in the original prompt)"
echo ""

read -p "Character State (e.g., 'weathered hand, pale skin'): " CHARACTER
read -p "Action (e.g., 'reaching toward artifact'): " ACTION
read -p "Camera (e.g., 'extreme closeup'): " CAMERA
read -p "Lighting (e.g., 'dim candlelight'): " LIGHTING
read -p "Environment (e.g., 'stone pedestal'): " ENVIRONMENT

# Run adherence check
echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "RUNNING ADHERENCE CHECK"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

python manual_adherence_check.py \
    --frames "$FRAME_10" "$FRAME_50" "$FRAME_90" \
    --character "$CHARACTER" \
    --action "$ACTION" \
    --camera "$CAMERA" \
    --lighting "$LIGHTING" \
    --environment "$ENVIRONMENT"

RESULT=$?

echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "TEST COMPLETE"
echo "════════════════════════════════════════════════════════════════════════════"

case $RESULT in
    0)
        echo "✅ Result: PASS (score ≥ 80)"
        ;;
    1)
        echo "⚠️  Result: CORRECTABLE (50 ≤ score < 80)"
        echo "   → In production, this would trigger a corrective diff + retry"
        ;;
    2)
        echo "🔴 Result: MANUAL REVIEW (score < 50)"
        echo "   → In production, this would be flagged for human review"
        ;;
    *)
        echo "❌ Result: ERROR"
        ;;
esac

echo ""
echo "Extracted frames saved in: $TEMP_DIR/"
echo "You can view them to see what the vision model analyzed."
echo ""

# Optionally clean up
read -p "Delete extracted frames? [y/N]: " CLEANUP
if [ "$CLEANUP" = "y" ] || [ "$CLEANUP" = "Y" ]; then
    rm -rf "$TEMP_DIR"
    echo "✓ Frames deleted"
else
    echo "✓ Frames kept in: $TEMP_DIR/"
fi

exit $RESULT
