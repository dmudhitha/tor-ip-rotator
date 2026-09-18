#!/usr/bin/env bash
# ========================================================
# Tor IP Rotator - System-Wide VPN Disabler (Linux)
# Restores original routing table and tears down TUN adapter
# Run with: sudo ./disable_vpn.sh
# ========================================================

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Please run with sudo: sudo ./disable_vpn.sh"
    exit 1
fi

echo "[*] Deactivating System-Wide Tor VPN..."

ip route del 0.0.0.0/1 dev tun0 2>/dev/null
ip route del 128.0.0.0/1 dev tun0 2>/dev/null
killall tun2socks-linux-amd64 2>/dev/null
ip link delete tun0 2>/dev/null

DEFAULT_IFACE=$(ip route show default | awk '/default/ {print $5}' | head -n1)
if [ -n "$DEFAULT_IFACE" ]; then
    DEFAULT_IP=$(ip -4 addr show "$DEFAULT_IFACE" | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)
    if [ -n "$DEFAULT_IP" ]; then
        ip rule del from "$DEFAULT_IP" table 100 2>/dev/null
    fi
fi
ip route flush table 100 2>/dev/null

echo "========================================================"
echo "[SUCCESS] System-Wide Tor VPN is now DISABLED."
echo "Standard internet routing has been restored."
echo "========================================================"
