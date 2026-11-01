"""Bounded explicit restart: GUI persistence, stopped owners, worker-only cleanup."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from .file_ownership import delete_restart_state
from .logging_setup import redact_secrets
from .models import DownloadJob, JobStatus
from .queue_batch import BatchOutcome


def restart_job(job: DownloadJob, choice: str, *, cleaner=None) -> DownloadJob:
    if choice not in {"keep", "replace"}: raise ValueError("Invalid restart choice")
    if not isinstance(job.options.download_dir, str) or not job.options.download_dir.strip():
        raise ValueError("Restart requires a destination directory")
    paths = job.torrent_file_paths if job.kind == "torrent" else [job.options.filename_template]
    for value in paths:
        if (not isinstance(value, str) or not value.strip() or "\x00" in value or
                PurePosixPath(value.replace("\\", "/")).is_absolute() or PureWindowsPath(value).drive or
                ".." in PurePosixPath(value.replace("\\", "/")).parts):
            raise ValueError("Restart requires relative output paths without '..'; choose a safe filename template/destination and requeue")
    changed = copy.deepcopy(job)
    if choice == "keep":
        # Cancellation suppresses the final inventory. Even a recorded temporary
        # path might now be a finished output. Keep never deletes any old path;
        # the fresh destination, not cleanup, guarantees a from-beginning attempt.
        changed.final_files.clear(); changed.partial_files.clear(); changed.temporary_files.clear()
        changed.subtitle_files.clear(); changed.thumbnail_files.clear(); changed.output_file = ""
    (cleaner or delete_restart_state)(changed, delete_final=choice == "replace")
    # A cancelled worker's final inventory can be incomplete. Never reuse an
    # unrecorded partial, nor overwrite a fixed torrent path or final output.
    destination = Path(changed.options.download_dir) / ("restart-" + uuid4().hex)
    changed.options.download_dir = str(destination)
    changed.created_job_directory = str(destination)
    changed.final_files.clear(); changed.output_file = ""
    changed.status = JobStatus.WAITING; changed.failure_code = ""; changed.failure_stage = ""
    changed.active_extractor_task = changed.active_transfer_task = changed.active_postprocess_task = False
    changed.updated_at = datetime.now(timezone.utc).isoformat()
    return changed


@dataclass(frozen=True)
class RestartResult:
    job_id: str
    job: DownloadJob | None = None
    error: str = ""


def _detail(error) -> str:
    return redact_secrets(str(error))[:500] or type(error).__name__


def _restart_batch(jobs, choice, cancel, processor):
    results = []
    for job in jobs:
        if cancel.is_set():
            results.append(RestartResult(job.id, error="Restart interrupted; review owned files before retrying"))
            continue
        try:
            changed = processor(job, choice)
            if not isinstance(changed, DownloadJob) or changed.id != job.id or changed.status != JobStatus.WAITING:
                raise ValueError("Invalid restart result")
            results.append(RestartResult(job.id, changed))
        except Exception as error: results.append(RestartResult(job.id, error=_detail(error)))
    return tuple(results)


class QueueRestart(QObject):
    """One32-job slice/worker; QueueBatch owns admission and final accounting."""
    persisted = Signal()

    def __init__(self, manager, batch, database, jobs, active, excluded, parent=None, *, processor=None):
        super().__init__(parent)
        self.manager = manager; self.batch = batch; self.database = database
        self.jobs = jobs; self.active = active; self.excluded = excluded
        self.processor = processor or restart_job
        self.pending = {}; self._ids = (); self._task_id = ""; self._results = None; self._closed = False
        self.manager.task_finished.connect(self._task_stopped)

    def start(self, ids, choice):
        if choice not in {"keep", "replace"}: raise ValueError("Invalid restart choice")
        if self._closed: return False
        return self.batch.start(ids, lambda values: self._admit(values, choice),
            "Restart (keep outputs)" if choice == "keep" else "Restart (replace owned outputs)", wait_each_slice=True)

    def owns(self, job_id): return job_id in self._ids

    def _admit(self, ids, choice):
        eligible = [key for key in ids if key in self.jobs() and key not in self.excluded()]
        admitted = []; failures = 0
        for key in eligible:
            owner = self.active().get(key)
            if owner and not self.manager.cancel(owner): failures += 1; continue
            if owner: self.pending[key] = choice
            admitted.append(key)
        self._ids = tuple(admitted); self._choice = choice
        # Register waiting IDs before any immediate result/admission failure.
        QTimer.singleShot(0, self._ready)
        return BatchOutcome(failed=failures, skipped=len(ids)-len(eligible), waiting=self._ids,
            error="Could not stop active owner; restart not admitted" if failures else "")

    def owner_stopped(self, job_id):
        self.pending.pop(job_id, None)
        self._ready()

    def _ready(self):
        if self._closed or not self._ids or self._task_id or any(key in self.active() for key in self._ids): return
        marked = []
        try:
            for key in self._ids:
                if key not in self.jobs(): raise RuntimeError("Restart job disappeared; no cleanup admitted")
                job = copy.deepcopy(self.jobs()[key]); job.status = JobStatus.INTERRUPTED
                job.active_extractor_task = job.active_transfer_task = job.active_postprocess_task = False
                job.technical_details = "Restart cleanup pending; files may change. Review owned files before retrying if interrupted."
                marked.append(job)
            self.database.save_jobs(marked)  # Durable non-runnable state BEFORE filesystem effects.
            self.jobs().update((job.id, job) for job in marked); self.persisted.emit()
            self._task_id = "queue-restart-" + uuid4().hex; self._results = None
            snapshots = copy.deepcopy(tuple(marked))
            operation = lambda cancel, _progress, values=snapshots, choice=self._choice, processor=self.processor: _restart_batch(values, choice, cancel, processor)
            self.manager.start("queue-restart", operation, task_id=self._task_id,
                on_result=self._received, on_error=self._error, on_finished=self._finished)
        except Exception as error:
            self._task_id = ""
            self._complete(tuple(RestartResult(key, error=_detail(error)) for key in self._ids))

    def _received(self, results): self._results = results

    def _error(self, message, _details):
        self._results = tuple(RestartResult(key, error=_detail(message)) for key in self._ids)

    def _finished(self, _task_id):
        self._task_id = ""
        if not self._closed:
            self._complete(self._results or tuple(RestartResult(key, error="Restart worker did not finish; review owned files") for key in self._ids))
        self._results = None

    def _task_stopped(self, task_id, _kind):
        if task_id == self._task_id: self._finished(task_id)

    def _complete(self, results):
        ids = self._ids; self._ids = ()
        by_id = {result.job_id: result for result in results if isinstance(result, RestartResult)}
        candidates = []; errors = {}
        for key in ids:
            result = by_id.get(key); current = self.jobs().get(key)
            error = result.error if result else "Restart result missing"
            if current is None: errors[key] = "Restart job disappeared"; continue
            if not error and (not isinstance(result.job, DownloadJob) or result.job.id != key or result.job.status != JobStatus.WAITING):
                error = "Invalid restart result"
            if error:
                job = copy.deepcopy(current); job.status = JobStatus.INTERRUPTED
                job.technical_details = "Restart failed; files may already have changed. Review owned files. " + _detail(error)
                errors[key] = _detail(error)
            else: job = result.job
            candidates.append(job)
        try: self.database.save_jobs(candidates)
        except Exception as error:
            errors.update((key, _detail(error) + "; restart not published; review owned files") for key in ids)
            for key in ids:
                if job := self.jobs().get(key):
                    job.status = JobStatus.INTERRUPTED; job.technical_details = errors[key]
        else:
            self.jobs().update((job.id, job) for job in candidates)
            if candidates: self.persisted.emit()
        for key in ids:
            self.pending.pop(key, None); self.batch.settle(key, errors.get(key, ""))

    def close(self):
        self._closed = True
        if self._task_id: self.manager.cancel(self._task_id)
        self.pending.clear()
        uncertain = []
        for key in self._ids:
            if job := self.jobs().get(key):
                job.status = JobStatus.INTERRUPTED
                job.technical_details = "Restart interrupted during shutdown; files may have changed. Review owned files before retrying."
                uncertain.append(job)
        return uncertain
