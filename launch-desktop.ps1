param([Parameter(ValueFromRemainingArguments=$true)][string[]]$DesktopArguments)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$desktopPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $desktopPython)) {
    Write-Error ("The project environment is missing. From this folder run:`n" +
        "  py -3.12 -m venv .venv`n" +
        "  .venv\Scripts\python.exe -m pip install -r requirements-desktop.txt")
    exit 1
}
& $desktopPython -B -X utf8 -m desktop @DesktopArguments
exit $LASTEXITCODE
