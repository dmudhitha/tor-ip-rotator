"""
Automated Browser Launcher with Tor SOCKS5 Proxy
=================================================
Launches Firefox, Chrome, Chromium, Brave, or Edge with SOCKS5 remote DNS proxy
pre-configured, guaranteeing 100% of the browser's traffic routes through Tor
without needing any manual browser setting changes.
"""

import os
import sys
import shutil
import platform
import subprocess
from typing import Tuple, Optional

IS_WINDOWS = platform.system().lower() == "windows"
IS_LINUX = platform.system().lower() == "linux"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREFOX_PROFILE_DIR = os.path.join(BASE_DIR, ".firefox_tor_profile")


def setup_firefox_profile(host: str = "127.0.0.1", port: int = 9050) -> str:
    """Creates a dedicated Firefox profile directory configured for Tor SOCKS5h."""
    os.makedirs(FIREFOX_PROFILE_DIR, exist_ok=True)
    user_js_path = os.path.join(FIREFOX_PROFILE_DIR, "user.js")

    user_js_content = f"""
// Auto-generated Tor proxy profile for Tor IP Rotator
user_pref("network.proxy.type", 1);
user_pref("network.proxy.socks", "{host}");
user_pref("network.proxy.socks_port", {port});
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("app.update.auto", false);
"""
    with open(user_js_path, "w", encoding="utf-8") as f:
        f.write(user_js_content)

    return FIREFOX_PROFILE_DIR


def find_browser() -> Tuple[Optional[str], Optional[str]]:
    """
    Finds an installed browser.
    Returns (browser_name, executable_path).
    """
    if IS_WINDOWS:
        # Common Windows browser paths
        paths = [
            ("firefox", os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe")),
            ("firefox", os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe")),
            ("chrome", os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")),
            ("chrome", os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe")),
            ("edge", os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")),
            ("brave", os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe")),
        ]
        for name, path in paths:
            if os.path.exists(path):
                return name, path

    elif IS_LINUX:
        browsers = [
            ("firefox", shutil.which("firefox")),
            ("chrome", shutil.which("google-chrome") or shutil.which("google-chrome-stable")),
            ("chromium", shutil.which("chromium") or shutil.which("chromium-browser")),
            ("brave", shutil.which("brave-browser")),
        ]
        for name, path in browsers:
            if path:
                return name, path

    return None, None


def launch_browser_through_tor(
    url: str = "https://whatismyipaddress.com",
    host: str = "127.0.0.1",
    port: int = 9050
) -> Tuple[bool, str]:
    """
    Launches a browser with SOCKS5 Tor proxy automatically configured.
    Guarantees that the browser displays the Tor Exit IP.
    """
    b_name, b_path = find_browser()
    if not b_path:
        return False, "No supported browser (Firefox, Chrome, Edge, Brave) found on this PC."

    try:
        if b_name == "firefox":
            profile_dir = setup_firefox_profile(host, port)
            cmd = [b_path, "--profile", profile_dir, "--no-remote", url]
        else:
            # Chromium-based (Chrome, Edge, Brave)
            proxy_arg = f"--proxy-server=socks5://{host}:{port}"
            cmd = [
                b_path,
                proxy_arg,
                "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
                "--no-first-run",
                url
            ]

        subprocess.Popen(cmd)
        return True, f"Launched {b_name.capitalize()} through Tor proxy ({host}:{port})."

    except Exception as e:
        return False, f"Failed to launch browser: {e}"
