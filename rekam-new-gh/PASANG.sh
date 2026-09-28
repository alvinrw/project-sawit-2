#!/usr/bin/env bash
# PASANG.sh - sekali jalan: cek Python, buat virtual env, pasang pyserial.
# Jalankan:  bash PASANG.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================"
echo " PASANG - Rekam Sawit"
echo "============================================"
echo

# --- 1. Cari Python 3 ---
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "[GAGAL] Python 3.10 atau lebih baru tidak ditemukan."
  echo
  echo "  Ubuntu/Debian : sudo apt update && sudo apt install python3 python3-venv python3-tk"
  echo "  Fedora/RHEL   : sudo dnf install python3 python3-tkinter"
  echo "  lalu jalankan ulang: bash PASANG.sh"
  echo
  exit 1
fi
echo "[OK] Python: $PY"
"$PY" -c 'import sys; print("     versi", sys.version.split()[0])'
echo

# --- 2. Virtual environment ---
if [ ! -d ".venv" ]; then
  echo "[1/2] Membuat virtual environment .venv ..."
  "$PY" -m venv .venv
else
  echo "[OK] Virtual environment sudah ada."
fi
echo

# --- 3. pyserial ---
echo "[2/2] Memasang pyserial (butuh internet) ..."
if ! .venv/bin/python -m pip install --upgrade pip --quiet; then
  echo "  (pip upgrade dilewati, lanjut pasang pyserial)"
fi
.venv/bin/python -m pip install pyserial
echo

# --- 4. Verifikasi ---
echo "[OK] Memeriksa instalasi ..."
if ! .venv/bin/python -c 'import serial, tkinter; print("     pyserial", serial.__version__); print("     tkinter OK")'; then
  echo
  echo "[GAGAL] tkinter belum ada. Di Ubuntu/Debian: sudo apt install python3-tk"
  echo "        lalu jalankan ulang: bash PASANG.sh"
  echo
  exit 1
fi

# --- 5. Struktur folder rekaman ---
mkdir -p data/raw_audio data/controls data/pilot_test metadata/captures
echo "[OK] Folder rekaman siap."

echo
echo "============================================"
echo " SELESAI. Untuk merekam: bash MULAI-rekam.sh"
echo "============================================"
echo
echo "Baca dulu BACA-DULU.md sebelum mulai merekam."
echo
