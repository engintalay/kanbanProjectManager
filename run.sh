#!/usr/bin/env bash
# Geliştirici sunucusu çalıştır
set -euo pipefail

if [ -d .venv/bin ]; then
  source .venv/bin/activate
fi

PORT="${PORT:-8000}"
exec python manage.py runserver 0.0.0.0:"$PORT"
