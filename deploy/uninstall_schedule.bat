@echo off
chcp 65001 >nul
echo === 무인 실행 예약 해제 ===
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Unregister-ScheduledTask -TaskName '쿠팡애널리틱스_야간무인' -Confirm:$false; Write-Host '[완료] 예약 해제됨' } catch { Write-Host '[안내] 등록된 예약이 없거나 권한이 필요합니다' }"
pause
