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
rem 업데이트(배포 때 정산 강제 종료 없이 — 소유자 11-23) = 새 zip 을 임시 폴더에 풀고 zip 루트 '업데이트.bat' 만 실행(앱·정산 멈춤 → 덮어쓰기 → 설치 → 이어서).
copy /Y "%~dp0deploy\업데이트.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\업데이트.bat" "dist\" >nul
copy /Y "%~dp0deploy\update.ps1" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\자동실행_삭제.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\remove_autorun.ps1" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\첫실행_설정안내.txt" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\라이브검증_안내.txt" "dist\coupang-analytics\" >nul
copy /Y "%~dp0INSTALL.md" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\정산_상태확인.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\정산증빙_전체받기.bat" "dist\coupang-analytics\" >nul
rem 정산서입력_반영.bat = 개발 PC 가 만든 정산서입력_YYMMDD.zip 을 output\정산서\입력\ 에 더하기만(지우기 없음 · D-399 계획 6).
copy /Y "%~dp0deploy\정산서입력_반영.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0deploy\inputs_apply.ps1" "dist\coupang-analytics\" >nul
rem output 내보내기(D-243 ①②) = bat + 표준 라이브러리만 쓰는 .py 2개(운용 PC py -3) · 기준본 기록은 개발 PC output 에 있을 때만(처음 1회용).
copy /Y "%~dp0deploy\output_내보내기.bat" "dist\coupang-analytics\" >nul
copy /Y "%~dp0tools\output_export.py" "dist\coupang-analytics\" >nul
copy /Y "%~dp0tools\output_archive.py" "dist\coupang-analytics\" >nul
if exist "%~dp0output\_내보내기_기준기록.json" copy /Y "%~dp0output\_내보내기_기준기록.json" "dist\coupang-analytics\" >nul
rem 정산 다운로드는 예약작업 없음(D-010): 00:10 앱이 ①판매수집 뒤 정산다운로드.exe watch 를 띄우고 다 받으면 종료.
rem 정산_상태확인.bat = 창 없는 정산 자동 다운로드의 '지금 상태'를 더블클릭으로 보는 모니터링 창(사람용).
echo.
echo [4/5] 이 PC 설정(구글시트 링크·입력소스 + 네이버/OpenAI/구글SA 키) 패키지에 포함...
echo   * 새 PC에서 추가 입력 없이 쓰도록 담습니다. _설정값.json 은 평문이라 설치 시 자동 삭제됩니다.
rem 설정 읽는 곳 = 이 저장소의 config.json(보존 폴더) — 안 주면 dist 안 exe 폴더 기준이라 config.json 이 없어 레지스트리만 읽고,
rem 레지스트리에 없는 키(셀독 계약자별 상품 현황 링크 contractor/url·재고현황 stock/url)가 빠졌다(R242 실측).
set "COUPANG_DATA_ROOT=%~dp0"
"dist\coupang-analytics\쿠팡애널리틱스.exe" --export-settings "dist\coupang-analytics\_설정값.json"
if errorlevel 1 echo   [경고] 설정 내보내기 실패 - 새 PC에서 설정 탭에 직접 입력해야 합니다(빌드는 계속).
set "COUPANG_DATA_ROOT="
echo.
echo [4.5/5] 노트북 통계 마스터를 씨앗으로 동봉(새 PC **첫 설치 시에만** 복사·업데이트는 기존 보존)...
if exist "%~dp0output\쿠팡데이타분석_통계.xlsx" (
  if not exist "dist\coupang-analytics\_씨앗" mkdir "dist\coupang-analytics\_씨앗"
  copy /Y "%~dp0output\쿠팡데이타분석_통계.xlsx" "dist\coupang-analytics\_씨앗\" >nul
  echo   [확인] 통계 마스터 씨앗 동봉^(노트북 것^) — 새 PC가 구글시트 복원 없이 이 마스터로 시작
) else (
  echo   [건너뜀] 노트북에 마스터 없음 — 씨앗 없이 배포^(새 PC는 구글시트 복원 또는 수동 복사^)
)
rem ⚠ 순위 크롬 프로필(data\chrome-pipeline)은 캐시 포함 수백MB라 zip 동봉 안 함(신뢰쿠키 교차이전도 제한적).
rem    운용 PC는 자기 data 폴더(휴지통 복원 등)를 쓰거나, 야간 실행으로 프로필이 스스로 warm 된다.
echo.
echo [4.6/5] 이 노트북에서 검증한 config.json·proxies.txt 를 씨앗으로 동봉(새 PC **첫 설치 시에만** 복사·업데이트는 보존)...
if not exist "dist\coupang-analytics\_씨앗" mkdir "dist\coupang-analytics\_씨앗"
if exist "%~dp0config.json" (
  copy /Y "%~dp0config.json" "dist\coupang-analytics\_씨앗\config.json" >nul
  echo   [확인] config.json 씨앗 동봉^(검증된 구글시트 링크4·입력소스·순위간격·프록시 토글 전부^) — 운용 PC는 복사만
) else (
  echo   [건너뜀] 노트북에 config.json 없음 — 운용 PC는 _설정값.json 에서 링크만 복원^(프록시 토글 누락 가능^)
)
if exist "%~dp0proxies.txt" (
  copy /Y "%~dp0proxies.txt" "dist\coupang-analytics\_씨앗\proxies.txt" >nul
  echo   [확인] proxies.txt 씨앗 동봉^(노출순위 프록시 자격증명^) — 첫 설치 때 복사되어 프록시가 바로 동작
  echo   ⚠ proxies.txt 는 자격증명이라 zip 은 외부 공유·업로드 금지^(API/SA 키와 동일 취급·설치 후 안전 보관^)
) else (
  echo   [건너뜀] 노트북에 proxies.txt 없음 — 프록시 ON 이어도 운용 PC에 파일 없으면 순위 스킵^(fail-closed^)
)
echo.
echo [4.7/5] 정산서 입력 묶음(업데이트.bat 이 output\정산서\ 에 더함 · 평문 비밀번호 없음 검사)...
del /Q "dist\정산서입력_*.zip" 2>nul
python tools\statement_inputs_pack.py --strict --dest dist
if errorlevel 1 goto :err
echo.
echo [5/5] 배포용 zip 압축(폴더째 — 개발·운용 폴더명 동일: coupang-analytics)...
del /Q "dist\쿠팡애널리틱스_배포.zip" 2>nul
rem zip 루트에 '0_먼저실행_보안제외.bat' 을 함께 넣는다(압축 풀기 전 관리자로 실행 → Defender 오탐 삭제 방지).
powershell -NoProfile -ExecutionPolicy Bypass -Command "$in = @(Get-ChildItem 'dist\정산서입력_*.zip' | ForEach-Object FullName); if ($in.Count -ne 1) { throw '정산서 입력 묶음이 1개가 아님' }; Compress-Archive -Path (@('dist\coupang-analytics','dist\0_먼저실행_보안제외.bat','dist\업데이트.bat') + $in) -DestinationPath 'dist\쿠팡애널리틱스_배포.zip' -Force"
if errorlevel 1 goto :err
echo.
echo 완료!
echo   결과 폴더: dist\coupang-analytics\  (쿠팡애널리틱스.exe·쿠팡진단.exe·정산다운로드.exe·설치.bat·_설정값.json)
echo   ※ 정산 자동 다운로드 계정·비번 = 설정 탭 원장 링크의 셀독계정상품이력관리원장(D-103) — 링크가 틀리거나 원장이 26시간 넘게 안 갱신되면 정산 중단.
echo   배포 zip:  dist\쿠팡애널리틱스_배포.zip   ← 이 파일 하나만 새 PC로 보내세요(폴더명=coupang-analytics, 노트북과 동일).
echo.
echo   [새 PC · 처음] zip 풀기 → coupang-analytics\ 안의 "설치.bat" 더블클릭(관리자 권장) → 끝.
echo     설치가 _씨앗\의 검증된 config.json·proxies.txt·통계마스터를 같은 폴더로 복사(첫 설치만) + 키 암호화이식
echo     + 바로가기·야간무인 등록. 설정 탭에 다시 입력할 것 없음(노트북 설정 그대로 복사됨).
echo   [운용 PC · 업데이트] 새 zip 을 **임시 폴더**에 풀기 → zip 루트의 "업데이트.bat" 더블클릭(관리자 확인 '예') → 끝.
echo     돌고 있는 앱·정산 프로그램을 스스로 멈추고(작업 관리자 강제 종료 불필요) 설치 폴더에 덮어쓴 뒤 설치(Y)·정산 이어서.
echo     output·data·config.json·proxies.txt 는 건드리지 않습니다(마스터·크롬 프로필·설정 유지 · 정산서 입력만 output\정산서\ 에 더함).
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
