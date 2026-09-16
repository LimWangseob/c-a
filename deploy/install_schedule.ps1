# 매일 18:00 무인 실행 작업을 등록합니다(앱이 06:00에 스스로 종료).
# 사용: 이 파일을 exe 와 같은 폴더(쿠팡애널리틱스)에 두고 install_schedule.bat 를 실행.
$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot '쿠팡애널리틱스.exe'
if (-not (Test-Path $exe)) {
    Write-Host "[오류] 같은 폴더에 쿠팡애널리틱스.exe 가 없습니다: $exe"
    exit 1
}
$action  = New-ScheduledTaskAction -Execute $exe -Argument '--auto' -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]'18:00')
# WakeToRun=자는 PC 깨워 실행 · StartWhenAvailable=놓치면 곧바로 · 13시간 제한(백스톱, 앱은 06:00 자동종료)
$settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 13)
Register-ScheduledTask -TaskName '쿠팡애널리틱스_야간무인' -Action $action -Trigger $trigger `
    -Settings $settings -Description '매일 18:00 무인 실행(06:00 자동 종료)' -Force | Out-Null

# ── 재부팅 복구: 로그온 시 --resume 로 실행(오늘 중단분만 이어서, 없으면 스스로 종료) ──
# Windows 업데이트 등으로 야간에 재부팅되면, 재로그인(자동로그인 설정 시) 직후 이 작업이 떠서
# 판매수집은 건너뛰고 순위부터 이어서 완료한다. 중단분이 없으면 아무것도 안 하고 즉시 종료한다.
$actionR  = New-ScheduledTaskAction -Execute $exe -Argument '--resume' -WorkingDirectory $PSScriptRoot
$triggerR = New-ScheduledTaskTrigger -AtLogOn
$triggerR.Delay = 'PT2M'      # 로그온 2분 뒤(세션·네트워크 안정 대기)
Register-ScheduledTask -TaskName '쿠팡애널리틱스_재부팅복구' -Action $actionR -Trigger $triggerR `
    -Settings $settings -Description '재부팅/로그온 시 오늘 중단분 이어서(--resume)' -Force | Out-Null

Write-Host '[완료] 작업 2개 등록됨:'
Write-Host '  1) 쿠팡애널리틱스_야간무인   — 매일 18:00 자동 실행 → 06:00 자동 종료'
Write-Host '  2) 쿠팡애널리틱스_재부팅복구 — 로그온 시 오늘 중단분만 이어서(없으면 즉시 종료)'
Write-Host '  - 해제: uninstall_schedule.bat'
Write-Host '  ※ 재부팅 자동복구가 무인으로 동작하려면 Windows 설정에서'
Write-Host '     "업데이트/다시 시작 후 로그인 정보로 자동 로그인 완료"를 켜 두세요(설정>계정>로그인 옵션).'
Write-Host '  ※ PC 가 완전히 꺼져 있으면 야간무인은 깨우지 못합니다(절전/대기 상태여야 WakeToRun 동작).'
