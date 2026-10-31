"""Run the actual frozen Cocoa GUI's isolated startup diagnostic on hosted macOS."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import re


QUEUE_SIZES = (100, 800, 1000, 5000)
QUEUE_STAGES = ("analyse", "enqueue", "start", "progress-two-active", "pause-all", "resume-all",
                "cancel-selected", "reload", "remove-selected-keep-files")


def validate_queue(data: object, count: int) -> None:
    """Require complete native evidence, not just a successful outer startup."""
    def require(condition):
        if not condition: raise RuntimeError("Frozen GUI queue report is incomplete or invalid")
    def integer(value, expected):
        return type(value) is int and value == expected
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    require(isinstance(data, dict))
    require(integer(data.get("schema"), 1) and data.get("result") == "passed" and
            integer(data.get("items"), count) and data.get("platform") == "darwin")
    for key, expected in {"max_owned_workers": 2, "confirmation_requests": 2, "network_attempts": 0,
                          "keychain_attempts": 0, "deletion_attempts": 0, "process_attempts": 0, "worker_errors": 0}.items():
        require(integer(data.get(key), expected))
    require("cleanup_fixture" in data and data["cleanup_fixture"] is None)
    cycles = data.get("cycles")
    require(isinstance(cycles, list) and len(cycles) == 2)
    for number, cycle in enumerate(cycles, 1):
        require(isinstance(cycle, dict))
        expected = dict(cycle=number, analysed=count, enqueued=count, started_workers=2, acknowledged_workers=2, cancelled=count,
                        restored=count, removed=count, remaining=0, active_tasks=0, confirmation_requests=1)
        require(all(integer(cycle.get(key), value) for key, value in expected.items()) and cycle.get("queue_rendered") is True)
        checks = cycle.get("selection_checks")
        require(isinstance(checks, dict))
        expected_selection = dict(filtered=count, status=count, all=count, none=0, sql_writes=0,
                                  sql_commits=0, sql_statements=0, owned_tasks=0)
        require(all(integer(checks.get(key), value) for key, value in expected_selection.items()))
        require(checks.get("cleared_hidden") is True and checks.get("viewport_matched") is True and
                type(checks.get("visible")) is int and 0 < checks["visible"] <= count)
        require(finite(checks.get("wall_seconds")))
    measurements = data.get("measurements")
    require(isinstance(measurements, list) and len(measurements) == 18)
    for measurement, (cycle, stage) in zip(measurements, ((n, s) for n in (1, 2) for s in QUEUE_STAGES)):
        require(isinstance(measurement, dict))
        require(integer(measurement.get("cycle"), cycle) and measurement.get("operation") == stage)
        for key in ("wall_seconds", "cpu_seconds", "max_heartbeat_gap_seconds", "peak_rss_mib", "current_rss_mib"):
            require(finite(measurement.get(key)))
        require(measurement["peak_rss_mib"] > 0 and measurement["current_rss_mib"] > 0)
        require(type(measurement.get("native_threads")) is int and measurement["native_threads"] > 0)
        require(integer(measurement.get("progress_widgets"), 0))
        require(type(measurement.get("active_tasks")) is int and 0 <= measurement["active_tasks"] <= 2)
        if stage in {"start", "progress-two-active"}: require(integer(measurement["active_tasks"], 2))
        sql = measurement.get("sql")
        require(isinstance(sql, dict) and all(type(sql.get(key)) is int and sql[key] >= 0 for key in ("statements", "commits", "writes")))
        writes = {"analyse": 0, "enqueue": count, "start": 2, "progress-two-active": 2, "pause-all": count,
                  "resume-all": count, "cancel-selected": count, "reload": 0, "remove-selected-keep-files": count}
        require(sql["writes"] == writes[stage] and sql["statements"] >= sql["writes"])
        if sql["writes"]: require(0 < sql["commits"] <= sql["writes"])


def native_trace(stderr: str | bytes | None) -> str:
    """Only traceback structure; never arbitrary process logs or source lines."""
    from morgan_media_downloader.logging_setup import redact_secrets
    if isinstance(stderr, bytes): stderr = stderr.decode("utf-8", errors="replace")
    lines = []
    for line in (stderr or "")[:65536].splitlines():
        if (re.fullmatch(r"Fatal Python error: (?:Aborted|Segmentation fault|Bus error|Illegal instruction)", line) or
                re.fullmatch(r"(?:Current thread|Thread) 0x[0-9a-fA-F]+(?: \(most recent call first\))?:", line) or
                re.fullmatch(r'  File "[^"\r\n]{1,400}", line [0-9]+ in [A-Za-z0-9_<>.]+', line) or
                line == "QThread: Destroyed while thread is still running"):
            lines.append(redact_secrets(line))
        if len(lines) >= 20: break
    return "\n" + "\n".join(lines) if lines else ""


def verify(app: Path, *, runner=subprocess.run, queue_items: int | None = None):
    if queue_items is not None and (type(queue_items) is not int or queue_items not in QUEUE_SIZES):
        raise ValueError("Unsupported queue diagnostic size")
    contents = app.resolve(strict=True) / "Contents"
    executable = contents / "MacOS/Morgan Media Downloader"
    if not executable.is_file() or not executable.resolve().is_relative_to(contents):
        raise RuntimeError("Frozen GUI executable missing or outside bundle")
    with tempfile.TemporaryDirectory(prefix="morgan-gui-probe-") as temporary:
        report = Path(temporary) / "startup.json"
        excluded = {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "NODE_OPTIONS", "NODE_PATH", "MORGAN_BGUTIL_HOME"}
        environment = {key: value for key, value in os.environ.items() if key not in excluded and not key.startswith("DYLD_")}
        if queue_items is not None:
            # No CI/service/SSH/API tokens enter the synthetic queue process.
            environment = {key: value for key, value in os.environ.items() if key in
                           {"TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "__CF_USER_TEXT_ENCODING"}}
        environment.update(HOME=temporary, PATH="/usr/bin:/bin", QT_QPA_PLATFORM="cocoa", PYINSTALLER_RESET_ENVIRONMENT="1")
        command = [str(executable), "--startup-check", str(report)]
        if queue_items is not None: command.extend(["--queue-items", str(queue_items)])
        try:
            result = runner(command, cwd=temporary, env=environment,
                            capture_output=True, text=True, timeout=150 if queue_items is not None else 45, check=False)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Frozen GUI diagnostic timed out" + (native_trace(error.stderr) if queue_items is not None else "")) from None
        if not report.is_file():
            raise RuntimeError(f"Frozen GUI startup diagnostic failed (exit {result.returncode}); no qualified report" +
                               (native_trace(result.stderr) if queue_items is not None else ""))
        with report.open("rb") as stream: payload = stream.read(32769)
        if len(payload) > 32768: raise RuntimeError("Frozen GUI startup report exceeds limit")
        data = json.loads(payload)
        if not isinstance(data, dict): raise RuntimeError("Malformed GUI startup report")
        if result.returncode != 0:
            # Only this isolated diagnostic's own redacted error is reported;
            # never dump a GUI process's potentially unstructured stdout/stderr.
            detail = str(data.get("error", "No error detail"))[:500].replace("\n", " ").replace("\r", " ")
            raise RuntimeError(f"Frozen GUI startup diagnostic failed (exit {result.returncode}): {detail}" +
                               (native_trace(result.stderr) if queue_items is not None else ""))
        if (data.get("schema") != 1 or data.get("result") != "passed" or data.get("qt_platform") != "cocoa" or
                any(data.get(key) is not True for key in ("frozen", "rendered", "closed_cleanly", "bundled_dependency_discovery")) or
                data.get("tabs") != ["Download", "Queue", "History", "Console", "Settings"]):
            raise RuntimeError("Frozen GUI report does not establish Cocoa rendering, dependency discovery and clean shutdown")
        if queue_items is not None: validate_queue(data.get("queue"), queue_items)
    return data


if __name__ == "__main__":
    # CI installs dependency wheels, not this source package. Keep diagnostic
    # redaction available on the failure path without ambient PYTHONPATH.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("app", type=Path)
    parser.add_argument("--queue-items", type=int, choices=QUEUE_SIZES)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.app, queue_items=arguments.queue_items), sort_keys=True))
