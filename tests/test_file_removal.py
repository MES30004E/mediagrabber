import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.file_removal import FileRemovalService
from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem
from morgan_media_downloader.tasks import TaskManager

APP = QApplication.instance() or QApplication([])


def spin(manager):
    deadline = time.monotonic() + 5
    while manager.active_count and time.monotonic() < deadline: APP.processEvents(); time.sleep(.001)
    assert not manager.active_count


def test_cleanup_uses_one_owned_worker_and_reports_after_thread_exit(tmp_path):
    manager = TaskManager(); calls = []; reports = []; main = threading.get_ident()
    def remove(job): calls.append((job.id, threading.get_ident())); return []
    service = FileRemovalService(manager, deleter=remove)
    jobs = [DownloadJob(MediaItem(f"https://example.test/{i}", str(i)), DownloadOptions()) for i in range(32)]
    service.completed.connect(lambda report: reports.append((report, manager.active_count)))
    service.start(jobs)
    with pytest.raises(RuntimeError): service.start(jobs)
    spin(manager)
    assert len(calls) == 32 and all(thread != main for _, thread in calls)
    assert len(reports) == 1 and reports[0][1] == 0
    assert all(not result.error for result in reports[0][0])
    assert not service.busy
    manager.shutdown()


def test_cleanup_failure_retains_separate_per_job_results_without_secret_errors():
    manager = TaskManager(); reports = []
    jobs = [DownloadJob(MediaItem("https://example.test/1", "Failure"), DownloadOptions()),
            DownloadJob(MediaItem("https://example.test/2", "Success"), DownloadOptions())]
    def remove(job):
        if job.id == jobs[0].id: raise OSError("https://user:synthetic-secret@example.test")
        return ["synthetic-owned-file"]
    service = FileRemovalService(manager, deleter=remove); service.completed.connect(reports.append)
    service.start(jobs); spin(manager)
    assert reports[0][0].error and "synthetic-secret" not in reports[0][0].error
    assert not reports[0][1].error and reports[0][1].removed == ("synthetic-owned-file",)
    manager.shutdown()


def test_oversized_cleanup_slice_is_refused_without_spawning_threads():
    manager = TaskManager(); service = FileRemovalService(manager, deleter=lambda _: [])
    job = DownloadJob(MediaItem("https://example.test/1", "Synthetic"), DownloadOptions())
    with pytest.raises(ValueError): service.start([job] * 33)
    assert manager.active_count == 0
    manager.shutdown()


def test_shutdown_releases_worker_state_without_publishing_closed_results():
    manager = TaskManager(); entered = threading.Event(); release = threading.Event(); reports = []
    def cleanup(_): entered.set(); assert release.wait(5); return []
    service = FileRemovalService(manager, deleter=cleanup); service.completed.connect(reports.append)
    service.start([DownloadJob(MediaItem("https://example.test/1", "Synthetic"), DownloadOptions())])
    assert entered.wait(2)
    service.close()
    timer = threading.Timer(.03, release.set); timer.start()
    assert manager.shutdown(1000)
    timer.join(); APP.processEvents()
    assert not service.busy and not reports
