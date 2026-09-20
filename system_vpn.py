"""
System-Wide VPN & Virtual Network Adapter Controller
====================================================
Transforms the local Tor SOCKS5 proxy into a full, system-wide VPN.
Uses WireGuard's official Wintun adapter + tun2socks (Windows)
or Linux TUN interface + tun2socks (Linux).

Forces 100% of all computer background programs, browsers, and network traffic
through the rotating Tor exit node.
"""

import os
import sys
import shutil
import platform
import subprocess
import threading
import logging
from typing import Tuple, Optional

logger = logging.getLogger("TorRotator.VPN")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR = os.path.join(BASE_DIR, "vpn_adapter")

IS_WINDOWS = platform.system().lower() == "windows"
IS_LINUX = platform.system().lower() == "linux"


class SystemVpnController:
    """Manages the virtual TUN network adapter and system-wide routing."""

    def __init__(self, socks_host: str = "127.0.0.1", socks_port: int = 9050):
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.is_active = False
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None

    def get_binary_path(self) -> str:
        """Returns the path to the platform-specific tun2socks executable."""
        if IS_WINDOWS:
            return os.path.join(ADAPTER_DIR, "tun2socks-windows-amd64.exe")
        return os.path.join(ADAPTER_DIR, "tun2socks-linux-amd64")

    def is_available(self) -> bool:
        """Checks if the required virtual adapter binaries exist."""
        bin_path = self.get_binary_path()
        if not os.path.exists(bin_path):
            return False
        if IS_WINDOWS:
            wintun = os.path.join(ADAPTER_DIR, "wintun.dll")
            return os.path.exists(wintun)
        return True

    def start_vpn(self) -> Tuple[bool, str]:
        """
        Launches tun2socks with the virtual network adapter.
        Requires Administrator/root privileges for routing table modifications.
        """
        if self.is_active:
            return True, "System VPN is already active."

        if not self.is_available():
            return False, "Virtual adapter binaries missing in vpn_adapter/ directory."

        bin_path = self.get_binary_path()
        proxy_url = f"socks5://{self.socks_host}:{self.socks_port}"

        try:
            if IS_WINDOWS:
                cmd = [
                    bin_path,
                    "-device", "wintun",
                    "-proxy", proxy_url
                ]
                self._process = subprocess.Popen(
                    cmd,
                    cwd=ADAPTER_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
            elif IS_LINUX:
                enable_sh = os.path.join(BASE_DIR, "enable_vpn.sh")
                if not os.path.exists(enable_sh):
                    return False, f"Script not found: {enable_sh}"
                
                if os.geteuid() == 0:
                    cmd = [enable_sh]
                elif shutil.which("pkexec"):
                    cmd = ["pkexec", enable_sh]
                else:
                    cmd = ["sudo", enable_sh]

                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
                if res.returncode == 0:
                    self.is_active = True
                    logger.info("System-wide virtual network adapter started via enable_vpn.sh.")
                    return True, "Virtual network adapter activated. System-wide traffic routed through Tor."
                else:
                    err_msg = (res.stderr or res.stdout).strip()
                    logger.error(f"Failed to enable VPN: {err_msg}")
                    return False, f"VPN Activation failed: {err_msg}"

            # Give tun2socks a moment to initialize or fail (Windows)
            import time
            time.sleep(0.8)
            if self._process and self._process.poll() is not None:
                err_bytes = self._process.stderr.read() if self._process.stderr else b""
                err_msg = err_bytes.decode("utf-8", errors="ignore").strip()
                self._process = None
                self.is_active = False

                if "operation not permitted" in err_msg.lower() or "privilege" in err_msg.lower():
                    tip = "Run enable_vpn.bat as Administrator (Windows) or sudo ./enable_vpn.sh (Linux)."
                    return False, f"Permission Denied: Virtual Network Adapter requires root/Administrator rights. {tip}"
                return False, f"Virtual adapter failed to start: {err_msg}"

            self.is_active = True
            logger.info("System-wide virtual network adapter started.")
            return True, "Virtual network adapter activated. System-wide traffic routed through Tor."

        except subprocess.TimeoutExpired:
            self.is_active = False
            return False, "VPN Activation timed out (polkit authentication prompt was dismissed or took longer than 60 seconds)."
        except PermissionError:
            self.is_active = False
            return False, "Administrator/root privileges required to create virtual network adapter."
        except Exception as e:
            self.is_active = False
            return False, f"Failed to start virtual adapter: {e}"

    def stop_vpn(self) -> Tuple[bool, str]:
        """Terminates the tun2socks process and releases the virtual network adapter."""
        if not self.is_active and not self._process:
            return True, "VPN is not running."

        if IS_LINUX:
            disable_sh = os.path.join(BASE_DIR, "disable_vpn.sh")
            try:
                if os.path.exists(disable_sh):
                    if os.geteuid() == 0:
                        cmd = [disable_sh]
                    elif shutil.which("pkexec"):
                        cmd = ["pkexec", disable_sh]
                    else:
                        cmd = ["sudo", disable_sh]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                self.is_active = False
                logger.info("System-wide virtual network adapter stopped.")
                return True, "Virtual network adapter deactivated."
            except Exception as e:
                logger.error(f"Error stopping VPN adapter: {e}")
                return False, f"Error stopping adapter: {e}"

        try:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None

            self.is_active = False
            logger.info("System-wide virtual network adapter stopped.")
            return True, "Virtual network adapter deactivated."
        except Exception as e:
            logger.error(f"Error stopping VPN adapter: {e}")
            return False, f"Error stopping adapter: {e}"


# ================= WINDOWS / LINUX SYSTEM PROXY HELPER =================

class SystemProxyController:
    """
    Lightweight alternative: Configures the OS System Proxy (WinINet / Desktop Environment)
    Forces Chrome, Edge, Brave, Windows Update, and all system apps through Tor with ZERO drivers!
    """

    @staticmethod
    def set_system_proxy(enable: bool, host: str = "127.0.0.1", port: int = 9050) -> Tuple[bool, str]:
        """Enables or disables OS-wide system proxy."""
        if IS_WINDOWS:
            try:
                import winreg
                reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE)

                if enable:
                    proxy_server = f"socks={host}:{port}"
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
                    logger.info(f"Windows System Proxy enabled: {proxy_server}")
                    msg = f"Windows System Proxy enabled for {host}:{port}"
                else:
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    logger.info("Windows System Proxy disabled.")
                    msg = "Windows System Proxy disabled."

                winreg.CloseKey(key)

                # Broadcast internet setting change so apps immediately pick it up
                try:
                    import ctypes
                    INTERNET_OPTION_SETTINGS_CHANGED = 39
                    INTERNET_OPTION_REFRESH = 37
                    ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
                    ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
                except Exception:
                    pass

                return True, msg
            except Exception as e:
                return False, f"Failed to modify Windows System Proxy: {e}"

        elif IS_LINUX:
            try:
                # GNOME / Cinnamon / XFCE / KDE system proxy
                if enable:
                    subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "mode", "manual"], check=False)
                    subprocess.run(["gsettings", "set", "org.gnome.system.proxy.socks", "host", host], check=False)
                    subprocess.run(["gsettings", "set", "org.gnome.system.proxy.socks", "port", str(port)], check=False)
                    msg = f"Linux Desktop System Proxy enabled ({host}:{port})"
                else:
                    subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "mode", "none"], check=False)
                    msg = "Linux Desktop System Proxy disabled."
                return True, msg
            except Exception as e:
                return False, f"Failed to set Linux desktop proxy: {e}"

        return False, "Unsupported platform."
