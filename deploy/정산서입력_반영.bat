@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==================================================
echo    정산서 입력 반영 - 개발 PC 가 만든 정산서입력_YYMMDD.zip 을 더하기만
echo ==================================================
echo.
echo  넣는 곳 : output\정산서\입력\  ^(셀독 판정표 = output\정산서\입력_셀독\^)
echo  * 지우는 파일 없음. 같은 이름 파일이 이미 있으면 덮기 전에
echo    output\정산서\입력\보관\날짜_시각\ 으로 옮깁니다 ^(내용이 같으면 그대로 둠^).
echo  * 받은 zip 의 풀린 사본도 같은 보관 폴더의 받은묶음\ 에 남깁니다.
echo  사용법 : zip 을 이 bat 위에 끌어다 놓거나, zip 을 이 bat 옆에 두고 실행 ^(가장 최근 이름^).
echo.

rem --- 폴더 찾기: 운용 PC = 이 bat 옆 output · 개발 저장소 = deploy\ 위 output
set "OUTDIR=%~dp0output"
if not exist "%OUTDIR%" set "OUTDIR=%~dp0..\output"
if not exist "%OUTDIR%" (
  echo  [오류] output 폴더를 찾지 못했습니다. coupang-analytics 폴더에서 실행하세요.
  pause
  exit /b 1
)
if not exist "%~dp0inputs_apply.ps1" (
  echo  [오류] inputs_apply.ps1 이 이 파일 옆에 없습니다.
  pause
  exit /b 1
)
rem --- 다른 PowerShell(7) 의 모듈 경로가 섞이지 않게(Windows PowerShell 기본 경로로)
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0inputs_apply.ps1" -OutDir "%OUTDIR%" -Zip "%~1" -Here "%~dp0."
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo  [완료] 반영했습니다.) else (echo  [실패] 위 안내를 확인하세요 - 아무것도 지우지 않았습니다.)
pause
exit /b %RC%
