"""Extensible SSD1306 dashboard presenter for Raspberry Pi 5."""

import argparse
from dataclasses import dataclass
from functools import partial
import signal
from threading import Event
import time
from typing import Callable

from managed_services import MANAGED_SERVICES, ServiceDefinition
from system_actions import reboot_pi, run_service_action, shutdown_pi
from system_info import (
    ScreenData,
    invalidate_service_states,
    managed_service_states,
    monitor_content,
    service_content,
)
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
    submenu: Callable[[], "ActionMenu"] | None = None
    confirm: bool = False
    progress_message: str = "Working..."
    terminal: bool = False


@dataclass(frozen=True)
class ActionScreen:
    title: str
    menu: Callable[[], "ActionMenu"]


@dataclass(frozen=True)
class ActionMenu:
    title: str
    items: tuple[ActionItem, ...]
    preview_lines: tuple[str, ...] = ()
    alert: bool = False


def service_action_menu(service: ServiceDefinition) -> ActionMenu:
    """Build one contextual service submenu from the shared state snapshot."""
    status = managed_service_states()[service.key]
    items: list[ActionItem] = []
    if status.enabled is None:
        actions = ()
    elif status.runtime in ("UP", "STARTING"):
        actions = ("stop", "restart")
    elif status.runtime in ("DOWN", "FAILED", "STOPPING"):
        actions = ("start",)
    else:
        actions = ()
    for action in actions:
        items.append(
            ActionItem(
                f"{action.title()} {service.label}",
                partial(run_service_action, service, action),
                confirm=True,
            )
        )
    if status.enabled is True:
        items.append(
            ActionItem(
                "Manual",
                partial(run_service_action, service, "noauto"),
                confirm=True,
            )
        )
    elif status.enabled is False:
        items.append(
            ActionItem(
                "Auto",
                partial(run_service_action, service, "auto"),
                confirm=True,
            )
        )
    items.append(ActionItem("Back"))
    return ActionMenu(
        f"{service.label} {status.display_state}", tuple(items), alert=status.alert
    )


def system_action_menu() -> ActionMenu:
    """Build the compact root menu from the single service declaration."""
    service_data = service_content()
    items: list[ActionItem] = [
        ActionItem(
            line,
            submenu=partial(service_action_menu, service),
        )
        for service, line in zip(MANAGED_SERVICES, service_data.lines)
    ]
    items.extend(
        (
            ActionItem(
                "Reboot",
                reboot_pi,
                confirm=True,
                progress_message="Rebooting...",
                terminal=True,
            ),
            ActionItem(
                "Shutdown",
                shutdown_pi,
                confirm=True,
                progress_message="Shutting down...",
                terminal=True,
            ),
            ActionItem("Back"),
        )
    )
    return ActionMenu(
        "SYSTEM",
        tuple(items),
        tuple(service_data.lines + ["Reboot / Shutdown", "OK = enter menu"]),
        service_data.alert,
    )


# Model: add screens and plug regular Python callables into this registry.
SCREENS = (
    InfoScreen("MONITOR", monitor_content),
    ActionScreen(
        "SYSTEM",
        system_action_menu,
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
        self.action_menu: ActionMenu | None = None
        self.menu_provider: Callable[[], ActionMenu] | None = None
        self.menu_stack: list[
            tuple[ActionMenu, Callable[[], ActionMenu], int]
        ] = []
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
            if self.action_menu is None:
                self.refresh_action_menu()
            action_menu = self.action_menu
            title = action_menu.title + (" /!\\" if action_menu.alert else "")
            if not self.action_mode:
                self.display(title, list(action_menu.preview_lines))
                return
            visible_count = 5
            default_index = len(action_menu.items) - 1
            display_index = self.item_index if self.action_mode else default_index
            max_start = max(0, len(action_menu.items) - visible_count)
            window_start = min(max(display_index - visible_count + 1, 0), max_start)
            visible_items = action_menu.items[
                window_start : window_start + visible_count
            ]
            labels = [item.label for item in visible_items]
            self.display(
                title,
                labels,
                display_index - window_start if self.action_mode else None,
            )

    def move_screen(self, offset: int):
        self.screen_index = (self.screen_index + offset) % len(SCREENS)
        self.action_mode = False
        self.menu_stack.clear()
        if isinstance(self.screen, ActionScreen):
            self.menu_provider = self.screen.menu
            self.refresh_action_menu(force=True)
        else:
            self.action_menu = None
            self.menu_provider = None
            self.item_index = 0
        self.render()

    def refresh_action_menu(self, force: bool = False):
        if force:
            invalidate_service_states()
        if self.menu_provider is None:
            self.menu_provider = self.screen.menu
        self.action_menu = self.menu_provider()
        self.item_index = len(self.action_menu.items) - 1

    def move_action(self, offset: int):
        self.item_index = (self.item_index + offset) % len(self.action_menu.items)
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
        item = self.action_menu.items[self.item_index]
        if item.submenu is not None:
            self.menu_stack.append((self.action_menu, self.menu_provider, self.item_index))
            self.menu_provider = item.submenu
            self.refresh_action_menu()
            self.render()
            return
        if item.callback is None:
            if self.menu_stack:
                self.action_menu, self.menu_provider, self.item_index = self.menu_stack.pop()
            else:
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
        if item.terminal and result == "Reboot requested":
            self.display("SYSTEM", ["Rebooting...", "Please wait"])
            while True:
                signal.pause()
        self.shutdown_in_progress = False
        lines = [result[index:index + 20] for index in range(0, len(result), 20)]
        self.display("RESULT", lines)
        time.sleep(2)
        self.input.discard_events()
        self.refresh_action_menu(force=True)
        self.render()

    def run(self):
        self.render()
        while not self.stop_requested:
            now = time.monotonic()
            deadlines = []
            if (
                (
                    isinstance(self.screen, InfoScreen)
                    or isinstance(self.screen, ActionScreen) and not self.action_mode
                )
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
                    self.item_index = len(self.action_menu.items) - 1
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
                    (
                        isinstance(self.screen, InfoScreen)
                        or isinstance(self.screen, ActionScreen)
                        and not self.action_mode
                    )
                    and not getattr(self.view, "is_headless", False)
                    and now - self.last_refresh >= REFRESH_SECONDS
                ):
                    if isinstance(self.screen, ActionScreen):
                        self.refresh_action_menu(force=True)
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
