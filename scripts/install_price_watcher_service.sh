#!/bin/bash
# Installs price_watcher.py as a macOS LaunchAgent so it starts on login,
# restarts itself if it crashes, and keeps running in the background
# without a terminal window open — the closest thing to "24/7" a personal
# Mac can offer. See the caveat in the printed output before relying on it.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_DIR/app"
VENV_PYTHON="$REPO_DIR/venv/bin/python"
LABEL="com.cheapflights.pricewatcher"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/cheap-flights-price-watcher"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "❌ Nie znaleziono $VENV_PYTHON — najpierw utwórz venv i zainstaluj zależności (patrz README)." >&2
  exit 1
fi
if [ ! -f "$APP_DIR/watchlist.json" ]; then
  echo "⚠️ Brak $APP_DIR/watchlist.json — skopiuj watchlist.example.json i dodaj swoje loty, zanim uruchomisz usługę:"
  echo "   cp \"$APP_DIR/watchlist.example.json\" \"$APP_DIR/watchlist.json\""
  exit 1
fi

mkdir -p "$LOG_DIR"

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>$APP_DIR/price_watcher.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$APP_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/price_watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/price_watcher.error.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "✅ Zainstalowano i uruchomiono $LABEL"
echo "   Logi:          tail -f \"$LOG_DIR/price_watcher.log\""
echo "   Zatrzymanie:    scripts/uninstall_price_watcher_service.sh"
echo "   Status:         launchctl list | grep $LABEL"
echo
echo "⚠️  To jest LaunchAgent (nie LaunchDaemon) — działa tylko, gdy jesteś"
echo "   zalogowany/a i Mac nie śpi. Prawdziwe 24/7 wymaga wyłączenia"
echo "   usypiania (Ustawienia > Bateria/Energia) albo docelowo przeniesienia"
echo "   tego na osobny, zawsze włączony serwer/VPS."
