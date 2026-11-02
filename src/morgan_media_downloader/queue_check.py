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


class DiagnosticBudget:
    """Two cumulative fixture budgets, never a larger queue-operation allowance.

    Additional collection work must not spend the original exercise's90seconds;
    neither may borrow from the other. Only explicit disposable diagnostics use it.
    """
    def __init__(self, *, clock=None):
        self._clock=clock or time.monotonic
        self._elapsed={"queue":0.,"collections":0.}; self._phase="queue"; self._started=self._clock()

    def _used(self,now): return self._elapsed[self._phase]+now-self._started

    def check(self):
        if self._used(self._clock())>=90: raise TimeoutError(f"Queue diagnostic {self._phase} deadline exceeded")

    def switch(self,phase):
        if phase not in self._elapsed: raise ValueError("Unknown diagnostic fixture")
        now=self._clock(); used=self._used(now)
        if used>=90: raise TimeoutError(f"Queue diagnostic {self._phase} deadline exceeded")
        self._elapsed[self._phase]=used; self._phase=phase; self._started=now

    def snapshot(self):
        self.check(); elapsed=dict(self._elapsed); elapsed[self._phase]=self._used(self._clock())
        return dict(limits_seconds={"queue":90,"collections":90},elapsed_seconds=elapsed)


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
    from .queue_model import JOB_ID_ROLE, PROGRESS_ROLE
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

    measurements = []; completed = []; prompts = []; restart_prompts = []; started = []; acknowledged = []; worker_errors = []
    restart_stats = dict(prepared=set(), processed=set(), max_slice=0, max_owned_workers=0, gui_cleanup_calls=0)
    attempts = dict(network=0, keychain=0, deletion=0, process=0)
    cleanup = dict(jobs=0, max_active_workers=0, max_slice=0, gui_thread_calls=0, heartbeat_ticks=0)
    import threading
    gui_thread = threading.get_ident(); max_owned = 0; budget=DiagnosticBudget()
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
        if _kind == "queue-restart":
            ids = window.queue_restart._ids
            restart_stats["max_slice"] = max(restart_stats["max_slice"], len(ids))
            restart_stats["max_owned_workers"] = max(restart_stats["max_owned_workers"], len(window.task_manager.active_ids(_kind)))
            connection = sqlite3.connect(window.database.path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT id,status FROM jobs WHERE id IN (" + ",".join("?" for _ in ids) + ")", ids).fetchall()
            finally: connection.close()
            if len(rows) != len(ids) or any(status != JobStatus.INTERRUPTED.value for _, status in rows):
                raise RuntimeError("Queue restart preparation was not committed")
            restart_stats["prepared"].update(key for key, _ in rows)
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
    def check_selection():
        begin = time.monotonic(); before = dict(sql); wanted = set(window.jobs)
        def require(condition):
            if not condition: raise RuntimeError("Queue selection diagnostic failed")
        def selected(): return {job.id for job in window._selected_jobs()}
        window.queue_selection_actions["all"].trigger()
        require(selected() == wanted)
        window.queue_status_filter.setCurrentText("Paused")
        require(window.queue_proxy.rowCount() == 0 and not selected())
        window.queue_selection_actions["none"].trigger()
        window.queue_status_filter.setCurrentText("Waiting")
        cleared = not selected() and not window._queue_selection_ids
        require(cleared)
        window.queue_search.setText("SYNTHETIC VIDEO")
        window.queue_selection_actions["filtered"].trigger(); filtered = len(selected())
        require(selected() == wanted)
        window.queue_selection_actions["status:Waiting"].trigger(); status = len(selected())
        require(selected() == wanted)
        application.processEvents()
        proxy = window.queue_proxy; viewport_height = window.queue_table.viewport().height()
        onscreen = set()
        for row in range(proxy.rowCount()):
            rectangle = window.queue_table.visualRect(proxy.index(row, 0))
            if rectangle.bottom() >= 0 and rectangle.top() < viewport_height:
                onscreen.add(proxy.index(row, 0).data(JOB_ID_ROLE))
        window.queue_selection_actions["visible"].trigger(); visible = len(selected())
        # Compare independent painted geometry, not another call to visible_rows.
        require(0 < visible <= count and selected() == onscreen)
        window.queue_selection_actions["all"].trigger(); all_count = len(selected())
        require(selected() == wanted and window.queue_filter.currentText() == "All" and
                window.queue_status_filter.currentText() == "All" and not window.queue_search.text())
        require(f"{count:,} selected" in window.queue_counts.text())
        window.queue_selection_actions["none"].trigger(); none = len(selected())
        require(none == 0 and not window._queue_selection_ids)
        window.queue_filter.setCurrentText("Media")
        require(sql == before and not window.task_manager.active_count)
        return dict(filtered=filtered, status=status, all=all_count, none=none, visible=visible,
            cleared_hidden=cleared, viewport_matched=True, sql_writes=0, sql_commits=0, sql_statements=0, owned_tasks=0,
            wall_seconds=round(time.monotonic()-begin, 6))
    def check_restart():
        nonlocal last_tick
        restart_stats.update(prepared=set(), processed=set(), max_slice=0, max_owned_workers=0, gui_cleanup_calls=0)
        membership={key:(job.collection_id,job.collection_name) for key,job in window.jobs.items()}
        window.queue_selection_actions["all"].trigger()
        initial_prompts = len(restart_prompts); before = dict(sql); gaps.clear(); last_tick = time.monotonic()
        cpu = time.process_time(); begin = time.monotonic()
        window.restart_selected(); spin_until(lambda: not window.queue_batch.busy)
        application.processEvents(); tick()
        committed = verified_reload(); info = window.queue_batch.describe()
        if (info["completed"] != count or info["failed"] or info["skipped"] or info["pending"] or
                len(restart_prompts)-initial_prompts != 1 or len(committed) != count or
                any(job.status != JobStatus.WAITING for job in committed) or
                any(not job.collection_id or (job.collection_id,job.collection_name)!=membership[job.id] for job in committed) or
                {job.id: job.to_dict() for job in committed} != {key: job.to_dict() for key, job in window.jobs.items()} or
                restart_stats["prepared"] != set(window.jobs) or restart_stats["processed"] != set(window.jobs) or
                restart_stats["max_owned_workers"] != 1 or not 0 < restart_stats["max_slice"] <= 32 or
                restart_stats["gui_cleanup_calls"] or window.task_manager.active_count or
                sql["writes"]-before["writes"] != 2*count or sql["commits"]-before["commits"] != 2*((count+31)//32)):
            raise RuntimeError("Queue restart diagnostic failed")
        result = dict(restarted=count, confirmation_requests=1, prepared_rows=len(restart_stats["prepared"]),
            committed_rows=len(committed), max_owned_workers=restart_stats["max_owned_workers"], max_slice=restart_stats["max_slice"],
            gui_cleanup_calls=restart_stats["gui_cleanup_calls"], worker_errors=info["failed"],
            membership_preserved=True,
            wall_seconds=round(time.monotonic()-begin, 6), cpu_seconds=round(time.process_time()-cpu, 6),
            max_heartbeat_gap_seconds=round(max(gaps, default=0), 6))
        window.queue_selection_actions["none"].trigger(); window.queue_filter.setCurrentText("Media")
        return result
    def check_collections(options):
        """Extra disposable admission after the original nine stages, not a
        substitute for their counts, workers, persistence or keep-removal gate.
        """
        from PySide6.QtCore import QPoint
        nonlocal last_tick
        begin=time.monotonic(); cpu=time.process_time(); gaps.clear(); last_tick=begin
        def require(condition):
            if not condition: raise RuntimeError("Queue collection diagnostic failed")
        items=[MediaItem(f"https://example.test/collections/video/{i}",f"Collection video{i}",
            original_url=f"https://example.test/collections/{i//(count//2)}",collection_title="Same synthetic title",
            collection_type="Playlist") for i in range(count)]
        window._enqueue_payload(items,None,options)
        values=list(window.jobs.values()); a=values[:count//2]; b=values[count//2:]
        a_ids={job.id for job in a}; b_ids={job.id for job in b}
        a_key=a[0].collection_id; b_key=b[0].collection_id
        require(len(values)==count and bool(a_key) and bool(b_key) and a_key!=b_key)
        require(all(job.collection_id==a_key for job in a) and all(job.collection_id==b_key for job in b))
        persisted=verified_reload()
        require({job.id:(job.collection_id,job.collection_name) for job in persisted}==
                {job.id:(job.collection_id,job.collection_name) for job in values})
        require(window.collections.model.rowCount()==3)
        untouched={job.id:job.to_dict() for job in b}
        def choose(key):
            row=window.collections.model.row_for_id(key); require(row is not None)
            window.collections.selector.setCurrentIndex(row); application.processEvents()
        choose(a_key); require(window.queue_proxy.rowCount()==count//2)
        rows=[]; scans=[]
        def changed(first,last,_roles): rows.append(last.row()-first.row()+1)
        original_sync=window.collections.model.index_state.sync
        def sync(*args,**kwargs): scans.append(True); return original_sync(*args,**kwargs)
        window.collections.model.dataChanged.connect(changed)
        try:
            with patch.object(window.collections.model.index_state,"sync",sync):
                value=copy.deepcopy(a[0]); value.progress=12.5; window._job_changed(value)
                window.queue_search.setText("NO MATCH"); window.queue_status_filter.setCurrentText("Completed")
        finally: window.collections.model.dataChanged.disconnect(changed)
        require(not scans and sum(rows)==2 and window.queue_proxy.rowCount()==0)
        require(window.collections.model.summary(a_key).progress==12.5/(count//2))
        action_prompts=[]; clear_prompts=[]; expected_clear=[]
        def action_confirm(action,jobs,scope):
            require(action in {"Pause","Resume","Cancel"} and {job.id for job in jobs}==a_ids and a_key[-6:] in scope)
            action_prompts.append(action); return True
        def clear_confirm(jobs,scope):
            require(bool(expected_clear) and {job.id for job in jobs}==expected_clear.pop(0) and "collection" in scope)
            clear_prompts.append(True); return "list"
        def trigger(menu,action):
            menu.popup(window.mapToGlobal(QPoint(200,200))); application.processEvents()
            require(menu.isVisible() and action.isEnabled()); action.trigger(); menu.hide()
            spin_until(lambda:not window.queue_batch.busy); application.processEvents()
        def intact():
            committed=verified_reload()
            require({job.id:job.to_dict() for job in committed if job.id in b_ids}==untouched)
        with patch.object(window,"_confirm_collection_action",action_confirm), patch.object(window,"_confirm_clear",clear_confirm):
            for action,status in (("Pause",JobStatus.PAUSED),("Resume",JobStatus.WAITING)):
                trigger(window.collections.actions_menu,window.collections.group_actions[action])
                require(all(job.status==status for job in verified_reload() if job.id in a_ids)); intact()
            completed=copy.deepcopy(window.jobs[a[0].id]); completed.status=JobStatus.COMPLETED_WARNINGS
            window._job_changed(completed)
            trigger(window.collections.actions_menu,window.collections.group_actions["Cancel"])
            require(window.jobs[a[0].id].status==JobStatus.COMPLETED_WARNINGS)
            require(all(window.jobs[key].status==JobStatus.CANCELLED for key in a_ids-{a[0].id})); intact()
            expected_clear.append({a[0].id})
            button=window.collections.clear_button
            require(button.isVisible() and button.isEnabled() and button.text()=="Clear Completed")
            button.click(); spin_until(lambda:not window.queue_batch.busy); application.processEvents()
            require(set(window.jobs)==(a_ids|b_ids)-{a[0].id}); intact()
            expected_clear.append(a_ids-{a[0].id})
            trigger(window.collections.clear_menu,window.collections.clear_actions["Cancelled"])
            require(set(window.jobs)==b_ids); intact()
            choose(b_key)
            failed=copy.deepcopy(window.jobs[b[0].id]); failed.status=JobStatus.FAILED; window._job_changed(failed)
            expected_clear.append({b[0].id})
            trigger(window.collections.clear_menu,window.collections.clear_actions["Failed"])
            require(set(window.jobs)==b_ids-{b[0].id})
            require({job.id for job in verified_reload()}==b_ids-{b[0].id})
            expected_clear.append(b_ids-{b[0].id})
            trigger(window.collections.clear_menu,window.collections.clear_actions["Collection"])
        require(not expected_clear and action_prompts==["Pause","Resume","Cancel"] and len(clear_prompts)==4)
        require(not window.jobs and not verified_reload() and not window.database.search_history() and
                not window.task_manager.active_count and window.collections.model.summary("").total==0)
        window.clear_queue_filters(); tick()
        return dict(admitted=count,groups=2,group_size=count//2,filtered_rows=count//2,hidden_rows=0,
            incremental_full_syncs=len(scans),incremental_summary_rows=sum(rows),action_confirmations=len(action_prompts),
            clear_confirmations=len(clear_prompts),completed_retained=1,cancelled=count//2-1,
            cleared_completed=1,cleared_cancelled=count//2-1,cleared_failed=1,cleared_collection=count//2-1,
            remaining=len(window.jobs),active_tasks=window.task_manager.active_count,other_group_unchanged=True,
            persisted_membership=True,primary_completed_clear=True,
            wall_seconds=round(time.monotonic()-begin,6),cpu_seconds=round(time.process_time()-cpu,6),
            max_heartbeat_gap_seconds=round(max(gaps,default=0),6))
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
            budget.check()
            application.processEvents(); time.sleep(.001)
        budget.check()
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
        budget.check()
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
    from . import ui, queue_restart
    original_restart_cleanup = queue_restart.delete_restart_state
    def empty_restart_cleanup(job, **kwargs):
        if any((job.final_files, job.partial_files, job.temporary_files, job.subtitle_files, job.thumbnail_files, job.output_file)):
            return forbidden("deletion")()
        restart_stats["gui_cleanup_calls"] += threading.get_ident() == gui_thread
        restart_stats["processed"].add(job.id)
        return original_restart_cleanup(job, **kwargs)  # Empty inventories: no filesystem paths are touched.
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
            stack.enter_context(patch.object(queue_restart, "delete_restart_state", empty_restart_cleanup))
            stack.enter_context(patch.object(ui, "_media_download_operation", synthetic_download))
            stack.enter_context(patch.object(window.file_removal, "deleter", fake_cleanup if synthetic_cleanup else forbidden("deletion")))
            stack.enter_context(patch.object(window.file_removal, "start", admit_cleanup))
            def confirm(_jobs): prompts.append(True); return "delete" if synthetic_cleanup else "list"
            stack.enter_context(patch.object(window, "_confirm_remove", confirm))
            def confirm_restart(_jobs): restart_prompts.append(True); return "keep"
            stack.enter_context(patch.object(window, "_confirm_restart", confirm_restart))
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
                selection_checks = check_selection()
                restart_checks = check_restart()
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
                budget.switch("collections")
                collection_checks=check_collections(options)
                budget.switch("queue")
                completed.append(dict(cycle=cycle, analysed=count, enqueued=count, started_workers=len(started)-initial_started,
                    acknowledged_workers=len(acknowledged)-initial_acknowledged, cancelled=count,
                    restored=len(restored), removed=count, remaining=0, active_tasks=0,
                    confirmation_requests=len(prompts)-initial_prompts, queue_rendered=True, selection_checks=selection_checks,
                    restart_checks=restart_checks,collection_checks=collection_checks))
            if max_owned > 2 or any(attempts.values()): raise RuntimeError("Queue diagnostic escaped its I/O/worker bounds")
    finally:
        heartbeat.stop(); heartbeat.deleteLater()
        window.database._connection.set_trace_callback(None)
        window.task_manager.task_started.disconnect(owned_started)
    return dict(schema=1, result="passed", items=count, platform=sys.platform, measurements=measurements, cycles=completed,
        confirmation_requests=len(prompts), max_owned_workers=max_owned, worker_errors=len(worker_errors),
        **{key+"_attempts": value for key, value in attempts.items()},
        cleanup_fixture=cleanup if synthetic_cleanup else None,timing_budgets=budget.snapshot(),
        scope="Isolated synthetic GUI/SQLite/owned-task exercise; no live accounts, network, media transfer, real file deletion or leak qualification")
