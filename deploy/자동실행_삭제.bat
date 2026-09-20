@echo off
cd /d "%~dp0"
echo === Coupang Analytics - Remove Auto Run ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0remove_autorun.ps1"
echo.
echo (If you see a permission error, right-click this file - Run as administrator.)
pause
