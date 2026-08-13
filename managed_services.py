"""Single declaration of systemd services monitored and controlled by the UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDefinition:
    key: str
    label: str
    unit: str
    wrapper: str


MANAGED_SERVICES = (
    ServiceDefinition("QLC+", "QLC+", "qlcplus.service", "/usr/local/bin/qlcplus-service"),
    ServiceDefinition(
        "OCULIZER", "Oculizer", "oculizer.service", "/usr/local/bin/oculizer-service"
    ),
    ServiceDefinition(
        "ASSISTANT",
        "Assistant",
        "livestageassistant.service",
        "/usr/local/bin/livestageassistant",
    ),
)

SERVICES_BY_KEY = {service.key: service for service in MANAGED_SERVICES}
