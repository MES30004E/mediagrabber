import sqlite3

import pytest

from morgan_media_downloader.database import Database
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


def fixture_jobs(count):
    return [DownloadJob(MediaItem(f"https://example.test/{i}", f"Synthetic {i}"), DownloadOptions(authentication_mode="None"))
            for i in range(count)]


def test_eight_hundred_job_save_and_remove_use_one_transaction_each(tmp_path):
    database = Database(tmp_path / "queue.sqlite3"); statements = []
    database._connection.set_trace_callback(statements.append)
    try:
        jobs = fixture_jobs(800)
        database.save_jobs(iter(jobs))
        assert sum(value == "COMMIT" for value in statements) == 1
        assert {job.id for job in database.load_jobs()} == {job.id for job in jobs}
        statements.clear()
        database.remove_jobs(job.id for job in jobs)
        assert sum(value == "COMMIT" for value in statements) == 1
        assert database.load_jobs() == []
    finally: database.close()


def test_bulk_save_rolls_back_every_row_on_mid_batch_sql_failure(tmp_path):
    database = Database(tmp_path / "queue.sqlite3")
    jobs = fixture_jobs(3)
    database.save_job(jobs[0]); jobs[0].status = JobStatus.PAUSED
    jobs[2].item.title = "reject-synthetic"
    database._connection.execute("CREATE TRIGGER reject_fixture BEFORE INSERT ON jobs WHEN NEW.title='reject-synthetic' BEGIN SELECT RAISE(ABORT,'synthetic rejection'); END")
    try:
        with pytest.raises(sqlite3.IntegrityError): database.save_jobs(jobs)
        restored = database.load_jobs()
        assert len(restored) == 1 and restored[0].status == JobStatus.WAITING
    finally: database.close()


def test_bulk_save_rolls_back_on_serialization_failure_and_can_retry(tmp_path):
    database = Database(tmp_path / "queue.sqlite3"); jobs = fixture_jobs(3)
    jobs[1].verification = {"invalid-synthetic": object()}
    try:
        with pytest.raises(TypeError): database.save_jobs(jobs)
        assert database.load_jobs() == []
        jobs[1].verification.clear(); database.save_jobs(jobs)
        assert len(database.load_jobs()) == 3
    finally: database.close()


def test_empty_batches_do_not_start_transactions_and_single_job_apis_remain_compatible(tmp_path):
    database = Database(tmp_path / "queue.sqlite3"); statements = []
    database._connection.set_trace_callback(statements.append)
    try:
        database.save_jobs(iter(())); database.remove_jobs(iter(()))
        assert not statements
        job = fixture_jobs(1)[0]; database.save_job(job); database.remove_job(job.id)
        assert database.load_jobs() == []
    finally: database.close()
