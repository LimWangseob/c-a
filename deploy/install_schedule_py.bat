@echo off
chcp 65001 >nul
REM === Register scheduler tasks (python source method) ===
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

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_schedule_py.ps1" "%~dp0.."
echo.
pause
