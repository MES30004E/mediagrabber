#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
SOURCE="$ROOT_DIR/resources/app-icon.png"
OUTPUT="$ROOT_DIR/resources/AppIcon.icns"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi
PYTHONPYCACHEPREFIX=/private/tmp/morgan-icon-cache "$PYTHON_BIN" "$ROOT_DIR/scripts/make_icon.py" "$SOURCE" "$OUTPUT"
