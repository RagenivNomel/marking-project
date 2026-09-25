param([Parameter(ValueFromRemainingArguments=$true)][string[]]$DesktopArguments)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$desktopPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $desktopPython)) {
    $desktopPython = (Get-Command python -ErrorAction Stop).Source
}
& $desktopPython -B -X utf8 -m desktop @DesktopArguments
exit $LASTEXITCODE
