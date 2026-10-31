import json
from types import SimpleNamespace

import pytest

from scripts.check_packaged_app import verify


def bundle(tmp_path):
    app = tmp_path / "App.app"; (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/Morgan Media Downloader").write_text("synthetic executable")
    return app


def test_packaged_gui_probe_requires_cocoa_frozen_render_and_clean_shutdown(tmp_path):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        assert command[0] == str(app / "Contents/MacOS/Morgan Media Downloader")
        assert kwargs["env"]["QT_QPA_PLATFORM"] == "cocoa" and kwargs["env"]["PATH"] == "/usr/bin:/bin"
        assert "PYTHONPATH" not in kwargs["env"] and "DYLD_LIBRARY_PATH" not in kwargs["env"]
        from pathlib import Path
        Path(command[-1]).write_text(json.dumps({"schema": 1, "result": "passed", "qt_platform": "cocoa", "frozen": True,
            "rendered": True, "closed_cleanly": True, "bundled_dependency_discovery": True,
            "tabs": ["Download", "Queue", "History", "Console", "Settings"]}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert verify(app, runner=run)["qt_platform"] == "cocoa"


@pytest.mark.parametrize("bad_field,bad_value", [("frozen", False), ("qt_platform", "offscreen"), ("rendered", False),
    ("closed_cleanly", False), ("bundled_dependency_discovery", False)])
def test_packaged_gui_probe_never_accepts_source_headless_or_partial_success(tmp_path, bad_field, bad_value):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        from pathlib import Path
        data = {"schema": 1, "result": "passed", "qt_platform": "cocoa", "frozen": True,
            "rendered": True, "closed_cleanly": True, "bundled_dependency_discovery": True,
            "tabs": ["Download", "Queue", "History", "Console", "Settings"]}
        data[bad_field] = bad_value; Path(command[-1]).write_text(json.dumps(data))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(RuntimeError): verify(app, runner=run)


def test_failed_startup_report_preserves_redacted_diagnostic(tmp_path):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        from pathlib import Path
        Path(command[-1]).write_text(json.dumps({"result": "failed", "error_type": "RuntimeError", "error": "synthetic startup failure cookie=[redacted]"}))
        return SimpleNamespace(returncode=2, stdout="", stderr="")
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        verify(app, runner=run)


def queue_payload(count=100):
    data = {"schema": 1, "result": "passed", "qt_platform": "cocoa", "frozen": True,
        "rendered": True, "closed_cleanly": True, "bundled_dependency_discovery": True,
        "tabs": ["Download", "Queue", "History", "Console", "Settings"]}
    stages = ("analyse", "enqueue", "start", "progress-two-active", "pause-all", "resume-all", "cancel-selected", "reload", "remove-selected-keep-files")
    queue = {"schema": 1, "result": "passed", "items": count, "platform": "darwin", "cycles": [], "measurements": [],
        "max_owned_workers": 2, "confirmation_requests": 2, "cleanup_fixture": None, "worker_errors": 0,
        "network_attempts": 0, "keychain_attempts": 0, "deletion_attempts": 0, "process_attempts": 0}
    writes = {"analyse": 0, "enqueue": count, "start": 2, "progress-two-active": 2, "pause-all": count,
        "resume-all": count, "cancel-selected": count, "reload": 0, "remove-selected-keep-files": count}
    for cycle in (1, 2):
        queue["cycles"].append({"cycle": cycle, "analysed": count, "enqueued": count, "started_workers": 2,
            "acknowledged_workers": 2, "cancelled": count, "restored": count, "removed": count, "remaining": 0, "active_tasks": 0,
            "confirmation_requests": 1, "queue_rendered": True})
        for stage in stages:
            queue["measurements"].append({"cycle": cycle, "operation": stage, "wall_seconds": .01, "cpu_seconds": .01,
                "max_heartbeat_gap_seconds": .01, "peak_rss_mib": 128.0, "current_rss_mib": 120.0,
                "native_threads": 8, "active_tasks": 2 if stage in {"start", "progress-two-active"} else 0,
                "progress_widgets": 0, "sql": {"statements": writes[stage]+2, "writes": writes[stage], "commits": 1}})
    data["queue"] = queue
    return data


def test_packaged_queue_probe_requests_two_real_cycles_and_does_not_inherit_tokens(tmp_path, monkeypatch):
    app = bundle(tmp_path); monkeypatch.setenv("SYNTHETIC_SECRET_TOKEN", "must-not-enter-child")
    def run(command, **kwargs):
        from pathlib import Path
        assert command[command.index("--queue-items")+1] == "100"
        assert kwargs["timeout"] >= 120 and "SYNTHETIC_SECRET_TOKEN" not in kwargs["env"]
        Path(command[command.index("--startup-check")+1]).write_text(json.dumps(queue_payload()))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert verify(app, runner=run, queue_items=100)["queue"]["items"] == 100


@pytest.mark.parametrize("defect", ["no_queue", "no_cycles", "wrong_count", "boolean_count", "outstanding_owner",
    "missing_stage", "duplicate_cycle", "network_attempt", "wrong_platform", "row_widgets", "nan_timing",
    "no_measured_workers", "no_measured_memory", "no_persisted_enqueue", "reload_writes"])
def test_packaged_queue_probe_rejects_partial_or_misleading_evidence(tmp_path, defect):
    app = bundle(tmp_path); data = queue_payload(); queue = data["queue"]
    if defect == "no_queue": data.pop("queue")
    elif defect == "no_cycles": queue["cycles"] = []
    elif defect == "wrong_count": queue["cycles"][0]["removed"] = 99
    elif defect == "boolean_count": queue["cycles"][0]["started_workers"] = True
    elif defect == "outstanding_owner": queue["cycles"][0]["active_tasks"] = 1
    elif defect == "missing_stage": queue["measurements"].pop()
    elif defect == "duplicate_cycle": queue["cycles"][1]["cycle"] = 1
    elif defect == "network_attempt": queue["network_attempts"] = 1
    elif defect == "wrong_platform": queue["platform"] = "linux"
    elif defect == "row_widgets": queue["measurements"][0]["progress_widgets"] = 100
    elif defect == "nan_timing": queue["measurements"][0]["wall_seconds"] = float("nan")
    elif defect == "no_measured_workers": queue["measurements"][2]["active_tasks"] = 0
    elif defect == "no_measured_memory": queue["measurements"][0]["current_rss_mib"] = 0
    elif defect == "no_persisted_enqueue": queue["measurements"][1]["sql"]["writes"] = 0
    elif defect == "reload_writes": queue["measurements"][7]["sql"]["writes"] = 100
    def run(command, **kwargs):
        from pathlib import Path
        Path(command[command.index("--startup-check")+1]).write_text(json.dumps(data))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(RuntimeError): verify(app, runner=run, queue_items=100)


def test_native_queue_crash_preserves_safe_stack_but_not_arbitrary_child_logs(tmp_path):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        return SimpleNamespace(returncode=-6, stdout="cookie=synthetic-cookie", stderr=
            'Fatal Python error: Aborted\nCurrent thread 0x123:\n  File "/synthetic/queue.py", line 4 in run\ncookie=synthetic-cookie\n')
    with pytest.raises(RuntimeError) as error: verify(app, runner=run, queue_items=100)
    assert "-6" in str(error.value) and "Aborted" in str(error.value)
    assert "/synthetic/queue.py" in str(error.value) and "synthetic-cookie" not in str(error.value)


def test_native_queue_timeout_preserves_only_bounded_safe_trace(tmp_path):
    import subprocess
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 150, stderr=(b'Fatal Python error: Aborted\n'
            b'  File "/synthetic/cookie=synthetic-cookie.py", line 4 in run\n'
            b'authorization=synthetic-authorization\n') * 100)
    with pytest.raises(RuntimeError) as error: verify(bundle(tmp_path), runner=run, queue_items=100)
    detail = str(error.value)
    assert "timed out" in detail and "Aborted" in detail and len(detail) < 5000
    assert "synthetic-cookie" not in detail and "synthetic-authorization" not in detail


def test_native_teardown_crash_after_report_still_preserves_stack(tmp_path):
    def run(command, **kwargs):
        from pathlib import Path
        Path(command[command.index("--startup-check")+1]).write_text(json.dumps(queue_payload()))
        return SimpleNamespace(returncode=-6, stdout="", stderr='Fatal Python error: Aborted\n  File "/synthetic/late.py", line 4 in run\ncookie=synthetic-cookie\n')
    with pytest.raises(RuntimeError) as error: verify(bundle(tmp_path), runner=run, queue_items=100)
    assert "Aborted" in str(error.value) and "/synthetic/late.py" in str(error.value)
    assert "synthetic-cookie" not in str(error.value)


def test_queue_validator_requires_committed_writes(tmp_path):
    data = queue_payload()
    for measurement in data["queue"]["measurements"]: measurement["sql"]["commits"] = 0
    def run(command, **kwargs):
        from pathlib import Path
        Path(command[command.index("--startup-check")+1]).write_text(json.dumps(data))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(RuntimeError): verify(bundle(tmp_path), runner=run, queue_items=100)


def test_standalone_checker_reports_native_failure_without_source_on_pythonpath(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    app = bundle(tmp_path)
    executable = app / "Contents/MacOS/Morgan Media Downloader"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "Fatal Python error: Aborted" >&2\nexit 6\n')
    executable.chmod(0o700)
    result = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve().parents[1] / "scripts/check_packaged_app.py"),
                             str(app), "--queue-items", "100"], cwd=tmp_path,
                            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and "Aborted" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr and "exit 6" in result.stderr
