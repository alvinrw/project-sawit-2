@echo off
cd /d "%~dp0"
python gui_recorder.py
if errorlevel 1 pause
