@echo off
rem Double-click to set up the kaomoji picker. See install.ps1 for what it does.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
