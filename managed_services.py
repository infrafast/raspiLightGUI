"""Single declaration of systemd services monitored and controlled by the UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDefinition:
    """Configuration for one monitored and controllable systemd service.

    key:
        Stable internal identifier. It is also the compact label used on the
        SYSTEM status preview and is referenced by ``depends_on``.
    label:
        User-facing name used in menus and action-result messages.
    unit:
        Exact systemd unit name queried for status and used to generate the
        installer's narrowly scoped sudo permissions.
    wrapper:
        Absolute path of a command accepting ``start``, ``stop``, ``restart``,
        ``auto`` and ``noauto``.
    depends_on:
        Optional tuple of other service keys that must all be running before
        this service can be started. Dependencies are checked, not started
        automatically.
    """

    key: str
    label: str
    unit: str
    wrapper: str
    depends_on: tuple[str, ...] = ()


# Tuple order defines the service order in the SYSTEM preview and root menu.
# Add, remove or reorder ServiceDefinition entries here; status lines, service
# submenus and sudo permissions are generated from this single declaration.
MANAGED_SERVICES = (
    ServiceDefinition(
        "QLC+",
        "QLC+",
        "qlcplus.service",
        "/usr/local/bin/qlcplus-service",
    ),
    ServiceDefinition(
        "OCULIZER",
        "Oculizer",
        "oculizer.service",
        "/usr/local/bin/oculizer-service",
        ("QLC+",),
    ),
    ServiceDefinition(
        "ASSISTANT",
        "Assistant",
        "livestageassistant.service",
        "/usr/local/bin/livestageassistant",
    ),
)

# Fast lookup used when resolving dependency keys.
SERVICES_BY_KEY = {service.key: service for service in MANAGED_SERVICES}

# The green LED reports this service. Its value must match a key declared above.
PRIMARY_SERVICE_KEY = "QLC+"
