"""User-level installation only; never install/enable Chrome extensions silently."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import sys

from .bridge import HOST, ORIGIN
from ..paths import bundle_root

MARKER = "Morgan Media Downloader development companion v1"
BUNDLE_ID = "com.morgan.media-downloader.dev"


def extension_directory():
    return bundle_root() / "companion" / "chrome"


def packaged_host():
    if not getattr(sys, "frozen", False): return None
    host = Path(sys.executable).resolve().with_name("MorganNativeHost")
    _safe_path(host)
    extension = extension_directory()
    if (not host.is_file() or not os.access(host, os.X_OK) or
            any(not (extension / name).is_file() for name in
                ("manifest.json", "core.mjs", "popup.js", "popup.html", "popup.css"))):
        raise ValueError("setup.bundle_incomplete")
    return host


def locations(home=None):
    home = Path(home) if home is not None else Path.home()
    return {"manifest": home / f"Library/Application Support/Google/Chrome/NativeMessagingHosts/{HOST}.json",
            "host": home / "Library/Application Support/Morgan Media Downloader/companion-host",
            "launcher": home / "Desktop/Morgan Media Downloader Dev.app"}


def _safe_path(path):
    for parent in (path, *path.parents):
        if parent.is_symlink(): raise ValueError("setup.symlink")


def _write(path, data, mode=0o600):
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement, no predictable temporary file or symlink following.
    import tempfile
    fd, name = tempfile.mkstemp(prefix=".morgan-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data if isinstance(data, bytes) else data.encode()); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, mode); os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _inspect(paths, *, launcher=True):
    for name, path in paths.items():
        if name != "launcher" or launcher: _safe_path(path)
    manifest = paths["manifest"]
    if manifest.exists():
        data = json.loads(manifest.read_text())
        if data.get("name") != HOST or data.get("description") != MARKER or data.get("allowed_origins") != [ORIGIN] or data.get("path") != str(paths["host"] / "host"):
            raise ValueError("setup.foreign_manifest")
    root = paths["host"]
    if root.exists():
        if not root.is_dir() or {p.name for p in root.iterdir()} - {"host", "bootstrap.py"}:
            raise ValueError("setup.foreign_host")
        for path in root.iterdir():
            _safe_path(path)
            if MARKER not in path.read_text(): raise ValueError("setup.foreign_host")
    app = paths["launcher"]
    if launcher and app.exists():
        files = {p.relative_to(app).as_posix() for p in app.rglob("*") if p.is_file() or p.is_symlink()}
        if files != {"Contents/Info.plist", "Contents/MacOS/launch"}: raise ValueError("setup.foreign_launcher")
        for path in app.rglob("*"): _safe_path(path)
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != BUNDLE_ID or MARKER not in (app / "Contents/MacOS/launch").read_text():
            raise ValueError("setup.foreign_launcher")


def install(*, home=None, repository=None, python=None, launcher=False):
    bundled = packaged_host()  # Validate everything before touching registration.
    if bundled is not None: launcher = False
    paths = locations(home)
    _inspect(paths, launcher=launcher)  # Inspect only targets this operation changes.
    repository = Path(repository) if repository is not None else Path(__file__).resolve().parents[3]
    python = Path(python) if python is not None else Path(sys.executable)
    if not repository.is_absolute() or not python.is_absolute(): raise ValueError("setup.absolute_paths_required")
    bootstrap = f'''# {MARKER}
import sys
sys.path.insert(0, {str(repository / "src")!r})
from morgan_media_downloader.youtube_companion.native_host import main
raise SystemExit(main())
'''
    wrapper = f'''#!/bin/sh
# {MARKER}
# stdout is reserved exclusively for Chrome native-message frames.
exec {shlex.quote(str(python))} -I {shlex.quote(str(paths["host"] / "bootstrap.py"))} "$@" 2>/dev/null
'''
    if bundled is not None:
        wrapper = f'''#!/bin/sh
# {MARKER}
# Start this independent one-file helper with a fresh PyInstaller environment.
PYINSTALLER_RESET_ENVIRONMENT=1 exec {shlex.quote(str(bundled))} "$@" 2>/dev/null
'''
    else:
        _write(paths["host"] / "bootstrap.py", bootstrap)
    _write(paths["host"] / "host", wrapper, 0o700)
    manifest = {"name": HOST, "description": MARKER, "path": str(paths["host"] / "host"),
                "type": "stdio", "allowed_origins": [ORIGIN]}
    _write(paths["manifest"], json.dumps(manifest, indent=2))
    if bundled is not None:
        (paths["host"] / "bootstrap.py").unlink(missing_ok=True)
    if launcher:
        script = f'''#!/bin/sh
# {MARKER}
fail() {{
  printf '%s\\n' "$1" >&2
  if [ "${{MORGAN_LAUNCHER_NO_DIALOG:-}}" != 1 ]; then
    /usr/bin/osascript -e 'display alert "Morgan Media Downloader Dev" message "Connect the external drive and check the project Python environment. This development launcher needs the original project; see its companion setup documentation."' >/dev/null 2>&1
  fi
  exit 1
}}
[ -d {shlex.quote(str(repository / "src/morgan_media_downloader"))} ] || fail 'Project unavailable: connect the external drive.'
[ -x {shlex.quote(str(python))} ] || fail 'Project Python unavailable: repair the development environment.'
cd {shlex.quote(str(repository))} || fail 'Project unavailable: connect the external drive.'
PYTHONPATH={shlex.quote(str(repository / "src"))} {shlex.quote(str(python))} -m morgan_media_downloader >/dev/null 2>&1 || fail 'The development application could not start. Check the project environment.'
'''
        info = {"CFBundleIdentifier": BUNDLE_ID, "CFBundleName": "Morgan Media Downloader Dev",
                "CFBundleDisplayName": "Morgan Media Downloader Dev", "CFBundleExecutable": "launch",
                "CFBundlePackageType": "APPL", "CFBundleVersion": "1", "LSMinimumSystemVersion": "12.0",
                "NSHighResolutionCapable": True}
        _write(paths["launcher"] / "Contents/Info.plist", plistlib.dumps(info))
        _write(paths["launcher"] / "Contents/MacOS/launch", script, 0o700)
    return paths


def remove(*, home=None, launcher=None):
    if launcher is None: launcher = not getattr(sys, "frozen", False)
    paths = locations(home); _inspect(paths, launcher=launcher)
    # Exact files only, never recursive deletion of user directories.
    files = [paths["manifest"], paths["host"] / "host", paths["host"] / "bootstrap.py"]
    if launcher: files += [paths["launcher"] / "Contents/MacOS/launch", paths["launcher"] / "Contents/Info.plist"]
    for path in files:
        path.unlink(missing_ok=True)
    directories = [paths["host"]]
    if launcher: directories += [paths["launcher"] / "Contents/MacOS", paths["launcher"] / "Contents", paths["launcher"]]
    for path in directories:
        if path.exists(): path.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "remove", "status", "disconnect"))
    parser.add_argument("--development-launcher", action="store_true", help="Explicitly include the legacy source-dependent Desktop launcher")
    args = parser.parse_args()
    try:
        if args.action == "install":
            install(launcher=args.development_launcher)
            print("User-level native host installed. Enable the extension in Chrome manually.")
            if args.development_launcher and not getattr(sys, "frozen", False): print("Legacy development launcher installed by explicit request.")
        elif args.action == "remove":
            remove(launcher=args.development_launcher and not getattr(sys, "frozen", False))
            print("Requested Companion setup artifacts removed. Keychain session unchanged; use disconnect to delete it.")
        elif args.action == "disconnect":
            from .bridge import CompanionController
            CompanionController().disconnect(); print("Stored session deleted.")
        else:
            paths = locations(); _inspect(paths, launcher=args.development_launcher and not getattr(sys, "frozen", False))
            print("Native host registered." if paths["manifest"].is_file() else "Native host not registered.")
    except Exception:
        print("Companion setup failed. Check user-folder permissions, existing files and project availability; nothing requires administrator access.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
