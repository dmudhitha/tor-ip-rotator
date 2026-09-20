#!/usr/bin/env python3
"""
Tor IP Rotator - Desktop GUI
=============================
A modern, dark-themed desktop application built with CustomTkinter.
Features:
- Real-time Tor connection status indicator
- Current Public Exit IP card with copy functionality
- Manual "Rotate IP Now" action with animated feedback
- Configurable Auto-Rotation with live countdown timer
- Embedded live console streaming from logs/rotator.log
- Built-in Simulation Mode toggle (offline testing without Tor installed)
- Settings panel with persistent JSON configuration
"""

import os
import sys
import time
import json
import shutil
import platform
import subprocess
import webbrowser
import requests
import logging
import threading
from typing import Optional

# Path setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import TorRotator, load_config, CONFIG_FILE, LOG_FILE, logger
from system_vpn import SystemVpnController, SystemProxyController
from browser_launcher import launch_browser_through_tor

try:
    import customtkinter as ctk
except ImportError:
    print("CRITICAL: 'customtkinter' is not installed. Run: pip install customtkinter")
    sys.exit(1)

# Set appearance mode and color theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class GuiLogHandler(logging.Handler):
    """Logging handler that pipes log records into the GUI console textbox."""

    def __init__(self, text_widget: ctk.CTkTextbox, master: "TorRotatorGUI"):
        super().__init__()
        self.text_widget = text_widget
        self.master = master

    def emit(self, record):
        if getattr(self.master, "is_closing", False):
            return
        msg = self.format(record)
        def append():
            try:
                if not getattr(self.master, "is_closing", False) and self.master.winfo_exists():
                    self.text_widget.configure(state="normal")
                    self.text_widget.insert("end", msg + "\n")
                    self.text_widget.see("end")
                    self.text_widget.configure(state="disabled")
            except Exception:
                pass
        try:
            self.master._safe_after(0, append)
        except Exception:
            pass


class TorRotatorGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🧅 Tor IP Rotator – Windows Prototype")
        self.geometry("900x720")
        self.minsize(800, 600)

        # Teardown safety flag
        self.is_closing = False

        # Suppress harmless background Tcl/Tk teardown after-script callbacks
        self.report_callback_exception = lambda exc, val, tb: None
        try:
            self.tk.call("proc", "bgerror", "msg", "")
        except Exception:
            pass

        # Core rotator backend
        self.rotator = TorRotator()
        self.vpn_controller = SystemVpnController(socks_host=self.rotator.socks_host, socks_port=self.rotator.socks_port)
        self.mock_service_stop: Optional[threading.Event] = None
        self.is_sim_mode = False
        self.is_tor_active = False
        self.real_isp_ip: Optional[str] = None

        # Countdown tracker
        self.seconds_remaining = 0
        self.countdown_timer_id = None
        self.is_rotating = False

        # Build UI
        self._build_header()
        self._build_tabs()
        self._setup_logging_pipeline()

        # System taskbar notification tray
        self.tray_icon = None
        self._setup_system_tray()

        # Window closing handler (hides to taskbar tray)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close_clicked)

        # Initial status check in background immediately on open
        self.after(100, self._initial_check)

    def _safe_after(self, ms: int, callback):
        """Thread-safe and teardown-safe wrapper around Tkinter after()."""
        if self.is_closing:
            return None
        try:
            if self.winfo_exists():
                return self.after(ms, callback)
        except Exception:
            pass
        return None

    # ================= UI BUILDERS =================

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#181a1f")
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Title & Subtitle
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=12)

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🧅 Tor IP Rotator",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            title_box,
            text="Automated Tor Circuit & Public Exit IP Manager",
            font=ctk.CTkFont(size=12),
            text_color="#8a8f98"
        )
        sub_lbl.pack(anchor="w")

        # Right-side status & action button
        right_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=16, pady=12)

        self.tray_btn = ctk.CTkButton(
            right_box,
            text="📥 Hide to Tray",
            command=self._hide_to_tray,
            fg_color="#2b2d35",
            hover_color="#3a3d47",
            font=ctk.CTkFont(size=12),
            width=115,
            height=32
        )
        self.tray_btn.pack(side="right", padx=(8, 0))

        self.tor_header_btn = ctk.CTkButton(
            right_box,
            text="🚀 Enable Tor",
            command=self._toggle_tor_header,
            fg_color="#10b981",
            hover_color="#059669",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=210,
            height=32
        )
        self.tor_header_btn.pack(side="right", padx=(8, 0))

        self.status_badge = ctk.CTkLabel(
            right_box,
            text="● Tor Disabled (Real IP)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#9ca3af"
        )
        self.status_badge.pack(side="right", padx=10)

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.tab_dash = self.tabview.add("📊 Dashboard")
        self.tab_settings = self.tabview.add("⚙️ Settings")

        self._build_dashboard_tab()
        self._build_settings_tab()

    def _build_dashboard_tab(self):
        # 1. IP Display Card
        ip_card = ctk.CTkFrame(self.tab_dash, corner_radius=12, fg_color="#1f232b")
        ip_card.pack(fill="x", padx=12, pady=10)

        ip_top = ctk.CTkFrame(ip_card, fg_color="transparent")
        ip_top.pack(fill="x", padx=16, pady=(12, 4))

        self.ip_caption = ctk.CTkLabel(
            ip_top,
            text="CURRENT IP (DIRECT REAL CONNECTION)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#9ca3af"
        )
        self.ip_caption.pack(side="left")

        self.proxy_info_lbl = ctk.CTkLabel(
            ip_top,
            text="SOCKS5: socks5h://127.0.0.1:9050 (Remote DNS)",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280"
        )
        self.proxy_info_lbl.pack(side="right")

        # Huge IP Label & Country Tag
        ip_center = ctk.CTkFrame(ip_card, fg_color="transparent")
        ip_center.pack(fill="x", padx=16, pady=(4, 12))

        ip_left_box = ctk.CTkFrame(ip_center, fg_color="transparent")
        ip_left_box.pack(side="left")

        self.ip_display = ctk.CTkLabel(
            ip_left_box,
            text="---.---.---.---",
            font=ctk.CTkFont(size=36, weight="bold"),
            text_color="#ffffff"
        )
        self.ip_display.pack(anchor="w")

        self.country_lbl = ctk.CTkLabel(
            ip_left_box,
            text="📍 Location: Global",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#10b981"
        )
        self.country_lbl.pack(anchor="w", pady=(2, 0))

        self.real_ip_lbl = ctk.CTkLabel(
            ip_left_box,
            text="🏠 Real ISP IP: Detecting...",
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af"
        )
        self.real_ip_lbl.pack(anchor="w", pady=(3, 0))

        # Action buttons on IP Card
        btn_box = ctk.CTkFrame(ip_center, fg_color="transparent")
        btn_box.pack(side="right")

        self.copy_btn = ctk.CTkButton(
            btn_box,
            text="📋 Copy IP",
            command=self._copy_ip,
            width=90,
            height=34,
            fg_color="#374151",
            hover_color="#4b5563"
        )
        self.copy_btn.pack(side="left", padx=6)

        self.refresh_btn = ctk.CTkButton(
            btn_box,
            text="🔄 Refresh",
            command=self._trigger_refresh_ip,
            width=90,
            height=34,
            fg_color="#374151",
            hover_color="#4b5563"
        )
        self.refresh_btn.pack(side="left", padx=6)

        self.rotate_btn = ctk.CTkButton(
            btn_box,
            text="⚡ Rotate IP Now",
            command=self._trigger_manual_rotation,
            font=ctk.CTkFont(weight="bold"),
            width=130,
            height=34,
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        self.rotate_btn.pack(side="left", padx=5)

        self.browser_btn = ctk.CTkButton(
            btn_box,
            text="🌐 Open Browser",
            command=self._launch_browser,
            font=ctk.CTkFont(weight="bold"),
            width=130,
            height=34,
            fg_color="#059669",
            hover_color="#047857"
        )
        self.browser_btn.pack(side="left", padx=5)

        # 2. Controls & Auto-Rotation Card
        ctrl_card = ctk.CTkFrame(self.tab_dash, corner_radius=12, fg_color="#1f232b")
        ctrl_card.pack(fill="x", padx=12, pady=8)

        ctrl_content = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl_content.pack(fill="x", padx=16, pady=12)

        # Left: Auto-rotation Switch & Selector
        left_ctrl = ctk.CTkFrame(ctrl_content, fg_color="transparent")
        left_ctrl.pack(side="left")

        self.auto_switch = ctk.CTkSwitch(
            left_ctrl,
            text="Auto-Rotation",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_auto_rotation
        )
        self.auto_switch.pack(side="left", padx=(0, 14))

        interval_lbl = ctk.CTkLabel(left_ctrl, text="Interval:", text_color="#9ca3af")
        interval_lbl.pack(side="left", padx=(0, 4))

        self.interval_menu = ctk.CTkOptionMenu(
            left_ctrl,
            values=["1 Minute (Test)", "5 Minutes", "30 Minutes", "60 Minutes"],
            command=self._on_interval_changed,
            width=135
        )
        self.interval_menu.set(f"{self.rotator.interval_minutes} Minutes" if self.rotator.interval_minutes in [5, 30, 60] else ("1 Minute (Test)" if self.rotator.interval_minutes == 1 else "30 Minutes"))
        self.interval_menu.pack(side="left", padx=(0, 14))

        country_lbl = ctk.CTkLabel(left_ctrl, text="Country:", text_color="#9ca3af")
        country_lbl.pack(side="left", padx=(0, 4))

        self.country_menu = ctk.CTkOptionMenu(
            left_ctrl,
            values=[
                "🌐 Any (Worldwide)",
                "🇺🇸 United States (US)",
                "🇩🇪 Germany (DE)",
                "🇳🇱 Netherlands (NL)",
                "🇨🇭 Switzerland (CH)",
                "🇬🇧 United Kingdom (GB)",
                "🇨🇦 Canada (CA)",
                "🇫🇷 France (FR)",
                "🇸🇪 Sweden (SE)",
                "🇯🇵 Japan (JP)",
                "🇸🇬 Singapore (SG)",
                "🇦🇺 Australia (AU)"
            ],
            command=self._on_country_changed,
            width=175
        )
        self.country_menu.set("🌐 Any (Worldwide)")
        self.country_menu.pack(side="left")

        # Right: Countdown Display
        right_ctrl = ctk.CTkFrame(ctrl_content, fg_color="transparent")
        right_ctrl.pack(side="right")

        self.countdown_lbl = ctk.CTkLabel(
            right_ctrl,
            text="Next Rotation: Inactive",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#9ca3af"
        )
        self.countdown_lbl.pack(side="right", padx=10)

        # 3. System-Wide Traffic Routing Card
        vpn_card = ctk.CTkFrame(self.tab_dash, corner_radius=12, fg_color="#1f232b")
        vpn_card.pack(fill="x", padx=12, pady=8)

        vpn_content = ctk.CTkFrame(vpn_card, fg_color="transparent")
        vpn_content.pack(fill="x", padx=16, pady=10)

        self.sys_proxy_switch = ctk.CTkSwitch(
            vpn_content,
            text="🖥️ OS System Proxy (Route Browsers)",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_system_proxy
        )
        self.sys_proxy_switch.pack(side="left", padx=(0, 20))

        self.tun_vpn_btn = ctk.CTkButton(
            vpn_content,
            text="🛡️ Virtual Adapter VPN (Wintun)",
            command=self._toggle_virtual_adapter_vpn,
            fg_color="#374151",
            hover_color="#4b5563",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32
        )
        self.tun_vpn_btn.pack(side="left", padx=10)

        self.vpn_status_lbl = ctk.CTkLabel(
            vpn_content,
            text="VPN: Inactive",
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af"
        )
        self.vpn_status_lbl.pack(side="right", padx=10)

        # 4. Live Console / Event Log
        log_header = ctk.CTkFrame(self.tab_dash, fg_color="transparent")
        log_header.pack(fill="x", padx=14, pady=(12, 4))

        log_title = ctk.CTkLabel(
            log_header,
            text="ACTIVITY LOG & ROTATION EVENTS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#9ca3af"
        )
        log_title.pack(side="left")

        clear_btn = ctk.CTkButton(
            log_header,
            text="Clear",
            command=self._clear_logs,
            width=60,
            height=24,
            fg_color="#374151",
            hover_color="#4b5563",
            font=ctk.CTkFont(size=11)
        )
        clear_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            self.tab_dash,
            corner_radius=10,
            fg_color="#131519",
            text_color="#e5e7eb",
            font=ctk.CTkFont(family="Courier", size=11),
            wrap="char"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

    def _build_settings_tab(self):
        card = ctk.CTkFrame(self.tab_settings, corner_radius=12, fg_color="#1f232b")
        card.pack(fill="both", expand=True, padx=16, pady=16)

        title = ctk.CTkLabel(
            card,
            text="Tor Network & Proxy Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.pack(anchor="w", padx=20, pady=(20, 10))

        form_frame = ctk.CTkFrame(card, fg_color="transparent")
        form_frame.pack(fill="x", padx=20, pady=10)

        # Field: SOCKS Host & Port
        lbl_socks = ctk.CTkLabel(form_frame, text="Tor SOCKS5 Host & Port:", anchor="w")
        lbl_socks.grid(row=0, column=0, sticky="w", pady=8)
        self.ent_socks_host = ctk.CTkEntry(form_frame, width=150)
        self.ent_socks_host.insert(0, str(self.rotator.socks_host))
        self.ent_socks_host.grid(row=0, column=1, padx=6, sticky="w")
        self.ent_socks_port = ctk.CTkEntry(form_frame, width=80)
        self.ent_socks_port.insert(0, str(self.rotator.socks_port))
        self.ent_socks_port.grid(row=0, column=2, padx=6, sticky="w")

        # Field: Control Host & Port
        lbl_ctrl = ctk.CTkLabel(form_frame, text="Tor Control Host & Port:", anchor="w")
        lbl_ctrl.grid(row=1, column=0, sticky="w", pady=8)
        self.ent_ctrl_host = ctk.CTkEntry(form_frame, width=150)
        self.ent_ctrl_host.insert(0, str(self.rotator.control_host))
        self.ent_ctrl_host.grid(row=1, column=1, padx=6, sticky="w")
        self.ent_ctrl_port = ctk.CTkEntry(form_frame, width=80)
        self.ent_ctrl_port.insert(0, str(self.rotator.control_port))
        self.ent_ctrl_port.grid(row=1, column=2, padx=6, sticky="w")

        # Field: IP Check URL
        lbl_url = ctk.CTkLabel(form_frame, text="Public IP API Check URL:", anchor="w")
        lbl_url.grid(row=2, column=0, sticky="w", pady=8)
        self.ent_ip_url = ctk.CTkEntry(form_frame, width=280)
        self.ent_ip_url.insert(0, str(self.rotator.ip_check_url))
        self.ent_ip_url.grid(row=2, column=1, columnspan=2, padx=6, sticky="w")

        # Field: Cooldown Wait Seconds
        lbl_wait = ctk.CTkLabel(form_frame, text="Rotation Stabilization Wait (seconds):", anchor="w")
        lbl_wait.grid(row=3, column=0, sticky="w", pady=8)
        self.ent_wait = ctk.CTkEntry(form_frame, width=80)
        self.ent_wait.insert(0, str(self.rotator.wait_seconds))
        self.ent_wait.grid(row=3, column=1, padx=6, sticky="w")

        # Field: Retry Count
        lbl_retry = ctk.CTkLabel(form_frame, text="Max Retry Count on Same IP:", anchor="w")
        lbl_retry.grid(row=4, column=0, sticky="w", pady=8)
        self.ent_retry = ctk.CTkEntry(form_frame, width=80)
        self.ent_retry.insert(0, str(self.rotator.retry_count))
        self.ent_retry.grid(row=4, column=1, padx=6, sticky="w")

        # Save Button
        self.save_btn = ctk.CTkButton(
            card,
            text="💾 Save Configuration",
            command=self._save_settings,
            font=ctk.CTkFont(weight="bold"),
            width=180,
            height=36,
            fg_color="#10b981",
            hover_color="#059669"
        )
        self.save_btn.pack(anchor="w", padx=20, pady=20)

    def _setup_logging_pipeline(self):
        """Attaches custom handler to logger to pipe events into the GUI console."""
        gui_handler = GuiLogHandler(self.log_textbox, self)
        formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        gui_handler.setFormatter(formatter)
        logger.addHandler(gui_handler)

        # Load existing lines from rotator.log if present
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-30:]
                self.log_textbox.configure(state="normal")
                for line in lines:
                    self.log_textbox.insert("end", line)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
            except Exception:
                pass

    # ================= EVENT HANDLERS & THREADING =================

    def _auto_start_tor_if_needed(self) -> bool:
        """Attempts to start the Tor daemon if it is not currently running."""
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

            if tor_bin:
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
                logger.info("Local Tor daemon auto-started.")
                return True
        except Exception as e:
            logger.warning(f"Could not auto-start Tor: {e}")
        return False

    def _stop_tor_daemon(self):
        """Terminates the local Tor background process."""
        try:
            if platform.system().lower() == "windows":
                subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["killall", "tor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.rotator.is_connected = False
            self.rotator.current_ip = None
            logger.info("Tor daemon process stopped.")
        except Exception as e:
            logger.warning(f"Error stopping Tor process: {e}")

    def _initial_check(self):
        """Initial background connection and IP detection test on application startup."""
        def run():
            if self.is_closing:
                return
            self._update_status("● Checking Connection...", "#f59e0b")
            self._update_ip("Fetching IP...")

            # 1. Fetch real direct ISP IP without proxy
            real_ip = None
            try:
                resp = requests.get("https://api.ipify.org", timeout=6)
                if resp.status_code == 200:
                    real_ip = resp.text.strip()
                    self.real_isp_ip = real_ip
                    self._safe_after(0, lambda: self.real_ip_lbl.configure(text=f"🏠 Real ISP IP: {real_ip} (Direct Connection)"))
                    logger.info(f"Direct connection checked. Real ISP IP: {real_ip}")
            except Exception as e:
                logger.warning(f"Could not fetch initial real IP: {e}")

            # 2. Check if Tor is actively running and connected
            connected, msg = self.rotator.check_tor_connection()
            if not connected:
                # Check if SOCKS port is responsive
                if self.rotator.is_port_open(self.rotator.socks_host, self.rotator.socks_port):
                    connected = True

            if connected:
                self.is_tor_active = True
                self._update_status("● Connected", "#10b981")
                if hasattr(self, "ip_caption"):
                    self._safe_after(0, lambda: self.ip_caption.configure(
                        text="CURRENT TOR EXIT IP",
                        text_color="#3b82f6"
                    ))
                if hasattr(self, "tor_header_btn"):
                    self._safe_after(0, lambda: self.tor_header_btn.configure(
                        state="normal",
                        text="🛑 Stop Tor & Browse Real IP",
                        fg_color="#dc2626",
                        hover_color="#b91c1c"
                    ))
                if real_ip and hasattr(self, "real_ip_lbl"):
                    self._safe_after(0, lambda: self.real_ip_lbl.configure(text=f"🏠 Real ISP IP: {real_ip} (Direct Connection)"))

                # Detect and display Tor Exit IP
                ip, err = self.rotator.get_current_ip(retries=3)
                if ip:
                    self._update_ip(ip)
                    logger.info(f"Tor is active. Public Tor Exit IP is {ip}")
                else:
                    self._update_ip("Connected (Circuit Building...)")
            else:
                self.is_tor_active = False
                self._update_status("● Tor Disabled (Real IP)", "#9ca3af")
                if hasattr(self, "ip_caption"):
                    self._safe_after(0, lambda: self.ip_caption.configure(
                        text="CURRENT IP (DIRECT REAL CONNECTION)",
                        text_color="#9ca3af"
                    ))
                if hasattr(self, "tor_header_btn"):
                    self._safe_after(0, lambda: self.tor_header_btn.configure(
                        state="normal",
                        text="🚀 Enable Tor",
                        fg_color="#10b981",
                        hover_color="#059669"
                    ))
                if hasattr(self, "real_ip_lbl"):
                    self._safe_after(0, lambda: self.real_ip_lbl.configure(text="🧅 Tor Status: Disabled / Stopped"))

                if real_ip:
                    self._update_ip(real_ip, "📍 Location: Direct ISP Connection (Real IP)")
                else:
                    self._update_ip("Direct Real IP", "📍 Location: Direct ISP Connection (Real IP)")

        threading.Thread(target=run, daemon=True).start()

    def _update_status(self, text: str, color: str):
        self._safe_after(0, lambda: self.status_badge.configure(text=text, text_color=color))

    def _update_ip(self, ip_text: str, location_text: Optional[str] = None):
        self._safe_after(0, lambda: self.ip_display.configure(text=ip_text))
        if location_text:
            self._safe_after(0, lambda: self.country_lbl.configure(text=location_text))
        elif self.is_tor_active:
            loc = self.rotator.current_country
            loc_text = f"📍 Location: {loc}" if loc else "📍 Location: Global Exit Node"
            self._safe_after(0, lambda: self.country_lbl.configure(text=loc_text))
        else:
            self._safe_after(0, lambda: self.country_lbl.configure(text="📍 Location: Direct ISP Connection (Real IP)"))

    def _on_country_changed(self, choice: str):
        """Switches Tor exit node country policy and immediately triggers circuit rotation."""
        mapping = {
            "🌐 Any (Worldwide)": "",
            "🇺🇸 United States (US)": "us",
            "🇩🇪 Germany (DE)": "de",
            "🇳🇱 Netherlands (NL)": "nl",
            "🇨🇭 Switzerland (CH)": "ch",
            "🇬🇧 United Kingdom (GB)": "gb",
            "🇨🇦 Canada (CA)": "ca",
            "🇫🇷 France (FR)": "fr",
            "🇸🇪 Sweden (SE)": "se",
            "🇯🇵 Japan (JP)": "jp",
            "🇸🇬 Singapore (SG)": "sg",
            "🇦🇺 Australia (AU)": "au"
        }
        code = mapping.get(choice, "")
        ok, err = self.rotator.set_exit_country(code)
        if ok:
            logger.info(f"Target exit country selected: {choice}. Requesting new circuit...")
            self._trigger_manual_rotation()
        else:
            logger.error(f"Failed to set exit country: {err}")

    def _toggle_system_proxy(self):
        """Enables or disables OS System-wide proxy."""
        enable = (self.sys_proxy_switch.get() == 1)
        success, msg = SystemProxyController.set_system_proxy(enable, host=self.rotator.socks_host, port=self.rotator.socks_port)
        if success:
            logger.info(msg)
        else:
            logger.warning(f"Could not update OS System Proxy: {msg}")

    def _toggle_virtual_adapter_vpn(self):
        """Toggles the tun2socks virtual network adapter (Wintun/TUN) to route 100% of PC traffic."""
        if not self.vpn_controller.is_active:
            if not self.is_tor_active:
                logger.warning("Tor must be enabled before activating Virtual Adapter VPN. Click '🚀 Enable Tor' first.")
                self.vpn_status_lbl.configure(text="VPN: Enable Tor First!", text_color="#f59e0b")
                self._safe_after(3000, lambda: self.vpn_status_lbl.configure(text="VPN: Inactive", text_color="#9ca3af"))
                return

            self.tun_vpn_btn.configure(state="disabled", text="⏳ Starting VPN...")
            def run():
                success, msg = self.vpn_controller.start_vpn()
                if success:
                    self._safe_after(0, lambda: self.tun_vpn_btn.configure(
                        state="normal",
                        text="🛡️ Virtual Adapter: ACTIVE",
                        fg_color="#10b981",
                        hover_color="#059669"
                    ))
                    self._safe_after(0, lambda: self.vpn_status_lbl.configure(text="VPN: 100% PC Traffic Routed", text_color="#10b981"))
                    logger.info("Virtual adapter VPN activated.")
                else:
                    self._safe_after(0, lambda: self.tun_vpn_btn.configure(
                        state="normal",
                        text="🛡️ Virtual Adapter VPN (Wintun)",
                        fg_color="#374151"
                    ))
                    self._safe_after(0, lambda: self.vpn_status_lbl.configure(text="VPN: Error", text_color="#ef4444"))
                    logger.error(f"VPN Activation failed: {msg}")
            threading.Thread(target=run, daemon=True).start()
        else:
            self.tun_vpn_btn.configure(state="disabled", text="⏳ Stopping VPN...")
            def run():
                self.vpn_controller.stop_vpn()
                self._safe_after(0, lambda: self.tun_vpn_btn.configure(
                    state="normal",
                    text="🛡️ Virtual Adapter VPN (Wintun)",
                    fg_color="#374151",
                    hover_color="#4b5563"
                ))
                self._safe_after(0, lambda: self.vpn_status_lbl.configure(text="VPN: Inactive", text_color="#9ca3af"))
                logger.info("Virtual adapter VPN stopped.")
            threading.Thread(target=run, daemon=True).start()

    def _launch_browser(self):
        """Launches browser. If Tor is active, routes through Tor proxy; otherwise opens with direct Real IP."""
        self.browser_btn.configure(state="disabled", text="⏳ Launching...")
        def run():
            if self.is_tor_active:
                ok, msg = launch_browser_through_tor(
                    url="https://whatismyipaddress.com",
                    host=self.rotator.socks_host,
                    port=self.rotator.socks_port
                )
                if ok:
                    logger.info(msg)
                else:
                    logger.error(f"Browser launch failed: {msg}")
            else:
                try:
                    webbrowser.open("https://whatismyipaddress.com")
                    logger.info("Opened default browser at https://whatismyipaddress.com (Direct Real IP)")
                except Exception as e:
                    logger.error(f"Browser launch failed: {e}")
            self._safe_after(1500, lambda: self.browser_btn.configure(state="normal", text="🌐 Open Browser"))
        threading.Thread(target=run, daemon=True).start()

    def _copy_ip(self):
        ip = self.ip_display.cget("text")
        if ip and "---" not in ip and "Disconnected" not in ip and "Fetching" not in ip:
            self.clipboard_clear()
            self.clipboard_append(ip)
            self.copy_btn.configure(text="✓ Copied!", fg_color="#10b981")
            self._safe_after(1500, lambda: self.copy_btn.configure(text="📋 Copy IP", fg_color="#374151"))

    def _clear_logs(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def _toggle_tor_header(self):
        """Toggles between Tor routing and Direct Real IP mode from the top header."""
        if self.is_tor_active:
            self._stop_tor_and_browse_real()
        else:
            self._enable_tor_mode()

    def _enable_tor_mode(self):
        """Starts Tor daemon, connects, queries new Tor exit IP, and updates header button to Stop."""
        if hasattr(self, "tor_header_btn"):
            self.tor_header_btn.configure(state="disabled", text="⏳ Starting Tor...")

        def run():
            logger.info("Enabling Tor service and routing...")
            self._update_status("● Starting Tor...", "#f59e0b")
            self._update_ip("Connecting to Tor...", "📍 Location: Establishing Tor Circuit...")

            started = self._auto_start_tor_if_needed()
            time.sleep(2.5)

            connected, msg = self.rotator.check_tor_connection()
            if connected:
                self.is_tor_active = True
                self._update_status("● Connected", "#10b981")
                if hasattr(self, "ip_caption"):
                    self._safe_after(0, lambda: self.ip_caption.configure(text="CURRENT TOR EXIT IP", text_color="#3b82f6"))
                if hasattr(self, "tor_header_btn"):
                    self._safe_after(0, lambda: self.tor_header_btn.configure(
                        state="normal",
                        text="🛑 Stop Tor & Browse Real IP",
                        fg_color="#dc2626",
                        hover_color="#b91c1c"
                    ))
                ip, err = self.rotator.get_current_ip(retries=3)
                if ip:
                    self._update_ip(ip)
                    logger.info(f"Tor re-enabled. Public Exit IP: {ip}")
                else:
                    self._update_ip("Connected")
                if hasattr(self, "real_ip_lbl") and hasattr(self, "real_isp_ip") and self.real_isp_ip:
                    self._safe_after(0, lambda: self.real_ip_lbl.configure(text=f"🏠 Real ISP IP: {self.real_isp_ip} (Direct Connection)"))
            else:
                self._update_status("● Tor Start Failed", "#ef4444")
                self._update_ip("Failed to Start", "📍 Location: Unavailable")
                if hasattr(self, "tor_header_btn"):
                    self._safe_after(0, lambda: self.tor_header_btn.configure(
                        state="normal",
                        text="🚀 Enable Tor",
                        fg_color="#10b981",
                        hover_color="#059669"
                    ))
                logger.error(f"Failed to start Tor: {msg}")

        threading.Thread(target=run, daemon=True).start()

    def _stop_tor_and_browse_real(self):
        """Stops Tor daemon, tears down TUN VPN/proxy, detects real ISP IP, and opens default browser."""
        if hasattr(self, "tor_header_btn"):
            self.tor_header_btn.configure(state="disabled", text="⏳ Stopping Tor...")

        def run():
            logger.info("Deactivating Tor, VPN, and restoring direct ISP connection...")
            self._update_status("● Stopping Tor & VPN...", "#f59e0b")

            # 1. Stop auto-rotation if active
            if self.rotator.is_auto_rotation_running():
                self.rotator.stop_auto_rotation()
                self._safe_after(0, lambda: self.auto_switch.deselect())
                self._safe_after(0, lambda: self.countdown_lbl.configure(text="Inactive", text_color="#9ca3af"))
                logger.info("Auto-rotation stopped.")

            # 2. Deactivate system VPN adapter and OS proxy
            try:
                self.vpn_controller.stop_vpn()
                SystemProxyController.set_system_proxy(enable=False)
                self._safe_after(0, lambda: self.tun_vpn_btn.configure(
                    state="normal",
                    text="🛡️ Virtual Adapter VPN (Wintun)",
                    fg_color="#374151",
                    hover_color="#4b5563"
                ))
                self._safe_after(0, lambda: self.vpn_status_lbl.configure(text="VPN: Inactive", text_color="#9ca3af"))
                self._safe_after(0, lambda: self.sys_proxy_switch.deselect())
                logger.info("System-wide VPN and proxy disabled.")
            except Exception as e:
                logger.warning(f"Error disabling VPN: {e}")

            # 3. Stop local Tor background daemon
            self._stop_tor_daemon()

            self.is_tor_active = False
            self._update_status("● Tor Disabled (Real IP)", "#9ca3af")
            if hasattr(self, "ip_caption"):
                self._safe_after(0, lambda: self.ip_caption.configure(
                    text="CURRENT IP (DIRECT REAL CONNECTION)",
                    text_color="#9ca3af"
                ))
            if hasattr(self, "real_ip_lbl"):
                self._safe_after(0, lambda: self.real_ip_lbl.configure(text="🧅 Tor Status: Disabled / Stopped"))

            # 4. Detect real direct ISP IP without proxy
            try:
                direct_resp = requests.get("https://api.ipify.org", timeout=8)
                if direct_resp.status_code == 200:
                    real_ip = direct_resp.text.strip()
                    self.real_isp_ip = real_ip
                    self._update_ip(real_ip, "📍 Location: Direct ISP Connection (Real IP)")
                    logger.info(f"Direct connection active. Real ISP IP: {real_ip}")
                else:
                    self._update_ip("Direct Real IP", "📍 Location: Direct ISP Connection (Real IP)")
            except Exception as e:
                logger.warning(f"Direct IP check error: {e}")
                self._update_ip("Real IP (Check Browser)", "📍 Location: Direct ISP Connection (Real IP)")

            # 5. Open standard browser with real IP
            try:
                webbrowser.open("https://whatismyipaddress.com")
                logger.info("Opened default browser at https://whatismyipaddress.com with real IP")
            except Exception as e:
                logger.error(f"Failed to open browser: {e}")

            # Update top button to "🚀 Enable Tor"
            if hasattr(self, "tor_header_btn"):
                self._safe_after(0, lambda: self.tor_header_btn.configure(
                    state="normal",
                    text="🚀 Enable Tor",
                    fg_color="#10b981",
                    hover_color="#059669"
                ))

        threading.Thread(target=run, daemon=True).start()

    def _trigger_refresh_ip(self):
        self.refresh_btn.configure(state="disabled")
        def run():
            self._update_status("● Checking IP...", "#f59e0b")
            try:
                r_resp = requests.get("https://api.ipify.org", timeout=5)
                if r_resp.status_code == 200:
                    self.real_isp_ip = r_resp.text.strip()
                    if self.is_tor_active and hasattr(self, "real_ip_lbl"):
                        self._safe_after(0, lambda: self.real_ip_lbl.configure(text=f"🏠 Real ISP IP: {self.real_isp_ip} (Direct Connection)"))
            except Exception:
                pass

            if self.is_tor_active:
                ip, err = self.rotator.get_current_ip(retries=3)
                if ip:
                    self._update_ip(ip)
                    connected, _ = self.rotator.check_tor_connection()
                    status_txt = "● Connected" if connected else "● SOCKS Active"
                    self._update_status(status_txt, "#10b981")
                else:
                    self._update_status("● Check Failed", "#ef4444")
            else:
                try:
                    resp = requests.get("https://api.ipify.org", timeout=6)
                    if resp.status_code == 200:
                        real_ip = resp.text.strip()
                        self._update_ip(real_ip, "📍 Location: Direct ISP Connection (Real IP)")
                        self._update_status("● Tor Disabled (Real IP)", "#9ca3af")
                    else:
                        self._update_status("● Check Failed", "#ef4444")
                except Exception as e:
                    logger.warning(f"Error refreshing direct IP: {e}")
                    self._update_status("● Check Failed", "#ef4444")
            self._safe_after(0, lambda: self.refresh_btn.configure(state="normal"))
        threading.Thread(target=run, daemon=True).start()

    def _trigger_manual_rotation(self):
        if self.is_rotating or self.is_closing:
            return
        if not self.is_tor_active:
            logger.warning("Cannot rotate IP: Tor is currently stopped. Click '🚀 Enable Tor' first.")
            self._update_status("● Enable Tor First", "#f59e0b")
            self._safe_after(2500, lambda: self._update_status("● Tor Disabled (Real IP)", "#9ca3af"))
            return
        self.is_rotating = True
        self.rotate_btn.configure(state="disabled", text="⏳ Rotating...")
        self._update_status("● Rotating Circuit...", "#f59e0b")

        def run():
            success, old_ip, new_ip, err = self.rotator.rotate_ip()
            if success:
                self._update_ip(new_ip)
                self._update_status("● Connected", "#10b981")
            else:
                self._update_status("● Rotation Failed", "#ef4444")
                logger.error(f"Manual rotation error: {err}")

            self._safe_after(0, self._finish_rotation)

        threading.Thread(target=run, daemon=True).start()

    def _finish_rotation(self):
        if self.is_closing:
            return
        self.is_rotating = False
        self.rotate_btn.configure(state="normal", text="⚡ Rotate IP Now")
        # Reset countdown if auto-rotation is running
        if self.auto_switch.get() == 1:
            self.seconds_remaining = self.rotator.interval_minutes * 60

    def _on_interval_changed(self, choice: str):
        mapping = {
            "1 Minute (Test)": 1,
            "5 Minutes": 5,
            "30 Minutes": 30,
            "60 Minutes": 60
        }
        mins = mapping.get(choice, 30)
        self.rotator.interval_minutes = mins
        logger.info(f"Rotation interval updated to {mins} minute(s)")
        if self.auto_switch.get() == 1:
            self.seconds_remaining = mins * 60

    def _toggle_auto_rotation(self):
        if self.auto_switch.get() == 1:
            if not self.is_tor_active:
                logger.warning("Cannot activate auto-rotation: Tor is stopped. Click '🚀 Enable Tor' first.")
                self.auto_switch.deselect()
                self._update_status("● Enable Tor First", "#f59e0b")
                self._safe_after(2500, lambda: self._update_status("● Tor Disabled (Real IP)", "#9ca3af"))
                return
            self.seconds_remaining = self.rotator.interval_minutes * 60
            self._update_countdown_label()
            self._start_countdown_loop()
            logger.info(f"Auto-rotation activated from GUI (Every {self.rotator.interval_minutes} minutes)")
        else:
            self._stop_countdown_loop()
            self.countdown_lbl.configure(text="Next Rotation: Inactive", text_color="#9ca3af")
            logger.info("Auto-rotation deactivated from GUI")

    def _start_countdown_loop(self):
        self._stop_countdown_loop()
        self._tick_countdown()

    def _stop_countdown_loop(self):
        if self.countdown_timer_id:
            try:
                self.after_cancel(self.countdown_timer_id)
            except Exception:
                pass
            self.countdown_timer_id = None

    def _tick_countdown(self):
        if self.auto_switch.get() != 1 or self.is_closing:
            return

        if self.seconds_remaining > 0:
            self.seconds_remaining -= 1
            self._update_countdown_label()
            self.countdown_timer_id = self._safe_after(1000, self._tick_countdown)
        else:
            # Trigger rotation
            self._trigger_manual_rotation()
            self.seconds_remaining = self.rotator.interval_minutes * 60
            self.countdown_timer_id = self._safe_after(1000, self._tick_countdown)

    def _update_countdown_label(self):
        if self.is_closing:
            return
        mins = self.seconds_remaining // 60
        secs = self.seconds_remaining % 60
        time_str = f"{mins:02d}m {secs:02d}s"
        self.countdown_lbl.configure(
            text=f"Next Rotation in: {time_str}",
            text_color="#10b981"
        )

    def _save_settings(self):
        try:
            cfg = {
                "rotation_interval_minutes": self.rotator.interval_minutes,
                "tor_socks_host": self.ent_socks_host.get().strip(),
                "tor_socks_port": int(self.ent_socks_port.get().strip()),
                "tor_control_host": self.ent_ctrl_host.get().strip(),
                "tor_control_port": int(self.ent_ctrl_port.get().strip()),
                "ip_check_url": self.ent_ip_url.get().strip(),
                "rotation_wait_seconds": int(self.ent_wait.get().strip()),
                "rotation_retry_count": int(self.ent_retry.get().strip())
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

            # Apply to current instance
            self.rotator.config = cfg
            self.rotator.socks_host = cfg["tor_socks_host"]
            self.rotator.socks_port = cfg["tor_socks_port"]
            self.rotator.control_host = cfg["tor_control_host"]
            self.rotator.control_port = cfg["tor_control_port"]
            self.rotator.ip_check_url = cfg["ip_check_url"]
            self.rotator.wait_seconds = cfg["rotation_wait_seconds"]
            self.rotator.retry_count = cfg["rotation_retry_count"]

            self.proxy_info_lbl.configure(text=f"SOCKS5: {self.rotator.socks_proxy_url} (Remote DNS)")
            self.save_btn.configure(text="✓ Saved!", fg_color="#059669")
            self._safe_after(1500, lambda: self.save_btn.configure(text="💾 Save Configuration", fg_color="#10b981"))
            logger.info("Configuration saved successfully from GUI")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")

    def _create_tray_image(self):
        """Creates an onion-style icon for the taskbar system tray."""
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((4, 4, 60, 60), fill='#7c3aed', outline='#a78bfa', width=3)
            draw.ellipse((14, 14, 50, 50), fill='#9333ea', outline='#c084fc', width=2)
            draw.ellipse((24, 24, 40, 40), fill='#ffffff')
            return img
        except Exception:
            return None

    def _toggle_tray_window(self):
        """Toggles window visibility on left-click of tray icon."""
        try:
            if self.state() == "withdrawn" or not self.winfo_viewable():
                self._show_from_tray()
            else:
                self._hide_to_tray()
        except Exception:
            self._show_from_tray()

    def _show_tray_popup_menu(self, x: int, y: int):
        """Displays native dark popup menu at coordinates for right-click on Linux."""
        try:
            import tkinter as tk
            menu = tk.Menu(
                self,
                tearoff=0,
                bg="#181a1f",
                fg="#f3f4f6",
                activebackground="#2563eb",
                activeforeground="#ffffff",
                font=("Helvetica", 10),
                relief="solid",
                bd=1
            )
            menu.add_command(label="🧅 Show Tor IP Rotator", command=self._show_from_tray)
            menu.add_command(label="📥 Hide to Tray", command=self._hide_to_tray)
            menu.add_separator()
            if self.is_tor_active:
                menu.add_command(label="⚡ Rotate IP Now", command=self._trigger_manual_rotation)
                menu.add_command(label="🛑 Stop Tor & Real IP", command=self._stop_tor_and_browse_real)
            else:
                menu.add_command(label="🚀 Enable Tor", command=self._enable_tor_mode)
            menu.add_separator()
            menu.add_command(label="❌ Quit Application", command=self._quit_fully)
            self._tray_tk_menu = menu

            # Display menu at cursor
            self._tray_tk_menu.tk_popup(int(x), int(y))
        except Exception as e:
            logger.warning(f"Error showing tray popup: {e}")
        finally:
            if hasattr(self, "_tray_tk_menu") and self._tray_tk_menu:
                self._tray_tk_menu.grab_release()

    def _setup_system_tray(self):
        """Initializes the background taskbar notification tray icon with full right-click support."""
        try:
            if platform.system().lower() != "windows":
                os.environ["PYSTRAY_BACKEND"] = "xorg"
                try:
                    import pystray._xorg
                    import Xlib.X

                    orig_create = pystray._xorg.Icon._create_window
                    def patched_create(icon_self):
                        win = orig_create(icon_self)
                        win.change_attributes(event_mask=Xlib.X.ExposureMask | Xlib.X.StructureNotifyMask | Xlib.X.ButtonPressMask)
                        return win
                    pystray._xorg.Icon._create_window = patched_create

                    def patched_button_press(icon_self, event):
                        if event.detail == 1:
                            self._safe_after(0, self._toggle_tray_window)
                        elif event.detail == 3:
                            self._safe_after(0, lambda: self._show_tray_popup_menu(event.root_x, event.root_y))
                    pystray._xorg.Icon._on_button_press = patched_button_press
                except Exception as patch_err:
                    logger.warning(f"Could not install Xorg right-click handler: {patch_err}")

            import pystray
            from pystray import MenuItem as item

            img = self._create_tray_image()
            if not img:
                return

            menu = pystray.Menu(
                item("🧅 Show Tor IP Rotator", lambda icon, item: self._safe_after(0, self._show_from_tray), default=True),
                item("📥 Hide to Tray", lambda icon, item: self._safe_after(0, self._hide_to_tray)),
                pystray.Menu.SEPARATOR,
                item("⚡ Rotate IP Now", lambda icon, item: self._safe_after(0, self._trigger_manual_rotation)),
                item("🛑 Stop Tor & Real IP", lambda icon, item: self._safe_after(0, self._stop_tor_and_browse_real)),
                pystray.Menu.SEPARATOR,
                item("❌ Quit Application", lambda icon, item: self._safe_after(0, self._quit_fully))
            )

            self.tray_icon = pystray.Icon(
                "tor_ip_rotator",
                img,
                "Tor IP Rotator (Click to show/hide)",
                menu=menu
            )
            # Run in daemon thread so it stays alive with the app
            tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            tray_thread.start()
            logger.info("Taskbar system tray icon initialized with right-click support.")
        except Exception as e:
            logger.warning(f"Could not start system tray icon: {e}")
            self.tray_icon = None

    def _hide_to_tray(self):
        """Hides the GUI window to the taskbar notification tray."""
        self.withdraw()
        logger.info("Application minimized to taskbar tray. Click the taskbar icon to restore.")

    def _show_from_tray(self):
        """Restores and brings the GUI window to the front."""
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()
        logger.info("Application restored from taskbar tray.")

    def _on_window_close_clicked(self):
        """When window 'X' is clicked, minimize to tray if available; otherwise exit."""
        if hasattr(self, "tray_icon") and self.tray_icon:
            self._hide_to_tray()
        else:
            self._on_close()

    def _quit_fully(self):
        """Completely terminates application and tears down tray icon."""
        self.is_closing = True
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self._on_close()

    def _on_close(self):
        """Clean shutdown handler adhering to multithreaded GUI teardown patterns."""
        self.is_closing = True
        self._stop_countdown_loop()
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.mock_service_stop:
            self.mock_service_stop.set()
        if hasattr(self, "vpn_controller") and self.vpn_controller.is_active:
            self.vpn_controller.stop_vpn()
        if hasattr(self, "sys_proxy_switch") and self.sys_proxy_switch.get() == 1:
            SystemProxyController.set_system_proxy(False)
        self.rotator.stop_auto_rotation()
        self._stop_tor_daemon()
        try:
            self.withdraw()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


def run_gui():
    app = TorRotatorGUI()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
