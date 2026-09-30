from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.ui import reconcile_stuck_job


def _job():
    job = DownloadJob(MediaItem("https://test", "Generic", source="Generic"), DownloadOptions())
    job.status = JobStatus.DOWNLOADING; job.last_state_transition = 10; job.last_progress_timestamp = 10
    return job


def test_zero_byte_zombie_becomes_explicit_failure():
    job = _job()
    assert reconcile_stuck_job(job, now=30, timeout=15)
    assert job.status == JobStatus.FAILED and job.failure_code == "Extractor returned no media"


def test_active_extractor_reconciles_generic_to_resolving_without_failure():
    job = _job(); job.active_extractor_task = True
    assert reconcile_stuck_job(job, now=30)
    assert job.status == JobStatus.ANALYSING and job.postprocessing_stage == "Resolving media"


def test_active_transfer_and_recent_progress_prevent_false_timeout():
    transfer = _job(); transfer.active_transfer_task = True
    assert not reconcile_stuck_job(transfer, now=100)
    recent = _job(); recent.last_progress_timestamp = 90
    assert not reconcile_stuck_job(recent, now=100, timeout=15)
