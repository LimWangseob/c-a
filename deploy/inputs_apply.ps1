# 정산서 입력 반영 — 개발 PC 가 만든 정산서입력_YYMMDD.zip 을 <output>\정산서\입력·입력_셀독 에 더하기만(지우기 없음 · 다른 내용이면 옛 파일을 보관으로 옮김).
# 부르는 곳 = 정산서입력_반영.bat(사람) · update.ps1(업데이트.bat — 소유자 11-25 '1, 2 모두 권장안대로 진행해줘' = 업데이트 하나로 입력까지).
param(
    [string]$OutDir = '',      # output 폴더
    [string]$Zip = '',         # 정산서입력_*.zip(없으면 Here 에서 이름 순 마지막)
    [string]$Here = ''
)
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'
function Get-Sha([string]$p) { $st = [IO.File]::OpenRead($p); try { [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($st)) } finally { $st.Close() } }
$base = Join-Path $OutDir '정산서'
$zip = $Zip
if (-not $zip) {
  $z = Get-ChildItem -LiteralPath $Here -Filter '정산서입력_*.zip' -File | Sort-Object Name | Select-Object -Last 1
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
