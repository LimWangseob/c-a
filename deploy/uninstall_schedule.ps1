# 스케줄러 작업 해제(야간무인 + 재부팅복구) — uninstall_schedule.bat 가 관리자 권한으로 호출.
foreach ($t in '쿠팡애널리틱스_야간무인', '쿠팡애널리틱스_재부팅복구') {
    try {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction Stop
        Write-Host ('[완료] 해제: ' + $t)
    } catch {
        Write-Host ('[안내] 없음/권한필요: ' + $t)
    }
}
