"""Low-overhead RGB LED monitor for Ethernet and qlcplus.service."""

from threading import Event, Thread
from typing import Callable

from gpio_devices import LedChannels
from system_info import managed_service_states
from system_monitor import network_state


PHASE_DURATION = 1.5
BLINK_INTERVAL = 0.25


def qlcplus_running() -> bool:
    """Reuse the shared systemd snapshot used by the OLED service page."""
    return managed_service_states()["QLC+"][0] in ("AUTO", "MANUAL")


class StatusLedController:
    """Alternate network and application phases in one interruptible worker."""

    def __init__(
        self,
        on_failure: Callable[[Exception], None] | None = None,
        channels=None,
        network_probe=network_state,
        service_probe=qlcplus_running,
    ):
        self.channels = channels if channels is not None else LedChannels()
        self.network_probe = network_probe
        self.service_probe = service_probe
        self.stop_event = Event()
        self.on_failure = on_failure
        self.error: Exception | None = None
        self.thread = Thread(target=self._run_guarded, name="status-led", daemon=True)

    def start(self):
        self.thread.start()

    def _wait(self, duration: float) -> bool:
        return self.stop_event.wait(duration)

    def _blink(self, led, duration: float):
        elapsed = 0.0
        while elapsed < duration and not self.stop_event.is_set():
            led.on()
            step = min(BLINK_INTERVAL, duration - elapsed)
            if self._wait(step):
                break
            elapsed += step
            if elapsed >= duration:
                break
            led.off()
            step = min(BLINK_INTERVAL, duration - elapsed)
            if self._wait(step):
                break
            elapsed += step
        led.off()

    def _network_phase(self):
        self.channels.all_off()
        state = self.network_probe()
        if not state.link_up:
            self._wait(PHASE_DURATION)
        elif state.ipv4:
            self.channels.blue.on()
            self._wait(PHASE_DURATION)
            self.channels.blue.off()
        else:
            self._blink(self.channels.blue, PHASE_DURATION)

    def _application_phase(self):
        self.channels.all_off()
        running = self.service_probe()
        if running:
            self.channels.green.on()
            self._wait(PHASE_DURATION)
            self.channels.green.off()
        else:
            self._blink(self.channels.green, PHASE_DURATION)

    def _run_guarded(self):
        try:
            while not self.stop_event.is_set():
                self._network_phase()
                if not self.stop_event.is_set():
                    self._application_phase()
        except Exception as error:
            self.error = error
            if self.on_failure is not None:
                self.on_failure(error)
        finally:
            self.channels.all_off()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.channels.close()
