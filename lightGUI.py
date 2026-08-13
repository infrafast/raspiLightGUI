"""Extensible SSD1306 dashboard presenter for Raspberry Pi 5."""

import argparse
from dataclasses import dataclass
import signal
from threading import Event
import time
from typing import Callable

from system_actions import (
    restart_assistant,
    restart_oculizer,
    restart_qlcplus,
    shutdown_pi,
    stop_assistant,
    stop_oculizer,
)
from system_info import ScreenData, monitor_content, service_content
from status_led import StatusLedController
from ui_backends import create_backend


REFRESH_SECONDS = 10.0
OLED_SLEEP_SECONDS = 300.0
ContentProvider = Callable[[], ScreenData | list[str]]
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
    default_index: int = 0


# Model: add screens and plug regular Python callables into this registry.
SCREENS = (
    InfoScreen("MONITOR", monitor_content),
    InfoScreen("SERVICE STATE", service_content),
    ActionScreen(
        "SYSTEM",
        (
            ActionItem("Restart Assistant", restart_assistant, confirm=True),
            ActionItem("Stop Assistant", stop_assistant, confirm=True),
            ActionItem("Restart Oculizer", restart_oculizer, confirm=True),
            ActionItem("Stop Oculizer", stop_oculizer, confirm=True),
            ActionItem("Restart QLC+", restart_qlcplus, confirm=True),
            ActionItem(
                "Shutdown",
                shutdown_pi,
                confirm=True,
                progress_message="Shutting down...",
                terminal=True,
            ),
            ActionItem("Back"),
        ),
        default_index=6,
    ),
)


class DashboardPresenter:
    """Hardware-independent navigation and action presentation."""

    def __init__(self, view, input_device, sleep_seconds: float):
        self.view = view
        self.input = input_device
        self.screen_index = 0
        self.item_index = 0
        self.action_mode = False
        self.last_refresh = 0.0
        self.last_activity = time.monotonic()
        self.sleep_seconds = sleep_seconds
        self.display_sleeping = False
        self.stop_requested = False
        self.shutdown_in_progress = False

    @property
    def screen(self):
        return SCREENS[self.screen_index]

    def display(self, title: str, lines: list[str], selected: int | None = None):
        self.view.display(title, lines, selected)
        self.last_refresh = time.monotonic()

    def render(self):
        # In headless mode the LED worker is the only user interface. Avoid
        # collecting temperature, CPU and service data that nobody can see.
        if getattr(self.view, "is_headless", False):
            self.last_refresh = time.monotonic()
            return
        if isinstance(self.screen, InfoScreen):
            try:
                content = self.screen.content()
                if isinstance(content, ScreenData):
                    lines = content.lines
                    alert = content.alert
                else:
                    lines = content
                    alert = False
            except Exception as error:
                print(f"Content provider failed: {error}")
                lines = ["Content error", type(error).__name__]
                alert = True
            title = self.screen.title + (" /!\\" if alert else "")
            self.display(title, lines)
        else:
            if not self.action_mode:
                self.display(self.screen.title, ["OK=enter menu"])
                return
            visible_count = 5
            max_start = max(0, len(self.screen.items) - visible_count)
            window_start = min(max(self.item_index - visible_count + 1, 0), max_start)
            visible_items = self.screen.items[
                window_start : window_start + visible_count
            ]
            self.display(
                self.screen.title,
                [item.label for item in visible_items],
                self.item_index - window_start if self.action_mode else None,
            )

    def move_screen(self, offset: int):
        self.screen_index = (self.screen_index + offset) % len(SCREENS)
        self.action_mode = False
        self.item_index = 0
        self.render()

    def move_action(self, offset: int):
        self.item_index = (self.item_index + offset) % len(self.screen.items)
        self.render()

    def confirm(self, label: str) -> bool:
        choice = 0
        while not self.stop_requested:
            self.display("CONFIRM", [label[:20], "Cancel", "Confirm"], choice + 1)
            event = self.input.next_event()
            if event in ("down", "up"):
                choice = 1 - choice
            elif event == "select":
                return choice == 1
            elif event == "quit":
                self.request_stop()
        return False

    def run_action(self):
        item = self.screen.items[self.item_index]
        if item.callback is None:
            self.action_mode = False
            self.render()
            return
        if item.confirm and not self.confirm(item.label):
            self.render()
            return

        self.display("SYSTEM", [item.label, item.progress_message])
        self.shutdown_in_progress = item.terminal
        try:
            result = item.callback()
        except Exception as error:
            print(f"Action failed: {error}")
            result = "Action failed"
        if item.terminal and result == "Shutdown requested":
            self.display("SYSTEM", ["Shutting down...", "Please wait"])
            while True:
                signal.pause()
        self.shutdown_in_progress = False
        lines = [result[index:index + 20] for index in range(0, len(result), 20)]
        self.display("RESULT", lines)
        time.sleep(2)
        self.input.discard_events()
        self.render()

    def run(self):
        self.render()
        while not self.stop_requested:
            now = time.monotonic()
            deadlines = []
            if (
                isinstance(self.screen, InfoScreen)
                and not getattr(self.view, "is_headless", False)
            ):
                deadlines.append(self.last_refresh + REFRESH_SECONDS)
            if (
                self.sleep_seconds > 0
                and self.view.can_sleep
                and not self.display_sleeping
            ):
                deadlines.append(self.last_activity + self.sleep_seconds)
            timeout = max(0.0, min(deadlines) - now) if deadlines else None
            event = self.input.next_event(timeout)
            if self.stop_requested:
                break
            if event not in (None, "unknown"):
                self.last_activity = time.monotonic()
                if self.display_sleeping:
                    self.view.wake()
                    self.display_sleeping = False
                    self.render()
                    continue
            if event == "down":
                self.move_action(1) if self.action_mode else self.move_screen(1)
            elif event == "up":
                self.move_action(-1) if self.action_mode else self.move_screen(-1)
            elif event == "select" and isinstance(self.screen, ActionScreen):
                if self.action_mode:
                    self.run_action()
                else:
                    self.action_mode = True
                    self.item_index = self.screen.default_index
                    self.render()
            elif event == "quit":
                self.request_stop()
            elif event is None:
                now = time.monotonic()
                if (
                    self.sleep_seconds > 0
                    and self.view.can_sleep
                    and not self.display_sleeping
                    and now - self.last_activity >= self.sleep_seconds
                ):
                    self.display_sleeping = self.view.sleep()
                if (
                    isinstance(self.screen, InfoScreen)
                    and not getattr(self.view, "is_headless", False)
                    and now - self.last_refresh >= REFRESH_SECONDS
                ):
                    self.render()

    def request_stop(self):
        self.stop_requested = True
        self.input.wake_up()

    def close(self):
        self.input.close()
        self.view.close()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("auto", "hardware", "console"),
        default="auto",
        help="I/O backend (default: auto with interactive console fallback)",
    )
    parser.add_argument(
        "--sleep-timeout",
        type=float,
        default=OLED_SLEEP_SECONDS,
        metavar="SECONDS",
        help="OLED inactivity timeout; 0 disables sleep (default: 300)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    presenter = None
    led_controller = None
    led_failure = Event()

    def stop_service(_signum, _frame):
        if presenter is not None and presenter.shutdown_in_progress:
            raise SystemExit(0)
        if presenter is not None:
            presenter.request_stop()

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    try:
        def led_failed(error):
            print(f"Status LED worker failed: {error}")
            led_failure.set()
            if presenter is not None:
                presenter.request_stop()

        try:
            led_controller = StatusLedController(on_failure=led_failed)
        except Exception as error:
            raise RuntimeError(f"status LED GPIO unavailable: {error}") from error
        led_controller.start()
        view, input_device, backend = create_backend(args.backend)
        print(f"Dashboard backend: {backend}")
        presenter = DashboardPresenter(view, input_device, max(0.0, args.sleep_timeout))
        if led_failure.is_set():
            presenter.request_stop()
        presenter.run()
        if led_controller.error is not None:
            raise RuntimeError(f"status LED failed: {led_controller.error}")
    except (OSError, RuntimeError) as error:
        print(f"Startup failed: {error}")
        raise SystemExit(1) from None
    finally:
        if presenter is not None and not presenter.shutdown_in_progress:
            presenter.close()
        if led_controller is not None:
            led_controller.stop()


if __name__ == "__main__":
    main()
