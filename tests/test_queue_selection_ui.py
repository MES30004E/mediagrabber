import copy
import time

import pytest
from PySide6.QtCore import QTimer

from morgan_media_downloader.models import JobStatus
from morgan_media_downloader.queue_model import JOB_ID_ROLE
from test_queue_model import make_job
from test_ui_diagnostics import _APP, _window


@pytest.fixture
def window(tmp_path, monkeypatch):
    value = _window(tmp_path, monkeypatch)
    for timer in value.findChildren(QTimer): timer.stop()
    value.tabs.setCurrentIndex(1); _APP.processEvents()
    try: yield value
    finally: value.close(); _APP.processEvents()


def populate(window, count=12):
    statuses = [JobStatus.WAITING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.COMPLETED_WARNINGS]
    jobs = [make_job(f"Video {i}", "torrent" if i % 2 else "media") for i in range(count)]
    for i, job in enumerate(jobs): job.status = statuses[(i//2) % len(statuses)]
    window.jobs = {job.id: job for job in jobs}; window.database.save_jobs(jobs)
    window._refresh_queue(); window._refresh_history()
    return jobs


def selected(window): return {job.id for job in window._selected_jobs()}


def finish_batch(window):
    deadline = time.monotonic()+10
    while window.queue_batch.busy and time.monotonic() < deadline: _APP.processEvents()
    assert not window.queue_batch.busy


def test_actual_menu_scopes_and_counts_replace_hidden_selection(window):
    jobs = populate(window)
    window.queue_selection_actions["all"].trigger()
    assert window.queue_filter.currentText() == "All" and selected(window) == set(window.jobs)
    window.queue_filter.setCurrentText("Media"); window.queue_status_filter.setCurrentText("Paused")
    assert selected(window) == {job.id for job in jobs if job.kind == "media" and job.status == JobStatus.PAUSED}
    window.queue_selection_actions["none"].trigger()
    assert not selected(window) and not window._queue_selection_ids and not window.selected_job_id
    window.clear_queue_filters()
    assert not selected(window), "None must not resurrect hidden remembered jobs"
    window.queue_search.setText("Video 1"); window.queue_selection_actions["filtered"].trigger()
    assert selected(window) == {jobs[1].id, jobs[10].id, jobs[11].id}
    assert "3 selected" in window.queue_counts.text() and "3 shown" in window.queue_counts.text() and "12 total" in window.queue_counts.text()


def test_status_menu_closures_select_correct_category_within_filtered_results(window):
    jobs = populate(window)
    window.queue_filter.setCurrentText("Torrents")
    for group, states in [("Waiting", {JobStatus.WAITING}), ("Paused", {JobStatus.PAUSED}),
                          ("Completed", {JobStatus.COMPLETED, JobStatus.COMPLETED_WARNINGS})]:
        window.queue_selection_actions[f"status:{group}"].trigger()
        assert selected(window) == {job.id for job in jobs if job.kind == "torrent" and job.status in states}
    window.queue_search.setText("Video 1"); window.select_queue("status", "Paused")
    assert selected(window) == {jobs[11].id}, "Literal substring also matches Video11"
    window.select_queue("status", "Failed")
    assert not selected(window)


def test_search_and_status_refilter_without_reformatting_source_jobs(window, monkeypatch):
    from morgan_media_downloader import queue_model
    jobs = populate(window, 800); calls = []; original = queue_model.presentation_row
    def present(job, route): calls.append(job.id); return original(job, route)
    monkeypatch.setattr(queue_model, "presentation_row", present)
    window.queue_search.setText("Video 10"); window.queue_status_filter.setCurrentText("Paused")
    assert calls == [], "Typing/filtering must use cached roles, not reformat800jobs"
    expected = [job.id for job in jobs if job.kind == "media" and job.status == JobStatus.PAUSED and "Video 10" in job.item.title]
    assert [window.queue_proxy.index(row, 0).data(JOB_ID_ROLE) for row in range(window.queue_proxy.rowCount())] == expected


def test_live_filter_membership_restores_uuid_selection_and_visible_details(window):
    jobs = populate(window); window.queue_status_filter.setCurrentText("Waiting"); window.select_queue("filtered")
    wanted = selected(window); target = next(job for job in jobs if job.id in wanted)
    changed = copy.deepcopy(target); changed.status = JobStatus.PAUSED; window._job_changed(changed)
    assert selected(window) == wanted-{target.id}
    assert window.selected_job_id in selected(window)
    changed.status = JobStatus.WAITING; window._job_changed(changed)
    assert selected(window) == wanted
    window.queue_status_filter.setCurrentText("Running")
    assert not selected(window) and not window.selected_job_id and not window.job_details.toPlainText()
    window.select_queue("none"); window.clear_queue_filters()
    assert not selected(window)


def test_removing_primary_selected_row_chooses_surviving_visible_details(window):
    jobs = populate(window, 4); window.select_queue("filtered")
    removed = window.selected_job_id
    window.jobs.pop(removed); window.database.remove_job(removed); window._refresh_queue()
    assert window.selected_job_id in selected(window)
    assert window.jobs[window.selected_job_id].item.title in window.job_details.toPlainText()


def test_visible_selection_is_screen_rows_not_all_filtered_rows(window):
    populate(window, 800); window.resize(1000, 760); _APP.processEvents()
    window.queue_table.verticalScrollBar().setValue(20); _APP.processEvents()
    proxy = window.queue_proxy; viewport = window.queue_table.viewport().rect()
    expected = {proxy.index(row, 0).data(JOB_ID_ROLE) for row in range(proxy.rowCount())
                if window.queue_table.visualRect(proxy.index(row, 0)).intersects(viewport)}
    before = window.queue_table.verticalScrollBar().value()
    window.queue_selection_actions["visible"].trigger()
    assert selected(window) == expected and 1 < len(expected) < proxy.rowCount()
    assert window.queue_table.verticalScrollBar().value() == before


@pytest.mark.parametrize("count", [800, 5000])
def test_filtered_bulk_remove_targets_only_selected_ids_with_one_keep_files_prompt(window, monkeypatch, count):
    jobs = populate(window, count); window.queue_status_filter.setCurrentText("Failed")
    window.queue_selection_actions["filtered"].trigger()
    expected = {job.id for job in jobs if job.kind == "media" and job.status == JobStatus.FAILED}
    assert selected(window) == expected
    prompts = []
    def confirm(values): prompts.append({job.id for job in values}); return "list"
    monkeypatch.setattr(window, "_confirm_remove", confirm)
    window.remove_selected(); finish_batch(window)
    assert prompts == [expected]
    assert set(window.jobs) == {job.id for job in jobs}-expected
    assert {job.id for job in window.database.load_jobs()} == set(window.jobs)


def test_invalid_selection_command_does_not_change_filters_or_targets(window):
    populate(window); window.select_queue("filtered"); before = selected(window)
    with pytest.raises(ValueError): window.select_queue("unknown")
    with pytest.raises(ValueError): window.select_queue("status", "unknown")
    assert selected(window) == before and window.queue_filter.currentText() == "Media"


@pytest.mark.parametrize("width,height", [(900, 650), (1180, 820)])
def test_queue_filter_and_selection_controls_fit_supported_window_sizes(window, width, height):
    populate(window, 800); window.select_queue("all"); window.resize(width, height); _APP.processEvents()
    for control in (window.queue_filter, window.queue_status_filter, window.queue_search,
                    window.queue_select_button, window.queue_counts, window.queue_clear_filters):
        assert control.isVisible()
        assert control.width() >= control.minimumSizeHint().width()
        assert window.rect().contains(control.mapTo(window, control.rect().topLeft()))
        assert window.rect().contains(control.mapTo(window, control.rect().bottomRight()))
