"""Run the actual frozen Cocoa GUI's isolated startup diagnostic on hosted macOS."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def verify(app: Path, *, runner=subprocess.run):
    contents = app.resolve(strict=True) / "Contents"
    executable = contents / "MacOS/Morgan Media Downloader"
    if not executable.is_file() or not executable.resolve().is_relative_to(contents):
        raise RuntimeError("Frozen GUI executable missing or outside bundle")
    with tempfile.TemporaryDirectory(prefix="morgan-gui-probe-") as temporary:
        report = Path(temporary) / "startup.json"
        excluded = {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "NODE_OPTIONS", "NODE_PATH", "MORGAN_BGUTIL_HOME"}
        environment = {key: value for key, value in os.environ.items() if key not in excluded and not key.startswith("DYLD_")}
        environment.update(HOME=temporary, PATH="/usr/bin:/bin", QT_QPA_PLATFORM="cocoa", PYINSTALLER_RESET_ENVIRONMENT="1")
        result = runner([str(executable), "--startup-check", str(report)], cwd=temporary, env=environment,
                        capture_output=True, text=True, timeout=45, check=False)
        if not report.is_file():
            raise RuntimeError(f"Frozen GUI startup diagnostic failed (exit {result.returncode}); no qualified report")
        with report.open("rb") as stream: payload = stream.read(32769)
        if len(payload) > 32768: raise RuntimeError("Frozen GUI startup report exceeds limit")
        data = json.loads(payload)
        if not isinstance(data, dict): raise RuntimeError("Malformed GUI startup report")
        if result.returncode != 0:
            # Only this isolated diagnostic's own redacted error is reported;
            # never dump a GUI process's potentially unstructured stdout/stderr.
            detail = str(data.get("error", "No error detail"))[:500].replace("\n", " ").replace("\r", " ")
            raise RuntimeError(f"Frozen GUI startup diagnostic failed (exit {result.returncode}): {detail}")
        if (data.get("schema") != 1 or data.get("result") != "passed" or data.get("qt_platform") != "cocoa" or
                any(data.get(key) is not True for key in ("frozen", "rendered", "closed_cleanly", "bundled_dependency_discovery")) or
                data.get("tabs") != ["Download", "Queue", "History", "Console", "Settings"]):
            raise RuntimeError("Frozen GUI report does not establish Cocoa rendering, dependency discovery and clean shutdown")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("app", type=Path)
    print(json.dumps(verify(parser.parse_args().app), sort_keys=True))
