"""Extensible SSD1306 dashboard for Raspberry Pi 5."""

from dataclasses import dataclass
import time
from typing import Callable

import adafruit_ssd1306
import board
import digitalio
from PIL import Image, ImageDraw, ImageFont

from system_actions import (
    restart_assistant,
    restart_oculizer,
    restart_qlcplus,
    shutdown_pi,
)
from system_info import monitor_content, service_content


WIDTH = 128
HEIGHT = 64
I2C_ADDRESS = 0x3C
REFRESH_SECONDS = 1.0

BUTTON_DOWN_PIN = board.D5    # Down/Back, physical pin 29
BUTTON_SELECT_PIN = board.D6  # Select/OK, physical pin 31
BUTTON_UP_PIN = board.D13     # Up/Next, physical pin 33

ContentProvider = Callable[[], list[str]]
ActionCallback = Callable[[], str]


@dataclass(frozen=True)
class InfoScreen:
    title: str
    content: ContentProvider


@dataclass(frozen=True)
class ActionItem:
    label: str
    callback: ActionCallback | None = None
    confirm: bool = False
    progress_message: str = "Working..."
    terminal: bool = False


@dataclass(frozen=True)
class ActionScreen:
    title: str
    items: tuple[ActionItem, ...]


# Add an InfoScreen or ActionScreen here to extend the carousel. Content and
# actions are regular callables, so they may also import an external module.
SCREENS = (
    InfoScreen("MONITOR", monitor_content),
    InfoScreen("SERVICE STATE", service_content),
    ActionScreen(
        "SYSTEM",
        (
            ActionItem("Restart Assistant", restart_assistant, confirm=True),
            ActionItem("Restart Oculizer", restart_oculizer, confirm=True),
            ActionItem("Restart QLC+", restart_qlcplus, confirm=True),
            ActionItem(
                "Shutdown",
                shutdown_pi,
                confirm=True,
                progress_message="Shutting down...",
                terminal=True,
            ),
            ActionItem("Exit"),
        ),
    ),
)


class Dashboard:
    def __init__(self):
        self.i2c = board.I2C()  # GPIO3/SCL (pin 5), GPIO2/SDA (pin 3)
        self.oled = adafruit_ssd1306.SSD1306_I2C(
            WIDTH, HEIGHT, self.i2c, addr=I2C_ADDRESS
        )
        self.button_down = self._make_button(BUTTON_DOWN_PIN)
        self.button_select = self._make_button(BUTTON_SELECT_PIN)
        self.button_up = self._make_button(BUTTON_UP_PIN)
        self.buttons = (self.button_down, self.button_select, self.button_up)

        self.image = Image.new("1", (WIDTH, HEIGHT))
        self.draw = ImageDraw.Draw(self.image)
        self.font = ImageFont.load_default()
        self.screen_index = 0
        self.item_index = 0
        self.action_mode = False
        self.last_refresh = 0.0

    @staticmethod
    def _make_button(pin):
        button = digitalio.DigitalInOut(pin)
        button.direction = digitalio.Direction.INPUT
        button.pull = digitalio.Pull.UP
        return button

    @property
    def screen(self):
        return SCREENS[self.screen_index]

    def display(self, title: str, lines: list[str], selected: int | None = None):
        self.draw.rectangle((0, 0, WIDTH, HEIGHT), fill=0)
        self.draw.text((0, 0), title[:21], font=self.font, fill=255)
        for index, text in enumerate(lines[:5]):
            prefix = ">" if selected == index else " "
            self.draw.text((0, 12 + index * 10), prefix, font=self.font, fill=255)
            self.draw.text((8, 12 + index * 10), text[:20], font=self.font, fill=255)
        self.oled.image(self.image)
        self.oled.show()
        self.last_refresh = time.monotonic()

    def render(self):
        if isinstance(self.screen, InfoScreen):
            try:
                lines = self.screen.content()
            except Exception as error:  # Keep the dashboard alive if a plugin fails.
                lines = ["Content error", type(error).__name__]
            self.display(self.screen.title, lines)
        else:
            self.display(
                self.screen.title,
                [item.label for item in self.screen.items],
                self.item_index if self.action_mode else None,
            )

    @staticmethod
    def _wait_for_release(button):
        while not button.value:
            time.sleep(0.01)
        time.sleep(0.03)

    def move_screen(self, offset: int):
        self.screen_index = (self.screen_index + offset) % len(SCREENS)
        self.item_index = 0
        # Enter action selection directly when an action page is reached.
        self.action_mode = isinstance(self.screen, ActionScreen)
        self.render()

    def move_action(self, offset: int):
        self.item_index = (self.item_index + offset) % len(self.screen.items)
        self.render()

    def confirm(self, label: str) -> bool:
        choice = 0  # Cancel is deliberately the safe default.
        while True:
            self.display("CONFIRM", [label[:20], "Cancel", "Confirm"], choice + 1)
            if not self.button_down.value or not self.button_up.value:
                button = self.button_down if not self.button_down.value else self.button_up
                self._wait_for_release(button)
                choice = 1 - choice
            elif not self.button_select.value:
                self._wait_for_release(self.button_select)
                return choice == 1
            time.sleep(0.02)

    def run_action(self):
        item = self.screen.items[self.item_index]
        if item.callback is None:  # Mandatory Exit item.
            self.action_mode = False
            self.render()
            return
        if item.confirm and not self.confirm(item.label):
            self.render()
            return

        self.display("SYSTEM", [item.label, item.progress_message])
        try:
            result = item.callback()
        except Exception as error:
            print(f"Action failed: {error}")
            result = "Action failed"
        if item.terminal and result == "Shutdown requested":
            # The host cannot report that it is fully off. Keep a meaningful
            # message in the OLED buffer until the Pi removes power.
            self.display("SYSTEM", ["Shutting down...", "Please wait"])
            while True:
                time.sleep(1)
        self.display("RESULT", [result[index:index + 20] for index in range(0, len(result), 20)])
        time.sleep(2)
        self.render()

    def run(self):
        self.render()
        while True:
            if not self.button_down.value:
                self._wait_for_release(self.button_down)
                if self.action_mode:
                    self.move_action(1)
                else:
                    self.move_screen(1)
            elif not self.button_up.value:
                self._wait_for_release(self.button_up)
                if self.action_mode:
                    self.move_action(-1)
                else:
                    self.move_screen(-1)
            elif not self.button_select.value:
                self._wait_for_release(self.button_select)
                if isinstance(self.screen, ActionScreen):
                    if self.action_mode:
                        self.run_action()
                    else:
                        self.action_mode = True
                        self.render()
            elif (
                isinstance(self.screen, InfoScreen)
                and time.monotonic() - self.last_refresh >= REFRESH_SECONDS
            ):
                self.render()
            time.sleep(0.02)

    def close(self):
        self.oled.fill(0)
        self.oled.show()
        for button in self.buttons:
            button.deinit()
        self.i2c.deinit()


def main():
    dashboard = None
    try:
        dashboard = Dashboard()
        dashboard.run()
    except KeyboardInterrupt:
        pass
    finally:
        if dashboard is not None:
            dashboard.close()


if __name__ == "__main__":
    main()
