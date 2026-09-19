#!/usr/bin/env python3
"""
Tor IP Rotator - Windows Prototype
===================================
A modular Python utility to monitor and rotate Tor exit node IP addresses on Windows.
Communicates with Tor via its ControlPort using Stem and verifies public exit IPs
via Tor's SOCKS5 proxy using Requests.
"""

import os
import sys
import time
import json
import logging
import threading
from typing import Optional, Tuple, Dict, Any

# Third-party dependencies
try:
    import requests
except ImportError:
    print("CRITICAL: 'requests' library is not installed. Run: pip install requests PySocks")
    sys.exit(1)

try:
    from stem import Signal, SocketError
    from stem.control import Controller
    from stem.connection import (
        AuthenticationFailure,
        PasswordAuthFailed,
        MissingPassword,
        IncorrectCookieSize,
        UnreadableCookieFile,
    )
except ImportError:
    print("CRITICAL: 'stem' library is not installed. Run: pip install stem")
    sys.exit(1)


# Path configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "rotator.log")


def setup_logger() -> logging.Logger:
    """Configures structured logging to logs/rotator.log matching project standards."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("TorRotator")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if reinitialized
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        # Format: YYYY-MM-DD HH:MM:SS LEVEL message
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()


def load_config(config_path: str = CONFIG_FILE) -> Dict[str, Any]:
    """Loads configuration from JSON file or returns secure defaults."""
    default_config = {
        "rotation_interval_minutes": 30,
        "tor_control_host": "127.0.0.1",
        "tor_control_port": 9051,
        "tor_socks_host": "127.0.0.1",
        "tor_socks_port": 9050,
        "tor_control_password": "",
        "tor_cookie_path": "",
        "ip_check_url": "https://api.ipify.org?format=json",
        "rotation_retry_count": 3,
        "rotation_wait_seconds": 15
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except Exception as e:
            print(f"[!] Warning: Could not parse {config_path} ({e}). Using default settings.")

    return default_config


class TorRotator:
    """Core controller for managing Tor circuits and verifying IP rotation."""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config = load_config(config_path)
        self.socks_host = self.config.get("tor_socks_host", "127.0.0.1")
        self.socks_port = self.config.get("tor_socks_port", 9050)
        self.control_host = self.config.get("tor_control_host", "127.0.0.1")
        self.control_port = self.config.get("tor_control_port", 9051)
        self.ip_check_url = self.config.get("ip_check_url", "https://api.ipify.org?format=json")
        self.retry_count = int(self.config.get("rotation_retry_count", 3))
        self.wait_seconds = int(self.config.get("rotation_wait_seconds", 15))
        self.interval_minutes = int(self.config.get("rotation_interval_minutes", 30))
        self.exit_country = self.config.get("exit_country", "").strip()

        # Internal state
        self.current_ip: Optional[str] = None
        self.current_country: Optional[str] = None
        self.is_connected: bool = False
        self._auto_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._rotation_lock = threading.Lock()

    def _authenticate_controller(self, controller: Controller):
        """Authenticates controller using password, cookie path, or auto-cookie discovery."""
        password = self.config.get("tor_control_password", "").strip()
        cookie_path = self.config.get("tor_cookie_path", "").strip()
        if password:
            controller.authenticate(password=password)
        elif cookie_path:
            controller.authenticate(cookie_path=cookie_path)
        else:
            controller.authenticate()

    @property
    def socks_proxy_url(self) -> str:
        """
        Returns SOCKS5 proxy URL with remote DNS resolution (socks5h://)
        to prevent DNS leaks.
        """
        return f"socks5h://{self.socks_host}:{self.socks_port}"

    def get_proxies_dict(self) -> Dict[str, str]:
        """Returns proxy dictionary for the requests library."""
        proxy = self.socks_proxy_url
        return {
            "http": proxy,
            "https": proxy
        }

    @staticmethod
    def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
        """Checks if a TCP port is currently listening."""
        import socket
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, socket.error):
            return False

    def set_exit_country(self, country_code: str) -> Tuple[bool, Optional[str]]:
        """
        Dynamically sets or clears Tor ExitNodes to a specific ISO country code (e.g. 'us', 'de', 'ch', 'nl').
        Pass '' or 'any' to reset to global exit nodes.
        """
        code = country_code.strip().lower()
        try:
            with Controller.from_port(address=self.control_host, port=self.control_port) as controller:
                self._authenticate_controller(controller)
                if code and code not in ["any", "all", "global", "none"]:
                    controller.set_conf("ExitNodes", f"{{{code}}}")
                    controller.set_conf("StrictNodes", "1")
                    self.exit_country = code.upper()
                    logger.info(f"Tor exit country set to: {self.exit_country}")
                else:
                    controller.reset_conf("ExitNodes")
                    controller.reset_conf("StrictNodes")
                    self.exit_country = ""
                    logger.info("Tor exit country reset to Any (Global)")
                return True, None
        except Exception as e:
            err = f"Failed to set exit country: {e}"
            logger.error(err)
            return False, err

    def check_tor_connection(self) -> Tuple[bool, str]:
        """
        Verifies whether Tor ControlPort is accessible and authenticates.
        Handles missing service, bad ports, and authentication failures.
        """
        try:
            with Controller.from_port(address=self.control_host, port=self.control_port) as controller:
                self._authenticate_controller(controller)
                self.is_connected = True
                logger.info("Tor connected")
                return True, "Connected"

        except SocketError as e:
            self.is_connected = False
            msg_str = str(e).lower()
            if "connection refused" in msg_str or "actively refused" in msg_str or "10061" in msg_str:
                # Check if SOCKS port is open!
                if self.is_port_open(self.socks_host, self.socks_port):
                    err_msg = (
                        f"Tor SOCKS proxy is active on {self.socks_host}:{self.socks_port},\n"
                        f"but ControlPort {self.control_port} is disabled!\n"
                        f"Please enable 'ControlPort {self.control_port}' and 'CookieAuthentication 1' in your torrc."
                    )
                else:
                    err_msg = "ERROR: Tor is not running.\nPlease start the Tor service."
            else:
                err_msg = "ERROR: Unable to connect to Tor Control Port."
            return False, err_msg

        except (MissingPassword, PasswordAuthFailed):
            self.is_connected = False
            return False, "ERROR: Tor ControlPort authentication failed (Invalid or missing password)."

        except (IncorrectCookieSize, UnreadableCookieFile):
            self.is_connected = False
            return False, "ERROR: Tor cookie authentication failed (Cannot read auth cookie file)."

        except AuthenticationFailure as e:
            self.is_connected = False
            return False, f"ERROR: Tor authentication failed: {e}"

        except Exception as e:
            self.is_connected = False
            return False, f"ERROR: Unexpected connection error: {e}"

    def get_current_ip(self, retries: int = 3) -> Tuple[Optional[str], Optional[str]]:
        """
        Retrieves the public Tor exit IP and country metadata through the Tor SOCKS5 proxy.
        Retries up to `retries` times with exponential backoff.
        """
        proxies = self.get_proxies_dict()
        backoff = 2

        # Prefer IP endpoints that return country metadata when default url is used
        urls_to_try = [self.ip_check_url]
        if "ipify" in self.ip_check_url:
            urls_to_try = ["http://ip-api.com/json", self.ip_check_url]

        for attempt in range(1, retries + 1):
            for check_url in urls_to_try:
                try:
                    response = requests.get(
                        check_url,
                        proxies=proxies,
                        timeout=15
                    )
                    response.raise_for_status()

                    # Parse JSON or fallback to raw text
                    try:
                        data = response.json()
                        ip = data.get("ip") or data.get("query", "")
                        ip = ip.strip()

                        # Extract country if available
                        country_name = data.get("country")
                        country_code = data.get("countryCode") or data.get("country_code")
                        if country_name and country_code:
                            self.current_country = f"{country_name} ({country_code})"
                        elif country_name:
                            self.current_country = country_name
                    except ValueError:
                        ip = response.text.strip()

                    if ip:
                        self.current_ip = ip
                        return ip, None

                except requests.exceptions.RequestException:
                    continue

            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2

    def request_new_circuit(self) -> Tuple[bool, Optional[str]]:
        """
        Connects to the Tor ControlPort and issues the NEWNYM signal.
        Enforces Tor rate-limiting cooldown if necessary.
        """
        try:
            with Controller.from_port(address=self.control_host, port=self.control_port) as controller:
                password = self.config.get("tor_control_password", "").strip()
                cookie_path = self.config.get("tor_cookie_path", "").strip()

                if password:
                    controller.authenticate(password=password)
                elif cookie_path:
                    controller.authenticate(cookie_path=cookie_path)
                else:
                    controller.authenticate()

                # Check NEWNYM cooldown
                newnym_wait = controller.get_newnym_wait()
                if newnym_wait > 0:
                    time.sleep(newnym_wait)

                controller.signal(Signal.NEWNYM)
                logger.info("Requesting new Tor circuit")
                return True, None

        except SocketError:
            return False, "ERROR: Unable to connect to Tor Control Port."
        except Exception as e:
            return False, f"ERROR: Failed to request new circuit: {e}"

    def rotate_ip(self) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Full rotation pipeline:
        1. Query old IP.
        2. Signal NEWNYM.
        3. Wait for new circuit.
        4. Query new IP.
        5. If identical, retry up to rotation_retry_count.
        Returns (success, old_ip, new_ip, error_message).
        """
        with self._rotation_lock:
            # Step 1: Detect current IP
            old_ip, err = self.get_current_ip(retries=self.retry_count)
            if not old_ip:
                # If we had a cached IP, use that as old_ip reference
                old_ip = self.current_ip or "Unknown"

            for attempt in range(1, self.retry_count + 1):
                # Step 2: Request NEWNYM
                sig_ok, sig_err = self.request_new_circuit()
                if not sig_ok:
                    return False, old_ip, None, sig_err

                # Step 3: Wait for circuit to establish
                time.sleep(self.wait_seconds)

                # Step 4: Check new IP
                new_ip, ip_err = self.get_current_ip(retries=self.retry_count)
                if not new_ip:
                    if attempt < self.retry_count:
                        continue
                    return False, old_ip, None, ip_err

                # Step 5: Verify change
                if new_ip != old_ip:
                    self.current_ip = new_ip
                    logger.info(f"New IP: {new_ip}")
                    logger.info("Rotation successful")
                    return True, old_ip, new_ip, None
                else:
                    # Same IP returned
                    print(f"\n[Attempt {attempt}/{self.retry_count}] Tor circuit changed, but exit IP remained the same. Retrying...")
                    time.sleep(5)

            return False, old_ip, new_ip, f"Exit IP remained unchanged ({new_ip}) after {self.retry_count} attempts."

    def _auto_rotation_worker(self):
        """Worker thread executing automatic periodic IP rotations."""
        logger.info(f"Auto-rotation started (Interval: {self.interval_minutes} minutes)")

        while not self._stop_event.is_set():
            # Wait for interval or until stopped
            wait_seconds = self.interval_minutes * 60
            # Wait in small slices to respond promptly to stop event
            elapsed = 0
            while elapsed < wait_seconds and not self._stop_event.is_set():
                time.sleep(1)
                elapsed += 1

            if self._stop_event.is_set():
                break

            # Perform scheduled rotation
            try:
                success, old_ip, new_ip, err = self.rotate_ip()
                if success:
                    print(f"\n[Auto-Rotation] Successfully rotated IP: {old_ip} -> {new_ip}")
                else:
                    print(f"\n[Auto-Rotation] Warning: Rotation failed: {err}")
            except Exception as e:
                print(f"\n[Auto-Rotation] Error during rotation: {e}")

        logger.info("Auto-rotation stopped")

    def start_auto_rotation(self, interval_minutes: Optional[int] = None) -> bool:
        """Starts automatic background IP rotation."""
        if self._auto_thread and self._auto_thread.is_alive():
            return False

        if interval_minutes and interval_minutes > 0:
            self.interval_minutes = interval_minutes

        self._stop_event.clear()
        self._auto_thread = threading.Thread(target=self._auto_rotation_worker, daemon=True)
        self._auto_thread.start()
        return True

    def stop_auto_rotation(self) -> bool:
        """Stops automatic background IP rotation."""
        if not self._auto_thread or not self._auto_thread.is_alive():
            return False

        self._stop_event.set()
        self._auto_thread.join(timeout=3)
        self._auto_thread = None
        return True

    def is_auto_rotation_running(self) -> bool:
        """Returns True if the auto-rotation thread is currently active."""
        return self._auto_thread is not None and self._auto_thread.is_alive()


def get_direct_real_ip(timeout: int = 6) -> Tuple[Optional[str], Optional[str]]:
    """Fetches the user's real direct ISP IP without proxy."""
    urls = [
        "https://api.ipify.org?format=json",
        "https://api.ipify.org",
        "https://icanhazip.com",
        "http://ip-api.com/json"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=timeout)
            if r.status_code == 200:
                try:
                    data = r.json()
                    ip = data.get("ip") or data.get("query")
                    if ip:
                        return ip.strip(), None
                except Exception:
                    pass
                text = r.text.strip()
                if text:
                    return text, None
        except Exception:
            continue
    return None, "Failed to reach direct IP service"


def start_tor_process() -> Tuple[bool, str]:
    """Starts user-owned local Tor background process."""
    import shutil
    import subprocess
    try:
        tor_bin = shutil.which("tor") or shutil.which("tor.exe")
        if not tor_bin and platform.system().lower() == "windows":
            for p in [
                os.path.expandvars(r"%ProgramFiles%\Tor Browser\Browser\TorBrowser\Tor\tor.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tor Browser\Browser\TorBrowser\Tor\tor.exe"),
                r"C:\Tor\tor.exe",
            ]:
                if os.path.exists(p):
                    tor_bin = p
                    break
        if not tor_bin:
            return False, "Tor executable not found in PATH or standard installation directories."

        base_dir = os.path.dirname(os.path.abspath(__file__))
        torrc_path = os.path.join(base_dir, "tor", "torrc")
        data_dir = os.path.join(base_dir, "tor", "data")
        os.makedirs(data_dir, exist_ok=True)

        cmd = [tor_bin, "-f", torrc_path, "--DataDirectory", data_dir]
        if platform.system().lower() != "windows":
            cmd.extend(["--RunAsDaemon", "1"])
            subprocess.run(cmd, check=False)
        else:
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
        return True, "Tor daemon started."
    except Exception as e:
        return False, f"Failed to start Tor process: {e}"


def stop_tor_process() -> Tuple[bool, str]:
    """Stops the Tor process."""
    import subprocess
    try:
        if platform.system().lower() == "windows":
            subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["killall", "tor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Tor process stopped."
    except Exception as e:
        return False, f"Failed to stop Tor process: {e}"


def render_banner(real_ip: str, tor_ip: Optional[str], tor_status: str, rotation_status: str):
    """Renders the CLI status banner clearly separating Real ISP IP and Tor Exit IP."""
    print("\n" + "=" * 44)
    print("           🧅 Tor IP Rotator (CLI)")
    print("=" * 44)
    print(f" Real ISP IP : {real_ip or 'Detecting...'}")
    if tor_status == "Connected":
        print(f" Tor Exit IP : {tor_ip or 'Fetching...'}")
        print(f" Tor Status  : ● Connected (Routing Active)")
    else:
        print(f" Tor Exit IP : [Tor is Stopped]")
        print(f" Tor Status  : ● Disabled (Browsing with Real IP)")
    print(f" Rotation    : {rotation_status}")
    print("=" * 44)
    print("Commands:\n")
    print("1. Show IPs (Real ISP IP & Tor Exit IP)")
    print("2. Change Tor IP (Request New Circuit)")
    print("3. Start Auto-Rotation")
    print("4. Stop Auto-Rotation")
    print("5. Detailed Status")
    print("6. 🚀 Enable / Start Tor")
    print("7. 🛑 Stop Tor & Browse with Real IP")
    print("8. Exit")
    print()


def run_cli():
    """Main CLI loop."""
    rotator = TorRotator()

    # Initial check
    print("[*] Detecting network interfaces and IP addresses...")
    real_ip, _ = get_direct_real_ip()
    connected, conn_msg = rotator.check_tor_connection()
    if connected:
        tor_ip, _ = rotator.get_current_ip(retries=2)
    else:
        tor_ip = None

    while True:
        tor_status = "Connected" if rotator.is_connected else "Disabled"
        rot_status = f"Every {rotator.interval_minutes} min (Running)" if rotator.is_auto_rotation_running() else f"Every {rotator.interval_minutes} min (Stopped)"

        render_banner(real_ip or "Unknown", tor_ip, tor_status, rot_status)

        try:
            choice = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            rotator.stop_auto_rotation()
            break

        if choice == "1":
            print("\n--- Current IP Information ---")
            r_ip, r_err = get_direct_real_ip()
            if r_ip:
                real_ip = r_ip
                print(f" [✓] Real ISP IP (Direct) : {real_ip}")
            else:
                print(f" [!] Real ISP IP error   : {r_err}")

            if rotator.is_connected:
                t_ip, t_err = rotator.get_current_ip()
                if t_ip:
                    tor_ip = t_ip
                    loc = rotator.current_country or "Global"
                    print(f" [✓] Tor Exit IP (Proxied): {tor_ip} (Location: {loc})")
                else:
                    print(f" [!] Tor Exit IP error   : {t_err}")
            else:
                print(" [-] Tor Exit IP (Proxied): Tor is currently STOPPED")
            print("------------------------------\n")

        elif choice == "2":
            if not rotator.is_connected:
                print("\n[!] Tor is currently stopped. Choose option 6 to enable Tor first.\n")
                continue
            print("\nRequesting new Tor circuit...\n")
            success, old_ip, new_ip, err = rotator.rotate_ip()
            if success:
                tor_ip = new_ip
                print(f"Old Tor IP:\n{old_ip}\n")
                print(f"New Tor IP:\n{new_ip}\n")
                print("Rotation successful.\n")
            else:
                print(f"[!] Rotation failed: {err}\n")

        elif choice == "3":
            if not rotator.is_connected:
                print("\n[!] Tor is currently stopped. Choose option 6 to enable Tor first.\n")
                continue
            if rotator.is_auto_rotation_running():
                print(f"\nAuto-rotation is already running (Interval: {rotator.interval_minutes} minutes).\n")
            else:
                print(f"\nStarting Auto Rotation with interval: {rotator.interval_minutes} minutes.")
                print("Allowed options: [1] 1 min (Test)  [2] 5 min  [3] 30 min  [4] 60 min  [Enter] Keep configured")
                sub = input("Select interval or press Enter: ").strip()
                interval_map = {"1": 1, "2": 5, "3": 30, "4": 60}
                selected_interval = interval_map.get(sub, rotator.interval_minutes)

                rotator.start_auto_rotation(interval_minutes=selected_interval)
                print(f"Auto-rotation started! Will rotate every {selected_interval} minute(s).\n")

        elif choice == "4":
            if rotator.is_auto_rotation_running():
                rotator.stop_auto_rotation()
                print("\nAuto-rotation stopped.\n")
            else:
                print("\nAuto-rotation is not currently running.\n")

        elif choice == "5":
            conn, msg = rotator.check_tor_connection()
            status_text = "Connected" if conn else f"Disconnected ({msg})"
            auto_text = "Active" if rotator.is_auto_rotation_running() else "Inactive"
            print("\n--- Detailed Status ---")
            print(f"Real ISP IP         : {real_ip or 'Unknown'}")
            print(f"Tor Connection      : {status_text}")
            print(f"Current Exit IP     : {rotator.current_ip or 'None (Tor Stopped)'}")
            print(f"SOCKS5 Proxy        : {rotator.socks_proxy_url}")
            print(f"Control Port        : {rotator.control_host}:{rotator.control_port}")
            print(f"Auto-Rotation       : {auto_text}")
            print(f"Configured Interval : {rotator.interval_minutes} minutes")
            print(f"Retry Count         : {rotator.retry_count}")
            print(f"Log File            : {LOG_FILE}")
            print("-----------------------\n")

        elif choice == "6":
            print("\n[*] Starting Tor daemon and establishing circuits...")
            started, msg = start_tor_process()
            time.sleep(2.5)
            conn, cmsg = rotator.check_tor_connection()
            if conn:
                rotator.is_connected = True
                print("[✓] Tor connected successfully.")
                t_ip, _ = rotator.get_current_ip(retries=3)
                if t_ip:
                    tor_ip = t_ip
                    print(f"[✓] Assigned Tor Exit IP: {tor_ip}")
                else:
                    print("[!] Tor circuit establishing, please wait a moment...")
            else:
                print(f"[!] Could not connect to Tor: {cmsg}")
                if "connection refused" in cmsg.lower() and platform.system().lower() == "linux":
                    print("[!] Tip: If Tor was stopped, run 'sudo systemctl start tor' or start user tor.")

        elif choice == "7":
            print("\n[*] Stopping Tor routing and restoring direct connection...")
            # 1. Stop auto-rotation if active
            if rotator.is_auto_rotation_running():
                rotator.stop_auto_rotation()
                print("[✓] Auto-rotation stopped.")

            # 2. Deactivate system-wide TUN VPN and OS proxy
            try:
                from system_vpn import SystemVpnController, SystemProxyController
                vpn = SystemVpnController()
                vpn.stop_vpn()
                SystemProxyController.set_system_proxy(enable=False)
                print("[✓] System VPN & Proxy routing deactivated.")
            except Exception as e:
                print(f"[!] Note on VPN deactivation: {e}")

            # 3. Stop local Tor background daemon
            stop_tor_process()
            rotator.is_connected = False
            rotator.current_ip = None
            tor_ip = None
            print("[✓] Tor service stopped.")

            # 4. Detect real direct ISP IP (without SOCKS proxy)
            print("[*] Verifying direct real ISP IP...")
            r_ip, _ = get_direct_real_ip()
            if r_ip:
                real_ip = r_ip
            print(f"\n========================================")
            print(f" [✓] Direct Connection Active!")
            print(f" [✓] Real ISP IP: {real_ip}")
            print(f"========================================\n")

            # 5. Open standard default browser
            print("[*] Launching standard browser with your real IP...")
            try:
                import webbrowser
                webbrowser.open("https://whatismyipaddress.com")
                print("[✓] Opened browser at https://whatismyipaddress.com\n")
            except Exception as e:
                print(f"[!] Could not launch browser: {e}\n")

        elif choice == "8":
            print("\nStopping services and exiting...")
            rotator.stop_auto_rotation()
            break

        else:
            print("\nInvalid selection. Please choose an option from 1 to 8.")


if __name__ == "__main__":
    if "--gui" in sys.argv or "-g" in sys.argv:
        try:
            from gui import run_gui
            run_gui()
        except ImportError as e:
            print(f"[!] Unable to launch GUI: {e}. Run: pip install customtkinter")
            sys.exit(1)
    else:
        run_cli()

