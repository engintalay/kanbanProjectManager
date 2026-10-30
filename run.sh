#!/usr/bin/env bash
# Geliştirici sunucusu çalıştır
set -euo pipefail

if [ -d .venv/bin ]; then
  source .venv/bin/activate
fi

PORT="${PORT:-8000}"
# Not: 404 logger'ı X-Forwarded-For header'ını zaten okur (run.sh'a ek bayrak gerekmez)
exec python manage.py runserver 0.0.0.0:"$PORT"
