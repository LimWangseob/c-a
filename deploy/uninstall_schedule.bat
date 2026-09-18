@echo off
cd /d "%~dp0"
REM === Unregister scheduler tasks (nightly + reboot-resume) ===
REM Usage: right-click this file - "Run as administrator"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo [ERROR] Administrator rights required.
  echo         Right-click this file and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_schedule.ps1"
echo.
pause
