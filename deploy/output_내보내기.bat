@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==================================================
echo    output 내보내기 - 바뀐 파일만 작게 묶기 (D-243)
echo ==================================================
echo.
echo  만드는 것 : 내보내기\output_변경분_날짜_시각.zip  ^(지난 내보내기 뒤 바뀐 파일만^)
echo              내보내기\output_확인용_날짜_시각.zip  ^(실행 로그·정산 로그·결과 엑셀 - 작음^)
echo  * 앱·정산이 도는 중이면 만들지 않고 멈춥니다 ^(18:00 실행·정산이 끝난 뒤 다시^).
echo  * 비밀번호가 든 파일^(원장 백업 등^)은 넣지 않습니다. 정산 증빙은 넣습니다.
echo.

rem --- 폴더 찾기: 운용 PC = 이 bat 옆 output · 개발 저장소 = deploy\ 위 output
set "OUT=%~dp0output"
set "TOOLS=%~dp0"
if not exist "%OUT%" set "OUT=%~dp0..\output"
if not exist "%TOOLS%output_export.py" set "TOOLS=%~dp0..\tools\"
if not exist "%OUT%" (
  echo  [오류] output 폴더를 찾지 못했습니다. coupang-analytics 폴더에서 실행하세요.
  pause
  exit /b 1
)
if not exist "%TOOLS%output_export.py" (
  echo  [오류] output_export.py 가 이 폴더에 없습니다 ^(output_archive.py 와 함께 있어야 함^).
  pause
  exit /b 1
)

rem --- 파이썬 찾기 (py -3 먼저, 없으면 python)
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo  [오류] 이 PC 에 Python 이 없습니다 - 통제 세션에 알려 주세요.
  pause
  exit /b 1
)

rem --- 처음 한 번: 개발 PC 가 만든 기준본 기록이 bat 옆에 있으면 사용
set "FIRST="
if not exist "%OUT%\_내보내기기록.json" if exist "%~dp0_내보내기_기준기록.json" set "FIRST=--baseline-record "%~dp0_내보내기_기준기록.json""

echo  고르세요:
echo    1 = 변경분 + 확인용 ^(기본^)
echo    2 = 확인용만
echo    3 = 지난 달까지의 백업·로그를 output\보관\YYYY-MM 로 옮긴 뒤 변경분 + 확인용 ^(지우지 않음^)
echo    4 = 보관 이동 미리보기만 ^(아무것도 안 옮김^)
set "PICK=1"
set /p PICK= 번호 [1]:
echo.
if "%PICK%"=="2" %PY% "%TOOLS%output_export.py" --output "%OUT%" --only check
if "%PICK%"=="3" %PY% "%TOOLS%output_export.py" --output "%OUT%" --archive %FIRST%
if "%PICK%"=="4" %PY% "%TOOLS%output_archive.py" --output "%OUT%" --dry-run
if not "%PICK%"=="2" if not "%PICK%"=="3" if not "%PICK%"=="4" %PY% "%TOOLS%output_export.py" --output "%OUT%" %FIRST%
set "RC=%errorlevel%"
echo.
if "%RC%"=="3" echo  [멈춤] 앱·정산이 도는 중입니다 - 끝난 뒤 다시 실행하세요.
if "%RC%"=="2" echo  [처음] 기준본 기록 파일^(_내보내기_기준기록.json^)을 이 bat 옆에 두고 다시 실행하세요.
if "%RC%"=="0" if not "%PICK%"=="4" echo  [완료] 위에 적힌 zip 을 개발 PC 로 옮기세요.
pause
exit /b %RC%
