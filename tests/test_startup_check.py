import json
import os
from pathlib import Path
import subprocess
import sys
import pytest


def launch(tmp_path, report, *, setup="", queue_items=None):
    project = Path(__file__).resolve().parents[1]
    home = tmp_path / "synthetic-home"; home.mkdir(exist_ok=True)
    data = tmp_path / "synthetic-user-data"; data.mkdir(exist_ok=True)
    marker = data / "settings.json"
    settings = '{"synthetic_user_preference":"must remain untouched","yt_dlp_check_updates_on_startup":false,"yt_dlp_auto_install_updates":false,"show_first_run_diagnostics":false,"clipboard_url_detection":false,"authentication_mode":"None"}'
    marker.write_text(settings)
    environment = dict(os.environ, HOME=str(home), MORGAN_DATA_DIR=str(data), MORGAN_LOG_DIR=str(data / "logs"),
        MORGAN_CACHE_DIR=str(data / "cache"), QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(project / "src"), PYTHONDONTWRITEBYTECODE="1")
    arguments = ["--startup-check", str(report)]
    if queue_items is not None: arguments.extend(["--queue-items", str(queue_items)])
    command = [sys.executable, "-B", "-m", "morgan_media_downloader", *arguments]
    if setup:
        command = [sys.executable, "-B", "-c", setup + "\nimport sys\nfrom morgan_media_downloader.app import main\nsys.argv=['app',*sys.argv[1:]]\nraise SystemExit(main())", *arguments]
    result = subprocess.run(command,
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120 if queue_items else 30)
    assert marker.read_text() == settings
    assert not (home / "Downloads").exists()
    return result


def test_actual_gui_diagnostic_renders_and_closes_without_using_existing_state(tmp_path):
    report = tmp_path / "report.json"
    result = launch(tmp_path, report)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["result"] == "passed"
    assert evidence["qt_platform"] == "offscreen"
    assert evidence["rendered"] is True and evidence["closed_cleanly"] is True
    assert evidence["tabs"] == ["Download", "Queue", "History", "Console", "Settings"]


def test_startup_diagnostic_refuses_to_overwrite_existing_report(tmp_path):
    report = tmp_path / "report.json"; report.write_text("keep existing")
    result = launch(tmp_path, report)
    assert result.returncode != 0
    assert report.read_text() == "keep existing"


def test_startup_diagnostic_never_calls_network_or_keychain(tmp_path):
    report = tmp_path / "report.json"
    attempted = tmp_path / "forbidden-attempt"
    setup = f"""
import socket
from pathlib import Path
from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
def forbidden(*args, **kwargs):
    Path({str(attempted)!r}).write_text('Forbidden I/O attempted')
    raise AssertionError('Network or Keychain must not be used')
socket.socket.connect = forbidden
KeychainSessionStore._operation = forbidden
"""
    result = launch(tmp_path, report, setup=setup)
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text())["result"] == "passed"
    assert not attempted.exists()


def test_startup_failure_is_reported_with_redacted_actionable_detail(tmp_path):
    report = tmp_path / "report.json"
    setup = """
import morgan_media_downloader.ui as ui
def broken(*args, **kwargs): raise RuntimeError('synthetic startup failure cookie=synthetic-cookie')
ui.MainWindow = broken
"""
    result = launch(tmp_path, report, setup=setup)
    assert result.returncode != 0
    evidence = json.loads(report.read_text())
    assert evidence["result"] == "failed"
    assert "synthetic startup failure" in evidence["error"]
    assert "synthetic-cookie" not in report.read_text()


@pytest.mark.parametrize("count", [100, 800, 1000, 5000])
def test_actual_gui_queue_diagnostic_exercises_two_real_cycles_in_isolated_state(tmp_path, count):
    report = tmp_path / "queue.json"
    result = launch(tmp_path, report, queue_items=count)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["result"] == "passed" and evidence["closed_cleanly"] is True
    queue = evidence["queue"]
    assert queue["items"] == count and len(queue["cycles"]) == 2
    assert queue["max_owned_workers"] == 2 and queue["confirmation_requests"] == 2
    assert all(cycle["removed"] == count and cycle["remaining"] == cycle["active_tasks"] == 0 for cycle in queue["cycles"])
    assert queue["network_attempts"] == queue["keychain_attempts"] == queue["deletion_attempts"] == queue["process_attempts"] == 0


def test_queue_diagnostic_never_calls_external_io_or_keychain(tmp_path):
    report = tmp_path / "queue.json"; attempted = tmp_path / "forbidden-attempt"
    setup = f"""
import socket
from pathlib import Path
from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
def forbidden(*args, **kwargs):
    Path({str(attempted)!r}).write_text('Forbidden I/O attempted')
    raise AssertionError('No network or Keychain')
socket.socket.connect = forbidden
KeychainSessionStore._operation = forbidden
"""
    result = launch(tmp_path, report, setup=setup, queue_items=100)
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text())["queue"]["network_attempts"] == 0 and not attempted.exists()


def test_queue_diagnostic_works_with_windowed_python_stdio_absent(tmp_path):
    report = tmp_path / "queue-windowed.json"
    result = launch(tmp_path, report, queue_items=100, setup="import sys\nsys.stdout = sys.stderr = None")
    assert result.returncode == 0, result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["closed_cleanly"] is True and len(evidence["queue"]["cycles"]) == 2
    assert "QUEUE_CHECK_STAGE" in result.stderr


def test_queue_items_without_explicit_report_never_starts_normal_application(tmp_path):
    # If the diagnostic flag fell through to normal startup, this spy proves it
    # before any real GUI/runtime/account work could start.
    setup = """
import sys
import morgan_media_downloader.app as app
def forbidden(): raise AssertionError('Normal startup must not run')
app.configure_logging = forbidden
sys.argv = ['app', '--queue-items', '100']
raise SystemExit(app.main())
"""
    result = launch(tmp_path, tmp_path / "unused.json", setup=setup)
    assert result.returncode == 2 and "--startup-check" in result.stderr
    assert "Normal startup must not run" not in result.stderr
