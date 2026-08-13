"""GPIO devices used by the dashboard buttons and RGB status LED."""

import os
from queue import Empty, SimpleQueue
from threading import Event

# Raspberry Pi 5 requires the lgpio backend. Honour an explicit operator
# override, but make the normal local and systemd commands self-contained.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")

from gpiozero import Button, LED


BUTTON_DOWN_GPIO = 5    # Physical pin 29
BUTTON_SELECT_GPIO = 6  # Physical pin 31
BUTTON_UP_GPIO = 13     # Physical pin 33
BLUE_LED_GPIO = 27      # Physical pin 13
GREEN_LED_GPIO = 22     # Physical pin 15


class GpioInput:
    """Edge-triggered button input with no active polling."""

    def __init__(self):
        self.events = SimpleQueue()
        self.wake = Event()
        self.buttons = (
            self._make_button(BUTTON_DOWN_GPIO, "down"),
            self._make_button(BUTTON_SELECT_GPIO, "select"),
            self._make_button(BUTTON_UP_GPIO, "up"),
        )

    def _make_button(self, gpio: int, event_name: str):
        button = Button(gpio, pull_up=True, bounce_time=0.05)
        button.when_pressed = lambda: self._push(event_name)
        return button

    def _push(self, event_name: str):
        self.events.put(event_name)
        self.wake.set()

    def next_event(self, timeout: float | None = None) -> str | None:
        self.wake.clear()
        try:
            return self.events.get_nowait()
        except Empty:
            self.wake.wait(timeout)
        try:
            return self.events.get_nowait()
        except Empty:
            return None

    def discard_events(self):
        while True:
            try:
                self.events.get_nowait()
            except Empty:
                return

    def wake_up(self):
        self.wake.set()

    def close(self):
        for button in self.buttons:
            button.close()


class LedChannels:
    """Software-controlled blue and green channels of a common-cathode RGB LED."""

    def __init__(self):
        self.blue = LED(BLUE_LED_GPIO)
        try:
            self.green = LED(GREEN_LED_GPIO)
        except Exception:
            self.blue.close()
            raise

    def all_off(self):
        self.blue.off()
        self.green.off()

    def close(self):
        self.all_off()
        self.blue.close()
        self.green.close()
