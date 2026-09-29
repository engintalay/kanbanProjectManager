#!/usr/bin/env bash
# Docker kurulumu: .env oluştur + ENCRYPTION_KEY üret
set -euo pipefail

# venv varsa aktif et
if [ -d .venv/bin ]; then
  source .venv/bin/activate
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi

# Şifre şifreleme anahtarı (Fernet) — boş ise doldur, değilse üret
KEY_VALUE="$(grep -E '^ENCRYPTION_KEY=' .env | awk '{print $2}')"
if [ -z "$KEY_VALUE" ]; then
  echo "[docker] ENCRYPTION_KEY üretiliyor..."
  NEW_KEY="$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
  sed -ri "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${NEW_KEY}|" .env
  echo "[docker] ENCRYPTION_KEY .env'e dolduruldu. Bu değeri asla git'e yüklemeyin."
else
  echo "[docker] ENCRYPTION_KEY zaten mevcut."
fi

echo "[docker] Hazır. Şimdi 'bash docker-up.sh' ile başlat."
