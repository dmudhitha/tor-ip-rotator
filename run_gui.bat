@echo off
REM Tor IP Rotator - Desktop GUI Launcher
REM Activates virtual environment and starts gui.py

cd /d "%~dp0"

echo ========================================================
echo             Launching Tor IP Rotator GUI
echo ========================================================

REM Check if venv exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "..\.venv\Scripts\activate.bat" (
    call ..\.venv\Scripts\activate.bat
)

python gui.py
