"""Pluggable content providers for information screens."""

from dataclasses import dataclass
import subprocess
from threading import Lock
import time
import re

import psutil

from managed_services import MANAGED_SERVICES
from system_monitor import network_state


POWER_OK_VOLTS = 4.80
# The hardware threshold is approximately 4.63 V. Use 4.65 V so the UI warns
# just before that threshold is crossed.
POWER_CRITICAL_VOLTS = 4.65
TEMP_HIGH_C = 70.0
TEMP_CRITICAL_C = 80.0
SERVICE_RESTART_ALERT = 3
SERVICE_STATE_MAX_AGE = 10.0
_service_state_lock = Lock()
_service_state_snapshot: tuple[float, dict[str, "ServiceStatus"]] | None = None


@dataclass(frozen=True)
class ScreenData:
    lines: list[str]
    alert: bool = False


@dataclass(frozen=True)
class ServiceStatus:
    runtime: str
    enabled: bool | None
    restarts: int

    @property
    def display_state(self) -> str:
        if self.runtime == "UP":
            if self.enabled is True:
                return "AUTO"
            if self.enabled is False:
                return "MANUAL"
            return "UNKNOWN"
        if self.enabled is True and self.runtime != "UNKNOWN":
            return f"{self.runtime} AUTO"
        return self.runtime


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
    """Return the latest wired IPv4 snapshot shared with the LED worker."""
    return network_state(max_age=10.0).ipv4 or "DOWN"


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


def _managed_service_info(service: str) -> ServiceStatus:
    """Return runtime/boot mode and restart count for a systemd service."""
    runtime, restarts = _systemd_info(service)
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", service],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        enabled = None
    else:
        enabled_state = result.stdout.strip().lower()
        if enabled_state in ("enabled", "enabled-runtime"):
            enabled = True
        elif enabled_state == "disabled":
            enabled = False
        else:
            enabled = None
    return ServiceStatus(runtime, enabled, restarts)


def managed_service_states(
    max_age: float = SERVICE_STATE_MAX_AGE,
) -> dict[str, ServiceStatus]:
    """Return one shared, bounded-age snapshot of all managed services."""
    global _service_state_snapshot

    with _service_state_lock:
        now = time.monotonic()
        if (
            max_age > 0
            and _service_state_snapshot is not None
            and now - _service_state_snapshot[0] <= max_age
        ):
            return dict(_service_state_snapshot[1])
        states = {
            service.key: _managed_service_info(service.unit)
            for service in MANAGED_SERVICES
        }
        _service_state_snapshot = (now, states)
        return dict(states)


def invalidate_service_states():
    """Force the next service consumer to obtain a fresh snapshot."""
    global _service_state_snapshot

    with _service_state_lock:
        _service_state_snapshot = None


def _service_line(label: str, status: ServiceStatus) -> str:
    suffix = f" R:{status.restarts}" if status.restarts > 1 else ""
    return f"{label}: {status.display_state}{suffix}"


def service_content() -> ScreenData:
    """Return the states of all declared systemd services."""
    states = managed_service_states()
    alert = any(
        status.runtime == "FAILED" or status.restarts >= SERVICE_RESTART_ALERT
        for status in states.values()
    )
    return ScreenData(
        lines=[
            _service_line(service.key, states[service.key])
            for service in MANAGED_SERVICES
        ],
        alert=alert,
    )
