@echo off
chcp 65001 >nul
echo === 매일 18:00 무인 실행 예약 등록 ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_schedule.ps1"
echo.
echo (권한 오류가 나면 이 파일을 마우스 우클릭 - 관리자 권한으로 실행)
pause
