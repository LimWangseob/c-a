# 쿠팡 애널리틱스 - 야간 무인 자동실행(18:00) + 재부팅 복구(로그온) 스케줄 작업 삭제(이 PC).
# 우리 작업만 실행 인자(--auto/--resume)로 찾아 지운다(한글 작업명 인코딩 문제 회피·소스/exe 둘 다 매칭).
$ErrorActionPreference = 'Stop'
Write-Host '=============================================='
Write-Host '   쿠팡 애널리틱스 - 자동 실행 삭제'
Write-Host '=============================================='
Write-Host ''
$tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $a = (($_.Actions | ForEach-Object { [string]$_.Arguments }) -join ' ')
    ($a -match '(^|\s)--auto(\s|$)') -or ($a -match '(^|\s)--resume(\s|$)')
}
if (-not $tasks) {
    Write-Host '  등록된 자동 실행 작업이 없습니다(이미 삭제됨).'
    Write-Host ''
    Write-Host '  18:00 자동 실행과 로그온 자동복구가 동작하지 않습니다.'
} else {
    $n = 0; $fail = 0
    foreach ($t in $tasks) {
        try {
            Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false -ErrorAction Stop
            Write-Host "  [삭제됨] $($t.TaskName)"
            $n++
        } catch {
            Write-Host "  [실패] $($t.TaskName): $($_.Exception.Message)"
            $fail++
        }
    }
    Write-Host ''
    if ($fail -gt 0) {
        Write-Host "  [주의] $fail 개 삭제 실패(관리자 권한 필요) - 아직 자동 실행이 남아 있습니다."
        Write-Host '         이 창을 닫고, "자동실행_삭제.bat" 를 우클릭 -> "관리자 권한으로 실행" 하세요.'
    } else {
        Write-Host "  자동 실행 작업 $n 개 삭제 완료 - 이제 18:00 자동 실행과 로그온 자동복구가 동작하지 않습니다."
        Write-Host '  앱은 바로가기로 수동 실행하면 됩니다. 다시 켜려면 "설치.bat" 에서 등록(Y).'
    }
}
Write-Host ''
