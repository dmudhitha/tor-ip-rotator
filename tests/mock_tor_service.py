"""
Mock Tor Service for Local Prototyping & Testing
=================================================
Runs a lightweight mock Tor daemon with:
1. Control Port (127.0.0.1:9051): Responds to PROTOCOLINFO, AUTHENTICATE, SIGNAL NEWNYM.
2. SOCKS5 Server (127.0.0.1:9050): Handles SOCKS5 handshakes and intercepts
   http/https requests to simulate public IP checks with changing Tor exit IPs.
"""

import socket
import threading
import time
import select
from typing import List

MOCK_IPS = [
    "185.220.101.5",
    "195.176.3.19",
    "51.89.24.12",
    "109.70.100.22",
    "185.241.208.155"
]

current_ip_index = 0
lock = threading.Lock()


def get_current_mock_ip() -> str:
    global current_ip_index
    with lock:
        return MOCK_IPS[current_ip_index % len(MOCK_IPS)]


def advance_mock_ip():
    global current_ip_index
    with lock:
        current_ip_index += 1
        return MOCK_IPS[current_ip_index % len(MOCK_IPS)]


# ==================== CONTROL PORT SERVER ====================

def handle_control_client(conn: socket.socket):
    try:
        buffer = ""
        while True:
            data = conn.recv(1024).decode("utf-8", errors="ignore")
            if not data:
                break
            buffer += data
            while "\r\n" in buffer or "\n" in buffer:
                if "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                else:
                    line, buffer = buffer.split("\n", 1)

                line = line.strip()
                if not line:
                    continue

                cmd_parts = line.split()
                cmd = cmd_parts[0].upper()

                if cmd == "PROTOCOLINFO":
                    response = (
                        "250-PROTOCOLINFO 1\r\n"
                        "250-AUTH METHODS=NULL\r\n"
                        "250-VERSION Tor=\"0.4.8.10\"\r\n"
                        "250 OK\r\n"
                    )
                    conn.sendall(response.encode("utf-8"))

                elif cmd == "AUTHENTICATE":
                    conn.sendall(b"250 OK\r\n")

                elif cmd == "SIGNAL":
                    if len(cmd_parts) > 1 and cmd_parts[1].upper() == "NEWNYM":
                        new_ip = advance_mock_ip()
                        conn.sendall(b"250 OK\r\n")
                    else:
                        conn.sendall(b"250 OK\r\n")

                elif cmd == "GETINFO":
                    # Stem checks getinfo
                    info_key = cmd_parts[1] if len(cmd_parts) > 1 else ""
                    if "status/circuit-established" in info_key:
                        conn.sendall(b"250-status/circuit-established=1\r\n250 OK\r\n")
                    else:
                        conn.sendall(b"250 OK\r\n")

                elif cmd == "QUIT":
                    conn.sendall(b"250 closing connection\r\n")
                    return
                else:
                    conn.sendall(b"250 OK\r\n")

    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_control_server(stop_event: threading.Event, port=9051):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
    except OSError:
        server.close()
        return

    server.listen(5)
    server.settimeout(0.5)

    while not stop_event.is_set():
        try:
            conn, _ = server.accept()
            t = threading.Thread(target=handle_control_client, args=(conn,), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break
    server.close()


def run_socks_server(stop_event: threading.Event, port=9050):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
    except OSError:
        server.close()
        return

    server.listen(5)
    server.settimeout(0.5)

    while not stop_event.is_set():
        try:
            conn, _ = server.accept()
            t = threading.Thread(target=handle_socks_client, args=(conn,), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break
    server.close()


def start_mock_tor_service():
    stop_event = threading.Event()
    t1 = threading.Thread(target=run_control_server, args=(stop_event, 9051), daemon=True)
    t2 = threading.Thread(target=run_socks_server, args=(stop_event, 9050), daemon=True)
    t1.start()
    t2.start()
    return stop_event


if __name__ == "__main__":
    stop_ev = start_mock_tor_service()
    print("Mock Tor Service running on Control: 9051, SOCKS5: 9050")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_ev.set()
        print("Mock Tor stopped.")
