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
- For DisplayCTL, document a milestone as validated only after it has been
  exercised on the target Raspberry Pi. Keep planned or untested initramfs,
  static-link, shutdown, reboot, panic, and update integrations explicitly marked
  as pending until confirmed on hardware.

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
  Start and Restart actions, obtain a fresh shared snapshot and require every
  dependency to have runtime `UP`. On failure, do not call the wrapper; return
  the OLED-safe message `Start <dependency label> first`. This pre-check ensures
  a blocked Restart cannot stop an already running service. The included profile
  declares that Oculizer depends on QLC+.
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
- `displayctl/displayctl.cpp`: minimal native SSD1306 helper used outside the
  normal raspiLightGUI lifetime.
- `displayctl/Makefile`: normal and intended static builds for DisplayCTL.

Keep presentation, input, probes, GPIO ownership, and policy separated. Put a
new reusable non-service probe in `system_monitor.py`; do not duplicate probes
in OLED and LED code. Add a managed service only in `MANAGED_SERVICES`, not with
per-service callbacks or rendering branches.

## DisplayCTL

### Purpose and scope

DisplayCTL is intentionally separate from the resident Python application. Its
only job is to select one embedded 128x64 monochrome bitmap, initialise the
SSD1306 over I2C, write that complete framebuffer, and exit. It must never gain
text rendering, fonts, layout logic, menus, polling, GPIO handling, service
monitoring, or a resident process.

The command interface is currently:

```text
displayctl boot
displayctl shutdown
displayctl reboot
displayctl panic
displayctl updating
```

The source opens `/dev/i2c-1`, selects SSD1306 address `0x3C`, writes controller
initialisation commands, configures the full 128x64 RAM window, transfers the
1024-byte framebuffer, closes the descriptor, and exits. It intentionally uses
Linux system calls and the kernel I2C userspace ABI rather than a display
library.

All production icons must be compiled into the executable as fixed 1024-byte
bitmaps. Do not add external image files, runtime conversion, fonts, asset
folders, or configuration files required by the executable.

The current five icon commands have been validated on the target OLED. Artwork
and pixel positioning may still be refined later without reopening the milestone
as long as command semantics, embedded-only assets, and full-screen rendering
behaviour remain unchanged.

### OLED ownership and hand-off

DisplayCTL and raspiLightGUI must not write to the SSD1306 concurrently.
The intended lifecycle is:

```text
initramfs -> displayctl boot -> DisplayCTL exits
systemd   -> raspiLightGUI takes ownership
shutdown  -> raspiLightGUI stops -> displayctl shutdown/reboot -> DisplayCTL exits
```

Do not add a daemon, lock manager, or background helper merely to coordinate the
handoff. Ordering should be enforced by initramfs flow and systemd dependencies.

### Build

The normal native build is defined by `displayctl/Makefile`:

```bash
cd displayctl
make
```

The Makefile also provides the optimized static build intended for initramfs:

```bash
make static
```

On the target Raspberry Pi this optimized build produced a 597816-byte (about
584 KiB) ARM64 executable. `file` reported it as statically linked and stripped,
`ldd` reported `not a dynamic executable`, and `readelf -l` showed no dynamic
interpreter. The executable itself was run successfully after the optimization.
The OLED was not physically observable during that final optimized-build test,
so the rendering result is assumed from the previously validated icon build and
must be visually rechecked when physical access is available.

If that later visual check reveals a rendering regression, compare or revert the
optimization introduced by commits `2c98cfb6505560e78079cb07e1cb506abdac3b1f`
(`displayctl.cpp`) and `c7819312926ef00e438792d4033a19c5308af34f`
(`displayctl/Makefile`). The pre-optimization implementation had already been
visually validated on the target OLED.

### Initramfs integration constraints

An initramfs integration has been assembled and has booted successfully on the
target Pi without preventing the normal system or raspiLightGUI from starting.
The production candidate consists only of the initramfs hook that embeds the
static binary and required I2C modules, plus the fail-open `init-premount` script
that attempts `displayctl boot`. Temporary remote-diagnostic mechanisms using
`/dev/kmsg`, initramfs `/run`, `local-bottom`, or `init-bottom` status hand-off
were removed after proving unreliable for post-boot verification.

For direct initramfs debugging on the target Pi, append `break=mount` to the
single line in `/boot/firmware/cmdline.txt` and reboot. This opens an initramfs
shell after the `init-premount` phase, allowing the installed script and I2C state
to be inspected directly. Useful checks include:

```sh
ls -l /dev/i2c-1
/scripts/init-premount/raspilightgui-displayctl ""
/usr/local/bin/displayctl boot
```

The explicit empty argument is useful when reproducing older script revisions
that used `set -u` together with an unsafe `$1` prereq check. Current scripts
must use `${1:-}` so normal argument-free initramfs execution cannot abort before
I2C setup. After debugging, remove `break=mount` from `cmdline.txt`; the file must
remain a single line, otherwise subsequent boots will continue stopping in the
initramfs shell.

Before considering the integration fully validated, confirm physically that the
boot icon is visible before raspiLightGUI takes over. The integration must remain
fail-open: failure to load I2C, create `/dev/i2c-1`, find DisplayCTL, or write the
OLED must never prevent the normal boot sequence.

### Validation milestones

Current hardware validation state:

1. **Native compile and direct OLED write: VALIDATED.** `make` succeeds on the
   Raspberry Pi, the executable runs, initialises the connected SSD1306, and a
   full framebuffer is written successfully.
2. **Embedded production icons: VALIDATED.** `boot`, `shutdown`, `reboot`,
   `panic`, and `updating` have all been displayed successfully on the target
   OLED. Exact artwork positioning may still be refined later.
3. **Static binary suitable for initramfs: VALIDATED WITH VISUAL RECHECK DUE.**
   The optimized `make static` build is 597816 bytes (about 584 KiB), statically
   linked, stripped, has no dynamic interpreter, and executes successfully on the
   target Raspberry Pi. Physical OLED output was not visible during this final
   optimized-build test; retain the pre-optimization implementation as the known
   visually validated fallback until the optimized binary is visually checked.
4. **Shutdown/reboot systemd hand-off: VALIDATED WITH VISUAL RECHECK DUE.** The
   reboot hook completed successfully in the previous boot journal. The poweroff
   hook was started without error and the machine completed a normal poweroff;
   its final completion record was not persisted because logging was already
   shutting down. Physical icon output remains to be checked on-site.
5. **Initramfs boot integration: ON HOLD — PHYSICAL VALIDATION PENDING.** The
   initramfs contains DisplayCTL and the required DesignWare/I2C modules, and the
   modified image has completed multiple normal boots with raspiLightGUI returning
   to its hardware backend. Remote attempts to prove the early OLED write through
   transient logging/status hand-off were inconclusive and have been removed.
   Assume the fail-open integration is the production candidate until an on-site
   visual boot test confirms or rejects it.

Update this list immediately when a milestone is confirmed on the Raspberry Pi,
and update the user-visible behaviour in `README.md` at the same time.

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