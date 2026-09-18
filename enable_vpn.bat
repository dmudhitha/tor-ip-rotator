@echo off
REM ========================================================
REM Tor IP Rotator - System-Wide VPN Enabler (Windows)
REM Routes 100% of PC traffic through Tor using WireGuard Wintun
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

cd /d "%~dp0"

echo ========================================================
echo         Activating Full System-Wide Tor VPN
echo ========================================================

REM Step 1: Check tun2socks and wintun
if not exist "vpn_adapter\tun2socks-windows-amd64.exe" (
    echo [ERROR] vpn_adapter\tun2socks-windows-amd64.exe not found!
    pause
    exit /b 1
)

REM Step 2: Kill any existing tun2socks
taskkill /F /IM tun2socks-windows-amd64.exe >nul 2>&1

REM Step 3: Launch tun2socks with Wintun adapter in background
echo [INFO] Starting virtual network adapter (WireGuard Wintun)...
start /B "" "vpn_adapter\tun2socks-windows-amd64.exe" -device wintun -proxy socks5://127.0.0.1:9050

timeout /t 3 /nobreak >nul

REM Step 4: Configure Wintun IP and Windows routing table
echo [INFO] Configuring Windows routing table...
netsh interface ip set address name="wintun" source=static addr=198.18.0.1 mask=255.255.0.0 gateway=none >nul 2>&1
route add 0.0.0.0 mask 128.0.0.0 198.18.0.1 metric 1
route add 128.0.0.0 mask 128.0.0.0 198.18.0.1 metric 1

echo ========================================================
echo [SUCCESS] System-Wide Tor VPN is now ACTIVE!
echo Every browser, background program, and game is routed through Tor.
echo To disable and restore normal internet, run disable_vpn.bat.
echo ========================================================
pause
