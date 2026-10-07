# 운용 PC: 정산 다운로드 자동 실행(watch) 작업 스케줄러 등록 — 관리자 PowerShell 에서 실행.
#   powershell -ExecutionPolicy Bypass -File tools\settlement_watch_register.ps1 -Root D:\coupang-analytics
#   (exe 배포본이면 -Exe "D:\coupang-analytics\정산다운로드.exe" 처럼 실행 파일을 지정)
# 동작: 로그온 2분 뒤 + 매일 08:00 에 watch 를 띄운다(이미 떠 있으면 잠금으로 바로 종료 — 중복 없음).
#   watch = 24시간 감시 — ①판매수집이 도는 동안만 정지, 아니면 실행(소급 연속→소진 후 하루 1회, 소유자 결정 2026-10-07).
# 제거: Unregister-ScheduledTask -TaskName '쿠팡애널리틱스_정산다운로드' -Confirm:$false
param([string]$Root = (Get-Location).Path, [string]$Exe = '')
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path

if ($Exe) {
    $action = New-ScheduledTaskAction -Execute $Exe -Argument 'watch' -WorkingDirectory $Root
} else {
    $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source      # 콘솔창 안 뜨는 pythonw
    if (-not $pyw) {
        $p = (Get-Command python -ErrorAction SilentlyContinue).Source
        if ($p) { $pyw = Join-Path (Split-Path $p) 'pythonw.exe' }
    }
    if (-not $pyw -or -not (Test-Path $pyw)) { Write-Host '[오류] pythonw.exe 를 찾지 못함 — Python 설치/PATH 확인'; exit 1 }
    $action = New-ScheduledTaskAction -Execute $pyw -Argument 'tools\settlement_download.py watch' -WorkingDirectory $Root
}
$logon = New-ScheduledTaskTrigger -AtLogOn
$logon.Delay = 'PT2M'
$daily = New-ScheduledTaskTrigger -Daily -At 08:00
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew      # 시간 제한 없음(상시)
Register-ScheduledTask -TaskName '쿠팡애널리틱스_정산다운로드' -Action $action -Trigger @($logon, $daily) `
    -Settings $set -Description '정산 파일 자동 다운로드(24시간 감시·①판매수집 중만 정지)' -Force | Out-Null
Write-Host '[완료] 쿠팡애널리틱스_정산다운로드 등록 — 로그온 2분 뒤·매일 08:00 (중복 실행은 잠금으로 막음)'
Write-Host ('  작업폴더: ' + $Root)
Write-Host '  기록: output\정산\로그\ (실행·처리기록·오류)'
