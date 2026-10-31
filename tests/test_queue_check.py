from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem
from morgan_media_downloader.queue_check import exercise_queue
from morgan_media_downloader.settings import AppSettings, SettingsStore
from morgan_media_downloader.ui import MainWindow
from morgan_media_downloader.yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_window(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MORGAN_CACHE_DIR", str(tmp_path / "cache"))
    SettingsStore().save(AppSettings(authentication_mode="None", cookies_file="", browser_profile="",
        download_dir=str(tmp_path / "downloads"), torrent_download_dir=str(tmp_path / "torrents"),
        converter_output_dir=str(tmp_path / "converted"), connection_mode="Direct / Normal Network",
        show_first_run_diagnostics=False, first_run_complete=True, clipboard_url_detection=False,
        yt_dlp_check_updates_on_startup=False, yt_dlp_auto_install_updates=False, managed_tor_auto_start=False,
        concurrent_downloads=2))
    runtime = YtDlpRuntimeManager(tmp_path / "runtime", bundled_loader=lambda: RuntimeSnapshot("synthetic", "Fixture", object), provider_checker=lambda: None)
    runtime.initialize(); window = MainWindow(runtime)
    for timer in window.findChildren(QTimer): timer.stop()
    window.show(); APP.processEvents()
    try: yield window
    finally: window.close(); APP.processEvents()


def test_real_queue_diagnostic_completes_two_cycles_with_owned_workers_and_persistence(isolated_window, tmp_path):
    window = isolated_window
    report = exercise_queue(window, APP, 100, tmp_path, cycles=2)
    assert report["schema"] == 1 and report["result"] == "passed" and report["items"] == 100
    assert len(report["cycles"]) == 2 and report["max_owned_workers"] == 2
    for cycle, result in enumerate(report["cycles"], 1):
        assert result == {"cycle": cycle, "analysed": 100, "enqueued": 100, "started_workers": 2,
            "acknowledged_workers": 2, "cancelled": 100, "restored": 100, "removed": 100, "remaining": 0, "active_tasks": 0,
            "confirmation_requests": 1, "queue_rendered": True}
    assert report["network_attempts"] == report["keychain_attempts"] == report["deletion_attempts"] == report["process_attempts"] == 0
    for cycle in (1, 2):
        stages = {stage["operation"]: stage for stage in report["measurements"] if stage["cycle"] == cycle}
        assert set(stages) == {"analyse", "enqueue", "start", "progress-two-active", "pause-all", "resume-all", "cancel-selected", "reload", "remove-selected-keep-files"}
        assert stages["enqueue"]["sql"]["writes"] == 100
        assert stages["reload"]["sql"]["writes"] == 0
        assert all(stage["progress_widgets"] == 0 and stage["active_tasks"] <= 2 for stage in stages.values())
    assert not window.jobs and not window.active and not window.database.search_history()


def test_diagnostic_refuses_populated_state_without_mutating_it(isolated_window, tmp_path):
    window = isolated_window; job = DownloadJob(MediaItem("https://example.test/sentinel", "Retain me"), DownloadOptions())
    window.jobs[job.id] = job; window.database.save_job(job)
    with pytest.raises(ValueError): exercise_queue(window, APP, 100, tmp_path)
    assert list(window.jobs) == [job.id] and len(window.database.search_history()) == 1


@pytest.mark.parametrize("change", ["outside_root", "authentication", "invalid_count"])
def test_diagnostic_refuses_nonisolated_or_credentialed_inputs(isolated_window, tmp_path, change):
    window = isolated_window; count = 100
    if change == "outside_root": window.settings.download_dir = str(tmp_path.parent / "not-owned")
    if change == "authentication": window.settings.authentication_mode = "Browser Cookies"
    if change == "invalid_count": count = 999999
    with pytest.raises(ValueError): exercise_queue(window, APP, count, tmp_path)
    assert not window.jobs and window.task_manager.active_count == 0


def test_failure_after_dispatch_drains_owned_thread_before_restoring_guards(isolated_window, tmp_path, monkeypatch):
    window = isolated_window
    def start_then_fail():
        window.task_manager.start("download-media", lambda cancel, _progress: cancel.wait(5))
        raise RuntimeError("synthetic dispatch failure")
    monkeypatch.setattr(window, "_dispatch", start_then_fail)
    with pytest.raises(RuntimeError, match="synthetic dispatch failure"):
        exercise_queue(window, APP, 100, tmp_path)
    assert window.task_manager.active_count == 0, "Do not release I/O guards with owned work still running"


def test_worker_timeout_is_not_successful_cancellation(isolated_window, tmp_path, monkeypatch):
    import threading
    original_wait = threading.Event.wait
    # Fail actual cancellation admission; bound only the synthetic worker wait
    # so this regression demonstrates the failure without waiting30seconds.
    monkeypatch.setattr(isolated_window.task_manager, "cancel", lambda _task_id: False)
    monkeypatch.setattr(threading.Event, "wait", lambda self, timeout=None:
        original_wait(self, .2 if timeout == 30 else timeout))
    with pytest.raises(RuntimeError, match="cancellation"):
        exercise_queue(isolated_window, APP, 100, tmp_path)
    assert isolated_window.task_manager.active_count == 0


def test_uncommitted_queue_rows_cannot_establish_persistence(isolated_window, tmp_path, monkeypatch):
    real_connection = isolated_window.database._connection
    class UncommittedConnection:
        def __getattr__(self, name): return getattr(real_connection, name)
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    monkeypatch.setattr(isolated_window.database, "_connection", UncommittedConnection())
    with pytest.raises(RuntimeError, match="persist"):
        exercise_queue(isolated_window, APP, 100, tmp_path)
    assert isolated_window.task_manager.active_count == 0
