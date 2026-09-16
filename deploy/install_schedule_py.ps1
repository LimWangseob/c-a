# 파이썬(소스) 실행 방식으로 스케줄러 작업 2개 등록 — install_schedule_py.bat 가 관리자 권한으로 호출.
# exe 가 아니라 이 PC 의 python 으로 D:\coupang-analytics\ui\app_qt.py 를 실행한다(최신 소스 그대로 = --resume 포함).
param([string]$Root)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path

# 콘솔창 안 뜨는 pythonw 우선(없으면 python 폴더에서 유도)
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $p = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($p) { $pyw = Join-Path (Split-Path $p) 'pythonw.exe' }
}
if (-not $pyw -or -not (Test-Path $pyw)) {
    Write-Host '[오류] pythonw.exe 를 찾지 못했습니다. Python 설치/PATH 를 확인하세요.'
    exit 1
}

$set = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 13)

# 1) 매일 18:00 무인 실행(06:00 앱이 스스로 종료)
$a1 = New-ScheduledTaskAction -Execute $pyw -Argument 'ui\app_qt.py --auto' -WorkingDirectory $Root
$t1 = New-ScheduledTaskTrigger -Daily -At 18:00
Register-ScheduledTask -TaskName '쿠팡애널리틱스_야간무인' -Action $a1 -Trigger $t1 `
    -Settings $set -Description '매일 18:00 무인 실행(06:00 자동 종료)' -Force | Out-Null

# 2) 로그온 시 재부팅 복구(--resume: 오늘 중단분만 이어서, 없으면 즉시 종료)
$a2 = New-ScheduledTaskAction -Execute $pyw -Argument 'ui\app_qt.py --resume' -WorkingDirectory $Root
$t2 = New-ScheduledTaskTrigger -AtLogOn
$t2.Delay = 'PT2M'
Register-ScheduledTask -TaskName '쿠팡애널리틱스_재부팅복구' -Action $a2 -Trigger $t2 `
    -Settings $set -Description '재부팅/로그온 시 오늘 중단분 이어서(--resume)' -Force | Out-Null

Write-Host ('[완료] 두 작업 등록됨')
Write-Host ('  python : ' + $pyw)
Write-Host ('  작업폴더: ' + $Root)
Write-Host '  1) 쿠팡애널리틱스_야간무인   — 매일 18:00 → 06:00 자동 종료'
Write-Host '  2) 쿠팡애널리틱스_재부팅복구 — 로그온 시 오늘 중단분 이어서'
Write-Host '  ※ 재부팅 복구가 무인으로 동작하려면 Windows "업데이트/재시작 후 자동 로그인 완료" 를 켜 두세요(이미 켜 두심).'
