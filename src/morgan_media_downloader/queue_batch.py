"""GUI-owned bounded action admission; never creates per-job workers."""
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from .logging_setup import redact_secrets


@dataclass(frozen=True)
class BatchOutcome:
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    waiting: tuple[str, ...] = ()
    error: str = ""


class QueueBatch(QObject):
    changed = Signal(dict)
    finished = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)
        self.busy = False; self._stepping = False; self._apply = None
        self._generation = 0
        self._ids = deque()
        self._waiting = set()
        self._info = dict(label="", completed=0, failed=0, skipped=0, pending=0, cancelled=False, error="")

    def describe(self): return dict(self._info)

    def start(self, ids: Iterable[str], apply: Callable[[list[str]], int | BatchOutcome | None], label: str, *, wait_each_slice=False) -> bool:
        if self.busy: return False
        self._generation += 1; generation = self._generation
        self._wait_each_slice = wait_each_slice
        self._ids = deque(dict.fromkeys(ids)); self._apply = apply
        self._info = dict(label=label, completed=0, failed=0, skipped=0, pending=len(self._ids), cancelled=False, error="")
        self.busy = True
        self.changed.emit(self.describe())
        if self.busy and generation == self._generation: self._timer.start(0)
        return True

    def cancel(self, *, abandon=False):
        if not self.busy: return
        generation = self._generation; already_cancelled = self._info["cancelled"]
        self._info["cancelled"] = True; self._timer.stop()
        if abandon: self._waiting.clear()
        if not already_cancelled: self.changed.emit(self.describe())
        if not self.busy or generation != self._generation: return
        if not self._stepping and not self._waiting: self._finish()

    def is_waiting(self, job_id: str) -> bool: return job_id in self._waiting

    def settle(self, job_id: str, error: str = ""):
        if not self.busy or job_id not in self._waiting: return
        generation = self._generation
        self._waiting.remove(job_id)
        self._info["failed" if error else "completed"] += 1
        if error: self._info["error"] = redact_secrets(str(error))[:500]
        self._info["pending"] = len(self._ids) + len(self._waiting)
        self.changed.emit(self.describe())
        if not self.busy or generation != self._generation: return
        if not self._waiting and (self._info["cancelled"] or not self._ids): self._finish()
        elif not self._waiting and self._ids: self._timer.start(0)

    def _finish(self):
        if not self.busy: return
        self.busy = False; self._apply = None; self._ids.clear()
        self.finished.emit(self.describe())

    def _step(self):
        if not self.busy: return
        generation = self._generation
        ids = [self._ids.popleft() for _ in range(min(32, len(self._ids)))]
        self._stepping = True
        try:
            outcome = (self._apply(ids) or 0) if ids else 0
            if type(outcome) is int:
                outcome = BatchOutcome(completed=len(ids)-outcome, skipped=outcome)
            if (not isinstance(outcome, BatchOutcome) or
                    any(type(count) is not int or count < 0 for count in (outcome.completed, outcome.failed, outcome.skipped)) or
                    len(set(outcome.waiting)) != len(outcome.waiting) or not set(outcome.waiting).issubset(ids) or
                    self._waiting.intersection(outcome.waiting) or
                    outcome.completed + outcome.failed + outcome.skipped + len(outcome.waiting) != len(ids)):
                raise ValueError("Invalid batch outcome count")
            for key in ("completed", "failed", "skipped"): self._info[key] += getattr(outcome, key)
            self._waiting.update(outcome.waiting)
            if outcome.error: self._info["error"] = redact_secrets(outcome.error)[:500]
        except Exception as error:
            self._info["failed"] += len(ids)
            self._info["error"] = redact_secrets(str(error))[:500] or type(error).__name__
        finally: self._stepping = False
        self._info["pending"] = len(self._ids) + len(self._waiting)
        self.changed.emit(self.describe())
        if not self.busy or generation != self._generation: return
        if (self._info["cancelled"] or not self._ids) and not self._waiting: self._finish()
        elif self._info["cancelled"] or not self._ids: return
        elif self._wait_each_slice and self._waiting: return
        else: self._timer.start(0)
