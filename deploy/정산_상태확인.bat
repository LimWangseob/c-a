@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================
echo    정산 자동 다운로드 - 현재 상태 확인
echo ==================================================
echo.
echo [1] 지금 상태(정산 watch 가 매 5분 갱신)
echo --------------------------------------------------
if exist "output\정산\로그\_현재상태.txt" (
  type "output\정산\로그\_현재상태.txt"
) else (
  echo   아직 상태 파일이 없습니다.
  echo   ^(정산 watch 가 한 번도 안 돌았거나, output 폴더가 아직 없음^)
)
echo.
echo [2] 자동 실행 작업 등록 여부
echo --------------------------------------------------
schtasks /query /tn "쿠팡애널리틱스_정산다운로드" >nul 2>&1 && (
  echo   [등록됨] '쿠팡애널리틱스_정산다운로드' 작업이 있습니다.
) || (
  echo   [작업 없음] 설치.bat 로 등록되지 않았습니다 ^(정산 자동 다운로드가 안 돕니다^).
)
echo.
echo [3] 지금 프로세스가 떠 있나
echo --------------------------------------------------
tasklist /fi "imagename eq 정산다운로드.exe" 2>nul | find /i "정산다운로드.exe" >nul && (
  echo   [실행 중] 정산다운로드.exe 프로세스가 떠 있습니다.
) || (
  echo   [실행 안 함] 정산다운로드.exe 프로세스가 없습니다 ^(대기 중이면 보통 떠 있어야 함^).
)
echo.
echo [4] 최신 상세 로그 끝부분 25줄
echo --------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d='output\정산\로그'; $f=Get-ChildItem $d -Filter '실행_*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){ Write-Host ('파일: '+$f.Name+'  (마지막 기록 '+$f.LastWriteTime.ToString('MM-dd HH:mm:ss')+')'); Write-Host ''; Get-Content -LiteralPath $f.FullName -Tail 25 -Encoding UTF8 } else { Write-Host '  상세 로그가 아직 없습니다.' }"
echo.
echo ==================================================
echo  * 처리 결과표(엑셀): output\정산\로그\처리기록_누적.csv
echo  * 이 창은 지금 이 순간의 상태입니다. 다시 보려면 이 파일을 또 더블클릭하세요.
echo ==================================================
echo.
pause
