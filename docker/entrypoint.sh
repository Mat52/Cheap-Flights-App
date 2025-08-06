#!/bin/bash
set -e

# Czyszczenie starych plików locka (na wypadek crashu Xvfb)
if [ -f /tmp/.X99-lock ]; then
    echo "⚠️ Usuwam stary plik locka: /tmp/.X99-lock"
    rm -f /tmp/.X99-lock
fi

if [ -S /tmp/.X11-unix/X99 ]; then
    echo "⚠️ Usuwam stary socket X11: /tmp/.X11-unix/X99"
    rm -f /tmp/.X11-unix/X99
fi

# Uruchamianie Xvfb tylko jeśli nie działa
if pgrep Xvfb > /dev/null; then
    echo "✅ Xvfb już działa — pomijam uruchamianie"
else
    Xvfb :99 -screen 0 1920x1080x24 &
fi

export DISPLAY=:99
# Przejście do katalogu aplikacji i uruchomienie scraper'a
cd /app
echo "🛫 Uruchamiam scraper lotów..."
python3 main.py