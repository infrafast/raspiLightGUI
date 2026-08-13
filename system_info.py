"""Pluggable content providers for information screens."""

from dataclasses import dataclass
import socket
import subprocess
import time
import re

import psutil


IP_REFRESH_SECONDS = 60.0
IP_DOWN_RETRY_SECONDS = 10.0
POWER_OK_VOLTS = 4.80
# The hardware threshold is approximately 4.63 V. Use 4.65 V so the UI warns
# just before that threshold is crossed.
POWER_CRITICAL_VOLTS = 4.65
TEMP_HIGH_C = 70.0
TEMP_CRITICAL_C = 80.0
SERVICE_RESTART_ALERT = 3
_cached_ip: str | None = None
_last_ip_refresh: float | None = None


@dataclass(frozen=True)
class ScreenData:
    lines: list[str]
    alert: bool = False


def _temperature_info() -> tuple[float | None, str]:
    try:
        temperatures = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None, "N/A"
    value = None
    for sensor_name in ("cpu_thermal", "soc_thermal"):
        if temperatures.get(sensor_name):
            value = temperatures[sensor_name][0].current
            break
    if value is None:
        for readings in temperatures.values():
            if readings:
                value = readings[0].current
                break
    if value is None:
        return None, "N/A"
    if value >= TEMP_CRITICAL_C:
        state = "CRIT"
    elif value >= TEMP_HIGH_C:
        state = "HIGH"
    else:
        state = "OK"
    return value, state


def _uptime() -> str:
    seconds = max(0, int(time.time() - psutil.boot_time()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    return f"{days}d {hours:02d}:{minutes:02d}" if days else f"{hours:02d}:{minutes:02d}"


def _vcgencmd(*arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["vcgencmd", *arguments],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _power_info() -> tuple[float | None, str]:
    """Return Pi 5 input voltage and OK/LOW/CRIT state."""
    adc = _vcgencmd("pmic_read_adc", "EXT5V_V")
    match = re.search(r"EXT5V_V[^=]*=\s*([0-9]+(?:\.[0-9]+)?)V", adc or "")
    if match is None:
        return None, "N/A"
    voltage = float(match.group(1))

    throttled = _vcgencmd("get_throttled")
    throttled_match = re.search(r"0x([0-9a-fA-F]+)", throttled or "")
    undervoltage_now = bool(
        throttled_match and int(throttled_match.group(1), 16) & 0x1
    )
    if undervoltage_now or voltage <= POWER_CRITICAL_VOLTS:
        state = "CRIT"
    elif voltage < POWER_OK_VOLTS:
        state = "LOW"
    else:
        state = "OK"
    return voltage, state


def _interface_ip() -> str:
    """Return a wired IPv4 address, caching success longer than a miss."""
    global _cached_ip, _last_ip_refresh

    now = time.monotonic()
    cache_age = now - _last_ip_refresh if _last_ip_refresh is not None else None
    cache_lifetime = (
        IP_REFRESH_SECONDS if _cached_ip not in (None, "DOWN") else IP_DOWN_RETRY_SECONDS
    )
    if cache_age is not None and cache_age < cache_lifetime:
        return _cached_ip

    interfaces = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    candidates = ["eth0"]
    candidates.extend(
        sorted(
            name
            for name in interfaces
            if name != "eth0" and name.startswith(("eth", "en"))
        )
    )
    _cached_ip = "DOWN"
    for interface in candidates:
        if interface not in interfaces or not stats.get(interface, None):
            continue
        if not stats[interface].isup:
            continue
        for address in interfaces[interface]:
            if address.family == socket.AF_INET and not address.address.startswith("127."):
                _cached_ip = address.address
                break
        if _cached_ip != "DOWN":
            break
    _last_ip_refresh = now
    return _cached_ip


def monitor_content() -> ScreenData:
    """Return five OLED-ready monitoring lines."""
    cpu = psutil.cpu_percent(interval=None)
    disk = psutil.disk_usage("/").percent
    memory = psutil.virtual_memory().percent
    voltage, power_state = _power_info()
    voltage_text = f"{voltage:.2f}" if voltage is not None else "N/A"
    temperature, temperature_state = _temperature_info()
    temperature_text = f"{temperature:.1f}C" if temperature is not None else "N/A"
    return ScreenData(
        lines=[
            f"T:{temperature_text} {temperature_state} V:{voltage_text} {power_state}",
            f"Uptime: {_uptime()}",
            f"CPU:{cpu:3.0f}% RAM:{memory:3.0f}%",
            f"Disk: {disk:.0f}%",
            f"ETH {_interface_ip()}",
        ],
        alert=temperature_state in ("HIGH", "CRIT")
        or power_state in ("LOW", "CRIT"),
    )


def _systemd_info(service: str) -> tuple[str, int]:
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                service,
                "--property=ActiveState",
                "--property=NRestarts",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN", 0
    properties = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    state = properties.get("ActiveState", "").lower()
    status = {
        "active": "UP",
        "activating": "STARTING",
        "reloading": "STARTING",
        "deactivating": "STOPPING",
        "inactive": "DOWN",
        "failed": "FAILED",
    }.get(state, "UNKNOWN")
    try:
        restarts = int(properties.get("NRestarts", "0"))
    except ValueError:
        restarts = 0
    return status, restarts


def _process_status(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    return "UP" if result.returncode == 0 else "DOWN"


def _managed_service_info(service: str) -> tuple[str, int]:
    """Return runtime/boot mode and restart count for a systemd service."""
    active, restarts = _systemd_info(service)
    if active != "UP":
        return active, restarts
    try:
        enabled = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", service],
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN", restarts
    return ("AUTO" if enabled.returncode == 0 else "MANUAL"), restarts


def _service_line(label: str, state: str, restarts: int) -> str:
    suffix = f" R:{restarts}" if restarts > 1 else ""
    return f"{label}: {state}{suffix}"


def service_content() -> ScreenData:
    """Return current systemd/process states without invoking a shell."""
    oculizer_state, oculizer_restarts = _managed_service_info(
        "oculizer.service"
    )
    assistant_state, assistant_restarts = _managed_service_info(
        "livestageassistant.service"
    )
    alert = (
        oculizer_state == "FAILED"
        or assistant_state == "FAILED"
        or oculizer_restarts >= SERVICE_RESTART_ALERT
        or assistant_restarts >= SERVICE_RESTART_ALERT
    )
    return ScreenData(
        lines=[
            _service_line("OCULIZER", oculizer_state, oculizer_restarts),
            _service_line("ASSISTANT", assistant_state, assistant_restarts),
            f"QLC+: {_process_status(['pgrep', '-f', 'qlcplus-qml'])}",
        ],
        alert=alert,
    )
