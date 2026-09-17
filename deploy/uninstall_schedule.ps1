# Unregister the coupang-analytics scheduler tasks. Called elevated by uninstall_schedule.bat.
#
# NOTE (encoding-proof): this script is intentionally PURE ASCII (no Korean text). The old version
# hard-coded the Korean task names in string literals; when the file was read in the wrong code page
# (cp949) by Windows PowerShell 5.1, the Korean bytes turned into mojibake and broke the quotes/parens,
# producing the garbled "press any key" console. We now find OUR tasks by their launch arguments
# (--auto / --resume) instead of by their (Korean) name, so no non-ASCII characters exist here.
$ErrorActionPreference = 'SilentlyContinue'

$targets = Get-ScheduledTask | Where-Object {
    $argStr = (($_.Actions | ForEach-Object { [string]$_.Arguments }) -join ' ')
    $exeStr = (($_.Actions | ForEach-Object { [string]$_.Execute })   -join ' ')
    # Match OUR tasks by their launch args (--auto / --resume). Covers both the dev/python
    # deployment (python + app_qt) and the packaged EXE deployment (a .exe launched with those
    # app-specific args). No non-ASCII here, so cp949 misreads cannot corrupt this file.
    (($argStr -match '(^|\s)--auto(\s|$)') -or ($argStr -match '(^|\s)--resume(\s|$)')) -and
    (($exeStr -match 'python') -or ($argStr -match 'app_qt') -or ($exeStr -match '(?i)\.exe(\s|"|$)'))
}

if (-not $targets) {
    Write-Host '[info] No coupang-analytics scheduler tasks found. Nothing to remove.'
    exit 0
}

foreach ($task in $targets) {
    Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false
    Write-Host ('[done] Removed task: ' + $task.TaskPath + $task.TaskName)
}
Write-Host ('[done] Total removed: ' + @($targets).Count)
