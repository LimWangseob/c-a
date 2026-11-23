@echo off
chcp 65001 >nul
setlocal
rem 업데이트 - 새 배포 zip 을 임시 폴더에 푼 뒤 이 파일만 더블클릭(소유자 11-23: 정산 프로그램 강제 종료 없이 배포).
rem   실행 중인 앱·정산 프로그램을 멈춤 -> 설치 폴더에 덮어쓰기(output·data·config.json 보존) -> 설치(예약 작업) -> 정산 이어서.
rem   zip 루트(coupang-analytics 폴더 옆)와 coupang-analytics 안 둘 다 같은 내용 - 새 폴더를 스스로 찾는다.
net session >nul 2>&1
if errorlevel 1 goto :elevate
set "SRC=%~dp0"
if exist "%~dp0coupang-analytics\update.ps1" set "SRC=%~dp0coupang-analytics\"
if not exist "%SRC%update.ps1" goto :noscript
echo === 쿠팡 애널리틱스 - 업데이트 ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%update.ps1" -Source "%SRC:~0,-1%"
echo.
pause
exit /b 0

:elevate
echo 관리자 권한이 필요합니다 - 확인 창이 뜨면 '예'를 눌러 주세요.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
if errorlevel 1 (
  echo [취소] 관리자 권한을 받지 못했습니다. 이 파일을 우클릭 - 관리자 권한으로 실행 하세요.
  pause
)
exit /b 0

:noscript
echo [오류] update.ps1 을 찾지 못했습니다. 새 zip 을 푼 폴더에서 실행하세요: %~dp0
pause
exit /b 1
