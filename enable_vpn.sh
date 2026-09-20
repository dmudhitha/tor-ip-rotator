#!/usr/bin/env bash
# ========================================================
# Tor IP Rotator - System-Wide VPN Enabler (Linux)
# Routes 100% of PC traffic through Tor using TUN adapter
# Run with: sudo ./enable_vpn.sh
# ========================================================

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Please run with sudo: sudo ./enable_vpn.sh"
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$DIR/vpn_adapter/tun2socks-linux-amd64"

echo "[*] Detecting default physical network interface and gateway..."
DEFAULT_IFACE=$(ip route show default | awk '/default/ {print $5}' | head -n1)
DEFAULT_GW=$(ip route show default | awk '/default/ {print $3}' | head -n1)
DEFAULT_IP=$(ip -4 addr show "$DEFAULT_IFACE" | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)

if [ -z "$DEFAULT_IFACE" ] || [ -z "$DEFAULT_GW" ] || [ -z "$DEFAULT_IP" ]; then
    echo "[ERROR] Could not automatically detect physical gateway / IP on $DEFAULT_IFACE."
    exit 1
fi

echo "[*] Interface: $DEFAULT_IFACE | Gateway: $DEFAULT_GW | Local IP: $DEFAULT_IP"

# Ensure Tor binds outgoing relay traffic to physical IP to prevent routing loops
echo "[*] Binding Tor daemon outbound connections to $DEFAULT_IP..."
VENV_PY="$DIR/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
    PYTHON_BIN="$VENV_PY"
else
    PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -c "
from stem.control import Controller
try:
    with Controller.from_port(port=9051) as c:
        c.authenticate()
        c.set_conf('OutboundBindAddress', '$DEFAULT_IP')
except Exception as e:
    pass
" 2>/dev/null

# Configure Policy Routing so Tor's own outbound packets bypass tun0
echo "[*] Configuring kernel policy routing for Tor relay traffic..."
ip rule del from "$DEFAULT_IP" table 100 2>/dev/null
ip route flush table 100 2>/dev/null
ip rule add from "$DEFAULT_IP" table 100 priority 100
ip route add default via "$DEFAULT_GW" dev "$DEFAULT_IFACE" table 100

echo "[*] Cleaning up any previous virtual TUN adapter..."
pkill -f tun2socks-linux-amd64 2>/dev/null || killall tun2socks-linux-amd64 2>/dev/null || true
ip route del 0.0.0.0/1 dev tun0 2>/dev/null
ip route del 128.0.0.0/1 dev tun0 2>/dev/null
ip link delete tun0 2>/dev/null

echo "[*] Creating Virtual TUN Adapter (tun0)..."
ip tuntap add mode tun dev tun0
ip addr add 198.18.0.1/15 dev tun0
ip link set dev tun0 up

echo "[*] Starting tun2socks routing engine..."
nohup "$BIN" --device tun0 --proxy socks5://127.0.0.1:9050 --interface "$DEFAULT_IFACE" </dev/null >/tmp/tun2socks.log 2>&1 &
sleep 1.5

if ! pgrep -f tun2socks-linux-amd64 >/dev/null; then
    echo "[ERROR] tun2socks failed to start. Log output:"
    cat /tmp/tun2socks.log 2>/dev/null
    exit 1
fi

# Add routes to direct all system traffic into tun0
echo "[*] Redirecting system routes into virtual adapter..."
ip route add 0.0.0.0/1 dev tun0
ip route add 128.0.0.0/1 dev tun0

echo "========================================================"
echo "[SUCCESS] System-Wide Tor VPN is now ACTIVE!"
echo "All PC applications, browsers, and services are routed through Tor."
echo "To verify in terminal: curl https://api.ipify.org"
echo "To disable and restore normal routing: sudo ./disable_vpn.sh"
echo "========================================================"
