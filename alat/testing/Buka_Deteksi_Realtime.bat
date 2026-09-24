@echo off
cd /d "%~dp0"
python deteksi_realtime.py
if errorlevel 1 pause
