#!/usr/bin/env bash
# MULAI-rekam.sh - jalankan aplikasi perekam.
# Jalankan PASANG.sh lebih dulu kalau ini gagal.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "[GAGAL] .venv belum ada. Jalankan: bash PASANG.sh"
  echo
  exit 1
fi

exec .venv/bin/python scripts/rekam.py
