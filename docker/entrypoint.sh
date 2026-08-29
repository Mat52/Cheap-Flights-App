#!/bin/bash
set -e

cd /app
echo "🚀 Uruchamiam aplikację webową (http://0.0.0.0:${PORT:-5000})..."
exec python3 webapp.py
