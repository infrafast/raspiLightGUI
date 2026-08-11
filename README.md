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

Refreshed every 10 seconds:

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

## Permanent service installation

The service pack follows the same lifecycle pattern as Oculizer. Run the
read-only preflight first, then install:

```bash
chmod +x raspi_service_pack/install.sh raspi_service_pack/raspilightgui-service
./raspi_service_pack/install.sh --check --service-user pi
sudo ./raspi_service_pack/install.sh --service-user pi
```

The installer:

- installs the Python, I²C, GPIO Zero and `lgpio` dependencies;
- enables the Raspberry Pi I²C interface;
- creates `.venv` and installs `requirements.txt`;
- adds the service account to the `gpio` and `i2c` groups;
- installs `raspilightgui.service` and its lifecycle command;
- installs narrowly scoped passwordless permissions for service control and
  system shutdown;
- leaves the current enabled/running state unchanged.

Enable at boot and start immediately:

```bash
raspilightgui-service auto
```

Lifecycle commands:

```bash
raspilightgui-service start
raspilightgui-service stop
raspilightgui-service restart
raspilightgui-service status
raspilightgui-service logs
raspilightgui-service last-state
raspilightgui-service health
raspilightgui-service noauto
```

`noauto` disables boot startup without stopping a currently running instance.
For a foreground diagnostic using the installed environment, run:

```bash
raspilightgui-service run-auto
```

The systemd unit uses `Restart=always` with a five-second delay, so an
unexpected exit is restarted without creating a tight failure loop. A normal
`raspilightgui-service stop` remains stopped.

## Runtime efficiency

- Buttons use GPIO edge callbacks through `gpiozero`/`lgpio`; there is no
  continuous button-polling loop.
- The main thread sleeps until a button event or the next information refresh.
- Monitoring and service states are sampled every 10 seconds and only for the
  information screen currently displayed.
- The `eth0` address is cached and checked at most once per minute.
- The OLED buffer is sent over I²C only when the rendered content has changed.
- Action screens do not have a periodic refresh.
- Button debounce is handled at the GPIO event layer with a 50 ms interval.

The service-pack commands must be installed at:

```text
/usr/local/bin/livestageassistant
/usr/local/bin/oculizer-service
```

The dashboard user must own the running QLC+ process so that it can read and
restart it. The installer creates the narrowly scoped shutdown and service
control permissions automatically.

## Manual development run

For development without installing the systemd unit:

```bash
sudo raspi-config nonint do_i2c 0
sudo apt install python3-venv python3-gpiozero python3-lgpio
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
GPIOZERO_PIN_FACTORY=lgpio python lightGUI.py
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
