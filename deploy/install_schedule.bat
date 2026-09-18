@echo off
cd /d "%~dp0"
echo === Register nightly unattended run (18:00 start, 06:00 stop) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_schedule.ps1"
echo.
echo (If you see a permission error, right-click this file - Run as administrator.)
pause
