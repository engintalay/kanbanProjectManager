#!/usr/bin/env bash
# Geliştirici sunucusu çalıştır
set -euo pipefail

if [ -d .venv/bin ]; then
  source .venv/bin/activate
fi

PORT="${PORT:-8000}"
# --use-x-forwarded-for: nginx arkasındaysken gerçek istemci IP'sini loglar
exec python manage.py runserver 0.0.0.0:"$PORT" --use-x-forwarded-for
