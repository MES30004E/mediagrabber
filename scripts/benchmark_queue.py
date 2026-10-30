"""Isolated synthetic queue baseline; no network, accounts, media or installation.

Each size runs in a separate process, so native faults and timeouts are evidence,
not a crash of the controller. Modal choices are intercepted and counted only.
The timings are measurements, not performance acceptance thresholds.
"""
from __future__ import annotations

import argparse
import copy
import cProfile
import io
import json
import os
from pathlib import Path
import resource
import pstats
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def native_threads():
    if sys.platform == "linux": return len(list(Path("/proc/self/task").iterdir()))
    if sys.platform == "darwin":
        return max(0, len(subprocess.check_output(["ps", "-M", "-p", str(os.getpid())], text=True).splitlines()) - 1)
    return None


def run_case(count, *, profile=False):
    with tempfile.TemporaryDirectory(prefix="morgan-queue-scale-") as temporary:
        root = Path(temporary)
        os.environ.update(QT_QPA_PLATFORM="offscreen", MORGAN_DATA_DIR=str(root / "data"),
                          MORGAN_LOG_DIR=str(root / "logs"), MORGAN_CACHE_DIR=str(root / "cache"))
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QProgressBar
        from morgan_media_downloader.models import DownloadOptions, JobStatus, MediaItem
        from morgan_media_downloader.settings import AppSettings, SettingsStore
        from morgan_media_downloader.ui import AnalysisContext, MainWindow
        from morgan_media_downloader.yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager

        SettingsStore().save(AppSettings(authentication_mode="None", download_dir=str(root / "downloads"),
            cookies_file="", browser_profile="", show_first_run_diagnostics=False, first_run_complete=True,
            yt_dlp_check_updates_on_startup=False, yt_dlp_auto_install_updates=False,
            clipboard_url_detection=False, managed_tor_auto_start=False, concurrent_downloads=2))
        runtime = YtDlpRuntimeManager(root / "runtime",
            bundled_loader=lambda: RuntimeSnapshot("synthetic", "Fixture", object), provider_checker=lambda: None)
        runtime.initialize()
        app = QApplication([]); app.setQuitOnLastWindowClosed(False)
        window = MainWindow(runtime)
        for timer in window.findChildren(QTimer): timer.stop()
        window.show(); app.processEvents()
        results = []; sql = {"statements": 0, "commits": 0, "writes": 0}; modal_calls = []
        def trace(statement):
            sql["statements"] += 1
            verb = statement.lstrip().split(" ", 1)[0].upper()
            if verb == "COMMIT": sql["commits"] += 1
            if verb in {"INSERT", "UPDATE", "DELETE"}: sql["writes"] += 1
        window.database._connection.set_trace_callback(trace)
        heartbeat_gaps = []; last_tick = time.monotonic()
        def tick():
            nonlocal last_tick
            now = time.monotonic(); heartbeat_gaps.append(now - last_tick); last_tick = now
        heartbeat = QTimer(); heartbeat.setInterval(5); heartbeat.timeout.connect(tick); heartbeat.start()

        def measure(name, operation):
            nonlocal last_tick
            before = dict(sql); heartbeat_gaps.clear(); last_tick = time.monotonic()
            cpu = time.process_time(); start = time.monotonic()
            profiler = cProfile.Profile() if profile and name == "pause-all" else None
            if profiler: profiler.enable()
            operation(); elapsed = time.monotonic() - start
            if profiler: profiler.disable()
            app.processEvents(); tick()
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            results.append({"operation": name, "wall_seconds": round(elapsed, 6),
                "cpu_seconds": round(time.process_time() - cpu, 6),
                "peak_rss_mib": round(rss / (1048576 if sys.platform == "darwin" else 1024), 2),
                "max_heartbeat_gap_seconds": round(max(heartbeat_gaps, default=0), 6),
                "native_threads": native_threads(), "active_tasks": window.task_manager.active_count,
                "progress_widgets": len(window.queue_table.findChildren(QProgressBar)),
                "sql": {key: sql[key] - before[key] for key in sql}})
            if profiler:
                report = io.StringIO()
                pstats.Stats(profiler, stream=report).strip_dirs().sort_stats("cumulative").print_stats(20)
                results[-1]["profile"] = report.getvalue()
            print(json.dumps({"items": count, "measurement": results[-1]}, sort_keys=True), file=sys.stderr, flush=True)

        def spin_idle():
            deadline = time.monotonic() + 5
            while window.task_manager.active_count and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.001)
            if window.task_manager.active_count: raise RuntimeError("Synthetic workers did not stop")

        items = [MediaItem(f"https://example.test/video/{i}", f"Synthetic video {i}", duration=60,
                           source="Synthetic", playlist_index=i + 1) for i in range(count)]
        options = DownloadOptions(download_dir=str(root / "downloads"), authentication_mode="None")
        def analyse():
            value = "https://example.test/playlist"
            window.input.setPlainText(value)
            window._analysis_ready({"items": items, "torrent": None,
                "context": AnalysisContext("scale-fixture", value, "preview", options)})
        def synthetic_download(job, proxy, settings, runtime, cancel, progress, tor):
            cancel.wait(5); job.status = JobStatus.PAUSED
            return job

        try:
            # Fail any accidental real network/Keychain operation in this probe.
            with patch("socket.create_connection", side_effect=AssertionError("No network in scale probe")), \
                 patch("morgan_media_downloader.youtube_companion.storage.KeychainSessionStore._operation",
                       side_effect=AssertionError("No Keychain in scale probe")), \
                 patch("morgan_media_downloader.ui._media_download_operation", synthetic_download):
                measure("analyse", analyse)
                measure("enqueue", lambda: window._enqueue_payload(items, None, options))
                if len(window.jobs) != count: raise AssertionError("Queue lost synthetic jobs")
                measure("start", window._dispatch)
                if len(window.active) != 2: raise AssertionError("Configured download bound not honored")
                snapshots = [copy.deepcopy(window.jobs[key]) for key in window.active]
                measure("progress-two-active", lambda: [window._job_changed(job) for job in snapshots])
                measure("pause-all", window.pause_all); spin_idle()
                measure("resume-all", window.resume_all)
                window.queue_table.selectAll()
                measure("cancel-selected", window.cancel_selected)
                measure("reload", lambda: window.database.load_jobs())
                restored = window.database.load_jobs()
                if len(restored) != count or any(job.status != JobStatus.CANCELLED for job in restored):
                    raise AssertionError("Cancelled state was not restored")
                window.queue_table.selectAll()
                def confirm(job): modal_calls.append(True); return "list"
                with patch.object(window, "_confirm_remove", confirm):
                    measure("remove-selected-keep-files", window.remove_selected)
                if window.jobs or window.database.load_jobs(): raise AssertionError("Removal did not complete")
                if window.task_manager.active_count: raise AssertionError("Probe leaked background tasks")
        finally:
            heartbeat.stop(); window.close(); app.processEvents()
        return {"items": count, "result": "passed", "platform": sys.platform, "measurements": results,
                "confirmation_requests": len(modal_calls), "scope": "Offscreen synthetic baseline, not live/network/native Cocoa qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=int, nargs="+", choices=[100, 800, 1000, 5000], default=[100, 800, 1000, 5000])
    parser.add_argument("--child", type=int, choices=[100, 800, 1000, 5000], help=argparse.SUPPRESS)
    parser.add_argument("--profile", action="store_true", help="Include pause-all's top20 cumulative profile; timings include profiler cost")
    args = parser.parse_args()
    if args.child:
        print(json.dumps(run_case(args.child, profile=args.profile), sort_keys=True), flush=True); return
    failed = False
    for count in args.items:
        try:
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", str(count)]
            if args.profile: command.append("--profile")
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
