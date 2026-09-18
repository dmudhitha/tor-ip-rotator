# 🧅 Tor IP Rotator & Virtual VPN (Linux & Windows Guide)

A high-performance, cross-platform Python desktop application and CLI to manage, rotate, and monitor public Tor exit node IP addresses. Features a modern dark-themed CustomTkinter GUI, a background system taskbar tray icon, automated circuit rotations, 1-click browser proxy launching, and full system-wide virtual network adapter (TUN/Wintun) routing.

> [!IMPORTANT]
> **Privacy First: Direct Real ISP IP by Default**
> By default upon startup, **Tor is strictly DISABLED**. The application displays your direct real ISP IP and routes traffic normally without proxying. Tor is **only activated when you explicitly click `🚀 Enable Tor`** inside the application. Clicking `🛑 Stop Tor & Browse Real IP` instantly halts Tor and restores your direct ISP connection.

---

## 📋 Table of Contents
- [✨ Key Features](#-key-features)
- [🏗️ Architecture & Control Flow](#️-architecture--control-flow)
- [🐧 Linux Setup & Usage Guide](#-linux-setup--usage-guide)
- [🪟 Windows Setup & Usage Guide](#-windows-setup--usage-guide)
- [🖥️ Desktop GUI Walkthrough](#️-desktop-gui-walkthrough)
- [⚙️ Configuration Reference (`config.json`)](#️-configuration-reference-configjson)
- [🛡️ System-Wide VPN vs. OS Proxy Modes](#️-system-wide-vpn-vs-os-proxy-modes)
- [🔒 Security & DNS Leak Prevention](#-security--dns-leak-prevention)
- [❓ Troubleshooting & FAQ](#-troubleshooting--faq)

---

## ✨ Key Features

* **Default Direct Connection**: Starts with Tor stopped and displays your real ISP IP; Tor only runs when explicitly requested.
* **On-Demand 1-Click Tor Routing**: Start Tor, establish circuits, query public exit IPs, or terminate Tor with a single click.
* **Modern Dark GUI (`gui.py`)**: Built with CustomTkinter featuring live IP display cards, country location flags, logs console, and countdown timer.
* **System Taskbar Tray Integration**:
  * Minimizes to the taskbar notification tray via the `📥 Hide to Tray` button or the window close (`X`) button.
  * Left-click tray icon to show/hide the window.
  * Native right-click context menu to rotate IP, toggle Tor state, or quit the application.
* **Country Exit Node Selector**: Route your Tor circuits through specific countries (United States, Germany, Netherlands, Switzerland, United Kingdom, Canada, France, Sweden, Japan, Singapore, Australia, or Worldwide).
* **1-Click Preconfigured Browser Launcher (`🌐 Open Browser`)**:
  * When Tor is active: launches a dedicated Firefox/Chromium instance pre-configured to route 100% of traffic through Tor SOCKS5 with remote DNS resolution (no manual browser proxy setup needed).
  * When Tor is stopped: automatically opens your default system browser with your direct Real ISP IP.
* **Automated & Manual IP Rotation**:
  * Manual circuit rotation (`Signal.NEWNYM`) with automatic verification that the exit IP has changed.
  * Configurable auto-rotation timer (1 min test, 5 min, 30 min, 60 min) with live visual countdown.
* **System-Wide Virtual Adapter VPN (Wintun / TUN)**:
  * Full PC traffic routing using `tun2socks` and Wintun driver (Windows) / TUN device (Linux).
  * 1-click OS-level desktop proxy toggle for standard desktop apps (Chrome, Edge, Brave, etc.).
* **Dual Interface**: Includes both the modern desktop GUI (`gui.py`) and a headless interactive CLI (`app.py`).

---

## 🏗️ Architecture & Control Flow

```text
               ┌────────────────────────────────────────────────────────┐
               │              Default Launch: Tor Stopped               │
               │         Direct ISP Public IP (No Proxy Routing)        │
               └───────────────────────────┬────────────────────────────┘
                                           │ Click "🚀 Enable Tor"
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               Tor IP Rotator Application                               │
│                                                                                        │
│   ┌────────────────────────┐      Stem Signals      ┌──────────────────────────────┐   │
│   │   GUI / CLI Manager    │ ─────────────────────> │      Tor ControlPort         │   │
│   │  (Countdown & State)   │   (Signal.NEWNYM /     │       127.0.0.1:9051         │   │
│   └───────────┬────────────┘    Exit Country Policy)└──────────────┬───────────────┘   │
│               │                                                    │                   │
│               │ SOCKS5h Verification                               │ Circuit Building  │
│               ▼ (Remote DNS)                                       ▼                   │
│   ┌────────────────────────┐                        ┌──────────────────────────────┐   │
│   │    Requests Client     │ ─────────────────────> │       Tor SOCKS5 Proxy       │   │
│   │  (https://api.ipify)   │                        │       127.0.0.1:9050         │   │
│   └────────────────────────┘                        └──────────────┬───────────────┘   │
└────────────────────────────────────────────────────────────────────┼───────────────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │     Tor Network      │
                                                          │ 3-Hop Encrypted Path │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │   Public Exit Node   │
                                                          │   (Assigned New IP)  │
                                                          └──────────────────────┘
```

---

## 🐧 Linux Setup & Usage Guide

Tested on **Ubuntu 22.04+**, **Bodhi Linux / Moksha (X11)**, **Debian**, and **Linux Mint**.

### 1. Prerequisites & System Packages
Open your terminal and install the required system libraries:
```bash
sudo apt update
sudo apt install -y tor python3 python3-pip python3-venv python3-tk git libx11-dev libxtst-dev
```

### 2. Clone / Open Project Directory
```bash
cd "/home/mudhitha/System/Ip change vpn/tor-ip-rotator"
```

### 3. Create and Activate Virtual Environment
```bash
# Create Python virtual environment
python3 -m venv .venv

# Enable system site-packages (for AppIndicator/Xlib access)
sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' .venv/pyvenv.cfg

# Activate the virtual environment
source .venv/bin/activate
```

### 4. Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Running the Application on Linux

#### A. Launch the Desktop GUI
```bash
# Using the helper script:
./run_gui.sh

# Or directly using Python:
./.venv/bin/python gui.py
```

#### B. Desktop App Menu & Shortcut
A desktop entry is provided for your system menu:
* **System Menu**: Navigate to **Applications -> Internet -> Tor IP Rotator (GUI)**.
* **Desktop Shortcut**: Double-click `Tor IP Rotator (GUI)` on your desktop.

#### C. Headless CLI Mode
For servers or terminal-only usage:
```bash
./run.sh
# Or:
./.venv/bin/python app.py
```

### 6. Linux Virtual Network Adapter VPN (Optional)
To route 100% of all Linux workstation traffic (all apps, terminal commands, background daemons) through Tor:
```bash
# Activate system-wide TUN VPN:
sudo ./enable_vpn.sh

# Deactivate VPN and restore normal networking:
sudo ./disable_vpn.sh
```
*(You can also toggle this with 1-click inside the GUI Settings tab using `pkexec` elevation).*

---

## 🪟 Windows Setup & Usage Guide

Tested on **Windows 10** and **Windows 11** (64-bit).

### 1. Prerequisites
1. **Python 3.8 or higher**:
   * Download from [python.org](https://www.python.org/downloads/).
   * ⚠️ **Crucial**: During installation, check the box **"Add Python to PATH"**.
2. **Tor Daemon**:
   * Download the **Tor Expert Bundle (Windows)** from the [Tor Project Official Downloads](https://www.torproject.org/download/tor/).
   * Extract to `C:\Tor` or keep the `tor.exe` in your system `PATH`.
   * *(Alternatively, if you already have Tor Browser installed, the application will automatically locate `tor.exe` in standard Tor Browser installation folders).*

### 2. Open PowerShell / Command Prompt
Navigate to the project folder:
```powershell
cd "C:\path\to\tor-ip-rotator"
```

### 3. Set Up Virtual Environment & Dependencies
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Running the Application on Windows

#### A. Launch the Desktop GUI (1-Click)
Double-click `run_gui.bat` or execute in PowerShell:
```powershell
.\run_gui.bat
```

#### B. Headless CLI Mode (1-Click)
Double-click `run.bat` or execute in PowerShell:
```powershell
.\run.bat
```

### 5. Windows System-Wide Virtual Network Adapter VPN (Wintun)
The project bundles the official WireGuard Windows `wintun.dll` and `tun2socks-windows-amd64.exe` inside `vpn_adapter/`.

To route 100% of Windows PC traffic through Tor:
* Right-click `enable_vpn.bat` and select **"Run as administrator"**.
* To stop: Right-click `disable_vpn.bat` and select **"Run as administrator"**.
* *(Or simply click `🛡️ Virtual Adapter VPN (Wintun)` in the GUI Dashboard).*

---

## 🖥️ Desktop GUI Walkthrough

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 🧅 Tor IP Rotator                        ● Tor Disabled (Real IP)  [🚀 Enable Tor]     │
│ Automated Tor Circuit & Public Exit IP                             [📥 Hide to Tray]   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [📊 Dashboard]  [⚙️ Settings]                                                           │
│                                                                                        │
│ ┌─ CURRENT IP (DIRECT REAL CONNECTION) ──────────────────────────────────────────────┐ │
│ │ 112.134.179.220                                                                    │ │
│ │ 📍 Location: Direct ISP Connection (Real IP)                                        │ │
│ │ [📋 Copy IP]  [🔄 Refresh IP]  [⚡ Rotate IP Now]  [🌐 Open Browser]               │ │
│ └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                        │
│ ┌─ EXIT NODE COUNTRY SELECTION ────┐  ┌─ AUTOMATIC IP ROTATION ──────────────────────┐ │
│ │ Target Country:                  │  │ [ Toggle ] Enable Auto-Rotation              │ │
│ │ [ 🌐 Any (Worldwide)          ▼ ]│  │ Interval: [ 30 Minutes                    ▼ ]│ │
│ └──────────────────────────────────┘  │ Next Rotation: Inactive                      │ │
│                                       └──────────────────────────────────────────────┘ │
│ ┌─ LIVE SYSTEM LOGS ─────────────────────────────────────────────────────────────────┐ │
│ │ 2026-09-19 01:05:42 INFO Tor stopped by default. Direct Real ISP IP: 112.134.179.220│ │
│ └────────────────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Key Controls
1. **Header Action Button**:
   * **`🚀 Enable Tor`** (Green): Starts the Tor daemon, connects, builds a circuit, and displays your new Tor exit IP.
   * **`🛑 Stop Tor & Browse Real IP`** (Red): Shuts down the Tor daemon, resets to direct ISP connection, queries your real IP, and opens your browser.
2. **`📥 Hide to Tray` & Window Close ("X")**:
   * Hides the window to your system taskbar tray.
   * Left-click the onion tray icon to restore the window.
   * Right-click the tray icon for quick shortcuts (`Show`, `Hide`, `Rotate IP Now`, `Enable/Stop Tor`, `Quit`).
3. **`🌐 Open Browser`**:
   * If Tor is active: launches Firefox or Chromium pre-configured with Tor SOCKS5 proxy and DNS leak protection.
   * If Tor is stopped: opens your default system browser with your direct Real IP.
4. **`⚡ Rotate IP Now`**:
   * Sends the `NEWNYM` signal to Tor's ControlPort to request a fresh circuit and immediately confirms the new exit IP.

---

## ⚙️ Configuration Reference (`config.json`)

You can modify settings in `config.json` or directly via the **⚙️ Settings** tab in the GUI:

```json
{
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
```

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `rotation_interval_minutes` | `30` | Minutes between automatic IP rotations. |
| `tor_control_host` | `127.0.0.1` | Host where Tor ControlPort is listening. |
| `tor_control_port` | `9051` | Port for Stem control commands (`NEWNYM`). |
| `tor_socks_host` | `127.0.0.1` | Host where Tor SOCKS5 proxy is listening. |
| `tor_socks_port` | `9050` | Port where Tor SOCKS5 proxy is listening. |
| `tor_control_password` | `""` | Password if Tor ControlPort uses `HashedControlPassword`. |
| `tor_cookie_path` | `""` | Optional explicit path to `control_auth_cookie`. |
| `ip_check_url` | `api.ipify.org` | Public API used to detect exit node IP. |
| `rotation_retry_count` | `3` | Attempts to retry if Tor picks the same exit node twice. |
| `rotation_wait_seconds` | `15` | Cooldown period for new circuit stabilization. |

---

## 🛡️ System-Wide VPN vs. OS Proxy Modes

The application offers two distinct system-wide traffic routing mechanisms:

### Mode 1: Virtual TUN/Wintun Adapter VPN
* **Mechanism**: Creates a virtual network adapter (`tun0` on Linux, `wintun` on Windows) and uses `tun2socks` to route all TCP/UDP traffic on your computer through Tor.
* **Coverage**: **100% of PC Traffic** (Browsers, terminal commands, background apps, game launchers, background Windows/Linux services).
* **Requirements**: Requires administrative/root elevation to create the virtual interface.

### Mode 2: OS Desktop System Proxy
* **Mechanism**: Sets the operating system's global proxy settings to `socks5://127.0.0.1:9050`.
* **Coverage**: Standard web browsers (Google Chrome, Microsoft Edge, Brave, Opera) and desktop applications that inherit OS proxy settings.
* **Requirements**: **Zero administrator privileges needed**. Instant 1-click toggle.

---

## 🔒 Security & DNS Leak Prevention

* **Remote DNS Resolution (`socks5h://`)**: All HTTP requests made by the application use the `socks5h` scheme. The `h` flag instructs the client to pass hostnames to Tor for DNS resolution, preventing your local ISP from intercepting DNS requests.
* **Localhost Binding**: In `tor/torrc`, `SocksPort` and `ControlPort` are bound strictly to `127.0.0.1`. Never expose them to `0.0.0.0`.
* **Cookie Authentication**: The Tor ControlPort requires Stem to supply the secret authentication cookie generated by Tor, ensuring unauthorized local programs cannot manipulate your circuits.
* **Credential Protection**: No sensitive authentication tokens or passwords are logged to `logs/rotator.log`.

---

## ❓ Troubleshooting & FAQ

### Q: Why does my browser show "Unable to connect to proxy server"?
**A**: Ensure you clicked **`🚀 Enable Tor`** in the application before browsing with a proxy-configured browser. If Tor is stopped, click **`🌐 Open Browser`** to browse with your direct Real IP, or enable Tor first.

### Q: The GUI shows `● Tor Not Running` on Linux.
**A**: Ensure the `tor` binary is installed:
```bash
sudo apt install tor
which tor
```
The application will automatically launch and manage its own isolated Tor instance using `tor/torrc`.

### Q: Can I run this without root / administrator privileges?
**A**: **Yes!** Running the application, rotating Tor IPs, and using the `🌐 Open Browser` button requires **no administrator or root privileges**. Administrator/root elevation is only required if you choose to activate the optional **Virtual Adapter VPN (Wintun/TUN)** mode.

### Q: How do I completely close the application?
**A**: Either right-click the taskbar tray icon and select **`❌ Quit Application`**, or click the `❌` button in the UI. Exiting the application automatically terminates the Tor daemon and releases all network configurations.

---

## 📄 License
This project is open-source and released under the [MIT License](LICENSE).
