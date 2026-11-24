@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==================================================
echo    정산서 입력 반영 - 개발 PC 가 만든 정산서입력_YYMMDD.zip 을 더하기만
echo ==================================================
echo.
echo  넣는 곳 : output\정산서\입력\  ^(셀독 판정표 = output\정산서\입력_셀독\^)
echo  * 지우는 파일 없음. 같은 이름 파일이 이미 있으면 덮기 전에
echo    output\정산서\입력\보관\날짜_시각\ 으로 옮깁니다 ^(내용이 같으면 그대로 둠^).
echo  * 받은 zip 의 풀린 사본도 같은 보관 폴더의 받은묶음\ 에 남깁니다.
echo  사용법 : zip 을 이 bat 위에 끌어다 놓거나, zip 을 이 bat 옆에 두고 실행 ^(가장 최근 이름^).
echo.

rem --- 폴더 찾기: 운용 PC = 이 bat 옆 output · 개발 저장소 = deploy\ 위 output
set "OUTDIR=%~dp0output"
if not exist "%OUTDIR%" set "OUTDIR=%~dp0..\output"
if not exist "%OUTDIR%" (
  echo  [오류] output 폴더를 찾지 못했습니다. coupang-analytics 폴더에서 실행하세요.
  pause
  exit /b 1
)
set "HERE=%~dp0"
set "ZIPARG=%~1"
set "SELF=%~f0"
rem --- 다른 PowerShell(7) 의 모듈 경로가 섞이지 않게(Windows PowerShell 기본 경로로)
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:SELF,[Text.Encoding]::UTF8); $m='#'+'__PS_BODY__'; iex $s.Substring($s.LastIndexOf($m))"
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo  [완료] 반영했습니다.) else (echo  [실패] 위 안내를 확인하세요 - 아무것도 지우지 않았습니다.)
pause
exit /b %RC%

#__PS_BODY__
$ErrorActionPreference = 'Stop'
function Get-Sha([string]$p) { $st = [IO.File]::OpenRead($p); try { [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($st)) } finally { $st.Close() } }
$base = Join-Path $env:OUTDIR '정산서'
$zip = $env:ZIPARG
if (-not $zip) {
  $z = Get-ChildItem -LiteralPath $env:HERE -Filter '정산서입력_*.zip' -File | Sort-Object Name | Select-Object -Last 1
  if ($z) { $zip = $z.FullName }
}
if (-not $zip -or -not (Test-Path -LiteralPath $zip)) { Write-Host '  [오류] 정산서입력_*.zip 을 찾지 못했습니다.'; exit 1 }
Write-Host "  zip : $zip"
$stamp = Get-Date -Format 'yyMMdd_HHmmss'
$keep = Join-Path $base ("입력\보관\" + $stamp)
$got = Join-Path $keep '받은묶음'
New-Item -ItemType Directory -Force -Path $got | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($zip, $got)
$added = 0; $moved = 0; $same = 0
foreach ($f in Get-ChildItem -LiteralPath $got -Recurse -File) {
  $rel = $f.FullName.Substring($got.Length + 1)
  $top = $rel.Split('\')[0]
  if ($top -ne '입력' -and $top -ne '입력_셀독') { Write-Host "  [건너뜀] 모르는 자리: $rel"; continue }
  $dst = Join-Path $base $rel
  if (Test-Path -LiteralPath $dst) {
    if ((Get-Sha $dst) -eq (Get-Sha $f.FullName)) { $same++; continue }
    $old = Join-Path $keep $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $old) | Out-Null
    Move-Item -LiteralPath $dst -Destination $old
    $moved++
  }
  New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
  Copy-Item -LiteralPath $f.FullName -Destination $dst
  $added++
  Write-Host "  + $rel"
}
Write-Host "  넣음 $added 개 (그중 옛 파일 보관 $moved 개) · 내용 같아 그대로 $same 개 · 보관 폴더 = $keep"
exit 0
