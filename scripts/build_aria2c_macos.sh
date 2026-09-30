#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
VERSION="1.37.0"
SOURCE_URL="https://github.com/aria2/aria2/releases/download/release-${VERSION}/aria2-${VERSION}.tar.xz"
SOURCE_SHA256="60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b"
BUILD_DIR="$(mktemp -d /private/tmp/morgan-aria2-build.XXXXXX)"
ARCHIVE="$BUILD_DIR/aria2-${VERSION}.tar.xz"
trap 'rm -rf "$BUILD_DIR"' EXIT

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  print -u2 "This script builds the bundled aria2c only on arm64 macOS."
  exit 1
fi

curl --fail --location --silent --show-error --output "$ARCHIVE" "$SOURCE_URL"
ACTUAL_SHA256="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
if [[ "$ACTUAL_SHA256" != "$SOURCE_SHA256" ]]; then
  print -u2 "aria2 source checksum mismatch: $ACTUAL_SHA256"
  exit 1
fi

tar -xJf "$ARCHIVE" -C "$BUILD_DIR"
cd "$BUILD_DIR/aria2-${VERSION}"
./configure \
  --disable-shared --enable-static \
  --without-gnutls --without-openssl --with-appletls \
  --without-libxml2 --without-libexpat --without-sqlite3 \
  --without-libcares --without-libssh2 --without-libgcrypt \
  --without-libnettle --without-libgmp \
  CFLAGS="-O2 -arch arm64 -mmacosx-version-min=12.0" \
  CXXFLAGS="-O2 -arch arm64 -mmacosx-version-min=12.0" \
  LDFLAGS="-arch arm64 -mmacosx-version-min=12.0"
make -j8

mkdir -p "$ROOT_DIR/resources/bin"
install -m 755 src/aria2c "$ROOT_DIR/resources/bin/aria2c"
file "$ROOT_DIR/resources/bin/aria2c"
"$ROOT_DIR/resources/bin/aria2c" --version | sed -n '1p'
shasum -a 256 "$ROOT_DIR/resources/bin/aria2c"
