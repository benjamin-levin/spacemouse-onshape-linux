#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
VENV="$ROOT/.venv"
SERVICE_NAME="spacemouse-onshape-bridge.service"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_TARGET="$USER_SYSTEMD_DIR/$SERVICE_NAME"
SERVICE_TEMPLATE="$ROOT/$SERVICE_NAME.template"
USER_SCRIPT="$REPO_ROOT/onshape-platform-patch.user.js"

echo "Setting up Onshape SpaceMouse bridge in: $ROOT"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi

echo "Installing Python dependencies..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$ROOT/requirements.txt"

echo "Ensuring launcher is executable..."
chmod +x "$ROOT/run_bridge.sh"

mkdir -p "$USER_SYSTEMD_DIR"
sed "s|@ROOT@|$ROOT|g" "$SERVICE_TEMPLATE" > "$SERVICE_TARGET"

echo "Reloading user systemd..."
systemctl --user daemon-reload

echo "Enabling and starting $SERVICE_NAME ..."
systemctl --user enable --now "$SERVICE_NAME"

cat <<EOF

Setup complete.

Bridge status:
  systemctl --user status $SERVICE_NAME --no-pager

Bridge logs:
  journalctl --user -u $SERVICE_NAME -f

Tampermonkey / Violentmonkey setup:
  1. Install Tampermonkey or Violentmonkey in your browser.
  2. Create a new userscript.
  3. Paste the contents of:
     $USER_SCRIPT
  4. Save the userscript and make sure it is enabled.
  5. Disable the old unpacked extension patch if it is still enabled.
  6. Open https://127.51.68.120:8181 once in that browser and accept the certificate exception.
  7. Refresh your Onshape document page.

Firefox note:
  The certificate exception must be accepted in Firefox itself.

Startup behavior:
  This user service starts automatically when you log into your desktop session.
  If you need it to run without an active login session, you would also need linger enabled.
EOF
