import copy

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from test_ui_diagnostics import _window

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch):
    value = _window(tmp_path, monkeypatch)
    for timer in value.findChildren(QTimer): timer.stop()
    try: yield value
    finally: value.close(); APP.processEvents()


def jobs_in(window):
    jobs = [DownloadJob(MediaItem(f"https://example.test/source/{i}", f"Video {i}",
        original_url=f"https://example.test/original/{i}"), DownloadOptions(authentication_mode="None", quality="720p"),
        id=f"fixture-{i}", status=JobStatus.DOWNLOADING, created_at=f"2026-01-02T03:04:0{i}.100000+00:00") for i in range(2)]
    window.jobs = {job.id: job for job in jobs}; window.database.save_jobs(jobs)
    window._refresh_queue(); window._refresh_history()
    return jobs


def watch_queries(window, monkeypatch):
    calls = []; original = window.database.search_history
    def query(*args, **kwargs):
        calls.append((args, kwargs)); return original(*args, **kwargs)
    monkeypatch.setattr(window.database, "search_history", query)
    return calls


def test_progress_only_updates_preserve_history_selection_and_items_but_persist_bytes(window, monkeypatch):
    jobs = jobs_in(window); window.history_table.selectRow(0)
    selected = window._history_selected_job().id
    items = [window.history_table.item(row, 1) for row in range(2)]
    calls = watch_queries(window, monkeypatch)
    for job in jobs:
        snapshot = copy.deepcopy(job); snapshot.progress = 37.5; snapshot.downloaded_bytes = 1536
        snapshot.speed = 2048; snapshot.total_bytes = 4096; snapshot.eta = 7
        window._job_changed(snapshot)
    assert calls == [], "Progress fields do not appear in history and must not rebuild it"
    assert [window.history_table.item(row, 1) for row in range(2)] == items
    assert window._history_selected_job().id == selected
    saved = {job.id: job for job in window.database.load_jobs()}
    assert all(saved[job.id].progress == 37.5 and saved[job.id].downloaded_bytes == 1536 for job in jobs)


@pytest.mark.parametrize("field,column,expected", [("title", 1, "Changed title"), ("original", 2, "https://example.test/new-original"),
    ("source", 3, "https://example.test/new-source"), ("output", 4, "/synthetic/final.mp4"),
    ("format", 5, "MP3"), ("status", 6, "Paused")])
def test_in_place_history_metadata_changes_still_refresh_actual_cells(window, monkeypatch, field, column, expected):
    job = jobs_in(window)[0]; calls = watch_queries(window, monkeypatch)
    if field == "title": job.item.title = expected
    elif field == "original": job.item.original_url = expected
    elif field == "source": job.item.source_url = expected
    elif field == "output": job.output_file = expected
    elif field == "format": job.options.audio_format = expected
    elif field == "status": job.status = JobStatus.PAUSED
    window._job_changed(job)
    assert len(calls) == 1
    row = next(row for row in range(2) if window.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == job.id)
    assert window.history_table.item(row, column).text() == expected


def test_hidden_progress_is_cheap_and_status_change_can_enter_current_filter(window, monkeypatch):
    job = jobs_in(window)[0]; window.history_filter.setCurrentText("Paused")
    assert window.history_table.rowCount() == 0
    calls = watch_queries(window, monkeypatch)
    job.progress = 25; window._job_changed(job)
    assert not calls and window.history_table.rowCount() == 0
    job.status = JobStatus.PAUSED; window._job_changed(job)
    assert len(calls) == 1 and window.history_table.rowCount() == 1
    assert window.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == job.id


def test_filtered_new_job_is_remembered_after_successful_save_then_can_match_sql_search(window, monkeypatch):
    jobs_in(window); window.history_search.setText("matching")
    calls = watch_queries(window, monkeypatch)
    new = DownloadJob(MediaItem("https://example.test/new", "Hidden new"), DownloadOptions(authentication_mode="None"), id="new")
    window._job_changed(new)
    assert len(calls) == 1 and window.history_table.rowCount() == 0
    new.progress = 25; window._job_changed(new)
    assert len(calls) == 1, "A hidden persisted job must not refresh endlessly"
    new.item.title = "Now matching"; window._job_changed(new)
    assert len(calls) == 2 and window.history_table.rowCount() == 1
    window.history_search.setText("VIDEO _")  # Existing SQL LIKE ASCII case/wildcard semantics.
    assert window.history_table.rowCount() == 2


def test_subsecond_creation_change_refreshes_without_changing_database_sort_policy(window, monkeypatch):
    jobs = jobs_in(window)
    previous = [(window.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole), window.history_table.item(row, 0).text()) for row in range(2)]
    jobs[0].created_at = "2026-01-02T03:04:00.999999+00:00"
    calls = watch_queries(window, monkeypatch); window._job_changed(jobs[0])
    # Existing save_job preserves the indexed created_at on conflict. Only the
    # payload changed here; do not invent a new DB sorting policy for this fix.
    assert len(calls) == 1
    assert [(window.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole), window.history_table.item(row, 0).text()) for row in range(2)] == previous


def test_refresh_does_not_acknowledge_another_jobs_unpersisted_mutation(window, monkeypatch):
    first, second = jobs_in(window)
    second.item.title = "Not persisted yet"
    first.status = JobStatus.PAUSED; window._job_changed(first)
    calls = watch_queries(window, monkeypatch); window._job_changed(second)
    assert len(calls) == 1
    assert any(window.history_table.item(row, 1).text() == "Not persisted yet" for row in range(2))


def test_failed_history_render_is_not_acknowledged_and_next_update_retries(window, monkeypatch):
    job = jobs_in(window)[0]; job.item.title = "Must retry"
    original = window.history_table.setItem
    def fail(*args): raise RuntimeError("synthetic presentation failure")
    monkeypatch.setattr(window.history_table, "setItem", fail)
    with pytest.raises(RuntimeError, match="synthetic presentation failure"): window._job_changed(job)
    monkeypatch.setattr(window.history_table, "setItem", original)
    calls = watch_queries(window, monkeypatch); window._job_changed(job)
    assert len(calls) == 1 and any(window.history_table.item(row, 1).text() == "Must retry" for row in range(2))


def test_failed_save_does_not_acknowledge_history_change(window, monkeypatch):
    job = jobs_in(window)[0]; job.item.title = "Persist before showing"
    save = window.database.save_job
    def fail(_job): raise OSError("synthetic persistence failure")
    monkeypatch.setattr(window.database, "save_job", fail)
    with pytest.raises(OSError, match="synthetic persistence failure"): window._job_changed(job)
    assert all(window.history_table.item(row, 1).text() != "Persist before showing" for row in range(2))
    monkeypatch.setattr(window.database, "save_job", save)
    calls = watch_queries(window, monkeypatch); window._job_changed(job)
    assert len(calls) == 1 and any(window.history_table.item(row, 1).text() == "Persist before showing" for row in range(2))


def test_explicit_removal_refresh_clears_history_and_readded_id_is_new(window, monkeypatch):
    jobs = jobs_in(window); removed = jobs[0]
    window.database.remove_job(removed.id); window.jobs.pop(removed.id); window._refresh_history()
    assert window.history_table.rowCount() == 1
    calls = watch_queries(window, monkeypatch); window._job_changed(removed)
    assert len(calls) == 1 and window.history_table.rowCount() == 2


@pytest.mark.parametrize("failure", ["query", "render"])
def test_failed_explicit_filter_refresh_retries_on_unchanged_callback(window, monkeypatch, failure):
    job = jobs_in(window)[0]
    window.history_search.blockSignals(True); window.history_search.setText("Video 0"); window.history_search.blockSignals(False)
    target, attribute = (window.database, "search_history") if failure == "query" else (window.history_table, "setItem")
    original = getattr(target, attribute)
    def fail(*_args, **_kwargs): raise RuntimeError("synthetic explicit refresh failure")
    monkeypatch.setattr(target, attribute, fail)
    with pytest.raises(RuntimeError, match="synthetic explicit refresh failure"): window._refresh_history()
    monkeypatch.setattr(target, attribute, original)
    calls = watch_queries(window, monkeypatch); job.progress = 25; window._job_changed(job)
    assert len(calls) == 1 and window.history_table.rowCount() == 1
    assert window.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == job.id


@pytest.mark.parametrize("action,initial,expected", [("pause", JobStatus.WAITING, "Paused"),
    ("resume", JobStatus.PAUSED, "Waiting"), ("cancel", JobStatus.WAITING, "Cancelled"),
    ("restart", JobStatus.FAILED, "Waiting"), ("stop_seeding", JobStatus.SEEDING, "Completed"),
    ("dispatch", JobStatus.WAITING, "Analysing"), ("watchdog", JobStatus.DOWNLOADING, "Failed")])
def test_noncallback_status_changes_reach_history_without_another_metadata_change(window, monkeypatch, action, initial, expected):
    target, other = jobs_in(window); target.status = initial
    other.metadata_success = True  # Do not make the watchdog fail the unrelated job.
    if action == "stop_seeding": target.kind = "torrent"; window.queue_filter.setCurrentText("All")
    window.database.save_jobs([target, other]); window._refresh_queue(); window._refresh_history()
    window.history_filter.setCurrentText(expected)
    window.queue_table.selectRow(0)
    calls = watch_queries(window, monkeypatch)
    if action == "pause": window._pause([target])
    elif action == "resume": window._resume([target])
    elif action == "cancel": window.cancel_selected()
    elif action == "restart":
        monkeypatch.setattr("morgan_media_downloader.ui.delete_restart_state", lambda *_args, **_kw: None)
        window.restart_selected()
    elif action == "stop_seeding": window.stop_seeding()
    elif action == "dispatch":
        monkeypatch.setattr(window.task_manager, "start", lambda _kind, _operation, **kw: kw["task_id"])
        window._dispatch()
    elif action == "watchdog": window._watchdog_jobs()
    other.progress = 25; window._job_changed(other)
    assert len(calls) == 1, "One real status change, not every progress callback"
    assert window.history_table.rowCount() == 1
    assert window.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == target.id
    assert window.history_table.item(0, 6).text() == expected


def test_partial_status_action_failure_invalidates_successfully_saved_rows(window, monkeypatch):
    first, second = jobs_in(window); first.status = second.status = JobStatus.WAITING
    third = DownloadJob(MediaItem("https://example.test/third", "Third"), DownloadOptions(authentication_mode="None"),
                        id="third", status=JobStatus.DOWNLOADING)
    window.jobs[third.id] = third; window.database.save_jobs([first, second, third]); window._refresh_queue(); window._refresh_history()
    original = window.database.save_job
    def save(job):
        if job.id == second.id: raise OSError("synthetic second save failure")
        original(job)
    monkeypatch.setattr(window.database, "save_job", save)
    with pytest.raises(OSError, match="synthetic second save failure"): window._pause([first, second])
    monkeypatch.setattr(window.database, "save_job", original)
    calls = watch_queries(window, monkeypatch); third.progress = 25; window._job_changed(third)
    assert len(calls) == 1
    statuses = {window.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole): window.history_table.item(row, 6).text() for row in range(3)}
    assert statuses[first.id] == "Paused" and statuses[second.id] == "Waiting"


def test_queue_render_failure_after_save_keeps_history_dirty_for_another_callback(window, monkeypatch):
    target, other = jobs_in(window); target.item.title = "Saved before queue failure"
    refresh = window._refresh_queue
    def fail(*_args, **_kw): raise RuntimeError("synthetic queue render failure")
    monkeypatch.setattr(window, "_refresh_queue", fail)
    with pytest.raises(RuntimeError, match="synthetic queue render failure"): window._job_changed(target)
    monkeypatch.setattr(window, "_refresh_queue", refresh)
    calls = watch_queries(window, monkeypatch); other.progress = 25; window._job_changed(other)
    assert len(calls) == 1
    assert any(window.history_table.item(row, 1).text() == "Saved before queue failure" for row in range(2))


def test_clear_completed_remains_dirty_if_queue_render_fails_before_history(window, monkeypatch):
    target, other = jobs_in(window); target.status = JobStatus.COMPLETED
    window.database.save_job(target); window._refresh_history()
    refresh = window._refresh_queue
    def fail(*_args, **_kw): raise RuntimeError("synthetic queue render failure")
    monkeypatch.setattr(window, "_refresh_queue", fail)
    with pytest.raises(RuntimeError, match="synthetic queue render failure"): window.clear_completed()
    monkeypatch.setattr(window, "_refresh_queue", refresh)
    calls = watch_queries(window, monkeypatch); other.progress = 25; window._job_changed(other)
    assert len(calls) == 1 and window.history_table.rowCount() == 1
    assert window.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == other.id
