"""Pluggable callbacks used by the SYSTEM action screen."""

import subprocess

from managed_services import SERVICES_BY_KEY, ServiceDefinition


def _run(
    command: list[str], success_message: str, failure_message: str, timeout: int = 20
) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        print(f"Command not found: {command[0]}")
        return failure_message
    except subprocess.TimeoutExpired:
        print(f"Command timed out: {command!r}")
        return failure_message
    if result.returncode == 0:
        return success_message
    detail = (result.stderr or result.stdout).strip()
    print(detail or f"Command failed with code {result.returncode}: {command!r}")
    return failure_message


def run_service_action(service: ServiceDefinition, action: str) -> str:
    """Run a declared service wrapper and return a compact semantic result."""
    if action == "start" and service.depends_on:
        # Import lazily to keep service declarations independent from probes.
        from system_info import managed_service_states

        states = managed_service_states(max_age=0.0)
        for dependency_key in service.depends_on:
            dependency = SERVICES_BY_KEY[dependency_key]
            if states[dependency_key].runtime != "UP":
                return f"Start {dependency.label} first"
    past_tense = {
        "start": "started",
        "stop": "stopped",
        "restart": "restarted",
        "auto": "set auto",
        "noauto": "set manual",
    }
    return _run(
        [service.wrapper, action],
        f"{service.label} {past_tense[action]}",
        f"{service.label} {action} error",
    )


def shutdown_pi() -> str:
    # -n prevents the UI from hanging on an interactive sudo password prompt.
    return _run(
        ["sudo", "-n", "systemctl", "poweroff"],
        "Shutdown requested",
        "Shutdown failed",
        timeout=5,
    )


def reboot_pi() -> str:
    # -n prevents the UI from hanging on an interactive sudo password prompt.
    return _run(
        ["sudo", "-n", "systemctl", "reboot"],
        "Reboot requested",
        "Reboot failed",
        timeout=5,
    )
