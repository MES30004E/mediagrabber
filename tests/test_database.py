from pathlib import Path

from morgan_media_downloader.database import Database
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


def test_queue_persistence(tmp_path: Path):
    database = Database(tmp_path / "queue.sqlite3")
    job = DownloadJob(MediaItem("https://example.com/video", "Example"), DownloadOptions(download_dir=str(tmp_path)))
    job.status = JobStatus.DOWNLOADING
    job.progress = 42.5
    database.save_job(job)
    database.close()

    reopened = Database(tmp_path / "queue.sqlite3")
    restored = reopened.load_jobs()[0]
    assert restored.item.title == "Example"
    assert restored.progress == 42.5
    assert restored.status == JobStatus.INTERRUPTED
    reopened.close()


def test_clear_completed_only_removes_completed(tmp_path: Path):
    database = Database(tmp_path / "queue.sqlite3")
    done = DownloadJob(MediaItem("a", "Done"), DownloadOptions()); done.status = JobStatus.COMPLETED
    waiting = DownloadJob(MediaItem("b", "Waiting"), DownloadOptions())
    database.save_job(done); database.save_job(waiting); database.clear_completed()
    assert [job.item.title for job in database.load_jobs()] == ["Waiting"]
    database.close()


def test_all_active_states_recover_as_interrupted(tmp_path: Path):
    database = Database(tmp_path / "downloads.sqlite3")
    active_states = (JobStatus.DOWNLOADING, JobStatus.CONVERTING, JobStatus.ANALYSING,
                     JobStatus.FETCHING_METADATA, JobStatus.SEEDING)
    for status in active_states:
        job = DownloadJob(MediaItem(f"https://example.test/{status.value}", status.value),
                          DownloadOptions(download_dir=str(tmp_path)))
        job.status = status
        database.save_job(job)
    database.close()

    restarted = Database(tmp_path / "downloads.sqlite3")
    assert len(restarted.load_jobs()) == len(active_states)
    assert {job.status for job in restarted.load_jobs()} == {JobStatus.INTERRUPTED}
    restarted.close()
