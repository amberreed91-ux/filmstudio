#!/bin/bash
# start_runway_backend.sh — the single documented way to start the backend.
#
# Guarantees the Runway-only storyboard engine regardless of stale shell
# state: unsets every DASHSCOPE_* variable, forces DEFAULT_IMAGE_PROVIDER
# and friends, then prints the exact git commit being served (compare with
# GET /health -> git_commit to detect a stale process).
#
# This script does NOT replace the live launchd job
# (gui/501/com.aifilmstudio.backend). To switch the live job to a new tree:
#   1. Back up the DB (see scripts/backup_studio_db.sh + docs/RELEASE_CHECKLIST.md).
#   2. launchctl bootout gui/$(id -u)/com.aifilmstudio.backend
#   3. Verify :8010 is free, then launchctl submit with the command below
#      (keep the unset + env pins identical).
# See docs/RELEASE_CHECKLIST.md for the full pre/post-restart procedure.
set -euo pipefail

cd "$(dirname "$0")/.."

# Purge stale DashScope credentials from the environment (the H1 stale-env trap).
unset DASHSCOPE_API_KEY DASHSCOPE_REGION DASHSCOPE_WORKSPACE_ID || true

export DEFAULT_IMAGE_PROVIDER=runway
export RUNWAY_API_ENABLED=true
export R43K_SOCKET_ONLY=1

COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "Starting studio-backend commit=${COMMIT} image_provider=runway port=8010"

if [ -z "${RUNWAYML_API_SECRET:-}" ] && [ -z "${RUNWAY_API_KEY:-}" ]; then
    echo "WARNING: no RUNWAYML_API_SECRET / RUNWAY_API_KEY in environment; storyboard renders will fail closed." >&2
fi

PORT="${STUDIO_BACKEND_PORT:-8010}"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "${PORT}"
