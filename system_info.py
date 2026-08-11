"""Pluggable content providers for information screens."""

import socket
import subprocess
import time

import psutil


IP_REFRESH_SECONDS = 60.0
_cached_ip = "DOWN"
_last_ip_refresh = 0.0


def _temperature() -> str:
    try:
        temperatures = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return "N/A"
    for sensor_name in ("cpu_thermal", "soc_thermal"):
        if temperatures.get(sensor_name):
            return f"{temperatures[sensor_name][0].current:.1f} C"
    for readings in temperatures.values():
        if readings:
            return f"{readings[0].current:.1f} C"
    return "N/A"


def _uptime() -> str:
    seconds = max(0, int(time.time() - psutil.boot_time()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    return f"{days}d {hours:02d}:{minutes:02d}" if days else f"{hours:02d}:{minutes:02d}"


def _interface_ip(interface: str = "eth0") -> str:
    global _cached_ip, _last_ip_refresh

    now = time.monotonic()
    if now - _last_ip_refresh < IP_REFRESH_SECONDS:
        return _cached_ip
    addresses = psutil.net_if_addrs().get(interface, [])
    for address in addresses:
        if address.family == socket.AF_INET:
            _cached_ip = address.address
            break
    else:
        _cached_ip = "DOWN"
    _last_ip_refresh = now
    return _cached_ip


def monitor_content() -> list[str]:
    """Return five OLED-ready monitoring lines."""
    cpu = psutil.cpu_percent(interval=None)
    disk = psutil.disk_usage("/").percent
    memory = psutil.virtual_memory().percent
    return [
        f"Temp: {_temperature()}",
        f"Uptime: {_uptime()}",
        f"CPU:{cpu:3.0f}% RAM:{memory:3.0f}%",
        f"Disk: {disk:.0f}%",
        f"ETH {_interface_ip()}",
    ]


def _systemd_status(service: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    state = result.stdout.strip().lower()
    return {
        "active": "UP",
        "activating": "STARTING",
        "reloading": "STARTING",
        "deactivating": "STOPPING",
        "inactive": "DOWN",
        "failed": "FAILED",
    }.get(state, "UNKNOWN")


def _process_status(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    return "UP" if result.returncode == 0 else "DOWN"


def _oculizer_status() -> str:
    active = _systemd_status("oculizer.service")
    if active != "UP":
        return active
    try:
        enabled = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", "oculizer.service"],
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    return "AUTO" if enabled.returncode == 0 else "MANUAL"


def service_content() -> list[str]:
    """Return current systemd/process states without invoking a shell."""
    return [
        f"OCULIZER: {_oculizer_status()}",
        f"ASSISTANT: {_systemd_status('livestageassistant.service')}",
        f"QLC+: {_process_status(['pgrep', '-f', 'qlcplus-qml'])}",
    ]
