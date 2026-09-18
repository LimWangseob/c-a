@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   쿠팡 애널리틱스 - EXE 빌드
echo ============================================
echo.
echo [1/3] 필요 패키지 설치...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :err
echo.
echo [2/3] EXE 빌드(PyInstaller)...
python -m PyInstaller --noconfirm coupang_analytics.spec
if errorlevel 1 goto :err
echo.
echo [3/3] 설치·무인 예약 스크립트 복사...
copy /Y "%~dp0deploy\설치.bat" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\설치.ps1" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\install_schedule.bat" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\install_schedule.ps1" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\uninstall_schedule.bat" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\uninstall_schedule.ps1" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\첫실행_설정안내.txt" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0INSTALL.md" "dist\쿠팡애널리틱스\" >nul
echo.
echo 완료!
echo   결과: dist\쿠팡애널리틱스\쿠팡애널리틱스.exe
echo   이 "쿠팡애널리틱스" 폴더 전체를 다른 PC로 복사해서 쓰세요.
echo   (실행 PC 에 Google Chrome 설치 필수)
echo   설치(바로가기 생성 등): 그 폴더의 설치.bat 실행
echo   무인 야간 실행: 설치.bat 에서 등록하거나 install_schedule.bat 실행(매일 18:00, 06:00 종료)
echo.
pause
exit /b 0
:err
echo.
echo [오류] 빌드 실패 - 위 메시지를 확인하세요. (Python 설치 여부/인터넷 연결 확인)
pause
exit /b 1
