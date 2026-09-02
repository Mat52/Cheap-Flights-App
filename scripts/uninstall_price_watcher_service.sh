#!/bin/bash
# Stops and removes the price_watcher LaunchAgent installed by
# install_price_watcher_service.sh. Does not touch watchlist.json or any
# Postgres data — just the background service registration.
set -euo pipefail

LABEL="com.cheapflights.pricewatcher"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PLIST_PATH" ]; then
  echo "ℹ️ $PLIST_PATH nie istnieje — usługa nie jest zainstalowana."
  exit 0
fi

launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"
echo "✅ Zatrzymano i odinstalowano $LABEL"
