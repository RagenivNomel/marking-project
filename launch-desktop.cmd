@echo off
setlocal
pushd "%~dp0"
set "desktopPython=%~dp0.venv\Scripts\python.exe"
if not exist "%desktopPython%" (
    echo The project environment is missing. From this folder run:
    echo   py -3.12 -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
    popd
    exit /b 1
)
"%desktopPython%" -B -X utf8 -m desktop %*
set "desktopExit=%ERRORLEVEL%"
popd
exit /b %desktopExit%
