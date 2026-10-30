"""Bounded owned cleanup worker. UI/database ownership stays with the caller."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from .file_ownership import delete_owned_files
from .logging_setup import redact_secrets


@dataclass(frozen=True)
class FileRemovalResult:
    job_id: str
    removed: tuple[str, ...] = ()
    error: str = ""


def remove_owned_batch(jobs, cancel, deleter):
    results = []
    for job in jobs:
        if cancel.is_set():
            results.append(FileRemovalResult(job.id, error="Cleanup stopped; queue entry retained"))
            continue
        try: results.append(FileRemovalResult(job.id, tuple(deleter(job))))
        except Exception as error:
            detail = redact_secrets(str(error))[:500] or type(error).__name__
            results.append(FileRemovalResult(job.id, error=detail))
    return tuple(results)


class FileRemovalService(QObject):
    completed = Signal(object)

    def __init__(self, manager, parent=None, *, deleter=None):
        super().__init__(parent)
        self.manager = manager; self.deleter = deleter or delete_owned_files
        self._task_id = ""; self._ids = (); self._results = None; self._closed = False
        self.manager.task_finished.connect(self._task_stopped)

    @property
    def busy(self): return bool(self._task_id)

    def start(self, jobs):
        if self.busy or self._closed: raise RuntimeError("Cleanup worker unavailable")
        if not 0 < len(jobs) <= 32 or len({job.id for job in jobs}) != len(jobs):
            raise ValueError("Cleanup requires 1–32 distinct jobs")
        snapshots = copy.deepcopy(tuple(jobs))
        self._ids = tuple(job.id for job in snapshots); self._results = None
        self._task_id = "queue-file-removal-" + uuid4().hex
        operation = lambda cancel, _progress, values=snapshots, deleter=self.deleter: remove_owned_batch(values, cancel, deleter)
        try:
            self.manager.start("queue-file-removal", operation, task_id=self._task_id,
                on_result=self._received, on_error=self._error, on_finished=self._finished)
        except Exception:
            self._task_id = ""; self._ids = (); self._results = None
            raise

    def _received(self, result): self._results = result

    def _error(self, message, _details):
        detail = redact_secrets(message)[:500] or "Cleanup worker failed; queue entries retained"
        self._results = tuple(FileRemovalResult(key, error=detail) for key in self._ids)

    def _finished(self, _task_id):
        results = self._results or tuple(FileRemovalResult(key, error="Cleanup did not finish; entries retained; some files may already have moved") for key in self._ids)
        self._task_id = ""; self._ids = (); self._results = None
        if not self._closed: self.completed.emit(results)

    def _task_stopped(self, task_id, _kind):
        # TaskManager deliberately suppresses user callbacks during shutdown,
        # but always emits this ownership signal after the thread has stopped.
        if task_id == self._task_id: self._finished(task_id)

    def close(self):
        self._closed = True
        if self._task_id: self.manager.cancel(self._task_id)
