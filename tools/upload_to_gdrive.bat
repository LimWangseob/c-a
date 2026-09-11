@echo off
REM ============================================================
REM  쿠팡 결과 파일 → 구글 드라이브 자동 업로드 (아침 9시 작업 스케줄러용)
REM  사전 준비(1회):
REM    1) rclone 설치:  winget install Rclone.Rclone   (또는 https://rclone.org/downloads/)
REM    2) rclone config 로 구글 드라이브 리모트 'gdrive' 등록(브라우저 OAuth는 본인이 로그인)
REM       - n(new) > name=gdrive > storage=drive > 나머지 기본 > 브라우저 인증 > y
REM    3) 아래 DEST 폴더명(쿠팡분석)을 원하는 드라이브 폴더로 바꾸세요.
REM ============================================================
setlocal
set "SRC=D:\coupang-analytics\output\쿠팡데이타분석_통계.xlsx"
set "DEST=gdrive:쿠팡분석"
set "TMP=%TEMP%\쿠팡데이타분석_통계_upload.xlsx"

REM 앱이 파일을 쓰는 중일 수 있으니 임시 사본으로 복사 후 업로드(잠김/반쓰기 회피)
copy /Y "%SRC%" "%TMP%" >nul
if errorlevel 1 (
  echo [%date% %time%] 복사 실패 - 파일이 없거나 열려있음
  exit /b 1
)

REM 드라이브에 같은 이름으로 덮어쓰기 업로드(최신 완료본 1개 유지)
rclone copyto "%TMP%" "%DEST%/쿠팡데이타분석_통계.xlsx" -v --log-file="D:\coupang-analytics\output\gdrive_upload.log"
set RC=%errorlevel%

del "%TMP%" >nul 2>&1
if %RC%==0 ( echo [%date% %time%] 업로드 성공 ) else ( echo [%date% %time%] 업로드 실패 rc=%RC% )
exit /b %RC%
