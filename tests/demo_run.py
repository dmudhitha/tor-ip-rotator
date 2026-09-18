"""
Live demonstration runner for Tor IP Rotator.
Starts the mock Tor service, simulates CLI operations:
1. Detect initial IP
2. Execute manual circuit rotation (Option 2)
3. Execute auto-rotation test (Option 3)
4. Show logs and status
"""

import time
import sys
import os

# Add parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mock_tor_service import start_mock_tor_service
from app import TorRotator, render_banner, LOG_FILE

# Start mock service
stop_service = start_mock_tor_service()
time.sleep(0.5)

try:
    print("\n========================================================")
    print("      DEMO: TOR IP ROTATOR IN ACTION (SIMULATION)      ")
    print("========================================================\n")

    rotator = TorRotator()
    # Use HTTP for simulated IP endpoint so no SSL handshake needed for mock server
    rotator.ip_check_url = "http://api.ipify.org?format=json"
    rotator.wait_seconds = 1  # Fast wait for demo

    # 1. Connection check
    connected, msg = rotator.check_tor_connection()
    print(f"[*] Checking Tor Control Port Connection: {msg}")

    # 2. Get Initial IP
    ip, err = rotator.get_current_ip()
    print(f"[*] Initial Detected Tor Exit IP: {ip}\n")

    # Render banner
    render_banner(rotator.current_ip, "Connected", f"Every {rotator.interval_minutes} minutes (Stopped)")

    # 3. Simulate Menu Option 2: Change IP
    print("> 2 (Change IP selected)\n")
    print("Requesting new Tor circuit...\n")
    success, old_ip, new_ip, err = rotator.rotate_ip()
    if success:
        print(f"Old IP:\n{old_ip}\n")
        print(f"New IP:\n{new_ip}\n")
        print("Rotation successful.\n")
    else:
        print(f"[!] Rotation failed: {err}\n")

    # 4. Simulate Menu Option 2 again: Another manual rotation
    print("> 2 (Change IP selected second time)\n")
    print("Requesting new Tor circuit...\n")
    success, old_ip, new_ip, err = rotator.rotate_ip()
    if success:
        print(f"Old IP:\n{old_ip}\n")
        print(f"New IP:\n{new_ip}\n")
        print("Rotation successful.\n")

    # 5. Display Status (Option 5)
    print("> 5 (Status selected)")
    print("\n--- Detailed Status ---")
    print(f"Tor Connection      : Connected")
    print(f"Current Exit IP     : {rotator.current_ip}")
    print(f"SOCKS5 Proxy        : {rotator.socks_proxy_url}")
    print(f"Control Port        : {rotator.control_host}:{rotator.control_port}")
    print(f"Auto-Rotation       : Inactive")
    print(f"Configured Interval : {rotator.interval_minutes} minutes")
    print(f"Retry Count         : {rotator.retry_count}")
    print(f"Log File            : {LOG_FILE}")
    print("-----------------------\n")

    # 6. Show generated log file contents
    print("[*] Generated logs in logs/rotator.log:")
    with open(LOG_FILE, "r") as f:
        print(f.read())

    print("========================================================")
    print("              DEMO EXECUTION COMPLETED                  ")
    print("========================================================\n")

finally:
    stop_service.set()
