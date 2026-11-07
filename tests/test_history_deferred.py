"""Hidden History must not rebuild or retain obsolete persisted presentation."""
import copy

import pytest
from PySide6.QtCore import QTimer, Qt

from morgan_media_downloader.database import Database
from morgan_media_downloader.models import JobStatus
from test_history_progress import APP, jobs_in, watch_queries
from test_ui_diagnostics import _window


@pytest.fixture
def window(tmp_path, monkeypatch):
    value = _window(tmp_path, monkeypatch)
    for timer in value.findChildren(QTimer): timer.stop()
    value.tabs.setCurrentIndex(1)
    try: yield value
    finally: value.close(); APP.processEvents()


def show_history(window):
    # Find by the existing navigation label, not a future library-sensitive index.
    window.tabs.setCurrentIndex(next(i for i in range(window.tabs.count()) if window.tabs.tabText(i) == "History"))


def test_startup_does_not_query_hidden_history(tmp_path, monkeypatch):
    calls = []
    original = Database.search_history
    def query(database, *args, **kwargs):
        calls.append(True)
        return original(database, *args, **kwargs)
    monkeypatch.setattr(Database, "search_history", query)
    value = _window(tmp_path, monkeypatch)
    try:
        for timer in value.findChildren(QTimer): timer.stop()
        assert not calls and value.history_table.rowCount() == 0
        show_history(value)
        assert len(calls) == 1
    finally: value.close(); APP.processEvents()


def test_hidden_changes_coalesce_and_use_latest_sql_filters(window, monkeypatch):
    calls = watch_queries(window, monkeypatch)
    first, _ = jobs_in(window)
    window.history_search.setText("Video _")
    window.history_filter.setCurrentText("Paused")
    first.status = JobStatus.PAUSED
    for percent in (10, 20, 30):
        first.progress = percent; window._job_changed(first)
    assert not calls and window.history_table.rowCount() == 0
    show_history(window)
    assert calls == [(("Video _", "Paused"), {})]
    assert window.history_table.rowCount() == 1
    assert window.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == first.id
    assert window.history_table.item(0, 6).text() == "Paused"


def test_clean_history_revisit_preserves_selection_items_and_avoids_query(window, monkeypatch):
    jobs_in(window); show_history(window)
    window.history_table.selectRow(0)
    selected = window._history_selected_job().id
    item = window.history_table.item(0, 1)
    calls = watch_queries(window, monkeypatch)
    window.tabs.setCurrentIndex(1); show_history(window)
    assert not calls and window.history_table.item(0, 1) is item
    assert window._history_selected_job().id == selected


def test_deferred_history_reads_saved_data_not_unpersisted_live_jobs(window, monkeypatch):
    first, second = jobs_in(window)
    second.item.title = "Unsaved mutable title"
    first.status = JobStatus.PAUSED; window._job_changed(first)
    show_history(window)
    assert all(window.history_table.item(i, 1).text() != "Unsaved mutable title" for i in range(2))
    calls = watch_queries(window, monkeypatch)
    window._job_changed(second)
    assert len(calls) == 1
    assert any(window.history_table.item(i, 1).text() == "Unsaved mutable title" for i in range(2))


def test_hidden_load_clear_cycles_release_stale_cells_and_snapshot_cache(window, monkeypatch):
    first, _ = jobs_in(window); show_history(window)
    assert window.history_table.rowCount() == 2
    window.tabs.setCurrentIndex(1)
    calls = watch_queries(window, monkeypatch)
    for cycle in range(5):
        for key in list(window.jobs): window.database.remove_job(key)
        window.jobs.clear(); window._refresh_queue(); window._refresh_history()
        new = copy.deepcopy(first); new.id = f"history-cycle-{cycle}"
        window._job_changed(new)
        assert window.history_table.rowCount() == 0
        assert not window._history_refresh_state._rows, "A hidden pending refresh must not retain obsolete job snapshots"
    assert not calls
    show_history(window)
    assert len(calls) == 1 and window.history_table.rowCount() == 1
    assert window.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == "history-cycle-4"


@pytest.mark.parametrize("failure", ["query", "render"])
def test_failed_deferred_presentation_retries_without_acknowledging_saved_change(window, monkeypatch, failure):
    job, _ = jobs_in(window)
    show_history(window)
    target, attribute = (window.database, "search_history") if failure == "query" else (window.history_table, "setItem")
    original = getattr(target, attribute)
    def fail(*_args, **_kwargs): raise RuntimeError("synthetic deferred history failure")
    monkeypatch.setattr(target, attribute, fail)
    with pytest.raises(RuntimeError, match="synthetic deferred history failure"):
        window._refresh_history()
    monkeypatch.setattr(target, attribute, original)
    calls = watch_queries(window, monkeypatch)
    window.tabs.setCurrentIndex(1); show_history(window)
    assert len(calls) == 1 and window.history_table.rowCount() == 2
    job.progress = 25; window._job_changed(job)
    assert len(calls) == 1, "A successful retry must acknowledge the rendered snapshot"


def test_pending_history_never_queries_after_window_close(window, monkeypatch):
    jobs_in(window)
    window.close()
    def fail(*_args, **_kwargs): raise AssertionError("History queried a closed database")
    monkeypatch.setattr(window.database, "search_history", fail)
    window._refresh_history()
    show_history(window)
