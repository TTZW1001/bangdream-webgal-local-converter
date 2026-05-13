@echo off
setlocal
cd /d "%~dp0"

set APP_VERSION=v0.2.0

echo Starting EXE build...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" -AppVersion "%APP_VERSION%"
set EXIT_CODE=%ERRORLEVEL%

echo.
if not "%EXIT_CODE%"=="0" (
    echo Build failed. Review the messages above.
    echo If output EXE is open, close it and try again.
    pause
    exit /b %EXIT_CODE%
)

echo Build completed.
echo Output folder: "%~dp0output"
pause
