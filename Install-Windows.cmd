@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1"
if errorlevel 1 (
    echo.
    echo Installation did not finish. Review the message above.
    pause
    exit /b 1
)
echo.
echo MediaGrab is ready in your Start menu.
pause
