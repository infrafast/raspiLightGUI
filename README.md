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

- CPU temperature, Pi 5 input voltage and power state
- System uptime
- CPU, RAM and root filesystem usage
- IPv4 address of `eth0`

### SERVICE STATE

- Oculizer systemd state: `AUTO`, `MANUAL`, `STARTING`, `STOPPING`, `FAILED`,
  `DOWN`, or `UNKNOWN`
- Live Stage Assistant systemd state: `UP`, `STARTING`, `STOPPING`, `FAILED`,
  `DOWN`, or `UNKNOWN`
- `qlcplus-qml` process state

### SYSTEM

- Restart Live Stage Assistant
- Restart Oculizer
- Restart QLC+ with its captured executable, arguments, working directory and
  environment
- Shut down the Raspberry Pi
- Go back from action mode to screen navigation

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
- **Back** returns to screen-navigation mode. Pressing **OK** on the inactive
  `SYSTEM` screen enters action mode again.
- `Shutdown` is selected by default whenever the `SYSTEM` action menu is entered.

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
- installs the proportional DejaVu font used by the OLED renderer;
- enables the Raspberry Pi I²C interface;
- creates `.venv` and installs `requirements.txt`;
- adds the service account to the `gpio` and `i2c` groups;
- installs `raspilightgui.service` and its lifecycle command;
- installs narrowly scoped passwordless permissions for service control and
  system shutdown, plus restarting `livestageassistant.service` from the OLED;
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

The installed service explicitly uses `--backend hardware`. If the OLED is
missing, its journal contains a short `no SSD1306 connected` startup error and
systemd retries after five seconds without emitting a Python traceback.

## Runtime efficiency

- Buttons use GPIO edge callbacks through `gpiozero`/`lgpio`; there is no
  continuous button-polling loop.
- The main thread sleeps until a button event or the next information refresh.
- Monitoring and service states are sampled every 10 seconds and only for the
  information screen currently displayed.
- The `eth0` address is cached and checked at most once per minute.
- The OLED buffer is sent over I²C only when the rendered content has changed.
- OLED text uses proportional DejaVu Sans Condensed when available. Each title
  and body line selects the largest configured size that fits its measured pixel
  width and is shortened with `...` only as a final fallback.
- Action screens do not have a periodic refresh.
- Button debounce is handled at the GPIO event layer with a 50 ms interval.

### Pi 5 power state

The MONITOR page reads the Pi 5 PMIC input with
`vcgencmd pmic_read_adc EXT5V_V` and displays a compact line such as:

```text
T:45.0C V:5.08 OK
```

Power states use these thresholds:

| State | Condition |
|-------|-----------|
| `OK` | 5 V input is at least 4.80 V |
| `LOW` | 5 V input is above 4.65 V and below 4.80 V |
| `CRIT` | 5 V input is at or below 4.65 V, or the current undervoltage bit from `vcgencmd get_throttled` is set |
| `N/A` | The PMIC reading is unavailable or unsupported |

The 4.80 V reliability target and approximately 4.63 V hardware undervoltage
threshold follow Raspberry Pi guidance. The UI deliberately uses 4.65 V as its
critical boundary to provide a small safety margin. These values describe the
Pi input, not an adjustable CPU core voltage.

The service-pack commands must be installed at:

```text
/usr/local/bin/livestageassistant
/usr/local/bin/oculizer-service
```

The dashboard user must own the running QLC+ process so that it can read and
restart it. The installer creates the narrowly scoped shutdown and service
control permissions automatically.

The Live Stage Assistant wrapper calls `sudo systemctl restart`. Since the OLED
service cannot enter an interactive password, the installer permits only this
exact additional command for the configured service user:

```text
/usr/bin/systemctl restart livestageassistant.service
```

This is not a general passwordless `sudo` permission. After upgrading an
existing raspiLightGUI installation, rerun the installer once to deploy the new
rule:

```bash
sudo ./raspi_service_pack/install.sh --service-user pi
sudo -u pi sudo -n /usr/bin/systemctl restart livestageassistant.service
```

The second command is an optional verification: it must complete without asking
for a password. The equivalent interactive wrapper command will then work too:

```bash
livestageassistant restart
```

## Manual development run

For development without installing the systemd unit:

```bash
sudo raspi-config nonint do_i2c 0
sudo apt install i2c-tools python3-venv python3-gpiozero python3-lgpio
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
GPIOZERO_PIN_FACTORY=lgpio python lightGUI.py
```

### Available launch modes

After activating `.venv`, the application can be started in any of these modes:

```bash
python lightGUI.py --backend auto
python lightGUI.py --backend hardware
python lightGUI.py --backend console
```

| Mode | Behaviour |
|------|-----------|
| `auto` | Tries the OLED and GPIO buttons first. If hardware initialization fails in an interactive TTY, it falls back to the console simulator. Without a TTY, it exits with an error. |
| `hardware` | Requires the SSD1306 and initializes the GPIO buttons. Missing hardware produces a short startup error; no console fallback is attempted. |
| `console` | Does not initialize the OLED or GPIO. It simulates the complete interface in an interactive terminal. |

Omitting `--backend` is equivalent to selecting `auto`:

```bash
python lightGUI.py
```

### Console simulation

The dashboard follows a Model/View/Presenter separation. The screen definitions
and presenter do not depend on the OLED or GPIO implementation. It can therefore
be exercised from an interactive terminal without connecting any hardware:

```bash
python lightGUI.py --backend console
```

Keyboard controls:

- Left or Up: previous screen/item
- Right or Down: next screen/item
- Enter: OK
- `q`: quit

The console keeps a fixed 21-character display width. Long titles and content
are shortened with `...`; unlike the OLED backend, the terminal backend does not
attempt to reduce a font size.

### Behaviour under systemd

The installed unit always executes:

```text
lightGUI.py --backend hardware
```

Console fallback is deliberately disabled because a systemd service has no
interactive terminal from which to read arrow keys. The resulting behaviour is:

- with the OLED available, the dashboard runs continuously using GPIO buttons;
- without the OLED, startup ends with a concise diagnostic in the journal;
- `Restart=always` retries a failed startup after five seconds;
- `raspilightgui-service stop` performs a deliberate stop and clears the OLED;
- an unexpected crash is restarted after five seconds;
- during a confirmed system shutdown, `Shutting down...` remains buffered on
  the OLED instead of being replaced by another page.

Inspect startup failures and runtime messages with:

```bash
raspilightgui-service status
raspilightgui-service logs
```

A normally-open button cannot be reliably distinguished from an unconnected
button in software: both appear as an inactive input held high by the configured
pull-up resistor. The OLED, unlike the buttons, can be detected by its I²C
acknowledgement.

## I²C troubleshooting

At startup, the application scans the bus and accepts the two common SSD1306
addresses, `0x3C` and `0x3D`. If startup reports that no SSD1306 was detected,
stop the service and inspect bus 1. `i2cdetect` is an optional diagnostic command
provided by the Raspberry Pi OS package `i2c-tools`:

```bash
raspilightgui-service stop
sudo apt install i2c-tools
ls -l /dev/i2c-1
i2cdetect -y 1
```

The address table should contain `3c` or `3d`. If every position is `--`, check:

- OLED VCC to Pi 3.3 V (physical pin 1 or 17), never 5 V unless the exact module
  explicitly supports it;
- OLED GND to a Pi GND pin;
- OLED SDA to GPIO2, physical pin 3;
- OLED SCL to GPIO3, physical pin 5;
- I²C enabled with `sudo raspi-config nonint do_i2c 0` followed by a reboot.

If `i2cdetect` shows another address, confirm that the display controller really
is an SSD1306. An `Errno 121 Remote I/O error` means that the addressed device did
not acknowledge the I²C transaction and normally indicates address, wiring, or
hardware rather than a Python failure.

## Extending the dashboard

The screen registry is the `SCREENS` tuple in `lightGUI.py`:

```python
InfoScreen("MY INFO", my_content_function)
ActionScreen(
    "MY ACTIONS",
    (
        ActionItem("Do something", my_action_function, confirm=True),
        ActionItem("Back"),
    ),
    default_index=0,
)
```

An information provider returns `list[str]`. An action returns a short status
string. Providers are kept in `system_info.py`, actions in `system_actions.py`,
and may call other Python modules or external programs. Every action screen must
end with a `Back` item whose callback is omitted.
