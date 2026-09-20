@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Coupang Analytics - Install ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
echo (If you see a permission error, right-click this file - Run as administrator.)
pause
