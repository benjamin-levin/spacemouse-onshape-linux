#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Missing virtual environment at $VENV"
  echo "Run:"
  echo "  $ROOT/setup_bridge.sh"
  exit 1
fi

exec "$VENV/bin/python" -m spacenav_ws.main serve
