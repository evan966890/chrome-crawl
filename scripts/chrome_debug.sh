#!/bin/bash
# chrome_debug.sh — Launch Chrome with remote debugging, reusing local cookies
#
# Chrome disallows remote debugging on the default profile, so we copy
# cookies to an isolated debug profile.
#
# Usage: chrome_debug.sh [port]   (default 9222)
# Note:  Close your normal Chrome first (or cookies DB may be locked)

set -euo pipefail

PORT="${1:-9222}"

# --- Detect Chrome path ---
if [[ "$OSTYPE" == darwin* ]]; then
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  SOURCE_PROFILE="$HOME/Library/Application Support/Google/Chrome"
elif [[ -f "/usr/bin/google-chrome" ]]; then
  CHROME="/usr/bin/google-chrome"
  SOURCE_PROFILE="$HOME/.config/google-chrome"
elif [[ -f "/usr/bin/google-chrome-stable" ]]; then
  CHROME="/usr/bin/google-chrome-stable"
  SOURCE_PROFILE="$HOME/.config/google-chrome"
else
  echo "ERROR: Chrome not found. Install Google Chrome first."
  exit 1
fi

DEBUG_PROFILE="$HOME/.chrome-crawl/debug-profile"
PORT_FILE="$HOME/.chrome-crawl/cdp-port"
mkdir -p "$HOME/.chrome-crawl"

# --- Detect system proxy (macOS) ---
PROXY="${ALL_PROXY:-${https_proxy:-}}"
if [[ -z "$PROXY" ]] && [[ "$OSTYPE" == darwin* ]]; then
  PROXY_HOST=$(networksetup -getsecurewebproxy Wi-Fi 2>/dev/null | awk '/^Server:/{print $2}')
  PROXY_PORT=$(networksetup -getsecurewebproxy Wi-Fi 2>/dev/null | awk '/^Port:/{print $2}')
  if [[ -n "$PROXY_HOST" ]] && [[ "$PROXY_HOST" != "(null)" ]]; then
    PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
  fi
fi

# --- Check Chrome exists ---
if [[ ! -f "$CHROME" ]]; then
  echo "ERROR: Chrome binary not found at $CHROME"
  exit 1
fi

# --- Handle port conflict ---
while lsof -i :"$PORT" >/dev/null 2>&1; do
  echo "Port $PORT in use, trying next..."
  PORT=$((PORT + 1))
  [[ "$PORT" -gt 9250 ]] && echo "ERROR: No available port" && exit 1
done

# --- Kill existing debug Chrome ---
if pgrep -f "chrome-crawl/debug-profile" >/dev/null 2>&1; then
  echo "Stopping existing debug Chrome..."
  pkill -f "chrome-crawl/debug-profile" 2>/dev/null || true
  sleep 2
fi

# --- Sync cookies ---
mkdir -p "$DEBUG_PROFILE/Default"
echo "Syncing cookies from Chrome profile..."
for f in Cookies "Cookies-journal"; do
  src="$SOURCE_PROFILE/Default/$f"
  [[ -f "$src" ]] && cp -f "$src" "$DEBUG_PROFILE/Default/$f" 2>/dev/null || true
done
[[ -f "$SOURCE_PROFILE/Local State" ]] && cp -f "$SOURCE_PROFILE/Local State" "$DEBUG_PROFILE/Local State" 2>/dev/null || true

# --- Build launch args ---
ARGS=(
  --remote-debugging-port="$PORT"
  --user-data-dir="$DEBUG_PROFILE"
  --no-first-run
  --no-default-browser-check
  --disable-background-timer-throttling
  --disable-backgrounding-occluded-windows
  --disable-renderer-backgrounding
)

if [[ -n "${PROXY:-}" ]]; then
  ARGS+=(--proxy-server="$PROXY")
  echo "Using proxy: $PROXY"
fi

# --- Launch ---
echo "Launching Chrome debug on port $PORT..."
"$CHROME" "${ARGS[@]}" &>/dev/null &
CHROME_PID=$!

# --- Wait for CDP ---
for i in $(seq 1 20); do
  if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "Chrome ready! CDP port=$PORT PID=$CHROME_PID"
    echo "$PORT" > "$PORT_FILE"
    exit 0
  fi
  sleep 1
done

echo "ERROR: CDP failed to start within 20s"
kill "$CHROME_PID" 2>/dev/null
exit 1
