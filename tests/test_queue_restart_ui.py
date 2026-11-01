import copy
import threading
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from morgan_media_downloader.models import JobStatus
from morgan_media_downloader.queue_restart import restart_job
from test_queue_model import make_job
from test_ui_diagnostics import _APP, _window


@pytest.fixture
def window(tmp_path, monkeypatch):
    value = _window(tmp_path, monkeypatch)
    for timer in value.findChildren(QTimer): timer.stop()
    value.tabs.setCurrentIndex(1); _APP.processEvents()
    try: yield value
    finally: value.close(); _APP.processEvents()


def populate(window, root, count):
    values = [make_job(f"Video {i}") for i in range(count)]
    for job in values: job.options.download_dir = str(root); job.status = JobStatus.FAILED
    window.jobs = {job.id: job for job in values}; window.database.save_jobs(values)
    window._refresh_queue(); window._refresh_history(); window.queue_table.selectAll()
    return values


def finish(window):
    deadline = time.monotonic()+20
    while window.queue_batch.busy and time.monotonic() < deadline: _APP.processEvents(); time.sleep(.001)
    assert not window.queue_batch.busy and window.task_manager.active_count == 0


@pytest.mark.parametrize("count", [800, 5000])
def test_bulk_restart_confirms_once_and_persists_exact_selected_ids(window, tmp_path, monkeypatch, count):
    values = populate(window, tmp_path, count); prompts = []
    def confirm(jobs): prompts.append({job.id for job in jobs}); return "keep"
    monkeypatch.setattr(window, "_confirm_restart", confirm)
    window.restart_selected(); assert window.queue_batch.busy
    finish(window)
    assert prompts == [{job.id for job in values}]
    assert window.queue_batch.describe()["completed"] == count and not window.queue_batch.describe()["failed"]
    assert all(job.status == JobStatus.WAITING for job in window.database.load_jobs())


def test_cancelled_restart_has_no_filesystem_worker_or_persistence_effect(window, tmp_path, monkeypatch):
    values = populate(window, tmp_path, 12); before = [job.to_dict() for job in values]
    monkeypatch.setattr(window, "_confirm_restart", lambda _jobs: "cancel")
    window.restart_selected(); _APP.processEvents()
    assert not window.queue_batch.busy and window.task_manager.active_count == 0
    assert [job.to_dict() for job in window.database.load_jobs()] == before


def test_restart_uses_post_modal_inventory_and_keeps_outputs(window, tmp_path, monkeypatch):
    values = populate(window, tmp_path, 1); original = values[0]
    partial = tmp_path / "latest.part"; partial.write_bytes(b"owned")
    final = tmp_path / "latest.mp4"; final.write_bytes(b"keep")
    def confirm(_jobs):
        latest = copy.deepcopy(original); latest.partial_files = [str(partial)]
        latest.final_files = [str(final)]; latest.output_file = str(final)
        window.jobs[latest.id] = latest; return "keep"
    monkeypatch.setattr(window, "_confirm_restart", confirm)
    window.restart_selected(); finish(window)
    changed = window.jobs[original.id]
    assert not partial.exists() and final.read_bytes() == b"keep"
    assert changed.options.download_dir != str(tmp_path) and not changed.output_file


def test_slow_restart_cleanup_yields_gui_heartbeats_and_never_runs_on_gui(window, tmp_path, monkeypatch):
    populate(window, tmp_path, 800); prompts = []; calls = []; ticks = []; main = threading.get_ident()
    monkeypatch.setattr(window, "_confirm_restart", lambda jobs: prompts.append(len(jobs)) or "keep")
    def process(job, choice):
        calls.append(threading.get_ident()); time.sleep(.001)
        return restart_job(job, choice)
    window.queue_restart.processor = process
    timer = QTimer(); timer.timeout.connect(lambda: ticks.append(time.monotonic())); timer.start(5)
    try: window.restart_selected(); finish(window)
    finally: timer.stop()
    assert prompts == [800] and len(calls) == 800 and all(thread != main for thread in calls)
    assert len(ticks) > 5


def test_real_restart_dialog_reports_one_count_and_defaults_to_keep(window, tmp_path):
    values = populate(window, tmp_path, 800); seen = []
    values[0].status = JobStatus.COMPLETED; window.active[values[1].id] = "synthetic-owner"
    def inspect():
        box = QApplication.activeModalWidget()
        seen.append((box.text(), box.defaultButton().text(), box.escapeButton()))
        box.reject()
    QTimer.singleShot(0, inspect)
    try: result = window._confirm_restart(values)
    finally: window.active.clear()
    assert result == "cancel" and len(seen) == 1
    assert "800" in seen[0][0] and "1 active" in seen[0][0] and "1 completed" in seen[0][0]
    assert "keep" in seen[0][1].lower() and seen[0][2] is not None


def test_closing_during_restart_retains_interrupted_state_and_drains_worker(window, tmp_path, monkeypatch):
    populate(window, tmp_path, 100); entered = threading.Event(); release = threading.Event(); calls = []
    monkeypatch.setattr(window, "_confirm_restart", lambda _jobs: "keep")
    def process(job, choice):
        entered.set(); assert release.wait(5); calls.append(job.id); return restart_job(job, choice)
    window.queue_restart.processor = process; window.restart_selected()
    deadline = time.monotonic()+3
    while not entered.is_set() and time.monotonic() < deadline: _APP.processEvents()
    assert entered.is_set(); path = window.database.path
    timer = threading.Timer(.03, release.set); timer.start()
    window.close(); timer.join(); _APP.processEvents()
    from morgan_media_downloader.database import Database
    database = Database(path)
    try: restored = database.load_jobs()
    finally: database.close()
    assert len(calls) == 1 and window.task_manager.active_count == 0
    assert len(restored) == 100 and all(job.status != JobStatus.WAITING for job in restored)
    assert sum("Restart interrupted" in job.technical_details for job in restored) == 32


def test_active_restart_waits_for_thread_exit_and_cannot_reuse_unreported_partial(window, tmp_path, monkeypatch):
    values = populate(window, tmp_path, 1); job = values[0]; job.status = JobStatus.DOWNLOADING
    release = threading.Event(); cancelled = threading.Event(); clean_calls = []
    unknown = tmp_path / "late-unreported.part"
    def transfer(cancel, _progress):
        assert cancel.wait(5); cancelled.set(); assert release.wait(5)
        unknown.write_bytes(b"late worker partial")
        return job
    task = f"job-{job.id}"
    window.active[job.id] = window.task_manager.start("download-media", transfer, task_id=task, on_finished=window._job_finished)
    monkeypatch.setattr(window, "_confirm_restart", lambda _jobs: "keep")
    def process(snapshot, choice):
        assert not window.active
        clean_calls.append(snapshot.id); return restart_job(snapshot, choice)
    window.queue_restart.processor = process; window.restart_selected()
    deadline = time.monotonic()+3
    try:
        while not cancelled.is_set() and time.monotonic() < deadline: _APP.processEvents()
        assert cancelled.is_set() and not clean_calls and window.queue_batch.busy
    finally: release.set()
    finish(window)
    assert clean_calls == [job.id] and unknown.exists()
    assert window.jobs[job.id].options.download_dir != str(tmp_path)


def test_shutdown_marker_persistence_failure_still_drains_restart_worker(window, tmp_path, monkeypatch):
    populate(window, tmp_path, 32); entered = threading.Event(); release = threading.Event()
    monkeypatch.setattr(window, "_confirm_restart", lambda _jobs: "keep")
    def process(job, choice):
        entered.set(); assert release.wait(5); return restart_job(job, choice)
    window.queue_restart.processor = process; window.restart_selected()
    deadline = time.monotonic()+3
    while not entered.is_set() and time.monotonic() < deadline: _APP.processEvents()
    assert entered.is_set()
    def fail(_jobs): raise OSError("synthetic close persistence failure")
    monkeypatch.setattr(window.database, "save_jobs", fail)
    timer = threading.Timer(.03, release.set); timer.start()
    window.close(); timer.join(); _APP.processEvents()
    assert window.task_manager.active_count == 0 and window.clean_marker.exists()


def test_removal_does_not_interleave_with_restart_started_while_confirmation_is_open(window, tmp_path, monkeypatch):
    populate(window, tmp_path, 1); ids = set(window.jobs)
    def confirm(_jobs): window.queue_restart.start(ids, "keep"); return "list"
    monkeypatch.setattr(window, "_confirm_remove", confirm)
    window.remove_selected()
    assert set(window.jobs) == ids
    finish(window)


def test_empty_selection_does_not_prompt_or_start_restart(window, monkeypatch):
    def unexpected(_jobs): raise AssertionError("No selection must not prompt")
    monkeypatch.setattr(window, "_confirm_restart", unexpected)
    window.restart_selected()
    assert not window.queue_batch.busy and window.task_manager.active_count == 0
