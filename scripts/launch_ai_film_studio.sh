#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project"
BACKEND_DIR="$ROOT_DIR/studio-backend"
FRONTEND_DIR="$ROOT_DIR/studio-app"
LOG_DIR="$HOME/Library/Logs/AI Film Studio"
BACKEND_LABEL="com.aifilmstudio.backend"
FRONTEND_LABEL="com.aifilmstudio.frontend"
BACKEND_PORT="8010"
FRONTEND_PORT="5001"

mkdir -p "$LOG_DIR"

port_is_listening() {
  local port="$1"
  lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1
}

submit_job() {
  local label="$1"
  local command="$2"

  launchctl remove "$label" >/dev/null 2>&1 || true
  launchctl submit -l "$label" -- /bin/zsh -lc "$command"
}

start_backend() {
  if port_is_listening "$BACKEND_PORT"; then
    return
  fi

  local python="$BACKEND_DIR/.venv/bin/python"
  if [[ ! -x "$python" ]]; then
    python="$ROOT_DIR/.venv/bin/python"
  fi
  if [[ ! -x "$python" ]]; then
    osascript -e 'display alert "AI Film Studio" message "The Python environment was not found. Open Codex once to repair dependencies, then try again."'
    exit 1
  fi

  submit_job "$BACKEND_LABEL" "cd '$BACKEND_DIR' && set -a && source .env && set +a && STUDIO_ACCESS_MODE=local RATE_LIMIT_PER_MINUTE=600 '$python' -m uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT > '$LOG_DIR/backend.log' 2>&1"
}

wait_for_backend_ready() {
  local attempts=30
  local status

  for _ in $(seq 1 "$attempts"); do
    status="$(curl --silent --output /dev/null --write-out '%{http_code}' --connect-timeout 1 --max-time 2 'http://127.0.0.1:8010/ready' || true)"
    if [[ "$status" == "200" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_frontend() {
  if port_is_listening "$FRONTEND_PORT"; then
    return
  fi

  local npm="/opt/homebrew/bin/npm"
  if [[ ! -x "$npm" ]]; then
    npm="$(command -v npm || true)"
  fi
  if [[ -z "$npm" || ! -x "$npm" ]]; then
    osascript -e 'display alert "AI Film Studio" message "npm was not found. Open Codex once to repair frontend dependencies, then try again."'
    exit 1
  fi

  submit_job "$FRONTEND_LABEL" "cd '$FRONTEND_DIR' && '$npm' run dev -- --host 127.0.0.1 > '$LOG_DIR/frontend.log' 2>&1"
}

wait_for_port() {
  local port="$1"
  local attempts="${2:-30}"

  for _ in $(seq 1 "$attempts"); do
    if port_is_listening "$port"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_backend

if ! wait_for_backend_ready; then
  printf 'AI Film Studio backend failed to become ready at http://127.0.0.1:8010/ready after 30 attempts.\n' >&2
  exit 1
fi

start_frontend

if ! wait_for_port "$FRONTEND_PORT" 30; then
  osascript -e 'display alert "AI Film Studio" message "The studio did not finish starting. Check ~/Library/Logs/AI Film Studio/frontend.log for details."'
  exit 1
fi

open "http://localhost:$FRONTEND_PORT/"
