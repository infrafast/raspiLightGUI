"""Hardware and terminal view/input adapters for the dashboard presenter."""

from queue import Empty, SimpleQueue
import os
from pathlib import Path
import select
import sys
from threading import Event
import time


WIDTH = 128
HEIGHT = 64
I2C_ADDRESS = 0x3C
SUPPORTED_I2C_ADDRESSES = (0x3C, 0x3D)


class OledView:
    """SSD1306 implementation of the dashboard view."""

    can_sleep = True

    def __init__(self):
        import adafruit_ssd1306
        import board
        from PIL import Image, ImageDraw, ImageFont

        self.i2c = board.I2C()
        address = self._detect_address()
        self.oled = adafruit_ssd1306.SSD1306_I2C(
            WIDTH, HEIGHT, self.i2c, addr=address
        )
        self.image = Image.new("1", (WIDTH, HEIGHT))
        self.draw = ImageDraw.Draw(self.image)
        self.title_fonts, self.body_fonts = self._load_fonts(ImageFont)
        self.last_frame = None
        self.sleeping = False

    @staticmethod
    def _load_fonts(image_font):
        """Load a proportional condensed font, with a built-in fallback."""
        candidates = (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        )
        font_path = next((path for path in candidates if path.is_file()), None)
        if font_path is None:
            fallback = image_font.load_default()
            return (fallback,), (fallback,)
        title_fonts = tuple(
            image_font.truetype(str(font_path), size) for size in (10, 9, 8)
        )
        body_fonts = tuple(
            image_font.truetype(str(font_path), size) for size in (9, 8, 7)
        )
        return title_fonts, body_fonts

    def _fit_text(self, text: str, max_width: int, fonts):
        """Choose the largest fitting font, then trim only as a last resort."""
        for font in fonts:
            if self.draw.textlength(text, font=font) <= max_width:
                return text, font
        font = fonts[-1]
        suffix = "..."
        while text and self.draw.textlength(text + suffix, font=font) > max_width:
            text = text[:-1]
        return text + suffix, font

    def _detect_address(self) -> int:
        deadline = time.monotonic() + 2.0
        while not self.i2c.try_lock():
            if time.monotonic() >= deadline:
                raise RuntimeError("I2C bus is busy")
            time.sleep(0.01)
        try:
            addresses = self.i2c.scan()
        except OSError as error:
            raise RuntimeError(f"I2C scan failed: {error}") from error
        finally:
            self.i2c.unlock()

        if I2C_ADDRESS in addresses:
            return I2C_ADDRESS
        for address in SUPPORTED_I2C_ADDRESSES:
            if address in addresses:
                print(f"OLED detected at 0x{address:02X}")
                return address
        found = ", ".join(f"0x{address:02X}" for address in addresses) or "none"
        raise RuntimeError(
            f"no SSD1306 connected (expected 0x3C/0x3D; found: {found})"
        )

    def display(self, title: str, lines: list[str], selected: int | None = None):
        if self.sleeping:
            return
        frame = (title, tuple(lines[:5]), selected)
        if frame == self.last_frame:
            return
        self.draw.rectangle((0, 0, WIDTH, HEIGHT), fill=0)
        title, title_font = self._fit_text(title, WIDTH, self.title_fonts)
        self.draw.text((0, 0), title, font=title_font, fill=255)
        for index, text in enumerate(lines[:5]):
            prefix = ">" if selected == index else " "
            text, body_font = self._fit_text(text, WIDTH - 8, self.body_fonts)
            y = 14 + index * 10
            self.draw.text((0, y), prefix, font=body_font, fill=255)
            self.draw.text((8, y), text, font=body_font, fill=255)
        self.oled.image(self.image)
        self.oled.show()
        self.last_frame = frame

    def sleep(self) -> bool:
        if not self.sleeping:
            if hasattr(self.oled, "poweroff"):
                self.oled.poweroff()
            else:
                self.oled.fill(0)
                self.oled.show()
            self.sleeping = True
        return True

    def wake(self):
        if self.sleeping:
            if hasattr(self.oled, "poweron"):
                self.oled.poweron()
            self.sleeping = False
            self.last_frame = None

    def close(self):
        self.wake()
        self.oled.fill(0)
        self.oled.show()
        self.i2c.deinit()


class GpioInput:
    """Edge-triggered GPIO button input; it performs no active polling."""

    def __init__(self):
        from gpiozero import Button

        self.events = SimpleQueue()
        self.wake = Event()
        self.buttons = (
            self._make_button(Button, 5, "down"),
            self._make_button(Button, 6, "select"),
            self._make_button(Button, 13, "up"),
        )

    def _make_button(self, button_class, gpio: int, event_name: str):
        button = button_class(gpio, pull_up=True, bounce_time=0.05)
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


class ConsoleView:
    """TTY representation with the same 21x6 logical display area."""

    can_sleep = False

    def __init__(self):
        self.last_frame = None

    @staticmethod
    def _fit_text(text: str, width: int) -> str:
        if len(text) <= width:
            return text
        if width <= 3:
            return "." * width
        return text[: width - 3] + "..."

    def display(self, title: str, lines: list[str], selected: int | None = None):
        frame = (title, tuple(lines[:5]), selected)
        if frame == self.last_frame:
            return
        rows = [self._fit_text(title, 21)]
        for index, text in enumerate(lines[:5]):
            prefix = ">" if selected == index else " "
            rows.append(prefix + self._fit_text(text, 20))
        rows.extend([""] * (6 - len(rows)))
        print("\033[2J\033[H", end="")
        print("+---------------------+")
        for row in rows[:6]:
            print(f"|{row:<21}|")
        print("+---------------------+")
        print("Arrows: navigate | Enter: OK | q: quit", flush=True)
        self.last_frame = frame

    def close(self):
        print("\033[0m", end="", flush=True)

    def sleep(self) -> bool:
        return False

    def wake(self):
        pass


class KeyboardInput:
    """Blocking terminal keyboard adapter for interactive simulation."""

    def __init__(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("console backend requires an interactive TTY")
        import termios
        import tty

        self.termios = termios
        self.fd = sys.stdin.fileno()
        self.previous_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def next_event(self, timeout: float | None = None) -> str | None:
        readable, _, _ = select.select([self.fd], [], [], timeout)
        if not readable:
            return None
        data = os.read(self.fd, 3)
        if data in (b"\r", b"\n"):
            return "select"
        if data in (b"q", b"Q", b"\x03"):
            return "quit"
        if data in (b"\x1b[B", b"\x1b[C"):
            return "down"
        if data in (b"\x1b[A", b"\x1b[D"):
            return "up"
        return "unknown"

    def discard_events(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 32)

    def wake_up(self):
        # Unix signals interrupt select(), so no explicit wake pipe is needed.
        pass

    def close(self):
        self.termios.tcsetattr(
            self.fd, self.termios.TCSADRAIN, self.previous_settings
        )


def create_backend(mode: str):
    """Build matching view/input adapters, with interactive auto fallback."""
    if mode == "console":
        return ConsoleView(), KeyboardInput(), "console"
    try:
        view = OledView()
        try:
            input_device = GpioInput()
        except Exception:
            view.close()
            raise
        return view, input_device, "hardware"
    except Exception as error:
        if mode == "auto" and sys.stdin.isatty() and sys.stdout.isatty():
            print(f"Hardware unavailable: {error}")
            print("Using interactive console simulation.")
            return ConsoleView(), KeyboardInput(), "console"
        raise RuntimeError(f"hardware unavailable: {error}") from error
