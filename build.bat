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
echo [3/5] 설치·무인 예약 스크립트 복사(코드 폴더 안)...
copy /Y "%~dp0deploy\설치.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\install.ps1" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\0_먼저실행_보안제외.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\0_먼저실행_보안제외.bat" "dist\" >nul
rem ⚠ Defender 오탐(미서명 PyInstaller exe) 대비 — 압축 전에 실행할 '보안 제외' 스크립트를 zip 루트에도 둔다.
copy /Y "%~dp0deploy\자동실행_삭제.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\remove_autorun.ps1" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\첫실행_설정안내.txt" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\라이브검증_안내.txt" "dist\coupang-analytics\" >nul
copy /Y "%~dp0INSTALL.md" "dist\coupang-analytics\" >nul
echo.
echo [4/5] 이 PC 설정(구글시트 링크·입력소스 + 네이버/OpenAI/구글SA 키) 패키지에 포함...
echo   * 새 PC에서 추가 입력 없이 쓰도록 담습니다. _설정값.json 은 평문이라 설치 시 자동 삭제됩니다.
"dist\coupang-analytics\쿠팡애널리틱스.exe" --export-settings "dist\coupang-analytics\_설정값.json"
if errorlevel 1 echo   [경고] 설정 내보내기 실패 - 새 PC에서 설정 탭에 직접 입력해야 합니다(빌드는 계속).
echo.
echo [4.5/5] 노트북 통계 마스터를 씨앗으로 동봉(새 PC **첫 설치 시에만** 복사·업데이트는 기존 보존)...
if exist "%~dp0output\쿠팡데이타분석_통계.xlsx" (
  if not exist "dist\coupang-analytics\_씨앗" mkdir "dist\coupang-analytics\_씨앗"
  copy /Y "%~dp0output\쿠팡데이타분석_통계.xlsx" "dist\coupang-analytics\_씨앗\" >nul
  echo   [확인] 통계 마스터 씨앗 동봉(노트북 것) — 새 PC가 구글시트 복원 없이 이 마스터로 시작
) else (
  echo   [건너뜀] 노트북에 마스터 없음 — 씨앗 없이 배포(새 PC는 구글시트 복원 또는 수동 복사)
)
rem ⚠ 순위 크롬 프로필(data\chrome-pipeline)은 캐시 포함 수백MB라 zip 동봉 안 함(신뢰쿠키 교차이전도 제한적).
rem    운용 PC는 자기 data 폴더(휴지통 복원 등)를 쓰거나, 야간 실행으로 프로필이 스스로 warm 된다.
echo.
echo [5/5] 배포용 zip 압축(폴더째 — 개발·운용 폴더명 동일: coupang-analytics)...
del /Q "dist\쿠팡애널리틱스_배포.zip" 2>nul
rem zip 루트에 '0_먼저실행_보안제외.bat' 을 함께 넣는다(압축 풀기 전 관리자로 실행 → Defender 오탐 삭제 방지).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\coupang-analytics','dist\0_먼저실행_보안제외.bat' -DestinationPath 'dist\쿠팡애널리틱스_배포.zip' -Force"
if errorlevel 1 goto :err
echo.
echo 완료!
echo   결과 폴더: dist\coupang-analytics\  (쿠팡애널리틱스.exe·쿠팡진단.exe·설치.bat·_설정값.json)
echo   배포 zip:  dist\쿠팡애널리틱스_배포.zip   ← 이 파일 하나만 새 PC로 보내세요(폴더명=coupang-analytics, 노트북과 동일).
echo.
echo   [새 PC · 처음] zip 풀기 → coupang-analytics\ 안의 "설치.bat" 더블클릭(관리자 권장) → 끝.
echo     설치가 같은 폴더에 output·data·config.json(**삭제 금지·보존**) 생성 + 바로가기·야간무인 + 설정 자동적용.
echo   [새 PC · 업데이트] 새 zip 의 coupang-analytics\ 를 **같은 폴더에 덮어쓰기**만.
echo     output·data·config.json 은 zip 에 없으니 덮어써도 그대로 보존됩니다(마스터·크롬 프로필·설정 유지).
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
