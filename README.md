# Raspberry Pi OLED Dashboard and RGB Status LED

raspiLightGUI is a lightweight Raspberry Pi 5 dashboard and controller. It
combines:

- a 128x64 SSD1306 OLED display and three navigation buttons;
- an RGB status LED for Ethernet and QLC+;
- system health and service monitoring;
- confirmed restart, stop, and shutdown actions;
- one continuously supervised systemd service.

## What the display shows

### MONITOR

The page shows CPU temperature, input voltage, uptime, CPU/RAM/disk usage, and
the active wired IPv4 address. It updates when opened and every 10 seconds while
visible.

Temperature states:

| State | Temperature |
|---|---|
| `OK` | Below 70 C |
| `HIGH` | 70 C to below 80 C |
| `CRIT` | 80 C or above |

Power states:

| State | Condition |
|---|---|
| `OK` | 4.80 V or above, without undervoltage |
| `LOW` | Above 4.65 V and below 4.80 V |
| `CRIT` | 4.65 V or below, or undervoltage detected |
| `N/A` | Voltage information unavailable |

### SERVICE STATE

The page shows `qlcplus.service`, `oculizer.service`, and
`livestageassistant.service`, in that order.

| State | Meaning |
|---|---|
| `AUTO` | Running and enabled at boot |
| `MANUAL` | Running but not enabled at boot |
| `STARTING` | Starting or reloading |
| `STOPPING` | Stopping |
| `DOWN` | Stopped normally |
| `FAILED` | Service failure |
| `UNKNOWN` | State unavailable |

An automatic service that is not currently running adds `AUTO` to its runtime
state, for example `DOWN AUTO` or `FAILED AUTO`.

`R:n` appears after more than one service restart. `/!\` in the title indicates
a failed service, repeated restarts, critical temperature, or critical power.

### SYSTEM

The main action page contains one entry per service, followed by `Reboot`,
`Shutdown`, and `Back`. Selecting QLC+, Oculizer, or Assistant opens a
contextual submenu that can:

- stop or restart the service when it is running or starting;
- start it when it is stopped, failed, or stopping;
- select `Auto` to enable startup at boot, or `Manual` to disable it.

`Reboot` and `Shutdown` remain in the main `SYSTEM` menu and require
confirmation. `Back` returns from a service submenu to `SYSTEM`, then from
`SYSTEM` to screen navigation.

Actions require confirmation and display a short success or failure message.
`Back` and confirmation cancellation are selected by default.
If a service state or startup mode is unavailable, potentially unsafe actions
are omitted. Menus use the same states shown on `SERVICE STATE`, but remain
stable while you are selecting an item.

## RGB status LED

Red indicates board power. Blue and green alternate to provide a visible
heartbeat:

| Check | Result | LED behaviour |
|---|---|---|
| Ethernet | Link and IPv4 address | Solid blue, appearing magenta with red |
| Ethernet | Link without IPv4 | Blinking blue/magenta |
| Ethernet | No link | Blue off; red only |
| QLC+ | Service running | Solid green, appearing yellow with red |
| QLC+ | Service not running | Blinking green/yellow |

Each Ethernet and QLC+ phase lasts about 1.5 seconds. Blink states alternate
every 250 ms. The LED continues working when the OLED is disconnected or asleep.

## Wiring

| Function | BCM GPIO | Physical pin | Connection |
|---|---:|---:|---|
| OLED power | 3.3 V | 1 | OLED VCC |
| RGB red anode | 3.3 V | 17 | Through 470 ohm resistor |
| OLED and button grounds | GND | 30 or 34 | OLED GND and common side of all buttons |
| RGB common cathode | GND | 14 | LED common cathode |
| OLED SDA | GPIO2 | 3 | SDA |
| OLED SCL | GPIO3 | 5 | SCL |
| Button Down / Back | GPIO5 | 29 | Other terminal to common button GND |
| Button Select / OK | GPIO6 | 31 | Other terminal to common button GND |
| Button Up / Next | GPIO13 | 33 | Other terminal to common button GND |
| RGB blue anode | GPIO27 | 13 | Through 330 ohm resistor |
| RGB green anode | GPIO22 | 15 | Through 330 ohm resistor |

Buttons use internal pull-up resistors. Never connect an LED channel without its
series resistor.

## Navigation

There are two interactive interfaces:

- hardware mode uses the OLED and the three physical buttons;
- simulated mode displays the same interface in a terminal and uses the
  keyboard. It is intended for diagnosis when no OLED is connected.

Navigation is identical in both modes:

| Action | Hardware | Simulated terminal |
|---|---|---|
| Previous page or item | Up / Next | Left or Up |
| Next page or item | Down / Back | Right or Down |
| Select / confirm | OK | Enter |
| Quit local simulation | — | `q` |

On information pages:

- Down / Back: next page;
- Up / Next: previous page;

The inactive `SYSTEM` page behaves like every other page: Up and Down continue
scrolling through the screens. It shows the action-menu preview without a
selection cursor, with `OK = enter menu` in place of `Back`. Press OK only when
you want to activate its selectable action list.

In the action list:

- Down or Up: change selection;
- OK on a service: open its contextual submenu;
- OK on an action: open its confirmation;
- `Back` inside a service submenu: return to the main `SYSTEM` menu;
- select `Back` and press OK to leave the menu and return to screen navigation.

The action list remains active until `Back` is confirmed. `Back` is selected by
default whenever the menu is entered.

The OLED sleeps after five minutes without input. The first button press wakes
it without navigating or executing an action.

## Installation

Install and configure the managed applications before raspiLightGUI. In
particular, QLC+ must be provided as `qlcplus.service` with the
`qlcplus-service` command from
[raspi5rackSetup](https://github.com/infrafast/raspi5rackSetup).

### 1. Preflight

From the repository directory, run the read-only check without `sudo`:

```bash
./raspi_service_pack/install.sh --check --service-user pi
```

Missing software or an unavailable OLED may be reported here. The permanent
installer installs supported dependencies and attempts to enable I2C.

### 2. Permanent installation

```bash
sudo ./raspi_service_pack/install.sh --service-user pi
```

The installer prepares Python and the required libraries, installs the service
and administration command, and leaves the service disabled until you choose to
start it.

Enable automatic startup and start now:

```bash
raspilightgui-service auto
```

Available administration commands:

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

`noauto` disables startup at boot without stopping the currently running
service.

## Local diagnosis

Install the project first, then stop the service before using the same GPIO from
a terminal:

```bash
raspilightgui-service stop
source .venv/bin/activate
```

Available modes:

```bash
python lightGUI.py
python lightGUI.py --backend hardware
python lightGUI.py --backend console
```

The first command uses automatic mode: it selects the OLED when available, the
terminal interface during an interactive local run without an OLED, or the LED-
only headless mode without an interactive terminal. Use the other commands only
to force hardware or console mode for diagnosis.

The physical RGB LED remains active in every mode. See [Navigation](#navigation)
for the terminal controls.

## OLED troubleshooting

If no OLED is detected, the installed service continues running the RGB LED.
Check the I2C bus with:

```bash
raspilightgui-service stop
i2cdetect -y 1
```

An SSD1306 normally appears at address `3c` or `3d`. If neither appears, check
3.3 V, ground, SDA on physical pin 3, and SCL on physical pin 5.

The LED behaviour was integrated from the companion
[raspiLed project](https://github.com/infrafast/raspiLed).
