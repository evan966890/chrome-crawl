#!/bin/bash
# install.sh — One-click setup for chrome-crawl
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== chrome-crawl installer ==="
echo ""

# 1. Check dependencies
echo "Checking dependencies..."

# Node.js (for cdp_fetch.js)
if ! command -v node &>/dev/null; then
  echo "ERROR: Node.js not found. Install it first:"
  echo "  macOS:  brew install node"
  echo "  Linux:  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs"
  exit 1
fi
NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
if [[ "$NODE_VER" -lt 22 ]]; then
  echo "WARNING: Node.js v22+ recommended (native WebSocket). Current: $(node -v)"
fi

# Python 3
if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python 3 not found."
  exit 1
fi

# Chrome
if [[ "$OSTYPE" == darwin* ]]; then
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
else
  CHROME=$(command -v google-chrome || command -v google-chrome-stable || echo "")
fi
if [[ ! -f "$CHROME" ]] && [[ -z "$CHROME" ]]; then
  echo "WARNING: Google Chrome not found. Install it before using chrome-crawl."
fi

echo "  Node.js: $(node -v)"
echo "  Python:  $(python3 --version)"
echo "  Chrome:  ${CHROME:-not found}"
echo ""

# 2. Install Python dependencies
echo "Installing Python dependencies..."
pip3 install --break-system-packages -q beautifulsoup4 requests 2>/dev/null \
  || pip3 install --user -q beautifulsoup4 requests 2>/dev/null \
  || pip3 install -q beautifulsoup4 requests
echo "  Done."
echo ""

# 3. Make scripts executable
chmod +x "$SCRIPT_DIR/scripts/chrome_debug.sh"
chmod +x "$SCRIPT_DIR/scripts/batch_crawl.py"
chmod +x "$SCRIPT_DIR/scripts/wechat_extract.py"
chmod +x "$SCRIPT_DIR/scripts/feishu_upload.py"
chmod +x "$SCRIPT_DIR/scripts/ima_crawl.py"

# 4. Create convenience symlinks (optional)
mkdir -p "$HOME/.chrome-crawl"
if [[ ! -L "$HOME/.chrome-crawl/scripts" ]]; then
  ln -sf "$SCRIPT_DIR/scripts" "$HOME/.chrome-crawl/scripts"
  echo "Symlinked: ~/.chrome-crawl/scripts → $SCRIPT_DIR/scripts"
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Quick start:"
echo "  1. Close your normal Chrome, then launch debug Chrome:"
echo "     $SCRIPT_DIR/scripts/chrome_debug.sh"
echo ""
echo "  2. Crawl a single article:"
echo "     python3 $SCRIPT_DIR/scripts/batch_crawl.py crawl 'https://mp.weixin.qq.com/s/xxx' -o ./output/"
echo ""
echo "  3. Batch crawl from URL list:"
echo "     python3 $SCRIPT_DIR/scripts/batch_crawl.py crawl urls.txt -o ./output/"
echo ""
