"""Explicit, disposable-state queue diagnostics shared by source/frozen probes.

Real GUI/SQLite/TaskManager paths; synthetic transfer only. Never a live download
or account diagnostic, and never called during ordinary startup.
"""
from __future__ import annotations

import copy
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import resource
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from unittest.mock import patch

SIZES = (100, 800, 1000, 5000)
# Fail closed if an owned thread cannot stop: do not restore real I/O targets
# underneath it. Only this explicit diagnostic subprocess can enter this state.
_retained_guards = []


def native_threads():
    if sys.platform == "linux": return len(list(Path("/proc/self/task").iterdir()))
    if sys.platform == "darwin":
        return max(0, len(subprocess.check_output(["/bin/ps", "-M", "-p", str(os.getpid())], text=True, timeout=2).splitlines())-1)
    return None


def current_rss_mib():
    if sys.platform == "darwin":
        return int(subprocess.check_output(["/bin/ps", "-o", "rss=", "-p", str(os.getpid())], text=True, timeout=2).strip()) / 1024
    if sys.platform == "linux":
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"): return int(line.split()[1]) / 1024
    return None


def exercise_queue(window, application, count: int, root: Path, *, cycles: int = 1,
                   profile: bool = False, synthetic_cleanup: bool = False,
                   on_measurement: Callable[[dict], None] | None = None) -> dict:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QProgressBar
    from .models import DownloadJob, DownloadOptions, JobStatus, MediaItem
    from .queue_model import PROGRESS_ROLE
    from .ui import AnalysisContext

    if type(count) is not int or count not in SIZES or type(cycles) is not int or cycles not in (1, 2):
        raise ValueError("Queue diagnostic requires a supported size and1–2cycles")
    root = root.resolve(strict=True)
    settings = window.settings
    if (settings.authentication_mode != "None" or settings.cookies_file or settings.browser_profile or
            settings.proxy_username or settings.connection_mode != "Direct / Normal Network" or settings.concurrent_downloads != 2):
        raise ValueError("Queue diagnostic requires anonymous direct settings and two workers")
    paths = (window.database.path, settings.download_dir, settings.torrent_download_dir, settings.converter_output_dir)
    if any(not path or not Path(path).resolve().is_relative_to(root) for path in paths):
        raise ValueError("Queue diagnostic paths must remain in disposable root")
    if window.jobs or window.active or window.task_manager.active_count or window.queue_batch.busy or window.database.search_history():
        raise ValueError("Queue diagnostic refuses populated state")

    measurements = []; completed = []; prompts = []; started = []; acknowledged = []; worker_errors = []
    attempts = dict(network=0, keychain=0, deletion=0, process=0)
    cleanup = dict(jobs=0, max_active_workers=0, max_slice=0, gui_thread_calls=0, heartbeat_ticks=0)
    import threading
    gui_thread = threading.get_ident(); max_owned = 0; deadline = time.monotonic() + 90
    sql = dict(statements=0, commits=0, writes=0)
    def trace(statement):
        sql["statements"] += 1; verb = statement.lstrip().split(" ", 1)[0].upper()
        if verb == "COMMIT": sql["commits"] += 1
        if verb in {"INSERT", "UPDATE", "DELETE"}: sql["writes"] += 1
    def forbidden(kind):
        def refuse(*_args, **_kwargs):
            attempts[kind] += 1
            raise RuntimeError(f"Queue diagnostic refused {kind} I/O")
        return refuse
    original_popen = subprocess.Popen
    allowed_processes = (["/bin/ps", "-M", "-p", str(os.getpid())], ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())])
    def guarded_popen(command, *args, **kwargs):
        if command not in allowed_processes or kwargs.get("shell") or kwargs.get("executable"):
            return forbidden("process")()
        return original_popen(command, *args, **kwargs)
    def owned_started(_task_id, _kind):
        nonlocal max_owned
        max_owned = max(max_owned, window.task_manager.active_count)
        if _kind == "queue-file-removal":
            cleanup["max_active_workers"] = max(cleanup["max_active_workers"], len(window.task_manager.active_ids(_kind)))
    def synthetic_download(job, proxy, captured, runtime, cancel, progress, tor):
        try:
            if job.options.authentication_mode != "None" or proxy is not None or tor is not None:
                raise RuntimeError("Synthetic transfer was given authentication or a network route")
            started.append(job.id)
            if not cancel.wait(30) or not cancel.is_set(): raise RuntimeError("Synthetic worker did not receive stop")
            job.status = JobStatus.PAUSED
            acknowledged.append(job.id)
            return job
        except BaseException:
            worker_errors.append(job.id)
            raise
    def committed_jobs():
        # A second read-only connection cannot see the writer's uncommitted
        # transaction. Do not mistake a same-connection read for persistence.
        connection = sqlite3.connect(window.database.path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return [DownloadJob.from_dict(json.loads(row[0])) for row in connection.execute("SELECT payload FROM jobs")]
        finally: connection.close()
    def verified_reload():
        loaded = window.database.load_jobs(); committed = committed_jobs()
        if {job.id: job.to_dict() for job in loaded} != {job.id: job.to_dict() for job in committed}:
            raise RuntimeError("Queue diagnostic persistence was not committed")
        return committed
    def fake_cleanup(_job):
        cleanup["gui_thread_calls"] += threading.get_ident() == gui_thread
        time.sleep(.001); cleanup["jobs"] += 1
        return []
    original_cleanup_start = window.file_removal.start
    def admit_cleanup(jobs):
        cleanup["max_slice"] = max(cleanup["max_slice"], len(jobs))
        return original_cleanup_start(jobs)
    gaps = []; last_tick = time.monotonic()
    def tick():
        nonlocal last_tick
        now = time.monotonic(); gaps.append(now-last_tick); last_tick = now
        if window.file_removal.busy: cleanup["heartbeat_ticks"] += 1
    heartbeat = QTimer(window); heartbeat.setInterval(5); heartbeat.timeout.connect(tick)
    def spin_until(predicate, fail_when=None):
        while not predicate():
            if fail_when is not None and fail_when(): raise RuntimeError("Synthetic workers did not start")
            if time.monotonic() >= deadline: raise TimeoutError("Queue diagnostic deadline exceeded")
            application.processEvents(); time.sleep(.001)
    def drain_before_restore(stack):
        stopped = window.task_manager.shutdown(10_000)
        stop_deadline = time.monotonic() + 1
        while stopped and window.task_manager.active_count and time.monotonic() < stop_deadline:
            application.processEvents()
        if not stopped or window.task_manager.active_count:
            _retained_guards.append(stack.pop_all())
            raise RuntimeError("Synthetic workers did not stop; I/O guards retained")
    def measure(cycle, name, operation):
        nonlocal last_tick
        if time.monotonic() >= deadline: raise TimeoutError("Queue diagnostic deadline exceeded")
        before = dict(sql); gaps.clear(); last_tick = time.monotonic()
        cpu = time.process_time(); begin = time.monotonic()
        profiler = cProfile.Profile() if profile and name == "pause-all" else None
        if profiler: profiler.enable()
        operation(); spin_until(lambda: not window.queue_batch.busy)
        elapsed = time.monotonic()-begin
        if profiler: profiler.disable()
        application.processEvents(); tick()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result = dict(cycle=cycle, operation=name, wall_seconds=round(elapsed, 6), cpu_seconds=round(time.process_time()-cpu, 6),
            peak_rss_mib=round(rss/(1048576 if sys.platform == "darwin" else 1024), 2), current_rss_mib=current_rss_mib(),
            max_heartbeat_gap_seconds=round(max(gaps, default=0), 6), native_threads=native_threads(),
            active_tasks=window.task_manager.active_count, progress_widgets=len(window.queue_table.findChildren(QProgressBar)),
            sql={key: sql[key]-before[key] for key in sql})
        if profiler:
            stream = io.StringIO(); pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(20)
            result["profile"] = stream.getvalue()
        measurements.append(result)
        if on_measurement is not None: on_measurement(dict(result))

    from contextlib import ExitStack
    from . import ui
    from .youtube_companion.storage import KeychainSessionStore
    window.database._connection.set_trace_callback(trace)
    window.task_manager.task_started.connect(owned_started); heartbeat.start()
    try:
        with ExitStack() as stack:
            for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo"):
                stack.enter_context(patch(target, side_effect=forbidden("network")))
            stack.enter_context(patch.object(KeychainSessionStore, "_operation", side_effect=forbidden("keychain")))
            stack.enter_context(patch("subprocess.Popen", guarded_popen))
            stack.enter_context(patch.object(ui, "delete_owned_files", side_effect=forbidden("deletion")))
            stack.enter_context(patch.object(ui, "delete_restart_state", side_effect=forbidden("deletion")))
            stack.enter_context(patch.object(ui, "_media_download_operation", synthetic_download))
            stack.enter_context(patch.object(window.file_removal, "deleter", fake_cleanup if synthetic_cleanup else forbidden("deletion")))
            stack.enter_context(patch.object(window.file_removal, "start", admit_cleanup))
            def confirm(_jobs): prompts.append(True); return "delete" if synthetic_cleanup else "list"
            stack.enter_context(patch.object(window, "_confirm_remove", confirm))
            # ExitStack unwinds LIFO: drain owned work before any I/O target or
            # global transfer callback can be restored, including on exceptions.
            stack.callback(drain_before_restore, stack)
            for cycle in range(1, cycles+1):
                initial_prompts = len(prompts); initial_started = len(started); initial_acknowledged = len(acknowledged)
                items = [MediaItem(f"https://example.test/video/{i}", f"Synthetic video{i}", duration=60,
                    source="Synthetic", playlist_index=i+1) for i in range(count)]
                options = DownloadOptions(download_dir=str(root / "downloads"), authentication_mode="None")
                def analyse():
                    value = "https://example.test/playlist"; window.input.setPlainText(value)
                    window._analysis_ready(dict(items=items, torrent=None, context=AnalysisContext("scale-fixture", value, "preview", options)))
                measure(cycle, "analyse", analyse)
                if len(window.items) != count: raise RuntimeError("Queue diagnostic lost analysis items")
                measure(cycle, "enqueue", lambda: window._enqueue_payload(items, None, options))
                if len(window.jobs) != count: raise RuntimeError("Queue diagnostic lost admitted jobs")
                measure(cycle, "start", window._dispatch)
                spin_until(lambda: len(started)-initial_started == 2,
                    fail_when=lambda: not window.task_manager.active_count)
                if len(window.active) != 2: raise RuntimeError("Queue diagnostic worker bound changed")
                snapshots = [copy.deepcopy(window.jobs[key]) for key in window.active]
                for job in snapshots: job.progress = 37.5; job.downloaded_bytes = 1536; job.total_bytes = 4096
                measure(cycle, "progress-two-active", lambda: [window._job_changed(job) for job in snapshots])
                frame = window.queue_table.viewport().grab()
                progress_column = window.queue_model.columns.index("Progress")
                if frame.isNull() or any(window.queue_table.model().index(row, progress_column).data(PROGRESS_ROLE) != 37.5 for row in range(2)):
                    raise RuntimeError("Queue progress did not render")
                measure(cycle, "pause-all", window.pause_all); spin_until(lambda: not window.task_manager.active_count)
                if worker_errors or sorted(acknowledged[initial_acknowledged:]) != sorted(started[initial_started:]):
                    raise RuntimeError("Queue diagnostic cancellation was not acknowledged by both workers")
                measure(cycle, "resume-all", window.resume_all)
                window.queue_table.selectAll(); measure(cycle, "cancel-selected", window.cancel_selected)
                restored = []
                measure(cycle, "reload", lambda: restored.extend(verified_reload()))
                if len(restored) != count or any(job.status != JobStatus.CANCELLED for job in restored):
                    raise RuntimeError("Queue cancellation was not persisted")
                window.queue_table.selectAll()
                name = "remove-selected-synthetic-cleanup" if synthetic_cleanup else "remove-selected-keep-files"
                measure(cycle, name, window.remove_selected)
                if window.jobs or window.database.search_history() or committed_jobs() or window.active or window.task_manager.active_count:
                    raise RuntimeError("Queue diagnostic retained jobs or workers")
                completed.append(dict(cycle=cycle, analysed=count, enqueued=count, started_workers=len(started)-initial_started,
                    acknowledged_workers=len(acknowledged)-initial_acknowledged, cancelled=count,
                    restored=len(restored), removed=count, remaining=0, active_tasks=0,
                    confirmation_requests=len(prompts)-initial_prompts, queue_rendered=True))
            if max_owned > 2 or any(attempts.values()): raise RuntimeError("Queue diagnostic escaped its I/O/worker bounds")
    finally:
        heartbeat.stop(); heartbeat.deleteLater()
        window.database._connection.set_trace_callback(None)
        window.task_manager.task_started.disconnect(owned_started)
    return dict(schema=1, result="passed", items=count, platform=sys.platform, measurements=measurements, cycles=completed,
        confirmation_requests=len(prompts), max_owned_workers=max_owned, worker_errors=len(worker_errors),
        **{key+"_attempts": value for key, value in attempts.items()},
        cleanup_fixture=cleanup if synthetic_cleanup else None,
        scope="Isolated synthetic GUI/SQLite/owned-task exercise; no live accounts, network, media transfer, real file deletion or leak qualification")
