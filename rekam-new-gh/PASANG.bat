@echo off
REM PASANG.bat - sekali jalan: cek Python, buat virtual env, pasang pyserial.
REM Jalankan file ini dengan klik ganda. Tutup jendela ini kalau selesai.

setlocal
cd /d "%~dp0"
title PASANG - Rekam Sawit

echo ============================================
echo  PASANG - Rekam Sawit
echo ============================================
echo.

REM --- 1. Cari Python ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [GAGAL] Python tidak ditemukan.
  echo.
  echo Pasang Python 3.10 atau lebih baru dari https://www.python.org/downloads/
  echo WAJIB centang "Add Python to PATH" saat instalasi.
  echo.
  pause
  exit /b 1
)
echo [OK] Python: %PY%
%PY% -c "import sys; print('     versi', sys.version.split()[0])"
echo.

REM --- 2. Virtual environment ---
if not exist ".venv" (
  echo [1/2] Membuat virtual environment .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [GAGAL] Gagal membuat virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [OK] Virtual environment sudah ada.
)
echo.

REM --- 3. pyserial ---
echo [2/2] Memasang pyserial (butuh internet) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install pyserial
if errorlevel 1 (
  echo.
  echo [GAGAL] Gagal memasang pyserial. Periksa koneksi internet lalu ulangi.
  pause
  exit /b 1
)
echo.

REM --- 4. Verifikasi ---
echo [OK] Memeriksa instalasi ...
".venv\Scripts\python.exe" -c "import serial, tkinter; print('     pyserial', serial.__version__); print('     tkinter OK')"
if errorlevel 1 (
  echo.
  echo [GAGAL] Ada yang belum lengkap. Yakini Python terpasang dengan tkinter.
  echo Di Windows, pilih "tcl/tk and IDLE" saat instalasi Python.
  pause
  exit /b 1
)

REM --- 5. Struktur folder rekaman ---
if not exist "data\raw_audio" mkdir "data\raw_audio"
if not exist "data\controls" mkdir "data\controls"
if not exist "data\pilot_test" mkdir "data\pilot_test"
if not exist "metadata\captures" mkdir "metadata\captures"
echo [OK] Folder rekaman siap.

echo.
echo ============================================
echo  SELESAI. Untuk merekam, klik MULAI-rekam.bat
echo ============================================
echo.
echo Baca dulu BACA-DULU.md sebelum mulai merekam.
echo.
pause
