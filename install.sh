#!/usr/bin/env bash
# Yerel kurulum: venv + bağımlılıklar + migration + seed admin
set -euo pipefail

if [ -f .env ]; then
  cp .env .env.local
fi

if [ ! -d .venv ]; then
  echo "[install] Sanal ortam oluşturuluyor..."
  python3 -m venv .venv
fi

if [ ! -d .venv/bin/activate ]; then
  source .venv/bin/activate
else
  echo "[install] .venv zaten mevcut, aktif ediliyor..."
  source .venv/bin/activate
fi

python -m pip install --upgrade pip

echo "[install] Bağımlılıklar kuruluyor..."
pip install -r requirements.txt

echo "[install] Migration çalışıyor..."
python manage.py migrate

echo "[install] Seed (rol + başlatıcı admin)..."
python manage.py seed_initial

echo "[install] Tamamlandı. Şimdi 'bash run.sh' ile çalıştır."
