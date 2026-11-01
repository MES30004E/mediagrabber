import copy
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.database import Database
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.queue_batch import QueueBatch
from morgan_media_downloader.queue_restart import QueueRestart, restart_job
from morgan_media_downloader.tasks import TaskManager

APP = QApplication.instance() or QApplication([])


def job_at(root, number=0):
    return DownloadJob(MediaItem(f"https://example.test/{number}", f"Video {number}"),
        DownloadOptions(download_dir=str(root), authentication_mode="Browser Cookies", quality="720p"),
        status=JobStatus.FAILED, progress=35, downloaded_bytes=120, failure_code="old failure")


@pytest.mark.parametrize("kind", ["media", "torrent"])
def test_keep_final_uses_fresh_destination_without_touching_final_or_foreign_files(tmp_path, kind):
    job = job_at(tmp_path); job.kind = kind; job.torrent_file_paths = ["album/video.mp4"]
    final = tmp_path / "video.mp4"; final.write_bytes(b"retained final")
    partial = tmp_path / "video.mp4.part"; partial.write_bytes(b"owned partial")
    foreign = tmp_path / "foreign.part"; foreign.write_bytes(b"unrelated")
    job.final_files = [str(final)]; job.partial_files = [str(partial)]; job.output_file = str(final)
    before = copy.deepcopy(job)
    first = restart_job(job, "keep"); second = restart_job(job, "keep", cleaner=lambda *_a, **_kw: None)
    assert job.to_dict() == before.to_dict(), "Policy must not mutate the live job"
    assert final.read_bytes() == b"retained final" and foreign.exists() and not partial.exists()
    assert Path(first.options.download_dir).parent == tmp_path
    assert first.options.download_dir != second.options.download_dir and not Path(first.options.download_dir).exists()
    assert not first.final_files and not first.output_file and first.progress == 0 and first.downloaded_bytes == 0
    assert first.status == JobStatus.WAITING and not first.failure_code
    assert first.options.authentication_mode == "Browser Cookies" and first.options.quality == "720p"
    assert first.torrent_file_paths == ["album/video.mp4"] and first.id == job.id


def test_replace_only_deletes_recorded_in_root_paths_and_resets_active_state(tmp_path):
    root = tmp_path / "downloads"; root.mkdir(); job = job_at(root)
    final = root / "owned.mp4"; final.write_bytes(b"owned")
    outside = tmp_path / "outside.mp4"; outside.write_bytes(b"foreign")
    unrelated = root / "unrelated.mp4"; unrelated.write_bytes(b"foreign")
    job.final_files = [str(final), str(outside)]; job.active_extractor_task = True
    job.active_transfer_task = True; job.active_postprocess_task = True
    changed = restart_job(job, "replace")
    assert not final.exists() and outside.exists() and unrelated.exists()
    assert Path(changed.options.download_dir).parent == root and not changed.final_files
    assert not changed.active_extractor_task and not changed.active_transfer_task and not changed.active_postprocess_task


def test_restart_uses_fresh_destination_even_without_recorded_final_and_invalid_choice_has_no_effects(tmp_path):
    job = job_at(tmp_path); partial = tmp_path / "file.part"; partial.write_bytes(b"partial")
    job.partial_files = [str(partial)]
    with pytest.raises(ValueError): restart_job(job, "typo")
    assert partial.exists()
    changed = restart_job(job, "keep")
    assert not partial.exists() and Path(changed.options.download_dir).parent == tmp_path
    assert changed.options.download_dir != str(tmp_path)


def test_keep_preserves_final_aliases_and_associated_sidecar_outputs(tmp_path):
    job = job_at(tmp_path)
    final = tmp_path / "final.mp4"; final.write_bytes(b"final")
    subtitle = tmp_path / "final.en.srt"; subtitle.write_text("owned subtitle")
    thumbnail = tmp_path / "final.jpg"; thumbnail.write_bytes(b"image")
    job.final_files = [str(tmp_path / "subdir" / ".." / "final.mp4")]
    job.partial_files = [str(final)]; job.subtitle_files = [str(subtitle)]; job.thumbnail_files = [str(thumbnail)]
    changed = restart_job(job, "keep")
    assert final.exists() and subtitle.exists() and thumbnail.exists()
    assert not changed.final_files and not changed.partial_files and not changed.subtitle_files and not changed.thumbnail_files


@pytest.mark.parametrize("choice", ["keep", "replace"])
def test_unrecorded_partial_is_not_deleted_or_reused_by_a_restart(tmp_path, choice):
    job = job_at(tmp_path); unknown = tmp_path / "unrecorded.part"; unknown.write_bytes(b"not inventoried")
    changed = restart_job(job, choice)
    assert unknown.exists() and Path(changed.options.download_dir).parent == tmp_path
    assert changed.options.download_dir != str(tmp_path)


def spin(predicate, timeout=8):
    deadline = time.monotonic()+timeout
    while not predicate() and time.monotonic() < deadline: APP.processEvents(); time.sleep(.001)
    assert predicate()


@pytest.fixture
def rig(tmp_path):
    manager = TaskManager(); batch = QueueBatch(); database = Database(tmp_path / "queue.sqlite3")
    jobs = {}; active = {}; excluded = set()
    controller = QueueRestart(manager, batch, database, lambda: jobs, lambda: active, lambda: excluded)
    try: yield manager, batch, database, jobs, active, excluded, controller
    finally: controller.close(); batch.cancel(abandon=True); manager.shutdown(); database.close(); APP.processEvents()


def test_controller_bounds_slices_waits_for_owner_and_uses_latest_inventory(rig, tmp_path):
    manager, batch, database, jobs, active, _excluded, controller = rig
    values = [job_at(tmp_path, i) for i in range(65)]; jobs.update((j.id, j) for j in values); database.save_jobs(values)
    active[values[0].id] = manager.start("transfer", lambda cancel, _progress: cancel.wait(5))
    calls = []; main = threading.get_ident(); slices = []; original = database.save_jobs
    def save(values):
        values = list(values); slices.append(len(values)); return original(values)
    database.save_jobs = save
    def process(job, choice):
        assert not active, "No cleanup before owned transfer exit"
        committed = {v.id: v for v in database.load_jobs()}
        assert committed[job.id].status == JobStatus.INTERRUPTED
        calls.append((job.id, tuple(job.partial_files), threading.get_ident()))
        return restart_job(job, choice, cleaner=lambda *_a, **_kw: None)
    controller.processor = process
    def stopped(_task_id, kind):
        if kind == "transfer":
            latest = copy.deepcopy(jobs[values[0].id]); latest.partial_files = ["latest synthetic inventory"]
            jobs[latest.id] = latest; active.pop(latest.id); controller.owner_stopped(latest.id)
    manager.task_finished.connect(stopped)
    assert controller.start(list(jobs), "keep")
    spin(lambda: not batch.busy)
    assert len(calls) == 65 and all(thread != main for _, _, thread in calls)
    assert calls[0][1] == ("latest synthetic inventory",)
    assert max(slices) == 32 and len(slices) == 6
    assert batch.describe()["completed"] == 65 and batch.describe()["failed"] == 0
    assert manager.active_count == 0 and not controller.pending
    assert all(j.status == JobStatus.WAITING for j in database.load_jobs())


@pytest.mark.parametrize("phase", ["prepare", "final"])
def test_failed_database_commit_never_runs_unprepared_or_publishes_waiting(rig, tmp_path, phase):
    manager, batch, database, jobs, _active, _excluded, controller = rig
    job = job_at(tmp_path); jobs[job.id] = job; database.save_job(job); original = database.save_jobs; calls = []; cleaned = []
    def save(values):
        values = list(values); calls.append(values[0].status)
        if (phase == "prepare" and len(calls) == 1) or (phase == "final" and values[0].status == JobStatus.WAITING):
            raise OSError("synthetic write failure")
        return original(values)
    database.save_jobs = save
    controller.processor = lambda job, choice: cleaned.append(job.id) or restart_job(job, choice, cleaner=lambda *_a, **_kw: None)
    controller.start([job.id], "keep"); spin(lambda: not batch.busy)
    assert len(cleaned) == (phase == "final")
    assert jobs[job.id].status != JobStatus.WAITING and database.load_jobs()[0].status != JobStatus.WAITING
    assert batch.describe()["failed"] == 1 and manager.active_count == 0


def test_stop_finishes_admitted_slice_and_no_later_slice(rig, tmp_path):
    _manager, batch, database, jobs, _active, _excluded, controller = rig
    values = [job_at(tmp_path, i) for i in range(100)]; jobs.update((j.id, j) for j in values); database.save_jobs(values)
    entered = threading.Event(); release = threading.Event(); calls = []
    def process(job, choice):
        entered.set(); assert release.wait(5); calls.append(job.id)
        return restart_job(job, choice, cleaner=lambda *_a, **_kw: None)
    controller.processor = process; controller.start(list(jobs), "keep")
    spin(entered.is_set); batch.cancel(); release.set(); spin(lambda: not batch.busy)
    assert len(calls) == 32 and batch.describe()["completed"] == 32 and batch.describe()["pending"] == 68
    assert sum(j.status == JobStatus.WAITING for j in database.load_jobs()) == 32


def test_cleanup_failure_is_redacted_and_other_jobs_finish(rig, tmp_path):
    _manager, batch, database, jobs, _active, excluded, controller = rig
    values = [job_at(tmp_path, i) for i in range(3)]; jobs.update((j.id, j) for j in values); database.save_jobs(values)
    excluded.add(values[2].id)
    def process(job, choice):
        if job.id == values[0].id: raise OSError("https://user:synthetic-restart-secret@example.test/file")
        return restart_job(job, choice, cleaner=lambda *_a, **_kw: None)
    controller.processor = process; controller.start(list(jobs), "keep"); spin(lambda: not batch.busy)
    assert batch.describe()["failed"] == 1 and batch.describe()["completed"] == 1 and batch.describe()["skipped"] == 1
    assert jobs[values[0].id].status == JobStatus.INTERRUPTED and jobs[values[2].id].status == JobStatus.FAILED
    assert "synthetic-restart-secret" not in str(batch.describe())+str(jobs[values[0].id].to_dict())


def test_worker_snapshot_cannot_mutate_gui_owned_job_while_running(rig, tmp_path):
    _manager, batch, database, jobs, _active, _excluded, controller = rig
    job = job_at(tmp_path); jobs[job.id] = job; database.save_job(job)
    entered = threading.Event(); release = threading.Event()
    def process(snapshot, choice):
        snapshot.item.title = "worker mutation"; entered.set(); assert release.wait(5)
        return restart_job(snapshot, choice)
    controller.processor = process; controller.start([job.id], "keep")
    try:
        spin(entered.is_set)
        assert jobs[job.id].item.title == "Video 0"
    finally: release.set(); spin(lambda: not batch.busy)


@pytest.mark.parametrize("failure", ["admission", "invalid_result"])
def test_worker_admission_or_result_failure_stays_interrupted(rig, tmp_path, monkeypatch, failure):
    manager, batch, database, jobs, _active, _excluded, controller = rig
    job = job_at(tmp_path); jobs[job.id] = job; database.save_job(job)
    if failure == "admission":
        def reject(*_a, **_kw): raise RuntimeError("synthetic thread admission failure")
        monkeypatch.setattr(manager, "start", reject)
    else: controller.processor = lambda *_args: "not a DownloadJob"
    controller.start([job.id], "keep"); spin(lambda: not batch.busy)
    assert batch.describe()["failed"] == 1 and not batch.describe()["completed"]
    assert database.load_jobs()[0].status == JobStatus.INTERRUPTED and manager.active_count == 0


def test_refused_owner_stop_does_not_clean_or_change_live_job(rig, tmp_path, monkeypatch):
    manager, batch, database, jobs, active, _excluded, controller = rig
    job = job_at(tmp_path); jobs[job.id] = job; database.save_job(job); active[job.id] = "not-owned"
    calls = []; monkeypatch.setattr(manager, "cancel", lambda _task: False)
    controller.processor = lambda *_a: calls.append(True)
    controller.start([job.id], "keep"); spin(lambda: not batch.busy)
    assert not calls and batch.describe()["failed"] == 1 and jobs[job.id].status == JobStatus.FAILED
