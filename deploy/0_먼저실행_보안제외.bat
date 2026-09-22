@echo off
chcp 65001 >nul
title 쿠팡애널리틱스 - 보안 검사 제외(먼저 실행)
REM ============================================================
REM  ⚠ 압축을 풀기 "전에" 이 파일을 관리자 권한으로 먼저 실행하세요.
REM  이유: 우리 exe 는 PyInstaller 로 만든 미서명 실행파일이라 Windows
REM        Defender 가 "오탐(가짜 위험·이름 끝 !ml)"으로 자동 삭제합니다.
REM        실제 바이러스가 아니라, 서명이 없어 Defender 가 의심하는 것입니다.
REM  이 스크립트가 설치 폴더를 Defender 검사에서 제외해 삭제를 막습니다.
REM ============================================================
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [!] 관리자 권한이 필요합니다.
  echo       이 파일을 마우스 오른쪽 클릭 → "관리자 권한으로 실행" 하세요.
  echo.
  pause
  exit /b 1
)
set "HERE=%~dp0"
echo.
echo   Windows Defender 검사 제외를 추가합니다...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionPath 'C:\coupang-analytics'; Add-MpPreference -ExclusionPath (Join-Path '%HERE%' 'coupang-analytics'); Add-MpPreference -ExclusionPath '%HERE%'"
echo.
echo   [OK] 검사 제외 추가 완료:
echo        - C:\coupang-analytics
echo        - %HERE%coupang-analytics
echo.
echo   이제 '쿠팡애널리틱스_배포.zip' 안의 coupang-analytics 폴더를
echo   C:\coupang-analytics 가 되도록 압축을 푸세요(이미 풀어 exe 가 지워졌으면 한 번 더 푸세요).
echo   그다음 coupang-analytics 폴더 안의 "설치.bat" 을 관리자 권한으로 실행하면 끝입니다.
echo.
pause
