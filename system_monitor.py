"""Low-cost system probes shared by the OLED dashboard and status LED."""

from dataclasses import dataclass
import socket
from threading import Lock
import time

import psutil


@dataclass(frozen=True)
class NetworkState:
    interface: str | None
    link_up: bool
    ipv4: str | None


_network_lock = Lock()
_network_snapshot: tuple[float, NetworkState] | None = None


def wired_interfaces(names=None) -> list[str]:
    """Return wired interface candidates, preferring the traditional eth0."""
    names = psutil.net_if_addrs() if names is None else names
    candidates = [name for name in names if name.startswith(("eth", "en"))]
    return sorted(candidates, key=lambda name: (name != "eth0", name))


def _read_network_state() -> NetworkState:
    """Read Ethernet carrier and global-ish IPv4 state without subprocesses."""
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    candidates = wired_interfaces(addresses)
    if not candidates:
        return NetworkState(None, False, None)

    # Prefer an interface that is up and has IPv4, then any interface with link.
    fallback = candidates[0]
    for interface in candidates:
        interface_stats = stats.get(interface)
        if not interface_stats or not interface_stats.isup:
            continue
        fallback = interface
        for address in addresses.get(interface, []):
            if address.family == socket.AF_INET and not address.address.startswith("127."):
                return NetworkState(interface, True, address.address)
    interface_stats = stats.get(fallback)
    return NetworkState(
        fallback,
        bool(interface_stats and interface_stats.isup),
        None,
    )


def network_state(max_age: float = 0.0) -> NetworkState:
    """Return network state, optionally reusing a recent shared snapshot."""
    global _network_snapshot

    with _network_lock:
        now = time.monotonic()
        if max_age > 0 and _network_snapshot and now - _network_snapshot[0] <= max_age:
            return _network_snapshot[1]
        state = _read_network_state()
        _network_snapshot = (now, state)
        return state
