#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
BIN_DIR="$ROOT_DIR/resources/bin"
ARCH="$(uname -m)"
RELEASE="b6.1.1"

case "$ARCH" in
  arm64) ASSET_ARCH="arm64" ;;
  x86_64) ASSET_ARCH="x64" ;;
  *) print -u2 "Unsupported macOS architecture: $ARCH"; exit 1 ;;
esac

mkdir -p "$BIN_DIR"
for TOOL in ffmpeg ffprobe; do
  if [[ ! -x "$BIN_DIR/$TOOL" ]]; then
    URL="https://github.com/eugeneware/ffmpeg-static/releases/download/$RELEASE/$TOOL-darwin-$ASSET_ARCH.gz"
    print "Downloading $TOOL for macOS $ARCH…"
    curl --fail --location --retry 3 "$URL" --output "$BIN_DIR/$TOOL.gz"
    gzip -df "$BIN_DIR/$TOOL.gz"
    chmod 755 "$BIN_DIR/$TOOL"
  fi
  "$BIN_DIR/$TOOL" -version | head -n 1
done
