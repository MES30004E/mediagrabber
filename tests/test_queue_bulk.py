"""P0 native queue contracts with synthetic jobs and no network/authentication."""
import pytest
from PySide6.QtWidgets import QHeaderView, QMessageBox

from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from test_ui_diagnostics import _window, _APP


def jobs(window, count):
    window.jobs = {job.id: job for job in [DownloadJob(MediaItem(f"https://example.test/{i}", f"Synthetic {i}"),
                   DownloadOptions(authentication_mode="None")) for i in range(count)]}
    window._refresh_queue(); window.queue_table.selectAll()


def test_removing_eight_hundred_jobs_asks_once_and_keeps_files_by_default(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); prompts = []
    def confirm(value): prompts.append(value); return "list"
    monkeypatch.setattr(window, "_confirm_remove", confirm)
    monkeypatch.setattr("morgan_media_downloader.ui.delete_owned_files", lambda *_: (_ for _ in ()).throw(AssertionError("Keep must never delete")))
    try:
        jobs(window, 800)
        window.remove_selected()
        assert len(prompts) == 1
        assert len(window.jobs) == 800, "Large removal must yield before work"
        from test_queue_batch import drain
        drain(window.queue_batch)
        assert not window.jobs and not window.database.load_jobs()
    finally: window.close(); _APP.processEvents()


def test_large_keep_removal_waits_for_active_task_and_batches_inactive_deletes(tmp_path, monkeypatch):
    import time
    window = _window(tmp_path, monkeypatch); commits = []; stopped = []
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "list")
    monkeypatch.setattr(window.task_manager, "cancel", lambda key: stopped.append(key) or True)
    try:
        jobs(window, 800); window.database.save_jobs(window.jobs.values())
        active = next(iter(window.jobs)); window.active[active] = "job-" + active
        window.database._connection.set_trace_callback(lambda sql: commits.append(sql) if sql == "COMMIT" else None)
        window.remove_selected()
        deadline = time.monotonic() + 5
        while len(window.jobs) > 1 and time.monotonic() < deadline: _APP.processEvents()
        assert set(window.jobs) == {active} and window.queue_batch.busy
        assert window.queue_batch.describe()["completed"] == 799
        assert window.queue_batch.describe()["pending"] == 1
        assert len(commits) == 25 and stopped == ["job-" + active]
        window._job_finished("job-" + active)
        assert not window.queue_batch.busy and not window.jobs
        assert window.queue_batch.describe()["completed"] == 800
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


@pytest.mark.parametrize("empty_message", [False, True])
def test_deferred_removal_database_failure_retains_entry_and_recovers_stopped_state(tmp_path, monkeypatch, empty_message):
    import time
    window = _window(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "list")
    monkeypatch.setattr(window.task_manager, "cancel", lambda _: True)
    try:
        jobs(window, 800); active = next(iter(window.jobs))
        window.jobs[active].status = JobStatus.DOWNLOADING
        window.database.save_jobs(window.jobs.values())
        window.active[active] = "job-" + active
        window.remove_selected()
        deadline = time.monotonic() + 5
        while len(window.jobs) > 1 and time.monotonic() < deadline: _APP.processEvents()
        window.database._connection.execute("CREATE TRIGGER reject_removal BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT,'synthetic delete failure'); END")
        if empty_message:
            def reject(_): raise OSError()
            monkeypatch.setattr(window.database, "remove_job", reject)
        window._job_finished("job-" + active)
        assert set(window.jobs) == {active} and not window.active and not window.queue_batch.busy
        assert window.queue_batch.describe()["failed"] == 1
        assert window.queue_batch.describe()["completed"] == 799
        assert window.jobs[active].status == JobStatus.INTERRUPTED
        assert len(window.database.load_jobs()) == 1
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


@pytest.mark.parametrize("pending_restart", [False, True])
def test_large_keep_removal_drains_real_owned_task_threads_before_reporting_complete(tmp_path, monkeypatch, pending_restart):
    import time
    from PySide6.QtCore import QTimer
    window = _window(tmp_path, monkeypatch); prompts = []; deleted_restart_data = []
    monkeypatch.setattr(window, "_confirm_remove", lambda selected: prompts.append(len(selected)) or "list")
    def held(job, proxy, settings, runtime, cancel, progress, tor):
        assert cancel.wait(5), "Synthetic worker must receive cancellation"
        job.status = JobStatus.PAUSED
        return job
    monkeypatch.setattr("morgan_media_downloader.ui._media_download_operation", held)
    monkeypatch.setattr("morgan_media_downloader.ui.delete_restart_state", lambda *_, **__: deleted_restart_data.append(True))
    try:
        for timer in window.findChildren(QTimer): timer.stop()
        jobs(window, 800); window.database.save_jobs(window.jobs.values())
        window.settings.concurrent_downloads = 2
        window._dispatch(); assert len(window.active) == 2
        if pending_restart: window.pending_restarts[next(iter(window.active))] = "restart"
        window.remove_selected()
        deadline = time.monotonic() + 8
        while (window.queue_batch.busy or window.task_manager.active_count) and time.monotonic() < deadline:
            _APP.processEvents(); time.sleep(.001)
        assert prompts == [800] and not window.queue_batch.busy
        assert not window.active and window.task_manager.active_count == 0
        assert not window.jobs and not window.database.load_jobs()
        assert window.queue_batch.describe()["completed"] == 800
        assert window.queue_batch.describe()["pending"] == 0
        assert not deleted_restart_data and not window.pending_restarts
    finally: window.close(); _APP.processEvents()


def test_bulk_cancel_choice_leaves_every_selected_job_unchanged(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_confirm_remove", lambda *_: "cancel")
    try:
        jobs(window, 800); before = set(window.jobs)
        window.remove_selected()
        assert set(window.jobs) == before and not window.pending_removals
    finally: window.close(); _APP.processEvents()


def test_queue_status_updates_do_not_autosize_columns_for_every_changed_cell(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); eager_resizes = []
    try:
        jobs(window, 100)
        header = window.queue_table.horizontalHeader()
        window.queue_table.model().dataChanged.connect(lambda *_: eager_resizes.append(
            any(header.sectionResizeMode(i) == QHeaderView.ResizeMode.ResizeToContents for i in range(header.count()))))
        window.pause_all()
        from test_queue_batch import drain
        drain(window.queue_batch)
        assert eager_resizes, "Real status cells must be changed"
        assert not any(eager_resizes), "Auto-content resizing per cell creates quadratic synchronous refresh work"
        assert all(job.status == JobStatus.PAUSED for job in window.jobs.values())
    finally: window.close(); _APP.processEvents()


def test_single_bulk_dialog_uses_keep_default_and_actual_status_counts(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); prompts = []
    def accept_default(box):
        prompts.append(box.text())
        assert box.defaultButton() is not None
        assert "keep files" in box.defaultButton().text().lower()
        box.defaultButton().click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", accept_default)
    try:
        jobs(window, 800)
        selected = list(window.jobs.values())
        selected[0].status = JobStatus.COMPLETED; selected[1].status = JobStatus.COMPLETED_WARNINGS
        window.active[selected[2].id] = "synthetic-task"
        assert window._confirm_remove(selected) == "list"
        assert len(prompts) == 1 and "800 selected" in prompts[0] and "1 active; 2 completed" in prompts[0]
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


def test_bulk_removal_waits_for_active_worker_before_optional_owned_file_deletion(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); deleted = []; cancelled = []
    monkeypatch.setattr(window, "_confirm_remove", lambda *_: "delete")
    monkeypatch.setattr(window.task_manager, "cancel", lambda task_id: cancelled.append(task_id) or True)
    window.file_removal.deleter = lambda job: deleted.append(job.id) or []
    try:
        jobs(window, 800)
        active = list(window.jobs.values())[:2]
        for job in active: window.active[job.id] = "job-" + job.id
        window.remove_selected()
        assert len(window.jobs) == 800 and not deleted
        from test_queue_batch import drain
        # First cleanup slice must wait for both actual download owners.
        _APP.processEvents()
        assert len(cancelled) == 2 and not deleted
        assert all(job.id not in deleted for job in active)
        assert set(window.pending_removals) == {job.id for job in active}
        for job in active: window._job_finished("job-" + job.id)
        drain(window.queue_batch)
        assert len(deleted) == 800 and not window.jobs and not window.pending_removals
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


def test_confirmation_snapshot_resolves_latest_job_inventory_after_modal_event_delivery(tmp_path, monkeypatch):
    import copy
    window = _window(tmp_path, monkeypatch); removed = []
    try:
        jobs(window, 1)
        original = next(iter(window.jobs.values()))
        latest = copy.deepcopy(original)
        latest.final_files = [str(tmp_path / "new-final-output")]
        def confirm(_):
            # An actual modal event loop can deliver a finished worker/result.
            window.jobs[original.id] = latest
            return "delete"
        monkeypatch.setattr(window, "_confirm_remove", confirm)
        window.file_removal.deleter = lambda job: removed.append(job) or []
        window.remove_selected()
        from test_queue_batch import drain
        drain(window.queue_batch)
        assert len(removed) == 1 and removed[0].id == latest.id
        assert removed[0].final_files == latest.final_files
    finally: window.close(); _APP.processEvents()


def test_enqueue_eight_hundred_jobs_commits_once_before_publishing_queue(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); statements = []
    try:
        window.database._connection.set_trace_callback(statements.append)
        items = [MediaItem(f"https://example.test/{i}", str(i)) for i in range(800)]
        window._enqueue_payload(items, None, DownloadOptions(authentication_mode="None", download_dir=str(tmp_path)))
        assert len(window.jobs) == len(window.database.load_jobs()) == 800
        assert statements.count("COMMIT") == 1
    finally: window.close(); _APP.processEvents()


def test_enqueue_database_failure_never_publishes_partial_jobs(tmp_path, monkeypatch):
    import pytest
    window = _window(tmp_path, monkeypatch)
    def reject(_): raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(window.database, "save_jobs", reject)
    try:
        with pytest.raises(OSError):
            window._enqueue_payload([MediaItem("https://example.test/1", "Synthetic")], None,
                DownloadOptions(authentication_mode="None", download_dir=str(tmp_path)))
        assert not window.jobs and window.database.load_jobs() == []
    finally: window.close(); _APP.processEvents()


def test_large_cancel_yields_and_persists_bounded_batches(tmp_path, monkeypatch):
    import time
    window = _window(tmp_path, monkeypatch); commits = []
    try:
        jobs(window, 800)
        window.database._connection.set_trace_callback(lambda sql: commits.append(sql) if sql == "COMMIT" else None)
        window.cancel_selected()
        assert all(job.status == JobStatus.WAITING for job in window.jobs.values()), "Large action must not run synchronously"
        deadline = time.monotonic() + 5
        while window.queue_batch.busy and time.monotonic() < deadline: _APP.processEvents()
        assert not window.queue_batch.busy
        assert all(job.status == JobStatus.CANCELLED for job in window.jobs.values())
        assert len(commits) == 25 and len(window.database.load_jobs()) == 800
    finally: window.close(); _APP.processEvents()


def test_stop_large_action_before_first_slice_leaves_jobs_and_workers_unchanged(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); cancellations = []
    monkeypatch.setattr(window.task_manager, "cancel", lambda key: cancellations.append(key))
    try:
        jobs(window, 800)
        window.cancel_selected()
        window._dispatch()  # Dispatch must not start waiting jobs during a batch.
        assert not window.active
        window.stop_queue_batch.click()
        assert not window.queue_batch.busy and window.queue_batch.describe()["pending"] == 800
        assert all(job.status == JobStatus.WAITING for job in window.jobs.values()) and not cancellations
    finally: window.close(); _APP.processEvents()


def test_failed_slice_preserves_live_state_and_does_not_cancel_workers(tmp_path, monkeypatch):
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch); cancellations = []
    try:
        jobs(window, 800); ids = list(window.jobs)
        window.database.save_jobs(window.jobs.values())
        window.active[ids[0]] = "synthetic-active"
        original = window.database.save_jobs; calls = []
        def reject_first(values):
            calls.append(True)
            if len(calls) == 1: raise OSError("synthetic persistence failure")
            return original(values)
        monkeypatch.setattr(window.database, "save_jobs", reject_first)
        monkeypatch.setattr(window.task_manager, "cancel", lambda key: cancellations.append(key))
        window.cancel_selected(); drain(window.queue_batch)
        assert window.queue_batch.describe()["failed"] == 32
        assert window.queue_batch.describe()["completed"] == 768
        assert not cancellations
        assert all(window.jobs[key].status == JobStatus.WAITING for key in ids[:32])
        persisted = {job.id: job.status for job in window.database.load_jobs()}
        assert all(persisted[key] == window.jobs[key].status for key in ids)
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


def test_destructive_queue_actions_cannot_interleave_with_pending_batch(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); effects = []
    monkeypatch.setattr(window, "_confirm_restart", lambda _: effects.append("restart") or "restart")
    monkeypatch.setattr(window, "_confirm_remove", lambda _: effects.append("remove") or "list")
    monkeypatch.setattr(window.database, "clear_completed", lambda: effects.append("clear"))
    try:
        jobs(window, 800); before = set(window.jobs)
        window.cancel_selected()
        window.restart_selected(); window.remove_selected(); window.clear_completed()
        assert not effects and set(window.jobs) == before
    finally: window.close(); _APP.processEvents()


def test_large_retry_captures_applied_authentication_without_replacing_quality(tmp_path, monkeypatch):
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch)
    try:
        jobs(window, 800)
        for job in window.jobs.values():
            job.status = JobStatus.FAILED; job.failure_code = "auth.required"
            job.options.quality = "720p"
        window.settings.authentication_mode = "Browser Cookies"
        window.settings.cookies_browser = "Firefox"
        window.settings.browser_profile = "synthetic-applied-profile"
        window.resume_selected()
        # Later unrelated settings edits must not change an admitted batch.
        window.settings.authentication_mode = "None"
        window.settings.browser_profile = "synthetic-later-profile"
        drain(window.queue_batch)
        for job in window.jobs.values():
            assert job.status == JobStatus.WAITING
            assert job.options.authentication_mode == "Browser Cookies"
            assert job.options.browser_profile == "synthetic-applied-profile"
            assert job.options.quality == "720p"
        assert len(window.database.load_jobs()) == 800
    finally: window.close(); _APP.processEvents()


def test_explicit_cleanup_deletes_only_temporary_owned_fixture_on_worker(tmp_path, monkeypatch):
    import threading
    from morgan_media_downloader.file_ownership import delete_owned_files
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch); threads = []; main = threading.get_ident()
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "delete")
    try:
        jobs(window, 1); job = next(iter(window.jobs.values()))
        owned = tmp_path / "owned.fixture"; owned.write_bytes(b"synthetic")
        foreign = tmp_path / "unrelated.fixture"; foreign.write_bytes(b"must remain")
        job.options.download_dir = str(tmp_path); job.final_files = [str(owned)]
        def cleanup(snapshot):
            threads.append(threading.get_ident())
            return delete_owned_files(snapshot, use_trash=False)
        window.file_removal.deleter = cleanup
        window.remove_selected(); drain(window.queue_batch)
        assert not owned.exists() and foreign.read_bytes() == b"must remain"
        assert threads and all(value != main for value in threads)
        assert not window.jobs and not window.file_removal.busy
    finally: window.close(); _APP.processEvents()


def test_stop_during_cleanup_finishes_one_slice_and_preserves_unprocessed_entries(tmp_path, monkeypatch):
    import threading
    import time
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch); entered = threading.Event(); release = threading.Event(); seen = []
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "delete")
    def cleanup(snapshot):
        entered.set(); assert release.wait(5)
        seen.append(snapshot.id); return []
    window.file_removal.deleter = cleanup
    try:
        jobs(window, 800); window.database.save_jobs(window.jobs.values())
        window.remove_selected()
        deadline = time.monotonic() + 5
        while not entered.is_set() and time.monotonic() < deadline: _APP.processEvents()
        assert entered.is_set() and len(window.task_manager.active_ids("queue-file-removal")) == 1
        window.stop_queue_batch.click()
        assert "Stopped" in window.statusBar().currentMessage()
        release.set(); drain(window.queue_batch)
        assert len(seen) == 32 and len(window.jobs) == 768
        assert window.queue_batch.describe()["pending"] == 768 and window.queue_batch.describe()["cancelled"]
    finally:
        release.set(); window.close(); _APP.processEvents()


def test_database_failure_after_cleanup_retains_entry_and_reports_partial_side_effects(tmp_path, monkeypatch):
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "delete")
    try:
        jobs(window, 1); window.database.save_jobs(window.jobs.values())
        window.file_removal.deleter = lambda _: ["synthetic moved path"]
        def reject(_): raise OSError()
        monkeypatch.setattr(window.database, "remove_jobs", reject)
        window.remove_selected(); drain(window.queue_batch)
        assert len(window.jobs) == len(window.database.load_jobs()) == 1
        assert window.queue_batch.describe()["failed"] == 1 and window.queue_batch.describe()["completed"] == 0
        assert "files may already have moved" in window.queue_batch.describe()["error"]
    finally: window.close(); _APP.processEvents()


def test_cleanup_worker_admission_failure_after_download_stop_is_settled(tmp_path, monkeypatch):
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "delete")
    monkeypatch.setattr(window.task_manager, "cancel", lambda _: True)
    def reject(_): raise RuntimeError("synthetic worker admission failure")
    monkeypatch.setattr(window.file_removal, "start", reject)
    try:
        jobs(window, 800); active = next(iter(window.jobs)); window.active[active] = "job-" + active
        window.remove_selected(); _APP.processEvents()
        window._job_finished("job-" + active)
        drain(window.queue_batch)
        assert window.queue_batch.describe()["failed"] == 800 and len(window.jobs) == 800
        assert not window.pending_removals and not window._delete_slice_ids
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


def test_close_during_cleanup_retains_interruption_evidence_without_late_queue_deletion(tmp_path, monkeypatch):
    import threading
    import time
    from morgan_media_downloader.database import Database
    window = _window(tmp_path, monkeypatch); entered = threading.Event(); release = threading.Event()
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "delete")
    def cleanup(_): entered.set(); assert release.wait(5); return []
    window.file_removal.deleter = cleanup
    try:
        jobs(window, 1); window.database.save_jobs(window.jobs.values())
        path = window.database.path
        window.remove_selected()
        deadline = time.monotonic() + 5
        while not entered.is_set() and time.monotonic() < deadline: _APP.processEvents()
        assert entered.is_set()
        timer = threading.Timer(.03, release.set); timer.start()
        assert window.close(); timer.join(); _APP.processEvents()
        assert window.task_manager.active_count == 0 and not window.file_removal.busy
        restarted = Database(path)
        try:
            restored = restarted.load_jobs()
            assert len(restored) == 1
            assert "Cleanup interrupted" in restored[0].technical_details
            assert "files may already have moved" in restored[0].technical_details
        finally: restarted.close()
    finally:
        release.set(); window.close(); _APP.processEvents()


def test_shutdown_wait_cannot_admit_another_destructive_queue_action(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); prompts = []
    monkeypatch.setattr(window, "_confirm_remove", lambda _: prompts.append(True) or "delete")
    try:
        jobs(window, 1)
        window._closing = True  # Close may remain pending while a blocked disk operation finishes.
        window.remove_selected()
        assert not prompts and not window.queue_batch.busy and not window.file_removal.busy
    finally:
        window._closing = False; window.close(); _APP.processEvents()


@pytest.mark.parametrize("choice", ["list", "delete"])
def test_confirmed_removal_supersedes_restart_before_later_slice_is_admitted(tmp_path, monkeypatch, choice):
    from test_queue_batch import drain
    window = _window(tmp_path, monkeypatch); restart_deletions = []
    monkeypatch.setattr(window, "_confirm_remove", lambda _: choice)
    monkeypatch.setattr("morgan_media_downloader.ui.delete_restart_state",
        lambda *_, **__: restart_deletions.append(True))
    window.file_removal.deleter = lambda _: []
    try:
        jobs(window, 800)
        late = list(window.jobs)[100]
        window.active[late] = "job-" + late
        window.pending_restarts[late] = "restart"
        window.remove_selected()
        # The owner finishes before even the first QTimer slice is admitted.
        window._job_finished("job-" + late)
        assert not restart_deletions and late not in window.pending_restarts
        drain(window.queue_batch)
        assert not window.jobs and window.queue_batch.describe()["completed"] == 800
    finally:
        window.active.clear(); window.close(); _APP.processEvents()


def test_shutdown_marker_persistence_failure_still_drains_worker_and_keeps_unclean_marker(tmp_path, monkeypatch):
    import threading
    import time
    from PySide6.QtGui import QCloseEvent
    window = _window(tmp_path, monkeypatch); entered = threading.Event(); release = threading.Event()
    monkeypatch.setattr(window, "_confirm_remove", lambda _: "delete")
    def cleanup(_): entered.set(); assert release.wait(5); return []
    window.file_removal.deleter = cleanup
    try:
        jobs(window, 1); window.database.save_jobs(window.jobs.values())
        window.remove_selected()
        deadline = time.monotonic() + 5
        while not entered.is_set() and time.monotonic() < deadline: _APP.processEvents()
        assert entered.is_set()
        def reject(_): raise OSError("synthetic marker persistence failure")
        monkeypatch.setattr(window.database, "save_jobs", reject)
        timer = threading.Timer(.03, release.set); timer.start()
        error = None; event = QCloseEvent()
        try: window.closeEvent(event)
        except OSError as caught: error = caught
        finally: timer.join()
        _APP.processEvents()  # Deliver queued thread-finished ownership notifications.
        assert error is None, "Marker failure must not escape before owned worker shutdown"
        assert event.isAccepted() and window.task_manager.active_count == 0 and not window.file_removal.busy
        assert window.clean_marker.exists(), "Failed persistence must remain visible at next startup"
    finally:
        release.set(); window.close(); _APP.processEvents()
