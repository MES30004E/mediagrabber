"""P0 native queue contracts with synthetic jobs and no network/authentication."""
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
        assert not window.jobs and not window.database.load_jobs()
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
    monkeypatch.setattr("morgan_media_downloader.ui.delete_owned_files", lambda job: deleted.append(job.id))
    try:
        jobs(window, 800)
        active = list(window.jobs.values())[:2]
        for job in active: window.active[job.id] = "job-" + job.id
        window.remove_selected()
        assert len(window.jobs) == 2 and len(deleted) == 798 and len(cancelled) == 2
        assert all(job.id not in deleted for job in active)
        assert set(window.pending_removals) == {job.id for job in active}
        for job in active: window._job_finished("job-" + job.id)
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
        monkeypatch.setattr("morgan_media_downloader.ui.delete_owned_files", lambda job: removed.append(job))
        window.remove_selected()
        assert removed == [latest] and removed[0] is latest
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
