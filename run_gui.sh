#!/usr/bin/env bash
# ========================================================
# Tor IP Rotator - Desktop GUI Launcher
# Runs: .venv/bin/python gui.py
# ========================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

if [ ! -f "$DIR/.venv/bin/python" ]; then
    echo "[*] Initializing virtual environment (.venv)..."
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
fi

exec "$DIR/.venv/bin/python" "$DIR/gui.py" "$@"
