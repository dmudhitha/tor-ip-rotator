"""
Unit tests for TorRotator logic, mock IP checking, mock Stem controller,
cooldown, rotation retry mechanism, and logging.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from app import TorRotator, load_config, setup_logger
from stem import SocketError
from stem.control import Controller


def test_load_config_defaults(tmp_path):
    # Test fallback when file doesn't exist
    non_existent = str(tmp_path / "missing.json")
    cfg = load_config(non_existent)
    assert cfg["rotation_interval_minutes"] == 30
    assert cfg["tor_control_port"] == 9051
    assert cfg["tor_socks_port"] == 9050


def test_load_config_custom(tmp_path):
    cfg_file = tmp_path / "custom_config.json"
    cfg_file.write_text(json.dumps({"rotation_interval_minutes": 5, "rotation_retry_count": 5}))
    cfg = load_config(str(cfg_file))
    assert cfg["rotation_interval_minutes"] == 5
    assert cfg["rotation_retry_count"] == 5
    assert cfg["tor_control_port"] == 9051  # Preserves defaults for missing keys


def test_socks_proxy_url():
    rotator = TorRotator()
    assert rotator.socks_proxy_url == "socks5h://127.0.0.1:9050"
    proxies = rotator.get_proxies_dict()
    assert proxies["http"] == "socks5h://127.0.0.1:9050"
    assert proxies["https"] == "socks5h://127.0.0.1:9050"


@patch("app.requests.get")
def test_get_current_ip_json_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ip": "185.220.101.5"}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    rotator = TorRotator()
    ip, err = rotator.get_current_ip()
    assert err is None
    assert ip == "185.220.101.5"
    assert rotator.current_ip == "185.220.101.5"


@patch("app.requests.get")
def test_get_current_ip_text_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.side_effect = ValueError("Not JSON")
    mock_resp.text = "195.176.3.19\n"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    rotator = TorRotator()
    ip, err = rotator.get_current_ip()
    assert err is None
    assert ip == "195.176.3.19"


@patch.object(TorRotator, "is_port_open", return_value=False)
@patch("app.Controller.from_port")
def test_check_tor_connection_not_running(mock_from_port, mock_port_open):
    mock_from_port.side_effect = SocketError("[Errno 111] Connection refused")

    rotator = TorRotator()
    connected, msg = rotator.check_tor_connection()
    assert not connected
    assert "Tor is not running" in msg


@patch.object(TorRotator, "is_port_open", return_value=True)
@patch("app.Controller.from_port")
def test_check_tor_connection_socks_only(mock_from_port, mock_port_open):
    mock_from_port.side_effect = SocketError("[Errno 111] Connection refused")

    rotator = TorRotator()
    connected, msg = rotator.check_tor_connection()
    assert not connected
    assert "ControlPort 9051 is disabled" in msg


@patch("app.Controller.from_port")
def test_check_tor_connection_success(mock_from_port):
    mock_ctrl = MagicMock()
    mock_from_port.return_value.__enter__.return_value = mock_ctrl

    rotator = TorRotator()
    connected, msg = rotator.check_tor_connection()
    assert connected
    assert msg == "Connected"
    mock_ctrl.authenticate.assert_called_once()


@patch("app.time.sleep")
@patch.object(TorRotator, "request_new_circuit")
@patch.object(TorRotator, "get_current_ip")
def test_rotate_ip_success_on_first_try(mock_get_ip, mock_request_circuit, mock_sleep):
    mock_request_circuit.return_value = (True, None)
    # Old IP is 1.1.1.1, new IP is 2.2.2.2
    mock_get_ip.side_effect = [("1.1.1.1", None), ("2.2.2.2", None)]

    rotator = TorRotator()
    rotator.wait_seconds = 0
    success, old_ip, new_ip, err = rotator.rotate_ip()

    assert success is True
    assert old_ip == "1.1.1.1"
    assert new_ip == "2.2.2.2"
    assert err is None
    assert rotator.current_ip == "2.2.2.2"


@patch("app.time.sleep")
@patch.object(TorRotator, "request_new_circuit")
@patch.object(TorRotator, "get_current_ip")
def test_rotate_ip_retry_when_same_ip(mock_get_ip, mock_request_circuit, mock_sleep):
    mock_request_circuit.return_value = (True, None)
    # 1. Initial old IP: 1.1.1.1
    # 2. Attempt 1 new IP: 1.1.1.1 (Same! Triggers retry)
    # 3. Attempt 2 new IP: 3.3.3.3 (Different! Success)
    mock_get_ip.side_effect = [
        ("1.1.1.1", None),
        ("1.1.1.1", None),
        ("3.3.3.3", None),
    ]

    rotator = TorRotator()
    rotator.retry_count = 3
    rotator.wait_seconds = 0

    success, old_ip, new_ip, err = rotator.rotate_ip()

    assert success is True
    assert old_ip == "1.1.1.1"
    assert new_ip == "3.3.3.3"
    assert rotator.current_ip == "3.3.3.3"


def test_auto_rotation_start_stop():
    rotator = TorRotator()
    assert not rotator.is_auto_rotation_running()

    started = rotator.start_auto_rotation(interval_minutes=1)
    assert started is True
    assert rotator.is_auto_rotation_running()

    # Second start should return False since already running
    assert rotator.start_auto_rotation(interval_minutes=1) is False

    stopped = rotator.stop_auto_rotation()
    assert stopped is True
    assert not rotator.is_auto_rotation_running()
