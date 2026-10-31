"""Opt-in, isolated GUI startup diagnostics; ordinary startup is unchanged."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time


def run_startup_check(report_path: Path, *, queue_items: int | None = None) -> int:
    # Never overwrite a user's file or follow a final-component symlink.
    if report_path.exists() or report_path.is_symlink() or not report_path.parent.is_dir(): return 2
    if queue_items is not None and (type(queue_items) is not int or queue_items not in (100, 800, 1000, 5000)): return 2
    evidence = {"schema": 1, "result": "failed", "rendered": False, "closed_cleanly": False,
                "frozen": bool(getattr(sys, "frozen", False)),
                "scope": "GUI construction/render/clean shutdown only; no live account, network or media-transfer qualification"}
    if queue_items is not None:
        evidence["scope"] = "Isolated GUI synthetic queue/SQLite/owned-worker cycles; no live account, network, real media/file deletion or leak qualification"
    keys = ("HOME", "MORGAN_DATA_DIR", "MORGAN_LOG_DIR", "MORGAN_CACHE_DIR", "XDG_CACHE_HOME", "MORGAN_BGUTIL_HOME")
    previous = {key: os.environ.get(key) for key in keys}
    def record_error(error):
        from .logging_setup import redact_secrets
        evidence.update(error_type=type(error).__name__, error=redact_secrets(str(error))[:500])
    try:
        with tempfile.TemporaryDirectory(prefix="morgan-startup-check-") as temporary:
            root = Path(temporary)
            os.environ.pop("MORGAN_BGUTIL_HOME", None)
            os.environ.update(HOME=temporary, MORGAN_DATA_DIR=str(root / "data"), MORGAN_LOG_DIR=str(root / "logs"),
                              MORGAN_CACHE_DIR=str(root / "cache"), XDG_CACHE_HOME=str(root / "cache"))
            if queue_items is not None:
                import faulthandler
                # The windowed frozen app can have sys.stderr=None. The verifier
                # supplies OS fd2; traceback output never depends on Python stdio.
                faulthandler.enable(file=2, all_threads=True)
            # Imports follow isolation, before any browser-profile/default-path
            # discovery. No existing settings, history, auth or runtime is used.
            from PySide6.QtCore import QCoreApplication, QTimer
            from PySide6.QtWidgets import QApplication
            from .settings import AppSettings, SettingsStore
            from .yt_runtime import YtDlpRuntimeManager
            from .ui import MainWindow
            settings = AppSettings(authentication_mode="None", cookies_file="", browser_profile="",
                download_dir=str(root / "downloads"), torrent_download_dir=str(root / "torrents"),
                converter_output_dir=str(root / "converted"), yt_dlp_check_updates_on_startup=False,
                yt_dlp_auto_install_updates=False, show_first_run_diagnostics=False, first_run_complete=True,
                clipboard_url_detection=False, managed_tor_auto_start=False, connection_mode="Direct / Normal Network",
                concurrent_downloads=2)
            SettingsStore().save(settings)
            manager = YtDlpRuntimeManager(); manager.initialize()
            QCoreApplication.setOrganizationName("Morgan")
            QCoreApplication.setApplicationName("Morgan Media Downloader")
            application = QApplication([]); application.setQuitOnLastWindowClosed(False)
            window = MainWindow(manager)
            # The GUI is real. Timed connection/provider/clipboard/update work is
            # explicitly outside this diagnostic; stop it before the event loop.
            for timer in window.findChildren(QTimer): timer.stop()
            if evidence["frozen"]:
                from .paths import find_binary
                from .provider import find_runtime, find_script_home
                contents = Path(sys.executable).resolve().parent.parent
                required = [find_binary(name) for name in ("ffmpeg", "ffprobe", "aria2c")]
                required.extend([find_runtime(for_player=True), find_script_home()])
                if any(not path or not Path(path).resolve().is_relative_to(contents) for path in required):
                    raise RuntimeError("Frozen dependency discovery escaped the bundle")
                evidence["bundled_dependency_discovery"] = True
            window.show()
            deadline = time.monotonic() + 10
            def inspect():
                try:
                    handle = window.windowHandle()
                    if not handle or not handle.isExposed():
                        if time.monotonic() < deadline:
                            QTimer.singleShot(50, inspect); return
                        raise RuntimeError("Window was not exposed")
                    frame = window.grab()
                    if not window.isVisible() or frame.isNull() or frame.width() < 900 or frame.height() < 650:
                        raise RuntimeError("Window did not render")
                    evidence.update(rendered=True, qt_platform=application.platformName(),
                        tabs=[window.tabs.tabText(index) for index in range(window.tabs.count())])
                    if queue_items is not None:
                        from .queue_check import exercise_queue
                        def stage_trace(stage):
                            breadcrumb = {key: stage[key] for key in ("cycle", "operation", "wall_seconds")}
                            os.write(2, ("QUEUE_CHECK_STAGE " + json.dumps(breadcrumb, sort_keys=True) + "\n").encode())
                        evidence["queue"] = exercise_queue(window, application, queue_items, root, cycles=2,
                                                           on_measurement=stage_trace)
                    if not window.close() or window.clean_marker.exists(): raise RuntimeError("Window did not close cleanly")
                    evidence.update(closed_cleanly=True, result="passed")
                except Exception as error:
                    record_error(error)
                    window.close()
                finally:
                    if evidence["rendered"] or time.monotonic() >= deadline or "error" in evidence: application.quit()
            QTimer.singleShot(0, inspect)
            application.exec()
    except Exception as error:
        record_error(error)
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
    try:
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, indent=2); stream.write("\n")
    except OSError: return 2
    return 0 if evidence["result"] == "passed" else 2
