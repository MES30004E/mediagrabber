"""Queue model integration preserves real actions, identity and view ownership."""
import copy

import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QProgressBar, QTableView

from morgan_media_downloader.models import JobStatus
from morgan_media_downloader.queue_model import JOB_ID_ROLE, PROGRESS_ROLE
from test_queue_model import make_job
from test_ui_diagnostics import _APP, _window


def select_rows(window, rows):
    selection = window.queue_table.selectionModel(); selection.clearSelection()
    for row in rows:
        selection.select(window.queue_table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)


@pytest.mark.parametrize("count", [800, 5000])
def test_large_queue_has_no_per_row_progress_widgets_but_preserves_data(count, tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        values = [make_job(str(i)) for i in range(count)]; values[-1].progress = 61.5
        window.jobs = {job.id: job for job in values}; window._refresh_queue()
        assert isinstance(window.queue_table, QTableView)
        assert not window.queue_table.findChildren(QProgressBar), "Queue progress must be painted, not one widget per job"
        model = window.queue_table.model()
        assert model.rowCount() == count and model.index(count-1, 3).data(PROGRESS_ROLE) == 61.5
        assert model.index(count-1, 0).data(JOB_ID_ROLE) == values[-1].id
    finally: window.close(); _APP.processEvents()


def test_multiple_selected_ids_survive_removal_insertion_and_hidden_view_roundtrip(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        values = [make_job(str(i)) for i in range(30)] + [make_job("Torrent", "torrent")]
        window.jobs = {job.id: job for job in values}; window._refresh_queue()
        select_rows(window, [5, 15]); wanted = {values[5].id, values[15].id}
        window.jobs.pop(values[0].id); extra = make_job("Extra"); window.jobs[extra.id] = extra
        window._refresh_queue()
        assert {job.id for job in window._selected_jobs()} == wanted
        window.queue_filter.setCurrentText("Torrents")
        assert not window._selected_jobs(), "Hidden remembered selection must not affect visible queue actions"
        window.queue_filter.setCurrentText("All")
        assert {job.id for job in window._selected_jobs()} == wanted
        # Reorder forces the source reset path; IDs, not old row numbers, survive.
        window.jobs = dict(reversed(list(window.jobs.items()))); window._refresh_queue()
        assert {job.id for job in window._selected_jobs()} == wanted
    finally: window.close(); _APP.processEvents()


def test_filtered_actions_target_visible_job_identity_not_source_row(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        media, torrent, other = make_job(), make_job("Torrent", "torrent"), make_job("Other", "torrent")
        window.jobs = {job.id: job for job in [media, torrent, other]}; window._refresh_queue()
        window.queue_filter.setCurrentText("Torrents"); select_rows(window, [0])
        assert [job.id for job in window._selected_jobs()] == [torrent.id]
        window.pause_selected()
        assert torrent.status == JobStatus.PAUSED
        assert media.status == other.status == JobStatus.WAITING
    finally: window.close(); _APP.processEvents()


def test_single_worker_progress_only_presents_and_notifies_its_row(tmp_path, monkeypatch):
    from morgan_media_downloader import queue_model
    window = _window(tmp_path, monkeypatch); presented = []; changes = []
    original = queue_model.presentation_row
    def trace(job, connection):
        presented.append(job.id); return original(job, connection)
    try:
        values = [make_job(str(i)) for i in range(800)]
        window.jobs = {job.id: job for job in values}; window._refresh_queue()
        monkeypatch.setattr(queue_model, "presentation_row", trace)
        # Observe actual source-model notification and real displayed result.
        source = window.queue_table.model()
        if hasattr(source, "sourceModel"): source = source.sourceModel()
        source.dataChanged.connect(lambda first, last, _: changes.append((first.row(), last.row())))
        changed = copy.deepcopy(values[45]); changed.progress = 83.5
        window._job_changed(changed)
        assert presented == [changed.id], "One worker callback must not reformat all800 rows"
        assert changes == [(45, 45)]
        assert window.queue_table.model().index(45, 3).data() == "83.5%"
    finally: window.close(); _APP.processEvents()


@pytest.mark.parametrize("view", ["Media", "Torrents", "All"])
def test_first_population_sizes_status_for_real_content_not_empty_header(tmp_path, monkeypatch, view):
    window = _window(tmp_path, monkeypatch)
    try:
        assert window.queue_table.model().rowCount() == 0
        window.queue_filter.setCurrentText(view)
        job = make_job(kind="torrent" if view == "Torrents" else "media"); job.status = JobStatus.COMPLETED_WARNINGS
        window.jobs[job.id] = job; window._refresh_queue()
        status_column = 1 if view == "Torrents" else 2
        text = window.queue_table.model().index(0, status_column).data()
        assert text == "Completed with warnings ⚠"
        assert window.queue_table.columnWidth(status_column) >= window.queue_table.fontMetrics().horizontalAdvance(text)
    finally: window.close(); _APP.processEvents()
