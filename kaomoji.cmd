@echo off
rem Starts the kaomoji picker in the background (tray icon, Ctrl+Alt+K). See README.md.
rem Uses the .venv that install.cmd makes; without one, whatever Python is on this PC.
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0kaomoji.py"
) else (
    where pythonw >nul 2>nul && (start "" pythonw "%~dp0kaomoji.py") || (start "" pyw -3 "%~dp0kaomoji.py")
)
