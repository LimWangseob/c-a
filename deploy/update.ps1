# 업데이트 — 새 배포 zip 을 **임시 폴더에 푼 뒤** 업데이트.bat 이 이 스크립트를 부른다(소유자 11-23: 배포 때 정산 프로그램이
# 돌고 있어 작업 관리자로 강제 종료하던 일을 없앰).
#   1) 설치 폴더 찾기(예약 작업 '--auto/--resume' 의 실행 파일 폴더 · 바탕화면 바로가기)  2) 그 폴더에서 실행 중인 프로그램 표시
#   3) 정산 프로그램 → 앱 → 나머지 순서로 트리째 종료(00:10 시작 정리·[정산 중지]와 같은 taskkill /F /T · D-024)
#   4) 다 멈췄는지(프로세스 다시 조회 + 덮어쓸 파일 잠금) 확인 — 하나라도 남으면 **복사 안 함**(이유 표시)
#   5) 복사(⛔ output\ · data\ · config.json · proxies.txt 는 절대 안 덮음 · 설치 폴더 파일은 지우지 않음) + 크기·exe 내용 대조
#   6) install.ps1(설치.bat 과 같은 단계 — 예약 작업 Y)  7) 정산·무인 앱을 멈췄으면 '재부팅 복구' 예약 작업(--resume)으로 다시 띄움
#      = 재부팅 때와 같은 길: 오늘 끊긴 단계만 이어서 + 정산 자동 수집 다시 기동(같은 회차 '완료'면 정산은 바로 끝남 D-091).
# 종료코드: 0 = 업데이트됨 · 2 = 아무것도 안 바꿈(이유 표시) · 3 = 복사 도중 실패(다시 실행하면 이어서 덮어씀).
param(
    [string]$Source = '',      # 새 zip 을 푼 coupang-analytics 폴더(기본 = 이 스크립트 폴더)
    [string]$Target = '',      # 설치 폴더(기본 = 예약 작업·바로가기에서 찾음)
    [switch]$Yes,              # 확인 질문 없이 진행(시험·원격용)
    [switch]$NoInstall,        # install.ps1 단계 건너뜀
    [switch]$NoRestart,        # 다시 띄우기 건너뜀(필요 여부만 표시)
    [int]$StopWaitSec = 30     # 종료 뒤 프로세스가 사라지길 기다리는 최대 초
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$APP = '쿠팡애널리틱스.exe'
$SETTLE = '정산다운로드.exe'
$NEED = @($APP, $SETTLE)                        # 새 폴더에 꼭 있어야 하는 실행 파일(Defender 가 지웠으면 멈춤)
$KEEP_DIRS = @('output', 'data')                # ⛔ 사용자 자료 — 절대 덮어쓰기·삭제 안 함
$KEEP_FILES = @('config.json', 'proxies.txt')

function Say([string]$m) { Write-Host $m }
function Stop-Here([string]$m) {
    Say ''
    Say "[중단] $m"
    Say '        설치 폴더는 바뀌지 않았습니다.'
    exit 2
}

function Get-FullPath([string]$p) {
    return [IO.Path]::GetFullPath($p).TrimEnd('\')
}

function Test-Under([string]$path, [string]$root) {
    if (-not $path) { return $false }
    return $path.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Find-Targets {
    # 설치 폴더 후보 = 예약 작업(--auto·--resume)의 실행 파일 폴더 + 바탕화면 바로가기 대상 폴더
    $found = @()
    foreach ($t in @(Get-ScheduledTask -ErrorAction SilentlyContinue)) {
        foreach ($a in @($t.Actions)) {
            if (([string]$a.Arguments -match '(^|\s)--(auto|resume)(\s|$)') -and $a.Execute) {
                $found += (Split-Path -Parent ([string]$a.Execute).Trim('"'))
            }
        }
    }
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) '쿠팡 애널리틱스.lnk'
    if (Test-Path $lnk) {
        $found += (Split-Path -Parent (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).TargetPath)
    }
    $ok = @()
    foreach ($f in $found) {
        if ($f -and (Test-Path (Join-Path $f $APP))) { $ok += (Get-FullPath $f) }
    }
    return @($ok | Sort-Object -Unique)
}

function Resolve-Target {
    if ($Target) { return (Get-FullPath $Target) }
    $c = @(Find-Targets)
    if ($c.Count -eq 1) { return $c[0] }
    if ($c.Count -gt 1) { Say ('  설치 폴더 후보가 여러 개입니다: ' + ($c -join ' · ')) }
    else { Say '  예약 작업·바탕화면 바로가기에서 설치 폴더를 찾지 못했습니다.' }
    if ($Yes) { Stop-Here '설치 폴더를 정할 수 없음 — -Target 으로 지정하세요.' }
    $typed = Read-Host '  설치 폴더 경로를 입력하세요(예: 쿠팡애널리틱스.exe 가 있는 폴더)'
    if (-not $typed) { Stop-Here '설치 폴더를 입력하지 않음.' }
    return (Get-FullPath $typed.Trim('"'))
}

function Get-Running([string]$root) {
    # 설치 폴더 안 실행 파일로 돌고 있는 프로세스 전부(앱·정산·진단 …) — 이 스크립트 자신 제외
    $me = $PID
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $me -and (Test-Under ([string]$_.ExecutablePath) $root)
    })
}

function Get-Kind($p) {
    if ($p.Name -ieq $SETTLE) { return '정산 프로그램' }
    if ($p.Name -ieq $APP) {
        if ([string]$p.CommandLine -match '(^|\s)--(auto|resume)(\s|$)') { return '앱(무인 실행)' }
        return '앱'
    }
    return '기타'
}

function Show-Running($procs) {
    foreach ($p in $procs) {
        $cl = [string]$p.CommandLine
        $tail = $cl.Substring(0, [Math]::Min(140, $cl.Length))
        Say ("    - {0} · {1} · PID {2} · {3}" -f (Get-Kind $p), $p.Name, $p.ProcessId, $tail)
    }
}

function Stop-Tree($p) {
    # 00:10 시작 정리·[정산 중지]와 같은 방법(app_process._KILL_PS · 자식 Chrome 까지 트리째)
    if (-not (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue)) {   # 앞 트리(앱)의 자식으로 이미 끝남
        Say ("  [멈춤] {0} (PID {1}) — 이미 끝남" -f $p.Name, $p.ProcessId); return
    }
    $ErrorActionPreference = 'Continue'      # taskkill 의 오류 출력을 예외로 바꾸지 않게(종료코드로 판정)
    & taskkill.exe /F /T /PID $p.ProcessId *> $null
    if ($LASTEXITCODE -eq 0) { Say ("  [멈춤] {0} {1} (PID {2}) + 자식 프로세스" -f (Get-Kind $p), $p.Name, $p.ProcessId) }
    else { Say ("  [경고] {0} (PID {1}) 종료 명령 실패(종료코드 {2})" -f $p.Name, $p.ProcessId, $LASTEXITCODE) }
}

function Wait-Gone($ids, [int]$sec) {
    $end = (Get-Date).AddSeconds($sec)
    while ((Get-Date) -lt $end) {
        $alive = @($ids | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
        if ($alive.Count -eq 0) { return }
        Start-Sleep -Milliseconds 300
    }
}

function Stop-All($procs) {
    # 정산 먼저(앱이 꺼지면 정산이 스스로 끝나게 돼 있지만 D-020 · 순서를 정해 확실히) → 앱 → 나머지
    $order = @($procs | Where-Object { $_.Name -ieq $SETTLE }) + @($procs | Where-Object { $_.Name -ieq $APP }) +
             @($procs | Where-Object { ($_.Name -ine $SETTLE) -and ($_.Name -ine $APP) })
    foreach ($p in $order) { Stop-Tree $p }
    Wait-Gone @($order | ForEach-Object { $_.ProcessId }) $StopWaitSec
    Start-Sleep -Seconds 2                     # 곧바로 다시 뜨는 것(다른 예약 실행 등)까지 잡으려고 잠깐 뒤 다시 조회
}

function Get-CopyList([string]$src) {
    # Rel = 상대 경로 · Full = 원본 전체 경로 — 보존 대상은 뺀다
    $list = @()
    foreach ($f in @(Get-ChildItem -LiteralPath $src -Recurse -File -Force)) {
        $rel = $f.FullName.Substring($src.Length + 1)
        $top = ($rel -split '\\')[0]
        if ($KEEP_DIRS -contains $top.ToLower() -and $rel.Contains('\')) { continue }
        if ($KEEP_FILES -contains $rel.ToLower()) { continue }
        $list += [pscustomobject]@{ Rel = $rel; Full = $f.FullName }
    }
    return $list
}

function Get-Locked($list, [string]$dst) {
    # 덮어쓸 파일 중 다른 프로그램이 쥐고 있는 것(배타적으로 열어 보기) — 있으면 복사 안 함
    $bad = @()
    foreach ($it in $list) {
        $d = Join-Path $dst $it.Rel
        if (-not (Test-Path -LiteralPath $d)) { continue }
        try {
            $fs = [IO.File]::Open($d, 'Open', 'ReadWrite', 'None')
            $fs.Close()
        } catch {
            $bad += "$($it.Rel) — $($_.Exception.Message)"
        }
    }
    return $bad
}

function Copy-All($list, [string]$dst) {
    $fail = @()
    foreach ($it in $list) {
        $d = Join-Path $dst $it.Rel
        try {
            $dir = Split-Path -Parent $d
            if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            [IO.File]::Copy($it.Full, $d, $true)
        } catch { $fail += "$($it.Rel): $($_.Exception.Message)" }
    }
    return $fail
}

function Get-Sha256([string]$path) {
    # .NET 직접(모듈 자동 로드에 기대지 않음 — 시험에서 Get-FileHash 를 못 찾은 실측 11-23)
    $fs = [IO.File]::OpenRead($path)
    try { return [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($fs)) }
    finally { $fs.Close() }
}

function Get-Mismatch($list, [string]$dst) {
    # 크기 전부 + 실행 파일(.exe) 내용(SHA-256) 대조
    $bad = @()
    foreach ($it in $list) {
        $d = Join-Path $dst $it.Rel
        if ((Get-Item -LiteralPath $d).Length -ne (Get-Item -LiteralPath $it.Full).Length) { $bad += $it.Rel; continue }
        if ($it.Rel -like '*.exe') {
            if ((Get-Sha256 $d) -ne (Get-Sha256 $it.Full)) { $bad += $it.Rel }
        }
    }
    return $bad
}

function Get-ResumeTask([string]$root) {
    foreach ($t in @(Get-ScheduledTask -ErrorAction SilentlyContinue)) {
        foreach ($a in @($t.Actions)) {
            $exe = ([string]$a.Execute).Trim('"')
            if (([string]$a.Arguments -match '(^|\s)--resume(\s|$)') -and (Test-Under $exe $root)) { return $t }
        }
    }
    return $null
}

function Start-Again([string]$root, [string]$why) {
    # 재부팅 복구 예약 작업(--resume) = 오늘 끊긴 단계만 이어서 + 정산 자동 수집 다시 기동(app_qt main · D-021)
    if ($NoRestart) { Say "  [다시 띄우기] 필요($why) — -NoRestart 로 건너뜀"; return }
    $t = Get-ResumeTask $root
    if (-not $t) {
        Say "  [다시 띄우기] ⚠ 재부팅 복구 예약 작업(--resume)이 없어 못 띄움($why)."
        Say '        앱을 켜고 정산 탭 [정산 시작]을 누르거나, 다음 00:10 무인 실행이 이어받습니다.'
        return
    }
    Start-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath
    Say "  [다시 띄우기] '$($t.TaskName)' 실행 — 재부팅 때처럼 오늘 남은 단계 + 정산 자동 수집을 이어서 합니다($why)."
    $end = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $end) {
        $s = @(Get-Running $root | Where-Object { $_.Name -ieq $SETTLE })
        if ($s.Count -gt 0) { Say "  [확인] 정산 프로그램 다시 실행 중(PID $($s[0].ProcessId))"; return }
        Start-Sleep -Seconds 2
    }
    Say '  [확인 필요] 30초 안에 정산 프로그램이 안 보임 — 이번 회차가 이미 끝났으면 정상입니다. 정산_상태확인.bat 으로 확인하세요.'
}

function Get-RestartReason($procs) {
    $why = @()
    if (@($procs | Where-Object { $_.Name -ieq $SETTLE }).Count) { $why += '정산 프로그램을 멈춤' }
    if (@($procs | Where-Object { (Get-Kind $_) -eq '앱(무인 실행)' }).Count) { $why += '무인 실행 앱을 멈춤' }
    return ($why -join ' · ')
}

function Confirm-Go([string]$dst, $procs) {
    if ($Yes) { return }
    if (@($procs | Where-Object { $_.Name -ieq $APP }).Count) {
        Say '  ⚠ 앱이 켜져 있습니다. 지금 멈추면 하던 단계는 업데이트 뒤 재부팅 복구(--resume)로 이어서 합니다.'
    }
    $ans = Read-Host "  설치 폴더 '$dst' 를 업데이트할까요? (위 프로그램은 멈춥니다) Y/N"
    if ($ans -notmatch '^[Yy]') { Stop-Here '사람이 취소함.' }
}

# ── 실행 ──────────────────────────────────────────────────────────
Say '=============================================='
Say '   쿠팡 애널리틱스 - 업데이트(실행 중인 프로그램 멈춤 → 덮어쓰기 → 설치 → 이어서)'
Say '=============================================='
$src = Get-FullPath $(if ($Source) { $Source } else { $PSScriptRoot })
foreach ($n in $NEED) {
    if (-not (Test-Path (Join-Path $src $n))) {
        Stop-Here "새 폴더에 '$n' 이 없습니다($src) — Windows Defender 가 지웠을 수 있어요. 0_먼저실행_보안제외.bat 을 관리자로 실행한 뒤 zip 을 다시 푸세요."
    }
}
Say "[1/6] 새 폴더: $src"
$dst = Resolve-Target
if (-not (Test-Path (Join-Path $dst $APP))) { Stop-Here "설치 폴더에 '$APP' 이 없습니다: $dst" }
if ($dst -ieq $src) { Stop-Here '새 폴더와 설치 폴더가 같습니다 — 새 zip 을 다른(임시) 폴더에 풀고 그 안의 업데이트.bat 을 실행하세요.' }
Say "      설치 폴더: $dst"

Say '[2/6] 설치 폴더에서 실행 중인 프로그램 확인...'
$running = @(Get-Running $dst)
if ($running.Count -eq 0) { Say '  [확인] 실행 중인 프로그램 없음 — 바로 덮어씁니다.' } else { Show-Running $running }
Confirm-Go $dst $running
$why = Get-RestartReason $running

Say '[3/6] 멈추기...'
if ($running.Count) { Stop-All $running } else { Say '  (멈출 것 없음)' }
$left = @(Get-Running $dst)
if ($left.Count) {
    Say '  [실패] 아직 실행 중:'
    Show-Running $left
    Stop-Here '멈추지 못한 프로그램이 있어 복사하지 않았습니다 — 작업 관리자에서 위 프로그램을 끝내거나 PC 를 다시 시작한 뒤 다시 실행하세요.'
}
$list = @(Get-CopyList $src)
$locked = @(Get-Locked $list $dst)
if ($locked.Count) {
    Say "  [실패] 다른 프로그램이 쥐고 있는 파일 $($locked.Count)개:"
    $locked | Select-Object -First 10 | ForEach-Object { Say "    - $_" }
    if ($why) { Start-Again $dst "$why · 업데이트 못 함(옛 버전 그대로)" }
    Stop-Here '사용 중인 파일이 있어 복사하지 않았습니다 — 그 파일을 연 프로그램(엑셀·탐색기 미리보기 등)을 닫고 다시 실행하세요.'
}
Say "  [확인] 멈춤 확인 — 실행 중 0개 · 덮어쓸 파일 잠금 0개"

Say "[4/6] 덮어쓰기 $($list.Count)개(⛔ output\ · data\ · config.json · proxies.txt 는 건드리지 않음 · 지우는 파일 없음)..."
$fail = @(Copy-All $list $dst)
if ($fail.Count) {
    $fail | Select-Object -First 10 | ForEach-Object { Say "    - $_" }
    Say "[실패] 복사 실패 $($fail.Count)개 — 업데이트.bat 을 다시 실행하면 이어서 덮어씁니다."
    exit 3
}
$bad = @(Get-Mismatch $list $dst)
if ($bad.Count) {
    $bad | Select-Object -First 10 | ForEach-Object { Say "    - $_" }
    Say "[실패] 복사 뒤 대조 불일치 $($bad.Count)개 — 업데이트.bat 을 다시 실행하세요."
    exit 3
}
Say "  [확인] 복사 $($list.Count)개 · 크기·exe 내용 대조 일치"

Say '[5/6] 설치(바로가기·설정 적용·야간 무인 예약 — 설치.bat 과 같음)...'
$inst = Join-Path $dst 'install.ps1'
if ($NoInstall) { Say '  (-NoInstall 로 건너뜀)' }
elseif (-not (Test-Path $inst)) { Say "  [경고] install.ps1 이 없어 건너뜀: $inst" }
else { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $inst }

Say '[6/6] 이어서 하기...'
if ($why) { Start-Again $dst $why } else { Say '  (멈춘 정산·무인 실행 없음 — 다시 띄울 것 없음 · 앱은 바로가기로 켜세요)' }
Say ''
Say '=============================================='
Say '  업데이트 완료'
Say '=============================================='
exit 0
