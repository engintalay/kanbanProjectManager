#!/usr/bin/env bash
# Migration çalıştır
set -euo pipefail
if [ -d .venv/bin ]; then
  source .venv/bin/activate
fi
exec python manage.py migrate "$@"
