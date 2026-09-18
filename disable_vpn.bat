@echo off
REM ========================================================
REM Tor IP Rotator - System-Wide VPN Disabler (Windows)
REM Restores standard routing table and stops virtual adapter
REM Run this script as Administrator!
REM ========================================================

:: Check for administrative permissions
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Administrative permissions required.
    echo Please right-click this file and choose 'Run as administrator'.
    pause
    exit /b 1
)

echo ========================================================
echo         Deactivating System-Wide Tor VPN
echo ========================================================

echo [INFO] Removing virtual adapter routes...
route delete 0.0.0.0 mask 128.0.0.0 198.18.0.1 >nul 2>&1
route delete 128.0.0.0 mask 128.0.0.0 198.18.0.1 >nul 2>&1

echo [INFO] Stopping virtual adapter process...
taskkill /F /IM tun2socks-windows-amd64.exe >nul 2>&1

echo ========================================================
echo [SUCCESS] System-Wide Tor VPN is now DISABLED.
echo Normal network routing has been restored.
echo ========================================================
pause
