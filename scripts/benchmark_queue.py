"""Isolated synthetic queue baseline; no network, accounts, media or installation.

Each size runs in a separate process, so native faults and timeouts are evidence,
not a crash of the controller. Modal choices are intercepted and counted only.
The timings are measurements, not performance acceptance thresholds.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run_case(count, *, profile=False, synthetic_cleanup=False):
    with tempfile.TemporaryDirectory(prefix="morgan-queue-scale-") as temporary:
        root = Path(temporary)
        os.environ.update(QT_QPA_PLATFORM="offscreen", MORGAN_DATA_DIR=str(root / "data"),
                          MORGAN_LOG_DIR=str(root / "logs"), MORGAN_CACHE_DIR=str(root / "cache"))
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from morgan_media_downloader.queue_check import exercise_queue
        from morgan_media_downloader.settings import AppSettings, SettingsStore
        from morgan_media_downloader.ui import MainWindow
        from morgan_media_downloader.yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager

        SettingsStore().save(AppSettings(authentication_mode="None", download_dir=str(root / "downloads"),
            torrent_download_dir=str(root / "torrents"), converter_output_dir=str(root / "converted"),
            cookies_file="", browser_profile="", show_first_run_diagnostics=False, first_run_complete=True,
            yt_dlp_check_updates_on_startup=False, yt_dlp_auto_install_updates=False,
            clipboard_url_detection=False, managed_tor_auto_start=False, concurrent_downloads=2,
            connection_mode="Direct / Normal Network"))
        runtime = YtDlpRuntimeManager(root / "runtime",
            bundled_loader=lambda: RuntimeSnapshot("synthetic", "Fixture", object), provider_checker=lambda: None)
        runtime.initialize()
        app = QApplication([]); app.setQuitOnLastWindowClosed(False)
        window = MainWindow(runtime)
        for timer in window.findChildren(QTimer): timer.stop()
        window.show(); app.processEvents()
        def progress(measurement):
            print(json.dumps({"items": count, "measurement": measurement}, sort_keys=True), file=sys.stderr, flush=True)
        try:
            return exercise_queue(window, app, count, root, profile=profile, synthetic_cleanup=synthetic_cleanup,
                on_measurement=progress)
        finally:
            window.close(); app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=int, nargs="+", choices=[100, 800, 1000, 5000], default=[100, 800, 1000, 5000])
    parser.add_argument("--child", type=int, choices=[100, 800, 1000, 5000], help=argparse.SUPPRESS)
    parser.add_argument("--profile", action="store_true", help="Include pause-all's top20 cumulative profile; timings include profiler cost")
    parser.add_argument("--synthetic-cleanup", action="store_true", help="Exercise owned cleanup workers with a 1ms/job fake deleter; never deletes files")
    args = parser.parse_args()
    if args.child:
        print(json.dumps(run_case(args.child, profile=args.profile, synthetic_cleanup=args.synthetic_cleanup), sort_keys=True), flush=True); return
    failed = False
    for count in args.items:
        try:
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", str(count)]
            if args.profile: command.append("--profile")
            if args.synthetic_cleanup: command.append("--synthetic-cleanup")
            result = subprocess.run(command,
                capture_output=True, text=True, timeout=120, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONFAULTHANDLER="1"))
            if result.returncode:
                failed = True
                print(json.dumps({"items": count, "result": "failed", "returncode": result.returncode,
                                  "stderr": result.stderr[-6000:]}, sort_keys=True), flush=True)
            else: print(result.stdout.strip(), flush=True)
        except subprocess.TimeoutExpired as error:
            detail = error.stderr or b""
            if isinstance(detail, bytes): detail = detail.decode("utf-8", errors="replace")
            failed = True
            print(json.dumps({"items": count, "result": "timeout", "limit_seconds": 120,
                              "stderr": detail[-6000:]}, sort_keys=True), flush=True)
    if failed: raise SystemExit(1)


if __name__ == "__main__": main()
