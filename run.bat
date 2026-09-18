@echo off
REM Tor IP Rotator - Windows App Launcher Helper
REM Activates virtual environment and starts app.py

cd /d "%~dp0"

echo ========================================================
echo               Tor IP Rotator Launcher
echo ========================================================

REM Check if venv exists
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else if exist "..\.venv\Scripts\activate.bat" (
    echo [INFO] Activating parent virtual environment...
    call ..\.venv\Scripts\activate.bat
) else (
    echo [WARNING] .venv not detected. Using system Python.
)

python app.py
pause
