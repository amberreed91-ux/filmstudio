#!/bin/bash
# Isolated Studio backend for the reference-upload live validation workstream.
# Own DB + own port so the user's running Studio (8010/data) is untouched.
cd "$(dirname "$0")"
export STUDIO_STORAGE_PATH="$(pwd)/.validation/data"
mkdir -p "$STUDIO_STORAGE_PATH"
exec ./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8047 --log-level info
