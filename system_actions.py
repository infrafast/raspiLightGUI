"""Pluggable callbacks used by the SYSTEM action screen."""

import os
from pathlib import Path
import signal
import subprocess
import time


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


def restart_assistant() -> str:
    return _run(
        ["/usr/local/bin/livestageassistant", "restart"],
        "Assistant restarted",
        "Assistant failed",
    )


def start_assistant() -> str:
    return _run(
        ["/usr/local/bin/livestageassistant", "start"],
        "Assistant started",
        "Assistant start error",
    )


def stop_assistant() -> str:
    return _run(
        ["/usr/local/bin/livestageassistant", "stop"],
        "Assistant stopped",
        "Assistant stop error",
    )


def restart_oculizer() -> str:
    return _run(
        ["/usr/local/bin/oculizer-service", "restart"],
        "Oculizer restarted",
        "Oculizer failed",
    )


def start_oculizer() -> str:
    return _run(
        ["/usr/local/bin/oculizer-service", "start"],
        "Oculizer started",
        "Oculizer start error",
    )


def stop_oculizer() -> str:
    return _run(
        ["/usr/local/bin/oculizer-service", "stop"],
        "Oculizer stopped",
        "Oculizer stop error",
    )


def _find_qlcplus() -> tuple[int, list[str], str, dict[str, str]] | None:
    """Capture a qlcplus-qml process exactly enough to restart it."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            raw_argv = (entry / "cmdline").read_bytes().rstrip(b"\0")
            argv = [part.decode(errors="surrogateescape") for part in raw_argv.split(b"\0")]
            if not argv or not any("qlcplus-qml" in argument for argument in argv):
                continue
            cwd = os.readlink(entry / "cwd")
            raw_env = (entry / "environ").read_bytes().rstrip(b"\0")
            env = {}
            for item in raw_env.split(b"\0"):
                key, separator, value = item.partition(b"=")
                if separator:
                    env[key.decode(errors="surrogateescape")] = value.decode(
                        errors="surrogateescape"
                    )
            return int(entry.name), argv, cwd, env
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return None


def restart_qlcplus() -> str:
    process = _find_qlcplus()
    if process is None:
        return "QLC+ not running"
    pid, argv, cwd, env = process
    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and Path(f"/proc/{pid}").exists():
            time.sleep(0.1)
        if Path(f"/proc/{pid}").exists():
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.2)
        subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"QLC+ restart failed: {error}")
        return "QLC+ restart failed"
    return "QLC+ restarted"


def shutdown_pi() -> str:
    # -n prevents the UI from hanging on an interactive sudo password prompt.
    return _run(
        ["sudo", "-n", "systemctl", "poweroff"],
        "Shutdown requested",
        "Shutdown failed",
        timeout=5,
    )
