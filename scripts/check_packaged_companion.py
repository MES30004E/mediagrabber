"""Hosted frozen-host qualification only; not full media-app/release qualification."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import tempfile

ORIGIN = "chrome-extension://cplbbpknliffempndiphmhaolpgipdgn/"


def verify_protocol(command: list[str]) -> int:
    packet = b'{"type":"ping"}'
    duplicate = b'{"type":"ping","type":"hello"}'
    cases = [(ORIGIN, struct.pack("=I", len(packet)) + packet, "ready"),
             ("chrome-extension://foreign/", struct.pack("=I", len(packet)) + packet, "rejected"),
             (ORIGIN, struct.pack("=I", 131073), "rejected"),
             (ORIGIN, b"\x01\x00", "rejected"),
             (ORIGIN, struct.pack("=I", len(duplicate)) + duplicate, "rejected")]
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} and not key.startswith("_PYI_")}
    environment.update(PATH="/usr/bin:/bin", PYINSTALLER_RESET_ENVIRONMENT="1")
    with tempfile.TemporaryDirectory(prefix="morgan-host-smoke-") as directory:
        for origin, request, expected in cases:
            process = subprocess.run([*command, origin], input=request, capture_output=True,
                                     timeout=30, cwd=directory, env=environment)
            if process.returncode or process.stderr or len(process.stdout) < 4:
                raise RuntimeError("Native host did not return a clean framed response")
            length, = struct.unpack("=I", process.stdout[:4])
            if length > 131072 or len(process.stdout) != length + 4:
                raise RuntimeError("Native host output contains a malformed or extra frame")
            response = json.loads(process.stdout[4:])
            if response.get("status") != expected or (expected == "ready" and response.get("protocol") != 1):
                raise RuntimeError("Native host protocol result did not match the request")
    return len(cases)


def verify_bundle(app: Path) -> dict:
    app = app.resolve(strict=True)
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "com.morgan.media-downloader" or info.get("CFBundleExecutable") != "Morgan Media Downloader":
        raise RuntimeError("Unexpected app identity or GUI entry point")
    helper = app / "Contents/MacOS/MorganNativeHost"
    if helper.is_symlink() or not helper.is_file() or not os.access(helper, os.X_OK):
        raise RuntimeError("Packaged native host is missing or not an executable")
    architecture = subprocess.run(["/usr/bin/file", "-b", str(helper)], capture_output=True, text=True, check=True).stdout
    if "Mach-O" not in architecture or "arm64" not in architecture:
        raise RuntimeError("Native host is not an Apple Silicon Mach-O executable")
    extension = app / "Contents/Resources/companion/chrome"
    for name in ("manifest.json", "core.mjs", "popup.js", "popup.html", "popup.css"):
        resource = extension / name
        if not resource.is_file() or not resource.resolve().is_relative_to(app):
            raise RuntimeError("Companion asset is missing or escapes the bundle")
    manifest = json.loads((extension / "manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"], validate=True)).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
    if ORIGIN != f"chrome-extension://{extension_id}/":
        raise RuntimeError("Shipped extension identity does not match the native host")
    count = verify_protocol([str(helper)])
    return {"app_version": info.get("CFBundleShortVersionString"), "extension_version": manifest["version"],
            "native_protocol_cases": count, "scope": "Companion only; not full app/media/release qualification"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify_bundle(arguments.app), sort_keys=True))
