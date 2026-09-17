# 다른 PC 설치 스크립트 — 설치.bat 가 호출한다(같은 폴더에 쿠팡애널리틱스.exe 가 있어야 함).
#   1) 쓰기 가능한 위치인지 점검   2) Google Chrome 설치 확인
#   3) 바탕화면·시작메뉴 바로가기 생성   4) (선택) 야간 무인 자동실행 등록
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

# 4) (선택) 야간 무인 자동실행 등록 ────────────────────────────
Write-Host '[4/4] 야간 무인 자동실행(매일 18:00 시작 → 06:00 종료) 등록'
Write-Host '      * 먼저 프로그램을 1회 실행해 입력 엑셀·API 키를 넣어 두어야 무인이 동작합니다.'
$ans = Read-Host '      지금 등록할까요? (Y=등록 / N=건너뛰기)'
if ($ans -match '^[Yy]') {
    $sched = Join-Path $root 'install_schedule.ps1'
    if (Test-Path $sched) {
        try {
            & $sched
        } catch {
            Write-Host "  [경고] 자동실행 등록 실패: $($_.Exception.Message)"
            Write-Host '         관리자 권한이 필요할 수 있습니다.'
            Write-Host '         이 설치 파일(설치.bat)을 마우스 우클릭 → "관리자 권한으로 실행" 후 다시 시도하세요.'
        }
    } else {
        Write-Host '  [경고] install_schedule.ps1 이 폴더에 없어 자동실행 등록을 건너뜁니다.'
    }
} else {
    Write-Host '  건너뜀. 나중에 필요하면 install_schedule.bat 로 등록할 수 있습니다.'
}

Write-Host ''
Write-Host '=============================================='
Write-Host '  설치 완료'
Write-Host "  실행: 바탕화면의 '쿠팡 애널리틱스' 바로가기 더블클릭"
Write-Host '  처음 1회 설정 탭에서 입력 엑셀·API 키를 넣으세요(이 PC 전용 암호화 저장).'
Write-Host '=============================================='
