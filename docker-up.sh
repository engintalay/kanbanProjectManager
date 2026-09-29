#!/usr/bin/env bash
# Docker ile başlat (build + up)
set -euo pipefail

echo "[docker] Build + başlatılıyor..."
if [ "${1:-}" = "--build" ]; then
  docker compose up --build -d
else
  docker compose up -d
fi

echo
echo "[docker] Uygulama çalışıyor:"
echo "  Nginx:  http://<lan-ip>:${NGINX_PORT:-8008}/"
echo "  Web:    http://<lan-ip>:${WEB_PORT:-8000}/"
echo
echo "[docker] Admin giriş: http://localhost:8008/admin/"
