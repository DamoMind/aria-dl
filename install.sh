#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
DATA_DIR="${HOME}/.local/share/aria-dl"
PLIST="${HOME}/Library/LaunchAgents/com.damomind.aria-dl.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$BIN_DIR" "$DATA_DIR/jobs" "$DATA_DIR/cookies"
chmod 700 "$DATA_DIR/cookies"

install -m 755 "$SCRIPT_DIR/aria-dl" "$BIN_DIR/aria-dl"
cp "$SCRIPT_DIR/README.md" "$DATA_DIR/README.md"

if [ -w /usr/local/bin ]; then
  ln -sf "$BIN_DIR/aria-dl" /usr/local/bin/aria-dl
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    command -v aria2c >/dev/null 2>&1 || brew install aria2
    command -v yt-dlp >/dev/null 2>&1 || brew install yt-dlp
    command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
  else
    echo "Note: install aria2, yt-dlp, and ffmpeg if not already on PATH."
  fi

  mkdir -p "${HOME}/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.damomind.aria-dl</string>
  <key>ProgramArguments</key>
  <array>
    <string>${BIN_DIR}/aria-dl</string>
    <string>tick</string>
  </array>
  <key>StartInterval</key>
  <integer>900</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardErrorPath</key>
  <string>${DATA_DIR}/tick.err</string>
</dict>
</plist>
PLIST_EOF

  UID_NUM="$(id -u)"
  launchctl bootout "gui/${UID_NUM}" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
  echo "Installed LaunchAgent: com.damomind.aria-dl (runs aria-dl tick every 15 min)"
fi

echo "Installed aria-dl to ${BIN_DIR}/aria-dl"
