@echo off
REM MULAI-rekam.bat - jalankan aplikasi perekam.
REM Jalankan PASANG.bat lebih dulu kalau ini gagal.

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [GAGAL] ".venv" belum ada.
  echo Jalankan PASANG.bat lebih dulu.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\rekam.py
if errorlevel 1 (
  echo.
  echo [GAGAL] Aplikasi berhenti dengan error. Lihat pesan di atas.
  echo Salin pesan itu dan kirim ke whoever yang mengawal rekaman.
  echo.
  pause
)
