# 다른 PC 설치 — **이 스크립트 하나로 통합**(설치.bat 이 호출). 같은 폴더에 쿠팡애널리틱스.exe 필요.
#   1) 쓰기 가능 위치 점검  2) Google Chrome 확인  3) 바로가기(바탕화면·시작메뉴)
#   4) 야간 무인 자동실행 등록/해제(예전 install_schedule.* · uninstall_schedule.* 를 여기에 합침)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$exe  = Join-Path $root '쿠팡애널리틱스.exe'

Write-Host '=============================================='
Write-Host '   쿠팡 애널리틱스 - 설치'
Write-Host '=============================================='
Write-Host ''

# 0) exe 존재 확인 ──────────────────────────────────────────────
if (-not (Test-Path $exe)) {
    Write-Host "[오류] 같은 폴더에 '쿠팡애널리틱스.exe' 가 없습니다."
    Write-Host "       이 설치 파일은 '쿠팡애널리틱스' 폴더 안(exe 옆)에 두고 실행하세요."
    Write-Host "       현재 폴더: $root"
    exit 1
}

# 1) 쓰기 가능 위치 점검 ────────────────────────────────────────
Write-Host '[1/4] 설치 위치 점검...'
$loc_bad = $false
$prog  = [Environment]::GetFolderPath('ProgramFiles')
$progx = ${env:ProgramFiles(x86)}
$win   = $env:WINDIR
foreach ($p in @($prog, $progx, $win)) {
    if ($p -and $root.ToLower().StartsWith($p.ToLower())) { $loc_bad = $true }
}
try {   # 실제로 파일을 만들어 써봐서 쓰기 가능한지 확인
    $probe = Join-Path $root ('.write_test_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType File -Path $probe -Force | Out-Null
    Remove-Item $probe -Force
} catch { $loc_bad = $true }
if ($loc_bad) {
    Write-Host '  [경고] 이 폴더는 쓰기가 제한된 위치일 수 있습니다(예: C:\Program Files).'
    Write-Host '         결과 파일(엑셀)·로그·크롬 프로필 저장이 막힐 수 있으니'
    Write-Host '         바탕화면이나 문서 폴더로 옮겨서 설치하는 것을 권장합니다.'
} else {
    Write-Host '  [확인] 쓰기 가능한 위치입니다.'
}
Write-Host ''

# 2) Google Chrome 설치 확인 ───────────────────────────────────
Write-Host '[2/4] Google Chrome 확인...'
$chromeCands = @(
    "$prog\Google\Chrome\Application\chrome.exe",
    "$progx\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $null
foreach ($c in $chromeCands) { if ($c -and (Test-Path $c)) { $chrome = $c; break } }
if (-not $chrome) {   # 레지스트리 App Paths 도 확인
    foreach ($k in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
                     'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).'(default)'
            if ($v -and (Test-Path $v)) { $chrome = $v; break }
        } catch { }
    }
}
if ($chrome) {
    Write-Host "  [확인] Chrome 설치됨: $chrome"
} else {
    Write-Host '  [경고] Google Chrome 을 찾지 못했습니다.'
    Write-Host '         이 프로그램은 실제 Chrome 으로만 동작합니다(정책).'
    Write-Host '         https://www.google.com/chrome 에서 설치한 뒤 사용하세요.'
}
Write-Host ''

# 3) 바로가기 생성(바탕화면 + 시작메뉴) ─────────────────────────
Write-Host '[3/4] 바로가기 생성...'
$sh = New-Object -ComObject WScript.Shell
$desktop  = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')   # 시작메뉴\프로그램
$made = @()
foreach ($dir in @($desktop, $programs)) {
    if (-not $dir) { continue }
    try {
        $lnk = $sh.CreateShortcut((Join-Path $dir '쿠팡 애널리틱스.lnk'))
        $lnk.TargetPath       = $exe
        $lnk.WorkingDirectory = $root
        $lnk.IconLocation     = "$exe,0"
        $lnk.Description       = '쿠팡 애널리틱스'
        $lnk.Save()
        $made += $dir
    } catch {
        Write-Host "  [경고] 바로가기 생성 실패($dir): $($_.Exception.Message)"
    }
}
if ($made.Count -gt 0) {
    Write-Host '  [확인] 바로가기 생성됨:'
    foreach ($d in $made) { Write-Host "         - $d\쿠팡 애널리틱스.lnk" }
}
Write-Host ''

# ── 야간 무인 자동실행 등록/해제 (예전 install_schedule / uninstall_schedule 통합) ──
function Register-AutoTasks {
    # 1) 매일 18:00 무인 실행(--auto, 앱이 06:00 자동 종료)
    $action  = New-ScheduledTaskAction -Execute $exe -Argument '--auto' -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]'18:00')
    # WakeToRun=자는 PC 깨움 · StartWhenAvailable=놓치면 곧바로 · 13시간 제한(백스톱, 앱은 06:00 자동종료)
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 13)
    Register-ScheduledTask -TaskName '쿠팡애널리틱스_야간무인' -Action $action -Trigger $trigger `
        -Settings $settings -Description '매일 18:00 무인 실행(06:00 자동 종료)' -Force | Out-Null
    # 2) 재부팅 복구: 로그온 시 --resume(오늘 중단분만 이어서, 없으면 즉시 종료)
    $actionR  = New-ScheduledTaskAction -Execute $exe -Argument '--resume' -WorkingDirectory $root
    $triggerR = New-ScheduledTaskTrigger -AtLogOn
    $triggerR.Delay = 'PT2M'      # 로그온 2분 뒤(세션·네트워크 안정 대기)
    Register-ScheduledTask -TaskName '쿠팡애널리틱스_재부팅복구' -Action $actionR -Trigger $triggerR `
        -Settings $settings -Description '재부팅/로그온 시 오늘 중단분 이어서(--resume)' -Force | Out-Null
}
function Unregister-AutoTasks {
    # 우리 작업만 실행 인자(--auto/--resume)로 찾아 제거(한글 작업명 인코딩 문제 회피)
    $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        $a = (($_.Actions | ForEach-Object { [string]$_.Arguments }) -join ' ')
        ($a -match '(^|\s)--auto(\s|$)') -or ($a -match '(^|\s)--resume(\s|$)')
    }
    foreach ($t in $tasks) {
        Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false -ErrorAction SilentlyContinue
    }
    return @($tasks).Count
}

Write-Host '[4/4] 야간 무인 자동실행(매일 18:00 시작 -> 06:00 종료)'
Write-Host '      * 먼저 프로그램을 1회 실행해 입력(관리대장)·API 키를 넣어 두어야 무인이 동작합니다.'
$ans = Read-Host '      등록=Y / 해제=R / 건너뛰기=N'
if ($ans -match '^[Yy]') {
    try {
        Register-AutoTasks
        Write-Host '  [확인] 자동실행 2개 등록: 쿠팡애널리틱스_야간무인(18:00) · 쿠팡애널리틱스_재부팅복구(로그온)'
        Write-Host '  ※ 재부팅 자동복구가 무인으로 동작하려면 Windows 설정>계정>로그인 옵션에서'
        Write-Host '     "업데이트/다시 시작 후 로그인 정보로 자동 로그인 완료"를 켜 두세요.'
        Write-Host '  ※ PC 가 완전히 꺼져 있으면 못 깨웁니다(절전/대기 상태여야 WakeToRun 동작).'
    } catch {
        Write-Host "  [경고] 자동실행 등록 실패: $($_.Exception.Message)"
        Write-Host '         관리자 권한이 필요합니다 → 설치.bat 을 우클릭 → "관리자 권한으로 실행" 후 다시 시도.'
    }
} elseif ($ans -match '^[Rr]') {
    try {
        $n = Unregister-AutoTasks
        Write-Host "  [확인] 자동실행 작업 $n 개 해제됨."
    } catch {
        Write-Host "  [경고] 해제 실패: $($_.Exception.Message) — 관리자 권한으로 다시 시도하세요."
    }
} else {
    Write-Host '  건너뜀. 나중에 설치.bat 을 다시 실행해 등록(Y)/해제(R)할 수 있습니다.'
}

Write-Host ''
Write-Host '=============================================='
Write-Host '  설치 완료'
Write-Host "  실행: 바탕화면의 '쿠팡 애널리틱스' 바로가기 더블클릭"
Write-Host '  처음 1회 설정 탭에서 입력(관리대장)·API 키를 넣으세요(이 PC 전용 암호화 저장).'
Write-Host '=============================================='
