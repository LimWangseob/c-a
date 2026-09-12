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
Write-Host '[완료] 작업 등록됨: 매일 18:00 자동 실행 → 06:00 자동 종료'
Write-Host '  - 확인: 작업 스케줄러에서 "쿠팡애널리틱스_야간무인"'
Write-Host '  - 해제: uninstall_schedule.bat'
Write-Host '  ※ PC 가 완전히 꺼져 있으면 깨우지 못합니다(절전/대기 상태여야 WakeToRun 동작).'
