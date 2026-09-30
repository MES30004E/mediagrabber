from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import DownloadJob, JobStatus
from .paths import application_support_dir


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or application_support_dir() / "downloads.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    output_file TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                """
            )

    def save_job(self, job: DownloadJob) -> None:
        payload = json.dumps(job.to_dict(), ensure_ascii=False)
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO jobs(id,status,title,source_url,output_file,created_at,updated_at,payload)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,title=excluded.title,
                   source_url=excluded.source_url,output_file=excluded.output_file,
                   updated_at=excluded.updated_at,payload=excluded.payload""",
                (job.id, job.status.value, job.item.title, job.item.source_url, job.output_file,
                 job.created_at, job.updated_at, payload),
            )

    def load_jobs(self) -> list[DownloadJob]:
        with self._lock:
            rows = self._connection.execute("SELECT payload FROM jobs ORDER BY created_at ASC").fetchall()
        jobs = []
        for row in rows:
            try:
                job = DownloadJob.from_dict(json.loads(row["payload"]))
                if job.status in {JobStatus.DOWNLOADING, JobStatus.CONVERTING, JobStatus.ANALYSING,
                                  JobStatus.FETCHING_METADATA, JobStatus.SEEDING}:
                    job.status = JobStatus.INTERRUPTED
                jobs.append(job)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
        return jobs

    def clear_completed(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM jobs WHERE status IN (?, ?)",
                                     (JobStatus.COMPLETED.value, JobStatus.COMPLETED_WARNINGS.value))

    def remove_job(self, job_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def search_history(self, query: str = "", status: str = "All") -> list[DownloadJob]:
        clauses, values = [], []
        if query:
            clauses.append("(title LIKE ? OR source_url LIKE ? OR output_file LIKE ?)")
            needle = f"%{query}%"
            values.extend([needle, needle, needle])
        if status != "All":
            clauses.append("status = ?")
            values.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM jobs" + where + " ORDER BY created_at DESC", values
            ).fetchall()
        return [DownloadJob.from_dict(json.loads(row["payload"])) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
