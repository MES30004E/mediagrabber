from pathlib import Path

from morgan_media_downloader.file_ownership import (delete_owned_files, delete_restart_state,
                                                    prepare_resumable_job, primary_output, record_job_file)
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


def _job(tmp_path: Path) -> DownloadJob:
    return DownloadJob(MediaItem("url", "Readable title"), DownloadOptions(download_dir=str(tmp_path)))


def test_restart_deletes_only_recorded_partial_and_resets_transfer(tmp_path: Path):
    job = _job(tmp_path)
    partial = tmp_path / "Readable title.mp4.part"; partial.write_bytes(b"partial")
    state = tmp_path / "Readable title.mp4.ytdl"; state.write_bytes(b"state")
    unrelated = tmp_path / "family.mov"; unrelated.write_bytes(b"keep")
    record_job_file(job, partial, "partial"); record_job_file(job, state, "partial")
    job.progress = 20; job.downloaded_bytes = 10; job.total_bytes = 50; job.speed = 4; job.eta = 10
    delete_restart_state(job)
    assert not partial.exists() and not state.exists() and unrelated.exists()
    assert (job.progress, job.downloaded_bytes, job.total_bytes, job.speed, job.eta) == (0, 0, 0, 0, None)


def test_remove_from_list_equivalent_does_not_touch_owned_files(tmp_path: Path):
    job = _job(tmp_path); media = tmp_path / "Readable title.mp4"; media.write_bytes(b"media")
    record_job_file(job, media, "final")
    assert primary_output(job) == str(media.resolve())
    assert media.exists()  # Queue/database removal does not call delete_owned_files.


def test_resume_and_retry_preserve_partial_data_and_progress(tmp_path: Path):
    job = _job(tmp_path); partial = tmp_path / "video.mp4.part"; partial.write_bytes(b"partial")
    record_job_file(job, partial, "partial"); job.status = JobStatus.INTERRUPTED
    job.progress = 20; job.downloaded_bytes = 7
    prepare_resumable_job(job)
    assert job.status == JobStatus.WAITING and partial.exists()
    assert job.progress == 20 and job.downloaded_bytes == 7 and job.partial_files


def test_delete_owned_media_never_deletes_unrelated_file_or_mixed_folder(tmp_path: Path):
    folder = tmp_path / "Playlist"; folder.mkdir()
    owned = folder / "001 - Track.mp4"; owned.write_bytes(b"owned")
    unrelated = folder / "notes.txt"; unrelated.write_text("keep")
    job = _job(tmp_path); job.created_job_directory = str(folder)
    record_job_file(job, owned, "final")
    assert delete_owned_files(job, use_trash=False) == [str(owned.resolve())]
    assert not owned.exists() and unrelated.exists() and folder.exists()


def test_job_created_folder_can_be_removed_only_when_every_file_is_owned(tmp_path: Path):
    folder = tmp_path / "Album"; folder.mkdir()
    first = folder / "01.mp3"; second = folder / "02.mp3"
    first.write_bytes(b"1"); second.write_bytes(b"2")
    job = _job(tmp_path); job.created_job_directory = str(folder)
    record_job_file(job, first, "final"); record_job_file(job, second, "final")
    delete_owned_files(job, use_trash=False)
    assert not folder.exists()
