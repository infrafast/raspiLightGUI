#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SERVICE_CLIENT=/usr/local/bin/raspilightgui-service
APP_UNIT=raspilightgui.service
service_user=${SUDO_USER:-pi}
check_only=false

usage() {
  cat <<'EOF'
Usage: sudo ./raspi_service_pack/install.sh [OPTIONS]

Install raspiLightGUI as a Raspberry Pi systemd service.
Options:
  --service-user USER  Runtime account (default: invoking sudo user or pi)
  --check              Validate the host and repository without changes
  --non-interactive    Accepted for automation; installation is non-interactive
  -h, --help           Show this help
EOF
}

fail() {
  echo "install.sh: $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --service-user) (($# >= 2)) || fail "--service-user requires a value"; service_user=$2; shift 2 ;;
    --check) check_only=true; shift ;;
    --non-interactive) shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

[[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || fail "Linux ARM64 is required"
[[ -r /etc/os-release ]] || fail "cannot identify the operating system"
grep -qE '^(ID=debian|ID=raspbian)$' /etc/os-release || fail "Debian or Raspberry Pi OS is required"
id "$service_user" >/dev/null 2>&1 || fail "service user '$service_user' does not exist"
service_home=$(getent passwd "$service_user" | cut -d: -f6)
[[ -n $service_home && -d $service_home ]] || fail "service user '$service_user' has no usable home"
service_group=$(id -gn "$service_user")
[[ -r $REPO_ROOT/lightGUI.py ]] || fail "missing lightGUI.py"
[[ -r $REPO_ROOT/requirements.txt ]] || fail "missing requirements.txt"

echo "raspiLightGUI Raspberry Pi installation"
echo "  repository:   $REPO_ROOT"
echo "  service user: $service_user"

if $check_only; then
  command -v python3 >/dev/null || fail "python3 is missing"
  python3 -c 'import sys; assert sys.version_info >= (3, 11), sys.version'
  [[ -e /dev/i2c-1 ]] || echo "Warning: /dev/i2c-1 is absent; enable I2C before starting."
  echo "Preflight passed; no changes made."
  exit 0
fi

[[ $EUID -eq 0 ]] || fail "installation requires sudo (use --check for preflight)"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y i2c-tools python3 python3-venv python3-gpiozero python3-lgpio
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_i2c 0
fi

python3 -m venv "$REPO_ROOT/.venv" --system-site-packages
"$REPO_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$REPO_ROOT/.venv/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"

for group in gpio i2c; do
  getent group "$group" >/dev/null && usermod -a -G "$group" "$service_user"
done

python3 - "$SCRIPT_DIR/raspilightgui-service" "$SERVICE_CLIENT" "$REPO_ROOT" <<'PY'
import os
import pathlib
import sys

source, destination, repository = sys.argv[1:]
text = pathlib.Path(source).read_text(encoding="utf-8")
pathlib.Path(destination).write_text(
    text.replace("@REPO_ROOT@", repository), encoding="utf-8"
)
os.chmod(destination, 0o755)
PY
python3 - "$SCRIPT_DIR/systemd/raspilightgui.service" "/etc/systemd/system/$APP_UNIT" "$service_user" "$service_group" "$service_home" "$REPO_ROOT" <<'PY'
import pathlib
import sys

source, destination, user, group, home, repository = sys.argv[1:]
text = pathlib.Path(source).read_text(encoding="utf-8")
text = (
    text.replace("@SERVICE_USER@", user)
    .replace("@SERVICE_GROUP@", group)
    .replace("@SERVICE_HOME@", home)
    .replace("@REPO_ROOT@", repository)
)
pathlib.Path(destination).write_text(text, encoding="utf-8")
PY
chmod 0644 "/etc/systemd/system/$APP_UNIT"
systemd-analyze verify "/etc/systemd/system/$APP_UNIT"

python3 - "/etc/sudoers.d/raspilightgui-service" "$service_user" <<'PY'
import pathlib
import sys

path, user = sys.argv[1:]
commands = (
    "/usr/bin/systemctl start raspilightgui.service",
    "/usr/bin/systemctl stop raspilightgui.service",
    "/usr/bin/systemctl restart raspilightgui.service",
    "/usr/bin/systemctl enable --now raspilightgui.service",
    "/usr/bin/systemctl disable raspilightgui.service",
    "/usr/bin/systemctl poweroff",
)
text = "Cmnd_Alias RASPILIGHTGUI_SERVICE = " + ", ".join(commands) + "\n"
text += f"{user} ALL=(root) NOPASSWD: RASPILIGHTGUI_SERVICE\n"
pathlib.Path(path).write_text(text, encoding="utf-8")
PY
chmod 0440 /etc/sudoers.d/raspilightgui-service
visudo -cf /etc/sudoers.d/raspilightgui-service

systemctl daemon-reload

echo "Installation complete."
echo "Manual start: raspilightgui-service start"
echo "Boot auto-start: raspilightgui-service auto"
echo "Status: raspilightgui-service status"
echo "Logs: raspilightgui-service logs"
