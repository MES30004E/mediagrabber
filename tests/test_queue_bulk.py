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
