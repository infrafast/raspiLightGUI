# Interactive Menu with an OLED Display and Buttons on Raspberry Pi 5


**Student**: Lennyn Alejandro Castillejo Robles<br>
**Course**: Programmable Systems

This project implements an extensible system dashboard on an `SSD1306` OLED
display using a Raspberry Pi 5 running Raspberry Pi OS and Python 3. Three
buttons navigate information pages and execute confirmed system actions.

---

## 🛠️ Components Used

- **Raspberry Pi 5 (Raspberry Pi OS)**
- **SSD1306 OLED display (128x64 pixels, I2C protocol)**
- **3 physical buttons**

---

## 🔌 Connections

### 📟 OLED Display (SSD1306)
| OLED | Raspberry Pi 5 pin |
|------|----------|
| VCC  | 3.3V     |
| GND  | GND      |
| SDA  | GPIO2 (physical pin 3) |
| SCL  | GPIO3 (physical pin 5) |

### 🔘 Buttons

| Function | GPIO | Physical pin |
|----------|------|--------------|
| Button 1 (Down) — ◀ / BACK | **GPIO5** | **Pin 29** |
| Button 2 (Select) — OK | **GPIO6** | **Pin 31** |
| Button 3 (Up) — ▶ / NEXT | **GPIO13** | **Pin 33** |
| Button common ground | GND | **Pin 30** or **Pin 34** |

All buttons are configured with an **internal pull-up resistor**. Connect one side
of each button to its GPIO pin and connect their common side to physical GND pin
30 or 34.

---

## Dashboard screens

### MONITOR

Refreshed every second:

- CPU temperature and system uptime
- CPU, RAM and root filesystem usage
- IPv4 address of `eth0`

### SERVICE STATE

- Oculizer systemd state: `AUTO`, `MANUAL`, `DOWN`, or `UNKNOWN`
- Live Stage Assistant systemd state: `UP`, `DOWN`, or `UNKNOWN`
- `qlcplus-qml` process state

### SYSTEM

- Restart Live Stage Assistant
- Restart Oculizer
- Restart QLC+ with its captured executable, arguments, working directory and
  environment
- Shut down the Raspberry Pi
- Exit action mode and return to screen navigation

All system actions require confirmation. `Cancel` is selected by default. For a
shutdown, the OLED displays `Shutting down...` before the poweroff request and
keeps that message buffered while Raspberry Pi OS stops. The display becomes
black when its power is removed; software running on the Pi cannot confirm a
state reached after the Pi itself has powered off.

After each non-terminal action, the OLED shows a short result such as
`Assistant restarted`, `Oculizer failed`, or `QLC+ not running`. More detailed
command errors are written to the console instead of overflowing the display.

## Navigation

In information-screen mode:

- **Down / BACK** opens the next screen.
- **Up / NEXT** opens the previous screen.
- Reaching `SYSTEM` enters action mode automatically.

In action mode:

- **Down** and **Up** select an item.
- **OK** executes or confirms the selected item.
- **Exit** returns to screen-navigation mode. Pressing **OK** on the inactive
  `SYSTEM` screen enters action mode again.

---

## Installation and execution

```bash
sudo raspi-config nonint do_i2c 0
sudo apt install python3-venv
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
python lightGUI.py
```

The service-pack commands must be installed at:

```text
/usr/local/bin/livestageassistant
/usr/local/bin/oculizer-service
```

The dashboard user must own the running QLC+ process so that it can read and
restart it. To allow shutdown without an interactive password, create a narrowly
scoped sudoers rule with `sudo visudo -f /etc/sudoers.d/raspi-light-gui`:

```sudoers
pi ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
```

## Extending the dashboard

The screen registry is the `SCREENS` tuple in `lightGUI.py`:

```python
InfoScreen("MY INFO", my_content_function)
ActionScreen(
    "MY ACTIONS",
    (
        ActionItem("Do something", my_action_function, confirm=True),
        ActionItem("Exit"),
    ),
)
```

An information provider returns `list[str]`. An action returns a short status
string. Providers are kept in `system_info.py`, actions in `system_actions.py`,
and may call other Python modules or external programs. Every action screen must
end with an `Exit` item whose callback is omitted.
