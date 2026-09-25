@echo off
setlocal
pushd "%~dp0"
set "desktopPython=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%desktopPython%" (
    "%desktopPython%" -B -X utf8 -m desktop %*
) else (
    python -B -X utf8 -m desktop %*
)
set "desktopExit=%ERRORLEVEL%"
popd
exit /b %desktopExit%
