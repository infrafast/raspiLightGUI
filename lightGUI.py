"""Interactive SSD1306 menu for Raspberry Pi 5 running Raspberry Pi OS."""

from datetime import datetime
import time

import adafruit_ssd1306
import board
import digitalio
from PIL import Image, ImageDraw, ImageFont


WIDTH = 128
HEIGHT = 64
I2C_ADDRESS = 0x3C

# BCM GPIO numbers for Down/Back, Select/OK and Up/Next respectively.
BUTTON_DOWN_PIN = board.D5    # Physical pin 29
BUTTON_SELECT_PIN = board.D6  # Physical pin 31
BUTTON_UP_PIN = board.D13     # Physical pin 33
MENU = ("1. Temperature", "2. Date", "3. Time", "4. Wind TJ", "5. Exit")


class LightGUI:
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
        self.current_option = 0

    @staticmethod
    def _make_button(pin):
        button = digitalio.DigitalInOut(pin)
        button.direction = digitalio.Direction.INPUT
        button.pull = digitalio.Pull.UP
        return button

    def _display_lines(self, lines):
        self.draw.rectangle((0, 0, WIDTH, HEIGHT), fill=0)
        for text, x, y in lines:
            self.draw.text((x, y), text, font=self.font, fill=255)
        self.oled.image(self.image)
        self.oled.show()

    def show_menu(self):
        lines = [("MAIN MENU:", 0, 0)]
        for index, item in enumerate(MENU):
            y = 12 + index * 10
            lines.append((">" if index == self.current_option else " ", 0, y))
            lines.append((item, 10, y))
        self._display_lines(lines)

    def show_info(self):
        now = datetime.now()
        messages = (
            "Temp: 24 C",
            f"Date: {now:%d/%m/%y}",
            f"Time: {now:%H:%M}",
            "Wind: 15 km/h",
            "Exiting...",
        )
        self._display_lines([(messages[self.current_option], 0, 0)])
        time.sleep(2)

    @staticmethod
    def _wait_for_release(button):
        while not button.value:
            time.sleep(0.01)
        time.sleep(0.03)  # Debounce the release edge.

    def run(self):
        self.show_menu()
        while True:
            if not self.button_down.value:
                self.current_option = (self.current_option - 1) % len(MENU)
                self._wait_for_release(self.button_down)
                self.show_menu()
            elif not self.button_up.value:
                self.current_option = (self.current_option + 1) % len(MENU)
                self._wait_for_release(self.button_up)
                self.show_menu()
            elif not self.button_select.value:
                self._wait_for_release(self.button_select)
                self.show_info()
                if self.current_option == len(MENU) - 1:
                    return
                self.show_menu()
            time.sleep(0.02)

    def close(self):
        self.oled.fill(0)
        self.oled.show()
        for button in self.buttons:
            button.deinit()
        self.i2c.deinit()


def main():
    app = None
    try:
        app = LightGUI()
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    main()
