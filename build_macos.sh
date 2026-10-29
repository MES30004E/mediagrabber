#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h}"
cd "$ROOT_DIR"
export UV_CACHE_DIR="$ROOT_DIR/.tools/uv-cache"
# Keep the base interpreter durable and off exFAT volumes, which cannot host
# uv's interpreter symlinks. A project venv can still use --copies below.
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}"
export UV_LINK_MODE="copy"
export PYINSTALLER_CONFIG_DIR="/private/tmp/morgan-media-downloader-pyinstaller-$UID"
export PIP_CACHE_DIR="$ROOT_DIR/.tools/pip-cache"
BUILD_WORK_DIR="$(mktemp -d /private/tmp/morgan-media-downloader-work.XXXXXX)"
BUILD_DIST_DIR="$(mktemp -d /private/tmp/morgan-media-downloader-dist.XXXXXX)"
FINAL_APP="$ROOT_DIR/dist/Morgan Media Downloader.app"
trap 'rm -rf "$BUILD_WORK_DIR" "$BUILD_DIST_DIR"' EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
  print -u2 "This build script must run on macOS."
  exit 1
fi

UV_BIN="${UV_BIN:-$(command -v uv || true)}"
if [[ -z "$UV_BIN" ]]; then
  mkdir -p "$ROOT_DIR/.tools"
  print "Downloading uv into the project…"
  curl --fail --location https://astral.sh/uv/install.sh --output "$ROOT_DIR/.tools/install-uv.sh"
  UV_UNMANAGED_INSTALL="$ROOT_DIR/.tools" sh "$ROOT_DIR/.tools/install-uv.sh"
  UV_BIN="$ROOT_DIR/.tools/uv"
fi

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]] || ! "$ROOT_DIR/.venv/bin/python" -c 'import encodings' >/dev/null 2>&1; then
  if [[ -d "$ROOT_DIR/.venv" ]]; then
    rm -rf "$ROOT_DIR/.venv"
  fi
  "$UV_BIN" python install 3.12
  BUILD_PYTHON="$($UV_BIN python find 3.12)"
  "$BUILD_PYTHON" -m venv --copies "$ROOT_DIR/.venv"
fi

# Refuse unsupported destinations before dependency installation or compilation.
# This does not choose a different destination or touch the existing app.
mkdir -p "$ROOT_DIR/dist"
PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/.venv/bin/python" -m morgan_media_downloader.app_installation --check-destination "$FINAL_APP"

# AppleDouble sidecars on non-APFS external volumes can confuse uv's wheel copier.
# pip ignores them, while still installing exclusively into the project venv.
find "$ROOT_DIR/.venv" -name '._*' -delete
"$ROOT_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
"$ROOT_DIR/scripts/download_media_tools.sh"
"$ROOT_DIR/scripts/make_icon.sh"
"$ROOT_DIR/.venv/bin/python" -m pytest
"$ROOT_DIR/.venv/bin/pyinstaller" --noconfirm --workpath "$BUILD_WORK_DIR" --distpath "$BUILD_DIST_DIR" "$ROOT_DIR/MorganMediaDownloader.spec"

codesign --force --deep --sign - "$BUILD_DIST_DIR/Morgan Media Downloader.app"
codesign --verify --deep --strict "$BUILD_DIST_DIR/Morgan Media Downloader.app"
PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/.venv/bin/python" -m morgan_media_downloader.app_installation "$BUILD_DIST_DIR/Morgan Media Downloader.app" "$FINAL_APP"

print "Built: $ROOT_DIR/dist/Morgan Media Downloader.app"
print "Launch with: open '$ROOT_DIR/dist/Morgan Media Downloader.app'"
