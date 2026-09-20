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
echo [3/5] 설치·무인 예약 스크립트 복사...
copy /Y "%~dp0deploy\설치.bat" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\install.ps1" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\첫실행_설정안내.txt" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0deploy\라이브검증_안내.txt" "dist\쿠팡애널리틱스\" >nul
copy /Y "%~dp0INSTALL.md" "dist\쿠팡애널리틱스\" >nul
echo.
echo [4/5] 이 PC 설정(구글시트 링크·입력소스 + 네이버/OpenAI/구글SA 키) 패키지에 포함...
echo   * 새 PC에서 추가 입력 없이 쓰도록 담습니다. _설정값.json 은 평문이라 설치 시 자동 삭제됩니다.
"dist\쿠팡애널리틱스\쿠팡애널리틱스.exe" --export-settings "dist\쿠팡애널리틱스\_설정값.json"
if errorlevel 1 echo   [경고] 설정 내보내기 실패 - 새 PC에서 설정 탭에 직접 입력해야 합니다(빌드는 계속).
echo.
echo [5/5] 배포용 zip 압축...
del /Q "dist\쿠팡애널리틱스_배포.zip" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\쿠팡애널리틱스' -DestinationPath 'dist\쿠팡애널리틱스_배포.zip' -Force"
if errorlevel 1 goto :err
echo.
echo 완료!
echo   결과 폴더: dist\쿠팡애널리틱스\  (쿠팡애널리틱스.exe·쿠팡진단.exe·설치.bat·_설정값.json)
echo   배포 zip:  dist\쿠팡애널리틱스_배포.zip   ← 이 파일 하나만 새 PC로 보내세요.
echo.
echo   [새 PC에서] zip 압축 풀기 → "설치.bat" 더블클릭(관리자 권장) → 끝.
echo     설치.bat 이: 바로가기 생성 + 야간 무인 등록 + **설정 자동 적용(키 포함)** + 평문 설정파일 삭제.
echo     설정 탭에 아무것도 다시 입력할 필요 없음(구글SA·네이버·OpenAI·시트 링크 모두 이식됨).
echo   (실행 PC 에 Google Chrome 설치 필수)
echo   ⚠ _설정값.json·배포 zip 에는 API/SA 키가 평문으로 들어있으니 외부 공유·업로드 금지, 설치 후 삭제하세요.
echo.
pause
exit /b 0
:err
echo.
echo [오류] 빌드 실패 - 위 메시지를 확인하세요. (Python 설치 여부/인터넷 연결 확인)
pause
exit /b 1
