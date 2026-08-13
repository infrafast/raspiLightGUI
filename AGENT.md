# Agent and Maintainer Instructions

## Documentation policy

- Keep all documentation in English.
- Update the documentation after every code, configuration, wiring, dependency,
  installation, command-line, monitoring, timing, or user-interface change.
- Do not create documentation files other than `README.md` and `AGENT.md`.
- Use `README.md` only for information useful to an end user: purpose, visible
  behaviour, wiring, installation commands, operation, and troubleshooting.
- Use `AGENT.md` for implementation details, architecture, maintenance rules,
  internal installer behaviour, validation procedures, and extension guidance.
- Keep `README.md` concise and approachable. Do not expose internal module maps,
  dependency-resolution mechanics, systemd template substitutions, caches,
  locks, worker implementation, or similar maintainer details there.
- Apply a strict user-value test before adding README content: keep it only when
  a user needs it to understand visible behaviour, wire the hardware, install or
  operate the application, choose a command, or solve a likely problem.
- Put implementation choices and explanations of how the software achieves its
  behaviour only in `AGENT.md`. This includes library/backend selection,
  environment variables, process and thread design, caching, ownership,
  dependency installation mechanics, and service internals.
- Do not document invisible implementation facts in `README.md` merely because
  they are technically noteworthy. Translate them into a user-facing outcome
  when needed; for example, say that no extra setup is required rather than
  naming the internal driver that makes it possible.
- Keep commands minimal. Do not include redundant default options, environment
  prefixes, permission changes for files already executable in Git, or setup
  steps already performed by the installer.
- When behaviour affects users, update both files at the appropriate level:
  describe the result in `README.md` and its implementation constraints here.
- Never let documentation describe behaviour that has not been implemented and
  verified.

## Project constraints

- Target Raspberry Pi 5 running 64-bit Raspberry Pi OS or Debian with Python
  3.11 or newer.
- Keep one Python process and one `raspilightgui.service` systemd unit.
- Minimise CPU use, memory use, subprocesses, GPIO activity, I2C writes, wakeups,
  and polling. This is an always-on embedded service.
- Preserve physical LED operation in `auto`, `hardware`, and `console` modes.
- `auto` is the default backend. User-facing examples must use
  `python lightGUI.py`, not the redundant `--backend auto` argument.
- Select `lgpio` in code with `os.environ.setdefault` before importing GPIO
  Zero. Users and systemd must not need to set `GPIOZERO_PIN_FACTORY`.
- Never add a console LED animation. Console mode replaces only the OLED and
  buttons; the GPIO LED remains real.
- The LED must continue operating when the OLED is absent. In that case the
  control panel uses a headless backend and must not perform invisible OLED probes.
- The LED monitor checks only wired Ethernet and QLC+. It must not monitor
  Oculizer, Live Stage Assistant, or future systemd services.
- Do not add command-line modes for forcing or testing individual LED channels.
- The installer assumes a fresh system. Do not add migration, detection, or
  shutdown logic for an old `lsa-status-led.service`.

## Service profiles

- Treat the control-panel architecture as generic even though the repository ships
  with a concrete live-production rack profile.
- The included profile is QLC+ lighting control, Oculizer mixing agent, and Live
  Stage Assistant, in that order. QLC+ is its primary service for the green LED.
- Keep profile-specific identifiers and `PRIMARY_SERVICE_KEY` in
  `managed_services.py`. Do not scatter service
  names through presentation, state, action, or installer logic.
- A different deployment should be adaptable by changing the service
  declarations, wrapper paths, and primary LED service, without rewriting the
  monitoring or menu algorithms.
- Declare dependencies by service key in `ServiceDefinition.depends_on`. Before
  a Start action, obtain a fresh shared snapshot and require every dependency to
  have runtime `UP`. On failure, do not call the wrapper; return the OLED-safe
  message `Start <dependency label> first`. The included profile declares that
  Oculizer depends on QLC+.
- In `README.md`, clearly distinguish generic control-panel behaviour from examples
  produced by the included rack profile. Do not present the example services as
  mandatory architectural components.

## Architecture

- `lightGUI.py`: screen registration, presentation, navigation, action flow,
  process lifecycle, signals, and LED-worker orchestration.
- `ui_backends.py`: OLED, terminal, and headless view/input adapters.
- `system_info.py`: OLED information providers and service-state presentation.
- `system_actions.py`: generic privileged service and system action callbacks. Actions
  return short semantic result strings suitable for the OLED.
- `system_monitor.py`: shared, thread-safe, low-cost wired-network probe.
- `managed_services.py`: the single ordered declaration of managed service
  labels, systemd units, and wrapper paths.
- `gpio_devices.py`: all BCM assignments and GPIO Zero button/LED devices.
- `status_led.py`: LED policy and its interruptible background worker.
- `raspi_service_pack/install.sh`: read-only preflight and permanent installer.
- `raspi_service_pack/systemd/raspilightgui.service`: systemd template.
- `raspi_service_pack/raspilightgui-service`: installed administration client.

Keep presentation, input, probes, GPIO ownership, and policy separated. Put a
new reusable non-service probe in `system_monitor.py`; do not duplicate probes
in OLED and LED code. Add a managed service only in `MANAGED_SERVICES`, not with
per-service callbacks or rendering branches.

## Behavioural invariants

### OLED and input

- Document OLED VCC on 3.3 V physical pin 1. OLED ground and the common side of
  all buttons use physical ground pin 30 or 34; each button's other terminal
  connects to its assigned GPIO.
- `MONITOR` and the inactive `SYSTEM` preview refresh immediately on entry and
  every 10 seconds while visible. Active action menus do not refresh.
- Identical OLED frames are not sent again over I2C.
- The screen sleeps after 300 seconds of inactivity by default. Monitoring and
  LED operation continue; the first button event wakes the display only.
- For technical diagnosis, change the OLED inactivity delay with
  `python lightGUI.py --backend hardware --sleep-timeout 600`, or disable sleep
  with `python lightGUI.py --backend hardware --sleep-timeout 0`. Keep these
  advanced commands out of the user README unless they become necessary for
  normal operation.
- Button GPIO uses edge callbacks and internal pull-ups, not a polling loop.
- Long OLED lines may use fitted proportional fonts, but line baselines and
  vertical spacing must remain fixed. Console lines are truncated with `...`.
- Content begins two pixels below the title layout while the title position is
  unchanged.
- `SYSTEM` replaces the former separate service-state screen. Its inactive
  five-line preview contains the three declared service states, a combined
  `...` continuation hint, and `OK = enter menu`, without a selection cursor.
  The hint must remain generic and must not duplicate action labels. Up/Down
  changes screens in this state.
- OK explicitly activates an action screen's item list. Select the first item
  whenever a root menu or submenu opens or is rebuilt. Action mode remains
  active until the user selects and confirms `Back`. Confirmation dialogs still
  default to `Cancel`.

### Monitoring

- Temperature: `OK` below 70 C, `HIGH` from 70 C to below 80 C, and `CRIT` at
  or above 80 C.
- Input voltage: `OK` at or above 4.80 V, `LOW` above 4.65 V and below 4.80 V,
  and `CRIT` at or below 4.65 V or when current undervoltage is reported.
- QLC+, Oculizer, and Live Stage Assistant share the same systemd state
  algorithm and appear in that order:
  running and enabled is `AUTO`; running and disabled is `MANUAL`; transitional,
  inactive, failed, and unreadable states remain distinct.
- Store runtime state and boot-enabled state separately in `ServiceStatus`.
  Query `is-enabled` even when a service is not running. Append `AUTO` to a
  non-running display state when boot startup is enabled.
- The inactive `SYSTEM` preview consumes the shared managed-service snapshot,
  cached for at most 10 seconds. Force a refresh on entry and every 10 seconds,
  and invalidate it after an executed action.
- Generate service lines, alerts, and actions by iterating only over
  `MANAGED_SERVICES`; do not add per-service monitoring or action functions.
- Keep the root `SYSTEM` menu to one item per declared service, followed by
  Reboot, Shutdown, and Back. A service item opens exactly one contextual
  submenu; do not add service screens to the main carousel.
- In a service submenu, `UP` and `STARTING` expose Stop then Restart; `DOWN`,
  `FAILED`, and `STOPPING` expose Start; `UNKNOWN` exposes no runtime action.
  Enabled services expose `Manual` (internally the wrapper's `noauto` command),
  disabled services expose Auto, and an unknown enablement state (including
  masked/static units) exposes no service action.
- Service Stop and Manual actions require confirmation. Service Start, Restart,
  and Auto execute immediately. Reboot and Shutdown always require confirmation.
- Freeze each generated menu while the user selects an item. After an executed
  action, invalidate the shared snapshot, rebuild the current submenu, and
  select its first item. Back returns one menu level or exits root action mode.
- After a service action, poll only that service at one-second intervals for at
  most 10 seconds while it is `STARTING` or `STOPPING`, then invalidate the
  shared snapshot and rebuild the submenu. Regenerate a parent menu when Back
  returns to it; never restore stale service-state labels.
- Show `R:n` only when the restart count is greater than one. A failed service
  or at least three restarts adds `/!\` to the screen title.
- Network and managed-service snapshots may be reused for up to 10 seconds.
  LED phases keep their visual cadence while consuming these shared snapshots.

### LED

- GPIO27 / physical pin 13 is blue; GPIO22 / physical pin 15 is green.
- Red is hardware-powered from 3.3 V / physical pin 17 and is not software
  controlled. The LED is common-cathode on physical pin 14.
- Alternate an approximately 1.5-second Ethernet phase with an approximately
  1.5-second QLC+ phase.
- Blink states use 250 ms on and 250 ms off.
- Ethernet: link plus IPv4 is solid blue; link without IPv4 blinks blue; no link
  leaves blue off.
- QLC+: `AUTO` or `MANUAL` is solid green; every other state blinks green.
- Waits must remain interruptible. Always turn software channels off and close
  GPIO devices on process exit or worker failure.
- A fatal LED worker error must stop the main loop so systemd can restart the
  complete service.

## Installer internals

`install.sh --check` must remain read-only. It validates the ARM64 Debian-family
host, service account, Python version, essential commands, repository files,
available Python modules, existing virtual environment, and I2C presence.
Installable missing dependencies are reported rather than treated as host
incompatibilities.

The permanent installer must:

- require root and remain non-interactive;
- install Python, venv, pip, GPIO Zero, `lgpio`, I2C tools, sudo, and
  the required font through APT;
- enable I2C through `raspi-config` when it is available;
- create `.venv` with `--system-site-packages` and install `requirements.txt`;
- make the virtual environment usable by the selected service account;
- add that account to the `gpio` and `i2c` groups when present;
- verify runtime imports as the service account;
- generate the administration client, systemd unit, and narrowly scoped
  passwordless sudo rules;
- derive managed-service sudo rules from `MANAGED_SERVICES`, never from a second
  hand-maintained list;
- validate systemd and sudoers output before reloading systemd;
- not enable or start the service automatically.

The systemd unit must invoke `.venv/bin/python` by absolute path, use the
repository as its working directory, rely on the application's default `lgpio`
selection, and use `Restart=always`. It must work without venv activation, an
environment prefix, or an interactive shell.

## Validation after changes

Run checks proportional to the change. At minimum:

```bash
python - <<'PY'
from pathlib import Path
for path in Path('.').glob('*.py'):
    compile(path.read_text(), str(path), 'exec')
PY
bash -n raspi_service_pack/install.sh raspi_service_pack/raspilightgui-service
git diff --check
```

Do not leave generated `__pycache__` or `.pyc` changes in the worktree. Hardware
changes also require Raspberry Pi validation of GPIO ownership, button events,
OLED layout, I2C fallback, LED colours/cadence, signals, and systemd restart.
