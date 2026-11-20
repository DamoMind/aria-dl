#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
DATA_DIR="${HOME}/.local/share/aria-dl"
PLIST="${HOME}/Library/LaunchAgents/com.damomind.aria-dl.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DO_COOKIES=0
YOUTUBE_PROXY=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--youtube-proxy" ]; then
    YOUTUBE_PROXY="$arg"
    prev=""
    continue
  fi
  case "$arg" in
    --cookies) DO_COOKIES=1 ;;
    --youtube-proxy) prev="--youtube-proxy" ;;
    --youtube-proxy=*) YOUTUBE_PROXY="${arg#--youtube-proxy=}" ;;
  esac
done
if [ -n "$prev" ]; then
  echo "install.sh: --youtube-proxy needs a URL" >&2
  exit 1
fi

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
  <integer>60</integer>
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
  echo "Installed LaunchAgent: com.damomind.aria-dl (runs aria-dl tick every 60 seconds)"
fi

echo "Installed aria-dl to ${BIN_DIR}/aria-dl"
if [ -n "$YOUTUBE_PROXY" ]; then
  mkdir -p "$DATA_DIR"
  DATA_DIR="$DATA_DIR" YOUTUBE_PROXY="$YOUTUBE_PROXY" python3 - << 'PY'
import json, os
path = os.path.join(os.environ["DATA_DIR"], "config.json")
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, ValueError):
    data = {}
if not isinstance(data, dict):
    data = {}
data["youtube_proxy"] = os.environ["YOUTUBE_PROXY"]
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=1)
    fh.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
  echo "Set youtube_proxy for aria-dl downloads only (system proxy unchanged)."
fi
if [ "$DO_COOKIES" -eq 1 ]; then
  if [ "$(uname -s)" = "Darwin" ]; then
    "$BIN_DIR/aria-dl" cookies refresh
  else
    echo "Note: --cookies runs the browser import on macOS. Use 'aria-dl cookies refresh' here if you still want it."
  fi
fi
