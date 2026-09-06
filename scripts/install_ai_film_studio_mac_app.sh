#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project"
LAUNCH_SCRIPT="$ROOT_DIR/scripts/launch_ai_film_studio.sh"
APP_DIR="$HOME/Applications"
APP_PATH="$APP_DIR/AI Film Studio.app"
LOGIN_AGENT="$HOME/Library/LaunchAgents/com.aifilmstudio.launcher.plist"

mkdir -p "$APP_DIR"
chmod +x "$LAUNCH_SCRIPT"

osacompile -o "$APP_PATH" -e "do shell script quoted form of \"$LAUNCH_SCRIPT\""

if [[ "${1:-}" == "--login" ]]; then
  mkdir -p "$(dirname "$LOGIN_AGENT")"
  cat > "$LOGIN_AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aifilmstudio.launcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>$LAUNCH_SCRIPT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/AI Film Studio/login-launcher.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/AI Film Studio/login-launcher-error.log</string>
</dict>
</plist>
PLIST
  launchctl unload "$LOGIN_AGENT" >/dev/null 2>&1 || true
  launchctl load "$LOGIN_AGENT"
fi

open -R "$APP_PATH"
echo "$APP_PATH"
