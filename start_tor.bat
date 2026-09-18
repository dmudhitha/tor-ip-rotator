@echo off
REM Tor IP Rotator - Windows Tor Launcher Helper
REM Launches the Tor process using tor/torrc configuration

echo ========================================================
echo         Starting Tor with Custom Configuration
echo ========================================================

cd /d "%~dp0"

REM Check if tor is in PATH
where tor >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] Found 'tor' in system PATH.
    tor -f tor\torrc
    goto end
)

REM Check local tor directory
if exist "tor\tor.exe" (
    echo [INFO] Found local tor\tor.exe.
    tor\tor.exe -f tor\torrc
    goto end
)

REM Check common installation directories
if exist "C:\Tor\tor.exe" (
    echo [INFO] Found Tor in C:\Tor\tor.exe.
    C:\Tor\tor.exe -f tor\torrc
    goto end
)

if exist "%LOCALAPPDATA%\Programs\Tor Browser\Browser\TorBrowser\Tor\tor.exe" (
    echo [INFO] Found Tor in Tor Browser directory.
    "%LOCALAPPDATA%\Programs\Tor Browser\Browser\TorBrowser\Tor\tor.exe" -f tor\torrc
    goto end
)

echo [ERROR] Tor executable not found in PATH or standard directories.
echo Please install Tor Expert Bundle from https://www.torproject.org/download/tor/
echo or place tor.exe into the tor\ directory.
pause

:end
