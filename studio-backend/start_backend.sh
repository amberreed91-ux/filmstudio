#!/bin/bash
# Startup script for studio-backend with proper environment loading

# Change to script directory
cd "$(dirname "$0")"

# Load .env file and export all variables
set -a
source .env
set +a

# Verify Runway API key is loaded
if [ -z "$RUNWAYML_API_SECRET" ]; then
    echo "WARNING: RUNWAYML_API_SECRET not found in .env"
else
    echo "✓ Runway API key loaded (length: ${#RUNWAYML_API_SECRET})"
fi

# Start uvicorn
echo "Starting studio-backend on port 8010..."
python -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload
